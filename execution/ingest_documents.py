"""Safely extract raw text and table structure from a native PDF into `.tmp/`."""

from __future__ import annotations

import argparse
import csv
import contextlib
import hashlib
import io
import json
import multiprocessing as multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
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
OCR_RENDER_DPI = 200
OCR_CONFIDENCE_REVIEW_THRESHOLD = 0.80
OCR_PAGE_TIMEOUT_SECONDS = 20


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


def _ocr_lines(tsv_text: str) -> list[dict[str, Any]]:
    """Group Tesseract TSV tokens into visual lines without interpreting document content."""
    words: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(tsv_text), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            words.append(
                {
                    "text": text,
                    "left": int(row.get("left") or 0),
                    "top": int(row.get("top") or 0),
                    "width": int(row.get("width") or 0),
                    "height": int(row.get("height") or 0),
                }
            )
        except ValueError:
            continue

    lines: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["left"])):
        line = next(
            (
                candidate
                for candidate in reversed(lines)
                if abs(candidate["top"] - word["top"])
                <= max(8, min(candidate["height"], word["height"]) // 2)
            ),
            None,
        )
        if line is None:
            line = {"top": word["top"], "height": word["height"], "words": []}
            lines.append(line)
        line["words"].append(word)
        line["top"] = min(line["top"], word["top"])
        line["height"] = max(line["height"], word["height"])

    normalized: list[dict[str, Any]] = []
    for line in sorted(lines, key=lambda item: item["top"]):
        line_words = sorted(line["words"], key=lambda item: item["left"])
        normalized.append({"top": line["top"], "words": line_words})
    return normalized


def _reconstruct_ocr_tables(lines: list[dict[str, Any]], page_ref: str) -> list[dict[str, Any]]:
    """Recover a basic invoice-like table only when its column headers are visible."""
    expected_headers = ("description", "service", "quantity", "unit", "line")
    header_index: int | None = None
    header_positions: list[int] = []
    for index, line in enumerate(lines):
        words = line["words"]
        lowered = " ".join(word["text"] for word in words).lower()
        if all(header in lowered for header in expected_headers):
            positions: list[int] = []
            for header in expected_headers:
                match = next((word for word in words if word["text"].lower().startswith(header)), None)
                if match is None:
                    positions = []
                    break
                positions.append(match["left"])
            if len(positions) == len(expected_headers):
                header_index = index
                header_positions = positions
                break
    if header_index is None:
        return []

    # OCR text is often right-aligned within numeric columns. The next header's
    # left edge is therefore a safer boundary than the midpoint between headers.
    boundaries = header_positions[1:]
    rows: list[list[str | None]] = [["Description", "Service period", "Quantity", "Unit price", "Line total"]]
    for line in lines[header_index + 1 :]:
        words = line["words"]
        line_text = " ".join(word["text"] for word in words).lower()
        if "payment terms" in line_text:
            break
        if line_text.startswith("invoice total"):
            amount_index = next(
                (index for index, word in enumerate(words) if "$" in word["text"]),
                len(words),
            )
            label = " ".join(word["text"] for word in words[:amount_index]).strip()
            amount = " ".join(word["text"] for word in words[amount_index:]).strip()
            rows.append([None, None, None, label or None, amount or None])
            continue
        cells = [[] for _ in expected_headers]
        for word in words:
            column = next(
                (index for index, boundary in enumerate(boundaries) if word["left"] < boundary),
                len(expected_headers) - 1,
            )
            cells[column].append(word["text"])
        values = [" ".join(cell).strip() or None for cell in cells]
        if any(values):
            rows.append(values)
    if len(rows) == 1:
        return []
    return [{"table_index": 1, "page_ref": page_ref, "rows": rows}]


def _ocr_page(
    source_path: str, page_number: int, page_ref: str
) -> tuple[str, list[dict[str, Any]], float | None, str]:
    """Render a page in-process and invoke Tesseract with fixed, non-shell arguments."""
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise RuntimeError("ocr_dependency_missing")
    try:
        import pypdfium2
    except ModuleNotFoundError as error:
        raise RuntimeError("ocr_dependency_missing") from error

    with tempfile.TemporaryDirectory(prefix="ledgerguard-ocr-") as temporary_directory:
        image_path = Path(temporary_directory) / "page.png"
        document = pypdfium2.PdfDocument(source_path)
        rendered = document[page_number - 1].render(scale=OCR_RENDER_DPI / 72)
        rendered.to_pil().save(image_path, format="PNG")
        command = [tesseract, str(image_path), "stdout", "--psm", "6", "-l", "eng"]
        text_result = subprocess.run(
            command,
            cwd=temporary_directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
            timeout=OCR_PAGE_TIMEOUT_SECONDS,
        )
        tsv_result = subprocess.run(
            [*command, "-c", "tessedit_create_tsv=1"],
            cwd=temporary_directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
            timeout=OCR_PAGE_TIMEOUT_SECONDS,
        )
    if text_result.returncode != 0 or tsv_result.returncode != 0:
        raise RuntimeError("ocr_failed")

    confidence_values: list[float] = []
    for row in csv.DictReader(io.StringIO(tsv_result.stdout), delimiter="\t"):
        if not (row.get("text") or "").strip():
            continue
        try:
            confidence = float(row.get("conf") or -1)
        except ValueError:
            continue
        if confidence >= 0:
            confidence_values.append(confidence / 100)
    confidence_score = (
        round(sum(confidence_values) / len(confidence_values), 4)
        if confidence_values
        else None
    )
    lines = _ocr_lines(tsv_result.stdout)
    renderer_version = str(
        getattr(getattr(pypdfium2, "version", None), "PYPDFIUM_INFO", "unknown")
    )
    return text_result.stdout.strip(), _reconstruct_ocr_tables(lines, page_ref), confidence_score, renderer_version


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
            ocr_used = False
            ocr_confidence_scores: list[float] = []
            ocr_renderer_version: str | None = None

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

                    ocr: dict[str, Any] | None = None
                    if not text and not tables:
                        ocr_used = True
                        try:
                            ocr_text, ocr_tables, confidence_score, ocr_renderer_version = _ocr_page(
                                source_path, page_number, str(page_number)
                            )
                        except RuntimeError as error:
                            page_warnings.append(str(error))
                        except (OSError, subprocess.TimeoutExpired):
                            page_warnings.append("ocr_failed")
                        else:
                            text = ocr_text
                            for table in ocr_tables:
                                table["table_index"] = len(tables) + 1
                                tables.append(table)
                                all_tables.append(table)
                            ocr = {
                                "engine": "tesseract",
                                "confidence_score": confidence_score,
                                "render_dpi": OCR_RENDER_DPI,
                            }
                            page_warnings.append("ocr_used")
                            if confidence_score is None:
                                page_warnings.append("ocr_confidence_unavailable")
                            else:
                                ocr_confidence_scores.append(confidence_score)
                                if confidence_score < OCR_CONFIDENCE_REVIEW_THRESHOLD:
                                    page_warnings.append("low_ocr_confidence_manual_review")

                    if text or tables:
                        any_extractable_content = True
                    else:
                        page_warnings.append("no_extractable_content")
                    page_payload = {
                        "page_ref": str(page_number),
                        "text": text,
                        "tables": tables,
                        "warnings": page_warnings,
                    }
                    if ocr is not None:
                        page_payload["ocr"] = ocr
                    pages.append(page_payload)

            if ocr_used:
                extraction_warnings.append("ocr_required")
                status = "partial"
                if any(
                    "low_ocr_confidence_manual_review" in page["warnings"] for page in pages
                ):
                    extraction_warnings.append("low_ocr_confidence_manual_review")
            elif not any_extractable_content:
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
                    "ocr": {
                        "engine": "tesseract" if ocr_used else None,
                        "renderer": "pypdfium2" if ocr_used else None,
                        "renderer_version": ocr_renderer_version,
                        "confidence_score": (
                            round(sum(ocr_confidence_scores) / len(ocr_confidence_scores), 4)
                            if ocr_confidence_scores
                            else None
                        ),
                        "manual_review_threshold": OCR_CONFIDENCE_REVIEW_THRESHOLD,
                    },
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
