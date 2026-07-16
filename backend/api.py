"""Minimal synchronous HTTP API for submitting one LedgerGuard document set."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from backend.agents._orchestration import PROJECT_ROOT
from backend.pipeline_runner import run_document_set

DocumentType = Literal["invoice", "contract", "statement"]
UPLOAD_DIRECTORY = PROJECT_ROOT / ".tmp" / "uploads"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PDF_CONTENT_TYPE = "application/pdf"

app = FastAPI(title="LedgerGuard API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


def _validate_upload(upload: UploadFile) -> None:
    """Reject unsupported uploads before their contents reach the pipeline."""
    filename = upload.filename or ""
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="pdf_required")
    if upload.content_type not in {PDF_CONTENT_TYPE, None}:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="pdf_content_type_required")


def _save_upload(upload: UploadFile) -> Path:
    """Store an upload under a generated name without trusting its supplied filename."""
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIRECTORY / f"{uuid.uuid4().hex}.pdf"
    partial = destination.with_suffix(".partial")
    size = 0
    signature = b""
    try:
        with partial.open("xb") as saved_file:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file_size_limit_exceeded")
                if len(signature) < 1024:
                    signature += chunk[: 1024 - len(signature)]
                saved_file.write(chunk)
        if size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_file")
        if b"%PDF-" not in signature:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="invalid_pdf_signature")
        partial.replace(destination)
        return destination
    except HTTPException:
        partial.unlink(missing_ok=True)
        raise
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="upload_save_failed") from error
    finally:
        upload.file.close()


def _validate_pdf_structure(path: Path) -> None:
    """Confirm the PDF has a readable page tree before invoking orchestration."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted or not reader.pages:
            raise ValueError("unusable_pdf")
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_pdf",
        ) from error


def _document_input(upload: UploadFile, document_type: DocumentType) -> dict[str, str]:
    saved_path = _save_upload(upload)
    return {
        "document_id": f"upload_{uuid.uuid4().hex}",
        "source_path": str(saved_path),
        "document_type": document_type,
    }


@app.post("/upload")
def upload(
    file: Annotated[UploadFile, File(description="Primary invoice, contract, or statement PDF")],
    document_type: Annotated[DocumentType, Form()],
    supporting_files: Annotated[list[UploadFile] | None, File()] = None,
    supporting_document_types: Annotated[list[DocumentType] | None, Form()] = None,
) -> dict[str, object]:
    """Save a validated PDF set, run the synchronous pipeline, and return its report payload."""
    support_files = supporting_files or []
    support_types = supporting_document_types or []
    if len(support_files) != len(support_types):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="supporting_document_types_required")

    uploads = [(file, document_type), *zip(support_files, support_types, strict=True)]
    for uploaded_file, _ in uploads:
        _validate_upload(uploaded_file)
    documents = [
        _document_input(uploaded_file, uploaded_type)
        for uploaded_file, uploaded_type in uploads
    ]
    for document in documents:
        _validate_pdf_structure(Path(document["source_path"]))
    try:
        result = run_document_set(documents=documents, user_id="anonymous")
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="pipeline_failed") from error
    return result["synthesis"]["report_payload"]
