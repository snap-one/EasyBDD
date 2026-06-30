"""
playwright_importer.py — Convert Playwright recordings to Easy BDD test cases.

Handles two input formats:
  1. JS/TS code   — output from the Playwright CRX recorder or codegen
  2. JSON trace   — Playwright trace.zip / trace.json (trace API)

Usage (via MCP tool):
    import_playwright_recording(source="path/to/test.js", test_name="Login flow")
    import_playwright_recording(source="path/to/trace.zip")
    import_playwright_recording(source="<raw JS code>")
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import GeneratedStep, GeneratedTestCase


# ── Selector resolution ────────────────────────────────────────────────────────

def _resolve_locator(expr: str) -> str:
    """
    Convert a Playwright locator expression to an Easy BDD selector string.

    Handles:
      getByRole('button', { name: 'Save' })  →  role=button[name="Save"]
      getByLabel('Username')                  →  label=Username
      getByPlaceholder('Enter email')         →  [placeholder="Enter email"]
      getByText('Submit')                     →  text=Submit
      getByTestId('submit-btn')               →  [data-testid="submit-btn"]
      locator('#id')                          →  #id
      locator('.class')                       →  .class
      locator('css >> text')                  →  css >> text   (pass-through)
      frameLocator(...)                       →  (skipped — too complex)
    """
    expr = expr.strip()

    # getByRole('role', { name: 'text', exact: true })
    m = re.search(r"getByRole\(['\"](\w+)['\"](?:,\s*\{([^}]*)\})?\)", expr)
    if m:
        role = m.group(1)
        opts = m.group(2) or ""
        name_m = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", opts)
        name = name_m.group(1) if name_m else ""
        return f'role={role}[name="{name}"]' if name else f"role={role}"

    # getByLabel('text')
    m = re.search(r"getByLabel\(['\"]([^'\"]+)['\"]", expr)
    if m:
        return f"label={m.group(1)}"

    # getByPlaceholder('text')
    m = re.search(r"getByPlaceholder\(['\"]([^'\"]+)['\"]", expr)
    if m:
        return f'[placeholder="{m.group(1)}"]'

    # getByText('text')
    m = re.search(r"getByText\(['\"]([^'\"]+)['\"]", expr)
    if m:
        return f"text={m.group(1)}"

    # getByTestId('id')
    m = re.search(r"getByTestId\(['\"]([^'\"]+)['\"]", expr)
    if m:
        return f'[data-testid="{m.group(1)}"]'

    # locator('selector') or locator("selector")
    # Use separate patterns to correctly handle XPaths like '//div[@id="x"]'
    # where the inner attribute values use the opposite quote style.
    m = re.search(r"(?:^|\.)locator\('([^']*)'\)", expr)
    if m:
        return m.group(1)
    m = re.search(r'(?:^|\.)locator\("([^"]*)"\)', expr)
    if m:
        return m.group(1)

    # nth(n) — keep as-is for now, strip it
    expr = re.sub(r"\.nth\(\d+\)", "", expr)

    # Fallback: return the expression cleaned up
    return expr.strip(".page ")


def _extract_string_arg(s: str) -> str:
    """Pull the first string literal from a JS argument string."""
    m = re.search(r"['\"`]([^'\"`]*)['\"`]", s)
    return m.group(1) if m else s.strip()


def _extract_args(s: str) -> List[str]:
    """Rough extraction of top-level comma-separated args from a call's arg string."""
    args = []
    depth = 0
    current = ""
    for ch in s:
        if ch in "({[":
            depth += 1
            current += ch
        elif ch in ")}]":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        args.append(current.strip())
    return args


# ── JS/TS code parser ──────────────────────────────────────────────────────────

# Matches:   await expect(locator).toXxx(args)
# The inner group uses a one-level nested-paren pattern so that
# expect(page.locator('#id')) is captured correctly — [^)]+
# would stop at the ) closing locator() instead of expect().
_EXPECT_RE = re.compile(
    r"(?:await\s+)?expect\(([^()]*(?:\([^)]*\)[^()]*)*)\)\s*\.\s*(toBeVisible|toBeHidden|"
    r"toContainText|toHaveText|toHaveValue|toHaveURL|toHaveTitle|"
    r"toBeChecked|toBeEnabled|toBeDisabled)\s*\(([^)]*)\)",
    re.DOTALL,
)

