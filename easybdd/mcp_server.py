"""
Easy BDD MCP (Model Context Protocol) server.

Exposes the Easy BDD framework to AI models as Tools, Resources, and Prompts
following the Model Context Protocol specification.

Usage:
    python -m easybdd mcp-serve            # STDIO transport (default, for Claude Desktop)
    python -m easybdd mcp-serve --sse      # SSE transport (for web clients)
    python -m easybdd mcp-serve --port 8080 --sse

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

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Path components MCP clients may never touch, even inside the project root:
# secrets, virtualenvs and VCS internals. Anything *outside* the project root
# is always refused.
_FORBIDDEN_PARTS = frozenset({".git", "env", "venv", ".venv", ".claude", "node_modules"})


def _abs(p: str | Path) -> Path:
    """Resolve a client-supplied path, confined to the project root.

    Relative paths resolve against the project root. Absolute paths are
    allowed only if they land inside the project root after resolving
    symlinks. Raises ValueError for anything outside the root or touching
    secrets (.env*), virtualenvs or VCS internals.
    """
    path = Path(p)
    resolved = (path if path.is_absolute() else _PROJECT_ROOT / path).resolve()
    try:
        rel = resolved.relative_to(_PROJECT_ROOT)
    except ValueError:
        raise ValueError(
            f"Access denied: '{p}' resolves outside the Easy BDD project root."
        ) from None
    for part in rel.parts:
        if part in _FORBIDDEN_PARTS or part.startswith(".env"):
            raise ValueError(f"Access denied: '{p}' touches a restricted path ('{part}').")
    return resolved


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
    ss_dir = _abs(shared_steps_dir) if shared_steps_dir else None

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
        Use `${variable_name}` anywhere in a string value.  Variables are
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
        from easybdd.services.testrail_service import TestRailService

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
        from easybdd.services.testrail_service import TestRailService
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
# Playwright recorder import
# ---------------------------------------------------------------------------


@mcp.tool()
def import_playwright_recording(
    source: str,
    test_name: str = "",
    project_id: int = 0,
    suite_id: int = 0,
    suite_name: str = "",
    section_name: str = "Imported from Playwright",
    output_dir: str = "tests/cases/imported",
    push_to_testrail: bool = False,
) -> str:
    """
    Convert a Playwright CRX recording to Easy BDD test cases (YAML) and
    optionally push them to TestRail.

    Parameters
    ----------
    source          : File path to a .js / .ts / .json / .zip trace file,
                      OR raw JS/TS code pasted directly as a string.
    test_name       : Override the test case name (used when source is raw code
                      with no test() wrapper).
    project_id      : TestRail project ID (required if push_to_testrail=True).
    suite_id        : TestRail suite ID (0 = create/find by suite_name).
    suite_name      : Name of the TestRail suite to create or reuse when suite_id=0.
                      Defaults to "Imported from Playwright" if not provided.
    section_name    : TestRail section to create/reuse within the suite.
    output_dir      : Where to write YAML files (relative to project root).
    push_to_testrail: If True, push cases to TestRail immediately after conversion.
    """
    from easybdd.crawler.playwright_importer import import_recording

    try:
        abs_output = str(_PROJECT_ROOT / output_dir)
        cases = import_recording(
            source=source,
            default_name=test_name or "Imported test",
            output_dir=abs_output,
        )
    except Exception as e:
        return json.dumps({"error": f"Import failed: {e}"})

    result: Dict[str, Any] = {
        "cases_imported": len(cases),
        "output_dir": output_dir,
        "cases": [{"name": c.name, "steps": len(c.steps), "tags": c.tags} for c in cases],
    }

    if push_to_testrail and cases and project_id:
        try:
            from easybdd.services.testrail_service import TestRailService
            from easybdd.crawler.testrail_publisher import TestRailPublisher

            tr = TestRailService()
            publisher = TestRailPublisher(
                testrail=tr,
                project_id=project_id,
                suite_id=suite_id or None,
                suite_name=suite_name or "Imported from Playwright",
                section_name=section_name,
            )
            case_ids = publisher.publish_all(cases)
            result["testrail_case_ids"] = case_ids
            result["pushed"] = len(case_ids)
        except Exception as e:
            result["testrail_error"] = str(e)

    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Ollama direct interface
# ---------------------------------------------------------------------------


@mcp.tool()
def ollama_chat(
    prompt: str,
    system: str = "",
    model: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Send a prompt directly to the configured Ollama model and return the response.

    Useful for:
      - Asking Ollama to analyse a test case or page snapshot
      - Generating test ideas for a specific feature
      - Reviewing Easy BDD YAML and suggesting improvements
      - Any freeform LLM task without leaving the MCP context

    Parameters
    ----------
    prompt      : The user message to send.
    system      : Optional system prompt (overrides the default).
    model       : Ollama model name. Defaults to CRAWLER_AI_MODEL from .env.
    temperature : Sampling temperature (0 = deterministic, 1 = creative).
    max_tokens  : Maximum tokens in the response.
    """
    import requests as _requests

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = model or os.getenv("CRAWLER_AI_MODEL", "qwen3-coder:30b-a3b-q4_K_M")
    timeout = int(os.getenv("OLLAMA_TIMEOUT", "1200"))
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

    default_system = (
        "You are an expert QA engineer and test automation specialist. "
        "You help with Easy BDD test cases, Playwright scripts, and test strategy."
    )

    messages = []
    if system or default_system:
        messages.append({"role": "system", "content": system or default_system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = _requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": num_ctx,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return json.dumps({"response": content, "model": model})
    except Exception as e:
        return json.dumps({"error": str(e), "base_url": base_url, "model": model})


@mcp.tool()
def ollama_analyze_test(path: str = "", case_id: int = 0, question: str = "") -> str:
    """
    Ask Ollama to review an Easy BDD test case and suggest improvements.
    Accepts either a local YAML file path OR a TestRail case ID.

    Parameters
    ----------
    path     : Relative path to a YAML file (e.g. tests/cases/crawled/login.yaml).
    case_id  : TestRail case ID — fetches steps from custom_preconds field.
    question : Custom question to ask Ollama (optional).
    """
    import yaml as _yaml
    import requests as _requests

    # ── Load content from YAML file OR TestRail case ──────────────────────────
    test_name = path or f"Case {case_id}"
    content = ""

    if case_id:
        try:
            from easybdd.services.testrail_service import TestRailService
            tr = TestRailService()
            case = tr.get_case(case_id)
            test_name = case.get("title", f"Case {case_id}")
            preconds = case.get("custom_preconds") or ""
            content = (
                f"# TestRail case {case_id}: {test_name}\n"
                f"# Section: {case.get('section_id', '')}\n\n"
                f"{preconds}"
            )
        except Exception as e:
            return json.dumps({"error": f"Could not fetch TestRail case {case_id}: {e}"})
    elif path:
        fpath = _abs(path)
        if not fpath.exists():
            return json.dumps({"error": f"File not found: {path}"})
        try:
            content = fpath.read_text(encoding="utf-8")
            data = _yaml.safe_load(content)
            test_name = data.get("name", path) if isinstance(data, dict) else path
        except Exception as e:
            return json.dumps({"error": f"Could not read YAML: {e}"})
    else:
        return json.dumps({"error": "Provide either path or case_id."})

    default_q = (
        "Review this Easy BDD test case. "
        "1. Identify any missing assertions or verification steps. "
        "2. Suggest 2-3 additional test cases for this feature. "
        "3. Note any steps that might be fragile or need better selectors."
    )

    prompt = f"{question or default_q}\n\nTest case:\n```yaml\n{content}\n```"

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("CRAWLER_AI_MODEL", "qwen3-coder:30b-a3b-q4_K_M")
    timeout = int(os.getenv("OLLAMA_TIMEOUT", "1200"))

    try:
        resp = _requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an expert QA engineer reviewing Easy BDD test cases."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": 2048, "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096"))},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        analysis = resp.json()["message"]["content"]
        return json.dumps({
            "test_name": test_name,
            "case_id": case_id or None,
            "analysis": analysis,
            "model": model,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def ollama_generate_tests(
    feature_description: str,
    page_url: str = "",
    existing_selectors: str = "",
    count: int = 5,
    push_to_testrail: bool = False,
    project_id: int = 0,
    suite_id: int = 0,
    section_name: str = "Ollama Generated",
    output_dir: str = "tests/cases/generated",
) -> str:
    """
    Ask Ollama to generate new Easy BDD test cases for a described feature.
    Optionally writes YAML files and pushes directly to TestRail.

    Parameters
    ----------
    feature_description : Plain-English description of the feature to test.
                          e.g. "Wi-Fi settings page with SSID, password, and Apply button"
    page_url            : URL of the page (used as browser.open target).
    existing_selectors  : Optional comma-separated selectors from the page to anchor tests to.
    count               : How many test cases to generate (default 5).
    push_to_testrail    : If True, push generated cases to TestRail.
    project_id          : TestRail project ID (required if push_to_testrail=True).
    suite_id            : TestRail suite ID (0 = default suite).
    section_name        : TestRail section to create/reuse.
    output_dir          : Where to write YAML files (relative to project root).
    """
    import requests as _requests

    system = """\
You are a QA automation engineer. Generate Easy BDD test cases in YAML format.

Easy BDD step syntax:
  - browser.open:              {url: "${base_url}"}
  - browser.fill:              {selector: "#field", value: "text"}
  - browser.click:             {selector: "role=button[name='Save']"}
  - browser.select:            {selector: "#dropdown", value: "option"}
  - browser.wait_for:          {selector: "text='Success'", timeout: 5000}
  - test.assert_text_contains: {selector: ".status", text: "Settings saved"}
  - test.assert_text_equals:   {selector: ".label", text: "ON"}
  - browser.assert_visible:    {selector: ".success-banner"}
  - browser.screenshot:        {name: "descriptive-name"}

Return ONLY valid YAML — a list of test case objects:
- name: "Test name"
  description: "What this verifies"
  tags: [browser, functional]
  steps:
    - browser.open: {url: "${base_url}"}
    - browser.fill: {selector: "#field", value: "value"}
    - browser.click: {selector: "role=button[name='Save']"}
    - browser.wait_for: {selector: "text='Saved'", timeout: 5000}
    - browser.screenshot: {name: "after-save"}
"""

    selector_hint = f"\n\nKnown selectors on this page: {existing_selectors}" if existing_selectors else ""
    url_hint = f"\nPage URL: {page_url}" if page_url else ""

    prompt = (
        f"Generate {count} functional Easy BDD test cases for:\n\n"
        f"{feature_description}{url_hint}{selector_hint}\n\n"
        f"Focus on: happy path, validation errors, edge cases, and save/apply workflows. "
        f"Use realistic test data values, not placeholders like 'value1'."
    )

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("CRAWLER_AI_MODEL", "qwen3-coder:30b-a3b-q4_K_M")
    timeout = int(os.getenv("OLLAMA_TIMEOUT", "1200"))

    try:
        resp = _requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "num_predict": 3000,
                    "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096")),
                    "temperature": 0.3,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        yaml_output = resp.json()["message"]["content"]

        # Strip markdown fences if present
        yaml_clean = yaml_output.strip()
        for fence in ("```yaml", "```"):
            if fence in yaml_clean:
                yaml_clean = yaml_clean.split(fence, 1)[1].split("```")[0].strip()
                break

        result: Dict[str, Any] = {"yaml": yaml_clean, "model": model}

        # Optionally write YAML files and push to TestRail
        if push_to_testrail or output_dir:
            import yaml as _yaml
            from pathlib import Path as _Path
            from easybdd.crawler.models import GeneratedTestCase, GeneratedStep

            try:
                raw_cases = _yaml.safe_load(yaml_clean)
                if not isinstance(raw_cases, list):
                    raw_cases = [raw_cases]

                cases = []
                for rc in raw_cases:
                    if not isinstance(rc, dict):
                        continue
                    steps = []
                    for action, params in (rc.get("steps") or []):
                        if isinstance(params, dict):
                            steps.append(GeneratedStep(action=action, params=params))
                        elif isinstance(params, str):
                            steps.append(GeneratedStep(action=action, params={"selector": params}))
                    cases.append(GeneratedTestCase(
                        name=rc.get("name", "Generated test"),
                        description=rc.get("description", ""),
                        tags=rc.get("tags", ["browser", "generated"]),
                        url=page_url,
                        steps=steps,
                    ))

                if output_dir:
                    from easybdd.crawler.yaml_writer import write_test_case
                    out = _abs(output_dir)
                    out.mkdir(parents=True, exist_ok=True)
                    for case in cases:
                        write_test_case(case, out)
                    result["files_written"] = len(cases)

                if push_to_testrail and project_id and cases:
                    from easybdd.services.testrail_service import TestRailService
                    from easybdd.crawler.testrail_publisher import TestRailPublisher
                    tr = TestRailService()
                    publisher = TestRailPublisher(
                        testrail=tr,
                        project_id=project_id,
                        suite_id=suite_id or None,
                        section_name=section_name,
                    )
                    case_ids = publisher.publish_all(cases)
                    result["testrail_case_ids"] = case_ids
                    result["pushed"] = len(case_ids)

            except Exception as e:
                result["push_error"] = str(e)

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def ollama_improve_testrail_case(
    case_id: int,
    write_back: bool = False,
    question: str = "",
) -> str:
    """
    Fetch a TestRail case, send its steps to Ollama for improvement suggestions,
    and optionally write the improved steps back to TestRail.

    Parameters
    ----------
    case_id    : TestRail case ID to fetch and improve.
    write_back : If True, updates the TestRail case's Preconditions with the
                 improved YAML that Ollama generates.
    question   : Custom improvement instruction (optional).
                 Default: fix missing assertions, add validation steps, improve selectors.
    """
    import yaml as _yaml
    import requests as _requests

    try:
        from easybdd.services.testrail_service import TestRailService
        tr = TestRailService()
        case = tr.get_case(case_id)
    except Exception as e:
        return json.dumps({"error": f"Could not fetch case {case_id}: {e}"})

    title = case.get("title", f"Case {case_id}")
    current_steps = case.get("custom_preconds") or ""

    if not current_steps.strip():
        return json.dumps({"error": f"Case {case_id} has no steps in custom_preconds."})

    default_q = (
        "Improve this Easy BDD test case. Return ONLY the improved YAML steps — "
        "no explanation, no markdown, just the YAML.\n\n"
        "Improvements to make:\n"
        "1. Add browser.wait_for after any save/apply/submit clicks\n"
        "2. Add browser.assert_text or browser.assert_visible to verify outcomes\n"
        "3. Replace generic ${field_N_value} placeholders with realistic test values\n"
        "4. Add a browser.screenshot at the end if missing\n"
        "5. Fix any steps that look incomplete or fragile"
    )

    prompt = f"{question or default_q}\n\nCurrent test case '{title}':\n```yaml\n{current_steps}\n```"

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("CRAWLER_AI_MODEL", "qwen3-coder:30b-a3b-q4_K_M")
    timeout = int(os.getenv("OLLAMA_TIMEOUT", "1200"))

    try:
        resp = _requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an expert QA engineer improving Easy BDD test cases. Return only valid YAML."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": 2048, "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096"))},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        improved = resp.json()["message"]["content"].strip()

        # Strip fences
        for fence in ("```yaml", "```"):
            if fence in improved:
                improved = improved.split(fence, 1)[1].split("```")[0].strip()
                break

        result: Dict[str, Any] = {
            "case_id": case_id,
            "title": title,
            "original": current_steps,
            "improved": improved,
            "model": model,
            "written_back": False,
        }

        if write_back:
            try:
                tr.update_case(case_id, custom_preconds=improved)
                result["written_back"] = True
            except Exception as e:
                result["write_back_error"] = str(e)

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# WORKFLOW PROMPTS — high-level orchestration for test engineers
# ---------------------------------------------------------------------------


