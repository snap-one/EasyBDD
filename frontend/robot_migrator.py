"""
Robot Framework → Easy BDD migrator.

Parses .robot files and converts them to Easy BDD YAML test files and
shared_steps.yaml entries, preserving variable syntax (${VAR} is the
same in both frameworks).

Supports:
  *** Settings ***   → suite-level setup/teardown + library hints
  *** Variables ***  → variables: block
  *** Keywords ***   → shared step definitions
  *** Test Cases ***  → individual YAML test files
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Keyword → Easy BDD action mapping
# ---------------------------------------------------------------------------

# Maps (case-insensitive) Robot keyword to Easy BDD action string.
# The value is either a plain string or a callable(args) -> dict.
_KEYWORD_MAP: Dict[str, Any] = {
    # BuiltIn
    "log":                    lambda args: {"action": "test.log", "params": {"message": args[0] if args else ""}},
    "log to console":         lambda args: {"action": "test.log", "params": {"message": args[0] if args else ""}},
    "should be equal":        lambda args: {"action": "test.assert", "params": {"expression": f"{args[0]} == {args[1]}" if len(args) >= 2 else args[0]}},
    "should be true":         lambda args: {"action": "test.assert", "params": {"expression": args[0] if args else "True"}},
    "should not be empty":    lambda args: {"action": "test.assert", "params": {"expression": f"{args[0]} != ''" if args else "True"}},
    "should contain":         lambda args: {"action": "test.assert", "params": {"expression": f'"{args[1]}" in str({args[0]})' if len(args) >= 2 else args[0]}},
    "sleep":                  lambda args: {"action": "browser.wait", "params": {"seconds": float(re.sub(r"[a-z]", "", args[0])) if args else 1}},
    "fail":                   lambda args: {"action": "test.assert", "params": {"expression": "False", "message": args[0] if args else "Force fail"}},
    "set variable":           lambda args: {"action": "eval.set", "params": {"key": "__result__", "value": args[0] if args else ""}},
    "run keyword if":         lambda args: {"action": "test.log", "params": {"message": f"[conditional] {' '.join(args)}"}},
    "run keyword":            lambda args: {"action": "test.log", "params": {"message": f"[keyword] {' '.join(args)}"}},
    # Browser / SeleniumLibrary / Browser library
    "open browser":           lambda args: {"action": "browser.open", "params": {"url": args[0] if args else ""}},
    "close browser":          lambda args: {"action": "browser.close", "params": {}},
    "go to":                  lambda args: {"action": "browser.open", "params": {"url": args[0] if args else ""}},
    "navigate to":            lambda args: {"action": "browser.open", "params": {"url": args[0] if args else ""}},
    "click element":          lambda args: {"action": "browser.click", "params": {"selector": args[0] if args else ""}},
    "click button":           lambda args: {"action": "browser.click", "params": {"selector": args[0] if args else ""}},
    "click link":             lambda args: {"action": "browser.click", "params": {"text": args[0] if args else ""}},
    "input text":             lambda args: {"action": "browser.fill", "params": {"selector": args[0] if args else "", "value": args[1] if len(args) > 1 else ""}},
    "fill text":              lambda args: {"action": "browser.fill", "params": {"selector": args[0] if args else "", "value": args[1] if len(args) > 1 else ""}},
    "type text":              lambda args: {"action": "browser.fill", "params": {"selector": args[0] if args else "", "value": args[1] if len(args) > 1 else ""}},
    "press keys":             lambda args: {"action": "browser.press_key", "params": {"selector": args[0] if args else "", "key": args[1] if len(args) > 1 else ""}},
    "press key":              lambda args: {"action": "browser.press_key", "params": {"key": args[0] if args else ""}},
    "capture page screenshot": lambda args: {"action": "browser.screenshot", "params": {"name": args[0] if args else "screenshot"}},
    "take screenshot":        lambda args: {"action": "browser.screenshot", "params": {"name": args[0] if args else "screenshot"}},
    "wait until element is visible": lambda args: {"action": "browser.wait_for", "params": {"selector": args[0] if args else "", "state": "visible"}},
    "wait until page contains": lambda args: {"action": "browser.wait_for_text", "params": {"text": args[0] if args else ""}},
    "element should be visible": lambda args: {"action": "test.assert_element_visible", "params": {"selector": args[0] if args else ""}},
    "page should contain":    lambda args: {"action": "test.assert_text_contains", "params": {"selector": "body", "text": args[0] if args else ""}},
    "get text":               lambda args: {"action": "browser.get_text", "params": {"selector": args[0] if args else "", "store_as": args[1] if len(args) > 1 else "text_result"}},
    # HTTP / RequestsLibrary
    "create session":         lambda args: {"action": "test.log", "params": {"message": f"[session] alias={args[0] if args else ''}"}},
    "get request":            lambda args: {"action": "api.request", "params": {"method": "GET", "url": args[1] if len(args) > 1 else args[0] if args else ""}},
    "post request":           lambda args: {"action": "api.request", "params": {"method": "POST", "url": args[1] if len(args) > 1 else args[0] if args else ""}},
    "put request":            lambda args: {"action": "api.request", "params": {"method": "PUT", "url": args[1] if len(args) > 1 else args[0] if args else ""}},
    "delete request":         lambda args: {"action": "api.request", "params": {"method": "DELETE", "url": args[1] if len(args) > 1 else args[0] if args else ""}},
    # OS / Process
    "run process":            lambda args: {"action": "command.shell", "params": {"command": " ".join(args)}},
    "run":                    lambda args: {"action": "command.shell", "params": {"command": args[0] if args else ""}},
    "execute command":        lambda args: {"action": "command.shell", "params": {"command": args[0] if args else ""}},
}


def _map_keyword(keyword: str, args: List[str]) -> Dict[str, Any]:
    """Convert a Robot keyword call to an Easy BDD step dict."""
    key = keyword.lower().strip()
    handler = _KEYWORD_MAP.get(key)
    if handler:
        result = handler(args)
        step = {"action": result["action"]}
        step.update(result["params"])
        return step
    # Unknown keyword → shared_step reference or test.log fallback
    # If the keyword looks like a user-defined one (Title Case / Words), treat as shared_step
    return {"action": "test.log", "message": f"TODO: {keyword} {' '.join(args)}".strip()}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class RobotSection:
    SETTINGS = "settings"
    VARIABLES = "variables"
    KEYWORDS = "keywords"
    TEST_CASES = "test cases"
    TASKS = "tasks"


def _normalize_var(text: str) -> str:
    """Convert ${VAR} Robot syntax to Easy BDD ${VAR} — already identical."""
    return text


def _split_args(line: str) -> List[str]:
    """Split a Robot Framework argument line (2+ spaces or tab separator)."""
    parts = re.split(r"  +|\t", line.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_robot_file(content: str) -> Dict[str, Any]:
    """
    Parse a .robot file and return a structured dict:
    {
        "settings":  { "suite_setup": [...], "suite_teardown": [...], "libraries": [...] },
        "variables": { "VAR_NAME": "value", ... },
        "keywords":  [ { "name": str, "args": [...], "steps": [...] }, ... ],
        "tests":     [ { "name": str, "tags": [...], "docs": str, "setup": [...],
                         "teardown": [...], "steps": [...] }, ... ],
    }
    """
    result: Dict[str, Any] = {
        "settings": {"suite_setup": [], "suite_teardown": [], "libraries": [], "resources": []},
        "variables": {},
        "keywords": [],
        "tests": [],
    }

    current_section: Optional[str] = None
    current_block: Optional[Dict[str, Any]] = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        # Blank / comment
        if not line.strip() or line.strip().startswith("#"):
            continue

        # Section header
        section_match = re.match(r"^\*{3}\s+(.+?)\s+\*{0,3}$", line)
        if section_match:
            current_section = section_match.group(1).lower().strip()
            current_block = None
            continue

        if current_section is None:
            continue

        # ---- Settings ----
        if current_section == RobotSection.SETTINGS:
            parts = _split_args(line)
            if not parts:
                continue
            key = parts[0].lower().rstrip(":")
            rest = parts[1:]
            if key == "library":
                result["settings"]["libraries"].extend(rest)
            elif key == "resource":
                result["settings"]["resources"].extend(rest)
            elif key in ("suite setup", "suite_setup"):
                result["settings"]["suite_setup"] = rest
            elif key in ("suite teardown", "suite_teardown"):
                result["settings"]["suite_teardown"] = rest

        # ---- Variables ----
        elif current_section == RobotSection.VARIABLES:
            parts = _split_args(line)
            if not parts:
                continue
            var_match = re.match(r"\$\{(.+?)\}", parts[0])
            if var_match:
                name = var_match.group(1)
                value = parts[1] if len(parts) > 1 else ""
                result["variables"][name] = _normalize_var(value)

        # ---- Keywords ----
        elif current_section == RobotSection.KEYWORDS:
            # Keyword header: no leading whitespace
            if not line.startswith(" ") and not line.startswith("\t"):
                current_block = {"name": line.strip(), "args": [], "steps": []}
                result["keywords"].append(current_block)
            elif current_block is not None:
                parts = _split_args(line)
                if not parts:
                    continue
                first = parts[0]
                rest = parts[1:]
                if first.lower() == "[arguments]":
                    # Extract parameter names (strip ${...})
                    for arg in rest:
                        m = re.match(r"\$\{(.+?)\}", arg)
                        current_block["args"].append(m.group(1) if m else arg)
                elif first.lower() == "[documentation]":
                    current_block["doc"] = " ".join(rest)
                elif first.lower() == "[return]":
                    current_block.setdefault("return_var", rest[0] if rest else "")
                else:
                    # Keyword call
                    step = _map_keyword(first, rest)
                    current_block["steps"].append(step)

        # ---- Test Cases / Tasks ----
        elif current_section in (RobotSection.TEST_CASES, RobotSection.TASKS):
            if not line.startswith(" ") and not line.startswith("\t"):
                current_block = {"name": line.strip(), "tags": [], "docs": "", "setup": [], "teardown": [], "steps": []}
                result["tests"].append(current_block)
            elif current_block is not None:
                parts = _split_args(line)
                if not parts:
                    continue
                first = parts[0]
                rest = parts[1:]
                if first.lower() == "[documentation]":
                    current_block["docs"] = " ".join(rest)
                elif first.lower() == "[tags]":
                    current_block["tags"].extend(rest)
                elif first.lower() == "[setup]":
                    if rest:
                        current_block["setup"].append({"_raw": True, "_keyword": rest[0], "_args": rest[1:]})
                elif first.lower() == "[teardown]":
                    if rest:
                        current_block["teardown"].append({"_raw": True, "_keyword": rest[0], "_args": rest[1:]})
                else:
                    # Store raw so robot_to_tests can resolve user-defined keywords
                    current_block["steps"].append({"_raw": True, "_keyword": first, "_args": rest})

    return result


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------

def _robot_steps_to_easy(steps: List[Dict], user_kw_slugs: set = None) -> List[Dict]:
    """Resolve raw keyword entries to Easy BDD step dicts."""
    result = []
    for s in steps:
        if s.get("_raw"):
            kw = s["_keyword"]
            args = s["_args"]
            if user_kw_slugs:
                result.append(_map_step_with_user_kws(kw, args, user_kw_slugs))
            else:
                result.append(_map_keyword(kw, args))
        else:
            result.append(s)
    return result


def robot_to_shared_steps(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert parsed Robot keywords into Easy BDD shared_steps.yaml structure.
    Returns dict ready for yaml.dump().
    """
    shared: Dict[str, Any] = {}
    for kw in parsed.get("keywords", []):
        # Slug: lowercase, underscored
        slug = re.sub(r"[^a-z0-9]+", "_", kw["name"].lower()).strip("_")
        entry: Dict[str, Any] = {
            "description": kw.get("doc", kw["name"]),
        }
        if kw.get("args"):
            entry["parameters"] = kw["args"]
        entry["steps"] = _robot_steps_to_easy(kw.get("steps", []))
        shared[slug] = entry
    return shared