# Matches:   await page.goto('url')
_GOTO_RE = re.compile(r"(?:await\s+)?(?:page|context)\s*\.\s*goto\s*\(\s*['\"]([^'\"]+)['\"]")

# Test function names
_TEST_FUNC_RE = re.compile(
    r"(?:test|it)\s*\(\s*['\"]([^'\"]+)['\"]",
)

# Boilerplate lines to skip (teardown / setup noise)
_SKIP_PATTERNS = (
    "context.close()", "browser.close()", "chromium.launch(",
    "firefox.launch(", "webkit.launch(", "newContext()", "newPage()",
    "browser.newContext", "browser.launch",
)

# Known Playwright action method names (order matters for search priority)
_ACTION_METHODS = [
    "fill", "type", "selectOption", "dblclick", "click", "check", "uncheck",
    "press", "tap", "hover", "focus", "clear", "screenshot",
    "waitForURL", "waitForSelector", "waitForTimeout",
]


def _extract_call_args(line: str, open_pos: int) -> str:
    """Return the content inside the parens starting at open_pos (the '(' char)."""
    depth = 1
    i = open_pos + 1
    while i < len(line) and depth > 0:
        if line[i] == "(":
            depth += 1
        elif line[i] == ")":
            depth -= 1
        i += 1
    return line[open_pos + 1: i - 1]


def _find_last_action(line: str) -> Optional[Tuple[str, str, str]]:
    """
    Scan *line* right-to-left for the last Playwright action method call.

    Returns (action_name, args_str, locator_expr) where locator_expr is
    everything in the line before the '.action(' token.
    Returns None if no known action is found.
    """
    best: Optional[Tuple[int, str, str, str]] = None  # (pos, action, args, locator)

    for action in _ACTION_METHODS:
        # Find every occurrence of .action( (not inside a string literal)
        pattern = r"\." + re.escape(action) + r"\s*\("
        for m in re.finditer(pattern, line):
            pos = m.start()
            open_paren = m.end() - 1  # position of '('
            args_str = _extract_call_args(line, open_paren)
            locator_expr = line[:pos]
            if best is None or pos > best[0]:
                best = (pos, action, args_str, locator_expr)

    if best is None:
        return None
    _, action, args_str, locator_expr = best
    return action, args_str, locator_expr


def _resolve_locator_chain(chain: str) -> str:
    """
    Given the locator portion of a Playwright statement (everything before
    the final .action()), extract the most specific (last) locator call.

    page.locator('#id')                                    → #id
    page.getByRole('button', { name: 'Save' })            → role=button[name="Save"]
    page.getByRole('cell', {...}).getByRole('textbox')     → role=textbox
    page.locator('div').filter({ hasText: /foo/ })         → div
    """
    # Strip leading 'await page' / 'await context' / 'page' etc.
    chain = re.sub(r"^\s*(?:await\s+)?(?:page|context|frame)\s*", "", chain).strip()

    # Collect all getBy*/locator() calls with their args (paren-aware)
    locator_methods = (
        "getByRole", "getByLabel", "getByPlaceholder",
        "getByText", "getByTestId", "locator",
    )
    calls: List[str] = []
    i = 0
    while i < len(chain):
        found = None
        for method in locator_methods:
            pattern = r"\." + re.escape(method) + r"\s*\("
            m = re.search(pattern, chain[i:])
            if m and (found is None or m.start() < found[0]):
                found = (m.start(), m.end(), method, m)
        if found is None:
            break
        rel_start, rel_end, method, _ = found
        open_paren = i + rel_end - 1  # position of '(' in original chain
        args_str = _extract_call_args(chain, open_paren)
        calls.append(f"{method}({args_str})")
        i = open_paren + len(args_str) + 2  # skip past closing ')'

    if not calls:
        return chain  # fallback: return the raw chain
    # Use the last (most specific) locator
    return _resolve_locator(calls[-1])


