"""
Test runner for executing Easy BDD tests
"""

import sys
import time
import threading
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
import contextlib

from .variable_manager import GlobalConfigManager
from .parser import YAMLParser, TestDefinition
from .generator import GherkinGenerator
from .html_reporter import HTMLReporter
from .soft_assertions import SoftAssertionManager
from .assertions import AssertionEngine, JSONSchemaValidator, ResponseValidator
from .datalake_logger import get_logger, DatalakeLogger
from ..services.browser_service import BrowserService
from ..services.jsonrpc_service import JSONRPCWebSocketService
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
    
    def run(self, test_path: Path, tags: List[str] = None, parallel_workers: int = 1) -> TestResult:
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
                execution_time=0.0
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
                    execution_time=0.0
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
                "file_path": str(test.file_path) if hasattr(test, 'file_path') else None,
                "execution_log": []
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
                    "file_path": str(test.file_path) if hasattr(test, 'file_path') else None
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
        if tests and hasattr(tests[0], 'file_path'):
            test_file_name = Path(tests[0].file_path).stem
        
        reporter = HTMLReporter(Path("reports"))
        report_path = reporter.generate_report(
            test_details=test_details,
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            execution_time=execution_time,
            test_file_name=test_file_name
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
            test_details=test_details
        )
    
    def _execute_test(self, test: TestDefinition, test_detail: Dict[str, Any] = None) -> bool:
        """Execute a single test with data iteration support"""
        try:
            # Store current test file name for screenshot naming
            if hasattr(test, 'file_path'):
                self._current_test_file = Path(test.file_path).stem
            
            # Check for data-driven testing
            if hasattr(test, 'data') and test.data:
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
        async_mode = getattr(test, 'async_execution', False)
        max_workers = getattr(test, 'max_workers', 3)
        
        if async_mode:
            return self._execute_async_data_iterations(test, data_sets, max_workers)
        else:
            return self._execute_sequential_data_iterations(test, data_sets)
    
    def _execute_async_data_iterations(self, test: TestDefinition, data_sets: List[Dict], max_workers: int) -> bool:
        """Execute data iterations asynchronously using thread pool"""
        print(f"    ⚡ Running {len(data_sets)} iterations ASYNCHRONOUSLY (max {max_workers} concurrent)...")
        
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
                    max_workers=1
                )
                
                print(f"    ⚙️  [Thread-{thread_id}] Starting iteration {iteration_num}...")
                start_time = time.time()
                
                # Execute this iteration
                success = self._execute_single_test(iteration_test)
                
                execution_time = time.time() - start_time
                
                if success:
                    print(f"    ✅ [Thread-{thread_id}] Iteration {iteration_num} PASSED ({execution_time:.1f}s)")
                else:
                    print(f"    ❌ [Thread-{thread_id}] Iteration {iteration_num} FAILED ({execution_time:.1f}s)")
                
                return iteration_num, success, execution_time
                
            except Exception as e:
                print(f"    ☠️  [Thread-{thread_id}] Iteration {iteration_num} ERROR: {e}")
                return iteration_num, False, 0
        
        # Execute iterations in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="EasyBDD") as executor:
            # Prepare iteration data with numbering
            iteration_data = [(i+1, data_set) for i, data_set in enumerate(data_sets)]
            
            # Submit all tasks
            print(f"    🚀 Submitting {len(iteration_data)} tasks to thread pool...")
            future_to_iteration = {executor.submit(execute_single_iteration, data): data[0] 
                                 for data in iteration_data}
            
            # Collect results as they complete
            for future in future_to_iteration:
                try:
                    iteration_num, success, exec_time = future.result(timeout=120)  # 2 minute timeout
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
        print(f"       ⚡ Concurrency benefit: {(len(data_sets) * avg_time / max(1, max([t for _, _, t in results]))):.1f}x speedup")
        
        return all_passed
    
    def _execute_sequential_data_iterations(self, test: TestDefinition, data_sets: List[Dict]) -> bool:
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
                max_workers=1
            )
            
            # Execute this iteration
            success = self._execute_single_test(iteration_test)
            if not success:
                all_passed = False
                print(f"    ❌ Data iteration {i} failed")
            else:
                print(f"    ✅ Data iteration {i} passed")
        
        return all_passed
    
    def _execute_single_test(self, test: TestDefinition, test_detail: Dict[str, Any] = None) -> bool:
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
            datalake_logger = DatalakeLogger(
                artifact_path="reports",
                post_results=True
            )
        except Exception as e:
            print(f"    ⚠️  Could not initialize datalake logger: {e}")
        
        # Redirect stdout to capture console output
        sys.stdout = DualWriter(original_stdout, console_output)
        
        try:
            # Load device configuration if specified
            if test.device_config:
                print(f"    🔧 Loading device config: {test.device_config}")
                device_data = self.config.load_device_config(test.device_config)
                if device_data:
                    print(f"    ✅ Device config loaded: {device_data.get('device_info', {}).get('name', test.device_config)}")
                else:
                    print(f"    ⚠️  Warning: Could not load device config: {test.device_config}")
            
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
                            services[service_type], step, test.variables,
                            soft_assert_manager, i
                        )
                        if not success:
                            print(f"    ⚠️  Setup step {i} failed: {step.action}")
                            print(f"       Details: {step_description}")
                            print(f"       Continuing with main test...")
                            # Setup failures don't stop the test, but are logged
                    except Exception as e:
                        print(f"    ⚠️  Setup step {i} failed with exception: {step.action}")
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
                    success = self._execute_step(services[service_type], step, test.variables, soft_assert_manager, i)
                    if not success:
                        print(f"    ❌ STEP {i} FAILED: {step.action}")
                        print(f"       Details: {step_description}")
                        
                        # Capture failure screenshot
                        failed_step_info = {
                            "step_number": i,
                            "step_action": step.action,
                            "step_details": step_description
                        }
                        failure_screenshot = self._capture_failure_screenshot(
                            services.get('browser'), test.name, i
                        )
                        
                        # Store failure info in test_detail if provided
                        if test_detail is not None:
                            test_detail['failed_step'] = failed_step_info
                            test_detail['failure_screenshot'] = failure_screenshot
                            test_detail['step_logs'] = step_logs
                        
                        return False
                    else:
                        print(f"    ✅ Step {i} completed successfully")
                        step_logs.append({
                            "step": i,
                            "action": step.action,
                            "status": "passed"
                        })
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
                        "traceback": traceback_str
                    }
                    failure_screenshot = self._capture_failure_screenshot(
                        services.get('browser'), test.name, i
                    )
                    
                    # Store failure info in test_detail if provided
                    if test_detail is not None:
                        test_detail['failed_step'] = failed_step_info
                        test_detail['failure_screenshot'] = failure_screenshot
                        test_detail['step_logs'] = step_logs
                    
                    return False
                
                # Small delay between steps for visibility
                time.sleep(0.5)
            
            # Check soft assertions at end of main test phase
            if soft_assert_manager and soft_assert_manager.has_failures():
                print(soft_assert_manager.get_summary())
                if test_detail is not None:
                    test_detail['soft_assertions'] = soft_assert_manager.to_dict()
                test_passed = False
                return False
            
            test_passed = True
            return True
            
        except Exception as e:
            print(f"      Error executing test: {e}")
            test_passed = False
            return False
            
        finally:
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
                                services[service_type], step, test.variables,
                                soft_assert_manager, i
                            )
                            if not success:
                                print(f"    ⚠️  Cleanup step {i} failed: {step.action}")
                                print(f"       Details: {step_description}")
                        except Exception as cleanup_error:
                            print(f"    ⚠️  Cleanup step {i} failed with exception: {step.action}")
                            print(f"       Error: {str(cleanup_error)}")
                            print(f"       Details: {step_description}")
                        
                        # Small delay between cleanup steps
                        time.sleep(0.5)
                        
                except Exception as cleanup_error:
                    print(f"    ⚠️  Cleanup phase error: {cleanup_error}")
            
            # Clean up services first (browser needs to close to save video)
            browser_service = services.get('browser')
            for service in services.values():
                if hasattr(service, 'close'):
                    try:
                        service.close()
                    except Exception as e:
                        print(f"    ⚠️  Service cleanup error: {e}")
            
            # Handle video recording AFTER browser closes
            if browser_service and hasattr(browser_service, 'get_video_path'):
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
                            test_detail['video_path'] = relative_path
                        
                        # Check video recording mode
                        video_mode = browser_service._get_browser_config(
                            'video_recording.mode', 'on-failure'
                        )
                        
                        # Clean up video if test passed and mode is on-failure
                        if video_mode == 'on-failure':
                            test_status = test_detail.get('status') if test_detail else None
                            if test_status == 'passed':
                                print(f"    🗑️  Deleting video (test passed)")
                                browser_service.cleanup_video(video_path)
                                if test_detail:
                                    test_detail['video_path'] = None
                except Exception as e:
                    print(f"    ⚠️  Video handling error: {e}")
                    import traceback
                    print(f"    Traceback: {traceback.format_exc()}")
            
            # Restore stdout before posting to datalake
            sys.stdout = original_stdout
            
            # Check datalake configuration
            datalake_enabled = True
            post_on_failure_only = False
            if hasattr(self.config, '_raw_config'):
                config_dict = self.config._raw_config.get('config', {})
                datalake_config = config_dict.get('datalake', {})
                datalake_enabled = datalake_config.get('enabled', True)
                post_on_failure_only = datalake_config.get(
                    'post_on_failure_only', False)
            
            # Post test results to datalake (if enabled)
            if datalake_logger and datalake_enabled:
                # Skip if only posting failures and test passed
                if post_on_failure_only and test_passed:
                    print(f"    ⏭️  Skipping datalake post (test passed, failure-only mode)")
                else:
                    try:
                        # Get test metadata from variables or use defaults
                        product = test.variables.get('product', 'Unknown') if test.variables else 'Unknown'
                        product_category = test.variables.get('product_category', 'Test') if test.variables else 'Test'
                        mac_address = test.variables.get('mac_address', '00:00:00:00:00:00') if test.variables else '00:00:00:00:00:00'
                        time_savings = test.variables.get('time_savings', 5.0) if test.variables else 5.0
                        
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
                            run_url=test_detail.get('report_url', '') if test_detail else '',
                            success=test_passed,
                            type='testrail'
                        )
                        print(f"    📊 Test metrics posted to datalake")
                    except Exception as e:
                        print(f"    ⚠️  Datalake posting error: {e}")
            elif not datalake_enabled:
                print(f"    ⏭️  Datalake logging disabled")
    
    def _capture_failure_screenshot(self, browser_service, test_name: str, step_number: int) -> Optional[str]:
        """Capture screenshot on test failure (only for browser/UI tests)"""
        try:
            # Only capture screenshot if browser service exists and page is active
            if (browser_service and 
                hasattr(browser_service, 'take_screenshot') and
                hasattr(browser_service, 'page') and 
                browser_service.page):
                # Create screenshots directory
                screenshots_dir = Path("reports/screenshots")
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate filename with test file prefix (without .png)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                # Get test file name if available
                test_file = getattr(self, '_current_test_file', 'test')
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
            params = step.parameters if hasattr(step, 'parameters') else {}
            parts = []
            
            # Extract key parameters that help identify the step
            if 'selector' in params:
                parts.append(f"selector='{params['selector']}'")
            if 'text' in params:
                parts.append(f"text='{params['text']}'")
            if 'button' in params:
                parts.append(f"button='{params['button']}'")
            if 'role' in params and 'name' in params:
                parts.append(f"role='{params['role']}', name='{params['name']}'")
            if 'value' in params:
                parts.append(f"value='{params['value']}'")
            if 'label' in params:
                parts.append(f"label='{params['label']}'")
            if 'url' in params:
                parts.append(f"url='{params['url']}'")
            if 'field' in params:
                parts.append(f"field='{params['field']}'")
            
            return ", ".join(parts) if parts else ""
        except Exception:
            return ""
    
    def _get_service_type(self, action: str) -> str:
        """Determine which service type to use for an action"""
        action_lower = action.lower()
        
        if any(keyword in action_lower for keyword in ['browser', 'click', 'fill', 'open', 'screenshot']):
            return 'browser'
        elif any(keyword in action_lower for keyword in ['api', 'request', 'post', 'get']):
            return 'api'
        elif any(keyword in action_lower for keyword in ['websocket', 'ws']):
            return 'websocket'
        else:
            return 'browser'  # Default to browser
    
    def _create_service(self, service_type: str):
        """Create a service instance"""
        if service_type == 'browser':
            from ..services.browser_service import BrowserService
            return BrowserService(self.config)
        elif service_type == 'api':
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
    
    def _execute_custom_action(self, action: str, step_params: dict,
                               variables: dict,
                               soft_assert_manager: SoftAssertionManager = None) -> bool:
        """Execute custom actions if available"""
        try:
            # Check soft assertions action
            if action == 'check soft assertions':
                if soft_assert_manager and soft_assert_manager.has_failures():
                    soft_assert_manager.raise_if_failures()
                else:
                    print("      ✓ No soft assertion failures")
                return True
            
            # Custom assertion actions
            if action == 'assert':
                return self._handle_assert_action(step_params, variables)
            elif action == 'assert json schema':
                return self._handle_json_schema_action(step_params, variables)
            elif action == 'assert response':
                return self._handle_response_assertion(step_params, variables)
            
            # JSON-RPC WebSocket actions
            if action.startswith('jsonrpc'):
                return self._handle_jsonrpc_action(
                    action, step_params, variables)
            
            # AWS S3 actions
            if action.startswith('aws') or 's3' in action:
                return self._handle_aws_action(
                    action, step_params, variables)
            
            # Check if we have custom actions defined
            if hasattr(self.config, 'get_custom_action'):
                custom_action = self.config.get_custom_action(action)
                if custom_action:
                    print(f"      Executing custom action: {action}")
                    # Execute custom action logic here
                    # This would integrate with custom action modules
                    return True
            
            # Check for device-specific actions
            device_actions = ['power_cycle', 'network_port', 'stress_test']
            if any(device_action in action for device_action in device_actions):
                print(f"      Custom action '{action}' detected but not "
                      f"implemented")
                # For now, just log and continue
                return False
                
            return False
        except Exception as e:
            # Don't catch JSON-RPC failures - let them propagate
            # to avoid "Unknown action" fallthrough
            if action.startswith('jsonrpc'):
                raise
            print(f"      Warning: Custom action '{action}' failed: {e}")
            return False
    
    def _execute_conditional_step(self, service, step, variables: dict,
                                  soft_assert_manager=None,
                                  step_number: int = 0) -> bool:
        """Execute a conditional if/then/else step"""
        condition = step.condition
        
        # Substitute variables in condition
        if hasattr(self.config, 'substitute_variables'):
            condition = self.config.substitute_variables(
                condition, variables)
        
        print(f"      Evaluating condition: {condition}")
        
        # Evaluate the condition
        try:
            # Create a safe evaluation context
            eval_context = variables.copy()
            result = eval(condition, {"__builtins__": {}}, eval_context)
            
            print(f"      Condition result: {result}")
            
            # Execute appropriate branch
            if result:
                if step.then_steps:
                    print(f"      → Executing THEN branch "
                          f"({len(step.then_steps)} steps)")
                    for i, then_step in enumerate(step.then_steps, 1):
                        svc_type = self._get_service_type(then_step.action)
                        svc = self._create_service(svc_type)
                        success = self._execute_step(
                            svc, then_step, variables,
                            soft_assert_manager, step_number)
                        if not success:
                            return False
                    return True
                else:
                    print(f"      → Condition true, no THEN steps")
                    return True
            else:
                if step.else_steps:
                    print(f"      → Executing ELSE branch "
                          f"({len(step.else_steps)} steps)")
                    for i, else_step in enumerate(step.else_steps, 1):
                        svc_type = self._get_service_type(else_step.action)
                        svc = self._create_service(svc_type)
                        success = self._execute_step(
                            svc, else_step, variables,
                            soft_assert_manager, step_number)
                        if not success:
                            return False
                    return True
                else:
                    print(f"      → Condition false, no ELSE steps")
                    return True
        except Exception as e:
            print(f"      ✗ Condition evaluation failed: {e}")
            raise ValueError(f"Invalid condition '{condition}': {e}")
    
    def _handle_assert_action(self, step_params: dict, variables: dict) -> bool:
        """Handle Assert action for custom expression evaluation."""
        # Extract from nested structure or top level
        params_dict = step_params.get('parameters', {})
        expression = step_params.get('expression', '') or params_dict.get('expression', '')
        message = step_params.get('message', '') or params_dict.get('message', f"Assertion failed: {expression}")
        
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
        # Extract from nested structure or top level
        params_dict = step_params.get('parameters', {})
        data = (step_params.get('data') or step_params.get('response') or
                params_dict.get('data') or params_dict.get('response'))
        schema = (step_params.get('schema') or step_params.get('schema_file') or
                  params_dict.get('schema') or params_dict.get('schema_file'))
        
        if not data:
            raise ValueError("Assert JSON schema requires 'data' or 'response' parameter")
        if not schema:
            raise ValueError("Assert JSON schema requires 'schema' or 'schema_file' parameter")
        
        # Resolve data from variables
        # The variable substitution converts dicts to strings, so check variables directly
        if isinstance(data, str):
            # Try to find the variable from the stringified value
            if data.startswith('{') or data.startswith('['):
                # This is a stringified dict/list from variable substitution
                # Find the original variable by checking which matches
                for var_name, var_value in variables.items():
                    if (isinstance(var_value, (dict, list)) and 
                        str(var_value).startswith(data[:50])):
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
        # Extract from nested structure or top level
        params_dict = step_params.get('parameters', {})
        response = step_params.get('response') or params_dict.get('response')
        expectations = (step_params.get('expect') or step_params.get('expectations') or
                       params_dict.get('expect') or params_dict.get('expectations'))
        
        if not response:
            raise ValueError("Assert response requires 'response' parameter")
        if not expectations:
            raise ValueError("Assert response requires 'expect' or 'expectations' parameter")
        
        # Resolve response from variables
        # The variable substitution converts dicts to strings, so we need to check variables directly
        if isinstance(response, str):
            # Try to find the variable name from the original step_params before substitution
            # Check if this looks like it was a variable (starts with dict marker '{')
            if response.startswith('{') or response.startswith('['):
                # This is a stringified dict/list from variable substitution
                # Try to find the original variable name by checking which variable matches
                for var_name, var_value in variables.items():
                    if isinstance(var_value, dict) and str(var_value).startswith(response[:50]):
                        response = var_value
                        break
            # Try direct variable lookup
            elif response in variables:
                response = variables[response]
        
        # Create validator and validate
        validator = ResponseValidator()
        result = validator.validate_response(response, expectations)
        
        if result.passed:
            print(f"      ✓ Response validation passed")
            return True
        else:
            print(f"      ✗ Response validation failed: {result.message}")
            if result.details:
                failures = result.details.get('failures', [])
                for failure in failures:
                    print(f"        - {failure}")
            raise AssertionError(result.message)
    
    def _handle_jsonrpc_action(self, action: str, step_params: dict,
                               variables: dict) -> bool:
        """Handle JSON-RPC WebSocket actions."""
        import asyncio
        
        # Get or create JSON-RPC service from variables
        jsonrpc_service = variables.get('_jsonrpc_service')
        
        # Extract parameters dict
        params = step_params.get('parameters', {})
        
        action_lower = action.lower()
        
        try:
            if 'connect' in action_lower:
                # Extract connection parameters
                server_url = params.get('server_url', '')
                device_id = params.get('device_id', '')
                protocol = params.get('protocol', 'firmware-protocol')
                session_id = params.get('session_id', None)
                
                if not server_url:
                    raise ValueError("JSONRPC connect requires 'server_url'")
                if not device_id:
                    raise ValueError("JSONRPC connect requires 'device_id'")
                
                # Optional parameters
                verify_ssl = params.get('verify_ssl', True)
                extra_headers = params.get('headers', {})
                
                # Create service
                jsonrpc_service = JSONRPCWebSocketService(
                    server_url=server_url,
                    device_id=device_id,
                    session_id=session_id,
                    protocol=protocol,
                    verify_ssl=verify_ssl,
                    extra_headers=extra_headers
                )
                
                # Connect
                loop = asyncio.get_event_loop()
                success = loop.run_until_complete(jsonrpc_service.connect())
                
                if success:
                    # Store service in variables
                    variables['_jsonrpc_service'] = jsonrpc_service
                    return True
                else:
                    raise ConnectionError("Failed to connect to JSON-RPC server")
            
            # All other actions require existing connection
            if not jsonrpc_service:
                raise ConnectionError(
                    "Not connected. Use 'JSONRPC connect' first")
            
            loop = asyncio.get_event_loop()
            
            if 'disconnect' in action_lower:
                loop.run_until_complete(jsonrpc_service.disconnect())
                variables.pop('_jsonrpc_service', None)
                return True
            
            elif 'start device updates' in action_lower:
                success = loop.run_until_complete(
                    jsonrpc_service.start_device_updates()
                )
                return success
            
            elif 'stop device updates' in action_lower:
                success = loop.run_until_complete(
                    jsonrpc_service.stop_device_updates()
                )
                return success
            
            elif 'get about' in action_lower:
                result = loop.run_until_complete(jsonrpc_service.get_about())
                store_as = params.get('store_as', '')
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None
            
            elif 'reset device' in action_lower:
                success = loop.run_until_complete(jsonrpc_service.reset_device())
                return success
            
            elif 'get network settings' in action_lower:
                result = loop.run_until_complete(
                    jsonrpc_service.get_network_settings()
                )
                store_as = params.get('store_as', '')
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None
            
            elif 'set network settings' in action_lower:
                success = loop.run_until_complete(
                    jsonrpc_service.set_network_settings(
                        device_name=params.get('device_name'),
                        device_ip=params.get('device_ip'),
                        subnet_mask=params.get('subnet_mask'),
                        gateway=params.get('gateway'),
                        dhcp_enabled=params.get('dhcp_enabled'),
                        dns_server1=params.get('dns_server1'),
                        dns_server2=params.get('dns_server2'),
                        web_port=params.get('web_port')
                    )
                )
                return success
            
            elif 'get time settings' in action_lower:
                result = loop.run_until_complete(
                    jsonrpc_service.get_time_settings()
                )
                store_as = params.get('store_as', '')
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None
            
            elif 'set time settings' in action_lower:
                success = loop.run_until_complete(
                    jsonrpc_service.set_time_settings(
                        timezone_name=params.get('timezone_name', ''),
                        timezone_notes=params.get('timezone_notes'),
                        utc_offset_minutes=params.get('utc_offset_minutes'),
                        current_time=params.get('current_time')
                    )
                )
                return success
            
            elif 'get status update frequency' in action_lower:
                result = loop.run_until_complete(
                    jsonrpc_service.get_status_update_frequency()
                )
                store_as = params.get('store_as', '')
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None
            
            elif 'set status update frequency' in action_lower:
                frequency = params.get('frequency', 0)
                success = loop.run_until_complete(
                    jsonrpc_service.set_status_update_frequency(frequency)
                )
                return success
            
            elif 'enable web connect' in action_lower:
                success = loop.run_until_complete(
                    jsonrpc_service.enable_web_connect(
                        ssh_server=params.get('ssh_server', ''),
                        tunnel_port=params.get('tunnel_port', 0)
                    )
                )
                return success
            
            elif 'disable web connect' in action_lower:
                success = loop.run_until_complete(
                    jsonrpc_service.disable_web_connect(
                        ssh_server=params.get('ssh_server', ''),
                        tunnel_port=params.get('tunnel_port', 0)
                    )
                )
                return success
            
            elif 'set cloud server url' in action_lower:
                success = loop.run_until_complete(
                    jsonrpc_service.set_cloud_server_url(
                        url=params.get('url', ''),
                        port=params.get('port', 0)
                    )
                )
                return success
            
            elif 'disable cloud' in action_lower:
                success = loop.run_until_complete(jsonrpc_service.disable_cloud())
                return success
            
            elif 'update firmware' in action_lower:
                firmware_url = params.get('firmware_url', '')
                success = loop.run_until_complete(
                    jsonrpc_service.update_firmware(firmware_url)
                )
                return success
            
            elif 'find device by serial' in action_lower:
                serial_num = params.get('serial_num', '')
                result = loop.run_until_complete(
                    jsonrpc_service.find_device_by_serial(serial_num)
                )
                store_as = params.get('store_as', '')
                if store_as and result:
                    variables[store_as] = result
                    print(f"      Stored response as: {store_as}")
                return result is not None
            
            else:
                print(f"      ❌ Unknown JSONRPC action: {action}")
                raise ValueError(f"Unknown JSONRPC action: {action}")
                
        except Exception as e:
            print(f"      ❌ JSONRPC action failed: {e}")
            # Re-raise to prevent "Unknown action" fallthrough
            raise
    
    def _handle_aws_action(self, action: str, step_params: dict,
                          variables: dict) -> bool:
        """Handle AWS S3 actions."""
        from ..services.aws_service import AWSService
        
        # Get or create AWS service from variables
        aws_service = variables.get('_aws_service')
        if not aws_service:
            aws_service = AWSService(logger=print)
            variables['_aws_service'] = aws_service
        
        # Extract parameters
        params = step_params.get('parameters', {})
        action_lower = action.lower()
        
        try:
            if 'list firmware' in action_lower or 'list files' in action_lower:
                # List and download firmware files
                bucket_name = params.get('bucket_name', '')
                if not bucket_name:
                    raise ValueError("AWS list firmware requires 'bucket_name'")
                
                urls = aws_service.list_firmware_files(
                    bucket_name=bucket_name,
                    folder_prefix=params.get('folder_prefix'),
                    filename_pattern=params.get('filename_pattern'),
                    version_pattern=params.get('version_pattern'),
                    file_extension=params.get('file_extension'),
                    specific_version=params.get('specific_version'),
                    cloudfront_url=params.get('cloudfront_url'),
                    cloudfront_filename_only=params.get(
                        'cloudfront_filename_only', False),
                    download_dir=params.get('download_dir'),
                    protocol=params.get('protocol', 'https'),
                    access_key_id=params.get('access_key_id'),
                    secret_access_key=params.get('secret_access_key'),
                    region=params.get('region')
                )
                
                # Store URLs in variable if requested
                store_as = params.get('store_as', '')
                if store_as and urls:
                    variables[store_as] = urls
                    print(f"      Stored {len(urls)} URLs as: {store_as}")
                
                return len(urls) > 0
            
            elif 'get latest firmware' in action_lower:
                # Get latest firmware file
                bucket_name = params.get('bucket_name', '')
                if not bucket_name:
                    raise ValueError("AWS get latest firmware requires "
                                   "'bucket_name'")
                
                result = aws_service.get_latest_firmware(
                    bucket_name=bucket_name,
                    folder_prefix=params.get('folder_prefix'),
                    filename_pattern=params.get('filename_pattern'),
                    version_pattern=params.get('version_pattern'),
                    file_extension=params.get('file_extension', '.bin'),
                    download_dir=params.get('download_dir'),
                    get_second_to_last=params.get('get_second_to_last', False),
                    access_key_id=params.get('access_key_id'),
                    secret_access_key=params.get('secret_access_key'),
                    region=params.get('region')
                )
                
                # Store individual values if requested
                if params.get('store_filename_as') and result['filename']:
                    variables[params['store_filename_as']] = result['filename']
                    print(f"      Stored filename as: "
                          f"{params['store_filename_as']}")
                    # Also store basename for easy file path construction
                    if 'basename' in result:
                        variables[f"{params['store_filename_as']}_basename"] = result['basename']
                
                if params.get('store_version_as') and result['version']:
                    variables[params['store_version_as']] = result['version']
                    print(f"      Stored version as: "
                          f"{params['store_version_as']}")
                
                if params.get('store_url_as') and result['url']:
                    variables[params['store_url_as']] = result['url']
                    print(f"      Stored URL as: {params['store_url_as']}")
                
                return result['filename'] is not None
            
            elif 'upload' in action_lower:
                # Upload file to S3
                bucket_name = params.get('bucket_name', '')
                local_file = params.get('local_file_path', '')
                
                if not bucket_name or not local_file:
                    raise ValueError("AWS upload requires 'bucket_name' and "
                                   "'local_file_path'")
                
                url = aws_service.upload_file(
                    bucket_name=bucket_name,
                    local_file_path=local_file,
                    s3_key=params.get('s3_key'),
                    make_public=params.get('make_public', True),
                    access_key_id=params.get('access_key_id'),
                    secret_access_key=params.get('secret_access_key'),
                    region=params.get('region')
                )
                
                # Store URL if requested
                store_as = params.get('store_as', '')
                if store_as and url:
                    variables[store_as] = url
                    print(f"      Stored URL as: {store_as}")
                
                return True
            
            elif 'delete folder' in action_lower:
                # Delete folder from S3
                bucket_name = params.get('bucket_name', '')
                folder_prefix = params.get('folder_prefix', '')
                
                if not bucket_name or not folder_prefix:
                    raise ValueError("AWS delete folder requires 'bucket_name' "
                                   "and 'folder_prefix'")
                
                aws_service.delete_folder(
                    bucket_name=bucket_name,
                    folder_prefix=folder_prefix,
                    access_key_id=params.get('access_key_id'),
                    secret_access_key=params.get('secret_access_key'),
                    region=params.get('region')
                )
                
                return True
            
            else:
                print(f"      ❌ Unknown AWS action: {action}")
                raise ValueError(f"Unknown AWS action: {action}")
                
        except Exception as e:
            print(f"      ❌ AWS action failed: {e}")
            raise
    
    def _execute_step(self, service, step, variables: dict, soft_assert_manager: SoftAssertionManager = None, step_number: int = 0) -> bool:
        """Execute a single step using the appropriate service"""
        try:
            # Check if this is a conditional step
            if hasattr(step, 'condition') and step.condition:
                return self._execute_conditional_step(
                    service, step, variables, soft_assert_manager, step_number)
            
            # Use GlobalConfigManager's variable substitution if available
            if hasattr(self.config, 'substitute_recursive'):
                # For GlobalConfigManager, set test variables in runtime scope
                for key, value in variables.items():
                    self.config.set_variable(key, value, 'runtime_data')
                
                # First, resolve nested variables in the test variables
                resolved_vars = {}
                for key, value in variables.items():
                    if isinstance(value, str):
                        resolved_vars[key] = self.config.substitute_variables(
                            value, variables)
                    else:
                        resolved_vars[key] = value
                    # Update the config with the resolved value
                    self.config.set_variable(
                        key, resolved_vars[key], 'runtime_data')
                
                # Use GlobalConfigManager's substitution with all variables
                step_params = self.config.substitute_recursive(
                    step.__dict__.copy())
            else:
                # Fallback to old method with multi-pass substitution
                resolved_vars = variables.copy()
                # Multiple passes to resolve nested variables
                for _ in range(3):  # Up to 3 levels of nesting
                    for key, value in resolved_vars.items():
                        if isinstance(value, str):
                            resolved_vars[key] = self._replace_variables(
                                value, resolved_vars)
                
                step_params = self._replace_variables(
                    step.__dict__.copy(), resolved_vars)
            
            action = step_params.get('action', '').lower()
            
            # Check for custom actions first
            if self._execute_custom_action(action, step_params, variables,
                                          soft_assert_manager):
                return True
            
            # Execute browser actions
            has_open_browser = hasattr(service, 'open_browser')
            is_browser_open = 'open' in action and 'browser' in action
            if has_open_browser and is_browser_open:
                url = (step_params.get('url', '') or
                       step_params.get('parameters', {}).get('url', ''))
                print(f"      Opening URL: '{url}'")
                service.open_browser(url)
                return True
                
            elif hasattr(service, 'click_element') and 'click' in action:
                params = step_params.get('parameters', {})
                selector = params.get('selector', '')
                text = params.get('text', '')
                button = params.get('button', '')
                role = params.get('role', '')
                name = params.get('name', '')
                service.click_element(selector=selector, text=text, button=button, role=role, name=name)
                return True
                
            elif hasattr(service, 'fill_form_field') and 'fill' in action:
                params = step_params.get('parameters', {})
                field = step_params.get('field', '') or params.get('field', '')
                value = step_params.get('value', '') or params.get('value', '')
                selector = step_params.get('selector', '') or params.get('selector', '')
                role = step_params.get('role', '') or params.get('role', '')
                name = step_params.get('name', '') or params.get('name', '')
                label = step_params.get('label', '') or params.get('label', '')
                
                if role and name:
                    print(f"      Filling {role} '{name}' with value '{value}'")
                    service.fill_form_field('', value, role=role, name=name)
                elif label:
                    print(f"      Filling field labeled '{label}' with value '{value}'")
                    service.fill_form_field('', value, label=label)
                elif field:
                    print(f"      Filling field '{field}' with value '{value}'")
                    service.fill_form_field(field, value)
                elif selector:
                    print(f"      Filling field '{selector}' with value '{value}'")
                    service.fill_element(selector, value)
                return True
                
            elif (hasattr(service, 'take_screenshot') and
                  'screenshot' in action):
                name = (step_params.get('name', 'screenshot') or
                        step_params.get('parameters', {}).
                        get('name', 'screenshot'))
                service.take_screenshot(name)
                return True
                
            elif (hasattr(service, 'verify_text') and 'verify' in action and
                  'text' in action):
                text = (step_params.get('text', '') or
                        step_params.get('parameters', {}).get('text', ''))
                params = step_params.get('parameters', {})
                soft_assert = (step_params.get('soft_assert', False) or
                             params.get('soft_assert', False))
                print(f"      Verifying text: '{text}'")
                service.verify_text(
                    text, soft_assert=soft_assert,
                    soft_assert_manager=soft_assert_manager,
                    step_number=step_number
                )
                return True
            
            elif (hasattr(service, 'verify_element') and 'verify' in action and
                  'element' in action):
                params = step_params.get('parameters', {})
                selector = (step_params.get('selector', '') or
                           params.get('selector', ''))
                soft_assert = (step_params.get('soft_assert', False) or
                             params.get('soft_assert', False))
                print(f"      Verifying element: '{selector}'")
                service.verify_element(
                    selector, soft_assert=soft_assert,
                    soft_assert_manager=soft_assert_manager,
                    step_number=step_number
                )
                return True
                
            elif hasattr(service, 'refresh_browser') and 'refresh' in action:
                print("      Refreshing browser")
                service.refresh_browser()
                return True
                
            # ===== PLAYWRIGHT NATIVE API ACTIONS =====
            
            elif hasattr(service, 'get_by_role') and 'get by role' in action:
                role = step_params.get('role', '')
                name = step_params.get('name', '')
                service.get_by_role(role, name)
                return True
                
            elif hasattr(service, 'get_by_text') and 'get by text' in action:
                text = step_params.get('text', '')
                exact = step_params.get('exact', False)
                service.get_by_text(text, exact=exact)
                return True
                
            elif hasattr(service, 'get_by_label') and 'get by label' in action:
                label = step_params.get('label', '')
                action_type = step_params.get('action_type', 'click')
                value = step_params.get('value', '')
                service.get_by_label(label, action=action_type, value=value)
                return True
                
            elif hasattr(service, 'hover_element') and 'hover' in action:
                selector = step_params.get('selector', '')
                service.hover_element(selector)
                return True
                
            elif hasattr(service, 'double_click_element') and 'double click' in action:
                selector = step_params.get('selector', '')
                service.double_click_element(selector)
                return True
                
            elif hasattr(service, 'press_key') and 'press key' in action:
                key = step_params.get('key', '')
                selector = step_params.get('selector', '')
                service.press_key(key, selector)
                return True
                
            elif hasattr(service, 'wait_for_element') and 'wait for element' in action:
                params = step_params.get('parameters', {})
                selector = params.get('selector', '')
                state = params.get('state', 'visible')
                timeout = params.get('timeout', None)
                service.wait_for_element(selector, state=state, timeout=timeout)
                return True
                
            elif hasattr(service, 'select_option') and 'select option' in action:
                params = step_params.get('parameters', {})
                selector = params.get('selector', '')
                value = params.get('value', '')
                label = params.get('label', '')
                service.select_option(selector, value=value, label=label)
                return True
                
            elif hasattr(service, 'upload_file') and 'upload' in action:
                # Check both top-level and parameters dict
                selector = (step_params.get('selector', '') or
                           step_params.get('parameters', {}).get('selector', ''))
                file_path = (step_params.get('file_path', '') or
                            step_params.get('parameters', {}).get('file_path', ''))
                service.upload_file(selector, file_path)
                return True
                
            elif hasattr(service, 'navigate_back') and 'navigate back' in action:
                service.navigate_back()
                return True
                
            elif hasattr(service, 'navigate_forward') and 'navigate forward' in action:
                service.navigate_forward()
                return True
                
            elif 'wait' in action:
                wait_time = step_params.get('time', '') or step_params.get('parameters', {}).get('time', 1)
                if isinstance(wait_time, str):
                    try:
                        wait_time = float(wait_time)
                    except ValueError:
                        wait_time = 1
                print(f"      Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                return True
            
            # API Actions - order matters, check specific actions first
            elif hasattr(service, 'request') and 'api request' in action:
                # Get parameters from nested structure or top level
                params_dict = step_params.get('parameters', {})
                method = (params_dict.get('method') or
                         step_params.get('method', 'GET')).upper()
                url = (step_params.get('url', '') or 
                      params_dict.get('url', ''))
                device_id = (step_params.get('device_id', '') or 
                            params_dict.get('device_id', 'default'))
                headers = (step_params.get('headers', {}) or 
                          params_dict.get('headers', {}))
                json_data = (step_params.get('json_data', {}) or 
                            params_dict.get('json_data', {}))
                data = (step_params.get('data', {}) or 
                       params_dict.get('data', {}))
                params = (step_params.get('params', {}) or 
                         params_dict.get('params', {}))
                
                print(f"      API {method}: {url} (device: {device_id})")
                response = service.request(method, url, device_id, 
                                        headers=headers, 
                                        json=json_data or None, 
                                        data=data or None,
                                        params=params or None)
                
                # Store response for validation
                variables['last_response'] = response
                variables['last_status'] = response.status_code
                # Parse JSON if content type is JSON
                content_type = response.headers.get('content-type', '')
                if content_type.startswith('application/json'):
                    variables['last_json'] = response.json()
                else:
                    variables['last_json'] = None
                
                # Store response in custom variable if specified
                store_as = (step_params.get('store_response') or 
                           params_dict.get('store_response'))
                if store_as:
                    response_dict = {
                        'status': response.status_code,
                        'headers': dict(response.headers),
                        'body': response.text,
                        'data': response.json() if content_type.startswith('application/json') else response.text,
                        'response_time': response.elapsed.total_seconds() * 1000  # in milliseconds
                    }
                    variables[store_as] = response_dict
                    if hasattr(self.config, 'set_variable'):
                        self.config.set_variable(store_as, response_dict, 'runtime_data')
                    print(f"      Stored response as: {store_as}")
                
                return True
                
            elif (hasattr(service, 'get') and 'api get' == action.strip()):
                # Get parameters from nested structure or top level
                params_dict = step_params.get('parameters', {})
                url = (step_params.get('url', '') or 
                      params_dict.get('url', ''))
                device_id = (step_params.get('device_id', '') or 
                            params_dict.get('device_id', 'default'))
                headers = (step_params.get('headers', {}) or 
                          params_dict.get('headers', {}))
                params = (step_params.get('params', {}) or 
                         params_dict.get('params', {}))
                
                print(f"      API GET: {url} (device: {device_id})")
                response = service.get(url, device_id,
                                      headers=headers, params=params)
                
                # Store response for validation
                variables['last_response'] = response
                variables['last_status'] = response.status_code
                variables['last_json'] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None
                
                return True
                
            elif (hasattr(service, 'post') and 'api post' == action.strip()):
                # Get parameters from nested structure or top level
                params_dict = step_params.get('parameters', {})
                url = (step_params.get('url', '') or 
                      params_dict.get('url', ''))
                device_id = (step_params.get('device_id', '') or 
                            params_dict.get('device_id', 'default'))
                headers = (step_params.get('headers', {}) or 
                          params_dict.get('headers', {}))
                json_data = (step_params.get('json_data', {}) or 
                            params_dict.get('json_data', {}))
                data = (step_params.get('data', {}) or 
                       params_dict.get('data', {}))
                
                print(f"      API POST: {url} (device: {device_id})")
                response = service.post(url, device_id,
                                       headers=headers,
                                       json=json_data or None,
                                       data=data or None)
                
                # Store response for validation
                variables['last_response'] = response
                variables['last_status'] = response.status_code
                variables['last_json'] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None
                
                return True
                
            elif hasattr(service, 'put') and 'api put' == action.strip():
                url = step_params.get('url', '')
                device_id = step_params.get('device_id', 'default')
                headers = step_params.get('headers', {})
                json_data = step_params.get('json_data', {})
                data = step_params.get('data', {})
                
                print(f"      API PUT: {url} (device: {device_id})")
                response = service.put(url, device_id, headers=headers, json=json_data or None, data=data or None)
                
                # Store response for validation
                variables['last_response'] = response
                variables['last_status'] = response.status_code
                variables['last_json'] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None
                
                return True
                
            elif hasattr(service, 'delete') and 'api delete' == action.strip():
                url = step_params.get('url', '')
                device_id = step_params.get('device_id', 'default')
                headers = step_params.get('headers', {})
                
                print(f"      API DELETE: {url} (device: {device_id})")
                response = service.delete(url, device_id, headers=headers)
                
                # Store response for validation
                variables['last_response'] = response
                variables['last_status'] = response.status_code
                variables['last_json'] = response.json() if response.headers.get('content-type', '').startswith('application/json') else None
                
                return True
                
            elif 'validate status' in action:
                expected_status = step_params.get('status', 200)
                actual_status = variables.get('last_status', 0)
                
                if actual_status == expected_status:
                    return True
                else:
                    return False
                    
            elif 'validate json' in action:
                field = step_params.get('field', '')
                expected_value = step_params.get('value', '')
                last_json = variables.get('last_json', {})
                
                if not last_json:
                    print(f"      ❌ No JSON response to validate")
                    return False
                
                # Support nested field access with dot notation
                actual_value = last_json
                for field_part in field.split('.'):
                    if isinstance(actual_value, dict) and field_part in actual_value:
                        actual_value = actual_value[field_part]
                    else:
                        actual_value = None
                        break
                
                print(f"      Validating JSON field '{field}': expected '{expected_value}', got '{actual_value}'")
                if str(actual_value) == str(expected_value):
                    print(f"      ✅ JSON validation passed")
                    return True
                else:
                    print(f"      ❌ JSON validation failed")
                    return False
                
            else:
                print(f"      ❌ Unknown action: {action}")
                print(f"      Available actions: click, fill, select option, wait, screenshot, etc.")
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
    
    def _filter_tests_by_tags(self, tests: List[TestDefinition], tags: List[str]) -> List[TestDefinition]:
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