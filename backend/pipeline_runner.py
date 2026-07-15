"""Wire the LedgerGuard stages for one document through to synthesized output."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.agents import (
    contract_drift_agent,
    duplicate_agent,
    pricing_agent,
    synthesis_agent,
    triage_agent,
)
from backend.agents._orchestration import PROJECT_ROOT, call_execution

Executor = Callable[[str, list[str]], dict[str, Any]]
Investigator = Callable[..., dict[str, Any]]
DocumentInput = Mapping[str, str | None]

_INVESTIGATORS: dict[str, Investigator] = {
    "pricing": pricing_agent.investigate,
    "duplicate": duplicate_agent.investigate,
    "contract_drift": contract_drift_agent.investigate,
}


def _write_verdict_artifact(verdicts: list[dict[str, Any]]) -> Path:
    """Materialize orchestration output only long enough for the synthesis script to read it."""
    temporary_dir = PROJECT_ROOT / ".tmp"
    temporary_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="investigation-verdicts-",
        dir=temporary_dir,
        delete=False,
    ) as artifact:
        json.dump(verdicts, artifact)
        return Path(artifact.name)


def _investigate(
    queue_item: Mapping[str, Any], user_id: str, executor: Executor
) -> dict[str, Any]:
    """Delegate one routed item to its independently callable investigation agent."""
    investigation_type = queue_item["suggested_investigation_type"]
    investigator = _INVESTIGATORS[investigation_type]
    investigation_executor = (
        call_execution
        if investigation_type in {"pricing", "duplicate", "contract_drift"}
        else executor
    )
    return {
        "candidate_id": queue_item["candidate_id"],
        "investigation_type": investigation_type,
        "verdict": investigator(
            queue_item["candidate_id"], user_id, executor=investigation_executor
        ),
    }


def _document_set(
    documents: Sequence[DocumentInput] | None,
    document_id: str | None,
    source_path: str | None,
    document_type: str | None,
) -> list[DocumentInput]:
    """Accept a complete document set while preserving the original single-document API."""
    if documents is not None:
        if not documents:
            raise ValueError("documents_must_not_be_empty")
        return list(documents)
    if not document_id or not source_path:
        raise ValueError("document_id_and_source_path_required")
    return [
        {
            "document_id": document_id,
            "source_path": source_path,
            "document_type": document_type or "unknown",
        }
    ]


def run_document_set(
    *,
    documents: Sequence[DocumentInput] | None = None,
    document_id: str | None = None,
    source_path: str | None = None,
    document_type: str | None = None,
    user_id: str,
    rule_config: str | None = None,
    executor: Executor = call_execution,
) -> dict[str, Any]:
    """Run real deterministic stages, then use the injected executor for Layer 2 agents."""
    document_set = _document_set(documents, document_id, source_path, document_type)
    ingestions = [
        call_execution(
            "ingest_documents.py",
            [
                "--document-id",
                str(document["document_id"]),
                "--source-path",
                str(document["source_path"]),
                "--document-type",
                str(document.get("document_type") or "unknown"),
            ],
        )
        for document in document_set
    ]
    normalization_arguments = [
        argument
        for ingestion in ingestions
        for argument in ("--extraction-artifact", ingestion["extraction_artifact"])
    ]
    normalization_arguments.extend(("--user-id", user_id))
    normalization = call_execution("normalize_data.py", normalization_arguments)
    rules_arguments = ["--normalized-records", normalization["normalized_records"]]
    if rule_config is not None:
        rules_arguments.extend(("--rule-config", rule_config))
    rules = call_execution("rules_engine.py", rules_arguments)
    triage = triage_agent.triage(
        rules["rule_run_id"], user_id, executor=call_execution
    )
    routed_items = [
        item
        for item in triage["triage_queue"]
        if item["suggested_investigation_type"] in _INVESTIGATORS
    ]

    with ThreadPoolExecutor(max_workers=max(1, len(routed_items))) as pool:
        futures = [
            pool.submit(_investigate, item, user_id, executor) for item in routed_items
        ]
        investigations = [future.result() for future in futures]

    verdict_artifact = _write_verdict_artifact(investigations)
    try:
        synthesis = synthesis_agent.synthesize(
            str(verdict_artifact), user_id, executor=call_execution
        )
    finally:
        verdict_artifact.unlink(missing_ok=True)

    return {
        "ingestion": ingestions,
        "normalization": normalization,
        "rules": rules,
        "triage": triage,
        "investigations": investigations,
        "synthesis": synthesis,
    }
