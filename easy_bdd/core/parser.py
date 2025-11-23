"""
YAML and JSON test definition parser with UI recorder support
"""

import yaml
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import re


@dataclass
class TestStep:
    """Represents a single test step"""

    action: str
    parameters: Dict[str, Any]
    shared_step: Optional[str] = None
    condition: Optional[str] = None  # Conditional expression
    then_steps: Optional[List["TestStep"]] = None  # Steps if condition true
    else_steps: Optional[List["TestStep"]] = None  # Steps if condition false
    retry_config: Optional[Dict[str, Any]] = None  # Retry configuration

    def __post_init__(self):
        # Ensure parameters is a dictionary
        if not isinstance(self.parameters, dict):
            self.parameters = {}


@dataclass
class SharedStep:
    """Represents a reusable shared step sequence"""

    name: str
    description: str
    parameters: List[str]
    steps: List[TestStep]


@dataclass
class TestDefinition:
    """Represents a complete test definition"""

    name: str
    description: str
    file_path: Path
    tags: List[str]
    variables: Dict[str, Any]
    setup: List[TestStep]
    steps: List[TestStep]
    cleanup: List[TestStep]
    data_source: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    async_execution: bool = False
    max_workers: int = 1
    device_config: Optional[str] = None  # Device configuration file reference

    def __post_init__(self):
        # Ensure all list fields are lists
        if not isinstance(self.tags, list):
            self.tags = []
        if not isinstance(self.setup, list):
            self.setup = []
        if not isinstance(self.steps, list):
            self.steps = []
        if not isinstance(self.cleanup, list):
            self.cleanup = []
        if not isinstance(self.variables, dict):
            self.variables = {}


