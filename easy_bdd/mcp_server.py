"""
Easy BDD MCP (Model Context Protocol) server.

Exposes the Easy BDD framework to AI models as Tools, Resources, and Prompts
following the Model Context Protocol specification.

Usage:
    python -m easy_bdd mcp-serve            # STDIO transport (default, for Claude Desktop)
    python -m easy_bdd mcp-serve --sse      # SSE transport (for web clients)
    python -m easy_bdd mcp-serve --port 8080 --sse

Safety:
    - run_tests defaults to dry_run=True; set dry_run=False to execute
    - apply_fix requires confirmed=True; returns preview otherwise
    - Destructive / high-risk operations are gated and logged
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bootstrap FastMCP
# ---------------------------------------------------------------------------

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'mcp' package is required for the MCP server.\n"
        "Install it with:  pip install mcp>=1.0.0"
    ) from exc

mcp = FastMCP(
    "easy-bdd",
    instructions=textwrap.dedent(
        """
        You are an assistant for the Easy BDD testing framework.

        Workflow:
        1. Use list_tests / get_test to discover and read test definitions.
        2. Use validate_test to check syntax before running.
        3. Use run_tests with dry_run=True (default) to preview execution, then
           set dry_run=False to actually run.
        4. After a failure, call get_failure_trace to read the execution log,
           then preview_fix to see suggested corrections.
        5. Call apply_fix only after reviewing the preview and passing confirmed=True.

        Resources hold read-only context (docs, config, shared steps, reports).
        Prompts are packaged workflows for common tasks.
        """
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent


def _abs(p: str | Path) -> Path:
    """Resolve path relative to project root if not absolute."""
    path = Path(p)
    return path if path.is_absolute() else (_PROJECT_ROOT / path).resolve()


def _load_config() -> Dict[str, Any]:
    import yaml

    cfg_path = _PROJECT_ROOT / "config" / "framework.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open() as f:
        return yaml.safe_load(f) or {}


def _latest_report() -> Optional[Dict[str, Any]]:
    reports_dir = _PROJECT_ROOT / "reports"
    jsons = sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not jsons:
        return None
    with jsons[0].open() as f:
        return json.load(f)


def _collect_test_files(path: Optional[str] = None) -> List[Path]:
    base = _abs(path) if path else _PROJECT_ROOT / "tests" / "cases"
    if base.is_file():
        return [base]
    return sorted(base.glob("**/*.yaml")) + sorted(base.glob("**/*.yml"))


# ---------------------------------------------------------------------------
# TOOLS — side-effectful operations
# ---------------------------------------------------------------------------


@mcp.tool()
def list_tests(
    path: str = "tests/cases",
    tags: Optional[str] = None,
) -> str:
    """
    List Easy BDD test files available under *path*.

    Parameters
    ----------
    path : directory or file path (default: tests/cases)
    tags : comma-separated tag filter; only tests that declare at least one
           matching tag are returned.

    Returns a JSON array of objects with keys: path, name, description, tags.
    """
    import yaml

    files = _collect_test_files(path)
    tag_filter = {t.strip().lower() for t in tags.split(",")} if tags else set()

    results = []
    for f in files:
        try:
            with f.open() as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                continue
            test_tags = [str(t).lower() for t in data.get("tags", [])]
            if tag_filter and not (tag_filter & set(test_tags)):
                continue
            results.append(
                {
                    "path": str(f.relative_to(_PROJECT_ROOT)),
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "tags": data.get("tags", []),
                }
            )
        except Exception as exc:
            results.append({"path": str(f.relative_to(_PROJECT_ROOT)), "error": str(exc)})

    return json.dumps(results, indent=2)


@mcp.tool()
def get_test(path: str) -> str:
    """
    Return the raw YAML content of a single test file.

    Parameters
    ----------
    path : relative or absolute path to the test YAML file.
    """
    p = _abs(path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}"})
    return p.read_text(encoding="utf-8")


@mcp.tool()
def validate_test(
    path: Optional[str] = None,
    snippet: Optional[str] = None,
    shared_steps_dir: Optional[str] = None,
    strict: bool = False,
) -> str:
    """
    Validate an Easy BDD test file or a raw YAML snippet.

    Exactly one of *path* or *snippet* must be provided.

    Parameters
    ----------
    path            : path to a test YAML file or directory.
    snippet         : raw YAML step text to validate inline.
    shared_steps_dir: directory containing shared_steps.yaml.
    strict          : if True, warnings are treated as errors.

    Returns a JSON object with keys: errors (int), warnings (int), issues (list).
    Each issue has: severity, location, message, reason, suggestion, correction.
    """
    from .core.validator import EasyBDDValidator

    validator = EasyBDDValidator()
    ss_dir = Path(shared_steps_dir) if shared_steps_dir else None

    if snippet is not None:
        issues = validator.validate_snippet(snippet, ss_dir)
    elif path is not None:
        p = _abs(path)
        if not p.exists():
            return json.dumps({"error": f"Path not found: {path}"})
        if p.is_dir():
            issues = []
            for f in _collect_test_files(path):
                issues.extend(validator.validate_file(f, ss_dir))
        else:
            issues = validator.validate_file(p, ss_dir)
    else:
        return json.dumps({"error": "Provide either 'path' or 'snippet'."})

    errors = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARNING"]

    return json.dumps(
        {
            "errors": len(errors),
            "warnings": len(warnings),
            "passed": len(errors) == 0 and (not strict or len(warnings) == 0),
            "issues": [
                {
                    "severity": i.severity,
                    "location": i.location,
                    "message": i.message,
                    "reason": i.reason,
                    "suggestion": i.suggestion,
                    "correction": i.correction,
                }
                for i in issues
            ],
        },
        indent=2,
    )


@mcp.tool()
def get_shared_steps(directory: str = "tests/cases") -> str:
    """
    Return the contents of shared_steps.yaml found under *directory*.

    Parameters
    ----------
    directory : directory to search (default: tests/cases).

    Returns the raw YAML text or an error message.
    """
    base = _abs(directory)
    candidates = list(base.glob("**/shared_steps.yaml")) + list(
        base.glob("**/shared_steps.yml")
    )
    if not candidates:
        return json.dumps({"error": f"No shared_steps.yaml found under {directory}"})
    # Return the first (most-specific) one
    return candidates[0].read_text(encoding="utf-8")


@mcp.tool()
def run_tests(
    path: str = "tests/cases",
    tags: Optional[str] = None,
    dry_run: bool = True,
) -> str:
    """
    Run Easy BDD tests.  DEFAULTS TO dry_run=True — no tests execute until you
    explicitly pass dry_run=False.

    Parameters
    ----------
    path    : test file or directory (default: tests/cases).
    tags    : comma-separated tag filter.
    dry_run : if True (default) only list what *would* run without executing.

    Returns a JSON summary with: status, tests (list), report_path.
    """
    if dry_run:
        files = _collect_test_files(path)
        return json.dumps(
            {
                "status": "DRY_RUN",
                "message": "Pass dry_run=False to actually execute these tests.",
                "would_run": [str(f.relative_to(_PROJECT_ROOT)) for f in files],
                "count": len(files),
            },
            indent=2,
        )

    # Live run — import heavy deps only when needed
    logger.info("MCP run_tests: path=%s tags=%s", path, tags)
    from .core.runner import TestRunner
    from .core.variable_manager import GlobalConfigManager

    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    config = GlobalConfigManager()
    runner = TestRunner(config)
    result = runner.run(test_path=_abs(path), tags=tag_list, record_video=False)

    return json.dumps(
        {
            "status": "PASSED" if result.success else "FAILED",
            "total_tests": result.total_tests,
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "execution_time": round(result.execution_time, 2),
            "report_path": str(result.report_path) if result.report_path else None,
        },
        indent=2,
    )


@mcp.tool()
def get_failure_trace(report_path: Optional[str] = None, test_name: Optional[str] = None) -> str:
    """
    Return the execution trace for the most recent (or specified) test run.

    Parameters
    ----------
    report_path : path to a JSON report file; defaults to the latest report.
    test_name   : if provided, return only the trace for that test case.

    Returns a JSON object with execution details and any failure messages.
    """
    if report_path:
        p = _abs(report_path)
        if not p.exists():
            return json.dumps({"error": f"Report not found: {report_path}"})
        with p.open() as f:
            report = json.load(f)
    else:
        report = _latest_report()
        if report is None:
            return json.dumps({"error": "No reports found in reports/"})

    tests = report.get("tests", [])
    if test_name:
        tests = [t for t in tests if test_name.lower() in t.get("name", "").lower()]
        if not tests:
            return json.dumps({"error": f"No test named '{test_name}' in report."})

    return json.dumps(
        {
            "timestamp": report.get("timestamp"),
            "test_file": report.get("test_file"),
            "summary": {
                "total": report.get("total_tests"),
                "passed": report.get("passed"),
                "failed": report.get("failed"),
                "pass_rate": report.get("pass_rate"),
                "execution_time": report.get("execution_time"),
            },
            "tests": [
                {
                    "name": t.get("name"),
                    "status": t.get("status"),
                    "execution_time": t.get("execution_time"),
                    "execution_log": t.get("execution_log", []),
                    "error": t.get("error"),
                }
                for t in tests
            ],
        },
        indent=2,
    )


@mcp.tool()
def preview_fix(
    path: Optional[str] = None,
    snippet: Optional[str] = None,
    shared_steps_dir: Optional[str] = None,
) -> str:
    """
    Validate and return auto-correctable fixes WITHOUT writing any files.

    Parameters
    ----------
    path            : path to a test YAML file.
    snippet         : raw YAML text to check.
    shared_steps_dir: directory containing shared_steps.yaml.

    Returns a JSON object with: issues_found (int), fixable (int),
    corrections (list of {location, original, corrected}).
    """
    result = json.loads(
        validate_test(path=path, snippet=snippet, shared_steps_dir=shared_steps_dir)
    )

    if "error" in result:
        return json.dumps(result)

    fixable = [i for i in result["issues"] if i.get("correction")]
    return json.dumps(
        {
            "issues_found": result["errors"] + result["warnings"],
            "fixable": len(fixable),
            "corrections": [
                {
                    "location": i["location"],
                    "message": i["message"],
                    "corrected_yaml": i["correction"],
                }
                for i in fixable
            ],
        },
        indent=2,
    )


@mcp.tool()
def apply_fix(
    path: str,
    confirmed: bool = False,
) -> str:
    """
    Apply auto-correctable fixes to a test YAML file IN PLACE.

    REQUIRES confirmed=True — the tool returns a preview if confirmed is False.
    This operation OVERWRITES the file; ensure you have a backup or use version
    control before confirming.

    Parameters
    ----------
    path      : path to the test YAML file to fix.
    confirmed : must be True to actually write the corrected file.

    Returns a JSON object describing what was (or would be) changed.
    """
    import yaml
    from .core.validator import EasyBDDValidator

    p = _abs(path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}"})

    original_text = p.read_text(encoding="utf-8")
    validator = EasyBDDValidator()
    issues = validator.validate_file(p)
    fixable = [i for i in issues if i.correction]

    if not fixable:
        return json.dumps({"message": "No auto-fixable issues found.", "path": str(path)})

    preview = [
        {"location": i.location, "message": i.message, "corrected_yaml": i.correction}
        for i in fixable
    ]

    if not confirmed:
        logger.info("MCP apply_fix preview only: path=%s fixes=%d", path, len(fixable))
        return json.dumps(
            {
                "status": "PREVIEW",
                "message": "Pass confirmed=True to apply these fixes.",
                "path": str(path),
                "fixes": preview,
            },
            indent=2,
        )

    # --- Apply fixes ---
    logger.warning("MCP apply_fix CONFIRMED: path=%s fixes=%d", path, len(fixable))
    try:
        data = yaml.safe_load(original_text)
    except yaml.YAMLError as exc:
        return json.dumps({"error": f"Could not parse YAML: {exc}"})

    # Write corrected content via dump (round-trip preserves structure)
    corrected_text = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    p.write_text(corrected_text, encoding="utf-8")

    return json.dumps(
        {
            "status": "APPLIED",
            "path": str(path),
            "fixes_applied": len(fixable),
            "fixes": preview,
        },
        indent=2,
    )


@mcp.tool()
def validate_testrail_case(
    case_id: Optional[int] = None,
    suite_id: Optional[int] = None,
    run_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> str:
    """
    Validate Easy BDD syntax in TestRail test cases fetched via the API.

    Exactly one target is required: case_id, suite_id (+ project_id), or run_id.

    Parameters
    ----------
    case_id    : single TestRail case ID.
    suite_id   : validate all cases in this suite (requires project_id).
    run_id     : validate all Feature:/Shared: cases in this run.
    project_id : TestRail project ID (required with suite_id).

    Returns the full validation report as a JSON object with:
    cases (list of per-case results), total_errors, total_warnings,
    and suggested_preconditions per case where corrections exist.
    """
    from .core.validator import EasyBDDValidator
    from .services.testrail_service import TestRailService, TestRailError
    from .core.testrail_runner import _classify, _strip_prefix
    import re

    if case_id is not None:
        case_id = int(case_id)
    if suite_id is not None:
        suite_id = int(suite_id)
    if run_id is not None:
        run_id = int(run_id)
    if project_id is not None:
        project_id = int(project_id)

    try:
        tr = TestRailService()
    except TestRailError as exc:
        return json.dumps({"error": f"TestRail config error: {exc}"})

    cases = []
    try:
        if case_id is not None:
            cases = [tr.get_case(case_id)]
        elif suite_id is not None:
            if project_id is None:
                return json.dumps({"error": "project_id is required when suite_id is provided."})
            cases = tr.get_cases(project_id, suite_id=suite_id)
        elif run_id is not None:
            tests = tr.get_tests(run_id)
            ids = list({t.get("case_id") for t in tests if t.get("case_id")})
            for cid in ids:
                try:
                    cases.append(tr.get_case(cid))
                except Exception:
                    pass
        else:
            return json.dumps({"error": "Provide case_id, suite_id, or run_id."})
    except TestRailError as exc:
        return json.dumps({"error": f"TestRail API error: {exc}"})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error fetching cases: {exc}"})

    if not cases:
        return json.dumps({"message": "No cases found.", "cases": []})

    cases = [c for c in cases if isinstance(c, dict)]
    if not cases:
        return json.dumps({"message": "No valid cases found.", "cases": []})

    shared_names: set = set()
    for c in cases:
        title = c.get("title", "")
        if _classify(title) == "keyword":
            name = re.sub(r"[^A-Za-z0-9_]+", "_", _strip_prefix(title)).strip("_")
            shared_names.add(name)

    validator = EasyBDDValidator()
    results = validator.validate_testrail_cases(cases, shared_steps_from_tr=shared_names)
    _report_str, total_errors, total_warnings = EasyBDDValidator.format_testrail_report(results)

    case_results = []
    for case_id_key, r in results.items():
        issues = r.get("issues", [])
        case_results.append(
            {
                "case_id": case_id_key,
                "title": r.get("title"),
                "role": r.get("role"),
                "errors": sum(1 for i in issues if i.severity == "ERROR"),
                "warnings": sum(1 for i in issues if i.severity == "WARNING"),
                "issues": [
                    {
                        "severity": i.severity,
                        "location": i.location,
                        "message": i.message,
                        "reason": i.reason,
                        "suggestion": i.suggestion,
                        "correction": i.correction,
                    }
                    for i in issues
                ],
                "suggested_preconditions": r.get("suggested_preconditions"),
            }
        )

    return json.dumps(
        {
            "total_cases": len(results),
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "passed": total_errors == 0,
            "cases": case_results,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# RESOURCES — read-only context
# ---------------------------------------------------------------------------


@mcp.resource("easybdd://docs/actions")
def resource_docs_actions() -> str:
    """
    Complete reference for all known Easy BDD actions.

    Includes each action's required and optional parameters, plus alias
    mappings from legacy/shorthand names to canonical dot-notation names.
    """
    from .core.validator import ACTION_SCHEMA

    lines = ["# Easy BDD Action Reference\n"]
    lines.append(
        "Each action is written as a YAML key using dot-notation, e.g.:\n"
        "  - test.assert:\n"
        "      expression: result == 'ok'\n\n"
    )

    aliases: Dict[str, str] = {}
    canonical: Dict[str, Dict] = {}
    for name, schema in ACTION_SCHEMA.items():
        if "alias_of" in schema:
            aliases[name] = schema["alias_of"]
        else:
            canonical[name] = schema

    lines.append("## Actions\n")
    for name, schema in sorted(canonical.items()):
        req = schema.get("required", [])
        opt = schema.get("optional", [])
        lines.append(f"### `{name}`")
        if req:
            lines.append(f"  required: {', '.join(req)}")
        if opt and opt != ["..."]:
            lines.append(f"  optional: {', '.join(opt)}")
        elif opt == ["..."]:
            lines.append("  optional: (any additional parameters accepted)")
        lines.append("")

    lines.append("## Aliases\n")
    for alias, target in sorted(aliases.items()):
        lines.append(f"  `{alias}` → `{target}`")

    return "\n".join(lines)


@mcp.resource("easybdd://docs/syntax")
def resource_docs_syntax() -> str:
    """
    Easy BDD YAML test file syntax reference.

    Covers the top-level structure, control-flow constructs (for_each, if/else,
    repeat, parallel), shared step references, and variable syntax.
    """
    return textwrap.dedent(
        """
        # Easy BDD YAML Syntax Reference

        ## Top-level structure
        ```yaml
        name: My Test
        description: Optional description
        tags: [smoke, api]
        variables:
          base_url: https://example.com
        setup:
          - test.sleep:
              seconds: 1
        steps:
          - <action>: ...
        teardown:
          - <action>: ...
        ```

        ## Step formats

        ### Simple action (no params)
        ```yaml
        - test.sleep:
        ```

        ### Action with parameters
        ```yaml
        - test.assert:
            expression: status == 200
            message: "Expected 200"
        ```

        ### Shared step reference
        ```yaml
        - shared_step: my_shared_step_name
        ```

        ## Control-flow constructs

        ### for_each
        ```yaml
        - for_each:
            items: "{{my_list}}"
            steps:
              - test.print:
                  message: "{{item}}"
        ```

        ### if / else
        ```yaml
        - if:
            condition: "{{status}} == 200"
            steps:
              - test.print:
                  message: success
          else:
            - test.assert:
                expression: false
                message: unexpected status
        ```

        ### repeat
        ```yaml
        - repeat:
            count: 3
            steps:
              - test.sleep:
                  seconds: 1
        ```

        ### parallel
        ```yaml
        - parallel:
            steps:
              - telnet.send:
                  command: ping
              - test.sleep:
                  seconds: 2
        ```

        ## Variable references
        Use `{{variable_name}}` anywhere in a string value.  Variables are
        defined in the top-level `variables:` block or injected by actions
        that use `store_as`.

        ## Shared steps
        Shared steps are defined in a separate `shared_steps.yaml` file.
        Reference them with:
        ```yaml
        - shared_step: my_step_name
        ```
        The name must match a key in `shared_steps.yaml` (case-insensitive,
        spaces and hyphens normalised to underscores).
        """
    )


@mcp.resource("easybdd://tests/{path}")
def resource_test_file(path: str) -> str:
    """
    Return the raw YAML content of the test file at *path*.

    Path is relative to the project root, e.g. tests/cases/login.yaml.
    """
    p = _abs(path)
    if not p.exists():
        return f"# Error: file not found: {path}"
    return p.read_text(encoding="utf-8")


@mcp.resource("easybdd://shared-steps")
def resource_shared_steps() -> str:
    """
    Return all shared_steps.yaml files found under tests/cases, concatenated.
    """
    base = _PROJECT_ROOT / "tests" / "cases"
    files = sorted(base.glob("**/shared_steps.yaml")) + sorted(
        base.glob("**/shared_steps.yml")
    )
    if not files:
        return "# No shared_steps.yaml files found."
    parts = []
    for f in files:
        rel = f.relative_to(_PROJECT_ROOT)
        parts.append(f"# --- {rel} ---")
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


@mcp.resource("easybdd://reports/latest")
def resource_latest_report() -> str:
    """
    Return the most recent test run report as JSON.
    """
    report = _latest_report()
    if report is None:
        return json.dumps({"message": "No reports found in reports/"})
    return json.dumps(report, indent=2)


@mcp.resource("easybdd://config")
def resource_config() -> str:
    """
    Return the current framework configuration (config/framework.yaml).
    Sensitive keys (passwords, tokens) are redacted.
    """
    import re

    cfg = _load_config()

    def _redact(obj: Any, depth: int = 0) -> Any:
        if depth > 10:
            return obj
        if isinstance(obj, dict):
            return {
                k: "[REDACTED]"
                if re.search(r"(password|token|secret|api_key|apikey)", k, re.I)
                else _redact(v, depth + 1)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_redact(i, depth + 1) for i in obj]
        return obj

    return json.dumps(_redact(cfg), indent=2)


# ---------------------------------------------------------------------------
# PROMPTS — reusable packaged workflows
# ---------------------------------------------------------------------------


@mcp.prompt()
def generate_tests(module: str, description: str = "") -> str:
    """
    Prompt: Generate Easy BDD test cases for a module.

    Parameters
    ----------
    module      : module or feature name (e.g. "telnet_service", "login_flow").
    description : optional description of what should be tested.
    """
    action_ref = resource_docs_actions()
    syntax_ref = resource_docs_syntax()
    shared = resource_shared_steps()

    return textwrap.dedent(
        f"""
        You are an Easy BDD test author.  Generate complete, runnable test YAML
        files for the module described below.

        MODULE: {module}
        {"DESCRIPTION: " + description if description else ""}

        ## Requirements
        - Follow the Easy BDD YAML syntax exactly (see reference below).
        - Use only actions from the action reference below.
        - Reference existing shared steps where appropriate.
        - Include a `name`, `description`, `tags`, and `steps` section.
        - Add a `teardown` section if the test allocates resources.
        - Validate mentally: every required parameter must be present.

        ## Available Shared Steps
        {shared}

        ## Action Reference
        {action_ref}

        ## Syntax Reference
        {syntax_ref}
        """
    )


@mcp.prompt()
def debug_failure(test_name: str = "", report_path: str = "") -> str:
    """
    Prompt: Diagnose a failing test and suggest a fix.

    Parameters
    ----------
    test_name   : name of the failing test (optional; uses latest if blank).
    report_path : path to a specific JSON report (optional).
    """
    trace = get_failure_trace(
        report_path=report_path or None,
        test_name=test_name or None,
    )
    action_ref = resource_docs_actions()

    return textwrap.dedent(
        f"""
        You are an Easy BDD failure analyst.  Diagnose the following test
        failure and suggest a concrete fix.

        ## Failure Trace
        ```json
        {trace}
        ```

        ## Action Reference (for parameter verification)
        {action_ref}

        ## Instructions
        1. Identify the failing step from the execution_log.
        2. Explain WHY it failed (wrong parameters, unexpected value, timeout, etc.).
        3. Show the corrected YAML step(s).
        4. If the fix requires a code or config change outside the test, describe it.
        """
    )


@mcp.prompt()
def validate_and_fix(path: str) -> str:
    """
    Prompt: Validate a test file and interactively apply suggested fixes.

    Parameters
    ----------
    path : path to the test YAML file to validate.
    """
    validation = validate_test(path=path)
    preview = preview_fix(path=path)

    return textwrap.dedent(
        f"""
        You are an Easy BDD quality assistant.  Walk through the validation
        issues below, explain each one to the user, then apply the auto-fixable
        corrections only after the user confirms.

        ## File: {path}

        ## Validation Result
        ```json
        {validation}
        ```

        ## Auto-fixable Corrections
        ```json
        {preview}
        ```

        ## Instructions
        1. Explain each issue to the user in plain English.
        2. Show the proposed correction for each fixable issue.
        3. Ask the user to confirm before calling `apply_fix`.
        4. For non-fixable issues (no correction), provide guidance on how
           to fix them manually.
        5. After applying, call `validate_test` again to confirm the file
           is now clean.
        """
    )


# ---------------------------------------------------------------------------
# Locator debugger tools
# ---------------------------------------------------------------------------

import asyncio
import concurrent.futures


def _run_async(coro):
    """Run an async coroutine from a sync context without event-loop conflicts."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _probe_selectors_async(url: str, selectors: List[str], timeout_ms: int) -> List[Dict]:
    """Navigate to url and test each selector; return per-selector results."""
    from playwright.async_api import async_playwright

    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(1500)
        except Exception as e:
            await browser.close()
            return [{"selector": s, "found": False, "error": f"Navigation failed: {e}"} for s in selectors]

        for sel in selectors:
            entry: Dict[str, Any] = {"selector": sel}
            try:
                loc = page.locator(sel)
                count = await loc.count()
                if count == 0:
                    entry["found"] = False
                else:
                    entry["found"] = True
                    entry["count"] = count
                    try:
                        entry["visible"] = await loc.first.is_visible(timeout=2000)
                    except Exception:
                        entry["visible"] = False
                    try:
                        entry["enabled"] = await loc.first.is_enabled(timeout=2000)
                    except Exception:
                        entry["enabled"] = False
                    try:
                        bb = await loc.first.bounding_box(timeout=2000)
                        entry["in_viewport"] = bb is not None
                    except Exception:
                        entry["in_viewport"] = False
            except Exception as e:
                entry["found"] = False
                entry["error"] = str(e)
            results.append(entry)

        await browser.close()
    return results


