from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .models import Criterion, RankedSupplier

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_criteria (
  criterion_id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
  weight REAL NOT NULL, max_score REAL NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS rfp_runs (
  rfp_run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
  error_message TEXT, trace_json TEXT NOT NULL DEFAULT '{\"steps\": []}');
CREATE TABLE IF NOT EXISTS supplier_results (
  rfp_run_id TEXT NOT NULL, supplier_name TEXT NOT NULL, submission_date TEXT NOT NULL,
  experience_rating REAL NOT NULL, absolute_score REAL NOT NULL, ppi REAL NOT NULL,
  final_rank INTEGER NOT NULL, result_json TEXT NOT NULL,
  PRIMARY KEY (rfp_run_id, supplier_name), FOREIGN KEY (rfp_run_id) REFERENCES rfp_runs(rfp_run_id));
"""
SEED = [(1, "Technical Capability", "Architecture, integrations, scalability, technical fit", 30, 10, 1),
        (2, "Implementation Plan", "Timeline, milestones, staffing, risk plan", 20, 10, 1),
        (3, "Commercial Value", "Pricing clarity, total cost, assumptions", 20, 10, 1),
        (4, "Security & Compliance", "Controls, certifications, privacy, auditability", 20, 10, 1),
        (5, "Support & Experience", "Support model, similar projects, references", 10, 10, 1)]

def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection

def initialize(path: str | Path) -> None:
    with connect(path) as db:
        db.executescript(SCHEMA)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(rfp_runs)")}
        if "error_message" not in columns: db.execute("ALTER TABLE rfp_runs ADD COLUMN error_message TEXT")
        if "trace_json" not in columns: db.execute("ALTER TABLE rfp_runs ADD COLUMN trace_json TEXT NOT NULL DEFAULT '{\"steps\": []}'")
        db.executemany("INSERT OR IGNORE INTO evaluation_criteria VALUES (?, ?, ?, ?, ?, ?)", SEED)

def active_criteria(path: str | Path) -> list[Criterion]:
    with connect(path) as db:
        rows = db.execute("SELECT * FROM evaluation_criteria WHERE is_active = 1 ORDER BY criterion_id").fetchall()
    return [Criterion(**(dict(row) | {"is_active": bool(row["is_active"])})) for row in rows]

def all_criteria(path: str | Path) -> list[Criterion]:
    with connect(path) as db:
        rows = db.execute("SELECT * FROM evaluation_criteria ORDER BY criterion_id").fetchall()
    return [Criterion(**(dict(row) | {"is_active": bool(row["is_active"])})) for row in rows]

def update_criteria(path: str | Path, criteria: list[Criterion]) -> None:
    active_weight = sum(item.weight for item in criteria if item.is_active)
    if not any(item.is_active for item in criteria): raise ValueError("At least one criterion must remain active.")
    if abs(active_weight - 100) > 0.001: raise ValueError(f"Active criteria weights must total 100; got {active_weight:g}.")
    with connect(path) as db:
        db.executemany("UPDATE evaluation_criteria SET weight = ?, is_active = ? WHERE criterion_id = ?", [(item.weight, int(item.is_active), item.criterion_id) for item in criteria])

def create_run(path: str | Path) -> str:
    run_id = f"RFP-{uuid4().hex[:10].upper()}"
    with connect(path) as db:
        db.execute("INSERT INTO rfp_runs (rfp_run_id, created_at, status, error_message, trace_json) VALUES (?, ?, ?, ?, ?)", (run_id, datetime.now(timezone.utc).isoformat(), "running", None, json.dumps({"steps": []})))
    return run_id

def update_run_trace(path: str | Path, run_id: str, trace: dict) -> None:
    with connect(path) as db: db.execute("UPDATE rfp_runs SET trace_json = ? WHERE rfp_run_id = ?", (json.dumps(trace), run_id))

def complete_run(path: str | Path, run_id: str, results: list[RankedSupplier], trace: dict | None = None) -> None:
    with connect(path) as db:
        db.executemany("INSERT INTO supplier_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(run_id, r.supplier_name, r.submission_date.isoformat(), r.experience_rating, r.absolute_score, r.ppi, r.final_rank, r.model_dump_json()) for r in results])
        if trace is None: db.execute("UPDATE rfp_runs SET status = ?, error_message = NULL WHERE rfp_run_id = ?", ("completed", run_id))
        else: db.execute("UPDATE rfp_runs SET status = ?, error_message = NULL, trace_json = ? WHERE rfp_run_id = ?", ("completed", json.dumps(trace), run_id))

def fail_run(path: str | Path, run_id: str, error_message: str) -> None:
    with connect(path) as db: db.execute("UPDATE rfp_runs SET status = ?, error_message = ? WHERE rfp_run_id = ?", ("failed", error_message[:1000], run_id))

def persist_run(path: str | Path, results: list[RankedSupplier]) -> str:
    run_id = create_run(path); complete_run(path, run_id, results); return run_id

def export_run(path: str | Path, run_id: str) -> dict:
    with connect(path) as db:
        run = db.execute("SELECT * FROM rfp_runs WHERE rfp_run_id = ?", (run_id,)).fetchone()
        rows = db.execute("SELECT result_json FROM supplier_results WHERE rfp_run_id = ? ORDER BY final_rank", (run_id,)).fetchall()
    run_data = dict(run); run_data["trace"] = json.loads(run_data.pop("trace_json", '{"steps": []}'))
    return {"run": run_data, "supplier_results": [json.loads(row["result_json"]) for row in rows]}
