"""
Configuration validation for Easy BDD Framework

Validates test files and configuration before execution.
"""

from typing import List, Dict, Any, Tuple
from pathlib import Path
import yaml


class ConfigValidator:
    """Validate test configurations and YAML files."""

    # Required fields in test files
    REQUIRED_TEST_FIELDS = {"name", "steps"}

    # Valid action prefixes
    VALID_ACTION_PREFIXES = {
        "browser",
        "api",
        "aws",
        "jsonrpc",
        "test",
        "websocket",
        "serial",
        "android",
    }

    # Deprecated actions (suggest replacements)
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

    def __init__(self, strict_mode: bool = False):
        """
        Initialize validator.

        Args:
            strict_mode: If True, treat warnings as errors
        """
        self.strict_mode = strict_mode
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_test_file(
        self, file_path: Path, strict: bool = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate a test YAML file.

        Args:
            file_path: Path to test file
            strict: If provided, overrides the instance strict_mode

        Returns:
            Tuple of (is_valid, messages)
        """
        # Use parameter value if provided, otherwise use instance setting
        strict_mode = strict if strict is not None else self.strict_mode

        self.errors = []
        self.warnings = []

        try:
            with open(file_path, "r") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"Failed to parse YAML: {e}")
            return False, self.errors + self.warnings

        # Validate structure
        self._validate_structure(data, file_path.name)

        # Validate steps
        if "steps" in data:
            self._validate_steps(data["steps"], "steps")

        if "setup" in data:
            self._validate_steps(data["setup"], "setup")

        if "cleanup" in data:
            self._validate_steps(data["cleanup"], "cleanup")

        # Check for deprecated actions
        self._check_deprecated_actions(data)

        # Check for security issues
        self._check_security_issues(data)

        is_valid = len(self.errors) == 0
        if strict_mode:
            is_valid = is_valid and len(self.warnings) == 0

        return is_valid, self.errors + self.warnings

    def _validate_structure(self, data: Dict[str, Any], filename: str):
        """Validate basic test structure."""
        if not isinstance(data, dict):
            self.errors.append(f"Test file must be a dictionary, got {type(data)}")
            return

        # Check required fields
        missing = self.REQUIRED_TEST_FIELDS - set(data.keys())
        if missing:
            self.errors.append(f"Missing required fields: {', '.join(missing)}")

        # Validate name
        if "name" in data:
            if not data["name"] or not isinstance(data["name"], str):
                self.errors.append("Test name must be a non-empty string")

        # Check for empty steps
        if "steps" in data:
            if not data["steps"]:
                self.warnings.append("Test has no steps defined")

    def _validate_steps(self, steps: List[Dict], section: str):
        """Validate test steps."""
        if not isinstance(steps, list):
            self.errors.append(f"{section} must be a list")
            return

        for idx, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                self.errors.append(f"{section}[{idx}]: Step must be a dictionary")
                continue

            # Check for action
            if "action" not in step:
                self.errors.append(f"{section}[{idx}]: Step missing 'action'")
                continue

            action = step["action"]
            if not action or not isinstance(action, str):
                self.errors.append(
                    f"{section}[{idx}]: Action must be a non-empty string"
                )
                continue

            # Validate action format
            self._validate_action(action, f"{section}[{idx}]")

            # Check for conditional steps
            if "condition" in step or "if" in step:
                self._validate_conditional_step(step, f"{section}[{idx}]")

    def _validate_action(self, action: str, location: str):
        """Validate action name format."""
        action_lower = action.lower()

        # Check if using dot notation
        if "." in action_lower:
            prefix = action_lower.split(".")[0]
            if prefix not in self.VALID_ACTION_PREFIXES:
                self.warnings.append(f"{location}: Unknown action prefix '{prefix}'")
        else:
            # Old format - suggest migration
            if action in self.DEPRECATED_ACTIONS:
                new_action = self.DEPRECATED_ACTIONS[action]
                self.warnings.append(
                    f"{location}: Consider using '{new_action}' "
                    f"instead of '{action}' (dot notation)"
                )

    def _validate_conditional_step(self, step: Dict, location: str):
        """Validate conditional step structure."""
        condition_key = "condition" if "condition" in step else "if"
        condition = step[condition_key]

        if not condition or not isinstance(condition, str):
            self.errors.append(f"{location}: Condition must be a non-empty string")

        # Check for then/else branches
        if "then" not in step and "then_steps" not in step:
            self.warnings.append(f"{location}: Conditional step has no 'then' branch")

        # Validate branch steps
        for branch in ["then", "then_steps", "else", "else_steps"]:
            if branch in step:
                if not isinstance(step[branch], list):
                    self.errors.append(f"{location}: '{branch}' must be a list")

    def _check_deprecated_actions(self, data: Dict[str, Any]):
        """Check for deprecated actions in test."""
        sections = ["steps", "setup", "cleanup"]
        deprecated_count = 0

        for section in sections:
            if section not in data:
                continue

            for step in data[section]:
                if isinstance(step, dict) and "action" in step:
                    if step["action"] in self.DEPRECATED_ACTIONS:
                        deprecated_count += 1

        if deprecated_count > 0:
            self.warnings.append(
                f"Found {deprecated_count} deprecated action(s). "
                "Consider migrating to dot notation. "
                "See docs/dot-notation-actions.md"
            )

    def _check_security_issues(self, data: Dict[str, Any]):
        """Check for potential security issues."""
        # Check for hardcoded credentials in variables
        if "variables" in data and isinstance(data["variables"], dict):
            for key, value in data["variables"].items():
                key_lower = key.lower()

                # Check for suspicious variable names with plain values
                if any(
                    word in key_lower for word in ["password", "secret", "token", "key"]
                ):
                    if isinstance(value, str) and not value.startswith("${"):
                        self.warnings.append(
                            f"Variable '{key}' may contain hardcoded "
                            "sensitive data. Consider using environment "
                            "variables: ${{{key}}}"
                        )

    def validate_directory(self, directory: Path) -> Dict[str, Any]:
        """
        Validate all test files in a directory.

        Args:
            directory: Path to directory containing tests

        Returns:
            Dictionary with validation results
        """
        results = {"total": 0, "valid": 0, "invalid": 0, "warnings": 0, "files": {}}

        for yaml_file in directory.glob("**/*.yaml"):
            if yaml_file.is_file():
                results["total"] += 1
                is_valid, messages = self.validate_test_file(yaml_file)

                error_count = len([m for m in messages if not m.startswith("Warning")])
                warning_count = len(messages) - error_count

                results["files"][str(yaml_file)] = {
                    "valid": is_valid,
                    "errors": error_count,
                    "warnings": warning_count,
                    "messages": messages,
                }

                if is_valid:
                    results["valid"] += 1
                else:
                    results["invalid"] += 1

                results["warnings"] += warning_count

        return results


def validate_test_file(file_path: str, strict: bool = False) -> bool:
    """
    Convenience function to validate a test file.

    Args:
        file_path: Path to test file
        strict: Treat warnings as errors

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_test_file("tests/cases/my_test.yaml")
        True
    """
    validator = ConfigValidator(strict_mode=strict)
    is_valid, messages = validator.validate_test_file(Path(file_path))

    for message in messages:
        print(f"  {message}")

    return is_valid
