# Troubleshooting Guide

Common issues and solutions for the Easy BDD Testing Framework.

## 🚨 Common Issues

### Installation Problems

#### Python Version Issues
**Problem:** Framework fails to install or run
```bash
ERROR: Python 3.7 is not supported
```

**Solution:**
```bash
# Check Python version
python --version

# Install Python 3.8+ if needed
# macOS with Homebrew:
brew install python@3.9

# Update PATH if necessary
export PATH="/usr/local/opt/python@3.9/bin:$PATH"

# Recreate virtual environment
rm -rf .venv
python3.9 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### Playwright Browser Installation
**Problem:** Browsers fail to install or launch
```bash
ERROR: Browser not found
```

**Solution:**
```bash
# Reinstall browsers
playwright uninstall --all
playwright install

# Install system dependencies (Linux)
sudo playwright install-deps

# Test browser installation
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    print('Browser launch successful')
    browser.close()
"
```

#### Permission Issues (macOS/Linux)
**Problem:** Permission denied errors
```bash
PermissionError: [Errno 13] Permission denied
```

**Solution:**
```bash
# Fix directory permissions
sudo chown -R $USER:$USER .
chmod +x .venv/bin/activate

# For global installations
sudo pip install --user -e .
```

### Test Execution Issues

#### Browser Launch Failures
**Problem:** Browser fails to start
```bash
ERROR: Could not start browser process
```

**Solutions:**
```bash
# 1. Run in headless mode
python -m easy_bdd run tests/cases/test.yaml

# 2. Try different browser
# Edit config/framework.yaml:
browser:
  type: "firefox"  # or "webkit"

# 3. Check system resources
free -m  # Linux
top      # macOS/Linux

# 4. Increase timeouts
# In test YAML:
variables:
  page_timeout: 60000
```

#### Element Not Found Errors
**Problem:** Elements cannot be located
```bash
ERROR: Element not found: #submit-button
```

**Solutions:**
```yaml
# 1. Use better selectors
# Instead of:
selector: "#submit-button"

# Try:
selector: "[data-testid='submit']"           # Data attributes
selector: "button:has-text('Submit')"        # Text content
selector: "[role='button'][aria-label='Submit']"  # ARIA

# 2. Add wait conditions
- action: Wait for element
  selector: "#submit-button"
  state: "visible"
  timeout: 10000

- action: Click element
  selector: "#submit-button"

# 3. Use alternative selectors in browser service
```

#### Timeout Issues
**Problem:** Tests timeout waiting for elements
```bash
ERROR: Timeout 5000ms exceeded
```

**Solutions:**
```yaml
# 1. Increase timeouts
- action: Wait for element
  selector: ".slow-loading-content"
  timeout: 30000  # 30 seconds

# 2. Wait for page state
- action: Wait for element
  selector: "body"
  state: "visible"

# 3. Add explicit waits
- action: Wait
  time: 3
  description: "Wait for page to stabilize"

# 4. Configure global timeouts
# In config/framework.yaml:
execution:
  default_timeout: 15000
```

### Data-Driven Test Issues

#### Variable Substitution Problems
**Problem:** Variables not being replaced
```yaml
# Shows: ${username} instead of actual value
```

**Solutions:**
```yaml
# 1. Check variable scope
variables:
  username: "testuser"  # Test level

data:
  - username: "user1"   # Data level (higher priority)

# 2. Verify syntax
url: ${base_url}/users/${user_id}  # Correct
url: $base_url/users/$user_id      # Incorrect

# 3. Escape special characters
password: "P@ssw0rd!"              # Correct
password: P@ssw0rd!                # May cause issues
```

#### Async Execution Problems
**Problem:** Async tests fail or interfere with each other
```bash
ERROR: Browser session conflict
```

**Solutions:**
```yaml
# 1. Reduce concurrent workers
async_execution: true
max_workers: 2  # Instead of 5

# 2. Add cleanup steps
cleanup:
  - action: Navigate back
  - action: Wait
    time: 1

# 3. Use sequential execution for debugging
async_execution: false

# 4. Isolate test data
data:
  - user_id: "user001"  # Unique IDs
    device_id: "dev001"
  - user_id: "user002"  # No conflicts
    device_id: "dev002"
```

## 🔧 Configuration Issues

### Framework Configuration Problems
**Problem:** Configuration not loading
```bash
ERROR: Config file not found
```

**Solutions:**
```bash
# 1. Create default config
mkdir -p config
cat > config/framework.yaml << EOF
browser:
  type: "chromium"
  headless: false
  timeout: 30000

execution:
  default_timeout: 5000
  retry_count: 3
EOF

# 2. Check file permissions
ls -la config/framework.yaml
chmod 644 config/framework.yaml

