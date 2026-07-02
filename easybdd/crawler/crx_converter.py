"""
crx_converter.py — Convert Playwright CRX / Chrome DevTools Recorder scripts
to Easy BDD dot-notation YAML.

Supports two input formats:

  1. **Chrome DevTools Recorder JSON** (.json)
     The JSON format exported from Chrome DevTools → Recorder panel.
     This is the same "chrome-devtools" format in RecorderConverter, but
     this module handles additional step types and emits proper YAML files.

  2. **Playwright TypeScript / JavaScript** (.ts / .js / .py)
     The output from "Export as Playwright test" in Chrome DevTools Recorder,
     or from `playwright codegen --target=typescript`.
     Handles all modern Playwright locator APIs (getByRole, getByLabel,
     getByPlaceholder, getByTestId, getByText, locator, frameLocator) and
     expect() assertions.

CLI usage:
    python -m easybdd crawler convert-crx path/to/recording.ts
    python -m easybdd crawler convert-crx path/to/recording.json
    python -m easybdd crawler convert-crx recording.ts --output tests/cases/

Programmatic usage:
    from easybdd.crawler.crx_converter import convert_crx_file
    yaml_text = convert_crx_file("recording.ts")
    # or get the dict directly:
    from easybdd.crawler.crx_converter import PlaywrightTsConverter
    data = PlaywrightTsConverter().convert(ts_code, filename="my_test")
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    """Escape double-quotes for use inside a YAML double-quoted string."""
    return s.replace('"', '\\"')


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_")


def _extract_base_url(url: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


# ── Playwright TypeScript / JavaScript converter ──────────────────────────────

class PlaywrightTsConverter:
    """
    Converts Playwright TypeScript/JavaScript test code to Easy BDD
    dot-notation YAML.

    Handles:
    - page.goto(url)
    - page.getByRole(role, { name })
    - page.getByLabel(label)
    - page.getByPlaceholder(placeholder)
    - page.getByTestId(testId)
    - page.getByText(text)
    - page.locator(selector)
    - page.frameLocator(frame).getBy*(...)  → iframe >> selector
    - Chained actions: .click() .fill(v) .check() .uncheck() .selectOption(v)
                       .press(key) .clear() .hover() .dblclick()
    - page.keyboard.press(key)
    - page.waitForURL(url)
    - page.waitForSelector(sel) / page.waitForTimeout(ms)
    - page.screenshot()
    - expect(locator).toBeVisible() / toHaveText() / toHaveValue() /
      toBeChecked() / toBeEnabled() / toBeDisabled()
    - expect(page).toHaveURL(url) / toHaveTitle(title)
    """

    # Regex fragments
    _STR = r"""(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')"""   # capture group 1 or 2
    _NUM = r"(\d+)"

    def convert(self, code: str, filename: str = "recording") -> Dict[str, Any]:
        """
        Convert TypeScript/JS source to an Easy BDD test data dict.
        The dict is suitable for yaml.dump().
        """
        test_name = self._extract_test_name(code) or _slugify(filename).replace("_", " ").title()
        steps: List[Dict[str, Any]] = []
        variables: Dict[str, Any] = {}

        for raw_stmt in self._iter_statements(code):
            step = self._parse_statement(raw_stmt, variables)
            if step:
                steps.append(step)

        result: Dict[str, Any] = {
            "name": test_name,
            "description": f"Converted from Playwright recording: {filename}",
            "tags": ["browser", "recorded", "playwright"],
        }
        if variables:
            result["variables"] = variables
        result["steps"] = steps
        return result

    # ── Test name extraction ──────────────────────────────────────────────────

    def _extract_test_name(self, code: str) -> Optional[str]:
        """Pull the test name from `test('name', ...)` or `it('name', ...)`."""
        m = re.search(r"\btest\s*\(\s*" + self._STR, code)
        if not m:
            m = re.search(r"\bit\s*\(\s*" + self._STR, code)
        if m:
            return (m.group(1) or m.group(2) or "").strip()
        return None

    # ── Statement iteration ───────────────────────────────────────────────────

    def _iter_statements(self, code: str) -> List[str]:
        """
        Extract individual await statements from the test body.
        Joins lines that are continuations of the same method chain.
        """
        # Strip block comments (safe — never inside strings in practice)
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
        # Strip TypeScript import/require lines (whole lines)
        code = re.sub(r"^[ \t]*(?:import|const|let|var|require)\b[^\n]*$", "", code, flags=re.MULTILINE)
        # Strip standalone comment lines (lines where // is the first non-whitespace)
        code = re.sub(r"^[ \t]*//[^\n]*$", "", code, flags=re.MULTILINE)
        # Strip test/it/describe wrapper opening (leave body)
        # Handles: test('name', async ({ page }) => {
        code = re.sub(r"\b(?:test|it|describe)\s*\([^\n]*\{", "", code)

        # Collect lines, join continuation chains
        raw_lines = code.splitlines()
        statements: List[str] = []
        buf = ""

        for line in raw_lines:
            stripped = line.strip().rstrip(";").strip()
            if not stripped:
                if buf:
                    statements.append(buf)
                    buf = ""
                continue

            # Remove leading `await`
            stripped = re.sub(r"^\s*await\s+", "", stripped)

            # Starts a new statement if it starts with `page.` or `expect(`
            is_new = (
                stripped.startswith("page.")
                or stripped.startswith("expect(")
                or re.match(r"^[a-zA-Z_$]", stripped) is not None
            )

            if is_new and buf:
                statements.append(buf)
                buf = stripped
            elif buf:
                buf += " " + stripped
            else:
                buf = stripped

        if buf:
            statements.append(buf)

        return statements

    # ── Statement dispatcher ──────────────────────────────────────────────────

    def _parse_statement(
        self, stmt: str, variables: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Parse one normalized statement (no `await`, no trailing `;`)."""
        # Skip boilerplate
        if not stmt.startswith(("page.", "expect(")):
            return None

        # page.goto(url)
        if stmt.startswith("page.goto("):
            return self._parse_goto(stmt, variables)

        # page.keyboard.press(key)
        if stmt.startswith("page.keyboard.press("):
            return self._parse_keyboard_press(stmt)

        # page.waitForURL / page.waitForSelector / page.waitForTimeout
        if stmt.startswith("page.waitForURL("):
            return self._parse_wait_for_url(stmt)
        if stmt.startswith("page.waitForSelector("):
            return self._parse_wait_for_selector(stmt)
        if stmt.startswith("page.waitForTimeout("):
            return None  # pure delay — not useful as a test step

        # page.screenshot()
        if stmt.startswith("page.screenshot("):
            return {"browser.screenshot": {"name": "screenshot"}}

        # expect(...)
        if stmt.startswith("expect("):
            return self._parse_expect(stmt)

        # page.frameLocator(...).getBy*(...).<action>()
        if "frameLocator(" in stmt:
            return self._parse_frame_action(stmt)

        # page.getBy*(...) / page.locator(...).<action>()
        if re.match(r"page\.(getBy\w+|locator)\(", stmt):
            return self._parse_locator_action(stmt)

        return None

    # ── goto ──────────────────────────────────────────────────────────────────

    def _parse_goto(self, stmt: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        m = re.match(r"page\.goto\(\s*" + self._STR, stmt)
        if not m:
            return None
        url = (m.group(1) or m.group(2) or "").strip()
        if url and "base_url" not in variables:
            variables["base_url"] = _extract_base_url(url)
        return {"browser.open": {"url": url}}

    # ── keyboard.press ────────────────────────────────────────────────────────

    def _parse_keyboard_press(self, stmt: str) -> Optional[Dict[str, Any]]:
        m = re.match(r"page\.keyboard\.press\(\s*" + self._STR, stmt)
        if not m:
            return None
        key = (m.group(1) or m.group(2) or "").strip()
        return {"browser.press_key": {"key": key}}

    # ── waitForURL ────────────────────────────────────────────────────────────

    def _parse_wait_for_url(self, stmt: str) -> Optional[Dict[str, Any]]:
        m = re.match(r"page\.waitForURL\(\s*" + self._STR, stmt)
        if m:
            url = (m.group(1) or m.group(2) or "").strip()
            return {"browser.wait_for_url": {"url": url}}
        return None

    # ── waitForSelector ───────────────────────────────────────────────────────

    def _parse_wait_for_selector(self, stmt: str) -> Optional[Dict[str, Any]]:
        m = re.match(r"page\.waitForSelector\(\s*" + self._STR, stmt)
        if m:
            sel = (m.group(1) or m.group(2) or "").strip()
            state = "visible"
            sm = re.search(r"state\s*:\s*['\"](\w+)['\"]", stmt)
            if sm:
                state = sm.group(1)
            return {"browser.wait_for": {"selector": sel, "state": state}}
        return None

    # ── expect ────────────────────────────────────────────────────────────────

    def _extract_expect_inner(self, stmt: str) -> Tuple[str, str]:
        """
        Given `expect(<locator>).<method>(...)`, return (locator_expr, rest).
        Uses paren-depth tracking so `getByRole('x', { name: 'y' })` works.
        """
        # Skip "expect("
        if not stmt.startswith("expect("):
            return ("", "")
        i = len("expect(")
        depth = 1
        while i < len(stmt) and depth > 0:
            if stmt[i] == "(":
                depth += 1
            elif stmt[i] == ")":
                depth -= 1
            i += 1
        # i now points just past the closing ) of expect(...)
        locator_expr = stmt[len("expect("):i - 1].strip()
        rest = stmt[i:].lstrip(".")  # strip leading dot before method name
        return (locator_expr, rest)

    def _parse_expect(self, stmt: str) -> Optional[Dict[str, Any]]:
        locator_expr, rest = self._extract_expect_inner(stmt)
        if not rest:
            return None

        # expect(page).toHaveURL / toHaveTitle
        if locator_expr == "page":
            m = re.match(r"toHaveTitle\(\s*" + self._STR, rest)
            if m:
                title = (m.group(1) or m.group(2) or "").strip()
                return {"test.assert_text_contains": {"selector": "title", "text": title}}
            m = re.match(r"toHaveURL\(\s*" + self._STR, rest)
            if m:
                url = (m.group(1) or m.group(2) or "").strip()
                return {"test.assert_url": {"url": url}}
            return None

        sel_fields = self._locator_expr_to_fields(locator_expr)
        if not sel_fields:
            return None

        # .toBeVisible()
        if rest.startswith("toBeVisible("):
            return {"browser.wait_for": {"selector": self._fields_to_selector(sel_fields), "state": "visible"}}

        # .toBeHidden()
        if rest.startswith("toBeHidden("):
            return {"browser.wait_for": {"selector": self._fields_to_selector(sel_fields), "state": "hidden"}}

        # .toBeChecked()
        if rest.startswith("toBeChecked("):
            return {"browser.assert_checked": {"selector": self._fields_to_selector(sel_fields)}}

        # .toBeEnabled()
        if rest.startswith("toBeEnabled("):
            return {"browser.wait_for": {"selector": self._fields_to_selector(sel_fields), "state": "enabled"}}

        # .toBeDisabled()
        if rest.startswith("toBeDisabled("):
            return {"browser.wait_for": {"selector": self._fields_to_selector(sel_fields), "state": "disabled"}}

        # .toHaveText(text)  / .toContainText(text)
        for method in ("toHaveText(", "toContainText("):
            if rest.startswith(method):
                tail = rest[len(method):]
                m = re.match(self._STR, tail)
                if m:
                    text_val = (m.group(1) or m.group(2) or "").strip()
                    return {"test.assert_text_contains": {
                        "selector": self._fields_to_selector(sel_fields),
                        "text": text_val,
                    }}

        # .toHaveValue(value)
        if rest.startswith("toHaveValue("):
            tail = rest[len("toHaveValue("):]
            m = re.match(self._STR, tail)
            if m:
                val = (m.group(1) or m.group(2) or "").strip()
                return {"test.assert_value": {
                    "selector": self._fields_to_selector(sel_fields),
                    "value": val,
                }}

        return None

    @staticmethod
    def _fields_to_selector(fields: Dict[str, Any]) -> str:
        """
        Collapse locator fields to a single Playwright selector string.
        browser.wait_for only accepts selector/state/timeout (unlike
        browser.click, which understands role/name/text/label), so
        role/text/label locators are expressed via selector engines.
        """
        if fields.get("selector"):
            return fields["selector"]
        if fields.get("role"):
            name = fields.get("name")
            if name:
                return f'role={fields["role"]}[name="{_esc(name)}"]'
            return f'role={fields["role"]}'
        if fields.get("text"):
            return f'text="{_esc(fields["text"])}"'
        if fields.get("label"):
            # Best effort — getByLabel also matches <label> association,
            # but aria-label is the closest selector-only equivalent.
            return f'[aria-label="{_esc(fields["label"])}"]'
        return "body"

    def _locator_expr_to_fields(self, expr: str) -> Dict[str, Any]:
        """
        Convert a page.getBy*(...) or page.locator(...) expression string
        to a selector fields dict.
        """
        # Only pass the first method call to avoid chained .filter() etc.
        base = expr.strip()
        # Synthesize a fake statement with .noop() to route through locator parser
        fields = self._extract_locator_fields(base)
        return fields if fields else {"selector": base}

    def _extract_locator_fields(self, locator_expr: str) -> Dict[str, Any]:
        """
        Parse `page.getBy*(...)` or `page.locator(...)` into a fields dict.
        """
        # getByRole(role, { name: 'X' })
        m = re.match(
            r"page\.getByRole\(\s*" + self._STR + r"(?:\s*,\s*\{[^}]*\})?",
            locator_expr,
        )
        if m:
            role = (m.group(1) or m.group(2) or "").strip()
            fields: Dict[str, Any] = {"role": role}
            nm = re.search(r"name\s*:\s*" + self._STR, locator_expr)
            if nm:
                fields["name"] = (nm.group(1) or nm.group(2) or "").strip()
            return fields

        # getByLabel('X')
        m = re.match(r"page\.getByLabel\(\s*" + self._STR, locator_expr)
        if m:
            return {"label": (m.group(1) or m.group(2) or "").strip()}

        # getByPlaceholder('X')
        m = re.match(r"page\.getByPlaceholder\(\s*" + self._STR, locator_expr)
        if m:
            ph = (m.group(1) or m.group(2) or "").strip()
            return {"selector": f'[placeholder="{_esc(ph)}"]'}

        # getByTestId('X')
        m = re.match(r"page\.getByTestId\(\s*" + self._STR, locator_expr)
        if m:
            tid = (m.group(1) or m.group(2) or "").strip()
            return {"selector": f'[data-testid="{_esc(tid)}"]'}

        # getByText('X')
        m = re.match(r"page\.getByText\(\s*" + self._STR, locator_expr)
        if m:
            return {"text": (m.group(1) or m.group(2) or "").strip()}

        # getByAltText('X')
        m = re.match(r"page\.getByAltText\(\s*" + self._STR, locator_expr)
        if m:
            alt = (m.group(1) or m.group(2) or "").strip()
            return {"selector": f'[alt="{_esc(alt)}"]'}

        # getByTitle('X')
        m = re.match(r"page\.getByTitle\(\s*" + self._STR, locator_expr)
        if m:
            title = (m.group(1) or m.group(2) or "").strip()
            return {"selector": f'[title="{_esc(title)}"]'}

        # locator('X')
        m = re.match(r"page\.locator\(\s*" + self._STR, locator_expr)
        if m:
            sel = (m.group(1) or m.group(2) or "").strip()
            return {"selector": sel}

        return {}

    # ── locator + action (main path) ──────────────────────────────────────────

    def _parse_locator_action(self, stmt: str) -> Optional[Dict[str, Any]]:
        """
        Parse `page.getBy*(...).action(...)` or `page.locator(...).action(...)`.
        """
        # Split into locator part and action part
        locator_expr, action_expr = self._split_locator_action(stmt)
        if not locator_expr or not action_expr:
            return None

        fields = self._extract_locator_fields(locator_expr)
        if not fields:
            return None

        return self._apply_action(fields, action_expr)

    def _split_locator_action(self, stmt: str) -> Tuple[str, str]:
        """
        Split `page.getByLabel('x').fill('y')` into
        ('page.getByLabel(\'x\')', '.fill(\'y\')')

        Handles nested parentheses so `page.locator('a:has(b)')` doesn't break.
        """
        # Find where the first top-level `.getBy*` or `.locator` call ends
        # and the action chain begins.
        # Strategy: find the first method call on page, track parens depth.
        # Pattern: page.<method>(...).<action>(...)

        i = 0
        # skip "page."
        if not stmt.startswith("page."):
            return "", ""
        i = 5  # len("page.")

        # Read method name
        m = re.match(r"(\w+)\(", stmt[i:])
        if not m:
            return "", ""
        method_name = m.group(1)
        i += m.start()

        # Find matching closing paren
        i = stmt.index("(", i)
        depth = 0
        j = i
        while j < len(stmt):
            if stmt[j] == "(":
                depth += 1
            elif stmt[j] == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1

        locator_expr = stmt[:j]
        rest = stmt[j:]  # should start with .<action>(...)

        # Handle optional .filter(...) / .nth(...) — skip, just grab the last method chain
        # For simplicity, take the last method call as the action
        # Remove any .filter() / .nth() / .first() / .last() prefixes
        rest_clean = re.sub(r"\.(filter|nth|first|last)\([^)]*\)", "", rest)

        return locator_expr, rest_clean.strip()

    def _apply_action(
        self, fields: Dict[str, Any], action_expr: str
    ) -> Optional[Dict[str, Any]]:
        """Map `.action(args)` string + selector fields → Easy BDD step dict."""
        action_expr = action_expr.lstrip(".")

        # .click()  .dblclick()
        if re.match(r"click\(", action_expr):
            return {"browser.click": fields}
        if re.match(r"dblclick\(", action_expr):
            # browser.double_click only understands selector (not role/name/label)
            return {"browser.double_click": {"selector": self._fields_to_selector(fields)}}

        # .fill('value')
        m = re.match(r"fill\(\s*" + self._STR, action_expr)
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            return {"browser.fill": {**fields, "value": val}}

        # .type('value')  (older Playwright API)
        m = re.match(r"type\(\s*" + self._STR, action_expr)
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            return {"browser.fill": {**fields, "value": val}}

        # .clear()  — Easy BDD has no clear action; fill with empty value
        if re.match(r"clear\(", action_expr):
            return {"browser.fill": {**fields, "value": ""}}

        # .check()  .uncheck()
        if re.match(r"check\(", action_expr):
            return {"browser.click": fields}  # Easy BDD: click toggles checkboxes
        if re.match(r"uncheck\(", action_expr):
            return {"browser.click": fields}

        # .selectOption('value')  — browser.select requires a selector string
        m = re.match(r"selectOption\(\s*" + self._STR, action_expr)
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            return {"browser.select": {
                "selector": self._fields_to_selector(fields),
                "value": val,
            }}

        # .press('key')
        m = re.match(r"press\(\s*" + self._STR, action_expr)
        if m:
            key = (m.group(1) or m.group(2) or "").strip()
            return {"browser.press_key": {**fields, "key": key}}

        # .hover()
        if re.match(r"hover\(", action_expr):
            return {"browser.hover": fields}

        # .focus()
        if re.match(r"focus\(", action_expr):
            return {"browser.click": fields}

        # .scrollIntoViewIfNeeded()
        if re.match(r"scrollIntoViewIfNeeded\(", action_expr):
            return None  # skip — not a meaningful test step

        # .screenshot()
        if re.match(r"screenshot\(", action_expr):
            return {"browser.screenshot": {"name": "element_screenshot"}}

        # .waitFor()
        if re.match(r"waitFor\(", action_expr):
            state = "visible"
            sm = re.search(r"state\s*:\s*['\"](\w+)['\"]", action_expr)
            if sm:
                state = sm.group(1)
            return {"browser.wait_for": {"selector": self._fields_to_selector(fields), "state": state}}

        return None

    # ── frameLocator ──────────────────────────────────────────────────────────

    def _parse_frame_action(self, stmt: str) -> Optional[Dict[str, Any]]:
        """
        Handle `page.frameLocator('iframe#id').getBy*(...).action(...)`.
        Converts to Easy BDD `selector: 'iframe#id >> <inner_selector>'`.
        """
        m = re.match(r"page\.frameLocator\(\s*" + self._STR + r"\s*\)\.", stmt)
        if not m:
            return None
        frame_sel = (m.group(1) or m.group(2) or "").strip()
        inner_stmt = "page." + stmt[m.end():]
        inner = self._parse_locator_action(inner_stmt)
        if not inner:
            return None

        # Inject iframe prefix into the selector fields
        action_key = next(iter(inner))
        params = inner[action_key]
        if isinstance(params, dict):
            # Build a combined selector using the iframe prefix syntax
            if params.get("role") and params.get("name"):
                inner_sel = f'role={params["role"]}[name="{_esc(params["name"])}"]'
            elif params.get("selector"):
                inner_sel = params["selector"]
            elif params.get("label"):
                inner_sel = f'[aria-label="{_esc(params["label"])}"]'
            elif params.get("text"):
                inner_sel = f'text="{_esc(params["text"])}"'
            else:
                inner_sel = str(params)

            combined = f"{frame_sel} >> {inner_sel}"
            new_params = {"selector": combined}
            # Keep value if present (for fill steps)
            if "value" in params:
                new_params["value"] = params["value"]
            if "key" in params:
                new_params["key"] = params["key"]
            return {action_key: new_params}

        return inner


# ── Chrome DevTools Recorder JSON converter (enhanced) ───────────────────────

class CrxJsonConverter:
    """
    Converts Chrome DevTools Recorder JSON exports to Easy BDD YAML.
    Delegates to the existing RecorderConverter for step parsing, but
    adds support for missing step types and handles the full selectors array.
    """

    def convert(self, data: Dict[str, Any], filename: str = "recording") -> Dict[str, Any]:
        from ..core.recorder_converter import RecorderConverter
        rc = RecorderConverter()
        path = Path(filename)
        return rc._convert_chrome_devtools_recording(data, path)  # type: ignore[attr-defined]


# ── Public API ────────────────────────────────────────────────────────────────

def convert_crx_file(
    input_path: str,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> str:
    """
    Read a Playwright TS/JS/JSON recording file, convert to Easy BDD YAML,
    optionally write to disk, and return the YAML string.

    Args:
        input_path:  Path to the source file (.ts / .js / .py / .json)
        output_path: Explicit output file path (overrides output_dir)
        output_dir:  Directory to write <stem>.yaml into (default: same dir as input)

    Returns:
        YAML string
    """
    src = Path(input_path)
    raw = src.read_text(encoding="utf-8")
    suffix = src.suffix.lower()

    if suffix in (".ts", ".js"):
        data = PlaywrightTsConverter().convert(raw, filename=src.stem)
    elif suffix == ".py":
        # Python codegen — route through existing converter
        from ..core.recorder_converter import RecorderConverter
        data = RecorderConverter().convert_playwright_native_code(raw)
        data.setdefault("name", src.stem.replace("_", " ").title())
    elif suffix == ".json":
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Could not parse {src.name} as JSON: {e}") from e
        data = CrxJsonConverter().convert(parsed, filename=src.stem)
    else:
        raise ValueError(
            f"Unsupported file extension '{suffix}'. "
            "Supported: .ts, .js, .py, .json"
        )

    yaml_text = _to_yaml(data)

    # Write output file
    if output_path:
        dest = Path(output_path)
    elif output_dir:
        dest = Path(output_dir) / f"{src.stem}_converted.yaml"
    else:
        dest = src.parent / f"{src.stem}_converted.yaml"

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml_text, encoding="utf-8")
    print(f"[convert-crx] Written → {dest}")

    return yaml_text


def _to_yaml(data: Dict[str, Any]) -> str:
    """
    Serialize test data dict to Easy BDD dot-notation YAML.

    The dot-notation keys (e.g. `browser.click`) must be written as
    block-mapping keys, not quoted strings.  PyYAML handles this correctly
    when the key string contains only word chars and dots.
    """
    return yaml.dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )


# ── CLI entry point (called from __main__.py) ─────────────────────────────────

def cli_convert_crx(args) -> int:
    """
    Implements `python -m easybdd crawler convert-crx <file>`.
    """
    import sys

    input_files: List[str] = args.input_files
    output_dir: Optional[str] = getattr(args, "output", None)

    ok = 0
    fail = 0
    for input_file in input_files:
        try:
            convert_crx_file(
                input_file,
                output_dir=output_dir,
            )
            ok += 1
        except Exception as e:
            print(f"[convert-crx] ERROR {input_file}: {e}", file=sys.stderr)
            fail += 1

    if ok:
        print(f"\n[convert-crx] Converted {ok} file(s) successfully.")
    return 0 if fail == 0 else 1
