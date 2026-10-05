from __future__ import annotations
from copy import deepcopy
from typing import Any

PHASES = ("Configuration & Evaluation Metrics", "Supplier Proposals", "Execution Flow", "Results")
WORKFLOW = (
    {"key": "configure", "number": "01", "title": "Configure", "owner": "Settings + Python", "input": "Active criteria and weights", "outcome": "A validated 100% evaluation configuration."},
    {"key": "ingest", "number": "02", "title": "Ingest", "owner": "Python", "input": "Supplier metadata and proposal PDFs", "outcome": "Extracted proposal text, with the source file recorded."},
    {"key": "assess", "number": "03", "title": "Assess", "owner": "LLM or demo evaluator", "input": "Proposal text and active criteria", "outcome": "Criterion scorecards with evidence, risks, and summaries."},
    {"key": "validate", "number": "04", "title": "Validate", "owner": "Python", "input": "Raw scorecards", "outcome": "Normalized, bounded scores plus recorded warnings."},
    {"key": "score", "number": "05", "title": "Score", "owner": "Python", "input": "Validated criterion scores and weights", "outcome": "Weighted absolute score for every supplier."},
    {"key": "benchmark", "number": "06", "title": "Benchmark", "owner": "Python", "input": "All supplier scores", "outcome": "Criterion leaders, gaps, relative performance, and PPI."},
    {"key": "rank", "number": "07", "title": "Rank", "owner": "Python", "input": "PPI and tie-break data", "outcome": "Stable final ranks with a human-readable explanation."},
    {"key": "persist", "number": "08", "title": "Persist", "owner": "SQLite", "input": "Run trace and ranked results", "outcome": "Auditable RFP_RUN_ID and downloadable JSON."},
)

def initial_trace() -> dict[str, list[dict[str, Any]]]:
    return {"steps": [{"key": step["key"], "status": "pending", "summary": "Waiting to run.", "details": []} for step in WORKFLOW]}

def update_trace_step(trace: dict[str, list[dict[str, Any]]], key: str, status: str, summary: str, details: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    updated = deepcopy(trace)
    for step in updated["steps"]:
        if step["key"] == key:
            step.update(status=status, summary=summary, details=details or [])
            return updated
    raise KeyError(f"Unknown workflow step: {key}")

def trace_lookup(trace: dict[str, list[dict[str, Any]]] | None) -> dict[str, dict[str, Any]]:
    return {step["key"]: step for step in (trace or {}).get("steps", [])}
