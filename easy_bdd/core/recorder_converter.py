import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class RecorderConverter:
    """Convert UI recorder formats to Easy BDD YAML format"""

    def __init__(self):
        self.converters = {
            "playwright": self._convert_playwright_recording,
            "codegen": self.convert_playwright_native_code,
            "selenium": self._convert_selenium_recording,
            "cypress": self._convert_cypress_recording,
            "puppeteer": self._convert_puppeteer_recording,
            "katalon": self._convert_katalon_recording,
            "chrome-devtools": self._convert_chrome_devtools_recording,
        }

    def convert_playwright_native_code(self, code: str) -> Dict[str, Any]:
        """Convert Playwright native code to Easy BDD YAML format"""
        steps = []
        lines = code.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            step = self._parse_playwright_line(line)
            if step:
                steps.extend(self._finalise_step(step))

        return {
            "name": "Playwright Native API Test",
            "description": "Converted from Playwright native API code",
            "tags": ["browser", "playwright", "native-api"],
            "steps": steps,
        }

    def _finalise_step(self, step: Dict[str, Any]) -> list:
        """Upgrade selectors to role-based then convert to browser.xxx format.

        Returns a list of [test.log entry, browser.xxx step] so callers can
        extend() rather than append() the result.
        """
        step = self.upgrade_step_to_role_selector(step)
        browser_step = self._to_browser_step(step)

        # Build a human-readable log message from the step params
        action_key = next(iter(browser_step)) if isinstance(browser_step, dict) else None
        if action_key:
            params = browser_step.get(action_key) or {}
            if isinstance(params, dict):
                detail_parts = []
                for k in ("name", "label", "role", "selector", "text", "url", "value"):
                    if k in params:
                        detail_parts.append(f"{k}={params[k]!r}")
                detail = ", ".join(detail_parts) if detail_parts else ""
                msg = f"{action_key}({detail})" if detail else action_key
            else:
                msg = action_key
            log_step = {"test.log": {"message": msg}}
            return [log_step, browser_step]

        return [browser_step]

    def _to_browser_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a flat {action: '...', param: ...} dict to the easy_bdd
        nested browser.xxx format:
          {browser.open: {url: ...}}
          {browser.click: {role: button, name: Save}}
          {browser.fill: {label: Email, value: user@test.com}}
        """
        action = step.get("action", "")
        params = {k: v for k, v in step.items() if k not in ("action", "description")}

        ACTION_MAP = {
            "Open browser":    "browser.open",
            "Click element":   "browser.click",
            "Double click":    "browser.click",
            "Fill form field": "browser.fill",
            "Hover":           "browser.hover",
            "Press key":       "browser.press_key",
            "Wait for element":"browser.wait_for_element",
            "Take screenshot": "browser.screenshot",
            "Verify text":     "browser.verify_text",
            "Select option":   "browser.select_option",
            "Scroll":          "browser.scroll",
            "Switch frame":    "browser.switch_frame",
            "Clear field":     "browser.clear",
            "Drag and drop":   "browser.drag_and_drop",
        }

        browser_action = ACTION_MAP.get(action)
        if browser_action:
            return {browser_action: params} if params else {browser_action: None}
        # Unknown action — pass through unchanged
        return step

    def _parse_playwright_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse individual Playwright code line to Easy BDD step"""
        # Skip boilerplate lines from sync/async script wrappers
        skip_prefixes = (
            "import ", "from ", "def ", "async def ", "with ", "browser =",
            "context =", "page =", "run(", "playwright =", "#", "expect(",
        )
        stripped = line.strip()
        if any(stripped.startswith(p) for p in skip_prefixes):
            return None

        # Remove optional 'await' and 'page.' prefix (handles both sync and async codegen output)
        line = re.sub(r"^\s*(?:await\s+)?page\.", "", stripped)
        line = line.rstrip(";")

        # Parse different Playwright methods

        # goto(url)
        if match := re.match(r'goto\(["\']([^"\']*)["\'](.*?)\)', line):
            return {
                "action": "Open browser",
                "url": match.group(1),
                "description": f"Navigate to {match.group(1)}",
            }

        # get_by_role(role, name=name).click()
        if match := re.match(
            r'get_by_role\(["\']([^"\']*)["\'](.*?)name\s*=\s*["\']([^"\']*)["\'](.*?)\.click\(\)',
            line,
        ):
            return {
                "action": "Click element",
                "role": match.group(1),
                "name": match.group(3),
            }

        # get_by_role(role, name=name).fill(value)
        if match := re.match(
            r'get_by_role\(["\']([^"\']*)["\'](.*?)name\s*=\s*["\']([^"\']*)["\'](.*?)\.fill\(["\']([^"\']*)["\']\)',
            line,
        ):
            return {
                "action": "Fill form field",
                "role": match.group(1),
                "name": match.group(3),
                "value": match.group(5),
            }

        # get_by_role(role).click() — no name
        if match := re.match(
            r'get_by_role\(["\']([^"\']*)["\'](?!\s*,\s*name)\s*\)\.click\(\)',
            line,
        ):
            return {
                "action": "Click element",
                "role": match.group(1),
            }

        # get_by_text(text).click()
        if match := re.match(r'get_by_text\(["\']([^"\']*)["\'](.*?)\.click\(\)', line):
            return {
                "action": "Click element",
                "text": match.group(1),
            }

        # get_by_label(label).fill(value)
        if match := re.match(
            r'get_by_label\(["\']([^"\']*)["\'](.*?)\.fill\(["\']([^"\']*)["\'](.*?)\)',
            line,
        ):
            return {
                "action": "Fill form field",
                "label": match.group(1),
                "value": match.group(3),
            }

        # get_by_label(label).click()
        if match := re.match(r'get_by_label\(["\']([^"\']*)["\'](.*?)\.click\(\)', line):
            return {
                "action": "Click element",
                "label": match.group(1),
            }

        # get_by_placeholder(placeholder).fill(value)
        if match := re.match(
            r'get_by_placeholder\(["\']([^"\']*)["\'](.*?)\.fill\(["\']([^"\']*)["\'](.*?)\)',
            line,
        ):
            return {
                "action": "Fill form field",
                "label": match.group(1),
                "value": match.group(3),
            }

        # click(selector)
        if match := re.match(r'click\(["\']([^"\']*)["\'](.*?)\)', line):
            return {
                "action": "Click element",
                "selector": match.group(1),
                "description": f"Click element: {match.group(1)}",
            }

        # fill(selector, value)
        if match := re.match(
            r'fill\(["\']([^"\']*)["\'](.*?)["\']([^"\']*)["\'](.*?)\)', line
        ):
            return {
                "action": "Fill form field",
                "field": match.group(1),
                "value": match.group(3),
                "description": f"Fill {match.group(1)} with {match.group(3)}",
            }

        # hover(selector)
        if match := re.match(r'hover\(["\']([^"\']*)["\'](.*?)\)', line):
            return {
                "action": "Hover",
                "selector": match.group(1),
                "description": f"Hover over: {match.group(1)}",
            }

        # dblclick(selector)
        if match := re.match(r'dblclick\(["\']([^"\']*)["\'](.*?)\)', line):
            return {
                "action": "Double click",
                "selector": match.group(1),
                "description": f"Double-click: {match.group(1)}",
            }

        # press(selector, key)
        if match := re.match(
            r'press\(["\']([^"\']*)["\'](.*?)["\']([^"\']*)["\'](.*?)\)', line
        ):
            return {
                "action": "Press key",
                "selector": match.group(1),
                "key": match.group(3),
                "description": f"Press {match.group(3)} in {match.group(1)}",
            }

        # wait_for_selector(selector)
        if match := re.match(r'wait_for_selector\(["\']([^"\']*)["\'](.*?)\)', line):
            return {
                "action": "Wait for element",
                "selector": match.group(1),
                "state": "visible",
                "description": f"Wait for element: {match.group(1)}",
            }

        # expect(locator).to_contain_text(text)
        if match := re.match(
            r'expect\(.*?locator\(["\']([^"\']*)["\'](.*?)\)\.to_contain_text\(["\']([^"\']*)["\'](.*?)\)',
            line,
        ):
            return {
                "action": "Verify text",
                "text": match.group(3),
                "description": f"Verify text: {match.group(3)}",
            }

        # screenshot()
        if "screenshot" in line:
            return {
                "action": "Take screenshot",
                "name": "recorded_screenshot",
                "description": "Take screenshot",
            }

        return None

    def _css_selector_to_role(self, selector: str) -> Optional[Tuple[str, str]]:
        """
        Try to extract (role, name) from a CSS selector.
        Returns None if the selector can't be safely mapped to a role.
        Examples:
          "button:has-text('Save')"  → ("button", "Save")
          "input[type='submit'][value='OK']" → ("button", "OK")
          "a:has-text('Home')" → ("link", "Home")
        """
        if not selector or selector.startswith("//") or selector.startswith("xpath="):
            return None

        # button with has-text
        m = re.match(r'^button:has-text\(["\']([^"\']+)["\']\)', selector, re.I)
        if m:
            return ("button", m.group(1))

        # input[type=submit] with value
        m = re.search(r'\[type=["\']?submit["\']?\]', selector, re.I)
        if m:
            v = re.search(r'\[value=["\']([^"\']+)["\']\]', selector)
            if v:
                return ("button", v.group(1))

        # input[type=button] with value
        m = re.search(r'\[type=["\']?button["\']?\]', selector, re.I)
        if m:
            v = re.search(r'\[value=["\']([^"\']+)["\']\]', selector)
            if v:
                return ("button", v.group(1))

        # link with has-text
        m = re.match(r'^a:has-text\(["\']([^"\']+)["\']\)', selector, re.I)
        if m:
            return ("link", m.group(1))

        # [role="button"] with has-text
        m = re.search(r'\[role=["\']button["\']\].*?:has-text\(["\']([^"\']+)["\']\)', selector, re.I)
        if m:
            return ("button", m.group(1))

        return None

    def _selector_to_label(self, selector: str) -> Optional[str]:
        """
        Try to extract a label/placeholder string from a CSS selector for fill steps.
        Returns None if no label can be safely extracted.
        """
        if not selector or selector.startswith("//") or selector.startswith("xpath="):
            return None

        # [aria-label="..."]
        m = re.search(r'\[aria-label=["\']([^"\']+)["\']\]', selector)
        if m:
            return m.group(1)

        # [placeholder="..."]
        m = re.search(r'\[placeholder=["\']([^"\']+)["\']\]', selector)
        if m:
            return m.group(1)

        return None

    def upgrade_step_to_role_selector(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upgrade a step's CSS selector to a role/label-based equivalent where possible.
        Returns a (possibly modified) copy of the step.
        Steps that already use role/label/text are returned unchanged.
        """
        if step.get("role") or step.get("label") or step.get("text"):
            return step

        upgraded = dict(step)
        action = step.get("action", "")
        is_fill = any(kw in action.lower() for kw in ("fill", "type", "input"))
        selector = step.get("selector") or (step.get("field") if is_fill else None)

        if not selector:
            return step

        if is_fill:
            label = self._selector_to_label(selector)
            if label:
                upgraded.pop("selector", None)
                upgraded.pop("field", None)
                upgraded["label"] = label
                return upgraded
        else:
            role_info = self._css_selector_to_role(selector)
            if role_info:
                upgraded.pop("selector", None)
                upgraded["role"] = role_info[0]
                upgraded["name"] = role_info[1]
                return upgraded

        return step

    # ------------------------------------------------------------------ #
    # Chrome DevTools Recorder                                            #
    # ------------------------------------------------------------------ #

    def _convert_chrome_devtools_recording(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Convert Chrome DevTools Recorder JSON export."""
        test_name = data.get("title", file_path.stem.replace("_", " ").title())
        steps = []
        variables = {}

        for raw in data.get("steps", []):
            step = self._convert_chrome_devtools_step(raw, variables)
            if step:
                steps.extend(self._finalise_step(step))

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "chrome-devtools"],
            "variables": variables,
            "steps": steps,
        }

    def _chrome_best_selector(self, selectors) -> Optional[str]:
        """
        Pick the most semantic selector from a Chrome DevTools selectors list.
        Chrome exports selectors as a list of lists, e.g.:
          [["aria/Submit Button"], ["#submit"], [".btn-submit"]]
        Preference: aria/ > text/ > CSS.
        """
        if not selectors:
            return None
        flat = [s[0] if isinstance(s, list) and s else s for s in selectors]
        for sel in flat:
            if isinstance(sel, str) and sel.startswith("aria/"):
                return sel
        for sel in flat:
            if isinstance(sel, str) and sel.startswith("text/"):
                return sel
        return flat[0] if flat else None

    def _aria_selector_to_step_fields(self, selector: str, action: str) -> Dict[str, Any]:
        """
        Convert an aria/ selector to role/label/text step fields.
        'aria/Submit'       → role=button name=Submit  (if action implies click)
        'aria/Email'        → label=Email              (if action implies fill)
        """
        label = selector[len("aria/"):]
        is_fill = action in ("change", "fill", "type")
        if is_fill:
            return {"label": label}
        # Default to role=button for interactive actions; callers can override
        return {"role": "button", "name": label}

    def _convert_chrome_devtools_step(
        self, raw: Dict[str, Any], variables: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        step_type = raw.get("type", "")

        if step_type == "navigate":
            url = raw.get("url", "")
            if url and "base_url" not in variables:
                variables["base_url"] = self._extract_base_url(url)
            return {"action": "Open browser", "url": url}

        if step_type in ("click", "doubleClick"):
            sel = self._chrome_best_selector(raw.get("selectors", []))
            step: Dict[str, Any] = {"action": "Double click" if step_type == "doubleClick" else "Click element"}
            if sel and sel.startswith("aria/"):
                step.update(self._aria_selector_to_step_fields(sel, "click"))
            elif sel and sel.startswith("text/"):
                step["text"] = sel[len("text/"):]
            elif sel:
                step["selector"] = sel
            return step

        if step_type == "change":
            sel = self._chrome_best_selector(raw.get("selectors", []))
            value = raw.get("value", "")
            step = {"action": "Fill form field", "value": value}
            if sel and sel.startswith("aria/"):
                step.update(self._aria_selector_to_step_fields(sel, "change"))
            elif sel:
                step["field"] = sel
            return step

        if step_type == "select":
            sel = self._chrome_best_selector(raw.get("selectors", []))
            value = raw.get("value", "")
            step: Dict[str, Any] = {"action": "Select option", "value": value}
            if sel and sel.startswith("aria/"):
                step["label"] = sel[len("aria/"):]
            elif sel:
                step["selector"] = sel
            return step

        if step_type == "keyDown":
            key = raw.get("key", "")
            return {"action": "Press key", "key": key}

        if step_type == "scroll":
            return {
                "action": "Scroll",
                "x": raw.get("x", 0),
                "y": raw.get("y", 0),
                "description": f"Scroll to ({raw.get('x', 0)}, {raw.get('y', 0)})",
            }

        if step_type == "waitForElement":
            sel = self._chrome_best_selector(raw.get("selectors", []))
            step = {"action": "Wait for element", "state": raw.get("visible", True) and "visible" or "hidden"}
            if sel and sel.startswith("aria/"):
                step["label"] = sel[len("aria/"):]
            elif sel:
                step["selector"] = sel
            return step

        if step_type == "waitForExpression":
            return {
                "action": "Wait",
                "condition": raw.get("expression", ""),
                "timeout": raw.get("timeout", 5000),
            }

        if step_type in ("hover", "mouseMove"):
            sel = self._chrome_best_selector(raw.get("selectors", []))
            step = {"action": "Hover"}
            if sel:
                step["selector"] = sel
            return step

        if step_type == "setViewport":
            return None  # Skip viewport steps — handled by config

        if step_type == "screenshot":
            return {"action": "Take screenshot", "name": raw.get("name", "screenshot")}

        return None

    # ------------------------------------------------------------------ #
    # Format detection                                                     #
    # ------------------------------------------------------------------ #

    def detect_format(self, data: Dict[str, Any]) -> Optional[str]:
        """Detect the UI recorder format"""

        # Chrome DevTools Recorder — has "title" + "steps" where steps have "type" and "selectors"
        if (
            isinstance(data, dict)
            and "title" in data
            and "steps" in data
            and isinstance(data.get("steps"), list)
            and data["steps"]
            and isinstance(data["steps"][0], dict)
            and "type" in data["steps"][0]
            and (
                "selectors" in data["steps"][0]
                or data["steps"][0].get("type") in ("navigate", "setViewport")
            )
        ):
            return "chrome-devtools"

        # Playwright Test Generator format
        if "actions" in data and isinstance(data.get("actions"), list):
            actions = data["actions"]
            if actions and isinstance(actions[0], dict):
                # Check for Playwright action types
                action_types = {
                    action.get("type", "")
                    for action in actions
                    if isinstance(action, dict)
                }
                if action_types & {"goto", "click", "fill", "press", "wait"}:
                    return "playwright"
            # Also check for Playwright code strings
            elif any(
                "page.click" in str(action) or "page.fill" in str(action)
                for action in actions
            ):
                return "playwright"

        # Playwright Codegen format (raw code)
        if isinstance(data, dict) and "steps" in data:
            steps = data.get("steps", [])
            if any("await page." in str(step) for step in steps):
                return "codegen"

        # Selenium IDE format
        if "tests" in data and "commands" in str(data):
            return "selenium"

        # Puppeteer format
        if "steps" in data and any(
            "page.goto" in str(step) for step in data.get("steps", [])
        ):
            return "puppeteer"

        # Cypress format
        if "commands" in data or any("cy." in str(data) for key in data):
            return "cypress"

        # Katalon format (array of command objects)
        if (
            isinstance(data, list)
            and data
            and all(
                isinstance(cmd, dict) and "command" in cmd and "target" in cmd
                for cmd in data
            )
        ):
            return "katalon"

        return None

    def convert(
        self, data: Dict[str, Any], format_name: str, file_path: Path
    ) -> Dict[str, Any]:
        """Convert recorder format to Easy BDD format"""
        if format_name in self.converters:
            return self.converters[format_name](data, file_path)
        raise ValueError(f"Unsupported recorder format: {format_name}")

    def convert_file(self, input_path: str, format_type: str = "auto") -> str:
        """
        Read a recorder file, auto-detect its format, convert to Easy BDD YAML,
        and return the YAML string.  Supports JSON recorder exports and raw
        Playwright codegen .py files.
        """
        import json
        import yaml

        file_path = Path(input_path)
        raw = file_path.read_text(encoding="utf-8")

        # Raw Python code (Playwright codegen output)
        if file_path.suffix == ".py" or (format_type == "auto" and raw.lstrip().startswith(("import", "from", "async", "def ", "with "))):
            test_data = self.convert_playwright_native_code(raw)
            return yaml.dump(test_data, default_flow_style=False, sort_keys=False, allow_unicode=True)

        # JSON-based recorder formats
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Could not parse {file_path.name} as JSON: {e}")

        if format_type == "auto":
            fmt = self.detect_format(data)
            if not fmt:
                raise ValueError(
                    f"Could not auto-detect recorder format for {file_path.name}. "
                    f"Use --format-type to specify: {', '.join(self.converters)}"
                )
        else:
            fmt = format_type

        test_data = self.convert(data, fmt, file_path)
        return yaml.dump(test_data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def _convert_playwright_recording(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Convert Playwright Test Generator recording"""

        test_name = data.get("name", file_path.stem.replace("_", " ").title())
        actions = data.get("actions", [])

        steps = []
        variables = {}

        for i, action in enumerate(actions):
            if isinstance(action, dict):
                step = self._convert_playwright_action(action, variables)
                if step:
                    steps.extend(self._finalise_step(step))
            elif isinstance(action, str):
                # Handle string-based actions
                step = self._parse_playwright_code_line(action, variables)
                if step:
                    steps.extend(self._finalise_step(step))

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "playwright"],
            "variables": variables,
            "steps": steps,
        }

    def _convert_playwright_action(
        self, action: Dict[str, Any], variables: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert individual Playwright action"""

        action_type = action.get("type", "")

        if action_type == "goto":
            url = action.get("url", "")
            if url and "base_url" not in variables:
                variables["base_url"] = self._extract_base_url(url)

            return {"action": "Open browser", "url": url}

        elif action_type == "click":
            selector = action.get("selector", "")
            text = action.get("text")

            if text:
                return {"action": "Click element", "text": text}
            else:
                return {"action": "Click element", "selector": selector}

        elif action_type == "fill":
            selector = action.get("selector", "")
            value = action.get("value", "")

            return {"action": "Fill form field", "field": selector, "value": value}

        elif action_type == "press":
            selector = action.get("selector", "")
            key = action.get("key", "")

            return {"action": "Press key", "selector": selector, "key": key}

        elif action_type == "wait":
            selector = action.get("selector", "")
            state = action.get("state", "visible")

            return {"action": "Wait for element", "selector": selector, "state": state}

        elif action_type == "screenshot":
            name = action.get("name", "screenshot")

            return {"action": "Take screenshot", "name": name}

        return None

    def _parse_playwright_code_line(
        self, code: str, variables: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Parse a single line of Playwright code"""

        return self._parse_playwright_line(code)

    def _extract_base_url(self, url: str) -> str:
        """Extract base URL from full URL"""

        from urllib.parse import urlparse

        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _extract_field_name(self, selector: str) -> str:
        """Extract field name from CSS selector"""
        # Match #id or [name="name"]
        if match := re.search(r"#(\w+)", selector):
            return match.group(1)
        elif match := re.search(r'\[name=["\'](\w+)["\']\]', selector):
            return match.group(1)
        elif match := re.search(r'\[id=["\'](\w+)["\']\]', selector):
            return match.group(1)

        return selector

    def _convert_selenium_recording(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Convert Selenium IDE recording"""

        test_name = data.get("name", file_path.stem.replace("_", " ").title())
        tests = data.get("tests", [])
        commands = []

        if tests:
            # Get commands from first test
            first_test = tests[0] if isinstance(tests, list) else tests
            commands = first_test.get("commands", [])

        steps = []
        for cmd in commands:
            step = self._convert_selenium_command(cmd)
            if step:
                steps.extend(self._finalise_step(step))

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "selenium"],
            "steps": steps,
        }

    def _selenium_target_to_selector(self, target: str) -> Dict[str, Any]:
        """
        Convert a Selenium IDE target (e.g. 'css=#btn', 'xpath=//button', 'id=submit',
        'linkText=Home', 'name=email') to an easy_bdd selector field dict.
        Prefers role/label/text over raw CSS where possible.
        """
        if not target:
            return {}
        if target.startswith("linkText="):
            return {"role": "link", "name": target[len("linkText="):]}
        if target.startswith("partialLinkText="):
            return {"text": target[len("partialLinkText="):]}
        if target.startswith("name="):
            return {"selector": f"[name='{target[len('name='):]}']"}
        if target.startswith("id="):
            return {"selector": f"#{target[len('id='):]}"}
        if target.startswith("css="):
            return {"selector": target[len("css="):]}
        if target.startswith("xpath="):
            return {"selector": target[len("xpath="):]}
        if target.startswith("label="):
            return {"label": target[len("label="):]}
        # Bare selector — pass through
        return {"selector": target}

    def _convert_selenium_command(
        self, cmd: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert Selenium IDE command"""

        command = cmd.get("command", "").lower().strip()
        target = cmd.get("target", "")
        value = cmd.get("value", "")

        # Navigation
        if command == "open":
            return {"action": "Open browser", "url": target}
        if command in ("goto", "navigateto"):
            return {"action": "Open browser", "url": target}

        # Clicks
        if command == "click":
            return {"action": "Click element", **self._selenium_target_to_selector(target)}
        if command == "clickat":
            return {"action": "Click element", **self._selenium_target_to_selector(target)}
        if command == "doubleclick":
            return {"action": "Double click", **self._selenium_target_to_selector(target)}
        if command == "clickandwait":
            return {"action": "Click element", **self._selenium_target_to_selector(target)}

        # Typing / form
        if command in ("type", "sendkeys"):
            return {"action": "Fill form field", "value": value, **self._selenium_target_to_selector(target)}
        if command == "clear":
            return {"action": "Clear field", **self._selenium_target_to_selector(target)}
        if command == "select":
            return {"action": "Select option", "value": value, **self._selenium_target_to_selector(target)}
        if command == "check":
            return {"action": "Click element", **self._selenium_target_to_selector(target)}
        if command == "uncheck":
            return {"action": "Click element", **self._selenium_target_to_selector(target)}

        # Mouse
        if command in ("mouseover", "mouseoverat"):
            return {"action": "Hover", **self._selenium_target_to_selector(target)}
        if command == "draganddroptarget":
            return {"action": "Drag and drop", "source": target, "target": value}

        # Waiting
        if command == "waitforpagetoload":
            return {"action": "Wait", "timeout": int(value) if str(value).isdigit() else 5000}
        if command == "waitforelementpresent":
            return {"action": "Wait for element", "state": "attached", **self._selenium_target_to_selector(target)}
        if command == "waitforelementvisible":
            return {"action": "Wait for element", "state": "visible", **self._selenium_target_to_selector(target)}
        if command == "waitforelementnotvisible":
            return {"action": "Wait for element", "state": "hidden", **self._selenium_target_to_selector(target)}
        if command in ("pause", "wait"):
            return {"action": "Wait", "timeout": int(value) if str(value).isdigit() else int(target) if str(target).isdigit() else 1000}

        # Assertions / verification (converted to browser.get_text + assert)
        if command in ("asserttext", "verifytext"):
            return {"action": "Verify text", "text": value, **self._selenium_target_to_selector(target)}
        if command in ("asserttitle", "verifytitle"):
            return {"action": "Verify title", "title": target or value}
        if command in ("assertelementpresent", "verifyelementpresent"):
            return {"action": "Wait for element", "state": "attached", **self._selenium_target_to_selector(target)}
        if command in ("assertelementnotpresent", "verifyelementnotpresent"):
            return {"action": "Wait for element", "state": "detached", **self._selenium_target_to_selector(target)}

        # Screenshots / misc
        if command == "capturescreenshotandwait":
            return {"action": "Take screenshot", "name": target or "screenshot"}
        if command in ("echo", "log"):
            return {"action": "test.print", "value": target}
        if command == "store":
            return {"action": "test.print", "value": f"store: {target} → {value}"}

        # Frames / windows
        if command == "selectframe":
            return {"action": "Switch frame", "selector": target}
        if command in ("selectwindow", "selectpopup"):
            return None  # Window switching not directly mappable

        # Scroll
        if command == "scrollto":
            return {"action": "Scroll", "selector": target}

        return None

    def _convert_cypress_recording(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Convert Cypress recording"""

        test_name = data.get("name", file_path.stem.replace("_", " ").title())
        commands = data.get("commands", [])

        steps = []
        for cmd in commands:
            step = self._convert_cypress_command(cmd)
            if step:
                steps.extend(self._finalise_step(step))

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "cypress"],
            "steps": steps,
        }

    def _convert_cypress_command(self, cmd: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Cypress command"""

        command = cmd.get("name", "").lower()
        selector = cmd.get("selector", "")
        text = cmd.get("text", "")

        if command == "visit":
            return {"action": "Open browser", "url": selector}
        elif command == "click":
            return {"action": "Click element", "selector": selector}
        elif command == "type":
            return {"action": "Fill form field", "field": selector, "value": text}

        return None

    def _convert_puppeteer_recording(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Convert Puppeteer recording"""

        test_name = data.get("name", file_path.stem.replace("_", " ").title())
        steps_data = data.get("steps", [])

        steps = []
        for step_data in steps_data:
            step = self._convert_puppeteer_step(step_data)
            if step:
                steps.extend(self._finalise_step(step))

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "puppeteer"],
            "steps": steps,
        }

    def _convert_puppeteer_step(
        self, step_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert Puppeteer step"""

        action = step_data.get("action", "").lower()
        selector = step_data.get("selector", "")
        value = step_data.get("value", "")

        if action == "goto":
            return {"action": "Open browser", "url": selector}
        elif action == "click":
            return {"action": "Click element", "selector": selector}
        elif action == "type":
            return {"action": "Fill form field", "field": selector, "value": value}

        return None

    def _convert_katalon_recording(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Convert Katalon recording"""

        test_name = file_path.stem.replace("_", " ").title()
        commands = data if isinstance(data, list) else []

        steps = []
        for cmd in commands:
            step = self._convert_katalon_command(cmd)
            if step:
                steps.extend(self._finalise_step(step))

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "katalon"],
            "steps": steps,
        }

    def _katalon_target_to_selector(self, target: str) -> Dict[str, Any]:
        """
        Convert a Katalon target string to easy_bdd selector fields.
        Katalon uses XPath or CSS preceded by 'xpath:' / 'css:' prefixes,
        or object repository names like 'Object Repository/Page_Login/btn_submit'.
        """
        if not target:
            return {}
        if target.startswith("xpath:"):
            return {"selector": target[len("xpath:"):]}
        if target.startswith("xpath="):
            return {"selector": target[len("xpath="):]}
        if target.startswith("css:"):
            return {"selector": target[len("css:"):]}
        if target.startswith("css="):
            return {"selector": target[len("css="):]}
        if target.startswith("//") or target.startswith("(//"):
            return {"selector": target}
        if target.startswith("id="):
            return {"selector": f"#{target[3:]}"}
        if target.startswith("name="):
            return {"selector": f"[name='{target[5:]}']"}
        if target.startswith("link="):
            return {"role": "link", "name": target[5:]}
        # Object repository path — use last segment as a hint
        if "/" in target:
            hint = target.rsplit("/", 1)[-1].replace("_", " ")
            return {"selector": target, "description": hint}
        return {"selector": target}

    def _convert_katalon_command(self, cmd: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Katalon Recorder command"""

        command = cmd.get("command", "").lower().strip()
        target = cmd.get("target", "")
        value = cmd.get("value", "")

        # Navigation
        if command == "openbrowser":
            return {"action": "Open browser", "url": target}
        if command in ("navigate", "navigateto"):
            return {"action": "Open browser", "url": target}

        # Clicks
        if command == "click":
            return {"action": "Click element", **self._katalon_target_to_selector(target)}
        if command == "clickat":
            return {"action": "Click element", **self._katalon_target_to_selector(target)}
        if command == "doubleclick":
            return {"action": "Double click", **self._katalon_target_to_selector(target)}
        if command == "rightclick":
            return {"action": "Click element", "button": "right", **self._katalon_target_to_selector(target)}

        # Text input
        if command in ("settext", "type", "sendkeys"):
            return {"action": "Fill form field", "value": value, **self._katalon_target_to_selector(target)}
        if command == "cleartext":
            return {"action": "Clear field", **self._katalon_target_to_selector(target)}
        if command == "settextandconfirm":
            return {"action": "Fill form field", "value": value, "press_enter": True, **self._katalon_target_to_selector(target)}

        # Select / checkbox
        if command in ("select", "selectoption"):
            return {"action": "Select option", "value": value, **self._katalon_target_to_selector(target)}
        if command == "check":
            return {"action": "Click element", **self._katalon_target_to_selector(target)}
        if command == "uncheck":
            return {"action": "Click element", **self._katalon_target_to_selector(target)}

        # Mouse
        if command in ("mouseover", "hovermouse"):
            return {"action": "Hover", **self._katalon_target_to_selector(target)}
        if command in ("draganddroptoelement", "draganddroptarget"):
            return {"action": "Drag and drop", "source": target, "target": value}

        # Waiting
        if command in ("waitforpagetoload", "waitforpageloadtimeout"):
            return {"action": "Wait", "timeout": int(value) if str(value).isdigit() else 5000}
        if command in ("waitforelement", "waitforelementpresent", "waitforelementvisible"):
            return {"action": "Wait for element", "state": "visible", **self._katalon_target_to_selector(target)}
        if command == "waitforelementtobeclickable":
            return {"action": "Wait for element", "state": "visible", **self._katalon_target_to_selector(target)}
        if command == "delay":
            return {"action": "Wait", "timeout": int(target) if str(target).isdigit() else 1000}

        # Assertions
        if command in ("verifytext", "asserttext"):
            return {"action": "Verify text", "text": value, **self._katalon_target_to_selector(target)}
        if command in ("verifyattribute", "assertattribute"):
            return {"action": "Verify text", "text": value, **self._katalon_target_to_selector(target)}
        if command in ("verifyelementpresent", "assertelementpresent"):
            return {"action": "Wait for element", "state": "attached", **self._katalon_target_to_selector(target)}

        # Screenshots
        if command in ("takescreenshot", "capturescreenshot"):
            return {"action": "Take screenshot", "name": target or "screenshot"}

        # Scroll
        if command in ("scrolltoview", "scrolltoelement"):
            return {"action": "Scroll", **self._katalon_target_to_selector(target)}

        # Frames
        if command == "switchtoframe":
            return {"action": "Switch frame", **self._katalon_target_to_selector(target)}
        if command == "switchtodefaultcontent":
            return {"action": "Switch frame", "selector": "default"}

        # Keyboard
        if command in ("sendspecialkey", "presskey"):
            return {"action": "Press key", "key": value or target}

        return None