@mcp.prompt()
def debug_testrail_run(run_id: int, auto_fix: bool = False) -> str:
    """
    Prompt: End-to-end debugging workflow for a failing TestRail run.

    Fetches failures, cross-references local YAML files, probes live selectors,
    suggests fixes, and (when auto_fix=True) applies and re-pushes them.

    Parameters
    ----------
    run_id   : TestRail run ID to debug (e.g. 194886).
    auto_fix : if True, also apply selector fixes and re-push to TestRail.
    """
    failures = get_testrail_run_failures(run_id=run_id)

    return textwrap.dedent(
        f"""
        You are an Easy BDD test engineer debugging a failing TestRail run.
        Work through each failure methodically using the tools available.

        ## Failing Run: R{run_id}
        ```json
        {failures}
        ```

        ## Step-by-step workflow

        ### 1 — Triage failures
        For each case in `failures`:
        - Note the `title`, `page_path`, and `yaml_hint` fields.
        - Group them by `section_name` (same page = same root cause).

        ### 2 — Locate local YAML files
        For each yaml_hint, call `list_tests` filtered to that filename, or call
        `get_test` with the path `tests/cases/crawled/<yaml_hint>`.
        If no local file exists, skip to step 5 (validate via TestRail).

        ### 3 — Validate the YAML
        Call `validate_test(path=<path>)` for each local file.
        Summarise errors and warnings per file.

        ### 4 — Probe live selectors (if any step has selector issues)
        For steps flagged with selector errors, call `probe_selector` with:
          - `url`: the `page_path` from the failure (prepend the device base URL)
          - `selector`: the failing CSS/ARIA selector
          - `fallback_selectors`: any alternatives you can infer

        {"### 5 — Apply fixes and re-push" if auto_fix else "### 5 — Preview fixes (read-only)"}
        {"Call `fix_test_selectors(path=<path>)` to heal selectors in-place, then `repush_yaml_to_testrail(path=<path>)` to update the TestRail case." if auto_fix else "Call `preview_fix(path=<path>)` to show what would change WITHOUT writing files. Present the corrected YAML for each case and ask the engineer to confirm before applying."}

        ### 6 — Validate TestRail cases directly (if no local file)
        Call `validate_testrail_case(run_id={run_id})` to check syntax in
        TestRail's Preconditions field for all Feature:/Shared: cases in the run.

        ### 7 — Summary
        Produce a table:
        | Case title | Local file | Status | Action taken |
        List any cases you could not fix and explain why.

        ## Rules
        - Always call `preview_fix` before `apply_fix` and confirm with the engineer.
        - Never call `apply_fix` with confirmed=True without explicit approval.
        - If `probe_selector` fails (navigation error), note the device may be offline.
        """
    )


