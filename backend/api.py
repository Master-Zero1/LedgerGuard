"""Minimal synchronous HTTP API for submitting one LedgerGuard document set."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from backend.agents._orchestration import PROJECT_ROOT
from backend.agents import dispute_agent
from backend.pipeline_runner import run_document_set
from backend.report_export import render_report_pdf

DocumentType = Literal["invoice", "contract", "statement"]
UPLOAD_DIRECTORY = PROJECT_ROOT / ".tmp" / "uploads"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PDF_CONTENT_TYPE = "application/pdf"
REPORT_ARTIFACTS: dict[str, Path] = {}
ANALYSIS_JOBS: dict[str, dict[str, Any]] = {}
ANALYSIS_JOBS_LOCK = Lock()

app = FastAPI(title="LedgerGuard API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class DraftRequest(BaseModel):
    """Browser-safe reference to one confirmed discrepancy in an uploaded report."""

    report_id: str
    discrepancy_id: str


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


def _prepare_documents(
    file: UploadFile,
    document_type: DocumentType,
    supporting_files: list[UploadFile] | None,
    supporting_document_types: list[DocumentType] | None,
) -> list[dict[str, str]]:
    """Apply the same upload validation and persistence behavior for both submission paths."""
    support_files = supporting_files or []
    support_types = supporting_document_types or []
    if len(support_files) != len(support_types):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="supporting_document_types_required")
    uploads = [(file, document_type), *zip(support_files, support_types, strict=True)]
    for uploaded_file, _ in uploads:
        _validate_upload(uploaded_file)
    documents = [_document_input(uploaded_file, uploaded_type) for uploaded_file, uploaded_type in uploads]
    for document in documents:
        _validate_pdf_structure(Path(document["source_path"]))
    return documents


def _report_response(result: dict[str, Any]) -> dict[str, Any]:
    """Store a synthesis artifact and return the public report shape used by /upload."""
    report_artifact = result["synthesis"].get("report_artifact")
    if not isinstance(report_artifact, str):
        raise ValueError("report_unavailable")
    report_payload = result["synthesis"].get("report_payload")
    if not isinstance(report_payload, dict):
        raise ValueError("report_unavailable")
    report_id = uuid.uuid4().hex
    REPORT_ARTIFACTS[report_id] = Path(report_artifact)
    return {**report_payload, "report_id": report_id}


def _set_job_stage(job_id: str, stage: str, completed: bool = False) -> None:
    """Update transient job state from pipeline_runner's status callback."""
    with ANALYSIS_JOBS_LOCK:
        job = ANALYSIS_JOBS.get(job_id)
        if job is None:
            return
        if completed:
            completed_stages = job.setdefault("completed_stages", [])
            if stage not in completed_stages:
                completed_stages.append(stage)
        else:
            job["stage"] = stage


def _run_analysis_job(job_id: str, documents: list[dict[str, str]]) -> None:
    """Execute one analysis after its upload request has returned 202 Accepted."""
    try:
        result = run_document_set(
            documents=documents,
            user_id="anonymous",
            status_update=lambda stage, completed=False: _set_job_stage(job_id, stage, completed),
        )
        report = _report_response(result)
    except Exception:
        with ANALYSIS_JOBS_LOCK:
            job = ANALYSIS_JOBS.get(job_id)
            if job is not None:
                job["stage"] = "failed"
                job["error"] = "analysis_failed"
        return
    with ANALYSIS_JOBS_LOCK:
        job = ANALYSIS_JOBS.get(job_id)
        if job is not None:
            job["stage"] = "complete"
            job["report"] = report


@app.post("/upload")
def upload(
    file: Annotated[UploadFile, File(description="Primary invoice, contract, or statement PDF")],
    document_type: Annotated[DocumentType, Form()],
    supporting_files: Annotated[list[UploadFile] | None, File()] = None,
    supporting_document_types: Annotated[list[DocumentType] | None, Form()] = None,
) -> dict[str, Any]:
    """Save a validated PDF set, run the synchronous pipeline, and return its report payload."""
    documents = _prepare_documents(file, document_type, supporting_files, supporting_document_types)
    try:
        result = run_document_set(documents=documents, user_id="anonymous")
        return _report_response(result)
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="pipeline_failed") from error


@app.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Primary invoice, contract, or statement PDF")],
    document_type: Annotated[DocumentType, Form()],
    supporting_files: Annotated[list[UploadFile] | None, File()] = None,
    supporting_document_types: Annotated[list[DocumentType] | None, Form()] = None,
) -> JSONResponse:
    """Accept a document set and begin background analysis without changing /upload behavior."""
    documents = _prepare_documents(file, document_type, supporting_files, supporting_document_types)
    job_id = uuid.uuid4().hex
    with ANALYSIS_JOBS_LOCK:
        ANALYSIS_JOBS[job_id] = {"stage": "queued", "completed_stages": []}
    background_tasks.add_task(_run_analysis_job, job_id, documents)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"job_id": job_id, "stage": "queued"})


@app.get("/status/{job_id}")
def analysis_status(job_id: str) -> dict[str, Any]:
    """Return transient analysis progress and the /upload-compatible report when complete."""
    with ANALYSIS_JOBS_LOCK:
        job = ANALYSIS_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
        response = {
            "job_id": job_id,
            "stage": job["stage"],
            "completed_stages": list(job.get("completed_stages", [])),
        }
        if job["stage"] == "complete":
            return {**response, **job["report"]}
        if job["stage"] == "failed":
            response["error"] = job["error"]
        return response


@app.post("/draft")
def draft_dispute(request: DraftRequest) -> dict[str, Any]:
    """Create one evidence-grounded email draft; this endpoint never sends email."""
    report_artifact = REPORT_ARTIFACTS.get(request.report_id)
    if report_artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_not_found")
    try:
        draft = dispute_agent.draft(
            request.discrepancy_id,
            "anonymous",
            report_artifact=str(report_artifact),
        )
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="draft_unavailable") from error
    if draft.get("status") != "draft":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="draft_requires_confirmed_evidence")
    return draft


@app.get("/report/{report_id}/download")
def download_report(report_id: str) -> Response:
    """Return a PDF export from the server-stored report payload only."""
    report_artifact = REPORT_ARTIFACTS.get(report_id)
    if report_artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_not_found")
    try:
        artifact = json.loads(report_artifact.read_text(encoding="utf-8"))
        report = artifact.get("report_payload") if isinstance(artifact, dict) else None
        if not isinstance(report, dict):
            raise ValueError("invalid_report")
        pdf = render_report_pdf({**report, "report_id": report_id})
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="report_export_unavailable") from error
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ledgerguard-report-{report_id[:8]}.pdf"',
            "Cache-Control": "no-store, max-age=0",
        },
    )
