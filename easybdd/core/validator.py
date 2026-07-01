"""
Easy BDD test case validator.

Validates full test files or raw step snippets for:
  - YAML syntax and indentation
  - Step structure (action format, control-flow constructs)
  - Known action names and required/optional parameters
  - Shared step name resolution (with case-mismatch hints)
  - Variable reference syntax
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

import yaml


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    severity: str    # "ERROR" or "WARNING"
    location: str    # e.g. "steps[0].for_each.steps[1]"
    message: str     # short one-liner
    reason: str      # why this is a problem
    suggestion: str = ""             # how to fix it (free-text)
    correction: Optional[str] = None # exact YAML snippet to paste as the replacement

    def __str__(self) -> str:
        tag = "ERROR  " if self.severity == "ERROR" else "WARNING"
        lines = [f"  [{tag}] {self.location}"]
        lines.append(f"           {self.message}")
        lines.append(f"     Why:  {self.reason}")
        if self.suggestion:
            lines.append(f"     Fix:  {self.suggestion}")
        if self.correction:
            lines.append("     Replace with:")
            for ln in self.correction.rstrip().splitlines():
                lines.append(f"       {ln}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Action schema
# ---------------------------------------------------------------------------
# Each entry maps an action name (lowercase) to its schema:
#   required: list of required parameter names
#   optional: list of optional parameter names (or _P_ANY for open-schema)
#   alias_of: canonical action name (if this is a legacy/alternate spelling)

_P_ANY = "..."  # sentinel: accept any parameters without warning

ACTION_SCHEMA: Dict[str, Dict] = {
    # test.*
    "test.assert":           {"required": ["expression"], "optional": ["message"]},
    "assert":                {"alias_of": "test.assert"},
    "test.sleep":            {"required": [], "optional": ["seconds", "duration", "timeout"]},
    "sleep":                 {"alias_of": "test.sleep"},
    "test.wait":             {"alias_of": "test.sleep"},
    "wait":                  {"alias_of": "test.sleep"},
    "test.print":            {"required": [], "optional": ["message", "text", "value"]},
    "print":                 {"alias_of": "test.print"},
    "test.log":              {"alias_of": "test.print"},
    "log":                   {"alias_of": "test.print"},
    "test.check_assertions": {"required": [], "optional": []},
    "check soft assertions": {"alias_of": "test.check_assertions"},
    "test.run":              {"required": ["path"], "optional": ["tags"]},
    "run test":              {"alias_of": "test.run"},
    "execute test":          {"alias_of": "test.run"},
    "test.assert_schema":    {"required": ["schema"], "optional": ["data"]},
    "assert json schema":    {"alias_of": "test.assert_schema"},
    "test.assert_response":  {
        "required": [],
        "optional": ["status", "body", "contains", "schema", "headers"],
    },
    "assert response": {"alias_of": "test.assert_response"},

    # eval.*
    "eval.exec": {"required": ["code"], "optional": ["store_as"]},
    "eval.run":  {"required": ["expression"], "optional": ["store_as", "code"]},
    "eval.set":  {"required": ["key"], "optional": ["value"]},
    "eval.get":  {"required": ["key"], "optional": ["store_as"]},
    "eval.clear": {"required": [], "optional": []},
    "eval.extract_version": {
        "required": [],
        "optional": [
            "from", "url", "source", "from_var", "list_var", "index",
            "pattern", "store_as", "run_name", "append_to_run_name",
        ],
    },

    # telnet.*
    "telnet.send": {
        "required": ["command"],
        "optional": ["host", "port", "username", "password", "prompt", "timeout", "store_as"],
    },

    # websocket.* / ws.*  (params mirror websocket_service._WEBSOCKET_CONTROL_PARAMS;
    # connections are pooled by url, so url is required on send/receive too)
    "websocket.connect":    {"required": ["url"], "optional": [
        "timeout", "headers", "subprotocols", "protocol", "verify_ssl", "session_token",
        "auth_url", "auth_username", "auth_password", "auth_body_key", "auth_token_var",
    ]},
    "ws.connect":           {"alias_of": "websocket.connect"},
    "websocket.disconnect": {"required": [], "optional": ["url"]},
    "ws.disconnect":        {"alias_of": "websocket.disconnect"},
    "websocket.send":       {"required": ["url"], "optional": [
        "data", "method", "timeout", "wait_for", "store_as", "headers",
        "subprotocols", "protocol", "verify_ssl", "session_token",
        "auth_url", "auth_username", "auth_password", "auth_body_key", "auth_token_var",
    ]},
    "ws.send":              {"alias_of": "websocket.send"},
    "websocket.receive":    {"required": ["url"], "optional": [
        "timeout", "wait_for", "store_as", "headers", "subprotocols", "protocol",
        "verify_ssl", "session_token",
        "auth_url", "auth_username", "auth_password", "auth_body_key", "auth_token_var",
    ]},
    "ws.receive":           {"alias_of": "websocket.receive"},
    "websocket.read":       {"alias_of": "websocket.receive"},
    "ws.read":              {"alias_of": "websocket.receive"},

    # browser.*
    "browser.open":         {"required": ["url"], "optional": []},
    "open browser":         {"alias_of": "browser.open"},
    "browser.click":        {"required": [], "optional": ["selector", "text", "button", "role", "name", "label"]},
    "click element":        {"alias_of": "browser.click"},
    "browser.fill":         {"required": [], "optional": [
        "selector", "field", "value", "role", "name", "label", "clear",
    ]},
    "fill form field":      {"alias_of": "browser.fill"},
    "fill field":           {"alias_of": "browser.fill"},

    # browser assertion family (dispatched dynamically in runner via the
    # browser service — see runner.py "TEST ASSERTIONS" block)
    "browser.assert_checked":         {"required": ["selector"], "optional": ["timeout"]},
    "test.assert_checked":            {"alias_of": "browser.assert_checked"},
    "browser.assert_unchecked":       {"required": ["selector"], "optional": ["timeout"]},
    "test.assert_unchecked":          {"alias_of": "browser.assert_unchecked"},
    "test.assert_text_contains":      {"required": ["selector", "text"], "optional": ["timeout"]},
    "test.assert_text_equals":        {"required": ["selector", "text"], "optional": ["timeout"]},
    "test.assert_element_visible":    {"required": ["selector"], "optional": ["timeout"]},
    "test.assert_element_not_visible": {"required": ["selector"], "optional": ["timeout"]},
    "test.assert_element_enabled":    {"required": ["selector"], "optional": ["timeout"]},
    "test.assert_element_disabled":   {"required": ["selector"], "optional": ["timeout"]},
    "test.assert_element_count":      {"required": ["selector", "count"], "optional": ["timeout"]},
    "browser.screenshot":   {"required": [], "optional": ["filename", "path"]},
    "take screenshot":      {"alias_of": "browser.screenshot"},
    "browser.wait":         {"required": [], "optional": ["selector", "timeout"]},
    "browser.wait_for":     {"required": [], "optional": ["selector", "timeout", "state"]},
    "wait for element":     {"alias_of": "browser.wait_for"},
    "browser.verify_text":  {"required": ["text"], "optional": ["selector"]},
    "verify text":          {"alias_of": "browser.verify_text"},
    "browser.verify_element": {"required": ["selector"], "optional": []},
    "verify element":       {"alias_of": "browser.verify_element"},
    "browser.select":       {"required": ["selector"], "optional": ["value", "label", "index"]},
    "select option":        {"alias_of": "browser.select"},
    "browser.hover":        {"required": ["selector"], "optional": []},
    "hover element":        {"alias_of": "browser.hover"},
    "browser.press_key":    {"required": ["key"], "optional": ["selector"]},
    "press key":            {"alias_of": "browser.press_key"},
    "browser.refresh":      {"required": [], "optional": []},
    "refresh browser":      {"alias_of": "browser.refresh"},
    "browser.back":         {"required": [], "optional": []},
    "navigate back":        {"alias_of": "browser.back"},
    "browser.forward":      {"required": [], "optional": []},
    "navigate forward":     {"alias_of": "browser.forward"},
    "browser.double_click": {"required": [], "optional": ["selector", "text"]},
    "double click element": {"alias_of": "browser.double_click"},
    "browser.upload":       {"required": ["selector", "file"], "optional": []},
    "upload file":          {"alias_of": "browser.upload"},

    # aws.*
    "aws.list_files": {
        "required": ["bucket_name"],
        "optional": ["folder_prefix", "filename_pattern", "store_as"],
    },
    "aws list firmware files": {"alias_of": "aws.list_files"},
    "s3.list":                 {"alias_of": "aws.list_files"},
    "aws.get_latest": {"required": [], "optional": ["store_as"]},
    "aws get latest firmware": {"alias_of": "aws.get_latest"},
    "aws.upload": {
        "required": ["bucket_name", "file_path"],
        "optional": ["key", "store_as"],
    },
    "aws.delete_folder": {
        "required": ["bucket_name"],
        "optional": ["folder_prefix"],
    },

    # jsonrpc.* / ovrc.*
    "jsonrpc.connect":        {"required": ["url"], "optional": ["device_id", "timeout"]},
    "ovrc.connect":           {"alias_of": "jsonrpc.connect"},
    "jsonrpc connect":        {"alias_of": "jsonrpc.connect"},
    "ovrc connect":           {"alias_of": "jsonrpc.connect"},
    "jsonrpc.disconnect":     {"required": [], "optional": []},
    "ovrc.disconnect":        {"alias_of": "jsonrpc.disconnect"},
    "jsonrpc disconnect":     {"alias_of": "jsonrpc.disconnect"},
    "ovrc disconnect":        {"alias_of": "jsonrpc.disconnect"},
    "jsonrpc.get_about":      {"required": [], "optional": ["store_as"]},
    "ovrc.get_about":         {"alias_of": "jsonrpc.get_about"},
    "ovrc.get about":         {"alias_of": "jsonrpc.get_about"},
    "jsonrpc get about":      {"alias_of": "jsonrpc.get_about"},
    "ovrc get about":         {"alias_of": "jsonrpc.get_about"},
    "jsonrpc.start_updates":      {"required": [], "optional": ["interval"]},
    "ovrc.start_device_updates":  {"alias_of": "jsonrpc.start_updates"},
    "ovrc.start device updates":  {"alias_of": "jsonrpc.start_updates"},
    "jsonrpc start device updates": {"alias_of": "jsonrpc.start_updates"},
    "ovrc start device updates":  {"alias_of": "jsonrpc.start_updates"},
    "jsonrpc.stop_updates":       {"required": [], "optional": []},
    "ovrc.stop_device_updates":   {"alias_of": "jsonrpc.stop_updates"},
    "ovrc.stop device updates":   {"alias_of": "jsonrpc.stop_updates"},
    "jsonrpc.reset_device":       {"required": [], "optional": []},
    "ovrc.reset_device":          {"alias_of": "jsonrpc.reset_device"},
    "jsonrpc.get_network_settings": {"required": [], "optional": ["store_as"]},
    "ovrc.get_network_settings":    {"alias_of": "jsonrpc.get_network_settings"},
    "ovrc.get network settings":    {"alias_of": "jsonrpc.get_network_settings"},
    "jsonrpc.get_time_settings":  {"required": [], "optional": ["store_as"]},
    "ovrc.get_time_settings":     {"alias_of": "jsonrpc.get_time_settings"},
    "ovrc.get time settings":     {"alias_of": "jsonrpc.get_time_settings"},
    "jsonrpc.send":   {"required": [], "optional": [_P_ANY]},
    "ovrc.send":      {"alias_of": "jsonrpc.send"},
    "ovrc.call":      {"alias_of": "jsonrpc.send"},

    # serial.*
    "serial.send": {
        "required": ["command"],
        "optional": ["port", "baud_rate", "prompt", "timeout", "store_as"],
    },

    # pagerduty.* / pd.*
    "pagerduty.trigger": {
        "required": ["description"],
        "optional": ["severity", "source", "component", "group", "class_type", "details"],
    },
    "pd.trigger":       {"alias_of": "pagerduty.trigger"},
    "pagerduty.resolve":  {"required": [], "optional": ["dedup_key"]},
    "pd.resolve":         {"alias_of": "pagerduty.resolve"},
    "pagerduty.acknowledge": {"required": [], "optional": ["dedup_key"]},
    "pd.acknowledge":     {"alias_of": "pagerduty.acknowledge"},

    # ssh.* (stateful Paramiko sessions — preferred over command.ssh for device work)
    "ssh.connect":    {
        "required": ["host", "username"],
        "optional": ["password", "key_filename", "passphrase", "port", "timeout", "look_for_keys", "allow_agent"],
    },
    "ssh.command":    {
        "required": ["host", "command"],
        "optional": ["username", "password", "key_filename", "port", "timeout", "prompt", "use_shell", "store_as"],
    },
    "ssh.disconnect": {"required": ["host"], "optional": ["port"]},

    # command.*
    "command.ssh":    {
        "required": ["command"],
        "optional": ["host", "username", "password", "key_file", "port", "store_as"],
    },
    "command.shell":  {"required": ["command"], "optional": ["cwd", "env", "store_as", "timeout"]},
    "command.bash":   {"alias_of": "command.shell"},
    "command.sh":     {"alias_of": "command.shell"},
    "command.python": {"required": ["script"], "optional": ["store_as", "cwd"]},
}

# Keys that are structural (not action names) in a step mapping
_STRUCTURAL_KEYS: FrozenSet[str] = frozenset([
    "action", "shared_step", "for_each", "while", "try", "if", "condition",
    "then", "else", "loop_var", "steps", "except", "finally", "limit",
    "break_if", "continue_if", "retry", "description",
    # these appear as siblings when eval.exec params are mis-indented
    "code", "store_as", "expression", "message", "seconds", "url", "host",
    "command", "key", "value", "data", "timeout", "port", "schema",
])

# Known action namespace prefixes
_KNOWN_PREFIXES: FrozenSet[str] = frozenset([
    "test", "eval", "browser", "api", "aws", "s3",
    "jsonrpc", "ovrc", "websocket", "ws", "telnet",
    "serial", "pagerduty", "pd", "command",
])

_VAR_REF_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_schema(action: str) -> Optional[Dict]:
    """Return schema for action, following aliases. None if completely unknown."""
    key = action.lower().strip()
    schema = ACTION_SCHEMA.get(key)
    if schema is None:
        return None
    if "alias_of" in schema:
        return ACTION_SCHEMA.get(schema["alias_of"])
    return schema


def _is_deprecated_alias(action: str) -> Optional[str]:
    """Return the canonical dot-notation name if action is a deprecated space-separated alias, else None."""
    key = action.lower().strip()
    schema = ACTION_SCHEMA.get(key)
    if schema and "alias_of" in schema and "." not in key:
        return schema["alias_of"]
    return None


def _collect_var_refs(value: Any) -> Set[str]:
    """Recursively collect all ${var} references from any nested value."""
    refs: Set[str] = set()
    if isinstance(value, str):
        refs.update(_VAR_REF_RE.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            refs.update(_collect_var_refs(v))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_var_refs(item))
    return refs


# ---------------------------------------------------------------------------
# Main validator class
# ---------------------------------------------------------------------------


class EasyBDDValidator:
    """
    Validates Easy BDD test files and step snippets.

    Usage:
        v = EasyBDDValidator()
        issues = v.validate_file(Path("tests/cases/my_test.yaml"))
        issues = v.validate_snippet("- test.assert:\\n    expression: x == 1")
        print(v.format_report(issues))
    """

    def __init__(self) -> None:
        self._shared_steps: Set[str] = set()
        self._shared_steps_loaded: bool = False

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def validate_file(
        self, path: Path, shared_steps_dir: Optional[Path] = None
    ) -> List[Issue]:
        """Validate a full test YAML file."""
        issues: List[Issue] = []
        # Load shared steps from CWD, the file's directory, and any explicit dir
        candidates = [
            Path("shared_steps.yaml"),
            path.parent / "shared_steps.yaml",
        ]
        if shared_steps_dir:
            candidates.append(shared_steps_dir / "shared_steps.yaml")
        self._load_shared_steps(candidates=candidates)
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as e:
            return [Issue("ERROR", str(path), f"Cannot read file: {e}",
                          "File is unreadable or does not exist.")]
        return self._validate_text(raw, context=str(path), issues=issues)

    def validate_snippet(
        self,
        yaml_text: str,
        shared_steps_dir: Optional[Path] = None,
    ) -> List[Issue]:
        """Validate a raw YAML string — full test doc or a bare step list."""
        self._load_shared_steps(candidates=[
            Path("shared_steps.yaml"),
            *(
                [shared_steps_dir / "shared_steps.yaml"]
                if shared_steps_dir else []
            ),
        ])
        return self._validate_text(yaml_text, context="<snippet>", issues=[])

    def validate_testrail_cases(
        self,
        cases: List[Dict[str, Any]],
        shared_steps_from_tr: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Validate a list of TestRail case dicts (as returned by get_cases/get_tests).

        Imports helper functions from testrail_runner to reuse the same HTML
        stripping, YAML fixup, and body-extraction logic the runner uses.

        Step content is read only from: custom_preconds, custom_steps,
        custom_steps_separated.  The Summary field (custom_summary) is never
        read and has no bearing on validation or test execution.

        Returns a dict:
          {case_id: {"title": str, "role": str, "issues": List[Issue]}}
        """
        from .testrail_runner import (
            _classify, _strip_prefix,
            _html_to_text, _fix_step_list_indent, _yaml_safe_load_lenient,
            _extract_inline_data, _parse_structured_steps, _parse_inline_body,
            _parse_preconds_vars,
        )

        # Merge any shared-step names fetched from TestRail (Shared: cases)
        if shared_steps_from_tr:
            self._shared_steps.update(shared_steps_from_tr)
            self._shared_steps_loaded = True
        self._load_shared_steps([Path("shared_steps.yaml")])

        results: Dict[str, Any] = {}

        for case in cases:
            case_id = case.get("id") or case.get("case_id") or "?"
            title = case.get("title", "") or case.get("name", "")
            role = _classify(title)
            clean_title = _strip_prefix(title)
            ctx = f"TR-{case_id} [{clean_title}]"

            if role == "var":
                # Variable cases: validate that it parses as key: value pairs
                issues: List[Issue] = []
                text = _html_to_text(case.get("custom_preconds") or "")
                if text:
                    try:
                        parsed = yaml.safe_load(text)
                        if parsed is not None and not isinstance(parsed, dict):
                            issues.append(Issue(
                                "ERROR", ctx,
                                "Var: body must be a YAML mapping of key: value pairs",
                                f"Got {type(parsed).__name__} instead of a dict.",
                                "Format as 'key: value' pairs, one per line.",
                            ))
                    except yaml.YAMLError as e:
                        issues.append(Issue(
                            "ERROR", ctx,
                            f"Var: body YAML parse error: {getattr(e, 'problem', str(e))}",
                            "The variable definitions could not be parsed as YAML.",
                            "Check for invalid YAML syntax in the Preconditions field.",
                        ))
                results[str(case_id)] = {"title": clean_title, "role": role, "issues": issues}
                continue

            if role == "test":
                # Test: cases point to a local file via tag: or file: — validate pointer format
                issues = []
                body = _html_to_text(
                    case.get("custom_preconds") or case.get("custom_steps") or ""
                )
                if body:
                    lines = {
                        ln.split(":", 1)[0].strip(): ln.split(":", 1)[1].strip()
                        for ln in body.splitlines()
                        if ":" in ln
                    }
                    if "tag" not in lines and "file" not in lines:
                        issues.append(Issue(
                            "WARNING", ctx,
                            "Test: body doesn't specify 'tag:' or 'file:' pointer",
                            "A Test: case should have either 'tag: <tag>' to match local YAML "
                            "tests by tag, or 'file: <path>' to point to a specific YAML file.",
                            "Add 'tag: my_tag' or 'file: tests/cases/my_test.yaml' "
                            "to the Preconditions field.",
                        ))
                results[str(case_id)] = {"title": clean_title, "role": role, "issues": issues}
                continue

            if role == "unknown":
                results[str(case_id)] = {
                    "title": clean_title, "role": role,
                    "issues": [Issue(
                        "WARNING", ctx,
                        f"Unrecognised case prefix in title: '{title[:40]}'",
                        "Case title must start with one of: "
                        "Feature:, Shared:, Test:, Var:, Setup:, Teardown:.",
                        "Add the appropriate prefix to the case title.",
                    )],
                }
                continue

            # For Feature:, Shared:, Setup:, Teardown: — extract and validate steps
            issues = []
            steps_text: Optional[str] = None
            steps_list: Optional[List] = None
            variables: Dict[str, Any] = {}

            preconds_text = _html_to_text(case.get("custom_preconds") or "")
            if preconds_text:
                _, preconds_clean = _extract_inline_data(preconds_text)
                fixed = _fix_step_list_indent(preconds_clean)
                try:
                    parsed = _yaml_safe_load_lenient(fixed)
                    if isinstance(parsed, list):
                        steps_list = [s for s in parsed if isinstance(s, dict)]
                    elif isinstance(parsed, dict) and "steps" in parsed:
                        steps_list = [s for s in (parsed.get("steps") or []) if isinstance(s, dict)]
                        variables = {
                            str(k).lstrip("$"): v
                            for k, v in (parsed.get("variables") or {}).items()
                        }
                    elif isinstance(parsed, dict):
                        steps_list = [parsed]
                    else:
                        steps_text = fixed  # could not parse as steps — treat as raw text
                except yaml.YAMLError as exc:
                    issues.append(Issue(
                        "ERROR", ctx,
                        f"YAML parse error in Preconditions: {getattr(exc, 'problem', str(exc))}",
                        "The Preconditions field contains invalid YAML.",
                        "Check indentation and quoting in TestRail's Preconditions field.",
                    ))
                    results[str(case_id)] = {"title": clean_title, "role": role, "issues": issues}
                    continue

            if not steps_list:
                structured = case.get("custom_steps_separated") or []
                has_structured = isinstance(structured, list) and any(
                    isinstance(r, dict) and (r.get("content") or r.get("expected"))
                    for r in structured
                )
                if has_structured:
                    steps_list = _parse_structured_steps(case)
                else:
                    raw_steps = case.get("custom_steps")
                    if isinstance(raw_steps, list) and any(
                        isinstance(r, dict) and (r.get("content") or r.get("expected"))
                        for r in raw_steps
                    ):
                        steps_list = _parse_structured_steps({"custom_steps_separated": raw_steps})
                    elif raw_steps:
                        steps_list = _parse_inline_body(str(raw_steps))
                if not variables:
                    variables = _parse_preconds_vars(case)

            if not steps_list and steps_text is None:
                issues.append(Issue(
                    "WARNING", ctx,
                    "No steps found in case body",
                    "The case has no parseable steps in Preconditions, Steps, or "
                    "Steps (Separated) fields.",
                    "Add steps to the Preconditions field in YAML format.",
                ))
                results[str(case_id)] = {"title": clean_title, "role": role, "issues": issues}
                continue

            corrected_yaml: Optional[str] = None
            if steps_list is not None:
                # Validate the steps and collect issues with per-step corrections
                try:
                    reconstructed = yaml.dump(
                        steps_list, default_flow_style=False, allow_unicode=True
                    )
                    step_issues = self._validate_text(reconstructed, context=ctx, issues=[])
                    issues.extend(step_issues)

                    # Build a corrected steps list by applying per-step corrections.
                    # Each correctable issue has a 'correction' field containing the
                    # fixed step as a YAML string.  Map them back by step index.
                    corrections_by_idx: Dict[int, Any] = {}
                    for iss in step_issues:
                        if not iss.correction:
                            continue
                        # Location is like "steps[N]" or "steps[N].sub"
                        m = re.search(r"steps\[(\d+)\]", iss.location)
                        if m:
                            idx = int(m.group(1))
                            try:
                                parsed_correction = yaml.safe_load(iss.correction)
                                if isinstance(parsed_correction, list) and parsed_correction:
                                    corrections_by_idx[idx] = parsed_correction[0]
                                elif isinstance(parsed_correction, dict):
                                    corrections_by_idx[idx] = parsed_correction
                            except Exception:
                                pass

                    corrected_steps = [
                        corrections_by_idx.get(i, step)
                        for i, step in enumerate(steps_list)
                    ]
                    corrected_yaml = yaml.dump(
                        corrected_steps, default_flow_style=False, allow_unicode=True
                    )
                except Exception as exc:
                    issues.append(Issue(
                        "ERROR", ctx,
                        f"Could not re-validate parsed steps: {exc}",
                        "Steps were parsed but could not be serialised back for validation.",
                    ))

            # Surface corrected_yaml only when it differs from the original input
            original_stripped = (preconds_text or "").strip()
            corrected_stripped = (corrected_yaml or "").strip()
            show_correction = bool(
                corrected_yaml
                and original_stripped
                and original_stripped != corrected_stripped
            )

            results[str(case_id)] = {
                "title": clean_title,
                "role": role,
                "issues": issues,
                "corrected_yaml": corrected_yaml if show_correction else None,
            }

        return results

    @staticmethod
    def format_testrail_report(results: Dict[str, Any]) -> Tuple[str, int, int]:
        """Format the result of validate_testrail_cases into a printable report.

        Returns (report_string, total_errors, total_warnings).
        """
        lines: List[str] = []
        total_errors = 0
        total_warnings = 0

        role_order = {"inline": 0, "keyword": 1, "setup": 2, "teardown": 3,
                      "test": 4, "var": 5, "unknown": 6}
        sorted_items = sorted(
            results.items(),
            key=lambda kv: (role_order.get(kv[1].get("role", "unknown"), 99), kv[0]),
        )

        for case_id, info in sorted_items:
            title = info.get("title", "")
            role = info.get("role", "?")
            issues: List[Issue] = info.get("issues", [])
            corrected_yaml: Optional[str] = info.get("corrected_yaml")
            errors = [i for i in issues if i.severity == "ERROR"]
            warnings = [i for i in issues if i.severity == "WARNING"]
            total_errors += len(errors)
            total_warnings += len(warnings)

            role_label = {
                "inline": "Feature", "keyword": "Shared",
                "setup": "Setup", "teardown": "Teardown",
                "test": "Test", "var": "Var", "unknown": "Unknown",
            }.get(role, role)

            if issues:
                status = "❌" if errors else "⚠️ "
                lines.append(f"{status} [{role_label}] C{case_id}: {title}")
                lines.append(EasyBDDValidator.format_report(issues))

                # Show corrected Preconditions block when auto-fixable differences were found
                if corrected_yaml:
                    lines.append("")
                    lines.append(
                        "  ── Suggested Preconditions (paste this into TestRail) ──────────"
                    )
                    for ln in corrected_yaml.rstrip().splitlines():
                        lines.append(f"  {ln}")
                    lines.append(
                        "  ─────────────────────────────────────────────────────────────────"
                    )
            else:
                lines.append(f"  ✅ [{role_label}] C{case_id}: {title}")

        return "\n".join(lines), total_errors, total_warnings

    # ------------------------------------------------------------------
    # Shared step loading
    # ------------------------------------------------------------------

    def _load_shared_steps(self, candidates: List[Path]) -> None:
        for p in candidates:
            if p and p.exists():
                try:
                    data = yaml.safe_load(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._shared_steps.update(data.keys())
                        self._shared_steps_loaded = True
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Core YAML parsing and dispatch
    # ------------------------------------------------------------------

    def _validate_text(self, text: str, context: str, issues: List[Issue]) -> List[Issue]:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            problem = getattr(exc, "problem", str(exc))
            mark = getattr(exc, "problem_mark", None)
            loc = f"{context}:line {mark.line + 1}" if mark else context
            issues.append(Issue(
                "ERROR", loc,
                f"YAML parse error: {problem}",
                "The YAML is syntactically invalid and cannot be parsed.",
                "Check indentation — YAML uses consistent spaces (2 or 4). "
                "Nested parameters under an action key must be indented further than the key.",
            ))
            return issues

        if data is None:
            issues.append(Issue("ERROR", context, "Empty document",
                                "The YAML file or snippet is empty."))
            return issues

        if isinstance(data, list):
            # Bare step list — validate as steps
            self._validate_steps(data, "steps", set(), set(), issues)
        elif isinstance(data, dict):
            self._validate_test_doc(data, context, issues)
        else:
            issues.append(Issue(
                "ERROR", context,
                f"Unexpected top-level type: {type(data).__name__}",
                "A test file must be a YAML mapping (dict) or a sequence (list) of steps.",
            ))
        return issues

    # ------------------------------------------------------------------
    # Full test document
    # ------------------------------------------------------------------

    def _validate_test_doc(self, data: dict, ctx: str, issues: List[Issue]) -> None:
        if "name" not in data:
            issues.append(Issue(
                "ERROR", ctx, "Missing required field 'name'",
                "Every test file must have a 'name' field to identify it.",
                "Add 'name: My Test Name' at the top level.",
            ))
        elif not (isinstance(data["name"], str) and data["name"].strip()):
            issues.append(Issue("ERROR", f"{ctx}.name", "'name' must be a non-empty string",
                                "The test name cannot be blank."))

        if "steps" not in data:
            issues.append(Issue(
                "ERROR", ctx, "Missing required field 'steps'",
                "Every test must define at least one step.",
                "Add a 'steps:' section.",
            ))

        # Collect declared variables
        known_vars: Set[str] = set()
        if "variables" in data:
            if isinstance(data["variables"], dict):
                known_vars.update(data["variables"].keys())
            else:
                issues.append(Issue(
                    "ERROR", f"{ctx}.variables", "'variables' must be a mapping",
                    "Variables must be key-value pairs, not a list or scalar.",
                    "Use 'variables:\\n  key: value' format.",
                ))

        # Validate step sections
        for section in ("setup", "steps", "cleanup"):
            if section not in data:
                continue
            steps = data[section]
            if not isinstance(steps, list):
                issues.append(Issue(
                    "ERROR", f"{ctx}.{section}", f"'{section}' must be a list",
                    "Step sections must be YAML sequences.",
                    f"Each step under '{section}' should start with '- '.",
                ))
            else:
                self._validate_steps(steps, section, known_vars.copy(), set(), issues)

        # Warn about unknown top-level keys
        _valid_doc_keys = {
            "name", "description", "tags", "variables", "setup", "steps", "cleanup",
            "data_source", "data", "async_execution", "max_workers", "device_config",
            "browsers", "record_video",
        }
        for key in data:
            if key not in _valid_doc_keys:
                issues.append(Issue(
                    "WARNING", f"{ctx}.{key}",
                    f"Unrecognised top-level field '{key}'",
                    "This key is not a known test document field and will be ignored by the runner.",
                    f"Valid fields: {', '.join(sorted(_valid_doc_keys))}",
                ))

    # ------------------------------------------------------------------
    # Step list and individual steps
    # ------------------------------------------------------------------

    def _validate_steps(
        self,
        steps: list,
        path: str,
        known_vars: Set[str],
        loop_vars: Set[str],
        issues: List[Issue],
    ) -> None:
        if not isinstance(steps, list):
            issues.append(Issue("ERROR", path, "Steps must be a list",
                                "A steps block must be a YAML sequence."))
            return
        for idx, step in enumerate(steps):
            self._validate_step(step, f"{path}[{idx}]", known_vars, loop_vars, issues)

    def _validate_step(
        self,
        step: Any,
        path: str,
        known_vars: Set[str],
        loop_vars: Set[str],
        issues: List[Issue],
    ) -> None:
        if not isinstance(step, dict):
            issues.append(Issue(
                "ERROR", path,
                f"Step must be a mapping, got '{type(step).__name__}'",
                "Each step must be a YAML mapping with an action key.",
                "Use '- action_name:\\n    param: value' or '- shared_step: Name'.",
            ))
            return

        avail = known_vars | loop_vars

        if "shared_step" in step:
            self._check_shared_step(step, path, avail, issues)
        elif "for_each" in step:
            self._check_for_each(step, path, known_vars, loop_vars, issues)
        elif "while" in step:
            self._check_while(step, path, known_vars, loop_vars, issues)
        elif "try" in step:
            self._check_try(step, path, known_vars, loop_vars, issues)
        elif "if" in step or "condition" in step:
            self._check_conditional(step, path, known_vars, loop_vars, issues)
        else:
            self._check_action(step, path, avail, issues)

    # ------------------------------------------------------------------
    # shared_step
    # ------------------------------------------------------------------

    def _check_shared_step(
        self, step: dict, path: str, avail: Set[str], issues: List[Issue]
    ) -> None:
        name = step.get("shared_step")
        if not isinstance(name, str) or not name.strip():
            issues.append(Issue(
                "ERROR", path, "shared_step name must be a non-empty string",
                "The shared_step key expects the step name as its string value.",
                "Example: '- shared_step: Get_Firmware_Version'",
            ))
            return

        if self._shared_steps_loaded:
            if name not in self._shared_steps:
                lower_map = {k.lower(): k for k in self._shared_steps}
                if name.lower() in lower_map:
                    canonical = lower_map[name.lower()]
                    corrected = yaml.dump(
                        [{"shared_step": canonical}], default_flow_style=False
                    ).strip()
                    issues.append(Issue(
                        "ERROR", path,
                        f"Shared step '{name}' not found — case mismatch",
                        f"Shared step lookup is case-sensitive. "
                        f"Found '{canonical}' in shared_steps.yaml but you referenced '{name}'.",
                        f"Change '{name}' to '{canonical}'.",
                        correction=corrected,
                    ))
                else:
                    available = sorted(self._shared_steps)
                    preview = ", ".join(available[:8])
                    if len(available) > 8:
                        preview += f" … ({len(available)} total)"
                    issues.append(Issue(
                        "ERROR", path,
                        f"Shared step '{name}' not found in shared_steps.yaml",
                        f"No shared step named '{name}' is defined.",
                        f"Available steps: {preview}",
                    ))
        else:
            issues.append(Issue(
                "WARNING", path,
                f"Cannot verify shared step '{name}' — no shared_steps.yaml found",
                "Run validation from the test's working directory, "
                "or pass --shared-steps-dir to locate shared_steps.yaml.",
            ))

        extra = set(step.keys()) - {"shared_step", "parameters"}
        if extra:
            issues.append(Issue(
                "WARNING", path,
                f"Unexpected keys in shared_step reference: {', '.join(sorted(extra))}",
                "Only 'shared_step' and 'parameters' are valid here.",
                "Remove extra keys or nest them under 'parameters:'.",
            ))

    # ------------------------------------------------------------------
    # for_each
    # ------------------------------------------------------------------

    def _check_for_each(
        self,
        step: dict,
        path: str,
        known_vars: Set[str],
        loop_vars: Set[str],
        issues: List[Issue],
    ) -> None:
        items = step.get("for_each")

        if items is None:
            issues.append(Issue(
                "ERROR", f"{path}.for_each",
                "for_each value is null — possible YAML indentation error",
                "The list following 'for_each:' must be indented under it, "
                "not at the same level.",
                "Example:\n"
                "    - for_each:\n"
                "        - 1\n"
                "        - 10\n"
                "      loop_var: my_var\n"
                "      steps: ...",
            ))

        loop_var = step.get("loop_var", "item")
        if loop_var == "item":
            issues.append(Issue(
                "WARNING", path,
                "for_each missing 'loop_var' — defaulting to 'item'",
                "Without loop_var the iteration variable is named 'item', "
                "which may conflict with other variables.",
                "Add 'loop_var: descriptive_name' alongside for_each.",
            ))
        elif not isinstance(loop_var, str) or not loop_var.strip():
            issues.append(Issue("ERROR", f"{path}.loop_var", "loop_var must be a non-empty string",
                                "The loop variable name must be a valid identifier."))

        if "steps" not in step:
            issues.append(Issue(
                "ERROR", path,
                "for_each missing 'steps' block",
                "A for_each loop requires a 'steps:' key containing the loop body.",
                "Add 'steps:\\n  - <step>' at the same indentation as 'for_each:'.",
            ))
        elif not isinstance(step["steps"], list):
            issues.append(Issue(
                "ERROR", f"{path}.steps", "'steps' must be a YAML sequence",
                "The steps block must start with '- ' list markers.",
            ))
        elif not step["steps"]:
            issues.append(Issue("WARNING", f"{path}.steps", "for_each body is empty",
                                "An empty loop body does nothing."))
        else:
            new_loop_vars = loop_vars | {str(loop_var)}
            self._validate_steps(
                step["steps"], f"{path}.steps", known_vars, new_loop_vars, issues
            )

        valid_keys = {"for_each", "loop_var", "steps", "limit", "break_if", "continue_if", "description"}
        for key in step:
            if key not in valid_keys:
                issues.append(Issue(
                    "WARNING", f"{path}.{key}",
                    f"Unrecognised key '{key}' in for_each block",
                    f"Valid for_each keys: {', '.join(sorted(valid_keys))}",
                    "If this is a step parameter, move it inside the 'steps:' list.",
                ))

    # ------------------------------------------------------------------
    # while
    # ------------------------------------------------------------------

    def _check_while(
        self,
        step: dict,
        path: str,
        known_vars: Set[str],
        loop_vars: Set[str],
        issues: List[Issue],
    ) -> None:
        condition = step.get("while")
        if not condition:
            issues.append(Issue(
                "ERROR", path,
                "while requires a condition expression",
                "The 'while' key expects a Python expression as its value.",
                "Example: '- while: retry_count < 5'",
            ))
        if "steps" not in step:
            issues.append(Issue(
                "ERROR", path, "while loop missing 'steps' block",
                "A while loop requires a 'steps:' block.",
                "Add 'steps:\\n  - <step>' inside the while block.",
            ))
        elif isinstance(step.get("steps"), list):
            self._validate_steps(step["steps"], f"{path}.steps", known_vars, loop_vars, issues)

    # ------------------------------------------------------------------
    # try/except/finally
    # ------------------------------------------------------------------

    def _check_try(
        self,
        step: dict,
        path: str,
        known_vars: Set[str],
        loop_vars: Set[str],
        issues: List[Issue],
    ) -> None:
        try_block = step.get("try")
        if not isinstance(try_block, list):
            issues.append(Issue(
                "ERROR", f"{path}.try", "try block must be a list of steps",
                "The 'try' key expects a YAML sequence.",
                "Example:\n    try:\n      - test.assert:\n          expression: ...",
            ))
        else:
            self._validate_steps(try_block, f"{path}.try", known_vars, loop_vars, issues)

        for clause in ("except", "finally"):
            if clause in step:
                block = step[clause]
                if not isinstance(block, list):
                    issues.append(Issue(
                        "ERROR", f"{path}.{clause}", f"'{clause}' block must be a list of steps",
                        f"The '{clause}' key expects a YAML sequence.",
                    ))
                else:
                    self._validate_steps(block, f"{path}.{clause}", known_vars, loop_vars, issues)

    # ------------------------------------------------------------------
    # if/condition
    # ------------------------------------------------------------------

    def _check_conditional(
        self,
        step: dict,
        path: str,
        known_vars: Set[str],
        loop_vars: Set[str],
        issues: List[Issue],
    ) -> None:
        condition = step.get("condition") or step.get("if")
        if not condition:
            issues.append(Issue(
                "ERROR", path, "if/condition requires a non-empty expression",
                "The 'if' or 'condition' key expects a Python expression.",
                "Example: '- if: execute == True'",
            ))

        if "then" not in step and "then_steps" not in step:
            issues.append(Issue(
                "WARNING", path,
                "if/condition has no 'then' branch",
                "A conditional with no 'then' branch will never do anything.",
                "Add 'then:\\n  - <step>' to define what happens when the condition is True.",
            ))

        for branch in ("then", "then_steps", "else", "else_steps"):
            if branch in step:
                block = step[branch]
                if not isinstance(block, list):
                    issues.append(Issue(
                        "ERROR", f"{path}.{branch}", f"'{branch}' must be a list of steps",
                        "Branch steps must be a YAML sequence.",
                    ))
                else:
                    self._validate_steps(block, f"{path}.{branch}", known_vars, loop_vars, issues)

    # ------------------------------------------------------------------
    # Regular action steps
    # ------------------------------------------------------------------

    def _check_action(
        self, step: dict, path: str, avail: Set[str], issues: List[Issue]
    ) -> None:
        if "action" in step:
            # Old format: {action: "name", param1: v1, ...}
            action = step["action"]
            if not isinstance(action, str) or not action.strip():
                issues.append(Issue("ERROR", path, "'action' must be a non-empty string",
                                    "The action field identifies what operation to perform."))
                return
            params = {
                k: v for k, v in step.items()
                if k not in ("action", "condition", "if", "then", "else", "retry", "description")
            }
        else:
            # Dot-notation format: find the first key that is not a structural keyword
            action_key = next(
                (k for k in step if k not in _STRUCTURAL_KEYS),
                None,
            )
            if action_key is None:
                # All keys are structural — possibly a misindented block
                structural_present = [k for k in step if k in _STRUCTURAL_KEYS]
                issues.append(Issue(
                    "ERROR", path,
                    "Cannot identify action: no action key found",
                    f"Found only structural keys: {structural_present}. "
                    "This usually means the action key and its parameters are at wrong indentation.",
                    "Make sure the action key (e.g. 'eval.exec:') is at the step level "
                    "and its parameters are indented two more spaces under it.",
                ))
                return
            action = action_key
            raw_params = step[action_key]

            if raw_params is None:
                # Check if sibling keys look like parameters (common indentation mistake)
                siblings = {k: v for k, v in step.items()
                            if k != action_key and k not in ("retry", "description")}
                if siblings:
                    corrected = yaml.dump(
                        [{action: siblings}], default_flow_style=False
                    ).strip()
                    issues.append(Issue(
                        "ERROR", path,
                        f"Parameters for '{action}' are at the wrong indentation level",
                        f"The keys {list(siblings.keys())} appear as siblings of '{action}:' "
                        f"but should be nested under it with 2 extra spaces of indentation.",
                        f"Indent {list(siblings.keys())} under '{action}:' by 2 more spaces.",
                        correction=corrected,
                    ))
                    return
                params = {}
            elif isinstance(raw_params, dict):
                params = raw_params
            else:
                # Scalar shorthand — e.g. test.print: "hello"
                params = {"value": raw_params}

        # Deprecation check: warn before schema validation so the warning is always emitted.
        canonical = _is_deprecated_alias(action)
        if canonical:
            issues.append(Issue(
                "WARNING", path,
                f"'{action}' is a deprecated action name — use '{canonical}' instead",
                "Space-separated action names are deprecated. Dot-notation is the standard.",
                f"Replace '{action}:' with '{canonical}:'.",
            ))

        self._check_action_schema(action, params, path, avail, issues)

    def _check_action_schema(
        self,
        action: str,
        params: dict,
        path: str,
        avail: Set[str],
        issues: List[Issue],
    ) -> None:
        schema = _resolve_schema(action)
        action_lower = action.lower()

        if schema is None:
            prefix = action_lower.split(".")[0] if "." in action_lower else action_lower
            if prefix not in _KNOWN_PREFIXES:
                issues.append(Issue(
                    "WARNING", path,
                    f"Unknown action '{action}'",
                    f"The namespace '{prefix}' is not a known Easy BDD action prefix. "
                    "Custom/plugin actions are allowed but won't be parameter-validated.",
                    f"Known namespaces: {', '.join(sorted(_KNOWN_PREFIXES))}",
                ))
            else:
                # Known prefix but unrecognised action — list similar known actions
                similar = sorted(
                    k for k in ACTION_SCHEMA
                    if k.startswith(prefix + ".") and "alias_of" not in ACTION_SCHEMA[k]
                )[:8]
                issues.append(Issue(
                    "WARNING", path,
                    f"Unrecognised action '{action}'",
                    f"'{action}' is not in the known action list for namespace '{prefix}'.",
                    f"Did you mean one of: {', '.join(similar)}?" if similar else
                    "Check the action name for typos.",
                ))
        else:
            required = schema.get("required", [])
            optional = schema.get("optional", [])
            is_open = optional == [_P_ANY] or _P_ANY in (optional or [])

            for req in required:
                if req not in params:
                    issues.append(Issue(
                        "ERROR", path,
                        f"Missing required parameter '{req}'",
                        f"Action '{action}' requires the '{req}' parameter.",
                        f"Add '{req}: <value>' under '{action}:'.",
                    ))

            if not is_open:
                all_known = set(required) | set(optional)
                for param in params:
                    if all_known and param not in all_known:
                        issues.append(Issue(
                            "WARNING", path,
                            f"Unrecognised parameter '{param}' for action '{action}'",
                            f"'{param}' is not a documented parameter and may be silently ignored.",
                            f"Known parameters: {', '.join(sorted(all_known))}",
                        ))

        # Variable reference validation
        for ref in _collect_var_refs(params):
            base = ref.split(".")[0]  # handle gv.key, item.field etc.
            if avail and base not in avail:
                issues.append(Issue(
                    "WARNING", path,
                    f"Potentially undefined variable '${{{ref}}}'",
                    f"Variable '{base}' is not declared in 'variables:' or any active loop variable. "
                    "It may be set at runtime by a previous step, device config, or shared step.",
                    "Declare it in the test's 'variables:' section if it must exist before this step.",
                ))

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_report(issues: List[Issue]) -> str:
        if not issues:
            return "  No issues found. Looks good!"
        errors = [i for i in issues if i.severity == "ERROR"]
        warnings = [i for i in issues if i.severity == "WARNING"]
        lines = []
        if errors:
            lines.append(f"  ERRORS ({len(errors)}):")
            for i in errors:
                lines.append(str(i))
        if warnings:
            if errors:
                lines.append("")
            lines.append(f"  WARNINGS ({len(warnings)}):")
            for i in warnings:
                lines.append(str(i))
        lines.append("")
        lines.append(
            f"  Result: {len(errors)} error(s), {len(warnings)} warning(s)"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backward-compat shim (used by older code that imports ConfigValidator)
# ---------------------------------------------------------------------------


class ConfigValidator:
    """Thin wrapper around EasyBDDValidator for backward compatibility."""

    REQUIRED_TEST_FIELDS = {"name", "steps"}
    VALID_ACTION_PREFIXES = _KNOWN_PREFIXES
    DEPRECATED_ACTIONS = {
        "Open browser": "browser.open",
        "Click element": "browser.click",
        "Fill form field": "browser.fill",
        "Fill field": "browser.fill",
        "Upload file": "browser.upload",
        "Take screenshot": "browser.screenshot",
        "Assert": "test.assert",
        "AWS list firmware files": "aws.list_files",
        "AWS get latest firmware": "aws.get_latest",
        "JSONRPC connect": "jsonrpc.connect",
    }

    def __init__(self, strict_mode: bool = False) -> None:
        self.strict_mode = strict_mode

    def validate_test_file(
        self, file_path: Path, strict: bool = None
    ) -> Tuple[bool, List[str]]:
        v = EasyBDDValidator()
        issues = v.validate_file(file_path)
        strict_mode = strict if strict is not None else self.strict_mode
        errors = [i for i in issues if i.severity == "ERROR"]
        warnings = [i for i in issues if i.severity == "WARNING"]
        messages = (
            [f"ERROR: {i.location}: {i.message}" for i in errors]
            + [f"WARNING: {i.location}: {i.message}" for i in warnings]
        )
        is_valid = len(errors) == 0 and (not strict_mode or len(warnings) == 0)
        return is_valid, messages

    def validate_directory(self, directory: Path) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "total": 0, "valid": 0, "invalid": 0, "warnings": 0, "files": {}
        }
        for yaml_file in directory.glob("**/*.yaml"):
            if yaml_file.is_file():
                results["total"] += 1
                is_valid, messages = self.validate_test_file(yaml_file)
                err_count = sum(1 for m in messages if m.startswith("ERROR"))
                warn_count = sum(1 for m in messages if m.startswith("WARNING"))
                results["files"][str(yaml_file)] = {
                    "valid": is_valid, "errors": err_count,
                    "warnings": warn_count, "messages": messages,
                }
                if is_valid:
                    results["valid"] += 1
                else:
                    results["invalid"] += 1
                results["warnings"] += warn_count
        return results


def validate_test_file(file_path: str, strict: bool = False) -> bool:
    """Convenience function to validate a test file (prints results)."""
    v = EasyBDDValidator()
    issues = v.validate_file(Path(file_path))
    print(EasyBDDValidator.format_report(issues))
    errors = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARNING"]
    return len(errors) == 0 and (not strict or len(warnings) == 0)