@mcp.prompt()
def validate_testrail_suite(project_id: int, suite_id: int, fix: bool = False) -> str:
    """
    Prompt: Validate every case in a TestRail suite and produce a prioritised fix plan.

    Parameters
    ----------
    project_id : TestRail project ID.
    suite_id   : TestRail suite ID to validate.
    fix        : if True, also generate corrected YAML for each fixable issue.
    """
    validation = validate_testrail_case(suite_id=suite_id, project_id=project_id)

    return textwrap.dedent(
        f"""
        You are an Easy BDD quality engineer validating a TestRail suite.

        ## Suite S{suite_id} — Validation Results
        ```json
        {validation}
        ```

        ## Your task

        ### 1 — Executive summary
        Report: total cases, error count, warning count, % passing.
        State whether the suite is ready to run or needs fixes first.

        ### 2 — Error catalogue (ERRORS only, sorted by frequency)
        Group errors by `message` type.  For each type:
        - Show the error message and how many cases are affected.
        - Show one representative `location` and `reason`.
        - Provide the canonical fix (the `suggestion` field).

        ### 3 — Case-level details (ERROR cases only)
        For each case with errors, show:
        | Case ID | Title | Errors | Top issue |

        ### 4 — Fix plan
        {"For each fixable issue (where `correction` is non-null), show the corrected YAML snippet. Ask the engineer which cases to push corrections back to TestRail for, then call `validate_testrail_case` per case to confirm the fix is clean." if fix else "List which issues are auto-fixable (correction field is non-null) vs. need manual attention. Offer to generate corrected YAML if the engineer wants to proceed."}

        ### 5 — Warnings (brief)
        List warning types and affected case count — don't enumerate each case.

        ## Rules
        - Do not push any corrections to TestRail without explicit engineer approval.
        - Focus on ERRORs first; warnings are advisory.
        - If `total_cases` is 0, explain that no Feature:/Shared: cases were found.
        """
    )