def _parse_js_line(line: str) -> Optional[Dict[str, Any]]:
    """Convert a single JS/TS line to a raw step dict."""
    line = line.strip()
    if not line or line.startswith("//") or line.startswith("*"):
        return None

    # Skip boilerplate / teardown
    if any(p in line for p in _SKIP_PATTERNS):
        return None

    # page.goto
    m = _GOTO_RE.search(line)
    if m:
        return {"action": "browser.open", "params": {"url": m.group(1)}}

    # await expect(locator).assertion(args)
    m = _EXPECT_RE.search(line)
    if m:
        locator_expr = m.group(1).strip()
        assertion = m.group(2)
        args_str = m.group(3).strip()
        selector = _resolve_locator(locator_expr)

        if assertion == "toBeVisible":
            return {"action": "browser.assert_visible", "params": {"selector": selector}}
        if assertion == "toBeHidden":
            return {"action": "browser.assert_not_visible", "params": {"selector": selector}}
        if assertion in ("toContainText", "toHaveText"):
            text = _extract_string_arg(args_str)
            return {"action": "browser.assert_text", "params": {"selector": selector, "text": text}}
        if assertion == "toHaveValue":
            val = _extract_string_arg(args_str)
            return {"action": "browser.assert_value", "params": {"selector": selector, "value": val}}
        if assertion == "toHaveURL":
            url = _extract_string_arg(args_str)
            return {"action": "browser.assert_url", "params": {"url": url}}
        if assertion == "toHaveTitle":
            title = _extract_string_arg(args_str)
            return {"action": "browser.assert_text", "params": {"selector": "title", "text": title}}
        if assertion == "toBeChecked":
            return {"action": "browser.assert_checked", "params": {"selector": selector}}
        if assertion == "toBeEnabled":
            return {"action": "browser.assert_enabled", "params": {"selector": selector}}
        if assertion == "toBeDisabled":
            return {"action": "browser.assert_disabled", "params": {"selector": selector}}
        return None

    # General action: find the last .action( in the line (paren-aware)
    result = _find_last_action(line)
    if not result:
        return None

    action, args_str, locator_expr = result
    selector = _resolve_locator_chain(locator_expr)

    if action in ("fill", "type"):
        value = _extract_string_arg(args_str)
        return {"action": "browser.fill", "params": {"selector": selector, "value": value}}

    if action == "click":
        return {"action": "browser.click", "params": {"selector": selector}}

    if action == "dblclick":
        return {"action": "browser.dblclick", "params": {"selector": selector}}

    if action == "check":
        return {"action": "browser.check", "params": {"selector": selector}}

    if action == "uncheck":
        return {"action": "browser.uncheck", "params": {"selector": selector}}

    if action == "selectOption":
        args = _extract_args(args_str)
        value = _extract_string_arg(args[0]) if args else ""
        label_m = re.search(r"label\s*:\s*['\"]([^'\"]+)['\"]", args_str)
        if label_m:
            value = label_m.group(1)
        return {"action": "browser.select", "params": {"selector": selector, "value": value}}

    if action == "press":
        key = _extract_string_arg(args_str)
        return {"action": "browser.press_key", "params": {"selector": selector, "key": key}}

    if action == "hover":
        return {"action": "browser.hover", "params": {"selector": selector}}

    if action == "clear":
        return {"action": "browser.fill", "params": {"selector": selector, "value": ""}}

    if action == "screenshot":
        name_m = re.search(r"path\s*:\s*['\"]([^'\"]+)['\"]", args_str)
        name = Path(name_m.group(1)).stem if name_m else "screenshot"
        return {"action": "browser.screenshot", "params": {"name": name}}

    if action == "waitForURL":
        pattern = _extract_string_arg(args_str)
        return {"action": "browser.wait_for_url", "params": {"pattern": pattern, "timeout": 10000}}

    if action == "waitForSelector":
        sel = _extract_string_arg(args_str)
        return {"action": "browser.wait_for", "params": {"selector": sel, "timeout": 10000}}

    if action == "waitForTimeout":
        ms = args_str.strip()
        return {"action": "browser.wait", "params": {"timeout": int(ms) if ms.isdigit() else 1000}}

    return None


def parse_playwright_code(
    code: str,
    default_name: str = "Imported test",
) -> List[Tuple[str, List[Dict]]]:
    """
    Parse a JS/TS Playwright test file.

    Returns list of (test_name, steps) tuples — one per test() block.
    If the code has no test() wrapper, treats the whole thing as one test.
    """
    results: List[Tuple[str, List[Dict]]] = []
    lines = code.splitlines()

    # Find test() blocks
    test_blocks: List[Tuple[str, int, int]] = []  # (name, start_line, end_line)
    brace_depth = 0
    in_test = False
    test_name = ""
    test_start = 0

    for i, line in enumerate(lines):
        func_m = _TEST_FUNC_RE.search(line)
        if func_m and not in_test:
            test_name = func_m.group(1)
            test_start = i
            in_test = True
            brace_depth = line.count("{") - line.count("}")
        elif in_test:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                test_blocks.append((test_name, test_start, i))
                in_test = False

    if not test_blocks:
        # No test() wrappers — parse the whole file as one test
        test_blocks = [(default_name, 0, len(lines) - 1)]

    for name, start, end in test_blocks:
        steps = []
        for line in lines[start:end + 1]:
            step = _parse_js_line(line)
            if step:
                steps.append(step)
        if steps:
            results.append((name, steps))

    return results