def _keyword_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _map_step_with_user_kws(keyword: str, args: List[str], user_kw_slugs: set) -> Dict[str, Any]:
    """Like _map_keyword but first checks user-defined keywords → shared_step."""
    slug = _keyword_slug(keyword)
    if slug in user_kw_slugs:
        step: Dict[str, Any] = {"shared_step": slug}
        # Bind positional args to a parameters dict for later use
        if args:
            step["parameters"] = {f"arg{i+1}": a for i, a in enumerate(args)}
        return step
    return _map_keyword(keyword, args)


def robot_to_tests(parsed: Dict[str, Any], suite_variables: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Convert parsed Robot tests into list of Easy BDD test dicts
    (each ready for yaml.dump() as a test file).
    """
    base_vars = dict(suite_variables or {})
    base_vars.update(parsed.get("variables", {}))

    # Build set of user-defined keyword slugs so test steps can reference them
    user_kw_slugs = {_keyword_slug(kw["name"]) for kw in parsed.get("keywords", [])}

    results = []
    suite_setup = parsed["settings"].get("suite_setup", [])
    suite_teardown = parsed["settings"].get("suite_teardown", [])

    for tc in parsed.get("tests", []):
        test_dict: Dict[str, Any] = {
            "name": tc["name"],
            "description": tc.get("docs", ""),
            "tags": tc.get("tags", []) or [],
        }

        if base_vars:
            test_dict["variables"] = base_vars

        # Suite-level setup as test setup
        setup_steps = []
        if suite_setup:
            kw_name = suite_setup[0]
            kw_args = suite_setup[1:]
            setup_steps.append(_map_keyword(kw_name, kw_args))
        if tc.get("setup"):
            setup_steps.extend(_robot_steps_to_easy(tc["setup"], user_kw_slugs))
        if setup_steps:
            test_dict["setup"] = setup_steps

        test_dict["steps"] = _robot_steps_to_easy(tc.get("steps", []), user_kw_slugs)

        # Teardown
        teardown_steps = []
        if tc.get("teardown"):
            teardown_steps.extend(_robot_steps_to_easy(tc["teardown"], user_kw_slugs))
        if suite_teardown:
            kw_name = suite_teardown[0]
            kw_args = suite_teardown[1:]
            teardown_steps.append(_map_keyword(kw_name, kw_args))
        if teardown_steps:
            test_dict["cleanup"] = teardown_steps

        results.append(test_dict)

    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def migrate(content: str) -> Dict[str, Any]:
    """
    Top-level migration function.  Returns:
    {
        "tests": [ { "name": str (slug), "yaml": str }, ... ],
        "shared_steps": { ... }  # merged dict for shared_steps.yaml
        "warnings": [ str, ... ]
    }
    """
    import yaml

    parsed = parse_robot_file(content)
    shared = robot_to_shared_steps(parsed)
    tests_raw = robot_to_tests(parsed)

    warnings: List[str] = []
    test_files = []
    for t in tests_raw:
        slug = re.sub(r"[^a-z0-9]+", "_", t["name"].lower()).strip("_")
        # Flag TODO steps
        todo_steps = [s for s in t.get("steps", []) if s.get("action") == "test.log" and str(s.get("message", "")).startswith("TODO:")]
        if todo_steps:
            warnings.append(f"Test '{t['name']}': {len(todo_steps)} step(s) could not be auto-mapped and need manual review.")
        test_files.append({
            "name": slug,
            "display_name": t["name"],
            "yaml": yaml.dump(t, sort_keys=False, allow_unicode=True),
        })

    if not parsed["tests"]:
        warnings.append("No test cases found in the file. Only keywords/variables were imported.")

    return {
        "tests": test_files,
        "shared_steps": shared,
        "shared_steps_yaml": yaml.dump(shared, sort_keys=False, allow_unicode=True) if shared else "",
        "warnings": warnings,
        "summary": {
            "tests": len(test_files),
            "shared_steps": len(shared),
            "variables": len(parsed.get("variables", {})),
        },
    }
