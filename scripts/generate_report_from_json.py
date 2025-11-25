#!/usr/bin/env python3
"""
Generate HTML report from a JSON test results file

Usage:
    python scripts/generate_report_from_json.py <json_file_path> [output_dir]
    
    Or use the virtual environment:
    .venv/bin/python scripts/generate_report_from_json.py <json_file_path> [output_dir]
"""
import json
import sys
from pathlib import Path

# Add parent directory to path to import easy_bdd modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from easy_bdd.core.html_reporter import HTMLReporter
except ImportError as e:
    print(f"❌ Error importing HTMLReporter: {e}")
    print(f"💡 Try using the virtual environment:")
    print(f"   .venv/bin/python scripts/generate_report_from_json.py <json_file_path>")
    sys.exit(1)


def generate_report_from_json(json_file_path: str, output_dir: str = None):
    """Generate HTML report from JSON test results file"""
    json_path = Path(json_file_path)
    
    if not json_path.exists():
        print(f"❌ Error: JSON file not found: {json_file_path}")
        return None
    
    # Read JSON file
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Determine output directory
    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = json_path.parent
    
    # Extract test details from JSON
    # Handle different JSON formats
    if "tests" in data:
        # Format from HTMLReporter (has "tests" array)
        test_details = data["tests"]
        total_tests = data.get("total_tests", len(test_details))
        passed = data.get("passed", sum(1 for t in test_details if t.get("status") in ["PASSED", "COMPLETED"]))
        failed = data.get("failed", sum(1 for t in test_details if t.get("status") == "FAILED"))
        execution_time = data.get("execution_time", sum(t.get("execution_time", 0) for t in test_details))
        test_file_name = data.get("test_file", json_path.stem.replace("_results", "").replace("_report", ""))
    elif "test_path" in data and "output" in data:
        # Format from web app test execution (has test_path, status, output array)
        from datetime import datetime
        
        # Parse execution time from started/finished timestamps
        execution_time = 0
        if "started" in data and "finished" in data:
            try:
                started = datetime.fromisoformat(data["started"].replace("Z", "+00:00"))
                finished = datetime.fromisoformat(data["finished"].replace("Z", "+00:00"))
                execution_time = (finished - started).total_seconds()
            except:
                pass
        
        # Try to extract execution time from output
        if execution_time == 0:
            for line in data.get("output", []):
                if "Execution time:" in line:
                    try:
                        execution_time = float(line.split("Execution time:")[1].split("seconds")[0].strip())
                        break
                    except:
                        pass
        
        # Try to extract test results from output
        passed = 0
        failed = 0
        for line in data.get("output", []):
            if "passed" in line.lower() and "failed" in line.lower():
                try:
                    # Parse "Test Results: X passed, Y failed"
                    parts = line.split("Test Results:")[1].strip()
                    passed = int(parts.split("passed")[0].strip())
                    failed = int(parts.split("failed")[0].split(",")[1].strip())
                    break
                except:
                    pass
        
        # If not found, use status field
        if passed == 0 and failed == 0:
            if data.get("status", "").lower() in ["passed", "completed", "success"]:
                passed = 1
            else:
                failed = 1
        
        total_tests = passed + failed if (passed + failed) > 0 else 1
        
        # Extract test name from output or test_path
        test_name = "Test"
        for line in data.get("output", []):
            if "Executing test" in line:
                try:
                    test_name = line.split("Executing test")[1].split(":")[1].strip()
                    break
                except:
                    pass
        
        if test_name == "Test":
            test_name = Path(data.get("test_path", "")).stem.replace("_", " ").title()
        
        # Create test detail structure
        test_details = [{
            "name": test_name,
            "description": "",
            "tags": [],
            "status": "PASSED" if data.get("status", "").lower() in ["passed", "completed", "success"] else "FAILED",
            "execution_time": execution_time,
            "file_path": data.get("test_path", ""),
            "execution_log": "\n".join(data.get("output", [])),
            "error": None if data.get("status", "").lower() in ["passed", "completed", "success"] else "\n".join(data.get("output", []))
        }]
        
        test_file_name = Path(data.get("test_path", json_path.stem)).stem
    elif isinstance(data, list):
        # Format is a list of test results
        test_details = data
        total_tests = len(test_details)
        passed = sum(1 for t in test_details if t.get("status") in ["PASSED", "COMPLETED"] or t.get("success", False))
        failed = sum(1 for t in test_details if t.get("status") == "FAILED" or (not t.get("success", True) and t.get("status") != "PASSED"))
        execution_time = sum(t.get("execution_time", 0) for t in test_details)
        test_file_name = json_path.stem.replace("_results", "").replace("_report", "")
    else:
        # Try to extract from other formats
        print(f"⚠️  Warning: Unknown JSON format. Attempting to parse...")
        test_details = []
        if "test_details" in data:
            test_details = data["test_details"]
        elif "results" in data:
            test_details = data["results"]
        else:
            # Try to use the data itself as a single test result
            test_details = [data]
        
        total_tests = len(test_details) if test_details else 1
        passed = sum(1 for t in test_details if t.get("status") in ["PASSED", "COMPLETED"] or t.get("success", False)) if test_details else 0
        failed = total_tests - passed
        execution_time = sum(t.get("execution_time", 0) for t in test_details) if test_details else data.get("execution_time", 0)
        test_file_name = json_path.stem.replace("_results", "").replace("_report", "")
    
    # Generate report
    reporter = HTMLReporter(output_path)
    report_path = reporter.generate_report(
        test_details=test_details,
        total_tests=total_tests,
        passed=passed,
        failed=failed,
        execution_time=execution_time,
        test_file_name=test_file_name,
    )
    
    print(f"✅ HTML Report generated: {report_path}")
    print(f"   Open with: open {report_path}")
    
    return report_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_report_from_json.py <json_file_path> [output_dir]")
        print("\nExample:")
        print("  python generate_report_from_json.py reports/araknis_simple_test_results_20251124_193356.json")
        print("  python generate_report_from_json.py reports/araknis_simple_test_results_20251124_193356.json reports/")
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    generate_report_from_json(json_file, output_dir)

