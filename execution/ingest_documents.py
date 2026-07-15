"""Safely extract raw text and table structure from a native PDF into `.tmp/`."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import multiprocessing as multiprocessing
import os
import sys
import uuid
import warnings
from pathlib import Path
from queue import Empty
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "raw-extractions"
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PAGES = 250
DEFAULT_TIMEOUT_SECONDS = 30


def _safe_error(code: str) -> dict[str, str]:
    """Return an error code without exposing a filename, stack trace, or document data."""
    return {"status": "failed", "error_code": code}


def _normalize_cell(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    """Write only to the caller-selected disposable artifact location."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".partial")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(path)


def _extract_in_worker(
    source_path: str,
    artifact_path: str,
    source_metadata: dict[str, str],
    max_pages: int,
    result_queue: Any,
) -> None:
    """Parse untrusted PDF content in a short-lived child process with no shell access."""
    with open(os.devnull, "w", encoding="utf-8") as devnull, contextlib.redirect_stdout(
        devnull
    ), contextlib.redirect_stderr(devnull):
        try:
            import pdfplumber
            from pypdf import PdfReader

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                reader = PdfReader(source_path, strict=False)
                if reader.is_encrypted:
                    result_queue.put(_safe_error("password_protected_pdf"))
                    return
                declared_page_count = len(reader.pages)

            if declared_page_count == 0:
                result_queue.put(_safe_error("empty_pdf"))
                return
            if declared_page_count > max_pages:
                result_queue.put(_safe_error("page_limit_exceeded"))
                return

            pages: list[dict[str, Any]] = []
            all_tables: list[dict[str, Any]] = []
            extraction_warnings: list[str] = []
            any_extractable_content = False

            with pdfplumber.open(source_path, unicode_norm="NFKC") as document:
                if len(document.pages) != declared_page_count:
                    extraction_warnings.append("page_count_mismatch")
                for page_number, page in enumerate(document.pages, start=1):
                    page_warnings: list[str] = []
                    try:
                        text = page.extract_text() or ""
                    except Exception:
                        text = ""
                        page_warnings.append("text_extraction_failed")

                    tables: list[dict[str, Any]] = []
                    try:
                        raw_tables = page.extract_tables()
                    except Exception:
                        raw_tables = []
                        page_warnings.append("table_extraction_failed")

                    for table_index, raw_table in enumerate(raw_tables, start=1):
                        if not isinstance(raw_table, list):
                            page_warnings.append("malformed_table")
                            continue
                        rows: list[list[str | None]] = []
                        for row in raw_table:
                            if not isinstance(row, list):
                                page_warnings.append("malformed_table_row")
                                continue
                            rows.append([_normalize_cell(cell) for cell in row])
                        table = {
                            "table_index": table_index,
                            "page_ref": str(page_number),
                            "rows": rows,
                        }
                        tables.append(table)
                        all_tables.append(table)

                    if text or tables:
                        any_extractable_content = True
                    else:
                        page_warnings.append("no_extractable_content")
                    pages.append(
                        {
                            "page_ref": str(page_number),
                            "text": text,
                            "tables": tables,
                            "warnings": page_warnings,
                        }
                    )

            if not any_extractable_content:
                extraction_warnings.append("ocr_required")
                status = "partial"
            elif any(page["warnings"] for page in pages):
                status = "partial"
            else:
                status = "completed"

            artifact = {
                "status": status,
                "source": source_metadata,
                "provenance": {
                    "parser": "pdfplumber",
                    "parser_version": pdfplumber.__version__,
                    "page_count": len(pages),
                },
                "raw_text": "\n\f\n".join(page["text"] for page in pages),
                "pages": pages,
                "tables": all_tables,
                "warnings": extraction_warnings,
            }
            _write_artifact(Path(artifact_path), artifact)
            result_queue.put({"status": status})
        except ModuleNotFoundError:
            result_queue.put(_safe_error("dependency_missing"))
        except Exception:
            result_queue.put(_safe_error("pdf_parse_failed"))


def _source_digest(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--document-type", default="unknown")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


def _validate_source(arguments: argparse.Namespace) -> tuple[Path | None, str | None]:
    if arguments.max_pages < 1 or arguments.timeout_seconds < 1:
        return None, "invalid_limit"
    try:
        source_path = Path(arguments.source_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "source_not_found"
    if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
        return None, "unsupported_file_type"
    try:
        if source_path.stat().st_size == 0:
            return None, "empty_file"
        if source_path.stat().st_size > MAX_FILE_BYTES:
            return None, "file_size_limit_exceeded"
        with source_path.open("rb") as source_file:
            if b"%PDF-" not in source_file.read(1024):
                return None, "invalid_pdf_signature"
    except OSError:
        return None, "source_unreadable"
    return source_path, None


def _failure_artifact(
    artifact_path: Path, document_id: str, document_type: str, error_code: str
) -> dict[str, Any]:
    artifact = {
        "status": "failed",
        "source": {"document_id": document_id, "document_type": document_type},
        "raw_text": "",
        "pages": [],
        "tables": [],
        "warnings": [error_code],
    }
    _write_artifact(artifact_path, artifact)
    return artifact


def main() -> int:
    arguments = _parse_arguments()
    document_token = hashlib.sha256(arguments.document_id.encode("utf-8")).hexdigest()[:12]
    artifact_path = DEFAULT_OUTPUT_DIR / f"{document_token}-{uuid.uuid4().hex}.json"
    source_path, validation_error = _validate_source(arguments)

    if validation_error is not None or source_path is None:
        _failure_artifact(
            artifact_path,
            arguments.document_id,
            arguments.document_type,
            validation_error or "source_validation_failed",
        )
        print(json.dumps({"status": "failed", "extraction_artifact": str(artifact_path)}))
        return 0

    source_metadata = {
        "document_id": arguments.document_id,
        "document_type": arguments.document_type,
        "source_file_name": source_path.name,
        "source_sha256": _source_digest(source_path),
    }
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    worker = context.Process(
        target=_extract_in_worker,
        args=(
            str(source_path),
            str(artifact_path),
            source_metadata,
            arguments.max_pages,
            result_queue,
        ),
        daemon=True,
    )
    worker.start()
    worker.join(arguments.timeout_seconds)
    if worker.is_alive():
        worker.terminate()
        worker.join()
        outcome: dict[str, Any] = _safe_error("parse_timeout")
    else:
        try:
            outcome = result_queue.get(timeout=1)
        except Empty:
            outcome = _safe_error("parser_worker_failed")

    if outcome["status"] == "failed":
        _failure_artifact(
            artifact_path,
            arguments.document_id,
            arguments.document_type,
            outcome["error_code"],
        )
    elif not artifact_path.is_file():
        _failure_artifact(
            artifact_path,
            arguments.document_id,
            arguments.document_type,
            "artifact_write_failed",
        )
        outcome = _safe_error("artifact_write_failed")

    print(
        json.dumps(
            {
                "status": outcome["status"],
                "extraction_artifact": str(artifact_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
