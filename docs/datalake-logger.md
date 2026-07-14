# Datalake Logger

**Comprehensive logging with error hints and metrics posting**

---

## Overview

The Datalake Logger provides advanced logging capabilities including:

- **Loguru Integration**: Beautiful console logging with colors
- **Error Hints**: AI-powered or rule-based error explanations
- **Datalake Metrics**: Post test results to data analytics platform
- **Limited Tracebacks**: Show only project-relevant stack frames

---

## Installation

Install required dependencies:

```bash
pip install loguru requests

# Optional: For AI-powered error hints
pip install openai
```

Or install via pyproject.toml:

```bash
pip install -e ".[ai]"
```

---

## Configuration

### Environment Variables

```bash
# Datalake configuration
export DATALAKE_URL="https://your-datalake-endpoint"
export DATALAKE_API_KEY="your-api-key"

# Optional: OpenAI for error hints
export OPENAI_API_KEY="your-openai-key"
```

### Framework Configuration

Add to `config/framework.yaml`:

```yaml
config:
  logging:
    enabled: true
    artifact_path: "reports/artifacts"
    post_results: true  # Set to false to disable Datalake posting
    console_to_file: true
    
    # Datalake configuration
    datalake:
      enabled: true
      url: "${DATALAKE_URL}"
      api_key: "${DATALAKE_API_KEY}"
    
    # Error hints
    error_hints:
      enabled: true
      use_gpt: true
      substitutions:
        - ["ConnectionError", "timeout", "Check network connectivity and API endpoint"]
        - ["AssertionError", "expected", "Verify test expectations match actual values"]
        - ["KeyError", "", "Missing required key in response data"]
```

---

## Usage

### Basic Logging

```python
from easybdd.core.datalake_logger import get_logger

# Get logger instance
logger = get_logger()

# Log messages
logger.info("Test started")
logger.debug("Detailed debug info")
logger.warning("Something might be wrong")
logger.error("An error occurred")
logger.exception("Error with traceback")
```

### In Test Steps

The logger is automatically integrated into the test runner:

```yaml
steps:
  - action: API request
    method: GET
    url: "/api/users"
    # Logger automatically logs request and response
```

### Error Hints

When errors occur, the logger provides helpful hints:

```
ERROR: builtins.KeyError: 'email'
Hint: Missing required key in response data. Check API documentation.
```

### Custom Error Hints

Add custom error hints in your configuration:

```python
logger = get_logger()

# Add custom hint
logger.error_hint_subs.append([
    "MyCustomError",  # Exception type contains
    "specific message",  # Exception value contains
    "This is your custom hint"  # Hint to display
])
```

---

## Datalake Metrics

Post test metrics to analytics platform:

```python
import datetime

logger = get_logger()

start_time = datetime.datetime.now()

# ... run tests ...

logger.datalake_post(
    test_name="Login Flow Test",
    product="Smart Home Hub",
    product_category="Automation",
    mac_address="00:11:22:33:44:55",
    time_savings=5.0,  # minutes saved
    start_time=start_time,
    console="Test passed\nAll assertions successful",
    run_url="https://testrail.example.com/run/123",
    success=True,
    type="easybdd"
)
```

**Metrics Tracked:**

- Test name and type
- Product information
- Start/end times
- Total execution time
- Success/failure status
- Time savings estimate
- Console output
- Links to test runs

---

## Advanced Features

### Decorator for Function Logging

```python
logger = get_logger()

@logger.wrapper
def my_test_function(param1, param2, nested=False):
    # Function automatically logs start and end
    return "result"
```

**Output:**

```
------------------------- Step 1 -------------------------
<-- my_test_function('value1', 'value2')
--> Response: result
```

### Limited Traceback

Only shows stack frames from your project:

```python
# Full traceback (100 lines)
Traceback (most recent call last):
  File "/usr/lib/python3.12/site-packages/...", line 123
  ...
  File "/your/project/easybdd/core/runner.py", line 456, in execute_step
    service.click_element(selector)

# Limited traceback (relevant only)
  File "/your/project/easybdd/core/runner.py", line 456, in execute_step
```

### Console to File

Save all console output to file:

```python
logger = get_logger()
logger.console2file()

# All logs now also saved to reports/artifacts/console.log
```

---

## Error Hint Customization

### Rule-Based Hints

```python
error_hints = [
    # [exception_type_contains, exception_value_contains, hint]
    ["ConnectionError", "timeout", "Check network and API endpoint"],
    ["HTTPError", "401", "Authentication failed - check credentials"],
    ["HTTPError", "404", "Resource not found - verify URL"],
    ["JSONDecodeError", "", "Invalid JSON response from API"],
    ["KeyError", "token", "Missing authentication token in response"],
    ["AssertionError", "expected 200", "API returned unexpected status code"],
]

logger = get_logger()
logger.error_hint_subs = error_hints
```

### AI-Powered Hints

