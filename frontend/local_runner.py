"""Local test-run orchestrator + persisted run history.

Executes selected local case files through easybdd.core.runner.TestRunner —
the same engine every other entry point (CLI, MCP server, TestRail runner)
uses — and persists a run record to reports/local_runs/<run_id>.json. The
per-case shape stored in `test_details` is exactly what
easybdd.core.runner.TestResult.test_details already produces (the same
shape TestRailRunner._run_yaml_files accumulates); this module only adds a
run-level envelope and disk persistence on top, so run history survives a
service restart instead of living only in memory.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SAFE_RUN_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"


class LocalRunStore:
    """Reads/writes run records as JSON files under `runs_dir`."""

    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not run_id or any(c not in _SAFE_RUN_ID for c in run_id):
            raise ValueError("Invalid run id")
        return self.runs_dir / f"{run_id}.json"

    def _write(self, record: Dict[str, Any]) -> None:
        path = self._path(record["run_id"])
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)
        tmp.replace(path)

    def create(self, run_id: str, name: str, project_id: str, case_ids: List[str]) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "run_id": run_id,
            "name": name,
            "project_id": project_id,
            "case_ids": case_ids,
            "status": "running",
            "started": datetime.now(timezone.utc).isoformat(),
            "finished": None,
            "counts": {"passed": 0, "failed": 0},
            "total": 0,
            "test_details": [],
        }
        self._write(record)
        return record

    def get(self, run_id: str) -> Dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            raise FileNotFoundError(run_id)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def append_result(self, run_id: str, detail: Dict[str, Any]) -> None:
        record = self.get(run_id)
        record["test_details"].append(detail)
        record["total"] = len(record["test_details"])
        record["counts"] = {
            "passed": sum(1 for d in record["test_details"] if d.get("status") == "PASSED"),
            "failed": sum(1 for d in record["test_details"] if d.get("status") != "PASSED"),
        }
        self._write(record)

    def finish(self, run_id: str, success: bool) -> None:
        record = self.get(run_id)
        record["status"] = "completed" if success else "failed"
        record["finished"] = datetime.now(timezone.utc).isoformat()
        self._write(record)

    def error(self, run_id: str, message: str) -> None:
        record = self.get(run_id)
        record["status"] = "error"
        record["finished"] = datetime.now(timezone.utc).isoformat()
        record["error"] = message
        self._write(record)

    def list(self, project_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        records = []
        for p in self.runs_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    r = json.load(f)
            except Exception:
                continue
            if project_id and r.get("project_id") != project_id:
                continue
            records.append(r)
        records.sort(key=lambda r: r.get("started") or "", reverse=True)
        return records[: max(1, min(limit, 200))]


def run_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: record.get(k) for k in
            ("run_id", "name", "project_id", "status", "started", "finished", "counts", "total")}


def execute_run(store: LocalRunStore, run_id: str, config, case_paths: List[Path]) -> None:
    """Run each case through TestRunner, persisting progress after every file.

    Intended to run as a FastAPI background task — never raises; execution
    errors are recorded on the run itself via store.error().
    """
    from easybdd.core.runner import TestRunner

    log_dir = store.runs_dir / "_logs" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    runner = TestRunner(config, log_dir=log_dir)

    all_passed = True
    try:
        for path in case_paths:
            if not path.exists():
                store.append_result(run_id, {"name": str(path), "status": "FAILED", "error": "File not found"})
                all_passed = False
                continue
            result = runner.run(path, generate_report=False)
            for detail in (result.test_details or []):
                store.append_result(run_id, detail)
            if not result.success:
                all_passed = False
        store.finish(run_id, all_passed)
    except Exception as exc:
        store.error(run_id, str(exc))


def report_context(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a TestResult.test_details entry to report_generator's expected shape."""
    step_logs = detail.get("step_logs") or []
    return {
        "test_name": detail.get("name", "unknown"),
        "success": detail.get("status") == "PASSED",
        "test_type": "local",
        "duration": detail.get("execution_time", 0),
        "steps_passed": sum(1 for s in step_logs if s.get("status") == "passed"),
        "steps_total": len(step_logs),
        "output": detail.get("execution_log", ""),
        "logs": (detail.get("execution_log") or "").splitlines(),
    }
