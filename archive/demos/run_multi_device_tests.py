# Method 4: Parallel Execution Script
# Python script to generate and run tests in parallel

import yaml
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def create_device_test(endpoint_id: str, device_name: str, expected_model: str) -> str:
    """Generate a device test file from template"""
    template = {
        'name': f'Device {endpoint_id} Configuration Test',
        'description': f'Test configuration for device endpoint {endpoint_id}',
        'tags': ['browser', 'playwright', 'device-config', f'device-{endpoint_id}'],
        'variables': {
            'base_url': 'http://binary:SnapAV704@192.168.100.8',
            'page': 'unit',
            'endpoint_id': endpoint_id,
            'device_name': device_name,
            'expected_model': expected_model
        },
        'steps': [
            {
                'action': 'Open browser',
                'url': '${base_url}/${page}/${endpoint_id}',
                'description': f'Open device {endpoint_id} configuration page'
            },
            {
                'action': 'Fill form field',
                'field': '[role="textbox"][name="Name"]',
                'value': '${device_name}',
                'description': f'Enter device name for {endpoint_id}'
            },
            {
                'action': 'Wait for element',
                'selector': '.btn.btn-outline:not([disabled])',
                'state': 'visible',
                'timeout': 10000,
                'description': 'Wait for save button to be enabled'
            },
            {
                'action': 'Click element',
                'selector': '.btn.btn-outline',
                'description': 'Save configuration'
            },
            {
                'action': 'Verify text',
                'text': '${device_name}',
                'description': 'Verify device name was saved'
            }
        ]
    }
    
    # Create test file
    test_file = Path(f'tests/cases/device_{endpoint_id}_config.yaml')
    with open(test_file, 'w') as f:
        yaml.dump(template, f, default_flow_style=False)
    
    return str(test_file)

def run_device_test(test_file: str) -> tuple:
    """Run a single device test"""
    try:
        result = subprocess.run([
            '.venv/bin/python', '-m', 'easy_bdd', 'run', test_file, '--headless'
        ], capture_output=True, text=True, timeout=120)
        
        return test_file, result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return test_file, False, "", "Test timed out"

# Device configurations
devices = [
    ('1204', 'RX-D46A9121077B', 'B-900-MOIP-4K-RX'),
    ('1205', 'RX-D46A9121077C', 'B-900-MOIP-4K-RX'),
    ('1206', 'RX-D46A9121077D', 'B-900-MOIP-4K-RX'),
    ('1207', 'RX-D46A9121077E', 'B-900-MOIP-4K-RX'),
    ('1208', 'RX-D46A9121077F', 'B-900-MOIP-4K-RX'),
    # Add more devices as needed
]

def main():
    # Generate test files
    test_files = []
    for endpoint_id, device_name, expected_model in devices:
        test_file = create_device_test(endpoint_id, device_name, expected_model)
        test_files.append(test_file)
    
    print(f"Generated {len(test_files)} test files")
    
    # Run tests in parallel (max 3 concurrent)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(run_device_test, test_files))
    
    # Report results
    passed = 0
    failed = 0
    
    for test_file, success, stdout, stderr in results:
        if success:
            passed += 1
            print(f"✅ {test_file}: PASSED")
        else:
            failed += 1
            print(f"❌ {test_file}: FAILED")
            if stderr:
                print(f"   Error: {stderr}")
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")

if __name__ == "__main__":
    main()