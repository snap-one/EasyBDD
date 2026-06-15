"""
Test runner for executing Easy BDD tests
"""

import contextlib
import datetime
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..services.browser_service import BrowserService
from ..services.command_service import CommandService
from ..services.ovrc_api_service import OvrCApiService
from .assertions import AssertionEngine, JSONSchemaValidator, ResponseValidator
from .data_loader import DataLoader
from .datalake_logger import DatalakeLogger, get_logger
from .generator import GherkinGenerator
from .html_reporter import HTMLReporter
from .parser import TestDefinition, YAMLParser
from .retry import RetryConfig, retry_action
from .safe_eval import safe_eval
from .security import mask_sensitive_data
from .soft_assertions import SoftAssertionManager
from .variable_manager import GlobalConfigManager

# from ..actions import action_registry


class _BreakSignal(Exception):
    """Raised by a 'break' step to exit the nearest enclosing loop."""


class _ContinueSignal(Exception):
    """Raised by a 'continue' step to skip to the next loop iteration."""


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
    test_details: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.test_details is None:
            self.test_details = []


class _GvLogEntry:
    """Mimics a single gv.log[n] dict entry from mybdd."""
    def __init__(self, variables: dict, offset: int = -1):
        self._vars = variables
        self._offset = offset

    def __getitem__(self, key: str):
        if self._offset in (-1, 0):
            mapping = {
                "response_txt":  self._vars.get("last_response", ""),
                "response":      self._vars.get("last_response", ""),
                "response_dict": self._vars.get("last_response_dict", {}),
                "status_code":   self._vars.get("last_status_code", 0),
                "response_code": self._vars.get("last_status_code", 0),
            }
        elif self._offset == -2:
            mapping = {
                "response_txt":  self._vars.get("prev_response", ""),
                "response_dict": self._vars.get("prev_response_dict", {}),
                "status_code":   0,
                "response_code": 0,
            }
        else:
            mapping = {"response_txt": "", "response_dict": {}, "status_code": 0, "response_code": 0}
        return mapping.get(key, "")

    def get(self, key, default=None):
        val = self[key]
        return val if val != "" else default


class _GvLog:
    """Mimics gv.log[] from mybdd — indexed access to response history."""
    def __init__(self, variables: dict):
        self._vars = variables

    def __getitem__(self, idx: int):
        return _GvLogEntry(self._vars, idx)


class _GvTests:
    """Mimics gv.tests from mybdd — variable store access."""
    def __init__(self, variables: dict):
        self._vars = variables

    def __getitem__(self, key: str):
        if key == "variables":
            return self._vars
        return {}

    def get(self, key, default=None):
        if key == "variables":
            return self._vars
        return default


class _Gv:
    """mybdd gv compatibility shim for eval.exec steps.

    Allows converted test code that still references gv.log[-1]['response_txt'],
    gv.tests['variables']['key'], etc. to run unchanged under Easy BDD.
    """
    def __init__(self, variables: dict):
        self.log = _GvLog(variables)
        self.tests = _GvTests(variables)