@mcp.prompt()
def create_test_from_description(
    feature_description: str,
    page_url: str = "",
    project_id: int = 0,
    suite_id: int = 0,
    count: int = 5,
) -> str:
    """
    Prompt: Generate Easy BDD tests from a plain-English description, optionally
    push them to TestRail.

    Parameters
    ----------
    feature_description : What feature or page should be tested.
    page_url            : URL of the page (used as browser.open target).
    project_id          : TestRail project ID (required to push to TestRail).
    suite_id            : TestRail suite ID (0 = default suite).
    count               : Number of test cases to generate (default 5).
    """
    syntax_ref  = resource_docs_syntax()
    action_ref  = resource_docs_actions()
    shared      = resource_shared_steps()

    push_section = (
        f"If the engineer approves, call `ollama_generate_tests` with:\n"
        f"  feature_description=<description>, page_url=\"{page_url}\",\n"
        f"  push_to_testrail=True, project_id={project_id}, suite_id={suite_id},\n"
        f"  count={count}."
        if project_id else
        "If the engineer approves, call `ollama_generate_tests` with the description and page_url. "
        "Ask for a TestRail project_id and suite_id if they want to push cases there."
    )

    return textwrap.dedent(
        f"""
        You are an Easy BDD test author.  Generate complete, runnable test cases
        for the feature described below, then offer to push them to TestRail.

        ## Feature to test
        {feature_description}
        {"Page URL: " + page_url if page_url else ""}

        ## Workflow

        ### Step 1 — Clarify scope (ask if unclear)
        - What is the happy path?
        - What validation/error states exist?
        - Are there any shared steps already available (see below)?
        - What is the target device/environment base URL?

        ### Step 2 — Generate test cases
        Call `ollama_generate_tests` with:
          feature_description="{feature_description}"
          {"page_url=" + repr(page_url) if page_url else "page_url=<ask the engineer>"}
          count={count}
          push_to_testrail=False   # generate only, don't push yet

        ### Step 3 — Show and review
        Display the generated YAML test cases.  For each:
        - Verify selectors look reasonable (not generic placeholders).
        - Check that assertions (browser.assert_text / browser.assert_visible) are present.
        - Suggest improvements inline.

        ### Step 4 — Validate syntax
        Call `validate_test(snippet=<generated_yaml>)` for each case.
        Fix any errors before proceeding.

        ### Step 5 — Push to TestRail (with approval)
        {push_section}

        ## Available Shared Steps
        {shared}

        ## Action Reference (abbreviated)
        {action_ref}

        ## Syntax Reference
        {syntax_ref}

        ## Rules
        - Never use placeholder values like "value1" or "field_N_value" in final tests.
        - Always include at least one assertion step per test.
        - Always add `browser.screenshot` as the last step.
        - Ask the engineer to confirm before pushing anything to TestRail.
        """
    )