Enable GPT-3.5 for automatic error explanations:

```bash
export OPENAI_API_KEY="your-key"
```

```python
logger = get_logger()

# AI hint will be generated automatically
try:
    complex_function_that_fails()
except Exception as e:
    logger.exception("Complex error occurred")
    # Output: "Hint: Missing required parameter in API call. (gpt)"
```

---

## Integration with Test Runner

The logger is automatically integrated:

```python
from easybdd.core.runner import TestRunner

runner = TestRunner(config_path="config/framework.yaml")

# Logger automatically tracks:
# - Test start/end times
# - Step execution
# - Errors and exceptions
# - Performance metrics
```

**Test Output:**

```
------------------------- Step 1 -------------------------
<-- API request: GET /api/users
📡 GET /api/users -> 200
Stored response as: users_response
✅ Step 1 completed successfully

------------------------- Step 2 -------------------------
<-- Assert: len(users_response['data']) > 0
✓ Assertion passed
✅ Step 2 completed successfully

Test Results: 1 passed, 0 failed
Execution time: 2.34 seconds

📊 HTML Report generated: reports/test_report_20251122_233000.html
```

---

## Best Practices

### 1. Use Appropriate Log Levels

```python
logger.debug("Detailed variable values for debugging")
logger.info("Test step completed")
logger.warning("Non-critical issue detected")
logger.error("Test failed")
```

### 2. Disable Posting in Development

```yaml
logging:
  post_results: false  # No Datalake posts during development
```

### 3. Add Context to Errors

```python
try:
    api_call()
except Exception as e:
    logger.error(f"API call failed for user {user_id}: {e}")
```

### 4. Use Error Hints Strategically

Focus on common errors your team encounters:

```python
error_hints = [
    ["TimeoutError", "selenium", "Element not found - check selector or wait time"],
    ["StaleElementReferenceException", "", "DOM changed - re-find element"],
    ["NoSuchElementException", "", "Element not present - verify page loaded"],
]
```

### 5. Monitor Datalake Metrics

Track time savings and success rates:

```python
# Estimate time saved vs manual testing
time_savings = 10  # minutes

logger.datalake_post(
    test_name=test.name,
    time_savings=time_savings,
    success=(test.result == "passed"),
    ...
)
```

---

## Troubleshooting

### Logger Not Working

```python
# Check if loguru is installed
pip list | grep loguru

# Install if missing
pip install loguru
```

### Datalake Posts Failing

```python
# Check configuration
logger = get_logger()
logger.debug("Datalake URL: " + os.environ.get('DATALAKE_URL'))

# Enable debug logging
logger.post_results = True
```

### GPT Hints Not Working

```bash
# Verify OpenAI key
echo $OPENAI_API_KEY

# Test API access
python -c "from openai import OpenAI; client = OpenAI(); print('OK')"
```

---

## Examples

### Complete Test with Logging

```yaml
name: "API Test with Logging"
description: "Demonstrates datalake logger integration"

variables:
  api_url: "https://api.example.com"
  product: "Smart Hub"
  mac_address: "00:11:22:33:44:55"

steps:
  - action: API request
    method: GET
    url: "${api_url}/devices"
    store_response: "devices"
  
  - action: Assert
    expression: "len(devices['data']) > 0"
    message: "Should have devices"
  
  # Logger automatically:
  # - Logs each step
  # - Tracks timing
  # - Submits metrics to datalake
```

### Custom Logging in Python

```python
from easybdd.core.datalake_logger import get_logger
import datetime

logger = get_logger(
    artifact_path="reports/my_artifacts",
    post_results=True
)

# Add custom error hints
logger.error_hint_subs = [
    ["ConnectionError", "", "Network issue - check VPN/firewall"],
    ["Timeout", "selenium", "Page load timeout - increase wait time"],
]

# Run test with logging
start_time = datetime.datetime.now()

try:
    # Your test code
    logger.info("Starting test execution")
    result = run_my_test()
    logger.info(f"Test completed: {result}")
    success = True
except Exception as e:
    logger.exception("Test failed")
    success = False

# Post to datalake
logger.datalake_post(
    test_name="My Custom Test",
    product="Smart Hub",
    product_category="Automation",
    mac_address="00:11:22:33:44:55",
    time_savings=8.0,
    start_time=start_time,
    console=logger.artifact_path / "console.log",
    run_url="https://example.com/test/123",
    success=success
)
```

---

## Summary

The Datalake Logger provides enterprise-grade logging:

| Feature | Benefit |
|---------|---------|
| **Loguru Integration** | Beautiful, colorful console output |
| **Error Hints** | Quick problem diagnosis |
| **Datalake Metrics** | Track performance and ROI |
| **Limited Tracebacks** | Focus on relevant code |

**Next Steps:**
- Configure environment variables
- Add custom error hints
- Track metrics in datalake
- Review [Configuration Guide](BROWSER_CONFIG.md)
