"""
UI Recorder integration utilities for Easy BDD Framework
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
import json


class RecorderConverter:
    """Converts various UI recorder formats to Easy BDD format"""
    
    def __init__(self):
        self.converters = {
            'playwright': self._convert_playwright_recording,
            'selenium': self._convert_selenium_recording,
            'puppeteer': self._convert_puppeteer_recording,
            'cypress': self._convert_cypress_recording,
            'codegen': self._convert_playwright_codegen,
            'katalon': self._convert_katalon_recording
        }
    
    def convert_playwright_native_code(self, code: str) -> Dict[str, Any]:\n        \"\"\"Convert Playwright native code to Easy BDD YAML format\"\"\"\n        import re\n        \n        steps = []\n        lines = code.strip().split('\\n')\n        \n        for line in lines:\n            line = line.strip()\n            if not line or line.startswith('#'):\n                continue\n                \n            step = self._parse_playwright_line(line)\n            if step:\n                steps.append(step)\n        \n        return {\n            'name': 'Playwright Native API Test',\n            'description': 'Converted from Playwright native API code',\n            'tags': ['browser', 'playwright', 'native-api'],\n            'steps': steps\n        }\n    \n    def _parse_playwright_line(self, line: str) -> Optional[Dict[str, Any]]:\n        \"\"\"Parse individual Playwright code line to Easy BDD step\"\"\"\n        import re\n        \n        # Remove 'await' and 'page.' prefix\n        line = re.sub(r'^\\s*await\\s+page\\.', '', line)\n        line = line.rstrip(';')\n        \n        # Parse different Playwright methods\n        \n        # goto(url)\n        if match := re.match(r'goto\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Open browser',\n                'url': match.group(1),\n                'description': f'Navigate to {match.group(1)}'\n            }\n        \n        # get_by_role(role, name=name).click()\n        if match := re.match(r'get_by_role\\([\"\\']([^\"\\']*)[\"\\'](.*?)name\\s*=\\s*[\"\\']([^\"\\']*)[\"\\'](.*?)\\.click\\(\\)', line):\n            return {\n                'action': 'Get by role',\n                'role': match.group(1),\n                'name': match.group(3),\n                'description': f'Click {match.group(1)} with name {match.group(3)}'\n            }\n        \n        # get_by_text(text).click()\n        if match := re.match(r'get_by_text\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\.click\\(\\)', line):\n            return {\n                'action': 'Get by text',\n                'text': match.group(1),\n                'description': f'Click text: {match.group(1)}'\n            }\n        \n        # get_by_label(label).fill(value)\n        if match := re.match(r'get_by_label\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\.fill\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Get by label',\n                'label': match.group(1),\n                'action_type': 'fill',\n                'value': match.group(3),\n                'description': f'Fill field labeled {match.group(1)} with {match.group(3)}'\n            }\n        \n        # get_by_placeholder(placeholder).fill(value)\n        if match := re.match(r'get_by_placeholder\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\.fill\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Get by placeholder',\n                'placeholder': match.group(1),\n                'action_type': 'fill',\n                'value': match.group(3),\n                'description': f'Fill field with placeholder {match.group(1)}'\n            }\n        \n        # click(selector)\n        if match := re.match(r'click\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Click element',\n                'selector': match.group(1),\n                'description': f'Click element: {match.group(1)}'\n            }\n        \n        # fill(selector, value)\n        if match := re.match(r'fill\\([\"\\']([^\"\\']*)[\"\\'](.*?)[\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Fill form field',\n                'field': match.group(1),\n                'value': match.group(3),\n                'description': f'Fill {match.group(1)} with {match.group(3)}'\n            }\n        \n        # hover(selector)\n        if match := re.match(r'hover\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Hover',\n                'selector': match.group(1),\n                'description': f'Hover over: {match.group(1)}'\n            }\n        \n        # dblclick(selector)\n        if match := re.match(r'dblclick\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Double click',\n                'selector': match.group(1),\n                'description': f'Double-click: {match.group(1)}'\n            }\n        \n        # press(selector, key)\n        if match := re.match(r'press\\([\"\\']([^\"\\']*)[\"\\'](.*?)[\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Press key',\n                'selector': match.group(1),\n                'key': match.group(3),\n                'description': f'Press {match.group(3)} in {match.group(1)}'\n            }\n        \n        # wait_for_selector(selector)\n        if match := re.match(r'wait_for_selector\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Wait for element',\n                'selector': match.group(1),\n                'state': 'visible',\n                'description': f'Wait for element: {match.group(1)}'\n            }\n        \n        # expect(locator).to_contain_text(text)\n        if match := re.match(r'expect\\(.*?locator\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)\\.to_contain_text\\([\"\\']([^\"\\']*)[\"\\'](.*?)\\)', line):\n            return {\n                'action': 'Verify text',\n                'text': match.group(3),\n                'description': f'Verify text: {match.group(3)}'\n            }\n        \n        # screenshot()\n        if 'screenshot' in line:\n            return {\n                'action': 'Take screenshot',\n                'name': 'recorded_screenshot',\n                'description': 'Take screenshot'\n            }\n        \n        return None\n\n    def detect_format(self, data: Dict[str, Any]) -> Optional[str]:
        """Detect the UI recorder format"""
        
        # Playwright Test Generator format
        if 'actions' in data and isinstance(data.get('actions'), list):
            actions = data['actions']
            if actions and isinstance(actions[0], dict):
                # Check for Playwright action types
                action_types = {action.get('type', '')
                                for action in actions 
                                if isinstance(action, dict)}
                if action_types & {'goto', 'click', 'fill', 'press', 'wait'}:
                    return 'playwright'
            # Also check for Playwright code strings
            elif any('page.click' in str(action) or 
                     'page.fill' in str(action) 
                     for action in actions):
                return 'playwright'
        
        # Playwright Codegen format (raw code)
        if isinstance(data, dict) and 'steps' in data:
            steps = data.get('steps', [])
            if any('await page.' in str(step) for step in steps):
                return 'codegen'
        
        # Selenium IDE format
        if 'tests' in data and 'commands' in str(data):
            return 'selenium'
        
        # Puppeteer format
        if 'steps' in data and any('page.goto' in str(step) 
                                   for step in data.get('steps', [])):
            return 'puppeteer'
        
        # Cypress format
        if 'commands' in data or any('cy.' in str(data) for key in data):
            return 'cypress'
        
        # Katalon format (array of command objects)
        if isinstance(data, list) and data and all(
            isinstance(cmd, dict) and 'command' in cmd and 'target' in cmd 
            for cmd in data
        ):
            return 'katalon'
        
        return None
    
    def convert(self, data: Dict[str, Any], format_name: str, 
                file_path: Path) -> Dict[str, Any]:
        """Convert recorder format to Easy BDD format"""
        
        if format_name in self.converters:
            return self.converters[format_name](data, file_path)
        else:
            raise ValueError(f"Unsupported recorder format: {format_name}")
    
    def _convert_playwright_recording(self, data: Dict[str, Any], 
                                    file_path: Path) -> Dict[str, Any]:
        """Convert Playwright Test Generator recording"""
        
        test_name = data.get('name', file_path.stem.replace('_', ' ').title())
        actions = data.get('actions', [])
        
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
            'name': test_name,
            'description': f'Auto-generated from {file_path.name}',
            'tags': ['browser', 'recorded', 'playwright'],
            'variables': variables,
            'steps': steps
        }
    
    def _convert_playwright_action(self, action: Dict[str, Any], 
                                 variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert individual Playwright action"""
        
        action_type = action.get('type', '')
        
        if action_type == 'goto':
            url = action.get('url', '')
            if url and 'base_url' not in variables:
                variables['base_url'] = self._extract_base_url(url)
            
            return {
                'action': 'Open browser',
                'url': url
            }
        
        elif action_type == 'click':
            selector = action.get('selector', '')
            text = action.get('text')
            
            if text:
                return {
                    'action': 'Click element',
                    'text': text
                }
            else:
                return {
                    'action': 'Click element',
                    'selector': selector
                }
        
        elif action_type == 'fill':
            selector = action.get('selector', '')
            value = action.get('value', '')
            
            # Try to extract field name from selector
            field_name = self._extract_field_name(selector)
            
            return {
                'action': 'Fill form field',
                'field': field_name or selector,
                'value': value
            }
        
        elif action_type == 'type':
            selector = action.get('selector', '')
            text = action.get('text', '')
            
            field_name = self._extract_field_name(selector)
            
            return {
                'action': 'Fill form field',
                'field': field_name or selector,
                'value': text
            }
        
        elif action_type == 'press':
            key = action.get('key', '')
            if key.lower() == 'enter':
                return {
                    'action': 'Press key',
                    'key': 'Enter'
                }
        
        elif action_type == 'waitForSelector':
            selector = action.get('selector', '')
            return {
                'action': 'Wait for element',
                'selector': selector,
                'timeout': action.get('timeout', 30)
            }
        
        elif action_type == 'screenshot':
            return {
                'action': 'Take screenshot',
                'name': action.get('name', 'recorded_screenshot')
            }
        
        return None
    
    def _parse_playwright_code_line(self, code_line: str, 
                                   variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse Playwright code line into Easy BDD action"""
        
        code_line = code_line.strip()
        
        # Extract page.goto() calls
        if 'page.goto(' in code_line:
            url_start = code_line.find("'") or code_line.find('"')
            if url_start > 0:
                quote_char = code_line[url_start]
                url_end = code_line.find(quote_char, url_start + 1)
                if url_end > 0:
                    url = code_line[url_start + 1:url_end]
                    return {
                        'action': 'Open browser',
                        'url': url
                    }
        
        # Extract page.click() calls
        elif 'page.click(' in code_line:
            selector = self._extract_selector_from_code(code_line, 'click')
            if selector:
                return {
                    'action': 'Click element',
                    'selector': selector
                }
        
        # Extract page.fill() calls
        elif 'page.fill(' in code_line:
            parts = self._extract_fill_params(code_line)
            if parts:
                selector, value = parts
                field_name = self._extract_field_name(selector)
                return {
                    'action': 'Fill form field',
                    'field': field_name or selector,
                    'value': value
                }
        
        # Extract page.waitForSelector() calls
        elif 'page.waitForSelector(' in code_line:
            selector = self._extract_selector_from_code(code_line, 'waitForSelector')
            if selector:
                return {
                    'action': 'Wait for element',
                    'selector': selector
                }
        
        return None
    
    def _convert_selenium_recording(self, data: Dict[str, Any], 
                                  file_path: Path) -> Dict[str, Any]:
        """Convert Selenium IDE recording"""
        
        test_name = data.get('name', file_path.stem.replace('_', ' ').title())
        commands = []
        
        if 'tests' in data:
            # Selenium IDE format
            test_data = data['tests'][0] if data['tests'] else {}
            commands = test_data.get('commands', [])
        else:
            commands = data.get('commands', [])
        
        steps = []
        variables = {}
        
        for command in commands:
            step = self._convert_selenium_command(command, variables)
            if step:
                steps.append(step)
        
        return {
            'name': test_name,
            'description': f'Auto-generated from Selenium IDE recording',
            'tags': ['browser', 'recorded', 'selenium'],
            'variables': variables,
            'steps': steps
        }
    
    def _convert_selenium_command(self, command: Dict[str, Any], 
                                variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Selenium IDE command"""
        
        command_name = command.get('command', '')
        target = command.get('target', '')
        value = command.get('value', '')
        
        if command_name == 'open':
            return {
                'action': 'Open browser',
                'url': target
            }
        
        elif command_name == 'click':
            return {
                'action': 'Click element',
                'selector': target
            }
        
        elif command_name == 'type':
            field_name = self._extract_field_name(target)
            return {
                'action': 'Fill form field',
                'field': field_name or target,
                'value': value
            }
        
        elif command_name == 'assertText':
            return {
                'action': 'Verify page contains',
                'text': value
            }
        
        elif command_name == 'waitForElementPresent':
            return {
                'action': 'Wait for element',
                'selector': target
            }
        
        return None
    
    def _convert_cypress_recording(self, data: Dict[str, Any], 
                                 file_path: Path) -> Dict[str, Any]:
        """Convert Cypress recording"""
        
        commands = data.get('commands', [])
        steps = []
        variables = {}
        
        for command in commands:
            step = self._convert_cypress_command(command, variables)
            if step:
                steps.append(step)
        
        return {
            'name': data.get('name', file_path.stem.replace('_', ' ').title()),
            'description': 'Auto-generated from Cypress recording',
            'tags': ['browser', 'recorded', 'cypress'],
            'variables': variables,
            'steps': steps
        }
    
    def _convert_cypress_command(self, command: Dict[str, Any], 
                               variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Cypress command"""
        
        cmd_name = command.get('name', '')
        args = command.get('args', [])
        
        if cmd_name == 'visit' and args:
            return {
                'action': 'Open browser',
                'url': args[0]
            }
        
        elif cmd_name == 'click' and args:
            return {
                'action': 'Click element',
                'selector': args[0]
            }
        
        elif cmd_name == 'type' and len(args) >= 2:
            field_name = self._extract_field_name(args[0])
            return {
                'action': 'Fill form field',
                'field': field_name or args[0],
                'value': args[1]
            }
        
        return None
    
    def _convert_puppeteer_recording(self, data: Dict[str, Any], 
                                   file_path: Path) -> Dict[str, Any]:
        """Convert Puppeteer recording"""
        
        steps_data = data.get('steps', [])
        steps = []
        variables = {}
        
        for step_data in steps_data:
            step = self._convert_puppeteer_step(step_data, variables)
            if step:
                steps.append(step)
        
        return {
            'name': data.get('name', file_path.stem.replace('_', ' ').title()),
            'description': 'Auto-generated from Puppeteer recording',
            'tags': ['browser', 'recorded', 'puppeteer'],
            'variables': variables,
            'steps': steps
        }
    
    def _convert_puppeteer_step(self, step_data: Dict[str, Any], 
                              variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Puppeteer step"""
        
        action_type = step_data.get('type', '')
        
        if action_type == 'navigate':
            return {
                'action': 'Open browser',
                'url': step_data.get('url', '')
            }
        
        elif action_type == 'click':
            return {
                'action': 'Click element',
                'selector': step_data.get('selector', '')
            }
        
        elif action_type == 'type':
            field_name = self._extract_field_name(step_data.get('selector', ''))
            return {
                'action': 'Fill form field',
                'field': field_name or step_data.get('selector', ''),
                'value': step_data.get('text', '')
            }
        
        return None
    
    def _convert_katalon_recording(self, data: List[Dict[str, Any]], 
                                 file_path: Path) -> Dict[str, Any]:
        """Convert Katalon Studio recording (array of command objects)"""
        
        steps = []
        variables = {}
        
        # Extract base URL from first open command
        for command in data:
            if command.get('command') == 'open':
                target = command.get('target', '')
                if target:
                    variables['base_url'] = self._extract_base_url(target)
                break
        
        for command in data:
            step = self._convert_katalon_command(command, variables)
            if step:
                steps.append(step)
        
        return {
            'name': file_path.stem.replace('_', ' ').title(),
            'description': 'Auto-generated from Katalon Studio recording',
            'tags': ['browser', 'recorded', 'katalon'],
            'variables': variables,
            'steps': steps
        }
    
    def _convert_katalon_command(self, command: Dict[str, Any], 
                               variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert individual Katalon command"""
        
        cmd = command.get('command', '')
        target = command.get('target', '')
        value = command.get('value', '')
        
        if cmd == 'open':
            return {
                'action': 'Open browser',
                'url': target
            }
        
        elif cmd == 'click':
            return {
                'action': 'Click element',
                'selector': self._normalize_katalon_selector(target)
            }
        
        elif cmd == 'type':
            field_name = self._extract_katalon_field_name(target)
            return {
                'action': 'Fill form field',
                'field': field_name or self._normalize_katalon_selector(target),
                'value': value
            }
        
        elif cmd == 'waitForElementPresent':
            return {
                'action': 'Wait for element',
                'selector': self._normalize_katalon_selector(target),
                'timeout': 30
            }
        
        elif cmd == 'assertElementPresent':
            return {
                'action': 'Verify element exists',
                'selector': self._normalize_katalon_selector(target)
            }
        
        elif cmd == 'assertText':
            return {
                'action': 'Verify text',
                'text': value,
                'selector': self._normalize_katalon_selector(target) if target else None
            }
        
        return None
    
    def _normalize_katalon_selector(self, selector: str) -> str:
        """Normalize Katalon selector to standard CSS/XPath"""
        if not selector:
            return selector
            
        # Keep XPath selectors as-is
        if selector.startswith('xpath='):
            return selector[6:]  # Remove 'xpath=' prefix
        
        # Handle CSS selectors
        if selector.startswith('css='):
            return selector[4:]  # Remove 'css=' prefix
        
        # Handle ID selectors
        if selector.startswith('id='):
            return f"#{selector[3:]}"  # Convert to CSS ID selector
        
        # Handle name selectors
        if selector.startswith('name='):
            return f"[name='{selector[5]}']"  # Convert to CSS attribute selector
        
        # Return as-is if no prefix
        return selector
    
    def _extract_katalon_field_name(self, selector: str) -> Optional[str]:
        """Extract field name from Katalon selector"""
        
        # From name= selector
        if 'name=' in selector:
            if selector.startswith('name='):
                return selector[5:]
            # From xpath with name attribute
            if '@name=' in selector:
                start = selector.find('@name=') + 6
                if selector[start] in ['"', "'"]:
                    quote = selector[start]
                    end = selector.find(quote, start + 1)
                    if end > start:
                        return selector[start + 1:end]
        
        # From input[@value=...] patterns - extract the value as field identifier
        if '@value=' in selector:
            start = selector.find('@value=') + 7
            if selector[start] in ['"', "'"]:
                quote = selector[start]
                end = selector.find(quote, start + 1)
                if end > start:
                    field_value = selector[start + 1:end]
                    # Use the value as a field identifier (common in Katalon recordings)
                    return f"field_with_value_{field_value.replace('-', '_').lower()}"
        
        return None
    
    def _convert_playwright_codegen(self, data: Dict[str, Any], 
                                  file_path: Path) -> Dict[str, Any]:
        """Convert Playwright codegen output"""
        
        code_steps = data.get('steps', [])
        steps = []
        variables = {}
        
        for code_line in code_steps:
            step = self._parse_playwright_code_line(str(code_line), variables)
            if step:
                steps.append(step)
        
        return {
            'name': data.get('name', file_path.stem.replace('_', ' ').title()),
            'description': 'Auto-generated from Playwright codegen',
            'tags': ['browser', 'recorded', 'playwright-codegen'],
            'variables': variables,
            'steps': steps
        }
    
    # Helper methods
    def _extract_base_url(self, full_url: str) -> str:
        """Extract base URL from full URL"""
        if '://' in full_url:
            parts = full_url.split('/')
            return f"{parts[0]}//{parts[2]}"
        return full_url
    
    def _extract_field_name(self, selector: str) -> Optional[str]:
        """Extract field name from selector"""
        # Extract from name attribute: [name="email"] -> email
        if 'name=' in selector:
            start = selector.find('name=') + 5
            if selector[start] in ['"', "'"]:
                quote = selector[start]
                end = selector.find(quote, start + 1)
                if end > start:
                    return selector[start + 1:end]
        
        # Extract from id: #email -> email
        if selector.startswith('#'):
            return selector[1:]
        
        # Extract from data-testid
        if 'data-testid=' in selector:
            start = selector.find('data-testid=') + 12
            if selector[start] in ['"', "'"]:
                quote = selector[start]
                end = selector.find(quote, start + 1)
                if end > start:
                    return selector[start + 1:end]
        
        return None
    
    def _extract_selector_from_code(self, code_line: str, method_name: str) -> Optional[str]:
        """Extract selector from Playwright code line"""
        method_call = f'page.{method_name}('
        start = code_line.find(method_call)
        if start >= 0:
            start += len(method_call)
            if code_line[start] in ['"', "'"]:
                quote = code_line[start]
                end = code_line.find(quote, start + 1)
                if end > start:
                    return code_line[start + 1:end]
        return None
    
    def _extract_fill_params(self, code_line: str) -> Optional[tuple]:
        """Extract selector and value from page.fill() call"""
        start = code_line.find('page.fill(')
        if start >= 0:
            start += 10  # length of 'page.fill('
            
            # Extract first parameter (selector)
            if code_line[start] in ['"', "'"]:
                quote1 = code_line[start]
                end1 = code_line.find(quote1, start + 1)
                if end1 > start:
                    selector = code_line[start + 1:end1]
                    
                    # Find second parameter (value)
                    comma_pos = code_line.find(',', end1)
                    if comma_pos > 0:
                        start2 = comma_pos + 1
                        while start2 < len(code_line) and code_line[start2] in [' ', '\\t']:
                            start2 += 1
                        
                        if start2 < len(code_line) and code_line[start2] in ['"', "'"]:
                            quote2 = code_line[start2]
                            end2 = code_line.find(quote2, start2 + 1)
                            if end2 > start2:
                                value = code_line[start2 + 1:end2]
                                return (selector, value)
        
        return None
    
    def convert_file(self, file_path: str, format_type: str = "auto") -> str:
        """Convert a recorder file to Easy BDD YAML format.
        
        Args:
            file_path: Path to the recorder file
            format_type: Type of recorder format (auto-detect if "auto")
            
        Returns:
            YAML content as string
        \"\"\"
        # Path already imported at top of file
        path_obj = Path(file_path)
        
        with open(file_path, 'r') as f:
            if file_path.endswith('.json'):
                data = json.load(f)
            else:
                data = json.loads(f.read())
        
        # Auto-detect format if needed
        if format_type == "auto":
            format_type = self.detect_format(data)
        
        # Convert to Easy BDD format
        test_def = self.convert(data, format_type, path_obj)
        
        # Convert to YAML
        import yaml
        return yaml.dump(test_def, default_flow_style=False, sort_keys=False)