# ---------------------------------------------------------------------------
# crawl_device — headless Playwright crawl → EasyBDD YAML → TestRail suite
# ---------------------------------------------------------------------------


@mcp.tool()
async def crawl_device(
    url: str,
    username: str,
    password: str,
    project_id: int,
    suite_name: str = "Automated Tests",
    output_dir: str = "tests/cases/crawled",
    push_to_testrail: bool = True,
    max_pages: int = 30,
    login_username_selector: str = "",
    login_password_selector: str = "",
    login_button_selector: str = "",
    nav_selector: str = "",
    ignore_ssl: bool = True,
) -> str:
    """
    Parameters
    ----------
    url                      : Base URL of the device (e.g. https://192.168.100.145)
    username                 : Login username
    password                 : Login password
    project_id               : TestRail project ID for the new suite
    suite_name               : Name of the new TestRail suite to create
    output_dir               : Local directory to write YAML files
    push_to_testrail         : Create new suite and push cases (default True)
    max_pages                : Maximum number of pages to visit (default 30)
    login_username_selector  : Override auto-detected username selector
    login_password_selector  : Override auto-detected password selector
    login_button_selector    : Override auto-detected login button selector
    nav_selector             : CSS selector for navigation links (auto-detected if blank)
    ignore_ssl               : Ignore SSL certificate errors (default True for self-signed)
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return json.dumps({"error": "playwright not installed"})

    from easybdd.crawler.accessibility_snapshotter import snapshot_page_a11y_async as snapshot_page_a11y
    from easybdd.crawler.rule_based_analyzer import analyze_snapshot_rules
    from easybdd.crawler.yaml_writer import write_all_cases
    from easybdd.crawler.models import GeneratedTestCase
    from urllib.parse import urlparse, urljoin
    import time as _time

    base_url = url.rstrip("/")
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    pages_visited: list = []
    all_cases: list = []
    errors: list = []

    async def _login(page) -> bool:
        user_candidates = (
            [login_username_selector] if login_username_selector
            else ["#login-usernameIpt", "#username", "#email",
                  'input[name="username"]', 'input[type="text"]',
                  'input[name="email"]', 'input[placeholder*="sername"]']
        )
        pass_candidates = (
            [login_password_selector] if login_password_selector
            else ["#login-passwordIpt", "#password", 'input[type="password"]',
                  'input[name="password"]', 'input[name="pass"]']
        )
        btn_candidates = (
            [login_button_selector] if login_button_selector
            else ["#login-login-btn", 'button[type="submit"]', 'input[type="submit"]',
                  'button:has-text("Login")', 'button:has-text("Sign in")',
                  'button:has-text("Log in")', ".login-btn", "#loginBtn"]
        )

        user_sel = pass_sel = btn_sel = None
        for sel in user_candidates:
            try:
                if await page.locator(sel).count() > 0:
                    user_sel = sel
                    break
            except Exception:
                continue
        for sel in pass_candidates:
            try:
                if await page.locator(sel).count() > 0:
                    pass_sel = sel
                    break
            except Exception:
                continue
        for sel in btn_candidates:
            try:
                if await page.locator(sel).count() > 0:
                    btn_sel = sel
                    break
            except Exception:
                continue

        if not (user_sel and pass_sel):
            errors.append("Could not auto-detect login form selectors")
            return False

        try:
            await page.fill(user_sel, username)
            await page.fill(pass_sel, password)
            if btn_sel:
                await page.click(btn_sel)
            else:
                await page.keyboard.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1500)
            return True
        except Exception as exc:
            errors.append(f"Login failed: {exc}")
            return False

    async def _discover_nav_links(page) -> list:
        nav_candidates = (
            [nav_selector] if nav_selector
            else ["#sidebar a", "nav a", ".sidebar a", ".nav a",
                  '[role="navigation"] a', ".menu a", "#menu a",
                  ".left-nav a", "#leftnav a", ".sidenav a"]
        )
        seen = set()
        links = []
        for sel in nav_candidates:
            try:
                elements = await page.locator(sel).all()
                for el in elements:
                    href = await el.get_attribute("href") or ""
                    if not href or href.startswith("#") or href.startswith("javascript"):
                        continue
                    full = urljoin(base_url, href)
                    if not full.startswith(origin):
                        continue
                    if full not in seen:
                        seen.add(full)
                        links.append(full)
                if links:
                    break
            except Exception:
                continue

        if not links:
            try:
                for el in await page.locator("a[href]").all():
                    href = await el.get_attribute("href") or ""
                    if not href or href.startswith("#") or href.startswith("javascript"):
                        continue
                    full = urljoin(base_url, href)
                    if full.startswith(origin) and full not in seen:
                        seen.add(full)
                        links.append(full)
            except Exception:
                pass

        return links[:max_pages]

    async def _crawl_page(page, page_url: str) -> tuple:
        path_parts = urlparse(page_url).path.strip("/").split("/")
        section = (path_parts[-1].replace("-", " ").replace("_", " ").title()
                   if path_parts and path_parts[-1] else "General")
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(800)
        except Exception as exc:
            errors.append(f"Navigation failed for {page_url}: {exc}")
            return [], section

        try:
            snapshot = await snapshot_page_a11y(page)
        except Exception as exc:
            errors.append(f"Snapshot failed for {page_url}: {exc}")
            return [], section

        try:
            cases = analyze_snapshot_rules(snapshot)
        except Exception as exc:
            errors.append(f"Analysis failed for {page_url}: {exc}")
            return [], section

        page_title = snapshot.title or section
        for case in cases:
            case.tags = list(set(case.tags) | {"crawled", "browser"})
            if not case.name.lower().startswith(page_title.lower()):
                case.name = f"{page_title} — {case.name}"

        pages_visited.append({
            "url": page_url,
            "title": snapshot.title,
            "section": section,
            "cases": len(cases),
        })
        return cases, section

    # ── Main crawl ───────────────────────────────────────────────────────────
    case_sections: list = []   # parallel list to all_cases: section name per case

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--ignore-certificate-errors", "--disable-web-security"]
            if ignore_ssl else [],
        )
        ctx = await browser.new_context(ignore_https_errors=ignore_ssl)
        page = await ctx.new_page()

        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1000)

            if not await _login(page):
                await browser.close()
                return json.dumps({"error": "Login failed", "details": errors})

            nav_links = await _discover_nav_links(page)
            landing = page.url
            if landing not in nav_links:
                nav_links.insert(0, landing)

            visited: set = set()
            for link in nav_links[:max_pages]:
                if link in visited:
                    continue
                visited.add(link)
                cases, section = await _crawl_page(page, link)
                for case in cases:
                    all_cases.append(case)
                    case_sections.append(section)

        finally:
            await browser.close()

    if not all_cases:
        return json.dumps({
            "pages_visited": len(pages_visited),
            "cases_generated": 0,
            "errors": errors,
            "message": "No test cases generated — no interactive elements found.",
        })

    # Write YAML files
    abs_output = _abs(output_dir)
    try:
        written_paths = write_all_cases(all_cases, abs_output, base_url=base_url)
    except Exception as exc:
        return json.dumps({"error": f"YAML write failed: {exc}", "errors": errors})

    # Push to TestRail
    pushed = 0
    testrail_suite_url = ""
    if push_to_testrail and project_id:
        try:
            import os as _os
            cfg = _load_config()
            tr_cfg = cfg.get("testrail", {})
            tr_url  = tr_cfg.get("url", "")  or _os.environ.get("TESTRAIL_URL", "")
            tr_user = tr_cfg.get("username", "") or _os.environ.get("TESTRAIL_USERNAME", "")
            tr_key  = tr_cfg.get("api_key", "")  or _os.environ.get("TESTRAIL_API_KEY", "")
            if not (tr_url and tr_user and tr_key):
                errors.append("TestRail credentials not configured in easybdd.yaml or env vars")
            else:
                from easybdd.services.testrail_service import TestRailService
                from easybdd.crawler.testrail_publisher import TestRailPublisher

                tr = TestRailService(tr_url, tr_user, tr_key)
                publisher = TestRailPublisher(
                    testrail=tr,
                    project_id=project_id,
                    suite_id=None,
                    suite_name=suite_name,
                    section_name="General",
                )
                for case, sec in zip(all_cases, case_sections):
                    try:
                        publisher.publish_case(case, section_name=sec)
                        pushed += 1
                    except Exception as exc:
                        errors.append(f"Push failed for '{case.name}': {exc}")

                sid = getattr(publisher, "_suite_id", None)
                if sid:
                    testrail_suite_url = (
                        f"{tr_url.rstrip('/')}/index.php?/suites/view/{sid}"
                    )
        except Exception as exc:
            errors.append(f"TestRail error: {exc}")

    return json.dumps({
        "pages_visited": len(pages_visited),
        "cases_generated": len(all_cases),
        "yaml_files_written": len(written_paths),
        "pushed_to_testrail": pushed,
        "suite_name": suite_name,
        "suite_url": testrail_suite_url,
        "pages": pages_visited,
        "errors": errors,
    }, indent=2)


# ---------------------------------------------------------------------------
# Onboarding routes (plain HTTP, only active for sse / streamable-http)
#
# Engineers set up their Claude client with one command — see onboarding/:
#   macOS / Linux:  curl -fsSL http://192.168.100.100:8092/setup | bash
#   Windows:        irm http://192.168.100.100:8092/setup.ps1 | iex
# Human-readable instructions live at /onboard.
# ---------------------------------------------------------------------------

_ONBOARDING_DIR = _PROJECT_ROOT / "onboarding"


def _onboarding_script(name: str):
    from starlette.responses import PlainTextResponse

    path = _ONBOARDING_DIR / name
    if not path.exists():
        return PlainTextResponse(f"echo 'Setup script {name} not found on server.'", status_code=404)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@mcp.custom_route("/setup", methods=["GET"])
async def route_setup_sh(request):
    return _onboarding_script("setup-easybdd-mcp.sh")


@mcp.custom_route("/setup.ps1", methods=["GET"])
async def route_setup_ps1(request):
    return _onboarding_script("setup-easybdd-mcp.ps1")


@mcp.custom_route("/jenkins-mcp-config", methods=["GET"])
async def route_jenkins_mcp_config(request):
    """Client config for the Jenkins MCP plugin — gated by the bearer token.

    Returns the Jenkins MCP endpoint plus a ready-made Basic Authorization
    header so the onboarding scripts can add a "jenkins" MCP server to
    engineers' Claude clients without anyone handling the Jenkins API token
    directly. The credentials live only in the production .env
    (JENKINS_URL / JENKINS_USERNAME / JENKINS_API_TOKEN — the same variables
    JenkinsService uses). 404s when they are not configured, which the
    setup scripts treat as "skip quietly".

    Not in _PUBLIC_PATHS on purpose: without EASYBDD_MCP_TOKEN set this
    would hand Jenkins credentials to anyone who can reach the port (the
    server already logs a loud warning when running unauthenticated).
    """
    import base64

    from starlette.responses import JSONResponse

    jenkins_url = os.environ.get("JENKINS_URL", "").strip().rstrip("/")
    username = os.environ.get("JENKINS_USERNAME", "").strip()
    api_token = os.environ.get("JENKINS_API_TOKEN", "").strip()
    if not (jenkins_url and username and api_token):
        return JSONResponse(
            {
                "error": "not_configured",
                "detail": "JENKINS_URL, JENKINS_USERNAME and JENKINS_API_TOKEN "
                          "are not all set in the server .env.",
            },
            status_code=404,
        )
    basic = base64.b64encode(f"{username}:{api_token}".encode()).decode()
    return JSONResponse(
        {
            "url": f"{jenkins_url}/mcp-server/mcp",
            "authorization": f"Basic {basic}",
        }
    )


@mcp.custom_route("/jira-mcp-config", methods=["GET"])
async def route_jira_mcp_config(request):
    """Client config for the self-hosted Jira MCP server — gated by the bearer token.

    Returns the mcp-atlassian endpoint plus a ready-made Basic Authorization
    header (Atlassian account email + Jira Cloud API token, the same shape
    mcp-atlassian's multi-user mode expects per-request) so the onboarding
    scripts can add a "jira" MCP server without anyone handling the Jira API
    token directly. Credentials live only in the production .env
    (JIRA_MCP_URL / JIRA_USERNAME / JIRA_API_TOKEN). 404s when they are not
    configured, which the setup scripts treat as "skip quietly".

    Not in _PUBLIC_PATHS on purpose: without EASYBDD_MCP_TOKEN set this
    would hand Jira credentials to anyone who can reach the port (the
    server already logs a loud warning when running unauthenticated).
    """
    import base64

    from starlette.responses import JSONResponse

    jira_mcp_url = os.environ.get("JIRA_MCP_URL", "").strip().rstrip("/")
    username = os.environ.get("JIRA_USERNAME", "").strip()
    api_token = os.environ.get("JIRA_API_TOKEN", "").strip()
    if not (jira_mcp_url and username and api_token):
        return JSONResponse(
            {
                "error": "not_configured",
                "detail": "JIRA_MCP_URL, JIRA_USERNAME and JIRA_API_TOKEN "
                          "are not all set in the server .env.",
            },
            status_code=404,
        )
    basic = base64.b64encode(f"{username}:{api_token}".encode()).decode()
    return JSONResponse(
        {
            "url": jira_mcp_url,
            "authorization": f"Basic {basic}",
        }
    )


@mcp.custom_route("/confluence-mcp-config", methods=["GET"])
async def route_confluence_mcp_config(request):
    """Client config for the self-hosted Confluence MCP server — gated by the bearer token.

    Same shape as /jira-mcp-config: returns the mcp-atlassian (Confluence mode)
    endpoint plus a ready-made Basic Authorization header (Atlassian account
    email + API token). Credentials live only in the production .env
    (CONFLUENCE_MCP_URL / CONFLUENCE_USERNAME / CONFLUENCE_API_TOKEN). 404s
    when they are not configured, which the setup scripts treat as
    "skip quietly".

    Not in _PUBLIC_PATHS on purpose: without EASYBDD_MCP_TOKEN set this
    would hand Confluence credentials to anyone who can reach the port (the
    server already logs a loud warning when running unauthenticated).
    """
    import base64

    from starlette.responses import JSONResponse

    confluence_mcp_url = os.environ.get("CONFLUENCE_MCP_URL", "").strip().rstrip("/")
    username = os.environ.get("CONFLUENCE_USERNAME", "").strip()
    api_token = os.environ.get("CONFLUENCE_API_TOKEN", "").strip()
    if not (confluence_mcp_url and username and api_token):
        return JSONResponse(
            {
                "error": "not_configured",
                "detail": "CONFLUENCE_MCP_URL, CONFLUENCE_USERNAME and "
                          "CONFLUENCE_API_TOKEN are not all set in the server .env.",
            },
            status_code=404,
        )
    basic = base64.b64encode(f"{username}:{api_token}".encode()).decode()
    return JSONResponse(
        {
            "url": confluence_mcp_url,
            "authorization": f"Basic {basic}",
        }
    )


@mcp.custom_route("/onboard", methods=["GET"])
async def route_onboard(request):
    from starlette.responses import HTMLResponse

    base = f"http://{request.url.hostname}:{request.url.port or 80}"
    jenkins_enabled = all(
        os.environ.get(v, "").strip()
        for v in ("JENKINS_URL", "JENKINS_USERNAME", "JENKINS_API_TOKEN")
    )
    jenkins_note = (
        """<li><code>jenkins</code> &mdash; control the Jenkins CI server (inspect jobs,
        trigger builds, read consoles). Currently <strong>enabled</strong>; the same
        commands below set it up automatically &mdash; no extra steps, no Jenkins
        credentials to handle.</li>"""
        if jenkins_enabled
        else """<li><code>jenkins</code> &mdash; control the Jenkins CI server. Currently
        <strong>not enabled</strong> on this server (an admin must set
        <code>JENKINS_URL</code> / <code>JENKINS_USERNAME</code> /
        <code>JENKINS_API_TOKEN</code> in the production <code>.env</code>); the setup
        commands below will skip it until then.</li>"""
    )
    jenkins_try = (
        """<li>Try: <em>"Using the jenkins tools, list the Jenkins jobs."</em></li>"""
        if jenkins_enabled
        else ""
    )
    jira_enabled = all(
        os.environ.get(v, "").strip()
        for v in ("JIRA_MCP_URL", "JIRA_USERNAME", "JIRA_API_TOKEN")
    )
    jira_note = (
        """<li><code>jira</code> &mdash; look up and update Jira issues. Currently
        <strong>enabled</strong>; the same commands below set it up automatically
        &mdash; no extra steps, no Jira credentials to handle.</li>"""
        if jira_enabled
        else """<li><code>jira</code> &mdash; look up and update Jira issues. Currently
        <strong>not enabled</strong> on this server (an admin must set
        <code>JIRA_MCP_URL</code> / <code>JIRA_USERNAME</code> /
        <code>JIRA_API_TOKEN</code> in the production <code>.env</code>); the setup
        commands below will skip it until then.</li>"""
    )
    jira_try = (
        """<li>Try: <em>"Using the jira tools, show me my open issues."</em></li>"""
        if jira_enabled
        else ""
    )
    confluence_enabled = all(
        os.environ.get(v, "").strip()
        for v in ("CONFLUENCE_MCP_URL", "CONFLUENCE_USERNAME", "CONFLUENCE_API_TOKEN")
    )
    confluence_note = (
        """<li><code>confluence</code> &mdash; search and read Confluence pages.
        Currently <strong>enabled</strong>; the same commands below set it up
        automatically &mdash; no extra steps, no Confluence credentials to
        handle.</li>"""
        if confluence_enabled
        else """<li><code>confluence</code> &mdash; search and read Confluence pages.
        Currently <strong>not enabled</strong> on this server (an admin must set
        <code>CONFLUENCE_MCP_URL</code> / <code>CONFLUENCE_USERNAME</code> /
        <code>CONFLUENCE_API_TOKEN</code> in the production <code>.env</code>); the
        setup commands below will skip it until then.</li>"""
    )
    confluence_try = (
        """<li>Try: <em>"Using the confluence tools, search for our onboarding docs."</em></li>"""
        if confluence_enabled
        else ""
    )
    return HTMLResponse(textwrap.dedent(f"""\
        <!doctype html>
        <html><head><meta charset="utf-8"><title>Easy BDD MCP setup</title>
        <style>
          body {{ font-family: system-ui, sans-serif; max-width: 46rem; margin: 3rem auto; padding: 0 1rem; line-height: 1.5; }}
          code, pre {{ background: #f4f4f4; border-radius: 6px; padding: 0.15rem 0.4rem; }}
          pre {{ padding: 0.8rem; overflow-x: auto; }}
          h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
        </style></head><body>
        <h1>Connect AI clients to Easy BDD</h1>
        <p>One-time setup. These commands configure Claude Desktop/Code and GitHub
        Copilot in VS Code (native MCP). Be on the office network / VPN and use the
        <strong>access token</strong> (ask Mark Fomin). No repository checkout needed.</p>

        <h2>What gets set up</h2>
        <ul>
          <li><code>easybdd</code> &mdash; run and fix tests, browse TestRail runs, and
          drive the Easy BDD framework from Claude or Copilot.</li>
          {jenkins_note}
          {jira_note}
          {confluence_note}
        </ul>

        <h2>Windows</h2>
        <p>Open <strong>PowerShell</strong> (Start menu &rarr; type "PowerShell") and paste
        (replace <code>PASTE-TOKEN-HERE</code> with the token):</p>
        <pre>$env:EASYBDD_TOKEN="PASTE-TOKEN-HERE"; irm {base}/setup.ps1 | iex</pre>

        <h2>macOS / Linux</h2>
        <p>Open <strong>Terminal</strong> and paste (replace <code>PASTE-TOKEN-HERE</code>
        with the token):</p>
        <pre>curl -fsSL {base}/setup | EASYBDD_TOKEN=PASTE-TOKEN-HERE bash</pre>
        <p>If you leave the token out, the script simply asks you for it.</p>

                <h2>Then</h2>
        <ol>
          <li>Fully quit Claude Desktop (system tray / menu bar &rarr; Quit) and reopen it.</li>
          <li>In a new chat, click the tools (sliders) icon under the message box &mdash; you should see <code>easybdd</code>{" and <code>jenkins</code>" if jenkins_enabled else ""}{" and <code>jira</code>" if jira_enabled else ""}{" and <code>confluence</code>" if confluence_enabled else ""}.</li>
          <li>Try: <em>"Using the easybdd tools, list the available tests."</em></li>
                    <li>For GitHub Copilot: restart VS Code (or run <em>Developer: Reload Window</em>), then ask the same prompt in Copilot Chat.</li>
          {jenkins_try}
          {jira_try}
          {confluence_try}
        </ol>

        <p>Problems? Contact Mark Fomin.</p>
        </body></html>
    """))


# ---------------------------------------------------------------------------
# Server entry-point (called from __main__.py)
# ---------------------------------------------------------------------------


# Routes that stay public even when EASYBDD_MCP_TOKEN is set — engineers must
# be able to fetch the setup scripts before they have anything configured.
_PUBLIC_PATHS = frozenset({"/onboard", "/setup", "/setup.ps1"})


class _BearerAuthMiddleware:
    """Require 'Authorization: Bearer <token>' on all HTTP routes except _PUBLIC_PATHS."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] not in _PUBLIC_PATHS:
            import hmac

            auth = ""
            for name, value in scope.get("headers", []):
                if name == b"authorization":
                    auth = value.decode("latin-1")
                    break
            supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(supplied, self.token):
                body = json.dumps({
                    "error": "unauthorized",
                    "detail": "Missing or invalid bearer token. "
                              "Re-run setup from http://192.168.100.100:8092/onboard "
                              "or ask Mark Fomin for the access token.",
                }).encode()
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b"Bearer"),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def serve(transport: str = "stdio", host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the MCP server."""
    if transport in ("sse", "streamable-http"):
        from mcp.server.fastmcp.server import TransportSecuritySettings
        mcp.settings.host = host
        mcp.settings.port = port
        # Disable DNS rebinding protection so LAN clients can connect via IP.
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )

        token = os.environ.get("EASYBDD_MCP_TOKEN", "").strip()
        if token:
            import uvicorn

            app = (
                mcp.streamable_http_app()
                if transport == "streamable-http"
                else mcp.sse_app()
            )
            logger.info("Bearer-token auth ENABLED (EASYBDD_MCP_TOKEN is set).")
            uvicorn.run(
                _BearerAuthMiddleware(app, token),
                host=host,
                port=port,
                log_level=mcp.settings.log_level.lower(),
            )
        else:
            logger.warning(
                "EASYBDD_MCP_TOKEN is not set — the MCP server is UNAUTHENTICATED. "
                "Anyone who can reach this port has full tool access."
            )
            mcp.run(transport=transport)
    else:
        mcp.run(transport="stdio")
