#!/usr/bin/env python3
"""
Live UI Recorder for Easy BDD Framework
Records browser interactions and converts them to Easy BDD YAML format in real-time
"""

import subprocess
import re
import yaml
from pathlib import Path
from typing import List, Dict, Any
import argparse


class LiveRecorder:
    """Records browser interactions and converts to Easy BDD YAML"""
    
    def __init__(self):
        self.steps = []
        self.variables = {}
        
    def parse_playwright_line(self, line: str) -> Dict[str, Any]:
        """Parse Playwright codegen line to Easy BDD step"""
        line = line.strip()
        
        # Skip non-page lines
        if not 'page.' in line:
            return None
        
        # Remove page. prefix and trailing semicolon
        line = re.sub(r'^\s*page\.', '', line)
        line = line.rstrip(';')
        
        # goto(url)
        if match := re.match(r'goto\(["\']([^"\']*)["\']', line):
            return {
                'action': 'Open browser',
                'url': match.group(1)
            }
        
        # get_by_role(role, name=name).click()
        if match := re.match(r'get_by_role\(["\'](\w+)["\'],?\s*name\s*=\s*["\']([^"\']*)["\'].*?\)\.click\(', line):
            return {
                'action': 'Click element',
                'role': match.group(1),
                'name': match.group(2),
                'description': f'Click {match.group(1)}: {match.group(2)}'
            }
        
        # get_by_role(role, name=name).fill(value)
        if match := re.match(r'get_by_role\(["\'](\w+)["\'],?\s*name\s*=\s*["\']([^"\']*)["\'].*?\)\.fill\(["\']([^"\']*)["\']', line):
            return {
                'action': 'Fill form field',
                'role': match.group(1),
                'name': match.group(2),
                'value': match.group(3),
                'description': f'Fill {match.group(2)}'
            }
        
        # get_by_label(label).fill(value)
        if match := re.match(r'get_by_label\(["\']([^"\']*)["\'].*?\)\.fill\(["\']([^"\']*)["\']', line):
            return {
                'action': 'Fill form field',
                'label': match.group(1),
                'value': match.group(2),
                'description': f'Fill {match.group(1)}'
            }
        
        # get_by_placeholder(placeholder).fill(value)
        if match := re.match(r'get_by_placeholder\(["\']([^"\']*)["\'].*?\)\.fill\(["\']([^"\']*)["\']', line):
            return {
                'action': 'Fill form field',
                'field': f'input[placeholder="{match.group(1)}"]',
                'value': match.group(2),
                'description': f'Fill field with placeholder: {match.group(1)}'
            }
        
        # get_by_role(role, name=name) (link/button without explicit click)
        if match := re.match(r'get_by_role\(["\'](\w+)["\'],?\s*name\s*=\s*["\']([^"\']*)["\']', line):
            if '.click()' not in line and '.fill(' not in line:
                return None  # Skip if no action
        
        # get_by_text(text).click()
        if match := re.match(r'get_by_text\(["\']([^"\']*)["\'].*?\)\.click\(', line):
            return {
                'action': 'Click element',
                'text': match.group(1),
                'description': f'Click text: {match.group(1)}'
            }
        
        # locator(selector).click() - with button parameter
        if match := re.match(r'locator\(["\']([^"\']*)["\'].*?\)\.click\((.+?)\)', line):
            params = match.group(2)
            step = {
                'action': 'Click element',
                'selector': match.group(1),
                'description': f'Click: {match.group(1)}'
            }
            # Check for button parameter (right-click, etc.)
            if 'button=' in params:
                return None  # Skip right-clicks for now
            return step
        
        # locator(selector).click() - handle escaped quotes
        if match := re.search(r'locator\((["\'])(.+?)\1\)\.click\(', line):
            return {
                'action': 'Click element',
                'selector': match.group(2).replace('\\"', '"').replace("\\'", "'"),
                'description': f"Click: {match.group(2)}"
            }
        
        # locator(selector).fill(value) - handle escaped quotes
        if match := re.search(r'locator\((["\'])(.+?)\1\)\.fill\((["\'])(.+?)\3', line):
            selector = match.group(2).replace('\\"', '"').replace("\\'", "'")
            value = match.group(4).replace('\\"', '"').replace("\\'", "'")
            # Skip empty fills (clearing fields)
            if not value:
                return None
            return {
                'action': 'Fill form field',
                'field': selector,
                'value': value,
                'description': f'Fill: {selector}'
            }
        
        # locator(selector).select_option(value) - handle escaped quotes
        if match := re.search(r'locator\((["\'])(.+?)\1\)\.select_option\((["\'])(.+?)\3', line):
            selector = match.group(2).replace('\\"', '"').replace("\\'", "'")
            value = match.group(4).replace('\\"', '"').replace("\\'", "'")
            return {
                'action': 'Select option',
                'selector': selector,
                'value': value,
                'description': f'Select from dropdown: {selector}'
            }
        
        # click(selector)
        if match := re.match(r'click\(["\']([^"\']*)["\']', line):
            return {
                'action': 'Click element',
                'selector': match.group(1),
                'description': f'Click: {match.group(1)}'
            }
        
        # fill(selector, value)
        if match := re.match(r'fill\(["\']([^"\']*)["\'],\s*["\']([^"\']*)["\']', line):
            return {
                'action': 'Fill form field',
                'field': match.group(1),
                'value': match.group(2),
                'description': f'Fill: {match.group(1)}'
            }
        
        # locator(selector).press(key)
        if match := re.match(r'locator\(["\']([^"\']*)["\'].*?\)\.press\(["\']([^"\']*)["\']', line):
            # Skip CapsLock and other non-essential keys
            key = match.group(2)
            if key.lower() in ['capslock', 'numlock', 'scrolllock']:
                return None
            return {
                'action': 'Press key',
                'selector': match.group(1),
                'key': key,
                'description': f'Press {key} in {match.group(1)}'
            }
        
        # press(key)
        if match := re.match(r'press\(["\']([^"\']*)["\']', line):
            return {
                'action': 'Press key',
                'key': match.group(1),
                'description': f'Press key: {match.group(1)}'
            }
        
        # wait_for_selector(selector)
        if match := re.match(r'wait_for_selector\(["\']([^"\']*)["\']', line):
            return {
                'action': 'Wait for element',
                'selector': match.group(1),
                'description': f'Wait for: {match.group(1)}'
            }
        
        # screenshot()
        if 'screenshot' in line:
            return {
                'action': 'Take screenshot',
                'name': 'recorded_screenshot'
            }
        
        # Skip expect() assertions - these become implicit validations
        if line.startswith('expect('):
            return None
        
        return None
    
    def record(self, url: str = None, output: str = None):
        """Start recording and convert to YAML"""
        print("🎬 Starting Easy BDD Live Recorder")
        print("=" * 60)
        print("Instructions:")
        print("1. Perform your actions in the browser")
        print("2. When done, close the browser window")
        print("3. Your test will be automatically converted to YAML")
        print("=" * 60)
        
        # Build playwright codegen command
        cmd = ['playwright', 'codegen']
        if url:
            cmd.append(url)
        
        try:
            # Run playwright codegen and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Parse the generated code
                code_lines = result.stdout.split('\n')
                
                # Extract steps from code
                for line in code_lines:
                    if 'page.' in line or 'await' in line:
                        step = self.parse_playwright_line(line)
                        if step:
                            self.steps.append(step)
                
                # Generate YAML
                if self.steps:
                    self._save_yaml(output)
                else:
                    print("❌ No actions recorded")
            else:
                print(f"❌ Recording failed: {result.stderr}")
                
        except FileNotFoundError:
            print("❌ Playwright not found. Install with: playwright install")
        except KeyboardInterrupt:
            print("\n⏹️  Recording cancelled")
    
    def _save_yaml(self, output_file: str = None):
        """Save recorded steps as YAML"""
        if not output_file:
            output_file = 'tests/cases/recorded_test.yaml'
        
        # Build YAML structure
        test_data = {
            'name': 'Recorded Test',
            'description': 'Test recorded using Easy BDD Live Recorder',
            'tags': ['browser', 'recorded'],
            'variables': self.variables,
            'steps': self.steps
        }
        
        # Create output directory if needed
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write YAML
        with open(output_path, 'w') as f:
            yaml.dump(test_data, f, 
                     default_flow_style=False, 
                     sort_keys=False,
                     allow_unicode=True)
        
        print(f"\n✅ Test saved to: {output_file}")
        print(f"📊 Recorded {len(self.steps)} steps")
        print(f"\nTo run: python -m easy_bdd run {output_file}")