# 3. Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config/framework.yaml'))"
```

### Environment Variable Issues
**Problem:** Environment variables not loading
```bash
ERROR: Variable BASE_URL not found
```

**Solutions:**
```bash
# 1. Check .env file exists
ls -la .env

# 2. Load environment manually
export BASE_URL="https://staging.example.com"
python -m easy_bdd run tests/cases/test.yaml

# 3. Use default values in YAML
variables:
  base_url: "${BASE_URL:https://localhost:3000}"  # Default fallback
```

## 🐛 Debugging Techniques

### Enable Debug Logging
```yaml
# In config/framework.yaml
logging:
  level: "DEBUG"
  file: "logs/debug.log"
```

```bash
# Run with verbose output
python -m easy_bdd run tests/cases/test.yaml --verbose

# Check logs
tail -f logs/debug.log
```

### Take Debug Screenshots
```yaml
steps:
  - action: Open browser
    url: ${app_url}
    
  - action: Take screenshot
    name: "debug-page-loaded"
    
  - action: Fill form field
    field: "#username"
    value: ${username}
    
  - action: Take screenshot
    name: "debug-username-filled"
    
  - action: Click element
    selector: "#submit"
    
  - action: Take screenshot
    name: "debug-after-click"
```

### Slow Down Execution
```yaml
# In config/framework.yaml
browser:
  slowMo: 1000  # 1 second delay between actions

# Or use wait steps
steps:
  - action: Click element
    selector: "#button"
    
  - action: Wait
    time: 2
    description: "Debug pause"
```

### Interactive Debugging
```python
# Add breakpoint in test
import pdb; pdb.set_trace()

# Or use browser developer tools
# Set headless: false and add long waits
```

## 📊 Performance Issues

### Slow Test Execution
**Problem:** Tests take too long to run

**Solutions:**
```yaml
# 1. Use headless mode
# In config/framework.yaml:
browser:
  headless: true

# 2. Reduce timeouts for fast tests
execution:
  default_timeout: 3000  # Instead of 10000

# 3. Enable async execution
async_execution: true
max_workers: 3

# 4. Optimize selectors
selector: "[data-testid='submit']"  # Fast
# Instead of:
selector: "div > div > button"      # Slow
```

### Memory Issues
**Problem:** High memory usage or crashes
```bash
ERROR: Out of memory
```

**Solutions:**
```yaml
# 1. Reduce concurrent workers
max_workers: 2  # Instead of 5

# 2. Add cleanup steps
cleanup:
  - action: Navigate back
  
# 3. Close browsers between tests
# Framework handles this automatically

# 4. Monitor system resources
# Run: htop or Activity Monitor
```

## 🔍 Test Debugging Strategies

### Isolate Failing Tests
```bash
# Run single test
python -m easy_bdd run tests/cases/failing_test.yaml

# Run specific data iteration
# Edit YAML to include only failing data item

# Run with tags
python -m easy_bdd run tests/cases/ --tags debug
```

### Validate Test Structure
```bash
# Generate Gherkin only (validates syntax)
python -m easy_bdd generate tests/cases/test.yaml

# Dry run (parse without execution)
python -m easy_bdd run tests/cases/test.yaml --dry-run
```

### Check Browser State
```yaml
steps:
  - action: Take screenshot
    name: "current-page-state"
    
  # Check page source in screenshots folder
  # Look for JavaScript errors in browser console
```

## 🆘 Getting Help

### Collect Debug Information
```bash
# System information
python --version
pip list | grep -E "(playwright|easy-bdd)"
playwright --version

# Test execution with debug
python -m easy_bdd run tests/cases/test.yaml --verbose --debug

# Browser information
ls ~/.cache/ms-playwright/  # Linux/macOS
dir %USERPROFILE%\AppData\Local\ms-playwright\  # Windows
```

### Create Minimal Reproduction
```yaml
name: Debug Test
description: Minimal test to reproduce issue

steps:
  - action: Open browser
    url: "https://example.com"
    
  - action: Take screenshot
    name: "debug"
    
  - action: Verify text
    text: "Example Domain"
```

### Log Analysis
```bash
# Check framework logs
tail -n 50 logs/test.log

# Check system logs (macOS)
log show --predicate 'subsystem contains "python"' --last 1h

# Check system logs (Linux)
journalctl -u python --since "1 hour ago"
```

### Report Issues
When reporting issues, include:

1. **Environment details:**
   - OS and version
   - Python version
   - Framework version
   - Browser versions

2. **Test files:**
   - Minimal YAML test case
   - Configuration files
   - Error messages

3. **Logs:**
   - Framework logs
   - Browser console errors
   - System error messages

4. **Screenshots:**
   - Expected vs actual results
   - Error states

---

*If you can't resolve an issue, create a detailed bug report with the information above.*

---

## TestRail & Runner Gotchas

Issues discovered during live test-authoring and debugging sessions. Each item
lists the symptom, root cause, and the fix or workaround.

---

### `expression: True` in `test.assert` raises TypeError

**Error:**
```
TypeError: compile() arg 1 must be a string, bytes or AST object
```

**Root cause:** YAML bare `True` / `False` becomes a Python `bool`. The runner
passes the value to `compile()`, which requires a string.

**Solution:** Always quote expression values in YAML:
```yaml
# Wrong
- action: test.assert
  expression: True

