"""
Test runner for executing Easy BDD tests
"""

import contextlib
import datetime
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..services.browser_service import BrowserService
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


class TestRunner:
    """Main test runner for Easy BDD Framework"""

    def __init__(self, config: GlobalConfigManager):
        self.config = config
        self.parser = YAMLParser()
        self.generator = GherkinGenerator()

        # Load custom actions
        # Load action modules if available
        # action_registry.load_action_modules(config)

    def run(
        self, test_path: Path, tags: List[str] = None, parallel_workers: int = 1
    ) -> TestResult:
        """Run tests from the specified path"""
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
        print(f"Execution time: {execution_time:.2f} seconds")
        print(f"{'='*60}")

        # Generate HTML report
        # Extract test file name for report naming
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

            # Check for data-driven testing
            if hasattr(test, "data") and test.data:
                return self._execute_data_driven_test(test)
            else:
                return self._execute_single_test(test, test_detail)
        except Exception as e:
            print(f"      Test execution failed: {e}")
            return False

    def _execute_data_driven_test(self, test: TestDefinition) -> bool:
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
                # Merge test variables with current data set
                iteration_variables = test.variables.copy() if test.variables else {}
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
                    iteration_num, success, exec_time = future.result(
                        timeout=120
                    )  # 2 minute timeout
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

            # Merge test variables with current data set
            iteration_variables = test.variables.copy() if test.variables else {}
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
        variables = (
            test.variables.copy() if test.variables else {}
        )  # Initialize variables for cleanup

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

        # Initialize datalake logger if post_results enabled
        datalake_logger = None
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
            print(f"    === Main Test Phase ===")
            for i, step in enumerate(test.steps, 1):
                step_description = self._get_step_description(step)
                print(f"    Step {i}/{len(test.steps)}: {step.action}")
                if step_description:
                    print(f"           → {step_description}")

                # Determine which service to use based on action
                service_type = self._get_service_type(step.action)

                if service_type not in services:
                    services[service_type] = self._create_service(service_type)

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
                        print(f"    ❌ STEP {i} FAILED: {step.action}")
                        print(f"       Details: {step_description}")

                        # Capture failure screenshot
                        failed_step_info = {
                            "step_number": i,
                            "step_action": step.action,
                            "step_details": step_description,
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
                    else:
                        print(f"    ✅ Step {i} completed successfully")
                        step_logs.append(
                            {"step": i, "action": step.action, "status": "passed"}
                        )
                except Exception as e:
                    print(f"    ❌ STEP {i} FAILED WITH EXCEPTION: {step.action}")
                    print(f"       Error: {str(e)}")
                    print(f"       Details: {step_description}")
                    import traceback

                    traceback_str = traceback.format_exc()
                    print(f"       Traceback: {traceback_str}")

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
                return False

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

            # Clean up services first (browser needs to close to save video)
            browser_service = services.get("browser")
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
                        product = (
                            test.variables.get("product", "Unknown")
                            if test.variables
                            else "Unknown"
                        )
                        product_category = (
                            test.variables.get("product_category", "Test")
                            if test.variables
                            else "Test"
                        )
                        mac_address = (
                            test.variables.get("mac_address", "00:00:00:00:00:00")
                            if test.variables
                            else "00:00:00:00:00:00"
                        )
                        time_savings = (
                            test.variables.get("time_savings", 5.0)
                            if test.variables
                            else 5.0
                        )

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

            # Custom assertion actions (support both formats)
            if action_lower in ["assert", "test.assert"]:
                return self._handle_assert_action(step_params, variables)
            elif action_lower in ["assert json schema", "test.assert_schema"]:
                return self._handle_json_schema_action(step_params, variables)
            elif action_lower in ["assert response", "test.assert_response"]:
                return self._handle_response_assertion(step_params, variables)

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

            # Test execution action (run another test as a step)
            if action_lower in ["test.run", "run test", "execute test"]:
                return self._handle_test_run_action(
                    step_params, variables, soft_assert_manager
                )

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
            # Don't catch JSON-RPC or OvrC failures - let them propagate
            # to avoid "Unknown action" fallthrough
            action_lower_check = action.lower()
            if action_lower_check.startswith(
                "jsonrpc"
            ) or action_lower_check.startswith("ovrc"):
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
            variables.get("verbose_logging", False)
            or variables.get("show_full_response", False)
            or params.get("verbose_logging", False)
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
            if "connect" in action_lower:
                # Extract connection parameters
                server_url = params.get("server_url", "")
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
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or params.get("verbose_logging", False)
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
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or params.get("verbose_logging", False)
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
            variables.get("verbose_logging", False)
            or variables.get("show_full_response", False)
            or params.get("verbose_logging", False)
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

        # Extract parameters using helper
        params = self._get_params(step_params)
        action_lower = action.lower()

        try:
            if "list firmware" in action_lower or "list files" in action_lower:
                # List and download firmware files
                bucket_name = params.get("bucket_name", "")
                if not bucket_name:
                    raise ValueError("AWS list firmware requires 'bucket_name'")

                urls = aws_service.list_firmware_files(
                    bucket_name=bucket_name,
                    folder_prefix=params.get("folder_prefix"),
                    filename_pattern=params.get("filename_pattern"),
                    version_pattern=params.get("version_pattern"),
                    file_extension=params.get("file_extension"),
                    specific_version=params.get("specific_version"),
                    cloudfront_url=params.get("cloudfront_url"),
                    cloudfront_filename_only=params.get(
                        "cloudfront_filename_only", False
                    ),
                    download_dir=params.get("download_dir"),
                    protocol=params.get("protocol", "https"),
                    access_key_id=params.get("access_key_id"),
                    secret_access_key=params.get("secret_access_key"),
                    region=params.get("region"),
                )

                # Store URLs in variable if requested
                store_as = params.get("store_as", "")
                if store_as and urls:
                    variables[store_as] = urls
                    print(f"      Stored {len(urls)} URLs as: {store_as}")

                return len(urls) > 0

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

                return result["filename"] is not None

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
            "api.get": "api get",
            "api.post": "api post",
            "api.put": "api put",
            "api.patch": "api patch",
            "api.delete": "api delete",
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
            # Check if this is a conditional step
            if hasattr(step, "condition") and step.condition:
                return self._execute_conditional_step(
                    service, step, variables, soft_assert_manager, step_number
                )

            # Use GlobalConfigManager's variable substitution if available
            if hasattr(self.config, "substitute_recursive"):
                # For GlobalConfigManager, set test variables in runtime scope
                for key, value in variables.items():
                    self.config.set_variable(key, value, "runtime_data")

                # First, resolve nested variables in the test variables
                # Do multiple passes to handle nested variables (e.g., api_base_url contains ${device_ip})
                resolved_vars = variables.copy()
                max_iterations = 10
                for iteration in range(max_iterations):
                    previous_vars = resolved_vars.copy()
                    for key, value in resolved_vars.items():
                        if isinstance(value, str):
                            # Substitute variables in the value
                            new_value = self.config.substitute_variables(
                                value, resolved_vars
                            )
                            resolved_vars[key] = new_value
                    # If no changes, we're done
                    if resolved_vars == previous_vars:
                        break

                # Update the config with the resolved values
                for key, value in resolved_vars.items():
                    self.config.set_variable(key, value, "runtime_data")

                # Use GlobalConfigManager's substitution with all variables
                # Pass variables as additional_vars to ensure they're available
                step_params = self.config.substitute_recursive(
                    step.__dict__.copy(), additional_vars=variables
                )
            else:
                # Fallback to old method with multi-pass substitution
                resolved_vars = variables.copy()
                # Multiple passes to resolve nested variables
                for _ in range(3):  # Up to 3 levels of nesting
                    for key, value in resolved_vars.items():
                        if isinstance(value, str):
                            resolved_vars[key] = self._replace_variables(
                                value, resolved_vars
                            )

                step_params = self._replace_variables(
                    step.__dict__.copy(), resolved_vars
                )

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
                service.click_element(
                    selector=selector, text=text, button=button, role=role, name=name
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
                    service.fill_element(selector, value)
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

            elif "wait" in action:
                wait_time = self._get_param(step_params, "time", 1)
                if isinstance(wait_time, str):
                    try:
                        wait_time = float(wait_time)
                    except ValueError:
                        wait_time = 1
                print(f"      Waiting {wait_time} seconds...")
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
                json_data = step_params.get("json_data", {}) or params_dict.get(
                    "json_data", {}
                )
                data = step_params.get("data", {}) or params_dict.get("data", {})
                params = step_params.get("params", {}) or params_dict.get("params", {})

                # Check for verbose logging
                verbose_logging = (
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", False)
                    or step_params.get("show_full_response", False)
                    or step_params.get("full_log", False)
                    or params_dict.get("verbose_logging", False)
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
                if is_json:
                    try:
                        response_json = response.json()
                        variables["last_json"] = response_json
                    except:
                        variables["last_json"] = None
                else:
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
                store_as = step_params.get("store_response") or params_dict.get(
                    "store_response"
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
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", False)
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
                if is_json:
                    try:
                        response_json = response.json()
                        variables["last_json"] = response_json
                    except:
                        variables["last_json"] = None
                else:
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
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", False)
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
                if is_json:
                    try:
                        response_json = response.json()
                        variables["last_json"] = response_json
                    except:
                        variables["last_json"] = None
                else:
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
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", False)
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
                if is_json:
                    try:
                        response_json = response.json()
                        variables["last_json"] = response_json
                    except:
                        variables["last_json"] = None
                else:
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
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", False)
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
                if is_json:
                    try:
                        response_json = response.json()
                        variables["last_json"] = response_json
                    except:
                        variables["last_json"] = None
                else:
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
                    variables.get("verbose_logging", False)
                    or variables.get("show_full_response", False)
                    or variables.get("full_log", False)
                    or step_params.get("verbose_logging", False)
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
                if is_json:
                    try:
                        response_json = response.json()
                        variables["last_json"] = response_json
                    except:
                        variables["last_json"] = None
                else:
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
