"""
TestRail-driven test runner for Easy BDD Framework.

Lifecycle (6 phases):
  1. find_run      — scan project for EASY_BDD: run with pending tests
  2. prepare_run   — fetch tests, parse run_vars from description
  3. cron_gate     — skip all if outside cron window
  4. execute_tests — resolve each case to YAML, run it, post result in real-time
  5. finalize_run  — write result summary back to run description
  6. retry_loop    — if retry > 0, mark failed as retest and loop from phase 4

Case prefix taxonomy:
  Var: <name>       — key: value pairs injected as variables into every test
  Setup: <name>     — executes before Test: cases
  Test: <name>      — main test case (body: tag: or file: pointer to local YAML)
  Inline: <name>    — main test case (steps written directly in TestRail fields)
  Teardown: <name>  — executes after all Test: cases

Test: case body format (Steps/Preconditions field):
  tag: <tag>    — run all local YAML tests in tests/cases/ that have this tag
  file: <path>  — run a specific YAML file (relative to tests/cases/ or absolute)

Inline: case body formats:
  Option A — Steps field contains a YAML steps list:
    - action: browser.open
      url: ${base_url}
    - action: browser.click
      role: button
      name: Login

  Option B — "Steps (Separated)" TestRail case type (recommended for teams):
    Step Description column: Easy BDD action YAML, one step per row:
      action: browser.fill
      field: "#username"
      value: ${username}
    Expected Result column: Python expression or natural language:
      Python   →  'Dashboard' in page_content   (becomes test.assert)
      Natural  →  Page shows the dashboard       (becomes soft test.assert with message)

  Preconditions field (both options):
    Parsed as key: value variable pairs (merged with Var: case variables):
      base_url: https://staging.example.com
      username: admin

Variable injection (Var: case body):
  base_url: https://staging.example.com
  username: testuser
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .runner import TestResult, TestRunner
from .variable_manager import GlobalConfigManager
from ..services.testrail_service import RunVariables, TestRailService, TestRailError


# Ordered prefix → role mapping (order matters: longest prefix checked first)
_CASE_ROLES: Dict[str, str] = {
    "Teardown:": "teardown",
    "Keyword:":  "keyword",
    "Inline:":   "inline",
    "Setup:":    "setup",
    "Test:":     "test",
    "Var:":      "var",
}


def _classify(title: str) -> str:
    for prefix, role in _CASE_ROLES.items():
        if title.startswith(prefix):
            return role
    return "unknown"


def _strip_prefix(title: str) -> str:
    for prefix in _CASE_ROLES:
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title.strip()


def _format_elapsed(seconds: float) -> str:
    seconds = max(1, int(seconds))
    minutes = seconds // 60
    secs = seconds % 60
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _cron_in_window(cron: str, now: datetime = None) -> bool:
    """Return True if a 5-field cron expression matches within a ±5 minute window."""
    now = now or datetime.now()
    parts = cron.strip().split()
    if len(parts) != 5:
        return False
    minute_f, hour_f, day_f, month_f, weekday_f = parts

    def expand(field: str) -> set:
        result: set = set()
        for token in field.split(","):
            token = token.strip()
            if token == "*":
                result.update(range(0, 100))
            elif token.startswith("*/"):
                step = int(token[2:])
                result.update(range(0, 100, max(1, step)))
            elif "-" in token:
                a, b = token.split("-", 1)
                result.update(range(int(a), int(b) + 1))
            else:
                try:
                    result.add(int(token))
                except ValueError:
                    pass
        return result

    minutes_set = expand(minute_f)
    hours_set = expand(hour_f)
    days_set = expand(day_f)
    months_set = expand(month_f)

    start = (now - timedelta(minutes=5)).replace(second=0, microsecond=0)
    for offset in range(11):
        candidate = start + timedelta(minutes=offset)
        if abs((now - candidate).total_seconds()) > 300:
            continue
        if (
            candidate.minute in minutes_set
            and candidate.hour in hours_set
            and candidate.day in days_set
            and candidate.month in months_set
        ):
            return True
    return False


def _get_case_body(test: Dict[str, Any]) -> str:
    """Extract case body text from a TestRail test object.

    Checks in order: custom_steps_separated (structured), custom_steps (text),
    custom_preconds (preconditions text).
    """
    steps = test.get("custom_steps_separated")
    if steps and isinstance(steps, list):
        parts = [
            part
            for step in steps
            if isinstance(step, dict)
            for part in (step.get("content", ""), step.get("expected", ""))
            if part
        ]
        if parts:
            return "\n".join(parts)

    for field in ("custom_steps", "custom_preconds"):
        value = test.get(field)
        if value:
            return str(value)
    return ""


def _parse_preconds_vars(test: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the Preconditions field as key: value variable pairs.

    Tries YAML first, then falls back to line-by-line splitting on the first colon.
    """
    import yaml as _yaml
    text = (test.get("custom_preconds") or "").strip()
    if not text:
        return {}
    try:
        parsed = _yaml.safe_load(text)
        if isinstance(parsed, dict):
            return {str(k): _coerce(str(v)) for k, v in parsed.items()}
    except Exception:
        pass
    variables: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith(("#", "-")):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key:
                variables[key] = _coerce(value)
    return variables