class YAMLParser:
    """Parser for YAML test definitions"""

    def __init__(self):
        self.supported_extensions = {".yaml", ".yml", ".json"}
        self.shared_steps: Dict[str, SharedStep] = {}
        self._load_shared_steps()

    def _load_shared_steps(self) -> None:
        """Load shared steps from shared_steps.yaml"""
        shared_steps_path = Path("shared_steps.yaml")
        if shared_steps_path.exists():
            try:
                with open(shared_steps_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if isinstance(data, dict):
                    for name, step_data in data.items():
                        if isinstance(step_data, dict):
                            shared_step = SharedStep(
                                name=name,
                                description=step_data.get("description", ""),
                                parameters=step_data.get("parameters", []),
                                steps=self._parse_steps(step_data.get("steps", [])),
                            )
                            self.shared_steps[name] = shared_step
            except Exception as e:
                print(f"Warning: Failed to load shared steps: {e}")

    def parse_file(self, file_path: Path) -> TestDefinition:
        """Parse a single YAML test file"""
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Test file not found: {file_path}")

        if file_path.suffix.lower() not in self.supported_extensions:
            raise ValueError(f"Unsupported file extension: {file_path.suffix}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix.lower() == ".json":
                    data = json.load(f)
                    # Check if it's a recorder format
                    data = self._detect_and_convert_recorder_format(data, file_path)
                else:
                    data = yaml.safe_load(f)
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid file format in {file_path}: {e}")

        if not isinstance(data, dict):
            raise ValueError(f"YAML file must contain a dictionary: {file_path}")

        return self._parse_test_definition(data, file_path)

    def parse_directory(self, directory_path: Path) -> List[TestDefinition]:
        """Parse all YAML files in a directory"""
        directory_path = Path(directory_path)

        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        if not directory_path.is_dir():
            raise ValueError(f"Path is not a directory: {directory_path}")

        test_files = []
        for ext in self.supported_extensions:
            test_files.extend(directory_path.glob(f"**/*{ext}"))

        tests = []
        for file_path in test_files:
            try:
                test = self.parse_file(file_path)
                tests.append(test)
            except Exception as e:
                print(f"Warning: Failed to parse {file_path}: {e}")

        return tests

    def _parse_test_definition(
        self, data: Dict[str, Any], file_path: Path
    ) -> TestDefinition:
        """Parse test definition from YAML data"""
        # Required fields
        if "name" not in data:
            raise ValueError("Test definition must have a 'name' field")

        if "steps" not in data:
            raise ValueError("Test definition must have a 'steps' field")

        # Extract basic fields
        name = data["name"]
        description = data.get("description", "")
        tags = data.get("tags", [])
        variables = data.get("variables", {})
        data_source = data.get("data_source")
        device_config = data.get("device_config")  # Device configuration file reference

        # Extract data-driven fields
        test_data = data.get("data", None)
        async_execution = data.get("async_execution", False)
        max_workers = data.get("max_workers", 1)

        # Parse steps
        setup_steps = self._parse_steps(data.get("setup", []))
        test_steps = self._parse_steps(data["steps"])
        cleanup_steps = self._parse_steps(data.get("cleanup", []))

        return TestDefinition(
            name=name,
            description=description,
            file_path=file_path,
            tags=tags,
            variables=variables,
            setup=setup_steps,
            steps=test_steps,
            cleanup=cleanup_steps,
            data_source=data_source,
            data=test_data,
            async_execution=async_execution,
            max_workers=max_workers,
            device_config=device_config,
        )

    def _parse_steps(self, steps_data: List[Dict[str, Any]]) -> List[TestStep]:
        """Parse list of step definitions"""
        if not isinstance(steps_data, list):
            raise ValueError("Steps must be a list")

        steps = []
        for i, step_data in enumerate(steps_data):
            if not isinstance(step_data, dict):
                raise ValueError(f"Step {i} must be a dictionary")

            # Check if this is a shared step
            if "shared_step" in step_data:
                shared_steps = self._expand_shared_step(step_data)
                steps.extend(shared_steps)
            # Check if this is a conditional step
            elif "condition" in step_data or "if" in step_data:
                condition = step_data.get("condition") or step_data.get("if")
                then_data = step_data.get("then", [])
                else_data = step_data.get("else", [])

                then_steps = self._parse_steps(then_data) if then_data else None
                else_steps = self._parse_steps(else_data) if else_data else None

                steps.append(
                    TestStep(
                        action="conditional",
                        parameters={"expression": condition},
                        condition=condition,
                        then_steps=then_steps,
                        else_steps=else_steps,
                    )
                )
            else:
                if "action" not in step_data:
                    raise ValueError(f"Step {i} must have an 'action' field")

                action = step_data["action"]

                # Extract retry configuration if present
                retry_config = step_data.get("retry")

                parameters = {
                    k: v
                    for k, v in step_data.items()
                    if k not in ["action", "condition", "if", "then", "else", "retry"]
                }

                steps.append(
                    TestStep(
                        action=action, parameters=parameters, retry_config=retry_config
                    )
                )

        return steps

    def _expand_shared_step(self, step_data: Dict[str, Any]) -> List[TestStep]:
        """Expand a shared step into its constituent steps"""
        shared_step_name = step_data["shared_step"]
        step_parameters = step_data.get("parameters", {})

        if shared_step_name not in self.shared_steps:
            raise ValueError(f"Shared step '{shared_step_name}' not found")

        shared_step = self.shared_steps[shared_step_name]
        expanded_steps = []

        for step in shared_step.steps:
            # Create a copy of the step with parameter substitution
            expanded_step = TestStep(
                action=step.action,
                parameters=self._substitute_parameters(
                    step.parameters, step_parameters
                ),
            )
            expanded_steps.append(expanded_step)

        return expanded_steps

    def _substitute_parameters(
        self, original_params: Dict[str, Any], substitutions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Substitute parameters in step parameters"""
        result = {}
        for key, value in original_params.items():
            if isinstance(value, str):
                # Replace parameter placeholders
                for param_name, param_value in substitutions.items():
                    value = value.replace(f"${{{param_name}}}", str(param_value))
            result[key] = value
        return result

    def validate_test_definition(self, test: TestDefinition) -> List[str]:
        """Validate a test definition and return list of errors"""
        errors = []

        # Basic validation
        if not test.name.strip():
            errors.append("Test name cannot be empty")

        if not test.steps:
            errors.append("Test must have at least one step")

        # Validate steps
        for i, step in enumerate(test.steps):
            step_errors = self._validate_step(step, f"Step {i + 1}")
            errors.extend(step_errors)

        # Validate setup steps
        for i, step in enumerate(test.setup):
            step_errors = self._validate_step(step, f"Setup step {i + 1}")
            errors.extend(step_errors)

        # Validate cleanup steps
        for i, step in enumerate(test.cleanup):
            step_errors = self._validate_step(step, f"Cleanup step {i + 1}")
            errors.extend(step_errors)

        return errors

    def _validate_step(self, step: TestStep, step_name: str) -> List[str]:
        """Validate a single step"""
        errors = []

        if not step.action.strip():
            errors.append(f"{step_name}: Action cannot be empty")

        return errors

    def _detect_and_convert_recorder_format(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Detect and convert UI recorder formats to Easy BDD format"""
        from .recorder_converter import RecorderConverter

        converter = RecorderConverter()
        detected_format = converter.detect_format(data)

        if detected_format:
            print(f"Detected {detected_format} recording format in {file_path.name}")
            return converter.convert(data, detected_format, file_path)

        # If no recorder format detected, return data as-is
        return data
