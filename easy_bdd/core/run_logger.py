"""
Step-level run logger for Easy BDD.

Mirrors the mybdd/app_logger.py console format:
  ──────────── Step N/total ────────────
  <-- action: key=value ...
  response_txt: ...
  response_dict: { ... }
  ✅ Step N passed (0.2s)

Two sinks:
  - stdout  : INFO, no timestamp, colorized (matches mybdd console)
  - file    : DEBUG, timestamped, full detail  → <artifact_dir>/console.log
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


# ── loguru setup ──────────────────────────────────────────────────────────────

try:
    from loguru import logger as _loguru
    _HAS_LOGURU = True
except ImportError:
    _HAS_LOGURU = False


class RunLogger:
    """Structured step logger with stdout + file sinks."""

    SEP_WIDTH = 44

    def __init__(self, artifact_dir: Optional[Path] = None):
        self._artifact_dir = Path(artifact_dir) if artifact_dir else None
        self._step_start_time: float = 0.0
        self._logger = None
        self._file_sink_id = None
        self._configure()

    # ── setup ─────────────────────────────────────────────────────────────────

    def _configure(self) -> None:
        if not _HAS_LOGURU:
            return

        lg = _loguru
        lg.remove()

        # stdout sink — plain message only, colorized, INFO and below WARNING
        lg.add(
            sys.stdout,
            level="INFO",
            format="{message}",
            colorize=True,
            filter=lambda r: r["level"].no < lg.level("WARNING").no,
        )

        # stderr sink — WARNING+, plain message
        lg.add(
            sys.stderr,
            level="WARNING",
            format="<yellow>{message}</yellow>",
            colorize=True,
        )

        if self._artifact_dir:
            self._artifact_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._artifact_dir / "console.log"
            self._file_sink_id = lg.add(
                str(log_path),
                level="DEBUG",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
                backtrace=True,
                diagnose=True,
                enqueue=True,
                rotation="10 MB",
                retention="7 days",
            )

        self._logger = lg

    def _info(self, msg: str) -> None:
        if self._logger:
            self._logger.opt(depth=2).info(msg)
        else:
            print(msg)

    def _debug(self, msg: str) -> None:
        if self._logger:
            self._logger.opt(depth=2).debug(msg)

    def _warn(self, msg: str) -> None:
        if self._logger:
            self._logger.opt(depth=2).warning(msg)
        else:
            print(f"WARNING: {msg}")

    # ── public API ────────────────────────────────────────────────────────────

    def test_start(self, name: str) -> None:
        self._info(f"\nExecuting: {name}")

    def test_pass(self, name: str, elapsed: float) -> None:
        self._info(f"  ✅ PASSED: {name} ({elapsed:.1f}s)")

    def test_fail(self, name: str, elapsed: float) -> None:
        self._info(f"  ❌ FAILED: {name} ({elapsed:.1f}s)")

    def phase(self, label: str) -> None:
        self._info(f"\n    === {label} ===")

    def step_start(self, n: int, total: int, action: str, params: Dict[str, Any]) -> None:
        self._step_start_time = time.time()
        sep = "─" * self.SEP_WIDTH
        self._info(f"\n    {sep}")
        self._info(f"    Step {n}/{total}: {action}")

        # Show every param as its own indented line (easier to read than one long line)
        SKIP = {"action", "condition", "then_steps", "else_steps", "steps",
                "loop_var", "for_each", "while_condition"}
        pairs = [(k, v) for k, v in params.items() if k not in SKIP]
        if pairs:
            self._info(f"    Params:")
            for k, v in pairs:
                v_str = _truncate(str(v), 200)
                self._info(f"      {k}: {v_str}")

    def step_pass(self, n: int, variables: Dict[str, Any], prev_response: Any) -> None:
        elapsed = time.time() - self._step_start_time
        _log_response(self._info, variables, prev_response)
        self._info(f"    ✅ Step {n} passed ({elapsed:.2f}s)")

    def step_fail(
        self,
        n: int,
        action: str,
        error: str,
        details: str = "",
        traceback_str: str = "",
    ) -> None:
        elapsed = time.time() - self._step_start_time
        self._warn(f"\n    ❌ STEP {n} FAILED: {action} ({elapsed:.2f}s)")
        if error:
            self._warn(f"    Error: {error}")
        if details:
            self._warn(f"    Details: {details}")
        if traceback_str:
            # Write full traceback to file only (DEBUG)
            self._debug(f"Traceback:\n{traceback_str}")
            # Print last two lines to console
            lines = [l for l in traceback_str.strip().splitlines() if l.strip()]
            if lines:
                self._warn(f"    {lines[-1]}")

    def shared_step(self, name: str, result: str) -> None:
        label = "passed" if result == "passed" else f"❌ {result}"
        self._info(f"    → shared_step: {name} ... {label}")

    def close(self) -> None:
        if self._logger and self._file_sink_id is not None:
            try:
                self._logger.remove(self._file_sink_id)
            except Exception:
                pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _format_params(action: str, params: Dict[str, Any]) -> list[str]:
    """Format step params into display lines (mybdd <-- style)."""
    if not params:
        return [action]

    SKIP = {"action", "shared_step", "condition", "then_steps", "else_steps", "steps",
            "loop_var", "for_each", "while_condition"}
    pairs = [(k, v) for k, v in params.items() if k not in SKIP]
    if not pairs:
        return [action]

    # First line: action key=value for short params
    first_key, first_val = pairs[0]
    first_val_str = _truncate(str(first_val), 80)
    lines = [f"{action}  {first_key}={first_val_str}"]
    for k, v in pairs[1:]:
        lines.append(f"{k}={_truncate(str(v), 100)}")
    return lines


def _log_response(log_fn, variables: Dict[str, Any], prev_response: Any) -> None:
    """Print response details if anything changed since the last step."""
    current = variables.get("last_response")
    if current is not None and current != prev_response:
        status = variables.get("last_status_code")
        if status:
            log_fn(f"    response_status: {status}")

        txt = str(current)
        if txt != str(prev_response):
            log_fn(f"    response_txt: {_truncate(txt, 300)}")

        # Pretty-print JSON body if available
        resp_dict = variables.get("last_response_dict")
        if resp_dict and isinstance(resp_dict, dict):
            try:
                dict_str = json.dumps(resp_dict, ensure_ascii=False, indent=2)
                log_fn(f"    response_dict:\n{_indent(dict_str, '      ')}")
            except Exception:
                pass
        elif not resp_dict and txt:
            try:
                parsed = json.loads(txt)
                dict_str = json.dumps(parsed, ensure_ascii=False, indent=2)
                log_fn(f"    response_dict:\n{_indent(dict_str, '      ')}")
            except Exception:
                pass


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())
