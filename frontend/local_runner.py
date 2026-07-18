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
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SAFE_RUN_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _temp_slug(text: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text))


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


def _matching_data_rows(path: Path, sku_filter: Optional[List[str]]):
    """Return (raw_yaml_dict, matching_rows) if `path` is data-driven and
    `sku_filter` is set, else (raw_yaml_dict, None) — None means "run as-is"."""
    import yaml

    if not sku_filter:
        return None, None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None, None
    data_rows = raw.get("data")
    if not isinstance(data_rows, list) or not data_rows:
        return None, None
    wanted = {str(s) for s in sku_filter}
    rows = [r for r in data_rows if isinstance(r, dict) and str(r.get("product")) in wanted]
    return raw, rows


def _clear_runtime_scope(config) -> None:
    """Clear the runner's transient per-run variable scopes.

    TestRunner._execute_single_test/_resolve_step_params resolve each run's
    variables into `runtime_data` (priority 5) and `test_variables` (priority
    4) — both outrank `collection_vars` (3.5) — and only clear `test_variables`
    at the *start of the next* run, after it has already re-merged the stale
    value into that call's own snapshot. Since a single `config`/`TestRunner`
    is reused across multiple `.run()` calls here (once per SKU row, or once
    per case), a prior call's resolved values would otherwise outrank the
    fresh `collection_vars` just set for the next call — reusing the wrong
    SKU's values. Clear both scopes ourselves before every `.run()`.
    """
    for name in ("runtime_data", "test_variables", "session_overrides"):
        scope = config.variable_manager.get_scope(name)
        if scope is not None:
            scope.variables.clear()


def _run_one_sku_row(runner, raw: Dict[str, Any], row: Dict[str, Any], config, log_dir: Path,
                      case_stem: str) -> List[Dict[str, Any]]:
    """Run a single data-row as a standalone (non-data-driven) test and tag
    each resulting test_details entry with the row's SKU."""
    import yaml

    temp_body = dict(raw)
    temp_body.pop("data", None)
    temp_path = log_dir / f"_sku_{_temp_slug(case_stem)}_{_temp_slug(row.get('product'))}.yaml"
    with open(temp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(temp_body, f, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100000)

    _clear_runtime_scope(config)
    for key, value in row.items():
        config.set_variable(key, value if isinstance(value, (list, dict)) else str(value), scope="collection_vars")

    result = runner.run(temp_path, generate_report=False)
    product = row.get("product")
    details = list(result.test_details or [])
    for detail in details:
        if product:
            detail["name"] = f"{detail.get('name', case_stem)} — {product}"
    return details


def execute_run(store: LocalRunStore, run_id: str, config, case_paths: List[Path],
                 sku_filter: Optional[List[str]] = None) -> None:
    """Run each case through TestRunner, persisting progress after every file.

    When `sku_filter` is given, any case with a top-level `data:` block runs
    once per matching row (via a scratch copy with `data:` stripped) so each
    SKU gets its own individually-named result instead of one combined
    data-iteration entry. Cases without a `data:` block are unaffected.

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

            raw, rows = _matching_data_rows(path, sku_filter)
            if rows is not None:
                for row in rows:
                    for detail in _run_one_sku_row(runner, raw, row, config, log_dir, path.stem):
                        store.append_result(run_id, detail)
                        if detail.get("status") != "PASSED":
                            all_passed = False
                continue

            _clear_runtime_scope(config)
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