# Correct
- action: test.assert
  expression: "True"

- action: test.assert
  expression: "status_code == 200"
```

---

### Method calls blocked in `test.assert` expressions

**Error:**
```
AssertionError: expression evaluation blocked: method calls not permitted
```

**Root cause:** The expression evaluator restricts `.method()` calls for security.

**Solution:** Use subscript (bracket) notation instead of method calls:
```yaml
# Wrong
expression: "payload.get('status')"

# Correct
expression: "payload['status'] == 'ok'"
```

---

### `store_as` param not working for `api.request`

**Symptom:** Variable appears undefined in later steps after using `store_as:` on
an `api.request` action.

**Root cause:** The runner was reading `params.get("store_response")` only. The
documented canonical name is `store_as`.

**Solution:** Fixed in the runner — both `store_as` and `store_response` now
work. Use `store_as:` going forward:
```yaml
- action: api.request
  method: GET
  url: ${api_base}/status
  store_as: api_response
```

---

### `aws.list_files` returns False / fails when no files match

**Symptom:** Step marked as failed even though "no files found yet" is expected.

**Root cause:** The handler returned `len(urls) > 0`, which evaluates to `False`
on an empty result — causing the step to register as a failure.

**Solution:** Fixed — the handler now always returns `True` and stores an empty
list `[]`. Assert on the list length in a separate `test.assert` step if needed:
```yaml
- action: aws.list_files
  bucket: my-bucket
  prefix: exports/
  store_as: found_files

- action: test.assert
  expression: "len(found_files) > 0"
  message: "Expected at least one exported file"
```

---

### `no_datalake: True` variable does not stop datalake posts

**Symptom:** Datalake results are posted even though `no_datalake: True` is set
in the test variables block.

**Root cause:** The runner only checked the CLI `--no-datalake` flag. Test-level
variables were never read for this setting.

**Solution:** Fixed in `runner.py` and `testrail_runner.py` — both now check the
`no_datalake` key in test variables and per-data-row variables. Set it at either
level:
```yaml
variables:
  no_datalake: True
```

---

### `folder_prefix` set to a Python list causes S3 API error

**Symptom:** S3 call fails with an error about an invalid prefix type.

**Root cause:** The `folder_prefix` parameter was set to a YAML list, but the S3
`list_objects` API requires a string prefix.

**Solution:** Use `discover_prefix: true` to let the framework resolve the prefix
dynamically, instead of passing a hard-coded list:
```yaml
# Wrong
folder_prefix:
  - exports/
  - archive/

# Correct
discover_prefix: true
```

---

### Teams notification fires even when no tests ran

**Symptom:** A Teams card is posted for a run where everything was skipped or blocked, causing noise.

**Root cause:** Earlier versions checked only whether the run completed, not whether any tests actually executed.

**Fix:** The notification is now suppressed when `(passed + failed) == 0`. If you are still not seeing notifications for runs where tests did execute, confirm that:

1. `TEAMS_WEBHOOK_URL` is set in the environment or `.env` file.
2. At least one test has a Passed or Failed result (not just Skipped/Blocked).
3. `no_teams: True` is not set in any Var: case in the run.

---

### `testrail-create-run` creates duplicate runs

**Symptom:** Running `testrail-create-run` twice for the same suite creates two identical open runs.

**Root cause:** The command does not check for existing open runs before creating a new one.

**Fix:** Use `--dry-run` to preview the runs that would be created before committing:

```bash
python -m easy_bdd testrail-create-run 77 52630 \
  --given-section "VPS" \
  --sections "Functions" "Firmware Resiliency" \
  --dry-run
```

If duplicate runs are already present, close or delete the extras manually in TestRail.

---

### `ovrc disconnect` fails with "requires server_url" or routes to connect handler

**Symptom:** An `ovrc disconnect` step errors out as if no server URL was
provided, or behaves like a connect step.

**Root cause:** The routing condition used `"connect" in action_lower`, which is
`True` for the string `"ovrc disconnect"` because `disconnect` contains the
substring `connect`. Disconnect steps were silently dispatched to the connect
handler.

**Solution:** Fixed — the connect branch now explicitly excludes disconnect:
```python
if "connect" in action_lower and "disconnect" not in action_lower:
```

No YAML changes are needed; existing test cases work correctly after the fix.