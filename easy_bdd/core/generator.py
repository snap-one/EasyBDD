"""
Gherkin feature generator from YAML test definitions
"""

from pathlib import Path
from typing import List
from .parser import TestDefinition, TestStep


class GherkinGenerator:
    """Generates Gherkin feature files from YAML test definitions"""
    
    def __init__(self):
        self.action_mappings = self._create_action_mappings()
    
    def _create_action_mappings(self) -> dict:
        """Create mappings from actions to Gherkin steps"""
        return {
            # Browser actions
            "Open browser": "Given I open a browser to \"{url}\"",
            "Click element": "When I click on element \"{selector}\"",
            "Click button": "When I click the \"{button}\" button",
            "Fill form field": "When I fill the \"{field}\" field with \"{value}\"",
            "Verify page contains": "Then the page should contain \"{text}\"",
            "Take screenshot": "And I take a screenshot named \"{name}\"",
            "Wait for element": "And I wait for element \"{selector}\" to appear",
            
            # API actions
            "Send API request": "When I send a {method} request to \"{url}\"",
            "Verify API response": "Then the response status should be {status_code}",
            "Extract from response": "And I extract \"{field}\" from response and save as \"{save_as}\"",
        }
    
    def yaml_to_gherkin(self, yaml_file: Path) -> str:
        """Convert a YAML test file to Gherkin feature"""
        from .parser import YAMLParser
        
        parser = YAMLParser()
        test = parser.parse_file(yaml_file)
        
        return self.generate_feature(test)
    
    def generate_feature(self, test: TestDefinition) -> str:
        """Generate Gherkin feature from test definition"""
        lines = []
        
        # Feature header
        lines.append(f"Feature: {test.name}")
        lines.append("")
        
        if test.description:
            lines.append(f"  {test.description}")
            lines.append("")
        
        # Tags
        if test.tags:
            tag_line = "  " + " ".join(f"@{tag}" for tag in test.tags)
            lines.append(tag_line)
        
        # Scenario
        lines.append(f"  Scenario: {test.name}")
        
        # Main test steps
        first_step = True
        for step in test.steps:
            keyword = "Given" if first_step else "And"
            
            # Use "When" for action steps, "Then" for verification steps
            if self._is_action_step(step):
                keyword = "When" if first_step else "And"
            elif self._is_verification_step(step):
                keyword = "Then"
            
            gherkin_step = self._convert_step_to_gherkin(step, keyword)
            lines.append(f"    {gherkin_step}")
            first_step = False
        
        return "\\n".join(lines)
    
    def _convert_step_to_gherkin(self, step: TestStep, default_keyword: str = "And") -> str:
        """Convert a test step to Gherkin format"""
        action = step.action
        params = step.parameters
        
        # Check if we have a direct mapping
        if action in self.action_mappings:
            template = self.action_mappings[action]
            try:
                # Format the template with parameters
                gherkin_text = template.format(**params)
                return gherkin_text
            except KeyError:
                # Missing parameter, use generic format
                return self._generic_step_format(step, default_keyword)
        else:
            # Use generic format for unknown actions
            return self._generic_step_format(step, default_keyword)
    
    def _generic_step_format(self, step: TestStep, keyword: str) -> str:
        """Generate generic Gherkin step format"""
        action = step.action.lower()
        params = step.parameters
        
        if not params:
            return f"{keyword} I {action}"
        
        # Create a readable parameter string
        param_parts = []
        for key, value in params.items():
            param_parts.append(f"{key}: {value}")
        
        param_string = ", ".join(param_parts)
        return f"{keyword} I {action} with {param_string}"
    
    def _is_action_step(self, step: TestStep) -> bool:
        """Check if step is an action (not verification)"""
        action_keywords = [
            "open", "click", "fill", "send", "connect", "tap", "enter",
            "upload", "invoke", "take"
        ]
        
        action_lower = step.action.lower()
        return any(keyword in action_lower for keyword in action_keywords)
    
    def _is_verification_step(self, step: TestStep) -> bool:
        """Check if step is a verification/assertion"""
        verify_keywords = [
            "verify", "check", "assert", "should", "contains", "expect"
        ]
        
        action_lower = step.action.lower()
        return any(keyword in action_lower for keyword in verify_keywords)
    
    def generate_multiple_features(self, tests: List[TestDefinition], output_dir: Path) -> List[Path]:
        """Generate multiple Gherkin features from test definitions"""
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files = []
        
        for test in tests:
            # Create feature file name based on test file
            feature_name = test.file_path.stem + ".feature"
            feature_path = output_dir / feature_name
            
            # Generate feature content
            feature_content = self.generate_feature(test)
            
            # Write feature file
            feature_path.write_text(feature_content, encoding="utf-8")
            generated_files.append(feature_path)
        
        return generated_files