# Tokens that suggest a string is a Python expression rather than natural language
_EXPR_SIGNALS = ("==", "!=", " in ", " not in ", " is ", " is not ", " and ", " or ",
                 ">(", ">=", "<=", "<(", "(", ".", "[")


def _parse_structured_steps(test: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map custom_steps_separated rows to Easy BDD step dicts (Option B).

    Each row:
      content  → parsed as an action YAML dict; plain text becomes test.log
      expected → Python expression becomes test.assert; natural language
                 becomes a soft test.assert with the text as the message
    """
    import yaml as _yaml
    rows = test.get("custom_steps_separated") or []
    if not isinstance(rows, list):
        return []
    steps: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        content  = (row.get("content")  or "").strip()
        expected = (row.get("expected") or "").strip()
        if content:
            try:
                parsed = _yaml.safe_load(content)
                if isinstance(parsed, dict):
                    steps.append(parsed)
                elif isinstance(parsed, list):
                    steps.extend(s for s in parsed if isinstance(s, dict))
                else:
                    steps.append({"action": "test.log", "message": content})
            except Exception:
                steps.append({"action": "test.log", "message": content})
        if expected:
            if any(sig in expected for sig in _EXPR_SIGNALS):
                steps.append({"action": "test.assert", "expression": expected})
            else:
                steps.append({
                    "action":     "test.assert",
                    "expression": "True",
                    "soft":       True,
                    "message":    expected,
                })
    return steps


def _parse_inline_body(body: str) -> List[Dict[str, Any]]:
    """Parse raw YAML from the Steps field as a steps list (Option A)."""
    import yaml as _yaml
    body = (body or "").strip()
    if not body:
        return []
    try:
        parsed = _yaml.safe_load(body)
        if isinstance(parsed, list):
            return [s for s in parsed if isinstance(s, dict)]
        if isinstance(parsed, dict) and "steps" in parsed:
            return [s for s in parsed["steps"] if isinstance(s, dict)]
    except Exception:
        pass
    return []


def _coerce(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


class TestRailRunner:
    """Runs Easy BDD tests driven by a TestRail test run.

    Usage:
        runner = TestRailRunner(config_manager)
        result = runner.run(project_id=59)
    """

    DEFAULT_PREFIX = "EASY_BDD:"

    def __init__(
        self,
        config_manager: GlobalConfigManager,
        testrail: TestRailService = None,
        tests_dir: Path = None,
        artifact_dir: Path = None,
        run_prefix: str = None,
        running_status_id: int = None,
    ):
        self._config = config_manager
        self._tr = testrail or TestRailService()
        self._tests_dir = Path(tests_dir or "tests/cases")
        self._artifact_dir = Path(artifact_dir or "reports/testrail")
        self._run_prefix = run_prefix or os.getenv(
            "TESTRAIL_RUN_PREFIX", self.DEFAULT_PREFIX
        )
        # Optional custom "Running" status ID — omit if your TestRail instance lacks it
        running_env = os.getenv("TESTRAIL_RUNNING_STATUS_ID")
        self._running_status_id: Optional[int] = (
            running_status_id
            or (int(running_env) if running_env else None)
        )

    def list_runs(self, project_id: int) -> List[Dict]:
        """Return all runs in a project that match the configured prefix."""
        created_after = int(time.time()) - 30 * 86400
        runs = self._tr.get_runs(project_id, created_after=created_after)
        return [r for r in runs if r.get("name", "").startswith(self._run_prefix)]

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    def run(
        self,
        project_id: int,
        run_id: int = None,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """Execute the full TestRail-driven lifecycle.

        Returns a summary dict: run_id, passed, failed, skipped, success.
        """
        return self._lifecycle(project_id, run_id, verbose)

    # ------------------------------------------------------------------ #
    # Lifecycle phases                                                     #
    # ------------------------------------------------------------------ #

    def _lifecycle(
        self, project_id: int, run_id: int = None, verbose: bool = True
    ) -> Dict[str, Any]:
        # Phase 1: Find run
        if run_id is not None:
            run = self._tr.get_run(run_id)
        else:
            run = self._find_run(project_id)
            if run is None:
                msg = (
                    f'No "{self._run_prefix}" run with pending tests found '
                    f"in project {project_id}"
                )
                if verbose:
                    print(f"\n[TestRail] {msg}")
                return {"skipped": True, "reason": msg}

        run_id = run["id"]
        run_vars = TestRailService.parse_run_vars(run.get("description"))

        if verbose:
            print(f"\n[TestRail] Run [{run_id}] {run['name']}")
            if run_vars.cron:
                print(f"[TestRail] Cron schedule: {run_vars.cron}")
            if run_vars.retry:
                print(f"[TestRail] Retries configured: {run_vars.retry}")

        # Phase 2: Get tests
        tests = self._tr.get_tests(run_id)
        if not tests:
            return {"skipped": True, "reason": "Run has no tests", "run_id": run_id}

        classified = self._classify_tests(tests)

        # Phase 3: Cron gate
        if run_vars.cron and not _cron_in_window(run_vars.cron):
            if verbose:
                print(
                    f"[TestRail] Outside cron window ({run_vars.cron}) — marking all skipped"
                )
            self._skip_all(classified)
            return {"skipped": True, "reason": "Outside cron window", "run_id": run_id}

        # Setup artifact directory
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

        # Extract Var: variables and merge with run_vars.extra
        injected_vars = self._extract_vars(classified)
        injected_vars.update(run_vars.extra)
        if verbose and injected_vars:
            print(f"[TestRail] Injected {len(injected_vars)} variable(s): {list(injected_vars.keys())}")

        # Phase 4–6: Execute with retry loop
        retry_remaining = run_vars.retry
        rerun_count = run_vars.rerun
        total_passed = total_failed = total_skipped = 0

        while True:
            passed, failed, skipped = self._execute_cases(
                classified, injected_vars, run_id, verbose
            )
            total_passed += passed
            total_failed += failed
            total_skipped += skipped

            # Phase 5: Finalize
            self._finalize(run_id, run_vars, passed, failed, skipped)

            if failed == 0 or retry_remaining <= 0:
                break

            if verbose:
                print(
                    f"\n[TestRail] Retry {rerun_count + 1}: "
                    f"{failed} failed, {retry_remaining} retry(s) left"
                )

            self._mark_failed_for_retest(run_id)
            retry_remaining -= 1
            rerun_count += 1
            run_vars.retry = retry_remaining
            run_vars.rerun = rerun_count
            try:
                self._tr.update_run(run_id, description=json.dumps(run_vars.to_dict()))
            except Exception:
                pass

            # Re-fetch tests with updated statuses
            tests = self._tr.get_tests(run_id)
            classified = self._classify_tests(tests)

        if verbose:
            print(
                f"\n[TestRail] Done — "
                f"Passed: {total_passed}  Failed: {total_failed}  Skipped: {total_skipped}"
            )

        return {
            "run_id": run_id,
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "success": total_failed == 0,
        }

    # ------------------------------------------------------------------ #
    # Phase helpers                                                        #
    # ------------------------------------------------------------------ #

    def _find_run(self, project_id: int) -> Optional[Dict]:
        """Return the first EASY_BDD: run with pending tests created in the last 30 days."""
        created_after = int(time.time()) - 30 * 86400
        runs = self._tr.get_runs(project_id, created_after=created_after)
        for run in runs:
            if not run.get("name", "").startswith(self._run_prefix):
                continue
            if run.get("untested_count", 0) > 0 or run.get("retest_count", 0) > 0:
                return run
        return None

    def _classify_tests(self, tests: List[Dict]) -> List[Dict]:
        return [
            {
                **t,
                "role": _classify(t.get("title", "")),
                "clean_title": _strip_prefix(t.get("title", "")),
            }
            for t in tests
        ]

    def _extract_vars(self, classified: List[Dict]) -> Dict[str, Any]:
        """Parse key: value pairs from all Var: cases."""
        variables: Dict[str, Any] = {}
        for test in classified:
            if test["role"] != "var":
                continue
            for line in _get_case_body(test).splitlines():
                line = line.strip()
                if ":" in line and not line.startswith(("-", "#")):
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if key:
                        variables[key] = _coerce(value)
        return variables

    # Status IDs that mean "this test needs to be run"
    _PENDING_STATUSES = frozenset({
        TestRailService.STATUS_UNTESTED,
        TestRailService.STATUS_RETEST,
    })

    def _execute_cases(
        self,
        classified: List[Dict],
        injected_vars: Dict[str, Any],
        run_id: int,
        verbose: bool,
    ) -> Tuple[int, int, int]:
        """Run Setup → Test → Teardown cases in order, posting results to TR in real-time.

        Only Test: cases in untested or retest status are executed.
        Setup: and Teardown: cases always run when there are pending tests.
        """
        passed = failed = skipped = 0

        # Filter Test: / Inline: cases to only those that need running
        pending_tests = [
            t for t in classified
            if t["role"] in ("test", "inline")
            and t.get("status_id", TestRailService.STATUS_UNTESTED) in self._PENDING_STATUSES
        ]

        if not pending_tests:
            if verbose:
                print("  No pending tests (untested or retest) — nothing to execute.")
            return passed, failed, skipped

        setups = [t for t in classified if t["role"] == "setup"]
        teardowns = [t for t in classified if t["role"] == "teardown"]
        execution_order = setups + pending_tests + teardowns

        for case in execution_order:
            test_id = case["id"]
            title = case["clean_title"]
            role = case["role"]
            body = _get_case_body(case)

            if verbose:
                print(f"\n  [{role.upper()}] {title}")

            # Post "running" status immediately (best-effort — only if configured)
            if self._running_status_id is not None:
                try:
                    self._tr.add_result(
                        test_id,
                        status_id=self._running_status_id,
                        comment="Running...",
                    )
                except Exception:
                    pass

            start_time = time.time()

            if role == "inline":
                test_passed, comment_lines = self._run_inline(case, injected_vars, verbose)
            else:
                yaml_files = self._resolve(body, title, injected_vars)
                if not yaml_files:
                    elapsed = _format_elapsed(time.time() - start_time)
                    if not body:
                        comment = (
                            "Case body is empty.\n"
                            "Test: cases: add 'tag: <tag>' or 'file: <path>' to the Steps field.\n"
                            "To write steps directly in TestRail, rename to 'Inline: <title>'."
                        )
                    elif not (body.startswith("tag:") or body.startswith("file:")):
                        comment = (
                            f"Unrecognised body format. Use:\n"
                            f"  tag: <tag>    — run all local YAMLs with that tag\n"
                            f"  file: <path>  — run a specific YAML file\n"
                            f"Or rename the case to 'Inline: {title}' to write steps directly.\n\n"
                            f"Body received:\n{body[:200]}"
                        )
                    else:
                        comment = f"No YAML tests found matching: {body[:200]}"
                    self._tr.add_result(
                        test_id,
                        status_id=TestRailService.STATUS_FAILED,
                        comment=comment,
                        elapsed=elapsed,
                    )
                    failed += 1
                    if verbose:
                        print(f"    FAIL — {comment.splitlines()[0]}")
                    continue
                test_passed, comment_lines = self._run_yaml_files(
                    yaml_files, injected_vars, verbose
                )

            elapsed = _format_elapsed(time.time() - start_time)
            comment = "\n".join(comment_lines) or ("Passed" if test_passed else "Failed")
            status_id = (
                TestRailService.STATUS_PASSED
                if test_passed
                else TestRailService.STATUS_FAILED
            )

            self._tr.add_result(test_id, status_id=status_id, comment=comment, elapsed=elapsed)

            if test_passed:
                passed += 1
                if verbose:
                    print(f"    PASS ({elapsed})")
            else:
                failed += 1
                if verbose:
                    print(f"    FAIL ({elapsed})")

        return passed, failed, skipped

    def _run_yaml_files(
        self,
        yaml_files: List[Path],
        injected_vars: Dict[str, Any],
        verbose: bool,
    ) -> Tuple[bool, List[str]]:
        """Execute a list of YAML files; return (all_passed, comment_lines)."""
        all_passed = True
        comment_lines: List[str] = []

        for yaml_path in yaml_files:
            result = self._run_single(yaml_path, injected_vars, verbose)
            if result is None:
                all_passed = False
                comment_lines.append(f"ERROR: could not execute {yaml_path.name}")
                continue

            for detail in result.test_details or []:
                name = detail.get("name", yaml_path.stem)
                status = detail.get("status", "FAILED")
                line = f"{status}: {name}"
                if status == "FAILED":
                    err = detail.get("error") or ""
                    log = detail.get("execution_log") or ""
                    tail = "\n".join(log.splitlines()[-10:]) if log else ""
                    if err:
                        line += f"\n{err}"
                    if tail:
                        line += f"\n---\n{tail}"
                comment_lines.append(line)

            if not result.success:
                all_passed = False

        return all_passed, comment_lines

    def _run_single(
        self,
        yaml_path: Path,
        injected_vars: Dict[str, Any],
        verbose: bool,
    ) -> Optional[TestResult]:
        try:
            # Inject TestRail variables into the collection scope
            if injected_vars:
                for k, v in injected_vars.items():
                    self._config.set_variable(k, str(v), scope="collection_vars")

            runner = TestRunner(self._config)
            return runner.run(yaml_path)
        except Exception as exc:
            if verbose:
                print(f"    ERROR running {yaml_path.name}: {exc}")
            return None

    def _build_inline_test_dict(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build an in-memory Easy BDD test dict from an Inline: case.

        Priority:
          1. custom_steps_separated rows → Option B (structured content/expected)
          2. custom_steps text           → Option A (raw YAML steps)
        Preconditions field → local variables (merged on top of injected_vars later).
        """
        title = case.get("clean_title", case.get("title", "Inline Test"))
        variables = _parse_preconds_vars(case)

        structured = case.get("custom_steps_separated") or []
        has_structured = isinstance(structured, list) and any(
            isinstance(r, dict) and (r.get("content") or r.get("expected"))
            for r in structured
        )

        if has_structured:
            steps = _parse_structured_steps(case)
        else:
            body = (case.get("custom_steps") or "").strip()
            steps = _parse_inline_body(body)

        if not steps:
            return None

        result: Dict[str, Any] = {"name": title, "steps": steps}
        if variables:
            result["variables"] = variables
        return result

    def _run_inline(
        self,
        case: Dict[str, Any],
        injected_vars: Dict[str, Any],
        verbose: bool,
    ) -> Tuple[bool, List[str]]:
        """Execute an Inline: case by materialising it as a temp YAML file."""
        import yaml as _yaml

        test_dict = self._build_inline_test_dict(case)
        if not test_dict:
            return False, [
                "Inline case has no steps.\n"
                "\nOption A — Steps field: paste a YAML steps list, e.g.:\n"
                "  - action: browser.open\n"
                "    url: ${base_url}\n"
                "  - action: browser.click\n"
                "    role: button\n"
                "    name: Login\n"
                "\nOption B — Use the 'Steps (Separated)' case type:\n"
                "  Step Description: action YAML (one step per row)\n"
                "  Expected Result:  Python expression or natural-language assertion\n"
                "\nPreconditions field: key: value variable pairs\n"
                "  base_url: https://staging.example.com"
            ]

        test_id = case.get("id", "tmp")
        tmp_path = self._artifact_dir / f"_inline_{test_id}.yaml"
        try:
            self._artifact_dir.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                _yaml.dump(test_dict, f, allow_unicode=True, default_flow_style=False,
                           sort_keys=False)
            return self._run_yaml_files([tmp_path], injected_vars, verbose)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _skip_all(self, classified: List[Dict]) -> None:
        for case in classified:
            if case["role"] in ("test", "setup", "teardown"):
                try:
                    self._tr.add_result(
                        case["id"],
                        status_id=TestRailService.STATUS_BLOCKED,
                        comment="Skipped: outside cron window",
                    )
                except Exception:
                    pass

    def _mark_failed_for_retest(self, run_id: int) -> None:
        try:
            for test in self._tr.get_tests(run_id):
                if test.get("status_id") == TestRailService.STATUS_FAILED:
                    self._tr.add_result(
                        test["id"],
                        status_id=TestRailService.STATUS_RETEST,
                        comment="Marked for retry",
                    )
        except Exception:
            pass

    def _finalize(
        self,
        run_id: int,
        run_vars: RunVariables,
        passed: int,
        failed: int,
        skipped: int,
    ) -> None:
        summary = {
            **run_vars.to_dict(),
            "last_result": {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "timestamp": datetime.now().isoformat(),
            },
        }
        try:
            self._tr.update_run(run_id, description=json.dumps(summary))
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Case body resolution                                                 #
    # ------------------------------------------------------------------ #

    def _resolve(
        self, body: str, title: str, variables: Dict[str, Any]
    ) -> List[Path]:
        """Resolve a case body string to a list of YAML file paths.

        Supported formats:
          tag: <tag>    — run all local YAMLs in tests_dir that have this tag
          file: <path>  — run a specific YAML file (relative to tests_dir or absolute)
        """
        body = (body or "").strip()
        if not body:
            return []

        if body.startswith("tag:"):
            return self._by_tag(body[4:].strip())
        if body.startswith("file:"):
            return self._by_file(body[5:].strip())

        # Unrecognised format — log it and return empty so it posts a clear failure
        return []

    def _by_tag(self, tag: str) -> List[Path]:
        import yaml
        matches: List[Path] = []
        for path in sorted(self._tests_dir.rglob("*.yaml")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and tag in (data.get("tags") or []):
                    matches.append(path)
            except Exception:
                continue
        return matches

    def _by_file(self, file_path: str) -> List[Path]:
        p = Path(file_path)
        if not p.is_absolute():
            p = self._tests_dir / file_path
        return [p] if p.exists() else []
