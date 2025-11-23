"""
Enhanced Test Runner with Centralized Variable Management
Integrates the new variable manager with the existing runner structure
"""

import sys
import time
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import ConfigManager
from .parser import YAMLParser, TestDefinition
from .generator import GherkinGenerator
from .variable_manager import get_global_config, GlobalConfigManager
from ..services.browser_service import BrowserService


@dataclass
class TestResult:
    """Test execution result"""

    success: bool
    total_tests: int
    passed: int
    failed: int
    skipped: int
    execution_time: float
    report_path: Optional[Path] = None


class EnhancedTestRunner:
    """Enhanced test runner with centralized variable management"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.parser = YAMLParser()
        self.generator = GherkinGenerator()

        # Initialize centralized variable manager
        self.global_config = get_global_config()

        # Load framework configuration into global config
        self._initialize_global_config()

    def _initialize_global_config(self):
        """Initialize the global configuration system"""
        # Load configuration from the actual config manager
        if self.config.config_path.exists():
            with open(self.config.config_path, "r") as f:
                import yaml

                raw_config = yaml.safe_load(f) or {}
        else:
            raw_config = {}

        # Set framework variables
        framework_vars = raw_config.get("variables", {})
        env_vars = raw_config.get("environment", {})

        # Load variables into appropriate scopes
        config_scope = self.global_config.variable_manager.get_scope("config_file")
        if config_scope:
            config_scope.update(framework_vars)

        env_scope = self.global_config.variable_manager.get_scope("environment_vars")
        if env_scope:
            env_scope.update(env_vars)

        # Load environment variables from OS
        self.global_config.variable_manager.load_environment_variables("EASYBDD_")

        # Load API configuration
        self.global_config.api_config_manager.load_api_config(raw_config)

        # Initialize services dict
        self.services = {}

    def run(
        self, test_path: Path, tags: List[str] = None, parallel_workers: int = 1
    ) -> TestResult:
        """Run tests from the specified path with enhanced variable management"""
        # Set runtime variables
        self.global_config.set_variable("test_run_start_time", time.time())
        self.global_config.set_variable("test_path", str(test_path))

        # Parse test definitions
        if test_path.is_file():
            tests = [self.parser.parse_file(test_path)]
        else:
            tests = self.parser.parse_directory(test_path)

        if not tests:
            print(f"No tests found in {test_path}")
            return TestResult(
                success=False,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                execution_time=0.0,
            )

        # Filter tests by tags
        if tags:
            tests = self._filter_tests_by_tags(tests, tags)

        # Generate Gherkin features
        features_dir = Path("tests/features")
        features_dir.mkdir(parents=True, exist_ok=True)

        feature_files = self.generator.generate_multiple_features(tests, features_dir)

        print(f"Generated {len(feature_files)} Gherkin features")
        print(f"Running {len(tests)} tests with enhanced variable management...")

        # Execute tests
        start_time = time.time()
        passed = 0
        failed = 0

        for i, test in enumerate(tests, 1):
            print(f"\nExecuting test {i}/{len(tests)}: {test.name}")
            try:
                success = self._execute_test(test)
                if success:
                    passed += 1
                    print(f"  ✅ PASSED: {test.name}")
                else:
                    failed += 1
                    print(f"  ❌ FAILED: {test.name}")
            except Exception as e:
                failed += 1
                print(f"  ❌ ERROR: {test.name} - {e}")

        execution_time = time.time() - start_time
        success = failed == 0

        # Store results in global variables for access by other tests
        self.global_config.set_variable("last_run_passed", passed)
        self.global_config.set_variable("last_run_failed", failed)
        self.global_config.set_variable("last_run_total", len(tests))
        self.global_config.set_variable("last_run_success", success)

        print(f"\n{'='*50}")
        print(f"Test Results: {passed} passed, {failed} failed")
        print(f"Execution time: {execution_time:.2f}s")
        print(f"Overall result: {'PASSED' if success else 'FAILED'}")

        result = TestResult(
            success=success,
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=0,
            execution_time=execution_time,
            report_path=Path("reports") / "report.html",
        )

        return result

    def _execute_test(self, test: TestDefinition) -> bool:
        """Execute a single test with enhanced variable management"""
        try:
            # Load device configuration if specified
            if hasattr(test, "device_config") and test.device_config:
                print(f"      Loading device config: {test.device_config}")
                device_data = self.global_config.load_device_config(test.device_config)
                if device_data:
                    print(
                        f"      ✅ Device config loaded: {device_data.get('device_info', {}).get('name', 'Unknown')}"
                    )

            # Set test-level variables in the global config
            if hasattr(test, "variables") and test.variables:
                test_scope = self.global_config.variable_manager.get_scope(
                    "test_variables"
                )
                test_scope.variables.clear()  # Clear previous test variables
                test_scope.update(test.variables)

            # Set current test info
            self.global_config.set_variable("current_test_name", test.name)
            self.global_config.set_variable("current_test_file", str(test.file_path))

            # Check for data-driven testing
            if hasattr(test, "data") and test.data:
                return self._execute_data_driven_test(test)
            else:
                return self._execute_single_test(test)
        except Exception as e:
            print(f"      Test execution failed: {e}")
            return False

    def _execute_single_test(self, test: TestDefinition) -> bool:
        """Execute a single test instance"""
        # Execute setup steps
        if hasattr(test, "setup") and test.setup:
            for setup_step in test.setup:
                success = self._execute_step_enhanced(setup_step)
                if not success:
                    print(f"      Setup step failed: {setup_step}")
                    return False

        # Execute main steps
        for i, step in enumerate(test.steps, 1):
            print(f"      Step {i}: {step.get('action', 'Unknown')}")
            success = self._execute_step_enhanced(step)
            if not success:
                print(f"      Step {i} failed: {step}")
                return False

        # Execute cleanup steps
        if hasattr(test, "cleanup") and test.cleanup:
            for cleanup_step in test.cleanup:
                try:
                    self._execute_step_enhanced(cleanup_step)
                except Exception as e:
                    print(
                        f"      Cleanup step failed (continuing): {cleanup_step} - {e}"
                    )

        return True

    def _execute_step_enhanced(self, step: Dict[str, Any]) -> bool:
        """Execute a single step with enhanced variable management"""
        try:
            # Substitute variables in the step using global config
            substituted_step = self.global_config.substitute_recursive(step)

            # Determine service type
            service_type = self._determine_service_type(substituted_step)

            # Get or create service
            if service_type not in self.services:
                self.services[service_type] = self._create_service_enhanced(
                    service_type
                )

            service = self.services[service_type]

            # Execute step
            return self._execute_step_on_service(service, substituted_step)

        except Exception as e:
            print(f"        Step execution error: {e}")
            return False

    def _create_service_enhanced(self, service_type: str):
        """Create a service instance with enhanced configuration"""
        if service_type == "browser":
            return BrowserService(self.config)
        elif service_type == "api":
            from ..services.api_service import APIService

            return APIService(self.global_config)
        else:
            # For now, return a mock service for other types
            return MockService(service_type)

    def _execute_step_on_service(self, service, step: Dict[str, Any]) -> bool:
        """Execute a step on a specific service"""
        action = step.get("action")

        # Store step results in variables for potential use by subsequent steps
        self.global_config.set_variable("last_step_action", action)
        self.global_config.set_variable("last_step_params", step)

        if hasattr(service, "execute_action"):
            result = service.execute_action(action, step)

            # Store result in global variables
            self.global_config.set_variable("last_step_result", result)
            return result
        else:
            print(
                f"        Service {type(service).__name__} doesn't support execute_action"
            )
            return False

    def _determine_service_type(self, step: Dict[str, Any]) -> str:
        """Determine which service should handle this step"""
        action = step.get("action", "").lower()

        # API actions
        if any(
            keyword in action
            for keyword in ["api", "request", "get", "post", "put", "delete", "patch"]
        ):
            return "api"

        # Browser actions
        elif any(
            keyword in action
            for keyword in ["click", "type", "navigate", "wait", "screenshot"]
        ):
            return "browser"

        # Default to browser for now
        return "browser"

    def _filter_tests_by_tags(
        self, tests: List[TestDefinition], tags: List[str]
    ) -> List[TestDefinition]:
        """Filter tests by tags"""
        filtered = []
        for test in tests:
            if hasattr(test, "tags") and test.tags:
                if any(tag in test.tags for tag in tags):
                    filtered.append(test)
            elif "all" in tags:
                filtered.append(test)
        return filtered

    def _execute_data_driven_test(self, test: TestDefinition) -> bool:
        """Execute test with multiple data sets using enhanced variables"""
        all_passed = True
        data_sets = test.data

        print(
            f"    Running {len(data_sets)} data iterations with enhanced variables..."
        )

        for i, data_set in enumerate(data_sets, 1):
            print(f"      Data iteration {i}/{len(data_sets)}")

            # Set iteration-specific variables
            self.global_config.set_variable("current_iteration", i)
            self.global_config.set_variable("total_iterations", len(data_sets))

            # Add data set variables to test scope
            iteration_scope = self.global_config.variable_manager.get_scope(
                "runtime_data"
            )
            iteration_scope.update(data_set)

            # Execute the test with this data set
            success = self._execute_single_test(test)
            if not success:
                all_passed = False
                print(f"      ❌ Data iteration {i} failed")
            else:
                print(f"      ✅ Data iteration {i} passed")

        return all_passed

    def debug_variables(self) -> Dict[str, Any]:
        """Get debug information about current variable state"""
        return self.global_config.debug_variables()

    def export_session_state(self, file_path: str = None):
        """Export current session state for debugging"""
        if not file_path:
            file_path = f"reports/session_debug_{int(time.time())}.json"

        self.global_config.variable_manager.save_session_state(file_path)
        print(f"Session state exported to: {file_path}")


class MockService:
    """Mock service for unsupported service types"""

    def __init__(self, service_type: str):
        self.service_type = service_type

    def execute_action(self, action: str, params: Dict[str, Any]) -> bool:
        """Mock action execution"""
        print(f"        Mock {self.service_type} service: {action} with {params}")
        return True
