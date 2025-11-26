from pathlib import Path
from typing import Any, Dict, Optional


class RecorderConverter:
    """Convert UI recorder formats to Easy BDD YAML format"""

    def __init__(self):
        self.converters = {
            "playwright": self._convert_playwright_recording,
            "codegen": self._convert_playwright_native_code,
            "selenium": self._convert_selenium_recording,
            "cypress": self._convert_cypress_recording,
            "puppeteer": self._convert_puppeteer_recording,
            "katalon": self._convert_katalon_recording,
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
                steps.append(step)

        return {
            "name": "Playwright Native API Test",
            "description": "Converted from Playwright native API code",
            "tags": ["browser", "playwright", "native-api"],
            "steps": steps,
        }

    def _parse_playwright_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse individual Playwright code line to Easy BDD step"""
        import re

        # Remove 'await' and 'page.' prefix
        line = re.sub(r"^\s*await\s+page\.", "", line)
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
                "action": "Get by role",
                "role": match.group(1),
                "name": match.group(3),
                "description": f"Click {match.group(1)} with name {match.group(3)}",
            }

        # get_by_text(text).click()
        if match := re.match(r'get_by_text\(["\']([^"\']*)["\'](.*?)\.click\(\)', line):
            return {
                "action": "Get by text",
                "text": match.group(1),
                "description": f"Click text: {match.group(1)}",
            }

        # get_by_label(label).fill(value)
        if match := re.match(
            r'get_by_label\(["\']([^"\']*)["\'](.*?)\.fill\(["\']([^"\']*)["\'](.*?)\)',
            line,
        ):
            return {
                "action": "Get by label",
                "label": match.group(1),
                "action_type": "fill",
                "value": match.group(3),
                "description": f"Fill field labeled {match.group(1)} with {match.group(3)}",
            }

        # get_by_placeholder(placeholder).fill(value)
        if match := re.match(
            r'get_by_placeholder\(["\']([^"\']*)["\'](.*?)\.fill\(["\']([^"\']*)["\'](.*?)\)',
            line,
        ):
            return {
                "action": "Get by placeholder",
                "placeholder": match.group(1),
                "action_type": "fill",
                "value": match.group(3),
                "description": f"Fill field with placeholder {match.group(1)}",
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

    def detect_format(self, data: Dict[str, Any]) -> Optional[str]:
        """Detect the UI recorder format"""

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
        else:
            raise ValueError(f"Unsupported recorder format: {format_name}")

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
                    steps.append(step)
            elif isinstance(action, str):
                # Handle string-based actions
                step = self._parse_playwright_code_line(action, variables)
                if step:
                    steps.append(step)

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

        # Try to extract name, id, or label from selector
        import re

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
                steps.append(step)

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "selenium"],
            "steps": steps,
        }

    def _convert_selenium_command(
        self, cmd: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert Selenium IDE command"""

        command = cmd.get("command", "").lower()
        target = cmd.get("target", "")
        value = cmd.get("value", "")

        if command == "open":
            return {"action": "Open browser", "url": target}
        elif command == "click":
            return {"action": "Click element", "selector": target}
        elif command == "type":
            return {"action": "Fill form field", "field": target, "value": value}
        elif command == "wait":
            return {
                "action": "Wait",
                "timeout": int(value) if value.isdigit() else 1000,
            }

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
                steps.append(step)

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
                steps.append(step)

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
                steps.append(step)

        return {
            "name": test_name,
            "description": f"Auto-generated from {file_path.name}",
            "tags": ["browser", "recorded", "katalon"],
            "steps": steps,
        }

    def _convert_katalon_command(self, cmd: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Katalon command"""

        command = cmd.get("command", "").lower()
        target = cmd.get("target", "")
        value = cmd.get("value", "")

        if command == "openbrowser":
            return {"action": "Open browser", "url": target}
        elif command == "click":
            return {"action": "Click element", "selector": target}
        elif command == "settext":
            return {"action": "Fill form field", "field": target, "value": value}

        return None