class InteractiveRecorder:
    """Records with real-time monitoring and conversion"""
    
    def __init__(self):
        self.steps = []
        self.parser = LiveRecorder()
        
    def start(self, url: str = None, output: str = None):
        """Start interactive recording session"""
        print("🎬 Starting Interactive Easy BDD Recorder")
        print("=" * 60)
        
        if not output:
            output = input("Output file (default: tests/cases/recorded_test.yaml): ").strip()
            if not output:
                output = 'tests/cases/recorded_test.yaml'
        
        print(f"\n📝 Recording to: {output}")
        print("\nInstructions:")
        print("1. Browser will open")
        print("2. Perform your test actions")
        print("3. Copy the generated Playwright code when done")
        print("4. Paste it here to convert to YAML")
        print("=" * 60)
        
        # Launch codegen
        cmd = ['playwright', 'codegen']
        if url:
            cmd.append(url)
            print(f"\n🌐 Opening: {url}\n")
        
        try:
            subprocess.Popen(cmd)
            
            print("\n⏳ Waiting for recording...")
            print("When done, paste the Playwright code here (Ctrl+D when finished):\n")
            
            # Read pasted code
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            
            # Parse and convert
            code = '\n'.join(lines)
            for line in lines:
                if 'page.' in line:
                    step = self.parser.parse_playwright_line(line)
                    if step:
                        self.steps.append(step)
            
            if self.steps:
                self._save_yaml(output)
                self._print_preview()
            else:
                print("\n❌ No valid steps found")
                
        except KeyboardInterrupt:
            print("\n⏹️  Recording cancelled")
    
    def _save_yaml(self, output_file: str):
        """Save steps to YAML"""
        test_data = {
            'name': 'Recorded Test',
            'description': 'Test recorded using Easy BDD Interactive Recorder',
            'tags': ['browser', 'recorded'],
            'steps': self.steps
        }
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            yaml.dump(test_data, f,
                     default_flow_style=False,
                     sort_keys=False,
                     allow_unicode=True)
        
        print(f"\n✅ Test saved to: {output_file}")
        print(f"📊 Recorded {len(self.steps)} steps\n")
    
    def _print_preview(self):
        """Print YAML preview"""
        print("Preview:")
        print("-" * 60)
        for i, step in enumerate(self.steps[:5], 1):
            action = step.get('action', 'Unknown')
            desc = step.get('description', '')
            print(f"  {i}. {action}: {desc}")
        if len(self.steps) > 5:
            print(f"  ... and {len(self.steps) - 5} more steps")
        print("-" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Easy BDD Live UI Recorder - Record browser actions as YAML tests'
    )
    parser.add_argument('url', nargs='?', help='Starting URL (optional)')
    parser.add_argument('-o', '--output', help='Output YAML file')
    parser.add_argument('-i', '--interactive', action='store_true',
                       help='Interactive mode with paste-in conversion')
    
    args = parser.parse_args()
    
    if args.interactive:
        recorder = InteractiveRecorder()
        recorder.start(url=args.url, output=args.output)
    else:
        recorder = LiveRecorder()
        recorder.record(url=args.url, output=args.output)


if __name__ == '__main__':
    main()