# ── JSON trace parser ──────────────────────────────────────────────────────────

def _trace_selector_to_easybdd(selector: str) -> str:
    """Convert a Playwright internal selector to Easy BDD format."""
    # Playwright internal format: "role=button[name="Save"]" — already compatible
    # Or "css=#id", "text=foo", etc.
    selector = selector.strip()
    # Strip "css=" prefix if present
    if selector.startswith("css="):
        selector = selector[4:]
    # internal:role=button[name="Save"] → role=button[name="Save"]
    if selector.startswith("internal:"):
        selector = selector[len("internal:"):]
    return selector


def parse_playwright_trace(trace_path: str) -> List[Tuple[str, List[Dict]]]:
    """
    Parse a Playwright trace file (.zip or .json) and extract user actions.

    Returns [(test_name, steps)] — typically one entry per trace.
    """
    path = Path(trace_path)
    raw_events: List[Dict] = []

    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            # Look for the main trace file
            trace_files = [n for n in zf.namelist() if n.endswith(".trace")]
            if not trace_files:
                raise ValueError(f"No .trace file found in {trace_path}")
            with zf.open(trace_files[0]) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            raw_events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
    elif path.suffix in (".json", ".trace"):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        raw_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    else:
        raise ValueError(f"Unsupported trace format: {path.suffix}")

    steps = []
    for event in raw_events:
        step = _trace_event_to_step(event)
        if step:
            steps.append(step)

    name = path.stem.replace("-", " ").replace("_", " ").title()
    return [(name, steps)] if steps else []


def _trace_event_to_step(event: Dict) -> Optional[Dict]:
    """Convert a single Playwright trace event to an Easy BDD step dict."""
    etype = event.get("type", "")

    # Playwright trace v1 format
    if etype == "action":
        method = event.get("method", "")
        params = event.get("params", {})
        selector = _trace_selector_to_easybdd(event.get("selector", ""))

        if method == "goto":
            return {"action": "browser.open", "params": {"url": params.get("url", "")}}
        if method in ("fill", "type"):
            return {"action": "browser.fill", "params": {"selector": selector, "value": params.get("value", "")}}
        if method == "click":
            return {"action": "browser.click", "params": {"selector": selector}}
        if method == "dblclick":
            return {"action": "browser.dblclick", "params": {"selector": selector}}
        if method in ("check", "setChecked"):
            return {"action": "browser.check", "params": {"selector": selector}}
        if method == "uncheck":
            return {"action": "browser.uncheck", "params": {"selector": selector}}
        if method == "selectOption":
            val = params.get("options", [{}])
            opt = val[0] if val else {}
            value = opt.get("value") or opt.get("label") or ""
            return {"action": "browser.select", "params": {"selector": selector, "value": value}}
        if method == "press":
            return {"action": "browser.press_key", "params": {"selector": selector, "key": params.get("key", "")}}
        if method == "hover":
            return {"action": "browser.hover", "params": {"selector": selector}}
        if method == "screenshot":
            return {"action": "browser.screenshot", "params": {"name": "trace-screenshot"}}
        if method == "waitForURL":
            return {"action": "browser.wait_for_url", "params": {"pattern": params.get("url", ""), "timeout": 10000}}

    # Playwright trace v2/v3 format (callLog events)
    if etype in ("call", "after") and event.get("apiName"):
        api = event["apiName"]
        params = event.get("params", {})
        selector_raw = params.get("selector", "")
        selector = _trace_selector_to_easybdd(selector_raw) if selector_raw else ""

        if "goto" in api:
            return {"action": "browser.open", "params": {"url": params.get("url", "")}}
        if "fill" in api and selector:
            return {"action": "browser.fill", "params": {"selector": selector, "value": params.get("value", "")}}
        if "click" in api and selector:
            return {"action": "browser.click", "params": {"selector": selector}}
        if "selectOption" in api and selector:
            opts = params.get("options", [{}])
            opt = opts[0] if opts else {}
            value = opt.get("value") or opt.get("label") or ""
            return {"action": "browser.select", "params": {"selector": selector, "value": value}}

    return None


