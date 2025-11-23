# Test Results Export Functionality

The Easy BDD framework now supports exporting test results to multiple formats using the `--export-results` argument.

## Usage

```bash
# Export to JSON (default format)
python -m easy_bdd run tests/web_ui/simple_test.yaml --export-results results.json

# Export to CSV
python -m easy_bdd run tests/web_ui/simple_test.yaml --export-results results.csv

# Export to XML
python -m easy_bdd run tests/web_ui/simple_test.yaml --export-results results.xml

# Auto-detect format by extension
python -m easy_bdd run tests/web_ui/ --export-results test_report.json
```

## Supported Formats

### JSON Format
- Complete test details including individual test information
- Structured data perfect for CI/CD integration
- Includes summary statistics and detailed test results

### CSV Format
- Summary section with key metrics
- Individual test results table
- Easy to import into spreadsheet applications

### XML Format
- Structured XML with summary and test details
- Compatible with many CI/CD systems and reporting tools
- Includes timestamps and status information

## Export Data Structure

### Summary Information
- Total tests executed
- Passed/Failed/Skipped counts
- Success rate percentage
- Total execution time
- Overall test status

### Individual Test Details
- Test name and description
- Tags for categorization
- Individual execution time
- Pass/Fail status
- Error messages for failed tests
- Source file path

## Examples

### JSON Export Example
```json
{
  "timestamp": "2025-11-22T14:20:48.065432",
  "summary": {
    "total_tests": 3,
    "passed": 1,
    "failed": 2,
    "skipped": 0,
    "success_rate": 33.33,
    "execution_time_seconds": 40.23
  },
  "status": "FAILED",
  "tests": [
    {
      "name": "Simple Web UI Test",
      "description": "Basic test to verify web UI framework works",
      "tags": ["smoke", "basic"],
      "status": "PASSED",
      "execution_time": 5.52,
      "file_path": "tests/web_ui/simple_test.yaml"
    }
  ]
}
```

### CSV Export Structure
```csv
SUMMARY
Metric,Value
Total Tests,1
Passed,1
Failed,0
Success Rate %,100.0

INDIVIDUAL TEST RESULTS
Test Name,Status,Description,Execution Time (s),Tags,Error
Simple Web UI Test,PASSED,Basic test to verify web UI framework works,5.52,"smoke, basic",
```

## Integration with CI/CD

The exported results can be easily integrated with:
- GitHub Actions
- GitLab CI
- Jenkins
- Azure DevOps
- Any CI/CD system that supports JSON/XML/CSV

Example GitHub Actions usage:
```yaml
- name: Run Tests and Export Results
  run: python -m easy_bdd run tests/ --export-results test-results.json

- name: Upload Test Results
  uses: actions/upload-artifact@v3
  with:
    name: test-results
    path: test-results.json
```