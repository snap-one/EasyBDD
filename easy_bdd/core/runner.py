"""
Test runner for executing Easy BDD tests
"""

import sys
import time
import threading
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import ConfigManager
from .parser import YAMLParser, TestDefinition
from .generator import GherkinGenerator
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


class TestRunner:
    """Main test runner for Easy BDD Framework"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.parser = YAMLParser()
        self.generator = GherkinGenerator()
    
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
        
        print(f"\n{'='*60}")
        print(f"Test Results: {passed} passed, {failed} failed")
        print(f"Execution time: {execution_time:.2f} seconds")
        print(f"{'='*60}")
        
        result = TestResult(
            success=success,
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=0,
            execution_time=execution_time,
            report_path=Path(self.config.get("reporting.output_dir", "reports")) / "report.html"
        )
        
        return result
    
    def _execute_test(self, test: TestDefinition) -> bool:
        """Execute a single test with data iteration support"""
        try:
            # Check for data-driven testing
            if hasattr(test, 'data') and test.data:
                return self._execute_data_driven_test(test)
            else:
                return self._execute_single_test(test)
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
    
    def _execute_single_test(self, test: TestDefinition) -> bool:
        """Execute a single test definition with setup, main steps, and cleanup"""
        services = {}
        
        try:
            # Execute setup steps first
            if test.setup:
                print(f"    === Setup Phase ===")
                for i, step in enumerate(test.setup, 1):
                    print(f"    Setup {i}: {step.action}")
                    
                    # Determine which service to use based on action
                    service_type = self._get_service_type(step.action)
                    
                    if service_type not in services:
                        services[service_type] = self._create_service(service_type)
                    
                    # Execute the setup step
                    success = self._execute_step(services[service_type], step, test.variables)
                    if not success:
                        print(f"    ❌ Setup step {i} failed - continuing with main test")
                        # Setup failures don't stop the test, but are logged
                    
                    # Small delay between steps
                    time.sleep(0.5)
            
            # Execute main test steps
            print(f"    === Main Test Phase ===")
            for i, step in enumerate(test.steps, 1):
                print(f"    Step {i}: {step.action}")
                
                # Determine which service to use based on action
                service_type = self._get_service_type(step.action)
                
                if service_type not in services:
                    services[service_type] = self._create_service(service_type)
                
                # Execute the step
                success = self._execute_step(services[service_type], step, test.variables)
                if not success:
                    return False
                
                # Small delay between steps for visibility
                time.sleep(0.5)
            
            return True
            
        except Exception as e:
            print(f"      Error executing test: {e}")
            return False
            
        finally:
            # Execute cleanup steps regardless of main test result
            if test.cleanup:
                try:
                    print(f"    === Cleanup Phase ===")
                    for i, step in enumerate(test.cleanup, 1):
                        print(f"    Cleanup {i}: {step.action}")
                        
                        # Determine which service to use based on action
                        service_type = self._get_service_type(step.action)
                        
                        if service_type not in services:
                            services[service_type] = self._create_service(service_type)
                        
                        # Execute cleanup step - don't let failures stop cleanup
                        try:
                            self._execute_step(services[service_type], step, test.variables)
                        except Exception as cleanup_error:
                            print(f"    ⚠️  Cleanup step {i} failed: {cleanup_error}")
                        
                        # Small delay between cleanup steps
                        time.sleep(0.5)
                        
                except Exception as cleanup_error:
                    print(f"    ⚠️  Cleanup phase error: {cleanup_error}")
            
            # Clean up services
            for service in services.values():
                if hasattr(service, 'close'):
                    try:
                        service.close()
                    except:
                        pass
    
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
        else:
            # For now, return a mock service for other types
            return MockService(service_type)
    
    def _execute_step(self, service, step, variables: dict) -> bool:
        """Execute a single step using the appropriate service"""
        try:
            # Replace variables in step parameters
            step_params = self._replace_variables(step.__dict__.copy(), variables)
            action = step_params.get('action', '').lower()
            
            # Execute browser actions
            if hasattr(service, 'open_browser') and 'open' in action and 'browser' in action:
                url = step_params.get('url', '') or step_params.get('parameters', {}).get('url', '')
                print(f"      Opening URL: '{url}'")
                service.open_browser(url)
                return True
                
            elif hasattr(service, 'click_element') and 'click' in action:
                selector = (step_params.get('selector', '') or 
                           step_params.get('parameters', {}).get('selector', ''))
                service.click_element(selector=selector)
                return True
                
            elif hasattr(service, 'fill_form_field') and 'fill' in action:
                field = (step_params.get('field', '') or 
                        step_params.get('parameters', {}).get('field', ''))
                value = (step_params.get('value', '') or 
                        step_params.get('parameters', {}).get('value', ''))
                selector = (step_params.get('selector', '') or 
                           step_params.get('parameters', {}).get('selector', ''))
                print(f"      Filling field '{field}' with value '{value}'")
                if field:
                    service.fill_form_field(field, value)
                elif selector:
                    service.fill_element(selector, value)
                return True
                
            elif hasattr(service, 'take_screenshot') and 'screenshot' in action:
                name = (step_params.get('name', 'screenshot') or 
                       step_params.get('parameters', {}).get('name', 'screenshot'))
                service.take_screenshot(name)
                return True
                
            elif hasattr(service, 'verify_text') and 'verify' in action and 'text' in action:
                text = (step_params.get('text', '') or 
                       step_params.get('parameters', {}).get('text', ''))
                print(f"      Verifying text: '{text}'")
                service.verify_text(text)
                return True
                
            elif hasattr(service, 'refresh_browser') and 'refresh' in action:
                print(f"      Refreshing browser")
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
                selector = step_params.get('selector', '')
                state = step_params.get('state', 'visible')
                timeout = step_params.get('timeout', None)
                service.wait_for_element(selector, state=state, timeout=timeout)
                return True
                
            elif hasattr(service, 'upload_file') and 'upload' in action:
                selector = step_params.get('selector', '')
                file_path = step_params.get('file_path', '')
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
                
            else:
                print(f"      Unknown action: {action}")
                return False
                
        except Exception as e:
            print(f"      Error in step execution: {e}")
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