class TestRunner:
    """Main test runner for Easy BDD Framework"""

    def __init__(self, config: GlobalConfigManager, log_dir: Path = None):
        self.config = config
        self.parser = YAMLParser()
        self.generator = GherkinGenerator()
        from .connection_pool import ConnectionPool
        self._connection_pool = ConnectionPool()
        self._eval_state: dict = {}
        from .run_logger import RunLogger, _fmt_duration
        self._run_logger = RunLogger(log_dir)
        self._fmt_duration = _fmt_duration

        # Load custom actions
        # Load action modules if available
        # action_registry.load_action_modules(config)

    def run(
        self, test_path: Path, tags: List[str] = None, parallel_workers: int = 1, record_video: bool = False,
        report_name: str = None, generate_report: bool = True,
    ) -> TestResult:
        """Run tests from the specified path"""
        self._record_video = record_video
        # Parse test definitions
        try:
            if test_path.is_file():
                tests = [self.parser.parse_file(test_path)]
            else:
                tests = self.parser.parse_directory(test_path)
        except Exception as e:
            print(f"\n❌ Failed to load test(s) from {test_path}")
            print(f"   Error: {e}")
            print(f"\n💡 To edit the test file, run:")
            if test_path.is_file():
                print(f"   python -m easy_bdd edit-test \"{test_path}\"")
            else:
                print(f"   python -m easy_bdd edit-test \"<test_file_path>\"")
            return TestResult(
                success=False,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                execution_time=0.0,
            )

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

        # Validate tests
        for test in tests:
            errors = self.parser.validate_test_definition(test)
            if errors:
                print(f"Validation errors in {test.file_path}:")
                for error in errors:
                    print(f"  - {error}")
                return TestResult(
                    success=False,
                    total_tests=len(tests),
                    passed=0,
                    failed=len(tests),
                    skipped=0,
                    execution_time=0.0,
                )

        # Generate Gherkin features
        features_dir = Path("tests/features")
        features_dir.mkdir(parents=True, exist_ok=True)

        feature_files = self.generator.generate_multiple_features(tests, features_dir)

        print(f"Generated {len(feature_files)} Gherkin features")
        print(f"Running {len(tests)} tests...")

        # Execute tests
        start_time = time.time()
        passed = 0
        failed = 0
        skipped = 0
        test_details = []

        for i, test in enumerate(tests, 1):
            test_start_time = time.time()

            # Capture console output for this test
            log_capture = StringIO()

            # Create test detail dictionary to capture failure info
            test_detail = {
                "name": test.name,
                "description": test.description,
                "tags": test.tags,
                "file_path": (
                    str(test.file_path) if hasattr(test, "file_path") else None
                ),
                "execution_log": [],
            }

            # Print to both console and capture
            header = f"\nExecuting test {i}/{len(tests)}: {test.name}"
            print(header)
            test_detail["execution_log"].append(header)

            try:
                # Store original stdout
                original_stdout = sys.stdout

                # Create a custom writer that writes to both console and capture
                class DualWriter:
                    def __init__(self, *writers):
                        self.writers = writers

                    def write(self, text):
                        for writer in self.writers:
                            writer.write(text)

                    def flush(self):
                        for writer in self.writers:
                            writer.flush()

                # Redirect stdout to capture logs
                sys.stdout = DualWriter(original_stdout, log_capture)

                success = self._execute_test(test, test_detail)

                # Restore stdout
                sys.stdout = original_stdout

                test_execution_time = time.time() - test_start_time

                # Capture the log
                test_detail["execution_log"] = log_capture.getvalue()

                # Update test details
                test_detail["status"] = "PASSED" if success else "FAILED"
                test_detail["execution_time"] = round(test_execution_time, 2)
                test_details.append(test_detail)

                if success:
                    passed += 1
                    print(f"  ✅ PASSED: {test.name}")
                else:
                    failed += 1
                    print(f"  ❌ FAILED: {test.name}")
            except Exception as e:
                test_execution_time = time.time() - test_start_time
                failed += 1
                print(f"  ❌ ERROR: {test.name} - {e}")

                # Record failed test details
                test_detail = {
                    "name": test.name,
                    "description": test.description,
                    "tags": test.tags,
                    "status": "FAILED",
                    "execution_time": round(test_execution_time, 2),
                    "error": str(e),
                    "file_path": (
                        str(test.file_path) if hasattr(test, "file_path") else None
                    ),
                }
                test_details.append(test_detail)

        execution_time = time.time() - start_time
        success = failed == 0

        print(f"\n{'='*60}")
        print(f"Test Results: {passed} passed, {failed} failed")
        print(f"Execution time: {self._fmt_duration(execution_time)}")
        print(f"{'='*60}")

        report_path = None
        if generate_report:
            test_file_name = "test"
            if tests and hasattr(tests[0], "file_path"):
                test_file_name = Path(tests[0].file_path).stem

            reporter = HTMLReporter(Path("reports"))
            report_path = reporter.generate_report(
                test_details=test_details,
                total_tests=len(tests),
                passed=passed,
                failed=failed,
                execution_time=execution_time,
                test_file_name=test_file_name,
                report_name=report_name,
            )
            print(f"\n📊 HTML Report generated: {report_path}")
            print(f"   Open with: open {report_path}")

        return TestResult(
            success=success,
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=skipped,
            execution_time=execution_time,
            report_path=report_path,
            test_details=test_details,
        )

    def _execute_test(
        self, test: TestDefinition, test_detail: Dict[str, Any] = None
    ) -> bool:
        """Execute a single test with data iteration support"""
        try:
            # Store current test file name for screenshot naming
            if hasattr(test, "file_path"):
                self._current_test_file = Path(test.file_path).stem

            # Check for data source file
            if hasattr(test, "data_source") and test.data_source:
                # Load data from external file
                data_file = Path(test.data_source)
                if not data_file.is_absolute():
                    # Resolve relative to test file directory
                    test_dir = Path(test.file_path).parent
                    data_file = test_dir / data_file

                try:
                    test.data = DataLoader.load_from_file(data_file)
                    print(
                        f"    📊 Loaded {len(test.data)} data rows from {data_file.name}"
                    )
                except Exception as e:
                    print(f"      ❌ Failed to load data from {data_file}: {e}")
                    return False

            # Multi-browser run: repeat test for each browser in the list
            browsers = getattr(test, "browsers", None) or []
            if len(browsers) > 1:
                return self._execute_multi_browser_test(test, browsers, test_detail)

            # Check for data-driven testing
            if hasattr(test, "data") and test.data:
                return self._execute_data_driven_test(test)
            else:
                return self._execute_single_test(test, test_detail)
        except Exception as e:
            print(f"      Test execution failed: {e}")
            return False

    def _execute_multi_browser_test(
        self,
        test: TestDefinition,
        browsers: List[str],
        test_detail: Dict[str, Any] = None,
    ) -> bool:
        """Run _execute_single_test once per browser; all must pass."""
        import copy

        all_passed = True
        results: Dict[str, bool] = {}

        print(f"    🌐 Multi-browser run: {browsers}")

        for browser in browsers:
            print(f"\n    {'─'*44}")
            print(f"    🖥  Browser: {browser.upper()}")
            print(f"    {'─'*44}")

            # Deep-copy the test so each run gets a fresh variable state
            test_copy = copy.deepcopy(test)
            # Inject the browser override so BrowserService picks it up
            if test_copy.variables is None:
                test_copy.variables = {}
            test_copy.variables["_browser_override"] = browser
            # Clear the browsers list so nested call doesn't recurse
            test_copy.browsers = [browser]

            # Build a per-browser sub-detail that feeds into the parent detail
            browser_detail: Dict[str, Any] = {
                "name": f"{test.name} [{browser}]",
                "browser": browser,
            }

            if hasattr(test_copy, "data") and test_copy.data:
                ok = self._execute_data_driven_test(test_copy)
            else:
                ok = self._execute_single_test(test_copy, browser_detail)

            results[browser] = ok
            status = "✅ PASSED" if ok else "❌ FAILED"
            print(f"    {status} [{browser}]")
            if not ok:
                all_passed = False

        # Summary
        print(f"\n    {'─'*44}")
        print(f"    Multi-browser results:")
        for browser, ok in results.items():
            icon = "✅" if ok else "❌"
            print(f"      {icon} {browser}")

        if test_detail is not None:
            test_detail["multi_browser_results"] = {
                b: ("PASSED" if ok else "FAILED") for b, ok in results.items()
            }

        return all_passed

    def _execute_data_driven_test(self, test: "TestDefinition") -> bool:
        """Execute test with multiple data sets"""
        all_passed = True
        data_sets = test.data

        print(f"    Running {len(data_sets)} data iterations...")

        # Check if async execution is enabled
        async_mode = getattr(test, "async_execution", False)
        max_workers = getattr(test, "max_workers", 3)

        if async_mode:
            return self._execute_async_data_iterations(test, data_sets, max_workers)
        else:
            return self._execute_sequential_data_iterations(test, data_sets)

    def _execute_async_data_iterations(
        self, test: TestDefinition, data_sets: List[Dict], max_workers: int
    ) -> bool:
        """Execute data iterations asynchronously using thread pool"""
        print(
            f"    ⚡ Running {len(data_sets)} iterations ASYNCHRONOUSLY (max {max_workers} concurrent)..."
        )

        all_passed = True
        results = []

        def execute_single_iteration(iteration_data):
            """Execute a single data iteration in a thread"""
            iteration_num, data_set = iteration_data
            thread_id = threading.get_ident()

            try:
                # Merge test variables with current data set (include config vars)
                try:
                    _cfg_vars = self.config.variable_manager.get_all_variables()
                except Exception:
                    _cfg_vars = {}
                iteration_variables = {**_cfg_vars, **(test.variables or {})}
                iteration_variables.update(data_set)

                # Create a copy of the test for this iteration
                iteration_test = TestDefinition(
                    name=f"{test.name} (Async Iteration {iteration_num})",
                    description=test.description,
                    file_path=test.file_path,
                    tags=test.tags,
                    variables=iteration_variables,
                    setup=test.setup,
                    steps=test.steps,
                    cleanup=test.cleanup,
                    data_source=test.data_source,
                    data=None,  # Don't pass data to avoid infinite recursion
                    async_execution=False,  # Don't nest async execution
                    max_workers=1,
                )

                print(
                    f"    ⚙️  [Thread-{thread_id}] Starting iteration {iteration_num}..."
                )
                start_time = time.time()

                # Execute this iteration
                success = self._execute_single_test(iteration_test)

                execution_time = time.time() - start_time

                if success:
                    print(
                        f"    ✅ [Thread-{thread_id}] Iteration {iteration_num} PASSED ({execution_time:.1f}s)"
                    )
                else:
                    print(
                        f"    ❌ [Thread-{thread_id}] Iteration {iteration_num} FAILED ({execution_time:.1f}s)"
                    )

                return iteration_num, success, execution_time

            except Exception as e:
                print(
                    f"    ☠️  [Thread-{thread_id}] Iteration {iteration_num} ERROR: {e}"
                )
                return iteration_num, False, 0

        # Execute iterations in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="EasyBDD"
        ) as executor:
            # Prepare iteration data with numbering
            iteration_data = [(i + 1, data_set) for i, data_set in enumerate(data_sets)]

            # Submit all tasks
            print(f"    🚀 Submitting {len(iteration_data)} tasks to thread pool...")
            future_to_iteration = {
                executor.submit(execute_single_iteration, data): data[0]
                for data in iteration_data
            }

            # Collect results as they complete
            for future in future_to_iteration:
                try:
                    # Support long-running iterations (up to 10 hours per iteration)
                    # For 9-hour tests, this allows plenty of headroom
                    iteration_num, success, exec_time = future.result(
                        timeout=36000  # 10 hour timeout (36000 seconds) for long-running tests
                    )
                    results.append((iteration_num, success, exec_time))
                    if not success:
                        all_passed = False
                except Exception as e:
                    iteration_num = future_to_iteration[future]
                    print(f"    ⚠️  Iteration {iteration_num} exception: {e}")
                    all_passed = False

        # Summary
        passed_count = sum(1 for _, success, _ in results if success)
        failed_count = len(results) - passed_count
        total_time = sum(exec_time for _, _, exec_time in results)
        avg_time = total_time / len(results) if results else 0

        print(f"\n    📈 ASYNC EXECUTION SUMMARY:")
        print(f"       ✅ Passed: {passed_count}/{len(data_sets)}")
        print(f"       ❌ Failed: {failed_count}/{len(data_sets)}")
        print(f"       ⏱️  Avg time per iteration: {avg_time:.1f}s")
        print(
            f"       ⚡ Concurrency benefit: {(len(data_sets) * avg_time / max(1, max([t for _, _, t in results]))):.1f}x speedup"
        )

        return all_passed

    def _execute_sequential_data_iterations(
        self, test: TestDefinition, data_sets: List[Dict]
    ) -> bool:
        """Execute data iterations sequentially (original behavior)"""
        all_passed = True

        for i, data_set in enumerate(data_sets, 1):
            print(f"\n    === Data Iteration {i}/{len(data_sets)} ===")

            # Merge config vars + test vars + data set (data set wins)
            try:
                _cfg_vars = self.config.variable_manager.get_all_variables()
            except Exception:
                _cfg_vars = {}
            iteration_variables = {**_cfg_vars, **(test.variables or {})}
            iteration_variables.update(data_set)

            # Create a copy of the test for this iteration
            iteration_test = TestDefinition(
                name=f"{test.name} (Iteration {i})",
                description=test.description,
                file_path=test.file_path,
                tags=test.tags,
                variables=iteration_variables,
                setup=test.setup,
                steps=test.steps,
                cleanup=test.cleanup,
                data_source=test.data_source,
                data=None,  # Don't pass data to avoid infinite recursion
                async_execution=False,  # Don't nest async execution
                max_workers=1,
            )

            # Execute this iteration
            success = self._execute_single_test(iteration_test)
            if not success:
                all_passed = False
                print(f"    ❌ Data iteration {i} failed")
            else:
                print(f"    ✅ Data iteration {i} passed")

        return all_passed

    def _execute_single_test(
        self, test: TestDefinition, test_detail: Dict[str, Any] = None
    ) -> bool:
        """Execute a single test definition with setup, main steps, and cleanup"""
        # Capture start time for datalake metrics
        start_time = datetime.datetime.now()

        services = {}
        failed_step_info = None
        failure_screenshot = None
        step_logs = []
        soft_assert_manager = SoftAssertionManager()
        console_output = StringIO()
        test_passed = False
        # Start with config-level vars (collection_vars set by TestRail injected_vars),
        # then overlay test-level variables so the test's own vars take priority.
        # Assign back to test.variables so every reference in the loop below picks up
        # the full merged dict without needing individual call-site changes.
        try:
            config_vars = self.config.variable_manager.get_all_variables()
        except Exception:
            config_vars = {}
        variables = {**config_vars, **(test.variables or {})}
        test.variables = variables  # single source of truth for the rest of _run_test

        # Push test-level variables into the variable manager so services like
        # BrowserService can read them via config.get_variable() (e.g. headless: false).
        try:
            test_scope = next(
                (s for s in self.config.variable_manager.scopes if s.name == "test_variables"),
                None,
            )
            if test_scope is not None:
                test_scope.variables.clear()
                test_scope.update(test.variables or {})
        except Exception:
            pass

        # Store original stdout to capture console output
        original_stdout = sys.stdout

        # Create a dual writer for capturing console output
        class DualWriter:
            def __init__(self, original, capture):
                self.original = original
                self.capture = capture

            def write(self, text):
                self.original.write(text)
                self.capture.write(text)

            def flush(self):
                self.original.flush()
                self.capture.flush()

        # Initialize datalake logger if post_results enabled.
        # Skip when running under the TestRail runner — it posts one log per run.
        datalake_logger = None
        _under_testrail = bool(variables.get("_testrail_run_id"))
        if not _under_testrail:
            try:
                datalake_logger = DatalakeLogger(artifact_path="reports", post_results=True)
            except Exception as e:
                print(f"    ⚠️  Could not initialize datalake logger: {e}")

        # Redirect stdout to capture console output
        sys.stdout = DualWriter(original_stdout, console_output)

        try:
            # Load environment, collection, and suite variables
            from .variable_loader import load_all_variables

            # Detect workspace name from test path (e.g., tests/cases/OvrC/test.yaml -> OvrC)
            workspace_name = None
            if hasattr(test, "file_path") and test.file_path:
                test_path = Path(test.file_path)
                # Get parent directory name as workspace (e.g., OvrC, Networking)
                if len(test_path.parts) >= 2:
                    workspace_name = test_path.parts[-2]  # Second to last part

            # Load all variables (environment, collection, suite)
            # Note: suite_id would need to be passed if running from a suite
            project_root = Path.cwd()
            loaded_vars = load_all_variables(
                self.config.variable_manager,
                workspace_name=workspace_name,
                suite_id=None,  # Could be passed as a parameter if needed
                project_root=project_root,
            )

            if loaded_vars.get("environment"):
                print(
                    f"    📦 Loaded {len(loaded_vars['environment'])} environment variable(s)"
                )
            if loaded_vars.get("collection"):
                print(
                    f"    📦 Loaded {len(loaded_vars['collection'])} collection variable(s) for workspace: {workspace_name}"
                )
            if loaded_vars.get("suite"):
                print(f"    📦 Loaded {len(loaded_vars['suite'])} suite variable(s)")

            # Load device configuration if specified
            if test.device_config:
                print(f"    🔧 Loading device config: {test.device_config}")
                device_data = self.config.load_device_config(test.device_config)
                if device_data:
                    print(
                        f"    ✅ Device config loaded: {device_data.get('device_info', {}).get('name', test.device_config)}"
                    )
                else:
                    print(
                        f"    ⚠️  Warning: Could not load device config: {test.device_config}"
                    )

            # Configure video recording: only enabled when explicitly requested via test
            # definition (record_video: true) or the --record-video CLI flag.
            should_record = bool(
                getattr(test, "record_video", None) or getattr(self, "_record_video", False)
            )
            self.config.set_variable(
                "browser.video_recording.enabled", should_record, "session_overrides"
            )

            # Execute setup steps first
            if test.setup:
                print(f"    === Setup Phase ===")
                for i, step in enumerate(test.setup, 1):
                    step_description = self._get_step_description(step)
                    print(f"    Setup {i}/{len(test.setup)}: {step.action}")
                    if step_description:
                        print(f"           → {step_description}")

                    # Determine which service to use based on action
                    service_type = self._get_service_type(step.action)

                    if service_type not in services:
                        services[service_type] = self._create_service(service_type)

                    # Execute the setup step
                    try:
                        success = self._execute_step(
                            services[service_type],
                            step,
                            test.variables,
                            soft_assert_manager,
                            i,
                        )
                        if not success:
                            print(f"    ⚠️  Setup step {i} failed: {step.action}")
                            print(f"       Details: {step_description}")
                            print(f"       Continuing with main test...")
                            # Setup failures don't stop the test, but are logged
                    except Exception as e:
                        print(
                            f"    ⚠️  Setup step {i} failed with exception: {step.action}"
                        )
                        print(f"       Error: {str(e)}")
                        print(f"       Details: {step_description}")
                        print(f"       Continuing with main test...")

                    # Small delay between steps
                    time.sleep(0.5)

            # Execute main test steps
            self._run_logger.phase("Main Test Phase")
            total_steps = len(test.steps)

            for i, step in enumerate(test.steps, 1):
                display_step_params = self._resolve_step_params(step, test.variables or {})
                step_params = display_step_params.get("parameters", {}) if isinstance(display_step_params, dict) else {}
                prev_response = (test.variables or {}).get("last_response")

                self._run_logger.step_start(i, total_steps, step.action, step_params)

                # Determine which service to use based on action
                service_type = self._get_service_type(step.action)

                if service_type not in services:
                    services[service_type] = self._create_service(service_type)

                # Show step indicator in browser if browser service is available
                browser_service = services.get("browser")
                if not browser_service and service_type == "browser":
                    browser_service = services.get(service_type)

                if browser_service and hasattr(browser_service, "show_step_indicator"):
                    try:
                        browser_service.show_step_indicator(
                            step_number=i,
                            total_steps=total_steps,
                            step_action=step.action,
                            step_description=self._get_step_description(step),
                        )
                    except Exception:
                        pass

                # Execute the step
                try:
                    success = self._execute_step(
                        services[service_type],
                        step,
                        test.variables,
                        soft_assert_manager,
                        i,
                    )
                    if not success:
                        self._run_logger.step_fail(
                            i, step.action,
                            error="step returned False",
                            details=self._get_step_description(step),
                        )

                        # Add failed step to step_logs
                        step_logs.append(
                            {"step": i, "action": step.action, "status": "failed"}
                        )

                        # Capture failure screenshot (of state after last successful step)
                        failed_step_info = {
                            "step_number": i,
                            "step_action": step.action,
                            "step_details": self._get_step_description(step),
                        }
                        # Use the screenshot captured after the last successful step
                        failure_screenshot = getattr(self, "_last_step_screenshot", None)
                        if not failure_screenshot:
                            # Fallback: capture screenshot now if we don't have one
                            failure_screenshot = self._capture_failure_screenshot(
                                services.get("browser"), test.name, i
                            )

                        if test_detail is not None:
                            test_detail["failed_step"] = failed_step_info
                            test_detail["failure_screenshot"] = failure_screenshot
                            test_detail["step_logs"] = step_logs

                        return False
                    else:
                        self._run_logger.step_pass(i, test.variables or {}, prev_response)
                        step_logs.append(
                            {"step": i, "action": step.action, "status": "passed"}
                        )
                        
                        # Capture screenshot after each successful browser step
                        # This ensures we have a screenshot of the state before failure
                        browser_service = services.get("browser")
                        if browser_service and service_type == "browser":
                            try:
                                screenshot_path = self._capture_step_screenshot(
                                    browser_service, test.name, i
                                )
                                if screenshot_path:
                                    self._last_step_screenshot = screenshot_path
                                    # Also store in test_detail for report
                                    if test_detail is not None:
                                        if "step_screenshots" not in test_detail:
                                            test_detail["step_screenshots"] = []
                                        test_detail["step_screenshots"].append({
                                            "step": i,
                                            "screenshot": screenshot_path
                                        })
                            except Exception as e:
                                # Don't fail the test if screenshot capture fails
                                pass
                except Exception as e:
                    import traceback
                    self._run_logger.step_fail(
                        i, step.action,
                        error=str(e),
                        details=self._get_step_description(step),
                        traceback_str=traceback.format_exc(),
                    )

                    # Add failed step to step_logs
                    step_logs.append(
                        {"step": i, "action": step.action, "status": "failed"}
                    )

                    # Capture failure screenshot
                    failed_step_info = {
                        "step_number": i,
                        "step_action": step.action,
                        "step_details": step_description,
                        "error": str(e),
                        "traceback": traceback_str,
                    }
                    failure_screenshot = self._capture_failure_screenshot(
                        services.get("browser"), test.name, i
                    )

                    # Store failure info in test_detail if provided
                    if test_detail is not None:
                        test_detail["failed_step"] = failed_step_info
                        test_detail["failure_screenshot"] = failure_screenshot
                        test_detail["step_logs"] = step_logs

                    return False

                # Small delay between steps for visibility
                time.sleep(0.5)

            # Check soft assertions at end of main test phase
            if soft_assert_manager and soft_assert_manager.has_failures():
                print(soft_assert_manager.get_summary())
                if test_detail is not None:
                    test_detail["soft_assertions"] = soft_assert_manager.to_dict()
                test_passed = False
                # Store step_logs even on soft assertion failure
                if test_detail is not None:
                    test_detail["step_logs"] = step_logs
                return False

            # Store step_logs when test passes
            if test_detail is not None:
                test_detail["step_logs"] = step_logs

            test_passed = True
            return True

        except Exception as e:
            print(f"      Error executing test: {e}")
            test_passed = False
            return False

        finally:
            # Auto-disconnect OvrC service at end of test (if connected)
            # Access variables from test.variables which is modified during execution
            test_vars = (
                test.variables if hasattr(test, "variables") and test.variables else {}
            )
            ovrc_service = test_vars.get("_ovrc_service")
            if ovrc_service and ovrc_service.server_url and ovrc_service.is_connected():
                try:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    print(f"    🔌 Auto-disconnecting OvrC WebSocket...")
                    loop.run_until_complete(ovrc_service.disconnect())
                    print(f"    ✅ Auto-disconnected successfully")
                except Exception as e:
                    print(f"    ⚠️  Warning: Failed to auto-disconnect OvrC: {e}")
                finally:
                    if test.variables:
                        test.variables.pop("_ovrc_service", None)

            # Execute cleanup steps regardless of main test result
            if test.cleanup:
                try:
                    print(f"    === Cleanup Phase ===")
                    for i, step in enumerate(test.cleanup, 1):
                        step_description = self._get_step_description(step)
                        print(f"    Cleanup {i}/{len(test.cleanup)}: {step.action}")
                        if step_description:
                            print(f"           → {step_description}")

                        # Determine which service to use based on action
                        service_type = self._get_service_type(step.action)

                        if service_type not in services:
                            services[service_type] = self._create_service(service_type)

                        # Execute cleanup step - don't let failures stop cleanup
                        try:
                            success = self._execute_step(
                                services[service_type],
                                step,
                                test.variables,
                                soft_assert_manager,
                                i,
                            )
                            if not success:
                                print(f"    ⚠️  Cleanup step {i} failed: {step.action}")
                                print(f"       Details: {step_description}")
                        except Exception as cleanup_error:
                            print(
                                f"    ⚠️  Cleanup step {i} failed with exception: {step.action}"
                            )
                            print(f"       Error: {str(cleanup_error)}")
                            print(f"       Details: {step_description}")

                        # Small delay between cleanup steps
                        time.sleep(0.5)

                except Exception as cleanup_error:
                    print(f"    ⚠️  Cleanup phase error: {cleanup_error}")

            # Hide step indicator before closing browser
            browser_service = services.get("browser")
            if browser_service and hasattr(browser_service, "hide_step_indicator"):
                try:
                    browser_service.hide_step_indicator()
                except Exception:
                    pass

            # Clean up services first (browser needs to close to save video)
            for service in services.values():
                if hasattr(service, "close"):
                    try:
                        service.close()
                    except Exception as e:
                        print(f"    ⚠️  Service cleanup error: {e}")

            # Handle video recording AFTER browser closes
            if browser_service and hasattr(browser_service, "get_video_path"):
                try:
                    # Give browser time to finalize video after closing
                    time.sleep(1.0)

                    video_path = browser_service.get_video_path()
                    if video_path and video_path.exists():
                        print(f"    🎥 Video recorded: {video_path.name}")

                        # Store video path in test_detail
                        if test_detail is not None:
                            # Convert to relative path for HTML report
                            relative_path = f"videos/{video_path.name}"
                            test_detail["video_path"] = relative_path

                        # Check video recording mode
                        video_mode = browser_service._get_browser_config(
                            "video_recording.mode", "on-failure"
                        )

                        # Clean up video if test passed and mode is on-failure
                        if video_mode == "on-failure":
                            test_status = (
                                test_detail.get("status") if test_detail else None
                            )
                            if test_status == "passed":
                                print(f"    🗑️  Deleting video (test passed)")
                                browser_service.cleanup_video(video_path)
                                if test_detail:
                                    test_detail["video_path"] = None
                except Exception as e:
                    print(f"    ⚠️  Video handling error: {e}")
                    import traceback

                    print(f"    Traceback: {traceback.format_exc()}")

            # Restore stdout before posting to datalake
            sys.stdout = original_stdout

            # Check datalake configuration
            datalake_enabled = True
            post_on_failure_only = False
            if hasattr(self.config, "_raw_config"):
                config_dict = self.config._raw_config.get("config", {})
                datalake_config = config_dict.get("datalake", {})
                datalake_enabled = datalake_config.get("enabled", True)
                post_on_failure_only = datalake_config.get(
                    "post_on_failure_only", False
                )

            # Allow test/var case to opt out via no_datalake variable
            _tvars_check = (test.variables or {})
            no_datalake = _tvars_check.get("no_datalake", False)
            if isinstance(no_datalake, str):
                no_datalake = no_datalake.strip().lower() in ("true", "1", "yes")
            if no_datalake:
                datalake_enabled = False

            # Post test results to datalake (if enabled)
            if datalake_logger and datalake_enabled:
                # Skip if only posting failures and test passed
                if post_on_failure_only and test_passed:
                    print(
                        f"    ⏭️  Skipping datalake post (test passed, failure-only mode)"
                    )
                else:
                    try:
                        # Get test metadata from variables or use defaults
                        _tvars = test.variables or {}
                        product = _tvars.get("product", "Unknown")
                        product_category = _tvars.get("product_category", "Test")
                        # Accept both 'mac_address' and 'mac' variable names
                        mac_address = (
                            _tvars.get("mac_address")
                            or _tvars.get("mac")
                            or "00:00:00:00:00:00"
                        )
                        time_savings = _tvars.get("time_savings", 5.0)

                        # Get console output (captured during test)
                        console = console_output.getvalue() if console_output else ""

                        # Post to datalake
                        datalake_logger.datalake_post(
                            test_name=test.name,
                            product=product,
                            product_category=product_category,
                            mac_address=mac_address,
                            time_savings=time_savings,
                            start_time=start_time,
                            console=console,
                            run_url=(
                                test_detail.get("report_url", "") if test_detail else ""
                            ),
                            success=test_passed,
                            type="testrail",
                        )
                        print(f"    📊 Test metrics posted to datalake")
                    except Exception as e:
                        print(f"    ⚠️  Datalake posting error: {e}")
            elif not datalake_enabled:
                print(f"    ⏭️  Datalake logging disabled")

    def _capture_failure_screenshot(
        self, browser_service, test_name: str, step_number: int
    ) -> Optional[str]:
        """Capture screenshot on test failure (only for browser/UI tests)"""
        try:
            # Only capture screenshot if browser service exists and page is active
            if (
                browser_service
                and hasattr(browser_service, "take_screenshot")
                and hasattr(browser_service, "page")
                and browser_service.page
            ):
                # Create screenshots directory
                screenshots_dir = Path("reports/screenshots")
                screenshots_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename with test file prefix (without .png)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                # Get test file name if available
                test_file = getattr(self, "_current_test_file", "test")
                filename = f"{test_file}_failure_step{step_number}_{timestamp}"

                # Take screenshot
                browser_service.take_screenshot(filename)

                # Return relative path for HTML report (with .png extension)
                return f"screenshots/{filename}.png"
        except Exception as e:
            # Silently skip screenshot for non-UI tests
            pass
        return None

    def _capture_step_screenshot(
        self, browser_service, test_name: str, step_number: int
    ) -> Optional[str]:
        """Capture screenshot after successful step (for failure preview)"""
        try:
            # Only capture screenshot if browser service exists and page is active
            if (
                browser_service
                and hasattr(browser_service, "take_screenshot")
                and hasattr(browser_service, "page")
                and browser_service.page
            ):
                # Create screenshots directory
                screenshots_dir = Path("reports/screenshots")
                screenshots_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename with test file prefix (without .png)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                # Get test file name if available
                test_file = getattr(self, "_current_test_file", "test")
                filename = f"{test_file}_step{step_number}_{timestamp}"

                # Take screenshot
                browser_service.take_screenshot(filename)

                # Return relative path for HTML report (with .png extension)
                return f"screenshots/{filename}.png"
        except Exception as e:
            # Silently skip screenshot for non-UI tests
            pass
        return None

    def _get_step_description(self, step) -> str:
        """Extract a human-readable description from step parameters"""
        try:
            params = step.parameters if hasattr(step, "parameters") else {}
            parts = []

            # Extract key parameters that help identify the step
            if "selector" in params:
                parts.append(f"selector='{params['selector']}'")
            if "text" in params:
                parts.append(f"text='{params['text']}'")
            if "button" in params:
                parts.append(f"button='{params['button']}'")
            if "role" in params and "name" in params:
                parts.append(f"role='{params['role']}', name='{params['name']}'")
            if "value" in params:
                parts.append(f"value='{params['value']}'")
            if "label" in params:
                parts.append(f"label='{params['label']}'")
            if "url" in params:
                parts.append(f"url='{params['url']}'")
            if "field" in params:
                parts.append(f"field='{params['field']}'")

            return ", ".join(parts) if parts else ""
        except Exception:
            return ""

    def _get_service_type(self, action: str) -> str:
        """Determine which service type to use for an action"""
        action_lower = action.lower()

        # Control-flow pseudo-actions need no service
        if action_lower in ("for_loop", "while_loop", "try_except", "break", "continue"):
            return "eval"

        # Handle dot notation (e.g., browser.click, aws.get_latest)
        if "." in action_lower:
            service_prefix = action_lower.split(".")[0]
            # Map service prefixes to service types
            service_map = {
                "browser": "browser",
                "api": "api",
                "aws": "aws",
                "s3": "aws",
                "jsonrpc": "jsonrpc",
                "websocket": "websocket",
                "ws": "websocket",
                "ovrc": "ovrc",  # OvrC API service
                "test": "browser",  # test.assert, test.wait use browser context
                "command": "command",  # Command execution service
                "pagerduty": "pagerduty",  # PagerDuty incident management
                "pd": "pagerduty",  # Short alias for PagerDuty
                "serial": "serial",  # Serial port communication
                "telnet": "telnet",  # Telnet communication
                "eval": "eval",  # Session-stateful Python eval
            }
            return service_map.get(service_prefix, "browser")

        # Legacy format support (backward compatibility)
        if any(
            keyword in action_lower
            for keyword in ["browser", "click", "fill", "open", "screenshot"]
        ):
            return "browser"
        elif any(
            keyword in action_lower for keyword in ["api", "request", "post", "get"]
        ):
            return "api"
        elif any(keyword in action_lower for keyword in ["websocket", "ws"]):
            return "websocket"
        elif "ovrc" in action_lower:
            return "ovrc"
        elif any(
            keyword in action_lower
            for keyword in [
                "command",
                "ssh",
                "bash",
                "shell",
                "powershell",
                "batch",
                "python",
            ]
        ):
            return "command"
        else:
            return "browser"  # Default to browser

    def _create_service(self, service_type: str):
        """Create a service instance"""
        if service_type == "browser":
            from ..services.browser_service import BrowserService

            return BrowserService(self.config)
        elif service_type == "api":
            from ..services.api_service import APIService

            # Pass the GlobalConfigManager instead of raw config
            try:
                return APIService(self.config)
            except Exception as e:
                print(f"Error creating API service: {e}")
                import traceback

                traceback.print_exc()
                raise
        elif service_type == "command":
            return CommandService(self.config)
        elif service_type == "pagerduty":
            from ..services.pagerduty_service import PagerDutyService
            return PagerDutyService(logger=print)
        elif service_type == "serial":
            from ..services.serial_service import SerialService
            return SerialService(self._connection_pool)
        elif service_type == "telnet":
            from ..services.telnet_service import TelnetService
            return TelnetService(self._connection_pool)
        elif service_type == "websocket":
            from ..services.websocket_service import WebSocketService
            return WebSocketService(self._connection_pool)
        elif service_type == "eval":
            return None  # eval actions are handled directly in _execute_custom_action
        else:
            # For now, return a mock service for other types
            return MockService(service_type)

    def _execute_custom_action(
        self,
        action: str,
        step_params: dict,
        variables: dict,
        soft_assert_manager: SoftAssertionManager = None,
    ) -> bool:
        """Execute custom actions if available"""
        try:
            action_lower = action.lower()

            # Check soft assertions action
            if action_lower in ["check soft assertions", "test.check_assertions"]:
                if soft_assert_manager and soft_assert_manager.has_failures():
                    soft_assert_manager.raise_if_failures()
                else:
                    print("      ✓ No soft assertion failures")
                return True

            # Sleep / wait action (no browser required)
            if action_lower in ["test.sleep", "sleep", "test.wait", "wait"]:
                params = self._get_params(step_params)
                seconds = float(
                    params.get("seconds")
                    or params.get("duration")
                    or params.get("timeout")
                    or 1
                )
                print(f"      ⏳ Sleeping {seconds}s...")
                time.sleep(seconds)
                return True

            # Log / print action (no service required — just prints a message)
            # Supports:
            #   - action: test.print / message: "..."   (explicit)
            #   - test.print: "..."                     (shorthand scalar)
            if action_lower in ["test.log", "log", "test.print", "print"]:
                params = self._get_params(step_params)
                message = str(
                    params.get("message")
                    or params.get("text")
                    or params.get("value")
                    or ""
                )
                if hasattr(self.config, "substitute_variables"):
                    message = self.config.substitute_variables(message, variables)
                print(f"      📝 {message}")
                return True

            # Custom assertion actions (support both formats)
            if action_lower in ["assert", "test.assert"]:
                return self._handle_assert_action(step_params, variables)
            elif action_lower in ["assert json schema", "test.assert_schema"]:
                return self._handle_json_schema_action(step_params, variables)
            elif action_lower in ["assert response", "test.assert_response"]:
                return self._handle_response_assertion(step_params, variables)
            elif action_lower in ["test.extract", "extract"]:
                return self._handle_extract_action(step_params, variables)

            # JSON-RPC WebSocket actions (support both formats)
            if (
                action_lower.startswith("jsonrpc")
                or action_lower.startswith("jsonrpc.")
                or action_lower.startswith("ovrc")
                or action_lower.startswith("ovrc.")
            ):
                return self._handle_ovrc_action(action, step_params, variables)

            # AWS S3 actions (support both formats)
            if (
                action_lower.startswith("aws")
                or action_lower.startswith("s3.")
                or "s3" in action_lower
            ):
                return self._handle_aws_action(action, step_params, variables)

            # PagerDuty actions (support both formats)
            if (
                action_lower.startswith("pagerduty")
                or action_lower.startswith("pd.")
                or action_lower.startswith("pagerduty.")
            ):
                return self._handle_pagerduty_action(action, step_params, variables)

            # Test execution action (run another test as a step)
            if action_lower in ["test.run", "run test", "execute test"]:
                return self._handle_test_run_action(
                    step_params, variables, soft_assert_manager
                )

            # Command execution actions
            # Handle both dot notation (command.ssh) and normalized format (command ssh)
            # Check if action starts with "command" and contains a command type
            command_types = ["ssh", "shell", "bash", "sh", "zsh", "fish", "tcsh", "csh", "dash", "ksh", "powershell", "pwsh", "cmd", "batch", "python"]
            if action_lower.startswith("command") and any(
                cmd_type in action_lower for cmd_type in command_types
            ):
                return self._handle_command_action(action, step_params, variables)

            # Wake-on-LAN
            if action_lower.startswith("wol"):
                return self._handle_wol_action(action, step_params, variables)

            # Serial port actions
            if action_lower.startswith("serial"):
                return self._handle_serial_action(action, step_params, variables)

            # Telnet actions
            if action_lower.startswith("telnet"):
                return self._handle_telnet_action(action, step_params, variables)

            # SSH actions (stateful Paramiko sessions — distinct from command.ssh)
            if action_lower.startswith("ssh."):
                return self._handle_ssh_action(action, step_params, variables)

            # LGIP IR control actions
            if action_lower.startswith("lgip"):
                return self._handle_lgip_action(action, step_params, variables)

            # WebSocket actions
            if action_lower.startswith("websocket") or action_lower.startswith("ws."):
                return self._handle_websocket_action(action, step_params, variables)

            # Eval actions (session-stateful Python execution)
            if action_lower.startswith("eval"):
                return self._handle_eval_action(action, step_params, variables)

            # Check if we have custom actions defined
            if hasattr(self.config, "get_custom_action"):
                custom_action = self.config.get_custom_action(action)
                if custom_action:
                    print(f"      Executing custom action: {action}")
                    # Execute custom action logic here
                    # This would integrate with custom action modules
                    return True

            # Check for device-specific actions
            device_actions = ["power_cycle", "network_port", "stress_test"]
            if any(device_action in action for device_action in device_actions):
                print(
                    f"      Custom action '{action}' detected but not " f"implemented"
                )
                # For now, just log and continue
                return False

            return False
        except Exception as e:
            # Don't catch JSON-RPC, OvrC, or Command failures - let them propagate
            # to avoid "Unknown action" fallthrough
            action_lower_check = action.lower()
            if (
                action_lower_check.startswith("jsonrpc")
                or action_lower_check.startswith("ovrc")
                or action_lower_check.startswith("command")
            ):
                raise
            # Re-raise eval failures — they should not silently fall through to
            # the browser handler which would report a confusing "Unknown action" error.
            if action_lower_check.startswith("eval"):
                raise
            # Re-raise assert/websocket/telnet/serial failures so they propagate
            # as proper step failures rather than "Unknown action" browser fallthrough.
            if (
                action_lower_check in ("assert", "test.assert", "assert json schema",
                                       "test.assert_schema", "assert response",
                                       "test.assert_response", "test.extract", "extract")
                or action_lower_check.startswith("websocket")
                or action_lower_check.startswith("ws.")
                or action_lower_check.startswith("telnet")
                or action_lower_check.startswith("serial")
                or action_lower_check.startswith("wol")
            ):
                raise
            print(f"      Warning: Custom action '{action}' failed: {e}")
            return False

    def _execute_conditional_step(
        self,
        service,
        step,
        variables: dict,
        soft_assert_manager=None,
        step_number: int = 0,
    ) -> bool:
        """Execute a conditional if/then/else step"""
        condition = step.condition

        # Substitute variables in condition
        if hasattr(self.config, "substitute_variables"):
            condition = self.config.substitute_variables(condition, variables)

        print(f"      Evaluating condition: {condition}")

        # Evaluate the condition
        try:
            # Create a safe evaluation context
            eval_context = variables.copy()
            result = safe_eval(condition, eval_context)

            print(f"      Condition result: {result}")

            # Execute appropriate branch
            if result:
                if step.then_steps:
                    print(
                        f"      → Executing THEN branch "
                        f"({len(step.then_steps)} steps)"
                    )
                    for i, then_step in enumerate(step.then_steps, 1):
                        svc_type = self._get_service_type(then_step.action)
                        svc = self._create_service(svc_type)
                        success = self._execute_step(
                            svc, then_step, variables, soft_assert_manager, step_number
                        )
                        if not success:
                            return False
                    return True
                else:
                    print(f"      → Condition true, no THEN steps")
                    return True
            else:
                if step.else_steps:
                    print(
                        f"      → Executing ELSE branch "
                        f"({len(step.else_steps)} steps)"
                    )
                    for i, else_step in enumerate(step.else_steps, 1):
                        svc_type = self._get_service_type(else_step.action)
                        svc = self._create_service(svc_type)
                        success = self._execute_step(
                            svc, else_step, variables, soft_assert_manager, step_number
                        )
                        if not success:
                            return False
                    return True
                else:
                    print(f"      → Condition false, no ELSE steps")
                    return True
        except Exception as e:
            print(f"      ✗ Condition evaluation failed: {e}")
            raise ValueError(f"Invalid condition '{condition}': {e}")

    # ------------------------------------------------------------------ #
    # Control flow: FOR / WHILE / TRY                                      #
    # ------------------------------------------------------------------ #

    def _eval_expr(self, expr: str, variables: dict) -> object:
        """Substitute variables then evaluate a Python expression safely."""
        if hasattr(self.config, "substitute_variables"):
            expr = self.config.substitute_variables(expr, variables)
        ctx = {**variables, **self._eval_state}
        return safe_eval(expr, ctx)

    def _run_loop_body(
        self,
        body: list,
        variables: dict,
        soft_assert_manager,
        step_number: int,
        break_if: str = None,
        continue_if: str = None,
    ) -> bool:
        """Execute loop body steps; propagates _BreakSignal / _ContinueSignal."""
        for loop_step in body:
            # Inline break_if / continue_if guards on the step itself
            if getattr(loop_step, "action", "") == "break":
                raise _BreakSignal()
            if getattr(loop_step, "action", "") == "continue":
                raise _ContinueSignal()

            svc_type = self._get_service_type(loop_step.action)
            svc = self._create_service(svc_type)
            success = self._execute_step(svc, loop_step, variables, soft_assert_manager, step_number)
            if not success:
                return False

        # Per-iteration guards declared on the loop itself
        if continue_if and self._eval_expr(continue_if, variables):
            raise _ContinueSignal()
        if break_if and self._eval_expr(break_if, variables):
            raise _BreakSignal()
        return True

    def _execute_for_loop(self, step, variables: dict, soft_assert_manager, step_number: int) -> bool:
        """Execute a for_each loop step."""
        iterable = self._eval_expr(step.for_each, variables)
        loop_var = step.loop_var or "item"
        limit = step.loop_limit or 1000

        if not hasattr(iterable, "__iter__"):
            raise ValueError(f"for_each expression is not iterable: {step.for_each!r}")

        items = list(iterable)
        if len(items) > limit:
            print(f"      ⚠ FOR loop: clamping {len(items)} items to limit {limit}")
            items = items[:limit]

        print(f"      → FOR {loop_var} in <{len(items)} items>")
        for idx, item in enumerate(items):
            variables[loop_var] = item
            try:
                ok = self._run_loop_body(
                    step.loop_steps or [],
                    variables,
                    soft_assert_manager,
                    step_number,
                    break_if=step.break_if,
                    continue_if=step.continue_if,
                )
                if not ok:
                    return False
            except _BreakSignal:
                print(f"      → FOR loop: BREAK at iteration {idx + 1}")
                break
            except _ContinueSignal:
                continue

        variables.pop(loop_var, None)
        return True

    def _execute_while_loop(self, step, variables: dict, soft_assert_manager, step_number: int) -> bool:
        """Execute a while loop step."""
        condition = step.while_condition
        limit = step.loop_limit or 1000
        iteration = 0

        print(f"      → WHILE {condition}")
        while iteration < limit:
            if not self._eval_expr(condition, variables):
                break
            iteration += 1
            try:
                ok = self._run_loop_body(
                    step.loop_steps or [],
                    variables,
                    soft_assert_manager,
                    step_number,
                    break_if=step.break_if,
                    continue_if=step.continue_if,
                )
                if not ok:
                    return False
            except _BreakSignal:
                print(f"      → WHILE loop: BREAK at iteration {iteration}")
                break
            except _ContinueSignal:
                continue
        else:
            print(f"      ⚠ WHILE loop reached iteration limit ({limit})")

        return True

    def _execute_try_except(self, step, variables: dict, soft_assert_manager, step_number: int) -> bool:
        """Execute a try/except/finally step."""
        success = True
        try:
            for try_step in (step.try_steps or []):
                svc_type = self._get_service_type(try_step.action)
                svc = self._create_service(svc_type)
                ok = self._execute_step(svc, try_step, variables, soft_assert_manager, step_number)
                if not ok:
                    success = False
                    break
        except Exception as exc:
            print(f"      → TRY failed: {exc}")
            if step.except_steps:
                variables["_exception"] = str(exc)
                for ex_step in step.except_steps:
                    svc_type = self._get_service_type(ex_step.action)
                    svc = self._create_service(svc_type)
                    self._execute_step(svc, ex_step, variables, soft_assert_manager, step_number)
            else:
                success = False
        finally:
            if step.finally_steps:
                print(f"      → FINALLY")
                for fin_step in step.finally_steps:
                    svc_type = self._get_service_type(fin_step.action)
                    svc = self._create_service(svc_type)
                    try:
                        self._execute_step(svc, fin_step, variables, soft_assert_manager, step_number)
                    except Exception as fin_exc:
                        print(f"      ⚠ FINALLY step error: {fin_exc}")

        return success

    def _resolve_url_with_variables(self, url: str, variables: dict) -> str:
        """Resolve URL with variable substitution, handling URL-encoded variables"""
        from urllib.parse import unquote

        # If URL contains URL-encoded braces, decode them first
        if "%7b" in url.lower() or "%7d" in url.lower():
            url = unquote(url)

        # Ensure all variables are available
        all_vars = variables.copy()
        if hasattr(self.config, "get_all_variables"):
            all_vars.update(self.config.get_all_variables())

        # Do multiple passes to resolve nested variables
        if hasattr(self.config, "substitute_variables"):
            max_passes = 5
            for _ in range(max_passes):
                new_url = self.config.substitute_variables(url, all_vars)
                if new_url == url:  # No more substitutions
                    break
                url = new_url
        else:
            url = self._replace_variables(url, all_vars)

        return url

    def _handle_assert_action(self, step_params: dict, variables: dict) -> bool:
        """Handle Assert action for custom expression evaluation."""
        # Extract parameters using helper
        expression = self._get_param(step_params, "expression", "")
        message = self._get_param(
            step_params, "message", f"Assertion failed: {expression}"
        )

        if not expression:
            raise ValueError("Assert action requires 'expression' parameter")

        # Create assertion engine with variables context
        engine = AssertionEngine(context=variables)
        result = engine.assert_expression(expression, message, variables)

        if result.passed:
            print(f"      ✓ Assertion passed: {expression}")
            return True
        else:
            print(f"      ✗ Assertion failed: {result.message}")
            if result.expected is not None and result.actual is not None:
                print(f"        Expected: {result.expected}")
                print(f"        Actual: {result.actual}")
            raise AssertionError(result.message)

    def _handle_json_schema_action(self, step_params: dict, variables: dict) -> bool:
        """Handle Assert JSON schema action."""
        # Extract parameters using helper
        data = self._get_param(step_params, "data") or self._get_param(
            step_params, "response"
        )
        schema = self._get_param(step_params, "schema") or self._get_param(
            step_params, "schema_file"
        )

        if not data:
            raise ValueError(
                "Assert JSON schema requires 'data' or 'response' parameter"
            )
        if not schema:
            raise ValueError(
                "Assert JSON schema requires 'schema' or 'schema_file' parameter"
            )

        # Resolve data from variables
        # The variable substitution converts dicts to strings, so check variables directly
        if isinstance(data, str):
            # Try to find the variable from the stringified value
            if data.startswith("{") or data.startswith("["):
                # This is a stringified dict/list from variable substitution
                # Find the original variable by checking which matches
                for var_name, var_value in variables.items():
                    if isinstance(var_value, (dict, list)) and str(
                        var_value
                    ).startswith(data[:50]):
                        data = var_value
                        break
            # Try direct variable lookup
            elif data in variables:
                data = variables[data]

        # Create validator and validate
        validator = JSONSchemaValidator()
        result = validator.validate(data, schema)

        if result.passed:
            print(f"      ✓ JSON schema validation passed")
            return True
        else:
            print(f"      ✗ JSON schema validation failed: {result.message}")
            if result.details:
                print(f"        Details: {result.details}")
            raise AssertionError(result.message)

    def _handle_response_assertion(self, step_params: dict, variables: dict) -> bool:
        """Handle Assert response action for HTTP response validation."""
        # Extract parameters using helper
        response = self._get_param(
            step_params, "response", "last_response"
        )  # Default to last_response
        expectations = self._get_param(step_params, "expect") or self._get_param(
            step_params, "expectations"
        )

        # Backward compatibility: support old "status" or "status_code" parameter
        status_code = self._get_param(step_params, "status") or self._get_param(
            step_params, "status_code"
        )
        if status_code and not expectations:
            # Convert old format to new expectations format
            expectations = {"status_code": status_code}

        if not response:
            # Try to use last_response if available
            if "last_response" in variables:
                response = "last_response"
            else:
                raise ValueError(
                    "Assert response requires 'response' parameter or a previous API call"
                )

        if not expectations:
            raise ValueError(
                "Assert response requires 'expect'/'expectations' parameter or 'status'/'status_code' parameter"
            )

        # Resolve response from variables
        # The variable substitution converts dicts to strings, so we need to check variables directly
        if isinstance(response, str):
            # Try to find the variable name from the original step_params before substitution
            # Check if this looks like it was a variable (starts with dict marker '{')
            if response.startswith("{") or response.startswith("["):
                # This is a stringified dict/list from variable substitution
                # Try to find the original variable name by checking which variable matches
                for var_name, var_value in variables.items():
                    if isinstance(var_value, dict) and str(var_value).startswith(
                        response[:50]
                    ):
                        response = var_value
                        break
            # Try direct variable lookup
            elif response in variables:
                response = variables[response]

        # Convert requests.Response object to dict format if needed
        import requests

        if isinstance(response, requests.Response):
            content_type = response.headers.get("content-type", "")
            is_json = content_type.startswith("application/json")
            response_dict = {
                "status": response.status_code,
                "status_code": response.status_code,  # Support both keys
                "headers": dict(response.headers),
                "body": response.text,
                "data": response.json() if is_json else response.text,
            }
            response = response_dict

        # Create validator and validate
        validator = ResponseValidator()
        result = validator.validate_response(response, expectations)

        if result.passed:
            print(f"      ✓ Response validation passed")
            return True
        else:
            print(f"      ✗ Response validation failed: {result.message}")
            if result.details:
                failures = result.details.get("failures", [])
                for failure in failures:
                    print(f"        - {failure}")
            raise AssertionError(result.message)

    def _handle_extract_action(self, step_params: dict, variables: dict) -> bool:
        """Handle test.extract — parse a field from a key:value text response.

        Supports two response formats:
          - CLI text:  'Switch Name          : AN-220-SW-R-16-POE'
          - JSON dict: {'restful_res': {'token': 'abc...'}}  (dot-notation field)

        Parameters
        ----------
        field     : field name to search for (case-insensitive substring match on the key)
        from      : variable name to read from (default: last_response)
        store_as  : variable name to store the extracted value
        equals    : if given, assert the extracted value equals this (after variable substitution)
        contains  : if given, assert the extracted value contains this string
        message   : custom assertion failure message
        """
        import re as _re
        params = self._get_params(step_params)

        field    = str(params.get("field", ""))
        from_var = str(params.get("from", "last_response"))
        store_as = str(params.get("store_as", ""))
        equals   = params.get("equals")
        contains = params.get("contains")
        message  = params.get("message", "")

        if not field:
            raise ValueError("test.extract requires 'field'")

        # Resolve the source variable
        source = variables.get(from_var, variables.get("last_response", ""))

        extracted = None

        if isinstance(source, dict):
            # JSON/dict response — dot-notation field lookup
            parts = field.split(".")
            node = source
            for part in parts:
                if isinstance(node, dict):
                    # case-insensitive key search
                    match = next((v for k, v in node.items() if k.lower() == part.lower()), None)
                    node = match
                else:
                    node = None
                    break
            extracted = str(node) if node is not None else None
        else:
            # CLI text response — scan for "Key ... : Value" lines
            text = str(source)
            field_lower = field.lower()
            for line in text.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    if field_lower in key.lower():
                        extracted = val.strip()
                        break

        if extracted is None:
            raise AssertionError(
                f"test.extract: field {field!r} not found in {from_var}"
            )

        print(f"      🔍 extract: {field!r} → {extracted!r}")

        # Store if requested
        if store_as:
            variables[store_as] = extracted
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, extracted, "runtime_data")

        # Assert equals
        if equals is not None:
            equals_str = str(equals)
            if hasattr(self.config, "substitute_variables"):
                equals_str = self.config.substitute_variables(equals_str, variables)
            if extracted != equals_str:
                msg = message or f"Expected {field!r} = {equals_str!r}, got {extracted!r}"
                raise AssertionError(msg)
            print(f"      ✅ {field!r} == {equals_str!r}")

        # Assert contains
        if contains is not None:
            contains_str = str(contains)
            if hasattr(self.config, "substitute_variables"):
                contains_str = self.config.substitute_variables(contains_str, variables)
            if contains_str not in extracted:
                msg = message or f"Expected {field!r} to contain {contains_str!r}, got {extracted!r}"
                raise AssertionError(msg)
            print(f"      ✅ {field!r} contains {contains_str!r}")

        return True

    def _ensure_ovrc_connection(
        self, variables: dict, params: dict = None
    ) -> OvrCApiService:
        """Ensure OvrC service is connected, auto-connect if needed."""
        import asyncio

        # Get existing service
        ovrc_service = variables.get("_ovrc_service")

        # Check if service exists and is connected (for WebSocket)
        if ovrc_service:
            # For HTTP-only services, they're always "connected"
            if ovrc_service.api_base_url and not ovrc_service.server_url:
                return ovrc_service
            # For WebSocket services, check connection status
            if ovrc_service.server_url and ovrc_service.is_connected():
                return ovrc_service

        # Need to create/connect - get connection parameters from variables or params
        if params is None:
            params = {}

        # Try to get connection parameters from variables (set during ovrc.connect)
        # Also check for common variable names
        server_url = (
            params.get("server_url")
            or variables.get("ovrc_server_url")
            or variables.get("server_url")
            or variables.get("ws_url")
            or variables.get("websocket_url")
        )
        device_id = (
            params.get("device_id")
            or variables.get("ovrc_device_id")
            or variables.get("device_id")
            or variables.get("mac")
            or variables.get("device_mac")
        )
        api_base_url = (
            params.get("api_base_url")
            or variables.get("ovrc_api_base_url")
            or variables.get("api_base_url")
            or variables.get("api_url")
        )

        # If no connection parameters found, raise error
        if not server_url and not api_base_url:
            raise ValueError(
                "OvrC connection required. Either:\n"
                "1. Call 'ovrc.connect' first with server_url or api_base_url, OR\n"
                "2. Set variables: ovrc_server_url/ovrc_api_base_url, ovrc_device_id"
            )

        # Get other connection parameters from variables
        protocol = (
            params.get("protocol")
            or variables.get("ovrc_protocol")
            or "firmware-protocol"
        )
        session_id = params.get("session_id") or variables.get("ovrc_session_id")
        verify_ssl = params.get("verify_ssl")
        if verify_ssl is None:
            verify_ssl = variables.get("ovrc_verify_ssl", True)
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() in ("true", "1", "yes", "on")

        # Get authentication parameters
        auth_type = (
            params.get("auth_type") or variables.get("ovrc_auth_type") or "bearer"
        )
        auth_token = (
            params.get("auth_token")
            or variables.get("ovrc_auth_token")
            or variables.get("auth_token")
        )
        auth_username = (
            params.get("auth_username")
            or variables.get("ovrc_auth_username")
            or variables.get("username")
        )
        auth_password = (
            params.get("auth_password")
            or variables.get("ovrc_auth_password")
            or variables.get("password")
        )
        api_key = (
            params.get("api_key")
            or variables.get("ovrc_api_key")
            or variables.get("api_key")
        )
        api_key_header = (
            params.get("api_key_header")
            or variables.get("ovrc_api_key_header")
            or "X-API-Key"
        )
        custom_auth_headers = (
            params.get("custom_auth_headers")
            or variables.get("ovrc_custom_auth_headers")
            or {}
        )

        # Get verbose logging
        verbose_logging = (
            variables.get("verbose_logging", True)
            or variables.get("show_full_response", False)
            or params.get("verbose_logging", True)
            or params.get("show_full_response", False)
        )
        if isinstance(verbose_logging, str):
            verbose_logging = verbose_logging.lower() in ("true", "1", "yes", "on")

        # Create service
        ovrc_service = OvrCApiService(
            server_url=server_url if server_url else None,
            device_id=device_id if device_id else None,
            session_id=session_id,
            protocol=protocol,
            verify_ssl=verify_ssl,
            extra_headers=params.get("headers", {}),
            api_base_url=api_base_url if api_base_url else None,
            auth_type=auth_type,
            auth_token=auth_token,
            auth_username=auth_username,
            auth_password=auth_password,
            api_key=api_key,
            api_key_header=api_key_header,
            custom_auth_headers=custom_auth_headers,
            verbose_logging=verbose_logging,
        )

        # Connect WebSocket if server_url provided
        if server_url:
            loop = asyncio.get_event_loop()
            print(f"      🔌 Auto-connecting to OvrC WebSocket: {server_url}")
            success = loop.run_until_complete(ovrc_service.connect())
            if not success:
                raise ConnectionError("Failed to auto-connect to OvrC WebSocket server")
            print(f"      ✅ Auto-connected successfully")

        # Store service in variables
        variables["_ovrc_service"] = ovrc_service

        # Store connection parameters in variables for future auto-connect
        if server_url:
            variables["ovrc_server_url"] = server_url
        if device_id:
            variables["ovrc_device_id"] = device_id
        if api_base_url:
            variables["ovrc_api_base_url"] = api_base_url
        if protocol:
            variables["ovrc_protocol"] = protocol

        return ovrc_service

    def _handle_ovrc_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle OvrC API actions (WebSocket and HTTP)."""
        import asyncio

        # Get or create OvrC API service from variables
        ovrc_service = variables.get("_ovrc_service")

        # Extract parameters using helper
        params = self._get_params(step_params)
        action_lower = action.lower()

        try:
            # Handle HTTP API requests (GET, POST, PUT, PATCH, DELETE)
            # Support both "ovrc.http.get", "ovrc.http.request", "ovrc http get", etc.
            if (
                action_lower.startswith("ovrc.http.")
                or action_lower.startswith("ovrc http")
                or action_lower.startswith("ovrc api")
            ):
                # Auto-connect if needed for HTTP requests
                if not ovrc_service or (
                    ovrc_service.server_url and not ovrc_service.is_connected()
                ):
                    ovrc_service = self._ensure_ovrc_connection(variables, params)
                return self._handle_ovrc_http_action(
                    action, step_params, variables, ovrc_service
                )

            # Handle WebSocket connection
            if "connect" in action_lower and "disconnect" not in action_lower:
                # Extract connection parameters
                server_url = params.get("url", "") or params.get("server_url", "")
                device_id = params.get("device_id", "")
                protocol = params.get("protocol", "firmware-protocol")
                session_id = params.get("session_id", None)

                # HTTP API configuration
                api_base_url = params.get("api_base_url", "")
                auth_type = params.get("auth_type", "bearer")
                auth_token = params.get("auth_token", "")
                auth_username = params.get("auth_username", "")
                auth_password = params.get("auth_password", "")
                api_key = params.get("api_key", "")
                api_key_header = params.get("api_key_header", "X-API-Key")
                custom_auth_headers = params.get("custom_auth_headers", {})

                if not server_url and not api_base_url:
                    raise ValueError(
                        "OvrC connect requires 'server_url' (WebSocket) or 'api_base_url' (HTTP)"
                    )

                # Optional parameters
                verify_ssl = params.get("verify_ssl", True)
                extra_headers = params.get("headers", {})

                # Get verbose logging flag from variables or params
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or params.get("verbose_logging", True)
                    or params.get("show_full_response", False)
                )
                # Convert string "true"/"false" to boolean
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )

                # Create service
                ovrc_service = OvrCApiService(
                    server_url=server_url if server_url else None,
                    device_id=device_id if device_id else None,
                    session_id=session_id,
                    protocol=protocol,
                    verify_ssl=verify_ssl,
                    extra_headers=extra_headers,
                    api_base_url=api_base_url if api_base_url else None,
                    auth_type=auth_type,
                    auth_token=auth_token,
                    auth_username=auth_username,
                    auth_password=auth_password,
                    api_key=api_key,
                    api_key_header=api_key_header,
                    custom_auth_headers=custom_auth_headers,
                    verbose_logging=verbose_logging,
                )

                # Connect WebSocket if server_url provided
                if server_url:
                    loop = asyncio.get_event_loop()
                    success = loop.run_until_complete(ovrc_service.connect())
                    if not success:
                        raise ConnectionError(
                            "Failed to connect to OvrC WebSocket server"
                        )

                # Store service in variables
                variables["_ovrc_service"] = ovrc_service

                # Update verbose logging if service already exists and flag changed
                if verbose_logging:
                    print(
                        f"      🔍 Verbose logging enabled - full request/response details will be shown"
                    )

                # If a method was specified, call it immediately after connecting
                method_name = params.get("method", "")
                if method_name and server_url:
                    loop2 = asyncio.get_event_loop()
                    print(f"      📡 Calling {method_name} after connect...")
                    method_params = params.get("params", {}) or {"deviceId": device_id, "version": 0}
                    response = loop2.run_until_complete(
                        ovrc_service.send_request(method_name, method_params)
                    )
                    result = response.result if response else None
                    store_as = params.get("store_as", "")
                    if store_as:
                        variables[store_as] = result
                        variables["last_response"] = result
                        print(f"      💾 Stored {method_name} response as: {store_as}")
                    elif result is not None:
                        variables["last_response"] = result

                return True

            # All other WebSocket actions - auto-connect if needed
            # Check if we need to auto-connect (service doesn't exist or is disconnected)
            needs_connection = False
            if not ovrc_service:
                needs_connection = True
            elif ovrc_service.server_url and not ovrc_service.is_connected():
                needs_connection = True

            if needs_connection:
                ovrc_service = self._ensure_ovrc_connection(variables, params)
                # Update the variables with the new service
                variables["_ovrc_service"] = ovrc_service

            loop = asyncio.get_event_loop()

            # Handle generic send/call action (flexible method name)
            if "send" in action_lower or "call" in action_lower:
                method = self._get_param(step_params, "method", "")
                if not method:
                    raise ValueError("OvrC send/call requires 'method' parameter")

                method_params = self._get_param(step_params, "params", {})
                # Handle different formats: dict, JSON string, or None
                if isinstance(method_params, str):
                    # Try to parse as JSON
                    method_params = method_params.strip()
                    if not method_params or method_params == "{}":
                        method_params = {}
                    else:
                        try:
                            import json

                            method_params = json.loads(method_params)
                        except json.JSONDecodeError:
                            # If JSON parsing fails, treat as empty
                            print(
                                f"      ⚠️  Warning: Could not parse params as JSON, using empty dict"
                            )
                            method_params = {}
                elif method_params is None:
                    method_params = {}
                elif not isinstance(method_params, dict):
                    # If it's not a dict or string, try to convert
                    try:
                        method_params = dict(method_params)
                    except:
                        method_params = {}

                timeout = self._get_param(step_params, "timeout", 10.0)
                if isinstance(timeout, str):
                    try:
                        timeout = float(timeout)
                    except:
                        timeout = 10.0

                # Update verbose logging if changed
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or params.get("verbose_logging", True)
                    or params.get("show_full_response", False)
                )
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )
                if ovrc_service.verbose_logging != verbose_logging:
                    ovrc_service.verbose_logging = verbose_logging

                print(f"      📤 Sending OvrC command: {method}")
                if method_params:
                    if ovrc_service.verbose_logging:
                        import json

                        print(
                            f"         Parameters: {json.dumps(method_params, indent=2)}"
                        )
                    else:
                        print(f"         Parameters: {method_params}")

                response = loop.run_until_complete(
                    ovrc_service.send_request(
                        method=method,
                        params=method_params,
                        wait_for_response=True,
                        timeout=timeout,
                    )
                )

                if response:
                    if response.error:
                        print(f"      ❌ OvrC command error: {response.error}")
                        raise ValueError(f"OvrC command failed: {response.error}")

                    result = response.result
                    store_as = self._get_param(step_params, "store_as", "")
                    if store_as and result:
                        variables[store_as] = result
                        print(f"      Stored response as: {store_as}")
                    return True
                else:
                    print(f"      ❌ No response received for method: {method}")
                    return False

            if "disconnect" in action_lower:
                loop.run_until_complete(ovrc_service.disconnect())
                variables.pop("_ovrc_service", None)
                return True

            elif "start device updates" in action_lower:
                success = loop.run_until_complete(ovrc_service.start_device_updates())
                store_as = params.get("store_as", "")
                if store_as and success:
                    # Wait for and extract system resources from device updates
                    import time
                    max_wait = 30  # Wait up to 30 seconds for system resources
                    wait_interval = 0.5
                    waited = 0
                    system_resources = None
                    best_resources = None
                    best_update = None
                    
                    print(f"      ⏳ Waiting for system resource data (up to {max_wait}s)...")
                    
                    # Check all available updates, not just the latest
                    while waited < max_wait:
                        # Get the latest update
                        latest_update = ovrc_service.get_latest_device_update()
                        if latest_update:
                            # Extract system resources from the update
                            extracted = self._extract_system_resources(latest_update)
                            
                            # Keep track of the best extraction (most resources found)
                            if extracted:
                                if not best_resources or (
                                    extracted.get("resources_found", False) and 
                                    len(extracted.get("resources", {})) > len(best_resources.get("resources", {}))
                                ):
                                    best_resources = extracted
                                    best_update = latest_update
                                
                                # If we found resources, we can break early
                                if extracted.get("resources_found"):
                                    system_resources = extracted
                                    print(f"      ✅ System resources found after {int(waited)}s")
                                    break
                        
                        # Also check all device updates (not just latest) for resources
                        if hasattr(ovrc_service, 'device_updates') and ovrc_service.device_updates:
                            for update in ovrc_service.device_updates[-5:]:  # Check last 5 updates
                                extracted = self._extract_system_resources(update)
                                if extracted and extracted.get("resources_found"):
                                    if not best_resources or len(extracted.get("resources", {})) > len(best_resources.get("resources", {})):
                                        best_resources = extracted
                                        best_update = update
                                    if not system_resources:
                                        system_resources = extracted
                                        print(f"      ✅ System resources found in previous update after {int(waited)}s")
                                        break
                        
                        if system_resources:
                            break
                        
                        time.sleep(wait_interval)
                        waited += wait_interval
                        if waited % 5 == 0:
                            print(f"      ⏳ Still waiting for system resources... ({int(waited)}s/{max_wait}s)")
                    
                    # Use best resources found, or system_resources if we found them
                    final_resources = system_resources or best_resources
                    
                    if final_resources:
                        variables[store_as] = final_resources
                        print(f"      💾 Stored system resources as: {store_as}")
                        
                        resources = final_resources.get("resources", {})
                        if resources:
                            print(f"      📊 System Resources Detected:")
                            if "cpu" in resources:
                                cpu_info = resources["cpu"]
                                if isinstance(cpu_info, dict):
                                    # Show usage_percent prominently
                                    if "usage_percent" in cpu_info:
                                        usage = cpu_info["usage_percent"]
                                        print(f"         CPU Usage: {usage:.2f}%")
                                    # Show other CPU fields
                                    other_fields = {k: v for k, v in cpu_info.items() if k not in ["source", "usage_percent"]}
                                    if other_fields:
                                        cpu_str = ", ".join([f"{k}: {v}" for k, v in other_fields.items()])
                                        print(f"         CPU Other: {cpu_str}")
                                else:
                                    print(f"         CPU: {cpu_info}")
                            if "memory" in resources:
                                mem_info = resources["memory"]
                                if isinstance(mem_info, dict):
                                    # Show usage_percent prominently
                                    if "usage_percent" in mem_info:
                                        usage = mem_info["usage_percent"]
                                        print(f"         Memory Usage: {usage:.2f}%")
                                    # Show memory sizes
                                    if "total" in mem_info:
                                        total = mem_info["total"]
                                        total_gb = total / (1024**3) if total > 1024 else total / 1024
                                        unit = "GB" if total > 1024 else "MB"
                                        print(f"         Memory Total: {total_gb:.2f} {unit}")
                                    if "used" in mem_info:
                                        used = mem_info["used"]
                                        used_gb = used / (1024**3) if used > 1024 else used / 1024
                                        unit = "GB" if used > 1024 else "MB"
                                        print(f"         Memory Used: {used_gb:.2f} {unit}")
                                    # Show other memory fields
                                    other_fields = {k: v for k, v in mem_info.items() if k not in ["source", "usage_percent", "total", "used", "free"]}
                                    if other_fields:
                                        mem_str = ", ".join([f"{k}: {v}" for k, v in other_fields.items()])
                                        print(f"         Memory Other: {mem_str}")
                                else:
                                    print(f"         Memory: {mem_info}")
                            if "disk" in resources:
                                disk_info = resources["disk"]
                                if isinstance(disk_info, dict):
                                    if "usage_percent" in disk_info:
                                        usage = disk_info["usage_percent"]
                                        print(f"         Disk Usage: {usage:.2f}%")
                                    disk_str = ", ".join([f"{k}: {v}" for k, v in disk_info.items() if k not in ["source", "usage_percent"]])
                                    if disk_str:
                                        print(f"         Disk: {disk_str}")
                                else:
                                    print(f"         Disk: {disk_info}")
                            if "network" in resources:
                                net_info = resources["network"]
                                if isinstance(net_info, dict):
                                    net_str = ", ".join([f"{k}: {v}" for k, v in net_info.items() if k != "source"])
                                    print(f"         Network: {net_str}")
                                else:
                                    print(f"         Network: {net_info}")
                        else:
                            print(f"      ⚠️  Device updates started, but no system resources detected yet")
                            print(f"      ℹ️  Resources may arrive in subsequent updates")
                    else:
                        # Store what we have even if resources aren't fully extracted
                        latest_update = ovrc_service.get_latest_device_update()
                        if latest_update:
                            # Still try to extract, even if not found
                            extracted = self._extract_system_resources(latest_update)
                            if extracted:
                                variables[store_as] = extracted
                                print(f"      💾 Stored device update as: {store_as}")
                                if not extracted.get("resources_found"):
                                    print(f"      ⚠️  System resources not detected in current update")
                                    print(f"      ℹ️  Will continue monitoring for resource data in future updates")
                            else:
                                variables[store_as] = {
                                    "raw_update": latest_update,
                                    "status": "updates_started",
                                    "device_online": ovrc_service.is_device_online(),
                                    "resources_found": False
                                }
                                print(f"      💾 Stored device update as: {store_as}")
                                print(f"      ⚠️  System resources not detected, but updates are active")
                        else:
                            variables[store_as] = {
                                "status": "updates_started",
                                "device_online": ovrc_service.is_device_online(),
                                "resources_found": False
                            }
                            print(f"      💾 Device updates started. System resources will be pulled automatically.")
                            print(f"      ℹ️  Waiting for device updates to arrive...")
                return success

            elif "stop device updates" in action_lower:
                success = loop.run_until_complete(ovrc_service.stop_device_updates())
                return success

            elif "get about" in action_lower:
                print(f"      📡 Calling dxGetAbout...")
                result = loop.run_until_complete(ovrc_service.get_about())
                store_as = params.get("store_as", "")
                if store_as and result:
                    variables[store_as] = result
                    print(f"      💾 Stored response as: {store_as}")
                return result is not None

            elif "reset device" in action_lower:
                success = loop.run_until_complete(ovrc_service.reset_device())
                return success

            elif "get network settings" in action_lower:
                result = loop.run_until_complete(ovrc_service.get_network_settings())
                store_as = params.get("store_as", "")
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None

            elif "set network settings" in action_lower:
                success = loop.run_until_complete(
                    ovrc_service.set_network_settings(
                        device_name=params.get("device_name"),
                        device_ip=params.get("device_ip"),
                        subnet_mask=params.get("subnet_mask"),
                        gateway=params.get("gateway"),
                        dhcp_enabled=params.get("dhcp_enabled"),
                        dns_server1=params.get("dns_server1"),
                        dns_server2=params.get("dns_server2"),
                        web_port=params.get("web_port"),
                    )
                )
                return success

            elif "get time settings" in action_lower:
                result = loop.run_until_complete(ovrc_service.get_time_settings())
                store_as = params.get("store_as", "")
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None

            elif "set time settings" in action_lower:
                success = loop.run_until_complete(
                    ovrc_service.set_time_settings(
                        timezone_name=params.get("timezone_name", ""),
                        timezone_notes=params.get("timezone_notes"),
                        utc_offset_minutes=params.get("utc_offset_minutes"),
                        current_time=params.get("current_time"),
                    )
                )
                return success

            elif "get status update frequency" in action_lower:
                result = loop.run_until_complete(
                    ovrc_service.get_status_update_frequency()
                )
                store_as = params.get("store_as", "")
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None

            elif "set status update frequency" in action_lower:
                frequency = params.get("frequency", 0)
                success = loop.run_until_complete(
                    ovrc_service.set_status_update_frequency(frequency)
                )
                return success

            elif "enable web connect" in action_lower:
                success = loop.run_until_complete(
                    ovrc_service.enable_web_connect(
                        ssh_server=params.get("ssh_server", ""),
                        tunnel_port=params.get("tunnel_port", 0),
                    )
                )
                return success

            elif "disable web connect" in action_lower:
                success = loop.run_until_complete(
                    ovrc_service.disable_web_connect(
                        ssh_server=params.get("ssh_server", ""),
                        tunnel_port=params.get("tunnel_port", 0),
                    )
                )
                return success

            elif "set cloud server url" in action_lower:
                success = loop.run_until_complete(
                    ovrc_service.set_cloud_server_url(
                        url=params.get("url", ""), port=params.get("port", 0)
                    )
                )
                return success

            elif "disable cloud" in action_lower:
                success = loop.run_until_complete(ovrc_service.disable_cloud())
                return success

            elif "update firmware" in action_lower:
                firmware_url = params.get("firmware_url", "")
                success = loop.run_until_complete(
                    ovrc_service.update_firmware(firmware_url)
                )
                return success

            elif "find device by serial" in action_lower:
                serial_num = params.get("serial_num", "")
                result = loop.run_until_complete(
                    ovrc_service.find_device_by_serial(serial_num)
                )
                store_as = params.get("store_as", "")
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None

            else:
                print(f"      ❌ Unknown OvrC action: {action}")
                raise ValueError(f"Unknown OvrC action: {action}")

        except Exception as e:
            print(f"      ❌ OvrC action failed: {e}")
            # Re-raise to prevent "Unknown action" fallthrough
            raise

    def _handle_ovrc_http_action(
        self, action: str, step_params: dict, variables: dict, ovrc_service: Any
    ) -> bool:
        """Handle OvrC HTTP API actions (GET, POST, PUT, PATCH, DELETE)."""
        import asyncio

        params = self._get_params(step_params)
        action_lower = action.lower()

        # Auto-connect if service doesn't exist or is disconnected
        # The _ensure_ovrc_connection method will handle HTTP-only services automatically
        if not ovrc_service or (
            ovrc_service.server_url and not ovrc_service.is_connected()
        ):
            ovrc_service = self._ensure_ovrc_connection(variables, params)

        # Update verbose logging if changed
        verbose_logging = (
            variables.get("verbose_logging", True)
            or variables.get("show_full_response", False)
            or params.get("verbose_logging", True)
            or params.get("show_full_response", False)
        )
        if isinstance(verbose_logging, str):
            verbose_logging = verbose_logging.lower() in ("true", "1", "yes", "on")
        if ovrc_service and ovrc_service.verbose_logging != verbose_logging:
            ovrc_service.verbose_logging = verbose_logging

        loop = asyncio.get_event_loop()
        endpoint = params.get("endpoint", "")
        # Support both "json_data" and "body" for request body
        json_data = params.get("json_data", params.get("body", {}))
        # Support both "params", "query", and "query_params" for query parameters
        query_params = params.get(
            "query_params", params.get("params", params.get("query", {}))
        )
        headers = params.get("headers", {})
        timeout = params.get("timeout", 30.0)
        store_as = params.get("store_as", "")

        try:
            # Handle generic "ovrc.http.request" action with method parameter
            if "http.request" in action_lower or "http request" in action_lower:
                method = params.get("method", "GET").upper()
                # Support query_params as alias for params
                if "query_params" in params:
                    query_params = params.get("query_params", {})
                result = loop.run_until_complete(
                    ovrc_service.http_request(
                        method=method,
                        endpoint=endpoint,
                        params=query_params,
                        json_data=json_data,
                        headers=headers,
                        timeout=timeout,
                    )
                )
            else:
                # Extract HTTP method from action (supports "ovrc.http.get", "ovrc http get", etc.)
                method_part = (
                    action_lower.split(".")[-1]
                    if "." in action_lower
                    else action_lower.split()[-1]
                )
                if "get" in method_part:
                    result = loop.run_until_complete(
                        ovrc_service.http_get(
                            endpoint,
                            params=query_params,
                            headers=headers,
                            timeout=timeout,
                        )
                    )
                elif "post" in method_part:
                    result = loop.run_until_complete(
                        ovrc_service.http_post(
                            endpoint,
                            json_data=json_data,
                            params=query_params,
                            headers=headers,
                            timeout=timeout,
                        )
                    )
                elif "put" in method_part:
                    result = loop.run_until_complete(
                        ovrc_service.http_put(
                            endpoint,
                            json_data=json_data,
                            params=query_params,
                            headers=headers,
                            timeout=timeout,
                        )
                    )
                elif "patch" in method_part:
                    result = loop.run_until_complete(
                        ovrc_service.http_patch(
                            endpoint,
                            json_data=json_data,
                            params=query_params,
                            headers=headers,
                            timeout=timeout,
                        )
                    )
                elif "delete" in method_part:
                    result = loop.run_until_complete(
                        ovrc_service.http_delete(
                            endpoint,
                            params=query_params,
                            headers=headers,
                            timeout=timeout,
                        )
                    )
                else:
                    raise ValueError(f"Unknown HTTP method in action: {action}")

            if store_as and result:
                variables[store_as] = result
                print(f"      Stored response as: {store_as}")

            # Check for error in response
            if result and "error" in result:
                print(f"      ⚠️  API returned error: {result.get('error')}")
                return False

            return result is not None

        except Exception as e:
            print(f"      ❌ OvrC HTTP API action failed: {e}")
            raise

    def _handle_pagerduty_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle PagerDuty incident management actions."""
        from ..services.pagerduty_service import PagerDutyService

        # Get or create PagerDuty service from variables
        pd_service = variables.get("_pagerduty_service")

        # Extract parameters
        params = self._get_params(step_params)
        action_lower = action.lower()

        try:
            # Initialize service if needed
            if not pd_service:
                api_key = (
                    params.get("api_key")
                    or variables.get("pagerduty_api_key")
                    or os.environ.get("PAGERDUTY_API_KEY")
                )
                api_base_url = params.get("api_base_url") or variables.get("pagerduty_api_base_url")
                pd_service = PagerDutyService(logger=print, api_key=api_key, api_base_url=api_base_url)
                variables["_pagerduty_service"] = pd_service

            # Create incident
            if "create" in action_lower and "incident" in action_lower:
                service_id = params.get("service_id", "")
                title = params.get("title", "")
                description = params.get("description", "")
                severity = params.get("severity", "error")
                urgency = params.get("urgency")
                priority_id = params.get("priority_id")
                assignees = params.get("assignees", [])
                escalation_policy_id = params.get("escalation_policy_id")
                custom_details = params.get("custom_details", {})

                if not service_id or not title:
                    raise ValueError("PagerDuty create incident requires 'service_id' and 'title'")

                result = pd_service.create_incident(
                    service_id=service_id,
                    title=title,
                    description=description,
                    severity=severity,
                    urgency=urgency,
                    priority_id=priority_id,
                    assignees=assignees if isinstance(assignees, list) else [assignees] if assignees else [],
                    escalation_policy_id=escalation_policy_id,
                    custom_details=custom_details,
                )

                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      💾 Stored incident as: {store_as}")
                return True

            # Resolve incident
            elif "resolve" in action_lower and "incident" in action_lower:
                incident_id = params.get("incident_id", "")
                resolution = params.get("resolution", "")

                if not incident_id:
                    raise ValueError("PagerDuty resolve incident requires 'incident_id'")

                result = pd_service.resolve_incident(incident_id=incident_id, resolution=resolution)
                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      💾 Stored resolved incident as: {store_as}")
                return True

            # Acknowledge incident
            elif "acknowledge" in action_lower and "incident" in action_lower:
                incident_id = params.get("incident_id", "")
                acknowledger_id = params.get("acknowledger_id")

                if not incident_id:
                    raise ValueError("PagerDuty acknowledge incident requires 'incident_id'")

                result = pd_service.acknowledge_incident(incident_id=incident_id, acknowledger_id=acknowledger_id)
                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      💾 Stored acknowledged incident as: {store_as}")
                return True

            # Get incident
            elif "get" in action_lower and "incident" in action_lower:
                incident_id = params.get("incident_id", "")

                if not incident_id:
                    raise ValueError("PagerDuty get incident requires 'incident_id'")

                result = pd_service.get_incident(incident_id=incident_id)
                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      💾 Stored incident as: {store_as}")
                return result is not None

            # List incidents
            elif "list" in action_lower and "incident" in action_lower:
                service_ids = params.get("service_ids", [])
                statuses = params.get("statuses", [])
                since = params.get("since")
                until = params.get("until")
                limit = params.get("limit", 25)

                if isinstance(service_ids, str):
                    service_ids = [s.strip() for s in service_ids.split(",") if s.strip()]
                if isinstance(statuses, str):
                    statuses = [s.strip() for s in statuses.split(",") if s.strip()]

                result = pd_service.list_incidents(
                    service_ids=service_ids,
                    statuses=statuses,
                    since=since,
                    until=until,
                    limit=limit,
                )
                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      💾 Stored {len(result)} incidents as: {store_as}")
                return True

            # Update incident
            elif "update" in action_lower and "incident" in action_lower:
                incident_id = params.get("incident_id", "")
                title = params.get("title")
                description = params.get("description")
                severity = params.get("severity")
                urgency = params.get("urgency")
                priority_id = params.get("priority_id")
                status = params.get("status")
                custom_details = params.get("custom_details", {})

                if not incident_id:
                    raise ValueError("PagerDuty update incident requires 'incident_id'")

                result = pd_service.update_incident(
                    incident_id=incident_id,
                    title=title,
                    description=description,
                    severity=severity,
                    urgency=urgency,
                    priority_id=priority_id,
                    status=status,
                    custom_details=custom_details,
                )
                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      💾 Stored updated incident as: {store_as}")
                return True

            # Get on-call users
            elif "oncall" in action_lower or "on-call" in action_lower:
                schedule_ids = params.get("schedule_ids", [])
                escalation_policy_ids = params.get("escalation_policy_ids", [])

                if isinstance(schedule_ids, str):
                    schedule_ids = [s.strip() for s in schedule_ids.split(",") if s.strip()]
                if isinstance(escalation_policy_ids, str):
                    escalation_policy_ids = [s.strip() for s in escalation_policy_ids.split(",") if s.strip()]

                result = pd_service.get_oncall_users(
                    schedule_ids=schedule_ids,
                    escalation_policy_ids=escalation_policy_ids,
                )
                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      💾 Stored {len(result)} on-call users as: {store_as}")
                return True

            # Get services
            elif "get" in action_lower and "service" in action_lower:
                service_id = params.get("service_id", "")
                query = params.get("query", "")
                limit = params.get("limit", 25)

                if service_id:
                    result = pd_service.get_service(service_id=service_id)
                else:
                    result = pd_service.get_services(query=query, limit=limit)

                store_as = params.get("store_as", "")
                if store_as:
                    if service_id:
                        variables[store_as] = result
                        print(f"      💾 Stored service as: {store_as}")
                    else:
                        variables[store_as] = result
                        print(f"      💾 Stored {len(result)} services as: {store_as}")
                return result is not None

            else:
                print(f"      ❌ Unknown PagerDuty action: {action}")
                raise ValueError(f"Unknown PagerDuty action: {action}")

        except Exception as e:
            print(f"      ❌ PagerDuty action failed: {e}")
            raise

    def _handle_test_run_action(
        self, step_params: dict, variables: dict, soft_assert_manager=None
    ) -> bool:
        """Handle test.run action - execute another test as a reusable step."""
        params = self._get_params(step_params)

        # Get test path
        test_path = params.get("test_path", "")
        if not test_path:
            raise ValueError("test.run requires 'test_path' parameter")

        # Resolve test path (support relative paths from tests/cases/)
        if not Path(test_path).is_absolute():
            # Try relative to tests/cases/ directory
            # Get tests directory from config
            tests_dir = self.config.get_variable("tests_dir", "tests")
            if isinstance(tests_dir, str):
                tests_dir = Path(tests_dir)
            else:
                tests_dir = Path("tests")

            base_path = tests_dir / "cases"
            test_file = base_path / test_path
            if not test_file.exists():
                # Try as-is (might already be full path relative to tests/)
                test_file = tests_dir / test_path
                if not test_file.exists():
                    # Try from current working directory
                    test_file = Path.cwd() / "tests" / "cases" / test_path
        else:
            test_file = Path(test_path)

        if not test_file.exists():
            raise FileNotFoundError(f"Test file not found: {test_path}")

        print(f"      🔄 Running test as step: {test_file.name}")

        # Get input variables to pass to the called test
        input_vars = params.get("variables", {})
        if isinstance(input_vars, str):
            # Try to parse as JSON
            try:
                import json

                input_vars = json.loads(input_vars)
            except Exception:
                # If not JSON, treat as key-value pairs
                input_vars = {}

        # Merge input variables with current variables (input_vars take precedence)
        called_test_vars = dict(variables)
        called_test_vars.update(input_vars)

        # Parse and load the test
        try:
            called_test = self.parser.parse_file(str(test_file))
        except Exception as e:
            raise ValueError(f"Failed to parse test file {test_path}: {e}")

        # Execute the called test using the same runner instance
        # Create a test detail dict to capture results
        called_test_detail = {
            "name": called_test.name,
            "status": "unknown",
            "variables": {},
        }

        # Execute the test with the merged variables
        # Store original variables and set merged variables
        original_test_vars = (
            called_test.variables.copy() if called_test.variables else {}
        )
        called_test.variables = called_test_vars.copy()
        # Also store as _merged_variables for step execution
        called_test._merged_variables = called_test_vars

        try:
            # Execute the test - it will use called_test.variables (which is now merged)
            success = self._execute_single_test(
                called_test, test_detail=called_test_detail
            )

            # Clean up the temporary attribute
            if hasattr(called_test, "_merged_variables"):
                delattr(called_test, "_merged_variables")

            # After execution, extract variables from the called test's variables
            # The called test may have set variables during execution
            store_vars = params.get("store_variables", {})
            if isinstance(store_vars, str):
                try:
                    import json

                    store_vars = json.loads(store_vars)
                except Exception:
                    store_vars = {}

            # Extract variables from called test's variables (after execution)
            if store_vars:
                print(f"      📦 Extracting variables from called test...")
                for var_name, var_path in store_vars.items():
                    try:
                        # Support dot notation paths (e.g., "about_result.firmware")
                        # Try from called_test.variables first (most up-to-date after execution)
                        value = self._extract_nested_value(
                            called_test.variables, var_path
                        )
                        if value is None:
                            # Fallback to called_test_vars
                            value = self._extract_nested_value(
                                called_test_vars, var_path
                            )
                        if value is not None:
                            variables[var_name] = value
                            print(f"      ✓ Extracted {var_name} = {value}")
                        else:
                            print(
                                f"      ⚠ Could not extract {var_name} from path: {var_path}"
                            )
                    except Exception as e:
                        print(f"      ⚠ Error extracting {var_name}: {e}")

            # Also merge any new variables that were set during execution
            # (variables that were stored in called_test.variables but not in original variables)
            for key, value in called_test.variables.items():
                if key not in input_vars:  # Don't overwrite input variables
                    # Add new variables or update existing ones (except input vars)
                    if key not in variables or (
                        key in variables and key not in input_vars
                    ):
                        variables[key] = value

            # Check continue_on_failure flag
            continue_on_failure = params.get("continue_on_failure", False)
            if isinstance(continue_on_failure, str):
                continue_on_failure = continue_on_failure.lower() in (
                    "true",
                    "1",
                    "yes",
                    "on",
                )

            if success:
                print(f"      ✅ Test step completed successfully")
                return True
            else:
                print(f"      ❌ Test step failed")
                if continue_on_failure:
                    print(
                        f"      ⚠ Continuing despite failure (continue_on_failure=true)"
                    )
                    return True
                else:
                    return False

        except Exception as e:
            print(f"      ❌ Error executing test step: {e}")
            import traceback

            traceback.print_exc()

            continue_on_failure = params.get("continue_on_failure", False)
            if isinstance(continue_on_failure, str):
                continue_on_failure = continue_on_failure.lower() in (
                    "true",
                    "1",
                    "yes",
                    "on",
                )

            if continue_on_failure:
                print(f"      ⚠ Continuing despite error (continue_on_failure=true)")
                return True
            else:
                raise

    def _handle_wol_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle Wake-on-LAN actions (wol.send)."""
        from ..services.wol_service import WoLService
        params = self._get_params(step_params)
        service = WoLService()
        result = service.execute(action, params, variables)
        store_as = params.get("store_as", "")
        if store_as and result is not None:
            variables[store_as] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, result, "runtime_data")
        print(f"      wol: packet sent to {params.get('mac') or variables.get('mac_for_report', '?')}")
        return True

    def _handle_serial_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle serial port actions (serial.send, serial.receive, serial.flush, serial.close)."""
        from ..services.serial_service import SerialService
        params = self._get_params(step_params)
        service = SerialService(self._connection_pool)
        result = service.execute(action, params, variables)
        store_as = params.get("store_as", "")
        if store_as and result is not None:
            variables[store_as] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, result, "runtime_data")
        if result is False:
            return False
        print(f"      serial: {action.split('.')[-1]} OK")
        return True

    def _handle_telnet_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle telnet actions (telnet.connect, telnet.send, telnet.receive, telnet.close)."""
        from ..services.telnet_service import TelnetService
        params = self._get_params(step_params)
        service = TelnetService(self._connection_pool)
        result = service.execute(action, params, variables)
        if result is False:
            return False
        # Always store string responses as last_response so downstream steps
        # (eval.exec, test.assert, etc.) can reference the device output.
        if isinstance(result, str) and result:
            variables["last_response"] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable("last_response", result, "runtime_data")
            # Print response so authors can see the actual device output immediately
            _resp_clean = result.strip()
            if _resp_clean:
                _lines = _resp_clean.splitlines()
                _preview_lines = _lines[:20]
                indented = "\n".join("         " + ln for ln in _preview_lines)
                print(f"      📥 response:\n{indented}")
                if len(_lines) > 20:
                    print(f"         ... ({len(_lines) - 20} more lines)")
        store_as = params.get("store_as", "")
        if store_as and result is not None:
            variables[store_as] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, result, "runtime_data")
            if store_as != "last_response":
                print(f"         stored as: {store_as}")
        print(f"      telnet: {action.split('.')[-1]} OK")
        return True

    def _handle_ssh_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle SSH actions (ssh.connect, ssh.command, ssh.disconnect)."""
        from ..services.ssh_service import SSHService
        params = self._get_params(step_params)
        service = SSHService(self._connection_pool)
        result = service.execute(action, params, variables)
        if result is False:
            return False
        if isinstance(result, str) and result:
            variables["last_response"] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable("last_response", result, "runtime_data")
        store_as = params.get("store_as", "")
        if store_as and result is not None:
            variables[store_as] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, result, "runtime_data")
        print(f"      ssh: {action.split('.')[-1]} OK")
        return True

    def _handle_lgip_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle LGIP IR control actions (lgip.connect, lgip.send_keycode, lgip.disconnect)."""
        from ..services.lgip_service import LGIPService
        params = self._get_params(step_params)
        service = LGIPService(self._connection_pool)
        result = service.execute(action, params, variables)
        if result is False:
            return False
        if isinstance(result, str) and result:
            variables["last_response"] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable("last_response", result, "runtime_data")
        store_as = params.get("store_as", "")
        if store_as and result is not None:
            variables[store_as] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, result, "runtime_data")
        print(f"      lgip: {action.split('.')[-1]} OK")
        return True

    def _handle_websocket_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle websocket actions (websocket.connect, websocket.send, websocket.receive, websocket.close)."""
        import json as _json
        from ..services.websocket_service import WebSocketService
        params = self._get_params(step_params)
        # Reuse the same WebSocketService instance across steps so the token
        # cache and connection pool are shared for the duration of the test.
        if not hasattr(self, "_websocket_service"):
            self._websocket_service = WebSocketService(self._connection_pool)
        service = self._websocket_service
        action_verb = action.split(".")[-1].lower()
        url = params.get("url", "")

        # --- pre-call logging ---
        if action_verb == "connect":
            protos = params.get("subprotocols") or params.get("protocol") or []
            if isinstance(protos, str):
                protos = [p.strip() for p in protos.split(",") if p.strip()]
            print(f"      🔌 websocket.connect → {url}")
            if protos:
                print(f"         subprotocols: {protos}")
            hdrs = {k: v for k, v in (params.get("headers") or {}).items()
                    if k.lower() != "authorization"}
            if hdrs:
                print(f"         headers: {hdrs}")
        elif action_verb == "send":
            data = params.get("data", "")
            method = params.get("method")
            print(f"      📤 websocket.send → {url}")
            if method:
                print(f"         method (JSON-RPC): {method}")
            if data:
                try:
                    payload_str = _json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data)
                    # Indent each line for alignment
                    indented = "\n".join("         " + ln for ln in payload_str.splitlines())
                    print(f"         payload:\n{indented}")
                except Exception:
                    print(f"         payload: {data}")
        elif action_verb in ("receive", "read"):
            print(f"      📥 websocket.receive ← {url}")
        elif action_verb == "close":
            print(f"      🔒 websocket.close → {url}")

        result = service.execute(action, params, variables)
        if result is False:
            return False

        # --- post-call logging ---
        if isinstance(result, str) and result:
            variables["last_response"] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable("last_response", result, "runtime_data")
            # Pretty-print response
            try:
                parsed = _json.loads(result)
                resp_str = _json.dumps(parsed, indent=2)
            except Exception:
                resp_str = result
            indented = "\n".join("         " + ln for ln in resp_str.splitlines())
            print(f"      📥 response:\n{indented}")

        store_as = params.get("store_as", "")
        if store_as and result is not None:
            variables[store_as] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, result, "runtime_data")
            if store_as != "last_response":
                print(f"         stored as: {store_as}")

        if action_verb not in ("send", "receive", "read"):
            print(f"      ✅ websocket.{action_verb} OK")
        return True

    def _handle_eval_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle session-stateful Python eval/exec actions.

        Actions:
          eval.run             — evaluate an expression, store result
          eval.exec            — execute a code block (state mutations persist)
          eval.set             — set a key in shared eval state
          eval.get             — read a key from shared eval state into variables
          eval.clear           — clear the entire eval state
          eval.extract_version — extract version string from a URL/filename/list
        """
        import math, re as _re, json as _json, datetime as _datetime, collections as _collections

        params = self._get_params(step_params)
        action_lower = action.lower()
        store_as = params.get("store_as", "")
        # Normalise legacy mybdd store_as keys: gv.tests['variables']['$key'] → key
        if store_as:
            import re as _re_sa
            _m = _re_sa.match(
                r"gv\.tests\[(?:'variables'|\"variables\")\]\[(?:'\$?(\w+)'|\"\$?(\w+)\")\]",
                store_as.strip(),
            )
            if _m:
                store_as = _m.group(1) or _m.group(2)

        import platform as _platform
        # Build the execution context: shared state + current test variables
        ctx = {
            "state": self._eval_state,
            "variables": variables,
            "math": math,
            "re": _re,
            "json": _json,
            "datetime": _datetime,
            "collections": _collections,
            "platform": _platform,
        }
        ctx.update(self._eval_state)
        ctx.update(variables)
        # Always set the gv shim last so variables["gv"] (a plain dict used for
        # ${gv.x} substitution) never overwrites the _Gv object in exec context.
        ctx["gv"] = _Gv(variables)

        if "set" in action_lower and "extract" not in action_lower:
            key = params.get("key", "")
            value = params.get("value")
            if key:
                self._eval_state[key] = value
                variables[key] = value
            return True

        if "extract_version" in action_lower or action_lower == "eval.extract_version":
            import re as _rev
            # Source: explicit 'from' string, or a variable name in 'from_var', or 'url'
            from_val = (
                params.get("from")
                or params.get("url")
                or params.get("source")
            )
            from_var = params.get("from_var") or params.get("list_var")
            if from_var:
                from_val = variables.get(from_var, "")

            # Resolve ${var} references in the source string
            if isinstance(from_val, list):
                # list of URLs — pick the index specified (default 0 = first/oldest; -1 = latest)
                idx = int(params.get("index", 0))
                from_val = from_val[idx] if from_val else ""
            elif not isinstance(from_val, str):
                from_val = str(from_val or "")

            # Default pattern: semver-style digits e.g. 1.0.02.00 or v2.3.1
            pattern = params.get("pattern", r"(\d+\.\d+[\.\d]*)")
            match = _rev.search(pattern, from_val)
            version = match.group(1) if match else ""

            store_as = params.get("store_as", "firmware_version")
            variables[store_as] = version
            self._eval_state[store_as] = version
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, version, "runtime_data")
            print(f"      🏷  Extracted version: {version!r} from {from_val!r} → stored as '{store_as}'")

            # Optionally update the TestRail run name
            run_name_template = params.get("run_name")
            append_to_run_name = params.get("append_to_run_name")
            if (run_name_template or append_to_run_name) and version:
                tr_run_id = int(variables.get("_testrail_run_id", 0))
                if tr_run_id:
                    try:
                        from ..services.testrail_service import TestRailService
                        cfg = self.config
                        tr = TestRailService(
                            url=cfg.get_variable("testrail.url") or cfg.get_variable("testrail_url", None),
                            username=cfg.get_variable("testrail.username") or cfg.get_variable("testrail_username", None),
                            api_key=cfg.get_variable("testrail.api_key") or cfg.get_variable("testrail_api_key", None),
                        )

                        def _subst_run_name(value: str) -> str:
                            return _rev.sub(
                                r"\$\{(\w+)\}",
                                lambda m: str(variables.get(m.group(1), m.group(0))),
                                str(value),
                            )

                        if run_name_template:
                            new_name = _subst_run_name(run_name_template)
                        else:
                            current_run = tr.get_run(tr_run_id)
                            current_name = str(current_run.get("name", "") or "")
                            suffix = _subst_run_name(append_to_run_name)
                            if suffix and current_name.endswith(suffix):
                                print(f"      ℹ  TestRail run [{tr_run_id}] already ends with: {suffix!r}")
                                return True
                            new_name = f"{current_name}{suffix}" if current_name else suffix

                        if new_name:
                            tr.update_run(tr_run_id, name=new_name)
                            print(f"      ✅ TestRail run [{tr_run_id}] renamed to: {new_name!r}")
                    except Exception as _e:
                        print(f"      ⚠  Could not update run name: {_e}")
            return True

        if "get" in action_lower:
            key = params.get("key", "")
            value = self._eval_state.get(key)
            if store_as:
                variables[store_as] = value
                if hasattr(self.config, "set_variable"):
                    self.config.set_variable(store_as, value, "runtime_data")
            return True

        if "clear" in action_lower:
            self._eval_state.clear()
            return True

        if "exec" in action_lower:
            code = params.get("code", "")
            if not code:
                raise ValueError("eval.exec requires 'code'")

            # Detect comment-only stubs generated by bdd_migrator and execute them.
            # e.g. "# upload_cloud_firmware: list S3 bucket 'X' path 'Y'\n# filter by regex 'Z'..."
            _exec_lines = [ln for ln in code.strip().splitlines() if ln.strip() and not ln.strip().startswith("#")]
            if not _exec_lines:
                import re as _re_stub
                _flat = " ".join(ln.strip().lstrip("# ") for ln in code.strip().splitlines())

                def _resolve_stub_var(val: str) -> str:
                    """Resolve ${var} references left in stub comments."""
                    return _re_stub.sub(
                        r"\$\{(\w+)\}",
                        lambda m: str(variables.get(m.group(1), m.group(0))),
                        val,
                    )

                _uc = _re_stub.search(
                    r"upload_cloud_firmware: list S3 bucket '(.+?)' path '(.+?)'", _flat
                )
                if _uc:
                    _bucket = _resolve_stub_var(_uc.group(1))
                    _path   = _resolve_stub_var(_uc.group(2))
                    _rx     = _re_stub.search(r"filter by regex '(.+?)'", _flat)
                    _aws_params: dict = {"bucket_name": _bucket, "folder_prefix": _path}
                    if _rx and _rx.group(1):
                        _aws_params["filename_pattern"] = _resolve_stub_var(_rx.group(1))
                    return self._handle_aws_action(
                        "aws.list_files", {"parameters": _aws_params}, variables
                    )

                # No recognised stub — code is all comments, treat as no-op
                return True

            # Intentional exec: eval.exec is an explicit test-authoring tool for trusted
            # test YAML files written by the QA team. It is not exposed to external input.
            exec(code, ctx)  # noqa: S102
            # Persist any new/changed keys back to eval state (exclude builtins)
            for k, v in ctx.items():
                if not k.startswith("_") and k not in ("state", "variables", "math", "re", "json", "datetime", "collections", "platform"):
                    self._eval_state[k] = v
                    variables[k] = v
                    if hasattr(self.config, "set_variable"):
                        self.config.set_variable(k, v, "runtime_data")
            # Mirror attributes set on the gv shim (e.g. gv.message = "...") into
            # variables["gv"] as a plain dict so ${gv.message} resolves correctly.
            _gv_obj = ctx.get("gv")
            if _gv_obj is not None:
                _gv_builtins = {"log", "tests"}
                _gv_dict = variables.get("gv")
                if not isinstance(_gv_dict, dict):
                    _gv_dict = {}
                    variables["gv"] = _gv_dict
                for _attr, _val in vars(_gv_obj).items():
                    if not _attr.startswith("_") and _attr not in _gv_builtins:
                        _gv_dict[_attr] = _val
                        self._eval_state[f"gv.{_attr}"] = _val
            return True

        # Default: eval.run — evaluate an expression
        expression = params.get("expression", "") or params.get("code", "")
        if not expression:
            raise ValueError("eval.run requires 'expression'")
        # Intentional eval: eval.run is an explicit test-authoring tool for trusted
        # test YAML files written by the QA team. It is not exposed to external input.
        result = eval(expression, ctx)  # noqa: S307
        print(f"      eval: {expression!r} → {result!r}")
        if store_as:
            variables[store_as] = result
            self._eval_state[store_as] = result
            if hasattr(self.config, "set_variable"):
                self.config.set_variable(store_as, result, "runtime_data")
        return True

    def _handle_command_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle command execution actions (SSH, shell, bash, PowerShell, batch, Python)"""
        try:
            params = self._get_params(step_params)
            action_lower = action.lower()

            # Create command service if not already created
            if not hasattr(self, "_command_service"):
                self._command_service = CommandService(self.config)

            # Handle SSH command
            # Support both "command.ssh" and "command ssh" formats
            if "command" in action_lower and "ssh" in action_lower:
                host = params.get("host", "")
                command = params.get("command", "")
                if not host or not command:
                    raise ValueError(
                        "SSH command requires 'host' and 'command' parameters"
                    )

                print(f"      🔐 Executing SSH command on {host}: {command[:50]}...")
                output, exit_code = self._command_service.execute_ssh_command(
                    host=host,
                    command=command,
                    username=params.get("username"),
                    password=params.get("password"),
                    key_file=params.get("key_file"),
                    port=params.get("port", 22),
                    timeout=params.get("timeout", 30),
                )

                # Store output if requested
                store_as = params.get("store_as")
                if store_as:
                    variables[store_as] = output
                    print(f"      Stored output as: {store_as}")

                # Store exit code if requested
                store_exit_code = params.get("store_exit_code")
                if store_exit_code:
                    variables[store_exit_code] = exit_code
                    print(f"      Stored exit code as: {store_exit_code}")

                # Print output
                if output:
                    print(f"      Output:\n{output}")

                # Check if we should fail on error
                fail_on_error = params.get("fail_on_error", True)
                if exit_code != 0 and fail_on_error:
                    raise RuntimeError(f"SSH command failed with exit code {exit_code}")

                return exit_code == 0

            # Handle shell command (generic shell - supports all shell types)
            # Support both "command.shell" and "command shell" formats
            # Also handle specific shell types: sh, zsh, fish, tcsh, csh, dash, ksh
            elif (
                "command" in action_lower
                and ("shell" in action_lower or any(shell_type in action_lower for shell_type in ["sh", "zsh", "fish", "tcsh", "csh", "dash", "ksh"]))
                and "bash" not in action_lower
                and "powershell" not in action_lower
                and "batch" not in action_lower
                and "python" not in action_lower
                and "ssh" not in action_lower
            ):
                # Extract shell type from action if specified (e.g., command.zsh, command.fish)
                shell_type = "auto"
                for shell_name in ["sh", "zsh", "fish", "tcsh", "csh", "dash", "ksh"]:
                    if shell_name in action_lower:
                        shell_type = shell_name
                        break
                
                # If not found in action, use parameter or default to auto
                if shell_type == "auto":
                    shell_type = params.get("shell", "auto")
                command = params.get("command", "")
                if not command:
                    raise ValueError("Shell command requires 'command' parameter")

                print(f"      💻 Executing shell command: {command[:50]}...")
                output, exit_code = self._command_service.execute_shell_command(
                    command=command,
                    shell=params.get("shell", "auto"),
                    working_directory=params.get("working_directory"),
                    timeout=params.get("timeout", 30),
                )

                # Store output if requested
                store_as = params.get("store_as")
                if store_as:
                    variables[store_as] = output
                    print(f"      Stored output as: {store_as}")

                # Store exit code if requested
                store_exit_code = params.get("store_exit_code")
                if store_exit_code:
                    variables[store_exit_code] = exit_code
                    print(f"      Stored exit code as: {store_exit_code}")

                # Print output
                if output:
                    print(f"      Output:\n{output}")

                # Check if we should fail on error
                fail_on_error = params.get("fail_on_error", True)
                if exit_code != 0 and fail_on_error:
                    raise RuntimeError(
                        f"Shell command failed with exit code {exit_code}"
                    )

                return exit_code == 0

            # Handle bash command
            # Support both "command.bash" and "command bash" formats
            elif "command" in action_lower and "bash" in action_lower:
                command = params.get("command", "")
                if not command:
                    raise ValueError("Bash command requires 'command' parameter")

                print(f"      🐚 Executing bash command: {command[:50]}...")
                output, exit_code = self._command_service.execute_bash_command(
                    command=command,
                    working_directory=params.get("working_directory"),
                    timeout=params.get("timeout", 30),
                )

                # Store output if requested
                store_as = params.get("store_as")
                if store_as:
                    variables[store_as] = output
                    print(f"      Stored output as: {store_as}")

                # Store exit code if requested
                store_exit_code = params.get("store_exit_code")
                if store_exit_code:
                    variables[store_exit_code] = exit_code
                    print(f"      Stored exit code as: {store_exit_code}")

                # Print output
                if output:
                    print(f"      Output:\n{output}")

                # Check if we should fail on error
                fail_on_error = params.get("fail_on_error", True)
                if exit_code != 0 and fail_on_error:
                    raise RuntimeError(
                        f"Bash command failed with exit code {exit_code}"
                    )

                return exit_code == 0

            # Handle PowerShell command
            # Support both "command.powershell" and "command powershell" formats
            elif "command" in action_lower and "powershell" in action_lower:
                command = params.get("command", "")
                if not command:
                    raise ValueError("PowerShell command requires 'command' parameter")

                print(f"      ⚡ Executing PowerShell command: {command[:50]}...")
                output, exit_code = self._command_service.execute_powershell_command(
                    command=command,
                    working_directory=params.get("working_directory"),
                    timeout=params.get("timeout", 30),
                )

                # Store output if requested
                store_as = params.get("store_as")
                if store_as:
                    variables[store_as] = output
                    print(f"      Stored output as: {store_as}")

                # Store exit code if requested
                store_exit_code = params.get("store_exit_code")
                if store_exit_code:
                    variables[store_exit_code] = exit_code
                    print(f"      Stored exit code as: {store_exit_code}")

                # Print output
                if output:
                    print(f"      Output:\n{output}")

                # Check if we should fail on error
                fail_on_error = params.get("fail_on_error", True)
                if exit_code != 0 and fail_on_error:
                    raise RuntimeError(
                        f"PowerShell command failed with exit code {exit_code}"
                    )

                return exit_code == 0

            # Handle batch command
            # Support both "command.batch" and "command batch" formats
            elif "command" in action_lower and "batch" in action_lower:
                command = params.get("command", "")
                if not command:
                    raise ValueError("Batch command requires 'command' parameter")

                print(f"      📜 Executing batch command: {command[:50]}...")
                output, exit_code = self._command_service.execute_batch_command(
                    command=command,
                    working_directory=params.get("working_directory"),
                    timeout=params.get("timeout", 30),
                )

                # Store output if requested
                store_as = params.get("store_as")
                if store_as:
                    variables[store_as] = output
                    print(f"      Stored output as: {store_as}")

                # Store exit code if requested
                store_exit_code = params.get("store_exit_code")
                if store_exit_code:
                    variables[store_exit_code] = exit_code
                    print(f"      Stored exit code as: {store_exit_code}")

                # Print output
                if output:
                    print(f"      Output:\n{output}")

                # Check if we should fail on error
                fail_on_error = params.get("fail_on_error", True)
                if exit_code != 0 and fail_on_error:
                    raise RuntimeError(
                        f"Batch command failed with exit code {exit_code}"
                    )

                return exit_code == 0

            # Handle Python code execution
            # Support both "command.python" and "command python" formats
            elif "command" in action_lower and "python" in action_lower:
                code = params.get("script", "") or params.get("code", "")
                if not code:
                    raise ValueError("Python command requires 'script' parameter")

                print(f"      🐍 Executing Python code: {code[:50]}...")
                output, result, exit_code = self._command_service.execute_python_code(
                    code=code,
                    working_directory=params.get("working_directory"),
                    timeout=params.get("timeout", 30),
                )

                # Store output if requested
                store_as = params.get("store_as")
                if store_as:
                    variables[store_as] = output
                    print(f"      Stored output as: {store_as}")

                # Store result if requested
                store_result = params.get("store_result")
                if store_result and result is not None:
                    variables[store_result] = result
                    print(f"      Stored result as: {store_result}")

                # Print output
                if output:
                    print(f"      Output:\n{output}")

                # Check if we should fail on error
                fail_on_error = params.get("fail_on_error", True)
                if exit_code != 0 and fail_on_error:
                    raise RuntimeError(
                        f"Python code execution failed with exit code {exit_code}"
                    )

                return exit_code == 0

            else:
                raise ValueError(f"Unknown command action: {action}")

        except Exception as e:
            print(f"      ❌ Command execution failed: {e}")
            # Re-raise to prevent "Unknown action" fallthrough
            raise

    def _extract_nested_value(self, data: dict, path: str) -> Any:
        """Extract a value from nested dict using dot notation path."""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    index = int(key)
                    current = current[index] if 0 <= index < len(current) else None
                except (ValueError, IndexError):
                    return None
            else:
                return None

            if current is None:
                return None

        return current

    def _handle_aws_action(
        self, action: str, step_params: dict, variables: dict
    ) -> bool:
        """Handle AWS S3 actions."""
        from ..services.aws_service import AWSService

        # Get or create AWS service from variables
        aws_service = variables.get("_aws_service")
        if not aws_service:
            aws_service = AWSService(logger=print)
            variables["_aws_service"] = aws_service

        # Extract parameters using helper — resolve ${vars} against current variables
        params = self._get_params(step_params)
        action_lower = action.lower()

        # Log credential source (mask secrets)
        key_id = (
            params.get("access_key_id")
            or variables.get("aws_access_key_id")
            or AWSService._global_config.get("access_key_id")
        )
        if key_id:
            masked = key_id[:4] + "****" + key_id[-4:] if len(key_id) > 8 else "****"
            print(f"      AWS credentials: key_id={masked} (explicit)")
        else:
            print(f"      AWS credentials: using AWS CLI / environment defaults")

        try:
            if any(k in action_lower for k in ("list firmware", "list files", "list_files", "list_firmware")):
                # List and download firmware files
                bucket_name = params.get("bucket_name", "")
                if not bucket_name:
                    raise ValueError("AWS list firmware requires 'bucket_name'")

                # Inject aws_access_key_id / aws_secret_access_key from run variables
                # if the step didn't specify them explicitly
                eff_key    = params.get("access_key_id")    or variables.get("aws_access_key_id")
                eff_secret = params.get("secret_access_key") or variables.get("aws_secret_access_key")

                # Default download_dir: <cwd>/Firmware/<folder_prefix>
                # Mirrors the S3 folder structure under a local Firmware/ root.
                # The directory is created automatically if it doesn't exist.
                folder_prefix = params.get("folder_prefix") or ""
                # If variable substitution left a string-encoded list (e.g.
                # "['upgrade','dummy']"), parse it back to an actual list so
                # aws_service can scan each folder separately.
                if isinstance(folder_prefix, str) and folder_prefix.startswith('['):
                    try:
                        import yaml as _yaml_fp
                        _fp_parsed = _yaml_fp.safe_load(folder_prefix)
                        if isinstance(_fp_parsed, list):
                            folder_prefix = _fp_parsed
                    except Exception:
                        pass
                _raw_download_dir = params.get("download_dir")
                if _raw_download_dir:
                    effective_download_dir = _raw_download_dir
                else:
                    from pathlib import Path as _Path
                    # When folder_prefix is a list use the first entry for the default dir
                    _fp_str = folder_prefix[0] if isinstance(folder_prefix, list) else folder_prefix
                    _rel = (_fp_str or "").lstrip("/").rstrip("/")
                    effective_download_dir = str(_Path.cwd() / "Firmware" / _rel) if _rel else str(_Path.cwd() / "Firmware")

                from pathlib import Path as _Path
                _Path(effective_download_dir).mkdir(parents=True, exist_ok=True)
                print(f"      📁 Download dir: {effective_download_dir}")

                urls = aws_service.list_firmware_files(
                    bucket_name=bucket_name,
                    folder_prefix=folder_prefix,
                    filename_pattern=params.get("filename_pattern"),
                    version_pattern=params.get("version_pattern"),
                    file_extension=params.get("file_extension"),
                    specific_version=params.get("specific_version"),
                    cloudfront_url=params.get("cloudfront_url"),
                    cloudfront_filename_only=params.get(
                        "cloudfront_filename_only", False
                    ),
                    download_dir=effective_download_dir,
                    protocol=params.get("protocol", "https"),
                    access_key_id=eff_key,
                    secret_access_key=eff_secret,
                    region=params.get("region"),
                    discover_prefix=params.get("discover_prefix", False),
                    repo_root=params.get("repo_root") or os.getcwd(),
                )

                # Store URLs in variable if requested
                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = urls
                    print(f"      Stored {len(urls)} URL(s) as: {store_as!r}")

                # Build and store local file paths (always, since we always download now)
                if urls:
                    import os as _os
                    local_paths = [
                        str(_Path(effective_download_dir) / _os.path.basename(u.split("?")[0]))
                        for u in urls
                    ]
                    local_paths_as = params.get("local_paths_as", "")
                    if local_paths_as:
                        variables[local_paths_as] = local_paths
                        print(f"      Stored {len(local_paths)} local path(s) as: {local_paths_as!r}")
                    # Always expose as a predictable name too
                    variables["_aws_local_paths"] = local_paths
                    variables["_aws_local_path"] = local_paths[0]
                    print(f"      Local path(s): {local_paths}")

                # Always expose result as last_response for eval.exec steps
                variables["last_response"] = urls

                if not urls:
                    print(f"      ⚠  0 files matched — check filter params above")
                return True

            elif "get latest firmware" in action_lower:
                # Get latest firmware file
                bucket_name = params.get("bucket_name", "")
                if not bucket_name:
                    raise ValueError(
                        "AWS get latest firmware requires " "'bucket_name'"
                    )

                result = aws_service.get_latest_firmware(
                    bucket_name=bucket_name,
                    folder_prefix=params.get("folder_prefix"),
                    filename_pattern=params.get("filename_pattern"),
                    version_pattern=params.get("version_pattern"),
                    file_extension=params.get("file_extension", ".bin"),
                    download_dir=params.get("download_dir"),
                    get_second_to_last=params.get("get_second_to_last", False),
                    access_key_id=params.get("access_key_id"),
                    secret_access_key=params.get("secret_access_key"),
                    region=params.get("region"),
                    discover_prefix=params.get("discover_prefix", False),
                    repo_root=params.get("repo_root") or os.getcwd(),
                )

                # Store individual values if requested
                if params.get("store_filename_as") and result["filename"]:
                    variables[params["store_filename_as"]] = result["filename"]
                    print(
                        f"      Stored filename as: " f"{params['store_filename_as']}"
                    )
                    # Also store basename for easy file path construction
                    if "basename" in result:
                        variables[f"{params['store_filename_as']}_basename"] = result[
                            "basename"
                        ]

                if params.get("store_version_as") and result["version"]:
                    variables[params["store_version_as"]] = result["version"]
                    print(f"      Stored version as: " f"{params['store_version_as']}")

                if params.get("store_url_as") and result["url"]:
                    variables[params["store_url_as"]] = result["url"]
                    print(f"      Stored URL as: {params['store_url_as']}")

                store_as = params.get("store_as", "")
                if store_as:
                    variables[store_as] = result
                    print(f"      Stored result as: {store_as}")

                return True

            elif "upload" in action_lower:
                # Upload file to S3
                bucket_name = params.get("bucket_name", "")
                local_file = params.get("local_file_path", "")

                if not bucket_name or not local_file:
                    raise ValueError(
                        "AWS upload requires 'bucket_name' and " "'local_file_path'"
                    )

                url = aws_service.upload_file(
                    bucket_name=bucket_name,
                    local_file_path=local_file,
                    s3_key=params.get("s3_key"),
                    make_public=params.get("make_public", True),
                    access_key_id=params.get("access_key_id"),
                    secret_access_key=params.get("secret_access_key"),
                    region=params.get("region"),
                )

                # Store URL if requested
                store_as = params.get("store_as", "")
                if store_as and url:
                    variables[store_as] = url
                    print(f"      Stored URL as: {store_as}")

                return True

            elif "delete folder" in action_lower:
                # Delete folder from S3
                bucket_name = params.get("bucket_name", "")
                folder_prefix = params.get("folder_prefix", "")

                if not bucket_name or not folder_prefix:
                    raise ValueError(
                        "AWS delete folder requires 'bucket_name' "
                        "and 'folder_prefix'"
                    )

                aws_service.delete_folder(
                    bucket_name=bucket_name,
                    folder_prefix=folder_prefix,
                    access_key_id=params.get("access_key_id"),
                    secret_access_key=params.get("secret_access_key"),
                    region=params.get("region"),
                )

                return True

            else:
                print(f"      ❌ Unknown AWS action: {action}")
                raise ValueError(f"Unknown AWS action: {action}")

        except Exception as e:
            print(f"      ❌ AWS action failed: {e}")
            raise

    def _get_params(self, step_params: dict) -> dict:
        """Extract parameters dict from step_params (handles nested structure)."""
        return step_params.get("parameters", {})

    def _get_param(self, step_params: dict, key: str, default=None):
        """Get parameter from step_params, checking both top level and nested."""
        # Check top level first
        if key in step_params and step_params[key] not in (None, ""):
            return step_params[key]
        # Check nested parameters
        params = step_params.get("parameters", {})
        return params.get(key, default)

    def _normalize_action(self, action: str) -> str:
        """Normalize action name to handle both dot notation and legacy formats"""
        action_lower = action.lower()

        # If no dot notation, return as-is (legacy format)
        if "." not in action_lower:
            return action_lower

        # Map dot notation to legacy action names for backward compatibility
        action_map = {
            "browser.open": "open browser",
            "browser.click": "click element",
            "browser.fill": "fill field",
            "browser.upload": "upload file",
            "browser.screenshot": "take screenshot",
            "browser.wait": "wait",
            "browser.select": "select option",
            "browser.hover": "hover element",
            "browser.refresh": "refresh browser",
            "browser.back": "navigate back",
            "browser.forward": "navigate forward",
            "browser.double_click": "double click element",
            "browser.press_key": "press key",
            "browser.wait_for": "wait for element",
            "browser.verify_text": "verify text",
            "browser.verify_element": "verify element",
            "aws.list_files": "aws list firmware files",
            "aws.get_latest": "aws get latest firmware",
            "aws.upload": "aws upload file",
            "aws.delete_folder": "aws delete folder",
            "jsonrpc.connect": "jsonrpc connect",
            "jsonrpc.disconnect": "jsonrpc disconnect",
            "jsonrpc.get_about": "jsonrpc get about",
            "jsonrpc.start_updates": "jsonrpc start device updates",
            "jsonrpc.stop_updates": "jsonrpc stop device updates",
            "jsonrpc.reset_device": "jsonrpc reset device",
            "ovrc.connect": "ovrc connect",
            "ovrc.disconnect": "ovrc disconnect",
            "ovrc.get_about": "ovrc get about",
            "ovrc.get about": "ovrc get about",
            "ovrc.start device updates": "ovrc start device updates",
            "ovrc.start_device_updates": "ovrc start device updates",
            "ovrc.stop device updates": "ovrc stop device updates",
            "ovrc.stop_device_updates": "ovrc stop device updates",
            "ovrc.get network settings": "ovrc get network settings",
            "ovrc.get_network_settings": "ovrc get network settings",
            "ovrc.get time settings": "ovrc get time settings",
            "ovrc.get_time_settings": "ovrc get time settings",
            "ovrc.send": "ovrc send",
            "ovrc.call": "ovrc send",
            "test.assert": "assert",
            "test.assert_schema": "assert json schema",
            "test.assert_response": "assert response",
            "test.wait": "wait",
            "log": "log",
            # API actions - map dot notation to space notation
            "api.request": "api request",
            "api.get": "api get",
            "api.post": "api post",
            "api.put": "api put",
            "api.patch": "api patch",
            "api.delete": "api delete",
            # Command actions
            "command.ssh": "command ssh",
            "command.shell": "command shell",
            "command.bash": "command bash",
            "command.powershell": "command powershell",
            "command.batch": "command batch",
            "command.python": "command python",
        }

        return action_map.get(action_lower, action_lower)

    def _execute_step(
        self,
        service,
        step,
        variables: dict,
        soft_assert_manager: SoftAssertionManager = None,
        step_number: int = 0,
    ) -> bool:
        """Execute a single step using the appropriate service"""
        # Check if retry configuration is present
        if hasattr(step, "retry_config") and step.retry_config:
            retry_config = RetryConfig(
                max_attempts=step.retry_config.get("max_attempts", 3),
                delay=step.retry_config.get("delay", 1.0),
                backoff_multiplier=step.retry_config.get("backoff_multiplier", 2.0),
                max_delay=step.retry_config.get("max_delay", 30.0),
            )

            # Wrap the execution in retry logic
            return retry_action(
                lambda: self._execute_step_internal(
                    service, step, variables, soft_assert_manager, step_number
                ),
                retry_config,
            )
        else:
            # Execute without retry
            return self._execute_step_internal(
                service, step, variables, soft_assert_manager, step_number
            )

    def _resolve_step_params(self, step, variables: dict) -> dict:
        """Resolve step variables for display and execution using the same rules."""
        if hasattr(self.config, "substitute_recursive"):
            # For GlobalConfigManager, set test variables in runtime scope
            for key, value in variables.items():
                self.config.set_variable(key, value, "runtime_data")

            # First, resolve nested variables in the test variables
            resolved_vars = variables.copy()
            max_iterations = 10
            for iteration in range(max_iterations):
                previous_vars = resolved_vars.copy()
                for key, value in resolved_vars.items():
                    if isinstance(value, str):
                        new_value = self.config.substitute_variables(
                            value, resolved_vars
                        )
                        resolved_vars[key] = new_value
                if resolved_vars == previous_vars:
                    break

            for key, value in resolved_vars.items():
                self.config.set_variable(key, value, "runtime_data")

            return self.config.substitute_recursive(
                step.__dict__.copy(), additional_vars=variables
            )

        resolved_vars = variables.copy()
        for _ in range(3):
            for key, value in resolved_vars.items():
                if isinstance(value, str):
                    resolved_vars[key] = self._replace_variables(
                        value, resolved_vars
                    )

        return self._replace_variables(step.__dict__.copy(), resolved_vars)

    def _execute_step_internal(
        self,
        service,
        step,
        variables: dict,
        soft_assert_manager: SoftAssertionManager = None,
        step_number: int = 0,
    ) -> bool:
        """Internal method to execute a single step (called by _execute_step with or without retry)"""
        try:
            # Control-flow constructs — handled before variable substitution
            action_tag = getattr(step, "action", "")
            if action_tag == "for_loop":
                return self._execute_for_loop(step, variables, soft_assert_manager, step_number)
            if action_tag == "while_loop":
                return self._execute_while_loop(step, variables, soft_assert_manager, step_number)
            if action_tag == "try_except":
                return self._execute_try_except(step, variables, soft_assert_manager, step_number)
            if action_tag == "break":
                raise _BreakSignal()
            if action_tag == "continue":
                raise _ContinueSignal()

            # Check if this is a conditional step
            if hasattr(step, "condition") and step.condition:
                return self._execute_conditional_step(
                    service, step, variables, soft_assert_manager, step_number
                )

            step_params = self._resolve_step_params(step, variables)

            action = step_params.get("action", "").lower()
            # Normalize action (convert dot notation to legacy format)
            action = self._normalize_action(action)

            # Check for custom actions first
            if self._execute_custom_action(
                action, step_params, variables, soft_assert_manager
            ):
                return True

            # Execute browser actions
            has_open_browser = hasattr(service, "open_browser")
            is_browser_open = "open" in action and "browser" in action
            if has_open_browser and is_browser_open:
                url = step_params.get("url", "") or step_params.get(
                    "parameters", {}
                ).get("url", "")
                print(f"      Opening URL: '{url}'")
                service.open_browser(url)
                return True

            elif hasattr(service, "click_element") and "click" in action:
                params = self._get_params(step_params)
                selector = params.get("selector", "")
                text = params.get("text", "")
                button = params.get("button", "")
                role = params.get("role", "")
                name = params.get("name", "")
                label = params.get("label", "")
                service.click_element(
                    selector=selector, text=text, button=button, role=role, name=name, label=label
                )
                return True

            elif hasattr(service, "fill_form_field") and "fill" in action:
                field = self._get_param(step_params, "field", "")
                value = self._get_param(step_params, "value", "")
                selector = self._get_param(step_params, "selector", "")
                role = self._get_param(step_params, "role", "")
                name = self._get_param(step_params, "name", "")
                label = self._get_param(step_params, "label", "")

                if role and name:
                    print(f"      Filling {role} '{name}' with value '{value}'")
                    service.fill_form_field("", value, role=role, name=name)
                elif label:
                    print(f"      Filling field labeled '{label}' with value '{value}'")
                    service.fill_form_field("", value, label=label)
                elif field:
                    print(f"      Filling field '{field}' with value '{value}'")
                    service.fill_form_field(field, value)
                elif selector:
                    print(f"      Filling field '{selector}' with value '{value}'")
                    service.fill_form_field(selector, value)
                return True

            elif hasattr(service, "take_screenshot") and "screenshot" in action:
                name = self._get_param(step_params, "name", "screenshot")
                service.take_screenshot(name)
                return True

            elif (
                hasattr(service, "verify_text")
                and "verify" in action
                and "text" in action
            ):
                text = self._get_param(step_params, "text", "")
                soft_assert = self._get_param(step_params, "soft_assert", False)
                print(f"      Verifying text: '{text}'")
                service.verify_text(
                    text,
                    soft_assert=soft_assert,
                    soft_assert_manager=soft_assert_manager,
                    step_number=step_number,
                )
                return True

            elif (
                hasattr(service, "verify_element")
                and "verify" in action
                and "element" in action
            ):
                selector = self._get_param(step_params, "selector", "")
                soft_assert = self._get_param(step_params, "soft_assert", False)
                print(f"      Verifying element: '{selector}'")
                service.verify_element(
                    selector,
                    soft_assert=soft_assert,
                    soft_assert_manager=soft_assert_manager,
                    step_number=step_number,
                )
                return True

            elif hasattr(service, "refresh_browser") and "refresh" in action:
                print("      Refreshing browser")
                service.refresh_browser()
                return True

            # ===== PLAYWRIGHT NATIVE API ACTIONS =====

            elif hasattr(service, "get_by_role") and "get by role" in action:
                role = step_params.get("role", "")
                name = step_params.get("name", "")
                service.get_by_role(role, name)
                return True

            elif hasattr(service, "get_by_text") and "get by text" in action:
                text = step_params.get("text", "")
                exact = step_params.get("exact", False)
                service.get_by_text(text, exact=exact)
                return True

            elif hasattr(service, "get_by_label") and "get by label" in action:
                label = step_params.get("label", "")
                action_type = step_params.get("action_type", "click")
                value = step_params.get("value", "")
                service.get_by_label(label, action=action_type, value=value)
                return True

            elif hasattr(service, "hover_element") and "hover" in action:
                selector = step_params.get("selector", "")
                service.hover_element(selector)
                return True

            elif hasattr(service, "double_click_element") and "double click" in action:
                selector = step_params.get("selector", "")
                service.double_click_element(selector)
                return True

            elif hasattr(service, "press_key") and "press key" in action:
                key = step_params.get("key", "")
                selector = step_params.get("selector", "")
                service.press_key(key, selector)
                return True

            elif hasattr(service, "wait_for_element") and "wait for element" in action:
                params = self._get_params(step_params)
                selector = params.get("selector", "")
                state = params.get("state", "visible")
                timeout = params.get("timeout", None)
                service.wait_for_element(selector, state=state, timeout=timeout)
                return True

            elif hasattr(service, "select_option") and "select option" in action:
                params = self._get_params(step_params)
                selector = params.get("selector", "")
                value = params.get("value", "")
                label = params.get("label", "")
                service.select_option(selector, value=value, label=label)
                return True

            elif hasattr(service, "upload_file") and "upload" in action:
                selector = self._get_param(step_params, "selector", "")
                file_path = self._get_param(step_params, "file_path", "")
                service.upload_file(selector, file_path)
                return True

            elif hasattr(service, "navigate_back") and "navigate back" in action:
                service.navigate_back()
                return True

            elif hasattr(service, "navigate_forward") and "navigate forward" in action:
                service.navigate_forward()
                return True

            # ===== TEST ASSERTIONS =====
            # Handle test.assert actions (e.g., test.assert_text_contains, test.assert_element_visible)
            elif action == "test.assert_text_contains" or (hasattr(service, "assert_text_contains") and "assert" in action and "text" in action and "contains" in action):
                selector = self._get_param(step_params, "selector", "")
                text = self._get_param(step_params, "text", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' contains text '{text}'")
                service.assert_text_contains(selector, text, timeout=timeout)
                return True

            elif action == "test.assert_text_equals" or (hasattr(service, "assert_text_equals") and "assert" in action and "text" in action and "equals" in action):
                selector = self._get_param(step_params, "selector", "")
                text = self._get_param(step_params, "text", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' text equals '{text}'")
                service.assert_text_equals(selector, text, timeout=timeout)
                return True

            elif action == "test.assert_element_visible" or (hasattr(service, "assert_element_visible") and "assert" in action and "element" in action and "visible" in action and "not" not in action):
                selector = self._get_param(step_params, "selector", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' is visible")
                service.assert_element_visible(selector, timeout=timeout)
                return True

            elif action == "test.assert_element_not_visible" or (hasattr(service, "assert_element_not_visible") and "assert" in action and "element" in action and "not" in action and "visible" in action):
                selector = self._get_param(step_params, "selector", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' is not visible")
                service.assert_element_not_visible(selector, timeout=timeout)
                return True

            elif action == "test.assert_element_enabled" or (hasattr(service, "assert_element_enabled") and "assert" in action and "element" in action and "enabled" in action):
                selector = self._get_param(step_params, "selector", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' is enabled")
                service.assert_element_enabled(selector, timeout=timeout)
                return True

            elif action == "test.assert_element_disabled" or (hasattr(service, "assert_element_disabled") and "assert" in action and "element" in action and "disabled" in action):
                selector = self._get_param(step_params, "selector", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' is disabled")
                service.assert_element_disabled(selector, timeout=timeout)
                return True

            elif action == "test.assert_element_count" or (hasattr(service, "assert_element_count") and "assert" in action and "element" in action and "count" in action):
                selector = self._get_param(step_params, "selector", "")
                count = self._get_param(step_params, "count", 1)
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' count equals {count}")
                service.assert_element_count(selector, count, timeout=timeout)
                return True

            elif action in ("browser.assert_checked", "test.assert_checked") or (hasattr(service, "assert_checked") and "assert" in action and "checked" in action and "un" not in action):
                selector = self._get_param(step_params, "selector", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' is checked")
                service.assert_checked(selector, timeout=timeout)
                return True

            elif action in ("browser.assert_unchecked", "test.assert_unchecked") or (hasattr(service, "assert_unchecked") and "assert" in action and "unchecked" in action):
                selector = self._get_param(step_params, "selector", "")
                timeout = self._get_param(step_params, "timeout", 10000)
                print(f"      Asserting element '{selector}' is unchecked")
                service.assert_unchecked(selector, timeout=timeout)
                return True

            elif "wait" in action:
                params = self._get_params(step_params)
                wait_time = (
                    params.get("seconds")
                    or params.get("duration")
                    or params.get("time")
                    or 1
                )
                if isinstance(wait_time, str):
                    try:
                        wait_time = float(wait_time)
                    except ValueError:
                        wait_time = 1
                else:
                    wait_time = float(wait_time)
                print(f"      ⏳ Sleeping {wait_time}s...")
                time.sleep(wait_time)
                return True

            elif action == "log":
                # Log action - print a message with variable substitution
                message = self._get_param(step_params, "message", "")
                # Substitute variables in message
                if hasattr(self.config, "substitute_variables"):
                    message = self.config.substitute_variables(message, variables)
                else:
                    # Fallback variable substitution
                    import re

                    def replace_var(match):
                        var_name = match.group(1)
                        return str(variables.get(var_name, match.group(0)))

                    message = re.sub(r"\$\{([^}]+)\}", replace_var, message)
                print(f"      📝 {message}")
                return True

            # API Actions - order matters, check specific actions first
            elif hasattr(service, "request") and "api request" in action:
                # Get parameters from nested structure or top level
                params_dict = step_params.get("parameters", {})
                method = (
                    params_dict.get("method") or step_params.get("method", "GET")
                ).upper()
                url = step_params.get("url", "") or params_dict.get("url", "")
                device_id = step_params.get("device_id", "") or params_dict.get(
                    "device_id", "default"
                )
                headers = step_params.get("headers", {}) or params_dict.get(
                    "headers", {}
                )
                json_data = (
                    step_params.get("json_data")
                    or params_dict.get("json_data")
                    or step_params.get("body")
                    or params_dict.get("body")
                )
                # If body/json_data is still empty, collect any unknown top-level
                # params as body fields (handles mis-indented YAML where body fields
                # end up as siblings of 'body:' rather than children)
                if not json_data:
                    _known = {
                        "method", "url", "device_id", "headers", "json_data",
                        "body", "data", "params", "store_as", "store_response",
                        "fail_on_error", "verbose_logging", "show_full_response",
                        "full_log", "parameters", "Accept", "Content-Type",
                        "API POST", "API GET", "API PUT", "API PATCH", "API DELETE",
                    }
                    _extra = {k: v for k, v in step_params.items() if k not in _known and v is not None}
                    if _extra:
                        print(f"      ⚠  'body' is empty — using top-level params as body: {list(_extra.keys())}")
                        json_data = _extra
                    else:
                        json_data = {}
                data = step_params.get("data", {}) or params_dict.get("data", {})
                params = step_params.get("params", {}) or params_dict.get("params", {})

                # Check for verbose logging
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", True)
                    or step_params.get("show_full_response", False)
                    or step_params.get("full_log", False)
                    or params_dict.get("verbose_logging", True)
                    or params_dict.get("show_full_response", False)
                    or params_dict.get("full_log", False)
                )
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )

                # Sync mybdd-style login vars (login_path, login_json, token_path)
                # into the auth_manager config so 401 auto-retry can authenticate.
                _login_path = variables.get("login_path", "")
                _login_json_raw = variables.get("login_json", "")
                _token_path = variables.get("token_path", "accessToken")
                if _login_path and _login_json_raw and hasattr(service, "auth_manager"):
                    _base = variables.get("url", "").rstrip("/")
                    _auth_ep = _base + _login_path if _login_path.startswith("/") else _login_path
                    try:
                        import ast as _ast
                        _creds = _ast.literal_eval(str(_login_json_raw)) if isinstance(_login_json_raw, str) else _login_json_raw
                    except Exception:
                        _creds = {}
                    _auth_cfg = {
                        "type": "bearer_token",
                        "endpoint": _auth_ep,
                        "additional_fields": _creds,  # pass login_json verbatim as payload
                        "token_field": _token_path,
                        "headers": variables.get("headers", {}),
                        "verify_ssl": False,
                    }
                    existing = service.auth_manager.get_auth_config(device_id or "default")
                    if not existing.get("endpoint"):
                        service.auth_manager.config_manager.api_config_manager.auth_configs[device_id or "default"] = _auth_cfg

                print(f"      API {method}: {url} (device: {device_id})")
                if verbose_logging:
                    import json

                    if headers:
                        print(f"         Headers: {json.dumps(headers, indent=2)}")
                    if params:
                        print(f"         Query Params: {json.dumps(params, indent=2)}")
                    if json_data:
                        print(f"         Request Body:")
                        body_str = json.dumps(json_data, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    elif data:
                        print(f"         Request Data: {data}")

                response = service.request(
                    method,
                    url,
                    device_id,
                    headers=headers,
                    json=json_data or None,
                    data=data or None,
                    params=params or None,
                )

                # Store response for validation
                variables["last_response"] = response
                variables["last_status"] = response.status_code

                # Parse JSON if content type is JSON
                content_type = response.headers.get("content-type", "")
                is_json = content_type.startswith("application/json")
                response_json = None
                try:
                    response_json = response.json()
                    variables["last_json"] = response_json
                    is_json = True
                except Exception:
                    variables["last_json"] = None

                # Print full response if verbose logging enabled
                if verbose_logging:
                    import json

                    print(f"         Status: {response.status_code}")
                    print(
                        f"         Response Headers: {json.dumps(dict(response.headers), indent=2)}"
                    )
                    if is_json and response_json:
                        print(f"         Response Body:")
                        body_str = json.dumps(response_json, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    else:
                        print(
                            f"         Response Body: {response.text[:500]}{'...' if len(response.text) > 500 else ''}"
                        )
                else:
                    print(f"         Status: {response.status_code}")

                # Store response in custom variable if specified
                store_as = (
                    step_params.get("store_response")
                    or params_dict.get("store_response")
                    or step_params.get("store_as")
                    or params_dict.get("store_as")
                )
                if store_as:
                    response_dict = {
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body": response.text,
                        "data": response_json if is_json else response.text,
                        "response_time": response.elapsed.total_seconds()
                        * 1000,  # in milliseconds
                    }
                    variables[store_as] = response_dict
                    if hasattr(self.config, "set_variable"):
                        self.config.set_variable(
                            store_as, response_dict, "runtime_data"
                        )
                    print(f"      Stored response as: {store_as}")

                # Check if we should fail on error status codes
                fail_on_error = step_params.get(
                    "fail_on_error", True
                ) or params_dict.get("fail_on_error", True)
                if isinstance(fail_on_error, str):
                    fail_on_error = fail_on_error.lower() in ("true", "1", "yes", "on")

                if fail_on_error and response.status_code >= 400:
                    import json

                    error_msg = f"API request failed with status {response.status_code}"
                    if is_json and response_json:
                        error_msg += f": {json.dumps(response_json, indent=2)}"
                    elif response.text:
                        error_msg += f": {response.text[:200]}"
                    print(f"      ❌ {error_msg}")
                    raise ValueError(error_msg)

                return True

            elif hasattr(service, "get") and action.strip() == "api get":
                # Get parameters using helper
                url = self._get_param(step_params, "url", "")
                device_id = self._get_param(step_params, "device_id", "default")
                headers = self._get_param(step_params, "headers", {})
                params = self._get_param(step_params, "params", {})

                # Resolve URL with variable substitution (handles URL-encoded variables)
                url = self._resolve_url_with_variables(url, variables)

                # Automatically add Authorization header if token is available
                # Check for token in variables (common names: token, auth_token, auth_token_{device_id}, {store_as}_token)
                if not headers:
                    headers = {}
                elif isinstance(headers, str):
                    # If headers is a string, try to parse it as JSON
                    try:
                        import json

                        headers = json.loads(headers) if headers.strip() else {}
                    except:
                        headers = {}

                # Check for stored token
                token = None
                if device_id and device_id != "default":
                    token = variables.get(f"auth_token_{device_id}")
                if not token:
                    token = variables.get("auth_token")
                if not token:
                    # Check if there's a variable named "token" (from store_as: token)
                    token = variables.get("token")
                    # If token is a dict (stored response), try to extract the actual token value
                    if isinstance(token, dict):
                        # Try common token field names
                        for field in [
                            "token",
                            "access_token",
                            "accessToken",
                            "auth_token",
                            "authToken",
                            "data",
                            "result",
                        ]:
                            if field in token:
                                field_value = token[field]
                                # If the field value is a string, use it
                                if isinstance(field_value, str):
                                    token = field_value
                                    break
                                # If the field value is a dict, check if it has a token field
                                elif isinstance(field_value, dict):
                                    for sub_field in [
                                        "token",
                                        "access_token",
                                        "accessToken",
                                    ]:
                                        if sub_field in field_value:
                                            token = field_value[sub_field]
                                            break
                                    if isinstance(token, str):
                                        break
                        # If still a dict, try getting the first string value if it looks like a token
                        if isinstance(token, dict):
                            for value in token.values():
                                if (
                                    isinstance(value, str)
                                    and len(value) > 10
                                    and " " not in value
                                ):
                                    token = value
                                    break
                if not token:
                    # Check for token in stored response objects
                    for key, value in variables.items():
                        if isinstance(value, dict):
                            # Try common token field names
                            for field in [
                                "token",
                                "access_token",
                                "accessToken",
                                "auth_token",
                                "authToken",
                            ]:
                                if field in value:
                                    field_value = value[field]
                                    if isinstance(field_value, str):
                                        token = field_value
                                        break
                            if token:
                                break

                # Add Authorization header if token found
                if token and "Authorization" not in headers:
                    # Ensure token is a string
                    if not isinstance(token, str):
                        token = str(token)
                    headers["Authorization"] = f"Bearer {token}"
                    print(f"      🔑 Using stored token for authentication")
                elif not token:
                    print(
                        f"      ⚠️  No token found. Checking variables: {list(variables.keys())}"
                    )
                    # Debug: print what's in the "token" variable if it exists
                    if "token" in variables:
                        print(
                            f"      🔍 'token' variable type: {type(variables['token'])}, value: {str(variables['token'])[:100]}"
                        )

                # Check for verbose logging
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", True)
                    or step_params.get("show_full_response", False)
                    or step_params.get("full_log", False)
                )
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )

                print(f"      API GET: {url} (device: {device_id})")
                if verbose_logging:
                    import json

                    if headers:
                        print(f"         📋 Request Headers:")
                        headers_str = json.dumps(headers, indent=2)
                        for line in headers_str.split("\n"):
                            print(f"           {line}")
                    if params:
                        print(f"         🔍 Query Params:")
                        params_str = json.dumps(params, indent=2)
                        for line in params_str.split("\n"):
                            print(f"           {line}")

                response = service.get(url, device_id, headers=headers, params=params)

                # Handle 401 errors by attempting to re-authenticate
                if response.status_code == 401:
                    print(f"      🔄 Received 401, attempting to re-authenticate...")
                    # Check if we have login credentials in variables
                    login_url = None
                    login_body = None

                    # Try to find login endpoint and credentials
                    api_base_url = variables.get("api_base_url", "")
                    # Resolve api_base_url if it contains variables
                    if api_base_url:
                        api_base_url = self._resolve_url_with_variables(
                            api_base_url, variables
                        )
                        # Common login endpoints
                        for endpoint in [
                            "/auth/login",
                            "/login",
                            "/auth/token",
                            "/token",
                        ]:
                            if endpoint in url or api_base_url.endswith(
                                endpoint.replace("/", "")
                            ):
                                login_url = (
                                    f"{api_base_url}{endpoint}"
                                    if not api_base_url.endswith(endpoint)
                                    else api_base_url
                                )
                                break

                    # If no explicit login URL found, try common pattern
                    if not login_url and api_base_url:
                        login_url = f"{api_base_url}/auth/login"

                    # Get credentials from variables
                    username = variables.get("username")
                    password = variables.get("password")

                    if login_url and username and password:
                        # Ensure login_url is fully resolved
                        login_url = self._resolve_url_with_variables(
                            login_url, variables
                        )
                        import json

                        login_body = json.dumps(
                            {"username": username, "password": password}
                        )
                        print(f"      🔑 Re-authenticating with stored credentials...")
                        # Make login request
                        login_response = service.post(
                            login_url, device_id, json=json.loads(login_body)
                        )
                        if login_response.status_code == 200:
                            login_json = login_response.json()
                            # Extract token
                            token_fields = [
                                "token",
                                "access_token",
                                "accessToken",
                                "auth_token",
                                "authToken",
                            ]
                            for field in token_fields:
                                if field in login_json:
                                    token = login_json[field]
                                    variables["auth_token"] = token
                                    if device_id and device_id != "default":
                                        variables[f"auth_token_{device_id}"] = token
                                    headers["Authorization"] = f"Bearer {token}"
                                    print(f"      ✅ Re-authenticated successfully")
                                    # Retry the original request
                                    response = service.get(
                                        url, device_id, headers=headers, params=params
                                    )
                                    break
                        else:
                            print(
                                f"      ⚠️  Re-authentication failed: {login_response.status_code}"
                            )

                # Store response for validation
                variables["last_response"] = response
                variables["last_status"] = response.status_code

                # Parse JSON response
                content_type = response.headers.get("content-type", "")
                is_json = content_type.startswith("application/json")
                response_json = None
                try:
                    response_json = response.json()
                    variables["last_json"] = response_json
                    is_json = True
                except Exception:
                    variables["last_json"] = None

                # Print full response if verbose logging enabled
                if verbose_logging:
                    import json

                    print(f"         📡 Status: {response.status_code}")
                    print(f"         📋 Response Headers:")
                    headers_str = json.dumps(dict(response.headers), indent=2)
                    for line in headers_str.split("\n"):
                        print(f"           {line}")
                    if is_json and response_json:
                        print(f"         📦 Response Body (JSON):")
                        body_str = json.dumps(response_json, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    else:
                        # Show FULL response text, not truncated
                        print(f"         📦 Response Body:")
                        # Print full response, handling long responses
                        if len(response.text) > 0:
                            for line in response.text.split("\n"):
                                print(f"           {line}")
                        else:
                            print(f"           (empty)")
                else:
                    # Always show a brief response preview so test authors can verify output
                    import json as _j
                    _body_preview = ""
                    if is_json and response_json:
                        _raw = _j.dumps(response_json)
                        _body_preview = _raw[:200] + ("…" if len(_raw) > 200 else "")
                    elif response.text:
                        _t = response.text.strip()
                        _body_preview = _t[:200] + ("…" if len(_t) > 200 else "")
                    if _body_preview:
                        print(f"         📡 Status: {response.status_code} | {_body_preview}")
                    else:
                        print(f"         📡 Status: {response.status_code}")

                # Check if we should fail on error status codes
                fail_on_error = step_params.get("fail_on_error", True)
                if isinstance(fail_on_error, str):
                    fail_on_error = fail_on_error.lower() in ("true", "1", "yes", "on")

                if fail_on_error and response.status_code >= 400:
                    import json

                    error_msg = f"API request failed with status {response.status_code}"
                    if is_json and response_json:
                        error_msg += f": {json.dumps(response_json, indent=2)}"
                    elif response.text:
                        error_msg += f": {response.text[:200]}"
                    print(f"      ❌ {error_msg}")
                    raise ValueError(error_msg)

                return True

            elif hasattr(service, "post") and action.strip() == "api post":
                # Get parameters using helper
                url = self._get_param(step_params, "url", "")
                device_id = self._get_param(step_params, "device_id", "default")
                headers = self._get_param(step_params, "headers", {})
                json_data = self._get_param(step_params, "json_data", {})
                data = self._get_param(step_params, "data", {})

                # Resolve URL with variable substitution (handles URL-encoded variables)
                url = self._resolve_url_with_variables(url, variables)

                # Handle 'body' parameter - it can be a JSON string that needs parsing
                body_param = self._get_param(step_params, "body", None)
                if body_param and not json_data and not data:
                    # If body is a string, try to parse it as JSON after variable substitution
                    if isinstance(body_param, str):
                        import json

                        try:
                            # Parse the JSON string (variables should already be substituted by substitute_recursive)
                            json_data = json.loads(body_param)
                        except json.JSONDecodeError:
                            # If parsing fails, treat as plain text data
                            data = body_param
                    else:
                        # Body is already a dict/list
                        json_data = body_param

                # Check for verbose logging
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", True)
                    or step_params.get("show_full_response", False)
                    or step_params.get("full_log", False)
                )
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )

                print(f"      API POST: {url} (device: {device_id})")
                if verbose_logging:
                    import json

                    if headers:
                        print(f"         📋 Request Headers:")
                        headers_str = json.dumps(headers, indent=2)
                        for line in headers_str.split("\n"):
                            print(f"           {line}")
                    if json_data:
                        print(f"         📤 Request Body (JSON):")
                        body_str = json.dumps(json_data, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    elif data:
                        print(f"         📤 Request Body:")
                        if isinstance(data, str):
                            for line in data.split("\n"):
                                print(f"           {line}")
                        else:
                            print(f"           {data}")

                response = service.post(
                    url,
                    device_id,
                    headers=headers,
                    json=json_data or None,
                    data=data or None,
                )

                # Store response for validation
                variables["last_response"] = response
                variables["last_status"] = response.status_code

                # Parse JSON response
                content_type = response.headers.get("content-type", "")
                is_json = content_type.startswith("application/json")
                response_json = None
                try:
                    response_json = response.json()
                    variables["last_json"] = response_json
                    is_json = True
                except Exception:
                    variables["last_json"] = None

                # Print full response if verbose logging enabled
                if verbose_logging:
                    import json

                    print(f"         📡 Status: {response.status_code}")
                    print(f"         📋 Response Headers:")
                    headers_str = json.dumps(dict(response.headers), indent=2)
                    for line in headers_str.split("\n"):
                        print(f"           {line}")
                    if is_json and response_json:
                        print(f"         📦 Response Body (JSON):")
                        body_str = json.dumps(response_json, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    else:
                        # Show FULL response text, not truncated
                        print(f"         📦 Response Body:")
                        if len(response.text) > 0:
                            for line in response.text.split("\n"):
                                print(f"           {line}")
                        else:
                            print(f"           (empty)")
                else:
                    print(f"         📡 Status: {response.status_code}")

                # Handle store_as parameter - extract and store token/response
                store_as = self._get_param(step_params, "store_as", "")
                if store_as:
                    import json

                    if is_json and response_json:
                        # Store the full JSON response
                        variables[store_as] = response_json
                        # Also try to extract common token fields and store them
                        # Common token field names: token, access_token, accessToken, auth_token, authToken
                        token_fields = [
                            "token",
                            "access_token",
                            "accessToken",
                            "auth_token",
                            "authToken",
                            "bearer_token",
                            "bearerToken",
                        ]
                        token_value = None
                        token_field_found = None

                        for field in token_fields:
                            if field in response_json:
                                token_value = response_json[field]
                                token_field_found = field
                                break

                        # If no standard token field found, check if the response itself is a token string
                        if not token_value:
                            # Check if response_json is a simple string token
                            if isinstance(response_json, str):
                                token_value = response_json
                                token_field_found = "response_body"
                            # Check if response_json is a dict with a single key-value that might be the token
                            elif (
                                isinstance(response_json, dict)
                                and len(response_json) == 1
                            ):
                                # If it's a single key-value pair, use the value as the token
                                token_value = list(response_json.values())[0]
                                token_field_found = list(response_json.keys())[0]

                        if token_value:
                            # Store token in a variable named after store_as
                            variables[f"{store_as}_token"] = token_value
                            # Also store as auth_token for the device_id if available
                            if device_id and device_id != "default":
                                variables[f"auth_token_{device_id}"] = token_value
                            # Store in global auth_token variable
                            variables["auth_token"] = token_value
                            # Also store as plain "token" variable for easy access
                            variables["token"] = token_value
                            print(
                                f"      🔑 Extracted and stored token from field '{token_field_found}': {str(token_value)[:20]}..."
                            )
                        else:
                            print(
                                f"      ⚠️  No token field found in response. Available fields: {list(response_json.keys()) if isinstance(response_json, dict) else 'N/A'}"
                            )
                        print(f"      💾 Stored response as: {store_as}")
                    else:
                        # Store text response
                        variables[store_as] = response.text
                        # If it looks like a token (no spaces, reasonable length), also store as token
                        if (
                            response.text
                            and len(response.text.strip()) < 500
                            and " " not in response.text.strip()
                        ):
                            token_value = response.text.strip()
                            variables["auth_token"] = token_value
                            variables["token"] = token_value
                            if device_id and device_id != "default":
                                variables[f"auth_token_{device_id}"] = token_value
                            print(f"      🔑 Extracted token from response text")
                        print(f"      💾 Stored response text as: {store_as}")

                # Check if we should fail on error status codes
                fail_on_error = step_params.get("fail_on_error", True)
                if isinstance(fail_on_error, str):
                    fail_on_error = fail_on_error.lower() in ("true", "1", "yes", "on")

                if fail_on_error and response.status_code >= 400:
                    import json

                    error_msg = f"API request failed with status {response.status_code}"
                    if is_json and response_json:
                        error_msg += f": {json.dumps(response_json, indent=2)}"
                    elif response.text:
                        error_msg += f": {response.text[:200]}"
                    print(f"      ❌ {error_msg}")
                    raise ValueError(error_msg)

                return True

            elif hasattr(service, "put") and action.strip() == "api put":
                url = self._get_param(step_params, "url", "")
                device_id = self._get_param(step_params, "device_id", "default")
                headers = self._get_param(step_params, "headers", {})
                json_data = self._get_param(step_params, "json_data", {})
                data = self._get_param(step_params, "data", {})

                # Ensure URL is fully resolved (handle nested variables)
                if hasattr(self.config, "substitute_variables"):
                    max_passes = 5
                    for _ in range(max_passes):
                        new_url = self.config.substitute_variables(url, variables)
                        if new_url == url:
                            break
                        url = new_url
                else:
                    url = self._replace_variables(url, variables)

                # Check for verbose logging
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", True)
                    or step_params.get("show_full_response", False)
                    or step_params.get("full_log", False)
                )
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )

                print(f"      API PUT: {url} (device: {device_id})")
                if verbose_logging:
                    import json

                    if headers:
                        print(f"         📋 Request Headers:")
                        headers_str = json.dumps(headers, indent=2)
                        for line in headers_str.split("\n"):
                            print(f"           {line}")
                    if json_data:
                        print(f"         📤 Request Body (JSON):")
                        body_str = json.dumps(json_data, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    elif data:
                        print(f"         📤 Request Body:")
                        if isinstance(data, str):
                            for line in data.split("\n"):
                                print(f"           {line}")
                        else:
                            print(f"           {data}")

                response = service.put(
                    url,
                    device_id,
                    headers=headers,
                    json=json_data or None,
                    data=data or None,
                )

                # Handle 401 errors by attempting to re-authenticate
                if response.status_code == 401:
                    print(f"      🔄 Received 401, attempting to re-authenticate...")
                    # Check if we have login credentials in variables
                    api_base_url = variables.get("api_base_url", "")
                    # Resolve api_base_url if it contains variables
                    if api_base_url:
                        api_base_url = self._resolve_url_with_variables(
                            api_base_url, variables
                        )
                    username = variables.get("username")
                    password = variables.get("password")

                    if api_base_url and username and password:
                        import json

                        login_url = f"{api_base_url}/auth/login"
                        # Ensure login_url is fully resolved
                        login_url = self._resolve_url_with_variables(
                            login_url, variables
                        )
                        login_body = json.dumps(
                            {"username": username, "password": password}
                        )
                        print(f"      🔑 Re-authenticating with stored credentials...")
                        # Make login request
                        login_response = service.post(
                            login_url, device_id, json=json.loads(login_body)
                        )
                        if login_response.status_code == 200:
                            login_json = login_response.json()
                            # Extract token
                            token_fields = [
                                "token",
                                "access_token",
                                "accessToken",
                                "auth_token",
                                "authToken",
                            ]
                            for field in token_fields:
                                if field in login_json:
                                    token = login_json[field]
                                    variables["auth_token"] = token
                                    if device_id and device_id != "default":
                                        variables[f"auth_token_{device_id}"] = token
                                    headers["Authorization"] = f"Bearer {token}"
                                    print(f"      ✅ Re-authenticated successfully")
                                    # Retry the original request
                                    response = service.put(
                                        url,
                                        device_id,
                                        headers=headers,
                                        json=json_data or None,
                                        data=data or None,
                                    )
                                    break

                # Store response for validation
                variables["last_response"] = response
                variables["last_status"] = response.status_code

                # Parse JSON response
                content_type = response.headers.get("content-type", "")
                is_json = content_type.startswith("application/json")
                response_json = None
                try:
                    response_json = response.json()
                    variables["last_json"] = response_json
                    is_json = True
                except Exception:
                    variables["last_json"] = None

                # Print full response if verbose logging enabled
                if verbose_logging:
                    import json

                    print(f"         📡 Status: {response.status_code}")
                    print(f"         📋 Response Headers:")
                    headers_str = json.dumps(dict(response.headers), indent=2)
                    for line in headers_str.split("\n"):
                        print(f"           {line}")
                    if is_json and response_json:
                        print(f"         📦 Response Body (JSON):")
                        body_str = json.dumps(response_json, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    else:
                        # Show FULL response text, not truncated
                        print(f"         📦 Response Body:")
                        # Print full response, handling long responses
                        if len(response.text) > 0:
                            for line in response.text.split("\n"):
                                print(f"           {line}")
                        else:
                            print(f"           (empty)")
                else:
                    print(f"         📡 Status: {response.status_code}")

                # Check if we should fail on error status codes
                fail_on_error = step_params.get("fail_on_error", True)
                if isinstance(fail_on_error, str):
                    fail_on_error = fail_on_error.lower() in ("true", "1", "yes", "on")

                if fail_on_error and response.status_code >= 400:
                    import json

                    error_msg = f"API request failed with status {response.status_code}"
                    if is_json and response_json:
                        error_msg += f": {json.dumps(response_json, indent=2)}"
                    elif response.text:
                        error_msg += f": {response.text[:200]}"
                    print(f"      ❌ {error_msg}")
                    raise ValueError(error_msg)

                return True

            elif hasattr(service, "delete") and action.strip() == "api delete":
                url = self._get_param(step_params, "url", "")
                device_id = self._get_param(step_params, "device_id", "default")
                headers = self._get_param(step_params, "headers", {})

                # Resolve URL with variable substitution (handles URL-encoded variables)
                url = self._resolve_url_with_variables(url, variables)

                # Handle headers if it's a string
                if isinstance(headers, str):
                    try:
                        import json

                        headers = json.loads(headers) if headers.strip() else {}
                    except:
                        headers = {}
                elif not headers:
                    headers = {}

                # Automatically add Authorization header if token is available
                token = None
                if device_id and device_id != "default":
                    token = variables.get(f"auth_token_{device_id}")
                if not token:
                    token = variables.get("auth_token")
                if not token:
                    token = variables.get("token")
                if not token:
                    # Check for token in stored response objects
                    for key, value in variables.items():
                        if isinstance(value, dict) and (
                            "token" in value or "access_token" in value
                        ):
                            token = value.get("token") or value.get("access_token")
                            break

                # Add Authorization header if token found
                if token and "Authorization" not in headers:
                    headers["Authorization"] = f"Bearer {token}"
                    print(f"      🔑 Using stored token for authentication")

                # Check for verbose logging
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", True)
                    or step_params.get("show_full_response", False)
                    or step_params.get("full_log", False)
                )
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )

                print(f"      API DELETE: {url} (device: {device_id})")
                if verbose_logging:
                    import json

                    if headers:
                        print(f"         📋 Request Headers:")
                        headers_str = json.dumps(headers, indent=2)
                        for line in headers_str.split("\n"):
                            print(f"           {line}")

                response = service.delete(url, device_id, headers=headers)

                # Handle 401 errors by attempting to re-authenticate
                if response.status_code == 401:
                    print(f"      🔄 Received 401, attempting to re-authenticate...")
                    # Check if we have login credentials in variables
                    api_base_url = variables.get("api_base_url", "")
                    # Resolve api_base_url if it contains variables
                    if api_base_url:
                        api_base_url = self._resolve_url_with_variables(
                            api_base_url, variables
                        )
                    username = variables.get("username")
                    password = variables.get("password")

                    if api_base_url and username and password:
                        import json

                        login_url = f"{api_base_url}/auth/login"
                        # Ensure login_url is fully resolved
                        login_url = self._resolve_url_with_variables(
                            login_url, variables
                        )
                        login_body = json.dumps(
                            {"username": username, "password": password}
                        )
                        print(f"      🔑 Re-authenticating with stored credentials...")
                        # Make login request
                        login_response = service.post(
                            login_url, device_id, json=json.loads(login_body)
                        )
                        if login_response.status_code == 200:
                            login_json = login_response.json()
                            # Extract token
                            token_fields = [
                                "token",
                                "access_token",
                                "accessToken",
                                "auth_token",
                                "authToken",
                            ]
                            for field in token_fields:
                                if field in login_json:
                                    token = login_json[field]
                                    variables["auth_token"] = token
                                    if device_id and device_id != "default":
                                        variables[f"auth_token_{device_id}"] = token
                                    headers["Authorization"] = f"Bearer {token}"
                                    print(f"      ✅ Re-authenticated successfully")
                                    # Retry the original request
                                    response = service.delete(
                                        url, device_id, headers=headers
                                    )
                                    break

                # Store response for validation
                variables["last_response"] = response
                variables["last_status"] = response.status_code

                # Parse JSON response
                content_type = response.headers.get("content-type", "")
                is_json = content_type.startswith("application/json")
                response_json = None
                try:
                    response_json = response.json()
                    variables["last_json"] = response_json
                    is_json = True
                except Exception:
                    variables["last_json"] = None

                # Print full response if verbose logging enabled
                if verbose_logging:
                    import json

                    print(f"         📡 Status: {response.status_code}")
                    print(f"         📋 Response Headers:")
                    headers_str = json.dumps(dict(response.headers), indent=2)
                    for line in headers_str.split("\n"):
                        print(f"           {line}")
                    if is_json and response_json:
                        print(f"         📦 Response Body (JSON):")
                        body_str = json.dumps(response_json, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    else:
                        # Show FULL response text, not truncated
                        print(f"         📦 Response Body:")
                        # Print full response, handling long responses
                        if len(response.text) > 0:
                            for line in response.text.split("\n"):
                                print(f"           {line}")
                        else:
                            print(f"           (empty)")
                else:
                    print(f"         📡 Status: {response.status_code}")

                # Check if we should fail on error status codes
                fail_on_error = step_params.get("fail_on_error", True)
                if isinstance(fail_on_error, str):
                    fail_on_error = fail_on_error.lower() in ("true", "1", "yes", "on")

                if fail_on_error and response.status_code >= 400:
                    import json

                    error_msg = f"API request failed with status {response.status_code}"
                    if is_json and response_json:
                        error_msg += f": {json.dumps(response_json, indent=2)}"
                    elif response.text:
                        error_msg += f": {response.text[:200]}"
                    print(f"      ❌ {error_msg}")
                    raise ValueError(error_msg)

                return True

            elif hasattr(service, "patch") and action.strip() == "api patch":
                url = self._get_param(step_params, "url", "")
                device_id = self._get_param(step_params, "device_id", "default")
                headers = self._get_param(step_params, "headers", {})
                json_data = self._get_param(step_params, "json_data", {})
                data = self._get_param(step_params, "data", {})

                # Resolve URL with variable substitution (handles URL-encoded variables)
                url = self._resolve_url_with_variables(url, variables)

                # Handle headers if it's a string
                if isinstance(headers, str):
                    try:
                        import json

                        headers = json.loads(headers) if headers.strip() else {}
                    except:
                        headers = {}
                elif not headers:
                    headers = {}

                # Automatically add Authorization header if token is available
                token = None
                if device_id and device_id != "default":
                    token = variables.get(f"auth_token_{device_id}")
                if not token:
                    token = variables.get("auth_token")
                if not token:
                    token = variables.get("token")
                if not token:
                    # Check for token in stored response objects
                    for key, value in variables.items():
                        if isinstance(value, dict) and (
                            "token" in value or "access_token" in value
                        ):
                            token = value.get("token") or value.get("access_token")
                            break

                # Add Authorization header if token found
                if token and "Authorization" not in headers:
                    headers["Authorization"] = f"Bearer {token}"
                    print(f"      🔑 Using stored token for authentication")

                # Check for verbose logging
                verbose_logging = (
                    variables.get("verbose_logging", True)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", True)
                    or step_params.get("show_full_response", False)
                    or step_params.get("full_log", False)
                )
                if isinstance(verbose_logging, str):
                    verbose_logging = verbose_logging.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )

                print(f"      API PATCH: {url} (device: {device_id})")
                if verbose_logging:
                    import json

                    if headers:
                        print(f"         📋 Request Headers:")
                        headers_str = json.dumps(headers, indent=2)
                        for line in headers_str.split("\n"):
                            print(f"           {line}")
                    if json_data:
                        print(f"         📤 Request Body (JSON):")
                        body_str = json.dumps(json_data, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    elif data:
                        print(f"         📤 Request Body:")
                        if isinstance(data, str):
                            for line in data.split("\n"):
                                print(f"           {line}")
                        else:
                            print(f"           {data}")

                response = service.patch(
                    url,
                    device_id,
                    headers=headers,
                    json=json_data or None,
                    data=data or None,
                )

                # Handle 401 errors by attempting to re-authenticate
                if response.status_code == 401:
                    print(f"      🔄 Received 401, attempting to re-authenticate...")
                    # Check if we have login credentials in variables
                    api_base_url = variables.get("api_base_url", "")
                    # Resolve api_base_url if it contains variables
                    if api_base_url:
                        api_base_url = self._resolve_url_with_variables(
                            api_base_url, variables
                        )
                    username = variables.get("username")
                    password = variables.get("password")

                    if api_base_url and username and password:
                        import json

                        login_url = f"{api_base_url}/auth/login"
                        # Ensure login_url is fully resolved
                        login_url = self._resolve_url_with_variables(
                            login_url, variables
                        )
                        login_body = json.dumps(
                            {"username": username, "password": password}
                        )
                        print(f"      🔑 Re-authenticating with stored credentials...")
                        # Make login request
                        login_response = service.post(
                            login_url, device_id, json=json.loads(login_body)
                        )
                        if login_response.status_code == 200:
                            login_json = login_response.json()
                            # Extract token
                            token_fields = [
                                "token",
                                "access_token",
                                "accessToken",
                                "auth_token",
                                "authToken",
                            ]
                            for field in token_fields:
                                if field in login_json:
                                    token = login_json[field]
                                    variables["auth_token"] = token
                                    if device_id and device_id != "default":
                                        variables[f"auth_token_{device_id}"] = token
                                    headers["Authorization"] = f"Bearer {token}"
                                    print(f"      ✅ Re-authenticated successfully")
                                    # Retry the original request
                                    response = service.patch(
                                        url,
                                        device_id,
                                        headers=headers,
                                        json=json_data or None,
                                        data=data or None,
                                    )
                                    break

                # Store response for validation
                variables["last_response"] = response
                variables["last_status"] = response.status_code

                # Parse JSON response
                content_type = response.headers.get("content-type", "")
                is_json = content_type.startswith("application/json")
                response_json = None
                try:
                    response_json = response.json()
                    variables["last_json"] = response_json
                    is_json = True
                except Exception:
                    variables["last_json"] = None

                # Print full response if verbose logging enabled
                if verbose_logging:
                    import json

                    print(f"         Status: {response.status_code}")
                    print(
                        f"         Response Headers: {json.dumps(dict(response.headers), indent=2)}"
                    )
                    if is_json and response_json:
                        print(f"         Response Body:")
                        body_str = json.dumps(response_json, indent=2)
                        for line in body_str.split("\n"):
                            print(f"           {line}")
                    else:
                        print(
                            f"         Response Body: {response.text[:500]}{'...' if len(response.text) > 500 else ''}"
                        )
                else:
                    print(f"         Status: {response.status_code}")

                return True

            elif "validate status" in action:
                expected_status = step_params.get("status", 200)
                actual_status = variables.get("last_status", 0)

                if actual_status == expected_status:
                    return True
                else:
                    return False

            elif "validate json" in action:
                field = step_params.get("field", "")
                expected_value = step_params.get("value", "")
                last_json = variables.get("last_json", {})

                if not last_json:
                    print(f"      ❌ No JSON response to validate")
                    return False

                # Support nested field access with dot notation
                actual_value = last_json
                for field_part in field.split("."):
                    if isinstance(actual_value, dict) and field_part in actual_value:
                        actual_value = actual_value[field_part]
                    else:
                        actual_value = None
                        break

                print(
                    f"      Validating JSON field '{field}': expected '{expected_value}', got '{actual_value}'"
                )
                if str(actual_value) == str(expected_value):
                    print(f"      ✅ JSON validation passed")
                    return True
                else:
                    print(f"      ❌ JSON validation failed")
                    return False

            else:
                print(f"      ❌ Unknown action: {action}")
                print(
                    f"      Available actions: click, fill, select option, wait, screenshot, etc."
                )
                return False

        except Exception as e:
            print(f"      ❌ Error in step execution: {e}")
            print(f"      Action: {action}")
            print(f"      Parameters: {step_params.get('parameters', {})}")
            import traceback

            print(f"      Traceback: {traceback.format_exc()}")
            return False
    
    def _extract_system_resources(self, device_update: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract system resources from device update with OS detection.
        
        First detects the operating system, then uses OS-specific extraction methods:
        - Linux: /proc/stat, /proc/meminfo style data
        - Windows: WMI-style data, Performance Counters
        - Embedded: Custom structures (Araknis, SnapAV, etc.)
        - OvrC: Nested params structures
        
        Args:
            device_update: Device update dictionary from OvrC
            
        Returns:
            Dictionary with extracted system resources
        """
        if not device_update:
            return {"resources_found": False}
        
        # Extract params from the update (contains the actual device data)
        update_params = device_update.get("params", {})
        if not update_params:
            # Try direct access if params doesn't exist
            update_params = device_update
        
        # Debug: Log the structure if verbose
        import os as os_module
        if os_module.getenv("DEBUG_RESOURCES", "false").lower() == "true":
            import json
            print(f"      🔍 Debug: Device update structure (first level keys): {list(update_params.keys())[:10]}")
            print(f"      🔍 Debug: Full update (truncated): {json.dumps(update_params, indent=2)[:500]}")
        
        # Step 1: Detect Operating System
        detected_os = self._detect_os_from_update(update_params)
        
        # Debug OS detection
        if os_module.getenv("DEBUG_RESOURCES", "false").lower() == "true":
            print(f"      🔍 Debug: Detected OS: {detected_os}")
        
        resources = {}
        found_resources = False
        
        # Step 2: Use OS-specific extraction methods, but ALWAYS fall back to generic
        # Try OS-specific first, then generic as backup
        resources = {}
        found_resources = False
        
        if detected_os == "linux":
            resources, found_resources = self._extract_linux_resources(update_params)
        elif detected_os == "windows":
            resources, found_resources = self._extract_windows_resources(update_params)
        elif detected_os == "embedded" or detected_os == "ovrc":
            resources, found_resources = self._extract_embedded_resources(update_params)
        
        # ALWAYS also try generic extraction as a fallback/backup
        # This ensures we catch resources even if OS-specific extraction misses them
        generic_resources, generic_found = self._extract_generic_resources(update_params)
        
        # Merge generic results with OS-specific results (generic takes precedence if OS-specific found nothing)
        if not found_resources or not resources:
            # If OS-specific didn't find anything, use generic
            resources = generic_resources
            found_resources = generic_found
        else:
            # Merge both - generic might have found additional data
            for key in ["cpu", "memory", "disk", "network"]:
                if key in generic_resources and key not in resources:
                    resources[key] = generic_resources[key]
                elif key in generic_resources and key in resources:
                    # Merge dictionaries
                    if isinstance(resources[key], dict) and isinstance(generic_resources[key], dict):
                        resources[key].update(generic_resources[key])
        
        # Debug: Log what we found before calculation
        import os as os_module
        if os_module.getenv("DEBUG_RESOURCES", "false").lower() == "true":
            print(f"      🔍 Debug: Extracted resources before calculation: {resources}")
        
        # Calculate percentages and finalize resources
        # ALWAYS call calculate_resource_percentages to ensure percentages are calculated
        # Even if resources is empty, it will handle it gracefully
        # This ensures we always have usage_percent values if any resource data exists
        resources = self._calculate_resource_percentages(resources) if resources else {}
        
        # Also store the raw update for reference
        result = {
            "resources": resources,
            "resources_found": found_resources or bool(resources),
            "detected_os": detected_os,
            "raw_update": device_update,
            "device_online": True,
            "timestamp": device_update.get("timestamp") or device_update.get("_received_at")
        }
        
        # Debug: Log final result
        if os_module.getenv("DEBUG_RESOURCES", "false").lower() == "true":
            print(f"      🔍 Debug: Final result resources: {result.get('resources')}")
            if result.get("resources"):
                cpu = result["resources"].get("cpu", {})
                mem = result["resources"].get("memory", {})
                print(f"      🔍 Debug: CPU data: {cpu}")
                print(f"      🔍 Debug: Memory data: {mem}")
        
        return result
    
    def _detect_os_from_update(self, update_params: Dict[str, Any]) -> str:
        """
        Detect operating system from device update data.
        
        Returns:
            'linux', 'windows', 'embedded', 'ovrc', or 'unknown'
        """
        def search_for_os_indicators(data, path="", depth=0, max_depth=5):
            """Recursively search for OS indicators"""
            if depth > max_depth:
                return None
            
            if isinstance(data, dict):
                for key, value in data.items():
                    key_lower = str(key).lower()
                    
                    # Check for explicit OS fields
                    if key_lower in ["os", "operating_system", "operatingsystem", "platform", "system", "os_type", "ostype"]:
                        if isinstance(value, str):
                            value_lower = value.lower()
                            if "linux" in value_lower:
                                return "linux"
                            elif "windows" in value_lower or "win" in value_lower:
                                return "windows"
                            elif "embedded" in value_lower or "firmware" in value_lower:
                                return "embedded"
                    
                    # Check for Linux-specific indicators
                    if any(indicator in key_lower for indicator in ["proc", "/proc", "meminfo", "stat", "loadavg", "uptime"]):
                        return "linux"
                    
                    # Check for Windows-specific indicators
                    if any(indicator in key_lower for indicator in ["wmi", "performance", "counter", "win32", "powershell"]):
                        return "windows"
                    
                    # Check for OvrC/embedded indicators
                    if any(indicator in key_lower for indicator in ["ovrc", "araknis", "snapav", "firmware", "device_type"]):
                        return "embedded"
                    
                    # Recursively search nested structures
                    if isinstance(value, (dict, list)):
                        result = search_for_os_indicators(value, f"{path}.{key}", depth + 1, max_depth)
                        if result:
                            return result
            
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        result = search_for_os_indicators(item, path, depth + 1, max_depth)
                        if result:
                            return result
            
            return None
        
        # Search for OS indicators
        detected = search_for_os_indicators(update_params)
        
        # Default to 'ovrc' if we're dealing with OvrC device updates
        if not detected:
            # Check if this looks like an OvrC update structure
            if "params" in update_params or "method" in update_params:
                detected = "ovrc"
            else:
                detected = "unknown"
        
        return detected
    
    def _extract_linux_resources(self, update_params: Dict[str, Any]) -> tuple:
        """Extract resources from Linux-style data structures"""
        resources = {}
        found = False
        
        def find_linux_resources(data, path="", depth=0, max_depth=10):
            found_res = {}
            if depth > max_depth:
                return found_res
            
            if isinstance(data, dict):
                for key, value in data.items():
                    if value is None:
                        continue
                    key_lower = str(key).lower()
                    current_path = f"{path}.{key}" if path else key
                    
                    # Linux CPU patterns: /proc/stat, /proc/loadavg
                    if any(pattern in key_lower for pattern in ["cpu", "loadavg", "load_avg", "cpuload"]):
                        if isinstance(value, (int, float)):
                            if "cpu" not in found_res:
                                found_res["cpu"] = {}
                            if "load" in key_lower or "loadavg" in key_lower:
                                found_res["cpu"]["load"] = float(value)
                            else:
                                found_res["cpu"]["usage_percent"] = float(value)
                            found_res["cpu"]["source"] = current_path
                        elif isinstance(value, dict):
                            if "cpu" not in found_res:
                                found_res["cpu"] = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)):
                                    found_res["cpu"][k] = float(v)
                            found_res["cpu"]["source"] = current_path
                    
                    # Linux memory patterns: /proc/meminfo
                    if any(pattern in key_lower for pattern in ["meminfo", "mem", "memory"]):
                        if isinstance(value, dict):
                            if "memory" not in found_res:
                                found_res["memory"] = {}
                            # Look for MemTotal, MemFree, MemAvailable
                            for k, v in value.items():
                                k_lower = str(k).lower()
                                if isinstance(v, (int, float)):
                                    if "total" in k_lower or "memtotal" in k_lower:
                                        found_res["memory"]["total"] = int(v)
                                    elif "free" in k_lower or "memfree" in k_lower:
                                        found_res["memory"]["free"] = int(v)
                                    elif "available" in k_lower or "memavailable" in k_lower:
                                        found_res["memory"]["available"] = int(v)
                                    elif "used" in k_lower or "memused" in k_lower:
                                        found_res["memory"]["used"] = int(v)
                            if found_res["memory"]:
                                found_res["memory"]["source"] = current_path
                    
                    # Recursively search
                    if isinstance(value, (dict, list)):
                        nested = find_linux_resources(value, current_path, depth + 1, max_depth)
                        found_res.update(nested)
            
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        nested = find_linux_resources(item, path, depth + 1, max_depth)
                        found_res.update(nested)
            
            return found_res
        
        extracted = find_linux_resources(update_params)
        if extracted:
            resources.update(extracted)
            found = True
        
        return resources, found
    
    def _extract_windows_resources(self, update_params: Dict[str, Any]) -> tuple:
        """Extract resources from Windows-style data structures (WMI, Performance Counters)"""
        resources = {}
        found = False
        
        def find_windows_resources(data, path="", depth=0, max_depth=10):
            found_res = {}
            if depth > max_depth:
                return found_res
            
            if isinstance(data, dict):
                for key, value in data.items():
                    if value is None:
                        continue
                    key_lower = str(key).lower()
                    current_path = f"{path}.{key}" if path else key
                    
                    # Windows CPU patterns: Processor, CPUUsage, PercentProcessorTime
                    if any(pattern in key_lower for pattern in ["processor", "cpu", "cpuusage", "percentprocessortime", "processortime"]):
                        if isinstance(value, (int, float)):
                            if "cpu" not in found_res:
                                found_res["cpu"] = {}
                            if "percent" in key_lower or "usage" in key_lower or "time" in key_lower:
                                found_res["cpu"]["usage_percent"] = float(value)
                            else:
                                found_res["cpu"]["usage_percent"] = float(value)
                            found_res["cpu"]["source"] = current_path
                        elif isinstance(value, dict):
                            if "cpu" not in found_res:
                                found_res["cpu"] = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)):
                                    k_lower = str(k).lower()
                                    if "percent" in k_lower or "usage" in k_lower:
                                        found_res["cpu"]["usage_percent"] = float(v)
                                    else:
                                        found_res["cpu"][k] = float(v)
                            found_res["cpu"]["source"] = current_path
                    
                    # Windows memory patterns: Memory, TotalPhysicalMemory, AvailablePhysicalMemory
                    if any(pattern in key_lower for pattern in ["memory", "physicalmemory", "totalphysical", "availablephysical", "freephysical"]):
                        if isinstance(value, (int, float)):
                            if "memory" not in found_res:
                                found_res["memory"] = {}
                            if "total" in key_lower:
                                found_res["memory"]["total"] = int(value)
                            elif "free" in key_lower or "available" in key_lower:
                                found_res["memory"]["free"] = int(value)
                            elif "used" in key_lower:
                                found_res["memory"]["used"] = int(value)
                            found_res["memory"]["source"] = current_path
                        elif isinstance(value, dict):
                            if "memory" not in found_res:
                                found_res["memory"] = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)):
                                    k_lower = str(k).lower()
                                    if "total" in k_lower:
                                        found_res["memory"]["total"] = int(v)
                                    elif "free" in k_lower or "available" in k_lower:
                                        found_res["memory"]["free"] = int(v)
                                    elif "used" in k_lower:
                                        found_res["memory"]["used"] = int(v)
                            if found_res["memory"]:
                                found_res["memory"]["source"] = current_path
                    
                    # Recursively search
                    if isinstance(value, (dict, list)):
                        nested = find_windows_resources(value, current_path, depth + 1, max_depth)
                        found_res.update(nested)
            
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        nested = find_windows_resources(item, path, depth + 1, max_depth)
                        found_res.update(nested)
            
            return found_res
        
        extracted = find_windows_resources(update_params)
        if extracted:
            resources.update(extracted)
            found = True
        
        return resources, found
    
    def _extract_embedded_resources(self, update_params: Dict[str, Any]) -> tuple:
        """Extract resources from embedded/OvrC-style data structures"""
        resources = {}
        found = False
        
        def find_embedded_resources(data, path="", depth=0, max_depth=10):
            found_res = {}
            if depth > max_depth:
                return found_res
            
            if isinstance(data, dict):
                for key, value in data.items():
                    if value is None:
                        continue
                    key_lower = str(key).lower()
                    current_path = f"{path}.{key}" if path else key
                    
                    # Embedded CPU patterns - very flexible
                    cpu_patterns = ["cpu", "cpuload", "cpu_load", "cpuusage", "cpu_usage", 
                                   "cpupercent", "cpu_percent", "cpuutil", "cpu_util",
                                   "load", "loadavg", "load_avg", "processor", "usage"]
                    if any(pattern in key_lower for pattern in cpu_patterns):
                        if isinstance(value, (int, float)):
                            if "cpu" not in found_res:
                                found_res["cpu"] = {}
                            # Store the value - we'll determine what it represents
                            if "percent" in key_lower or "usage" in key_lower or "util" in key_lower:
                                found_res["cpu"]["usage_percent"] = float(value)
                            elif "load" in key_lower:
                                found_res["cpu"]["load"] = float(value)
                            else:
                                # Default: assume it's usage_percent if it's a reasonable value
                                val = float(value)
                                if 0 <= val <= 100:
                                    found_res["cpu"]["usage_percent"] = val
                                elif 0 <= val <= 1:
                                    found_res["cpu"]["usage_percent"] = val  # Will be converted to percentage later
                                else:
                                    found_res["cpu"]["usage_percent"] = val
                            found_res["cpu"]["source"] = current_path
                        elif isinstance(value, dict):
                            if "cpu" not in found_res:
                                found_res["cpu"] = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)):
                                    k_lower = str(k).lower()
                                    # Store with appropriate key
                                    if "percent" in k_lower or "usage" in k_lower or "util" in k_lower:
                                        found_res["cpu"]["usage_percent"] = float(v)
                                    elif "load" in k_lower:
                                        found_res["cpu"]["load"] = float(v)
                                    else:
                                        # Store as-is, will be processed later
                                        found_res["cpu"][k] = float(v)
                            found_res["cpu"]["source"] = current_path
                    
                    # Embedded memory patterns - very flexible
                    mem_patterns = ["memory", "mem", "ram", "physicalmemory", "totalmemory",
                                   "usedmemory", "freememory", "availablememory",
                                   "memtotal", "memfree", "memused", "memavailable"]
                    if any(pattern in key_lower for pattern in mem_patterns):
                        if isinstance(value, (int, float)):
                            if "memory" not in found_res:
                                found_res["memory"] = {}
                            # Determine what type of memory value this is
                            if "total" in key_lower or "memtotal" in key_lower:
                                found_res["memory"]["total"] = int(value)
                            elif "free" in key_lower or "available" in key_lower or "memfree" in key_lower or "memavailable" in key_lower:
                                found_res["memory"]["free"] = int(value)
                            elif "used" in key_lower or "memused" in key_lower:
                                found_res["memory"]["used"] = int(value)
                            else:
                                # If we can't determine, store as total (common case)
                                found_res["memory"]["total"] = int(value)
                            found_res["memory"]["source"] = current_path
                        elif isinstance(value, dict):
                            if "memory" not in found_res:
                                found_res["memory"] = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)):
                                    k_lower = str(k).lower()
                                    # Store with appropriate key
                                    if "total" in k_lower or "memtotal" in k_lower:
                                        found_res["memory"]["total"] = int(v)
                                    elif "free" in k_lower or "available" in k_lower or "memfree" in k_lower or "memavailable" in k_lower:
                                        found_res["memory"]["free"] = int(v)
                                    elif "used" in k_lower or "memused" in k_lower:
                                        found_res["memory"]["used"] = int(v)
                                    else:
                                        # Store as-is for later processing
                                        found_res["memory"][k] = int(v) if isinstance(v, (int, float)) and v > 1000 else float(v)
                            if found_res["memory"]:
                                found_res["memory"]["source"] = current_path
                    
                    # Recursively search
                    if isinstance(value, (dict, list)):
                        nested = find_embedded_resources(value, current_path, depth + 1, max_depth)
                        found_res.update(nested)
            
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        nested = find_embedded_resources(item, path, depth + 1, max_depth)
                        found_res.update(nested)
            
            return found_res
        
        extracted = find_embedded_resources(update_params)
        if extracted:
            resources.update(extracted)
            found = True
        
        return resources, found
    
    def _extract_generic_resources(self, update_params: Dict[str, Any]) -> tuple:
        """Generic fallback extraction method"""
        # Use the original generic extraction logic as fallback
        resources = {}
        found_resources = False
        
        def find_resource_data(data, path="", depth=0, max_depth=15):
            """Recursively search for CPU, memory, disk, network data"""
            if depth > max_depth:
                return {}
            
            found = {}
            if isinstance(data, dict):
                for key, value in data.items():
                    if value is None:
                        continue
                    
                    current_path = f"{path}.{key}" if path else key
                    key_lower = str(key).lower()
                    
                    # CPU detection - EXTENSIVE patterns for ALL operating systems
                    cpu_patterns = [
                        "cpu", "processor", "load", "usage", "utilization", "util",
                        "cpuusage", "cpuload", "cpu_usage", "cpu_load", "cpuutil", "cpu_util",
                        "processorusage", "processorload", "cpuloadavg", "cpu_load_avg",
                        "cpupercent", "cpu_percent", "cpuutilization", "cpu_utilization",
                        "percentcpu", "percent_cpu", "cpupct", "cpu_pct",
                        "loadavg", "load_avg", "loadaverage", "load_average",
                        "systemload", "system_load", "cpuloadavg1m", "cpuloadavg5m",
                        "processorusage", "processor_usage", "processorutilization"
                    ]
                    if any(pattern in key_lower for pattern in cpu_patterns):
                        if isinstance(value, (int, float)) and value >= 0:
                            # Update existing CPU or create new
                            if "cpu" not in found:
                                found["cpu"] = {}
                            # Store the value - we'll calculate percentage later if needed
                            if "usage" in key_lower or "utilization" in key_lower or "util" in key_lower or "percent" in key_lower or "pct" in key_lower:
                                found["cpu"]["usage_percent"] = float(value)
                            elif "load" in key_lower:
                                found["cpu"]["load"] = float(value)
                            else:
                                # Default to usage_percent - try to interpret the value
                                val = float(value)
                                if 0 <= val <= 1:
                                    found["cpu"]["usage_percent"] = val  # Will be converted to percentage
                                elif 0 <= val <= 100:
                                    found["cpu"]["usage_percent"] = val
                                else:
                                    found["cpu"]["usage_percent"] = val  # Store as-is, will be normalized
                            found["cpu"]["source"] = current_path
                            found_resources = True
                        elif isinstance(value, dict):
                            # Nested CPU data - merge with existing
                            if "cpu" not in found:
                                found["cpu"] = {}
                            cpu_data = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)) and v >= 0:
                                    k_lower = str(k).lower()
                                    if "usage" in k_lower or "utilization" in k_lower or "util" in k_lower or "percent" in k_lower or "pct" in k_lower:
                                        cpu_data["usage_percent"] = float(v)
                                    elif "load" in k_lower:
                                        cpu_data["load"] = float(v)
                                    else:
                                        cpu_data[k] = float(v)
                            if cpu_data:
                                found["cpu"].update(cpu_data)
                                found["cpu"]["source"] = current_path
                                found_resources = True
                        elif isinstance(value, list):
                            # Sometimes CPU data is in a list (e.g., load averages)
                            for item in value:
                                if isinstance(item, (int, float)) and item >= 0:
                                    if "cpu" not in found:
                                        found["cpu"] = {}
                                    if "load" in key_lower:
                                        found["cpu"]["load"] = float(item)
                                    else:
                                        found["cpu"]["usage_percent"] = float(item)
                                    found["cpu"]["source"] = current_path
                                    found_resources = True
                                    break
                    
                    # Memory detection - EXTENSIVE patterns for ALL operating systems
                    mem_patterns = [
                        "memory", "mem", "ram", "physicalmemory", "physical_memory", "physical",
                        "totalmemory", "total_memory", "usedmemory", "used_memory", "usagememory",
                        "freememory", "free_memory", "availablememory", "available_memory",
                        "memtotal", "memfree", "memavailable", "memused", "memusage",
                        "totalram", "usedram", "freeram", "availableram",
                        "systemmemory", "system_memory", "totalphysical", "availablephysical",
                        "freephysical", "usedphysical", "physicalmem", "physical_mem"
                    ]
                    if any(pattern in key_lower for pattern in mem_patterns):
                        if isinstance(value, (int, float)) and value > 0:
                            # Single value - merge with existing memory data
                            if "memory" not in found:
                                found["memory"] = {}
                            if "free" in key_lower or "available" in key_lower:
                                found["memory"]["free"] = int(value)
                            elif "used" in key_lower or "usage" in key_lower:
                                found["memory"]["used"] = int(value)
                            elif "total" in key_lower:
                                found["memory"]["total"] = int(value)
                            else:
                                # If we can't determine, assume it's total if it's a large number (> 1MB)
                                if value > 1048576:  # > 1MB
                                    found["memory"]["total"] = int(value)
                            found["memory"]["source"] = current_path
                            found_resources = True
                        elif isinstance(value, dict):
                            # Nested memory data - merge with existing
                            if "memory" not in found:
                                found["memory"] = {}
                            mem_data = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)) and v >= 0:
                                    k_lower = str(k).lower()
                                    if "total" in k_lower or "memtotal" in k_lower:
                                        mem_data["total"] = int(v)
                                    elif "free" in k_lower or "available" in k_lower or "memfree" in k_lower or "memavailable" in k_lower:
                                        mem_data["free"] = int(v)
                                    elif "used" in k_lower or "usage" in k_lower or "memused" in k_lower or "memusage" in k_lower:
                                        mem_data["used"] = int(v)
                                    elif "percent" in k_lower or "pct" in k_lower:
                                        mem_data["usage_percent"] = float(v)
                                    else:
                                        # Store as-is - might be useful later
                                        mem_data[k] = int(v) if v > 1000 else float(v)
                            if mem_data:
                                found["memory"].update(mem_data)
                                found["memory"]["source"] = current_path
                                found_resources = True
                    
                    # Disk detection
                    disk_patterns = ["disk", "storage", "filesystem", "file_system", "volume",
                                    "diskusage", "disk_usage", "storageusage", "storage_usage"]
                    if any(pattern in key_lower for pattern in disk_patterns):
                        if isinstance(value, dict):
                            disk_data = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)):
                                    disk_data[k] = int(v) if "size" in k.lower() or "free" in k.lower() or "used" in k.lower() else float(v)
                            if disk_data:
                                found["disk"] = {**disk_data, "source": current_path}
                                found_resources = True
                    
                    # Network detection
                    network_patterns = ["network", "net", "interface", "ethernet", "wifi", "wireless",
                                       "networkusage", "network_usage", "bandwidth", "throughput"]
                    if any(pattern in key_lower for pattern in network_patterns):
                        if isinstance(value, dict):
                            net_data = {}
                            for k, v in value.items():
                                if isinstance(v, (int, float)):
                                    net_data[k] = int(v)
                            if net_data:
                                found["network"] = {**net_data, "source": current_path}
                                found_resources = True
                    
                    # Recursively search nested structures
                    if isinstance(value, (dict, list)):
                        nested = find_resource_data(value, current_path, depth + 1, max_depth)
                        found.update(nested)
            
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, (dict, list)):
                        nested = find_resource_data(item, f"{path}[{i}]", depth + 1, max_depth)
                        found.update(nested)
            
            return found
        
        # Search for resources
        extracted = find_resource_data(update_params)
        
        # Organize found resources and calculate percentages
        if extracted:
            for key, value in extracted.items():
                if key in ["cpu", "memory", "disk", "network"]:
                    resources[key] = value
        
        # Calculate percentages from raw values if needed
        # This is a fallback - _calculate_resource_percentages will also do this, but we do it here too for safety
        # CPU: If we have usage but it's 0-1 range, convert to 0-100
        if "cpu" in resources:
            cpu_data = resources["cpu"]
            if isinstance(cpu_data, dict):
                # Check if we have usage_percent
                if "usage_percent" in cpu_data:
                    usage = cpu_data["usage_percent"]
                    # If value is between 0-1, assume it's a fraction and convert to percentage
                    if 0 <= usage <= 1:
                        cpu_data["usage_percent"] = usage * 100
                    # If value is already > 1, assume it's already a percentage
                    cpu_data["usage_percent"] = float(cpu_data["usage_percent"])
                # If we have load but no usage_percent, try to convert
                elif "load" in cpu_data:
                    load = cpu_data["load"]
                    if isinstance(load, (int, float)):
                        if 0 <= load <= 1:
                            cpu_data["usage_percent"] = load * 100
                        else:
                            cpu_data["usage_percent"] = float(load)
                # If we have any numeric value, try to use it
                else:
                    for k, v in cpu_data.items():
                        if k != "source" and isinstance(v, (int, float)) and v >= 0:
                            if 0 <= v <= 1:
                                cpu_data["usage_percent"] = v * 100
                            elif v > 1 and v <= 100:
                                cpu_data["usage_percent"] = float(v)
                            break
        
        # Memory: Calculate percentage from used/total if we have both
        if "memory" in resources:
            mem_data = resources["memory"]
            if isinstance(mem_data, dict):
                # Try multiple patterns for total, used, free
                total = (mem_data.get("total") or mem_data.get("total_memory") or 
                        mem_data.get("memtotal") or mem_data.get("total_ram") or
                        mem_data.get("physicalmemory") or mem_data.get("physical_memory"))
                used = (mem_data.get("used") or mem_data.get("used_memory") or 
                       mem_data.get("memused") or mem_data.get("used_ram") or
                       mem_data.get("usedphysical") or mem_data.get("used_physical"))
                free = (mem_data.get("free") or mem_data.get("free_memory") or 
                       mem_data.get("memfree") or mem_data.get("free_ram") or
                       mem_data.get("available") or mem_data.get("available_memory") or 
                       mem_data.get("memavailable") or mem_data.get("available_ram") or
                       mem_data.get("freephysical") or mem_data.get("free_physical") or
                       mem_data.get("availablephysical") or mem_data.get("available_physical"))
                
                # Calculate used if we have total and free
                if total and free and not used:
                    used = total - free
                    mem_data["used"] = used
                
                # Calculate percentage if we have total and used
                if total and used and total > 0:
                    usage_percent = (used / total) * 100
                    mem_data["usage_percent"] = round(usage_percent, 2)
                # If we have usage_percent but it's 0-1 range, convert
                elif "usage_percent" in mem_data:
                    usage = mem_data["usage_percent"]
                    if 0 <= usage <= 1:
                        mem_data["usage_percent"] = usage * 100
                    mem_data["usage_percent"] = float(mem_data["usage_percent"])
        
        # Disk: Calculate percentage from used/total if we have both
        if "disk" in resources:
            disk_data = resources["disk"]
            if isinstance(disk_data, dict):
                total = disk_data.get("total") or disk_data.get("total_size") or disk_data.get("size")
                used = disk_data.get("used") or disk_data.get("used_size")
                free = disk_data.get("free") or disk_data.get("free_size") or disk_data.get("available")
                
                # Calculate used if we have total and free
                if total and free and not used:
                    used = total - free
                    disk_data["used"] = used
                
                # Calculate percentage if we have total and used
                if total and used and total > 0:
                    usage_percent = (used / total) * 100
                    disk_data["usage_percent"] = round(usage_percent, 2)
                # If we have usage_percent but it's 0-1 range, convert
                elif "usage_percent" in disk_data:
                    usage = disk_data["usage_percent"]
                    if 0 <= usage <= 1:
                        disk_data["usage_percent"] = usage * 100
        
        return resources, found_resources
    
    def _calculate_resource_percentages(self, resources: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate percentages for CPU, memory, and disk resources"""
        import os as os_module
        debug = os_module.getenv("DEBUG_RESOURCES", "false").lower() == "true"
        
        if not resources:
            return {}
        
        if debug:
            print(f"      🔍 Debug: Calculating percentages for resources: {resources}")
        
        # CPU: If we have usage but it's 0-1 range, convert to 0-100
        if "cpu" in resources:
            cpu_data = resources["cpu"]
            if isinstance(cpu_data, dict):
                if debug:
                    print(f"      🔍 Debug: CPU data before calculation: {cpu_data}")
                
                # Check if we have usage_percent
                if "usage_percent" in cpu_data:
                    usage = cpu_data["usage_percent"]
                    if debug:
                        print(f"      🔍 Debug: Found usage_percent: {usage}")
                    # If value is between 0-1, assume it's a fraction and convert to percentage
                    if 0 <= usage <= 1:
                        cpu_data["usage_percent"] = usage * 100
                        if debug:
                            print(f"      🔍 Debug: Converted 0-1 range to percentage: {cpu_data['usage_percent']}")
                    # Ensure it's a float
                    cpu_data["usage_percent"] = float(cpu_data["usage_percent"])
                # If we have load but no usage_percent, try to convert
                elif "load" in cpu_data:
                    load = cpu_data["load"]
                    if isinstance(load, (int, float)):
                        if debug:
                            print(f"      🔍 Debug: Found load value: {load}")
                        if 0 <= load <= 1:
                            cpu_data["usage_percent"] = load * 100
                        else:
                            cpu_data["usage_percent"] = float(load)
                        if debug:
                            print(f"      🔍 Debug: Converted load to usage_percent: {cpu_data['usage_percent']}")
                # If we have any numeric value in CPU data, try to use it
                else:
                    # Look for any numeric value that could be CPU usage
                    for key, value in cpu_data.items():
                        if key not in ["source"] and isinstance(value, (int, float)) and value >= 0:
                            if debug:
                                print(f"      🔍 Debug: Found numeric CPU value {key}: {value}")
                            if 0 <= value <= 1:
                                cpu_data["usage_percent"] = value * 100
                            elif value > 1 and value <= 100:
                                cpu_data["usage_percent"] = float(value)
                            elif value > 100 and value <= 1000:
                                # Might be in 0-1000 range (e.g., 0-1000 = 0-100%), normalize
                                cpu_data["usage_percent"] = float(value) / 10.0
                            elif value > 1000:
                                # Very large value, might be in different units, try to normalize
                                cpu_data["usage_percent"] = min(100.0, float(value) / 100.0)
                            else:
                                cpu_data["usage_percent"] = float(value)
                            if debug:
                                print(f"      🔍 Debug: Set usage_percent to: {cpu_data['usage_percent']}")
                            break
                    
                    # If still no usage_percent, set a default of 0 to ensure the key exists
                    if "usage_percent" not in cpu_data:
                        cpu_data["usage_percent"] = 0.0
                        if debug:
                            print(f"      🔍 Debug: No CPU usage found, defaulting to 0%")
                
                # Log CPU percentage for visibility
                if "usage_percent" in cpu_data and cpu_data["usage_percent"] is not None:
                    print(f"      💻 CPU Usage: {cpu_data['usage_percent']:.2f}%")
                elif debug:
                    print(f"      🔍 Debug: No usage_percent calculated for CPU. Available keys: {list(cpu_data.keys())}")
                else:
                    # Even if not in debug mode, ensure we have a value
                    if "usage_percent" not in cpu_data:
                        cpu_data["usage_percent"] = 0.0
        
        # Memory: Calculate percentage from used/total if we have both
        if "memory" in resources:
            mem_data = resources["memory"]
            if isinstance(mem_data, dict):
                if debug:
                    print(f"      🔍 Debug: Memory data before calculation: {mem_data}")
                
                # Try multiple patterns for total, used, free
                total = (mem_data.get("total") or mem_data.get("total_memory") or 
                        mem_data.get("memtotal") or mem_data.get("total_ram") or
                        mem_data.get("physicalmemory") or mem_data.get("physical_memory"))
                used = (mem_data.get("used") or mem_data.get("used_memory") or 
                       mem_data.get("memused") or mem_data.get("used_ram") or
                       mem_data.get("usedphysical") or mem_data.get("used_physical"))
                free = (mem_data.get("free") or mem_data.get("free_memory") or 
                       mem_data.get("memfree") or mem_data.get("free_ram") or
                       mem_data.get("available") or mem_data.get("available_memory") or 
                       mem_data.get("memavailable") or mem_data.get("available_ram") or
                       mem_data.get("freephysical") or mem_data.get("free_physical") or
                       mem_data.get("availablephysical") or mem_data.get("available_physical"))
                
                if debug:
                    print(f"      🔍 Debug: Memory values - total: {total}, used: {used}, free: {free}")
                
                # Calculate used if we have total and free
                if total and free and not used:
                    used = total - free
                    mem_data["used"] = used
                    if debug:
                        print(f"      🔍 Debug: Calculated used from total-free: {used}")
                
                # Calculate percentage if we have total and used
                if total and used and total > 0:
                    usage_percent = (used / total) * 100
                    mem_data["usage_percent"] = round(usage_percent, 2)
                    print(f"      💾 Memory Usage: {mem_data['usage_percent']:.2f}% ({used}/{total} bytes)")
                    if debug:
                        print(f"      🔍 Debug: Calculated memory percentage: {usage_percent}%")
                # If we have usage_percent but it's 0-1 range, convert
                elif "usage_percent" in mem_data:
                    usage = mem_data["usage_percent"]
                    if 0 <= usage <= 1:
                        mem_data["usage_percent"] = usage * 100
                    mem_data["usage_percent"] = float(mem_data["usage_percent"])
                    print(f"      💾 Memory Usage: {mem_data['usage_percent']:.2f}%")
                elif debug:
                    print(f"      🔍 Debug: Cannot calculate memory percentage. Missing total or used. Available keys: {list(mem_data.keys())}")
                else:
                    # Even if not in debug mode, ensure we have a value if we have any memory data
                    if mem_data and "usage_percent" not in mem_data:
                        # Try to calculate from any available data
                        if total and free:
                            used = total - free
                            if total > 0:
                                mem_data["usage_percent"] = round((used / total) * 100, 2)
                                mem_data["used"] = used
                                print(f"      💾 Memory Usage: {mem_data['usage_percent']:.2f}% (calculated from total-free)")
                        else:
                            mem_data["usage_percent"] = 0.0
        
        # Disk: Calculate percentage from used/total if we have both
        if "disk" in resources:
            disk_data = resources["disk"]
            if isinstance(disk_data, dict):
                total = disk_data.get("total") or disk_data.get("total_size") or disk_data.get("size")
                used = disk_data.get("used") or disk_data.get("used_size")
                free = disk_data.get("free") or disk_data.get("free_size") or disk_data.get("available")
                
                # Calculate used if we have total and free
                if total and free and not used:
                    used = total - free
                    disk_data["used"] = used
                
                # Calculate percentage if we have total and used
                if total and used and total > 0:
                    usage_percent = (used / total) * 100
                    disk_data["usage_percent"] = round(usage_percent, 2)
                # If we have usage_percent but it's 0-1 range, convert
                elif "usage_percent" in disk_data:
                    usage = disk_data["usage_percent"]
                    if 0 <= usage <= 1:
                        disk_data["usage_percent"] = usage * 100
        
        return resources

    def _replace_variables(self, data, variables: dict):
        """Replace ${variable} placeholders in data"""
        if isinstance(data, dict):
            return {k: self._replace_variables(v, variables) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_variables(item, variables) for item in data]
        elif isinstance(data, str):
            result = data
            for key, value in variables.items():
                result = result.replace(f"${{{key}}}", str(value))
            return result
        else:
            return data


class MockService:
    """Mock service for non-implemented service types"""

    def __init__(self, service_type: str):
        self.service_type = service_type

    def close(self):
        pass

    def _filter_tests_by_tags(
        self, tests: List[TestDefinition], tags: List[str]
    ) -> List[TestDefinition]:
        """Filter tests by tags"""
        filtered_tests = []

        for test in tests:
            # Check if test has any of the required tags
            if any(tag in test.tags for tag in tags):
                filtered_tests.append(test)

        return filtered_tests

    def dry_run(self, test_path: Path, tags: List[str] = None) -> List[TestDefinition]:
        """Perform a dry run to validate tests without executing them"""
        # Parse test definitions
        if test_path.is_file():
            tests = [self.parser.parse_file(test_path)]
        else:
            tests = self.parser.parse_directory(test_path)

        # Filter tests by tags
        if tags:
            tests = self._filter_tests_by_tags(tests, tags)

        # Validate tests
        for test in tests:
            errors = self.parser.validate_test_definition(test)
            if errors:
                print(f"❌ {test.name} ({test.file_path}):")
                for error in errors:
                    print(f"   - {error}")
            else:
                print(f"✅ {test.name} ({test.file_path})")

        return tests