# ── Converter: raw steps → GeneratedTestCase ──────────────────────────────────

def _steps_to_case(
    name: str,
    raw_steps: List[Dict],
    url: str = "",
) -> GeneratedTestCase:
    """Convert a list of raw step dicts to a GeneratedTestCase."""
    steps = []

    # Derive URL from first browser.open step if not provided
    if not url:
        for s in raw_steps:
            if s["action"] == "browser.open":
                url = s["params"].get("url", "")
                break

    # Deduplicate: remove a click when the very next step is a fill/click on the
    # same selector (Playwright records a click before every fill — redundant in Easy BDD)
    deduped: List[Dict] = []
    for i, s in enumerate(raw_steps):
        if s["action"] == "browser.click" and i + 1 < len(raw_steps):
            nxt = raw_steps[i + 1]
            if (nxt["action"] in ("browser.fill", "browser.click") and
                    nxt["params"].get("selector") == s["params"].get("selector")):
                continue  # skip redundant pre-fill click
        deduped.append(s)

    for s in deduped:
        steps.append(GeneratedStep(
            action=s["action"],
            params=s["params"],
            description=_auto_description(s),
        ))

    # Ensure test ends with a screenshot
    if steps and steps[-1].action != "browser.screenshot":
        slug = re.sub(r"[^a-z0-9]", "-", name.lower())[:30]
        steps.append(GeneratedStep(
            action="browser.screenshot",
            params={"name": f"{slug}-final"},
            description="Capture final state",
        ))

    # Infer tags from step content
    tags = ["browser", "imported"]
    action_names = {s.action for s in steps}
    if "browser.fill" in action_names:
        tags.append("form")
    if any("login" in str(s.params).lower() or "sign" in str(s.params).lower() for s in steps):
        tags.append("auth")

    return GeneratedTestCase(
        name=name,
        description=f"Imported from Playwright recording — {name}",
        tags=tags,
        url=url,
        steps=steps,
    )


def _auto_description(step: Dict) -> str:
    """Generate a human-readable description for a step."""
    action = step["action"]
    p = step.get("params", {})
    sel = p.get("selector", "")
    val = p.get("value", "")
    url = p.get("url", "")

    if action == "browser.open":
        return f"Open {url}"
    if action == "browser.fill":
        return f"Fill '{sel}' with '{val}'"
    if action == "browser.click":
        return f"Click '{sel}'"
    if action == "browser.select":
        return f"Select '{val}' from '{sel}'"
    if action == "browser.press_key":
        return f"Press {p.get('key', '')} on '{sel}'"
    if action == "browser.assert_visible":
        return f"Verify '{sel}' is visible"
    if action == "browser.assert_text":
        return f"Verify '{sel}' contains '{p.get('text', '')}'"
    if action == "browser.assert_url":
        return f"Verify URL is '{url}'"
    if action == "browser.wait_for":
        return f"Wait for '{sel}'"
    if action == "browser.wait_for_url":
        return f"Wait for URL matching '{p.get('pattern', '')}'"
    if action == "browser.screenshot":
        return f"Screenshot: {p.get('name', '')}"
    return action


# ── Public API ─────────────────────────────────────────────────────────────────

def import_recording(
    source: str,
    default_name: str = "Imported test",
    output_dir: str = "tests/cases/imported",
) -> List[GeneratedTestCase]:
    """
    Import a Playwright recording from:
      - A file path (.js, .ts, .json, .trace, .zip)
      - Raw JS/TS code (string starting with 'import', 'const', 'await', 'test(')

    Returns a list of GeneratedTestCase objects ready for YAML writing and TestRail push.
    """
    from pathlib import Path as _Path
    from .yaml_writer import write_test_case

    # Detect if source is a file path or raw code
    is_file = False
    path = _Path(source)
    if len(source) < 512 and path.exists():
        is_file = True

    if is_file:
        suffix = path.suffix.lower()
        if suffix in (".zip", ".trace", ".json"):
            raw = parse_playwright_trace(source)
        else:
            code = path.read_text(encoding="utf-8")
            raw = parse_playwright_code(code, default_name=path.stem)
    else:
        # Raw code string
        raw = parse_playwright_code(source, default_name=default_name)

    cases = [_steps_to_case(name, steps) for name, steps in raw]

    # Write YAML files
    out = _Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for case in cases:
        write_test_case(case, out)

    return cases
