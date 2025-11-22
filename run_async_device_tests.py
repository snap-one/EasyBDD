#!/usr/bin/env python3
"""
Async Multi-Device Test Runner for Easy BDD Framework
Demonstrates running device tests asynchronously
"""

import asyncio
import subprocess
import tempfile
import yaml
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple

class AsyncDeviceTestRunner:
    def __init__(self, base_url: str, max_workers: int = 3):
        self.base_url = base_url
        self.max_workers = max_workers
        
    def create_device_test(self, endpoint_id: str, device_name: str) -> str:
        """Create a temporary test file for a device"""
        test_config = {
            'name': f'Device {endpoint_id} Async Test',
            'description': f'Async test for device endpoint {endpoint_id}',
            'tags': ['browser', 'playwright', 'device-config', f'async-{endpoint_id}'],
            'variables': {
                'base_url': self.base_url,
                'page': 'unit',
                'endpoint_id': endpoint_id,
                'device_name': device_name
            },
            'steps': [
                {
                    'action': 'Open browser',
                    'url': '${base_url}/${page}/${endpoint_id}',
                    'description': 'Open device configuration page'
                },
                {
                    'action': 'Take screenshot',
                    'name': 'async_device_${endpoint_id}_loaded',
                    'description': 'Capture device page after loading'
                },
                {
                    'action': 'Fill form field',
                    'field': '[role="textbox"][name="Name"]',
                    'value': '${device_name}',
                    'description': 'Enter device name'
                },
                {
                    'action': 'Wait for element',
                    'selector': '.btn.btn-outline:not([disabled])',
                    'state': 'visible',
                    'timeout': 10000,
                    'description': 'Wait for button to become enabled'
                },
                {
                    'action': 'Click element',
                    'selector': '.btn.btn-outline',
                    'description': 'Click the outline button'
                },
                {
                    'action': 'Take screenshot',
                    'name': 'async_device_${endpoint_id}_configured',
                    'description': 'Capture page after configuration'
                },
                {
                    'action': 'Verify text',
                    'text': '${device_name}',
                    'description': 'Verify device name appears on page'
                }
            ]
        }
        
        # Create temporary test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f, default_flow_style=False)
            return f.name
    
    def run_single_device_test(self, endpoint_id: str, device_name: str) -> Tuple[str, bool, float, str]:
        """Run a single device test"""
        print(f"🔧 [Device-{endpoint_id}] Starting test...")
        
        start_time = time.time()
        test_file = None
        
        try:
            # Create test file
            test_file = self.create_device_test(endpoint_id, device_name)
            
            # Run test
            result = subprocess.run([
                '.venv/bin/python', '-m', 'easy_bdd', 'run', 
                test_file, '--headless'
            ], capture_output=True, text=True, timeout=120)
            
            execution_time = time.time() - start_time
            success = result.returncode == 0
            
            if success:
                print(f"✅ [Device-{endpoint_id}] PASSED ({execution_time:.1f}s)")
                return endpoint_id, True, execution_time, result.stdout
            else:
                print(f"❌ [Device-{endpoint_id}] FAILED ({execution_time:.1f}s)")
                return endpoint_id, False, execution_time, result.stderr
                
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            print(f"⏰ [Device-{endpoint_id}] TIMEOUT ({execution_time:.1f}s)")
            return endpoint_id, False, execution_time, "Test timed out"
            
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"💥 [Device-{endpoint_id}] ERROR ({execution_time:.1f}s): {e}")
            return endpoint_id, False, execution_time, str(e)
            
        finally:
            # Cleanup
            if test_file and Path(test_file).exists():
                Path(test_file).unlink()
    
    def run_async_tests(self, devices: List[Tuple[str, str]]) -> Dict[str, any]:
        """Run multiple device tests asynchronously"""
        print(f"🚀 Starting async execution for {len(devices)} devices...")
        print(f"⚡ Max concurrent workers: {self.max_workers}")
        
        results = []
        start_time = time.time()
        
        # Use ThreadPoolExecutor for concurrent execution
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="DeviceTest") as executor:
            # Submit all tasks
            future_to_device = {
                executor.submit(self.run_single_device_test, endpoint_id, device_name): (endpoint_id, device_name)
                for endpoint_id, device_name in devices
            }
            
            # Collect results as they complete
            for future in future_to_device:
                endpoint_id, device_name = future_to_device[future]
                try:
                    result = future.result(timeout=150)  # 2.5 minute timeout per test
                    results.append(result)
                except Exception as e:
                    print(f"💥 [Device-{endpoint_id}] Exception: {e}")
                    results.append((endpoint_id, False, 0, str(e)))
        
        total_time = time.time() - start_time
        
        # Analyze results
        passed = sum(1 for _, success, _, _ in results if success)
        failed = len(results) - passed
        avg_time = sum(exec_time for _, _, exec_time, _ in results) / len(results) if results else 0
        max_time = max((exec_time for _, _, exec_time, _ in results), default=0)
        
        # Calculate speedup (theoretical vs actual)
        theoretical_sequential_time = sum(exec_time for _, _, exec_time, _ in results)
        speedup = theoretical_sequential_time / total_time if total_time > 0 else 1
        
        return {
            'results': results,
            'summary': {
                'total_tests': len(devices),
                'passed': passed,
                'failed': failed,
                'total_time': total_time,
                'avg_time': avg_time,
                'max_time': max_time,
                'speedup': speedup,
                'theoretical_sequential_time': theoretical_sequential_time
            }
        }
    
    def print_results(self, test_results: Dict[str, any]):
        """Print formatted test results"""
        results = test_results['results']
        summary = test_results['summary']
        
        print("\\n" + "="*60)
        print("🎯 ASYNC MULTI-DEVICE TEST RESULTS")
        print("="*60)
        
        # Individual results
        for endpoint_id, success, exec_time, output in results:
            status = "✅ PASSED" if success else "❌ FAILED"
            print(f"{status} | Device-{endpoint_id:>4} | {exec_time:>6.1f}s")
        
        print("-"*60)
        
        # Summary statistics
        print(f"📊 Summary:")
        print(f"   Total Tests:    {summary['total_tests']}")
        print(f"   ✅ Passed:      {summary['passed']}")
        print(f"   ❌ Failed:      {summary['failed']}")
        print(f"   ⏱️  Total Time:   {summary['total_time']:.1f}s")
        print(f"   📈 Avg Time:     {summary['avg_time']:.1f}s")
        print(f"   ⚡ Speedup:      {summary['speedup']:.1f}x")
        print(f"   💡 Efficiency:   {(summary['speedup']/self.max_workers)*100:.1f}%")
        
        print("="*60)

def main():
    """Main execution function"""
    # Device configurations
    devices = [
        ('1204', 'RX-D46A9121077B'),
        ('1012', 'RX-D46A9121E8C0'),
        ('1156', 'RX-D46A91272239'),
        # Add more devices as needed
    ]
    
    # Initialize runner
    runner = AsyncDeviceTestRunner(
        base_url='http://binary:SnapAV704@192.168.100.8',
        max_workers=3
    )
    
    # Run async tests
    test_results = runner.run_async_tests(devices)
    
    # Display results
    runner.print_results(test_results)
    
    # Exit with appropriate code
    summary = test_results['summary']
    if summary['failed'] > 0:
        exit(1)
    else:
        print("🎉 All tests passed!")
        exit(0)

if __name__ == "__main__":
    main()