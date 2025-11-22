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