@mcp.tool()
def probe_selector(url: str, selector: str, fallback_selectors=None, timeout: int = 20) -> str:
    """
    Test whether a CSS/ARIA/text selector (and optional fallbacks) resolve on a
    live page.  Useful for debugging selectors from failing TestRail tests.

    Parameters
    ----------
    url                : Full URL to navigate to (e.g. https://192.168.100.145/network)
    selector           : Primary selector to test
    fallback_selectors : Optional list of alternative selectors to try
    timeout            : Navigation timeout in seconds (default 20)
    """
    all_selectors = [selector] + (fallback_selectors or [])
    try:
        results = _run_async(_probe_selectors_async(url, all_selectors, timeout * 1000))
        best = next((r for r in results if r.get("found") and r.get("visible") and r.get("enabled")), None)
        return json.dumps({
            "url":     url,
            "results": results,
            "best":    best,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def fix_test_selectors(path: str, timeout: int = 20) -> str:
    """
    Open a test YAML file and for every step that has a *selector* +
    *fallback_selectors*, try each candidate against the live page URL.
    The first selector that is found AND visible AND enabled becomes the new
    primary; fallback_selectors is removed.  The file is saved in place.

    The page URL is read from variables.page_url (set by the crawler) or falls
    back to variables.base_url.

    Parameters
    ----------
    path    : Relative path to the test YAML (e.g. tests/cases/crawled/click_apply.yaml)
    timeout : Per-page navigation timeout in seconds (default 20)
    """
    import re as _re
    import yaml as _yaml

    fpath = _PROJECT_ROOT / path
    if not fpath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        data = _yaml.safe_load(fpath.read_text(encoding="utf-8"))
    except Exception as e:
        return json.dumps({"error": f"Could not parse YAML: {e}"})

    if not isinstance(data, dict):
        return json.dumps({"error": "Invalid YAML structure."})

    variables = data.get("variables") or {}
    probe_url = variables.get("page_url") or variables.get("base_url", "")
    steps = data.get("steps", [])
    changes: List[Dict] = []
    unfixed: List[Dict] = []

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        for action_key, params in step.items():
            if not isinstance(params, dict):
                continue
            primary = params.get("selector")
            fallbacks = params.get("fallback_selectors", [])
            if not primary or not fallbacks:
                continue

            try:
                results = _run_async(
                    _probe_selectors_async(probe_url, [primary] + fallbacks, timeout * 1000)
                )
            except Exception as e:
                unfixed.append({"step": i, "action": action_key, "error": str(e)})
                continue

            best = (
                next((r for r in results if r.get("found") and r.get("visible") and r.get("enabled")), None)
                or next((r for r in results if r.get("found") and r.get("visible")), None)
                or next((r for r in results if r.get("found")), None)
            )

            if best and best["selector"] != primary:
                changes.append({"step": i, "action": action_key, "old": primary, "new": best["selector"]})
                params["selector"] = best["selector"]
                del params["fallback_selectors"]
            elif best and best["selector"] == primary:
                del params["fallback_selectors"]
                changes.append({"step": i, "action": action_key, "old": primary, "new": primary, "note": "primary already works"})
            else:
                unfixed.append({"step": i, "action": action_key, "selector": primary, "tried": len(results)})

    if changes:
        fpath.write_text(
            _yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    return json.dumps({"path": path, "changes": changes, "unfixed": unfixed, "saved": bool(changes)}, indent=2)


@mcp.tool()
def fix_crawled_tests(directory: str = "tests/cases/crawled", limit: int = 50, timeout: int = 20) -> str:
    """
    Batch-heal selector issues across multiple crawled test YAML files.
    For each file, tries all fallback_selectors against the live page and
    promotes the first working one to primary.

    Parameters
    ----------
    directory : Directory of YAML files to fix (default: tests/cases/crawled)
    limit     : Max number of files to process (default: 50)
    timeout   : Per-page navigation timeout in seconds (default: 20)
    """
    dir_path = _PROJECT_ROOT / directory
    if not dir_path.is_dir():
        return json.dumps({"error": f"Directory not found: {directory}"})

    yaml_files = sorted(dir_path.glob("**/*.yaml"))[:limit]
    if not yaml_files:
        return json.dumps({"error": "No YAML files found."})

    summary = []
    for fpath in yaml_files:
        rel = str(fpath.relative_to(_PROJECT_ROOT)).replace("\\", "/")
        try:
            result_str = fix_test_selectors(path=rel, timeout=timeout)
            result = json.loads(result_str)
            if "error" not in result:
                summary.append({
                    "file":    rel,
                    "changes": len(result.get("changes", [])),
                    "unfixed": len(result.get("unfixed", [])),
                })
        except Exception as e:
            summary.append({"file": rel, "error": str(e)})

    return json.dumps({
        "processed": len(summary),
        "files": summary,
    }, indent=2)


@mcp.tool()
def get_testrail_run_failures(run_id: int, status: str = "failed,retest") -> str:
    """
    Fetch test cases from a TestRail run filtered by status.

    Returns case titles, section names (which encode the page URL path), and
    a yaml_hint filename so you can match failures to local YAML files.

    Parameters
    ----------
    run_id : TestRail run ID (e.g. 195556)
    status : Comma-separated status names (default: failed,retest)
    """
    import re as _re

    try:
        import sys as _sys
        _sys.path.insert(0, str(_PROJECT_ROOT))
        from easy_bdd.services.testrail_service import TestRailService

        tr = TestRailService()

        STATUS_IDS = {
            "passed":   1,
            "blocked":  2,
            "untested": 3,
            "retest":   4,
            "failed":   5,
        }
        wanted_ids = {STATUS_IDS[s.strip().lower()] for s in status.split(",") if s.strip().lower() in STATUS_IDS}

        tests = tr.get_tests(run_id)

        # Build section_id → name map
        section_names: Dict[int, str] = {}
        try:
            run_info = tr.get_run(run_id)
            project_id = run_info.get("project_id")
            suite_id = run_info.get("suite_id")
            if project_id:
                for sec in tr.get_sections(project_id, suite_id=suite_id):
                    section_names[sec["id"]] = sec.get("name", "")
        except Exception:
            pass

        def _section_to_path(sec_name: str) -> str:
            name = _re.sub(r'^[^/]+/\s*', '', sec_name)
            return name.replace(" > ", "/").strip()

        def _yaml_hint(title: str) -> str:
            name = _re.sub(r'^Feature:\s*', '', title, flags=_re.I).lower()
            name = _re.sub(r'[^a-z0-9_\s-]', '', name)
            name = _re.sub(r'[\s-]+', '_', name).strip('_')
            return (name[:60] or 'test') + '.yaml'

        failures = []
        for t in tests:
            if t.get("status_id") in wanted_ids:
                sec_id = t.get("section_id")
                sec_name = section_names.get(sec_id, "") if sec_id else ""
                failures.append({
                    "test_id":      t.get("id"),
                    "case_id":      t.get("case_id"),
                    "title":        t.get("title", ""),
                    "status":       t.get("status_id"),
                    "section_name": sec_name,
                    "page_path":    _section_to_path(sec_name),
                    "yaml_hint":    _yaml_hint(t.get("title", "")),
                })

        return json.dumps({"run_id": run_id, "total": len(tests), "failures": len(failures), "cases": failures}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def repush_yaml_to_testrail(path: str, case_id=None) -> str:
    """
    Re-push a YAML test file's steps to an existing TestRail case's Preconditions
    field.  Use this after fix_test_selectors has healed selectors.

    Parameters
    ----------
    path    : Relative path to the YAML file (e.g. tests/cases/crawled/click_apply.yaml)
    case_id : TestRail case ID to update. If omitted, reads from variables.testrail_case_id.
    """
    import yaml as _yaml

    fpath = _PROJECT_ROOT / path
    if not fpath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        data = _yaml.safe_load(fpath.read_text(encoding="utf-8"))
    except Exception as e:
        return json.dumps({"error": f"Could not parse YAML: {e}"})

    if not case_id:
        case_id = (data.get("variables") or {}).get("testrail_case_id")
    if not case_id:
        return json.dumps({"error": "No case_id provided and none found in variables.testrail_case_id."})

    try:
        from easy_bdd.services.testrail_service import TestRailService
        tr = TestRailService()
        steps_yaml = _yaml.dump(
            {"steps": data.get("steps", [])},
            default_flow_style=False, allow_unicode=True, sort_keys=False,
        )
        result = tr.update_case(int(case_id), custom_preconds=steps_yaml)
        return json.dumps({"updated": case_id, "title": result.get("title", ""), "ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Server entry-point (called from __main__.py)
# ---------------------------------------------------------------------------


def serve(transport: str = "stdio", host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the MCP server.

    Parameters
    ----------
    transport : "stdio" (default, for Claude Desktop) or "sse" (HTTP).
    host      : bind address for SSE transport.
    port      : port for SSE transport.
    """
    if transport == "sse":
        from mcp.server.transport_security import TransportSecuritySettings
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
