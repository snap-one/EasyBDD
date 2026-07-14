# Advanced Features Guide

Advanced capabilities of the Easy BDD Testing Framework.

## ⚡ Async Execution

### Understanding Async vs Sequential

**Sequential Execution (Default):**
- Tests run one after another
- Safer for shared resources
- Easier to debug
- Takes longer total time

**Async Execution:**
- Multiple tests run simultaneously  
- Faster overall execution
- Better resource utilization
- More complex debugging

### Enabling Async Execution

```yaml
name: Concurrent Test
description: Run multiple iterations simultaneously

# Enable async execution
async_execution: true
max_workers: 3        # Number of concurrent workers

data:
  - item: "item1"
  - item: "item2"
  - item: "item3"

steps:
  - action: Open browser
    url: ${base_url}/${item}
  - action: Take screenshot
    name: ${item}-result
```

### Performance Comparison

```yaml
# Sequential: 30s + 30s + 30s = 90 seconds total
async_execution: false
max_workers: 1

# Async: max(30s, 30s, 30s) = 30 seconds total  
async_execution: true
max_workers: 3
```

### Optimal Worker Configuration

```yaml
# For browser tests (memory intensive)
max_workers: 3

# For API tests (I/O intensive)
max_workers: 10

# For device tests (hardware limited)
max_workers: 1

# For mixed workloads
max_workers: 5
```

## 🎭 Setup and Cleanup Phases

### Three-Phase Test Structure

1. **Setup Phase** - Prepare test environment
2. **Main Test Phase** - Execute core test logic
3. **Cleanup Phase** - Restore environment state

```yaml
name: Complete Test with All Phases

setup:
  - action: Reset database
  - action: Open browser
    url: ${admin_url}
  - action: Take screenshot
    name: "environment-ready"

steps:
  - action: Execute main test logic
  - action: Verify results

cleanup:
  - action: Logout user
  - action: Clear test data
  - action: Take screenshot
    name: "cleanup-complete"
```

### Setup Phase Best Practices

```yaml
setup:
  # Environment preparation
  - action: API request
    url: "/api/test/reset"
    method: "POST"
    description: "Reset test environment"
  
  # Data seeding
  - action: API request
    url: "/api/test/seed"
    method: "POST"
    body: '{"users": 5, "products": 10}'
    description: "Create test data"
  
  # System stabilization
  - action: Wait
    seconds: 3
    description: "Allow system to stabilize"
  
  # Initial state capture
  - action: Take screenshot
    name: "setup-complete-${test_id}"
```

### Cleanup Phase Best Practices

```yaml
cleanup:
  # State capture
  - action: Take screenshot
    name: "pre-cleanup-${test_id}"
  
  # Navigation cleanup
  - action: Navigate back
    description: "Return to safe state"
  
  # Data cleanup
  - action: API request
    url: "/api/test/cleanup"
    method: "DELETE"
    description: "Remove test data"
  
  # Final verification
  - action: Take screenshot
    name: "cleanup-complete-${test_id}"
  
  # Cooldown period
  - action: Wait
    seconds: 1
    description: "Brief pause before next test"
```

### Error Handling in Phases

```yaml
# Setup failures don't stop main test
setup:
  - action: Optional setup step
    continue_on_error: true

# Cleanup always runs, even on test failure
cleanup:
  - action: Critical cleanup
    # This will run even if main test fails
```

## 🔄 Variable Management

### Variable Priority Order

1. **Data iteration variables** (highest priority)
2. **Test-level variables**
3. **Environment variables**
4. **Global configuration variables**

```yaml
variables:
  username: "test_user"      # Test level
  
data:
  - username: "admin_user"   # Data level (overrides test level)
    password: "admin_pass"
  - username: "regular_user"
    password: "user_pass"
```

### Dynamic Variable Generation

There are no built-in `${timestamp}`/`${uuid}`/`${random}` variables — generate
dynamic values at runtime with `eval.exec`. Any variable assigned in the code
block is persisted and available to later steps via `${var_name}`:

```yaml
steps:
  - eval.exec:
      code: "import time, uuid; ts = int(time.time()); run_uuid = str(uuid.uuid4())"

  - action: Take screenshot
    name: "test-${ts}-${run_uuid}"
```

### Environment-Specific Variables

```yaml
variables:
  # Read from OS environment variables (no built-in default-value syntax —
  # the placeholder is left unresolved if the variable isn't set)
  base_url: "${env.BASE_URL}"
  api_key: "${env.API_KEY}"
  timeout: "${env.TIMEOUT}"

  # Conditional variables
  debug_mode: "${env.DEBUG}"
  log_level: "${env.LOG_LEVEL}"
```

## 📊 Advanced Data Patterns

### Complex Data Structures

```yaml
data:
  - test_scenario: "admin_workflow"
    user:
      username: "admin@company.com"
      password: "admin123"
      role: "administrator"
      permissions: ["read", "write", "delete"]
    expected_results:
      dashboard_title: "Admin Dashboard"
      menu_items: ["Users", "Settings", "Reports"]
      action_buttons: ["Create", "Edit", "Delete"]
    test_data:
      create_user:
        name: "Test User"
        email: "newuser@test.com"
      
  - test_scenario: "user_workflow"  
    user:
      username: "user@company.com"
      password: "user123"
      role: "standard_user"
      permissions: ["read"]
    expected_results:
      dashboard_title: "User Dashboard"
      menu_items: ["Profile", "Reports"]
      action_buttons: ["View"]
```

### Conditional Test Logic

```yaml
data:
  - test_type: "positive"
    input_valid: true
    username: "valid@example.com"
    password: "ValidPass123!"
    expected_outcome: "success"
    verify_text: "Welcome"
    
  - test_type: "negative_email"
    input_valid: false
    username: "invalid-email"
    password: "ValidPass123!"
    expected_outcome: "validation_error"
    verify_text: "Please enter a valid email"
    
  - test_type: "negative_password"
    input_valid: false
    username: "valid@example.com"
    password: "weak"
    expected_outcome: "validation_error"
    verify_text: "Password must be at least 8 characters"
```

### Data-Driven Browser Configuration

```yaml
data:
  - browser: "chromium"
    viewport: "1920x1080"
    device: "desktop"
    user_agent: "desktop"
    
  - browser: "webkit"
    viewport: "375x667" 
    device: "iPhone"
    user_agent: "mobile"
    
  - browser: "firefox"
    viewport: "1366x768"
    device: "laptop"
    user_agent: "desktop"

steps:
  - action: Configure browser
    browser: ${browser}
    viewport: ${viewport}
    
  - action: Open browser
    url: ${app_url}
    
  - action: Take screenshot
    name: "${device}-${browser}-view"
```

## 🎯 Advanced Selectors

### Playwright-Specific Selectors

```yaml
steps:
  # Text content selectors
  - action: Click element
    selector: "text=Click me"
  
  # Text with wildcards
  - action: Click element
    selector: "text=/Click.*me/"
  
  # Element with specific text
  - action: Click element
    selector: "button:has-text('Submit')"
  
  # Proximity selectors
  - action: Fill form field
    field: "input:near(:text('Email'))"
    value: "user@example.com"
  
  # Nth element
  - action: Click element
    selector: "button >> nth=0"  # First button
  
  # Chained selectors
  - action: Click element
    selector: ".modal >> text=OK"
```

### Robust Selector Strategies

```yaml
# Priority order for selectors:
# 1. Data attributes (most stable)
selector: "[data-testid='submit-button']"

# 2. ARIA attributes (semantic)
selector: "[role='button'][aria-label='Submit']"

# 3. Text content (readable)
selector: "button:has-text('Submit')"

# 4. Stable CSS classes
selector: ".btn.btn-primary"

# 5. IDs (if stable)
selector: "#submit-btn"

# Avoid:
# - Generic tag selectors: "div > div > button"
# - Auto-generated classes: ".css-abc123"
# - Position-based: "button:nth-child(3)"
```

## 🔧 Advanced Configuration

### Environment-Specific Configuration

Create `config/environments/staging.yaml`:
```yaml
browser:
  headless: true
  slowMo: 0
  
execution:
  default_timeout: 10000
  retry_count: 3
  
variables:
  base_url: "https://staging.example.com"
  api_url: "https://api-staging.example.com"
```

Create `config/environments/production.yaml`:
```yaml
browser:
  headless: true
  slowMo: 500  # Slower for production
  
execution:
  default_timeout: 15000
  retry_count: 5
  
variables:
  base_url: "https://example.com"
  api_url: "https://api.example.com"
```

### Dynamic Configuration Loading

```bash
# Load environment-specific config
export TEST_ENV=staging
python -m easybdd run tests/cases/test.yaml

# Framework automatically loads:
# config/environments/${TEST_ENV}.yaml
```

### Runtime Configuration Override

```bash
# Override config at runtime
python -m easybdd run tests/cases/test.yaml \
  --config browser.headless=false \
  --config execution.default_timeout=30000
```

## 🚀 Performance Optimization

### Parallel Execution Strategies

```yaml
# Test-level parallelization
async_execution: true
max_workers: 3

# File-level parallelization (future)
# Run multiple test files simultaneously
```

### Resource Management

```yaml
# Browser reuse strategy
browser:
  reuse_context: true     # Reuse browser contexts
  max_contexts: 5         # Limit concurrent contexts
  
# Memory management
execution:
  cleanup_interval: 10    # Clean up every 10 tests
  max_memory_mb: 2048     # Memory limit per worker
```

### Caching Strategies

```yaml
# Cache static resources
browser:
  cache_strategy: "aggressive"
  cache_dir: ".cache/browser"
  
# Reuse authentication
auth:
  cache_tokens: true
  cache_duration: 3600    # 1 hour
```

## 🎨 Custom Extensions

### Custom Actions (Future)

```yaml
# Define custom action
custom_actions:
  login_user:
    description: "Complete user login flow"
    parameters: ["username", "password"]
    steps:
      - action: Fill form field
        field: "[name='username']"
        value: "${username}"
      - action: Fill form field
        field: "[name='password']"
        value: "${password}"
      - action: Click element
        selector: "[type='submit']"

# Use custom action
steps:
  - action: login_user
    username: "${user_email}"
    password: "${user_password}"
```

### Shared Step Libraries (Future)

```yaml
# Reference shared steps
shared_steps: "./shared/common_steps.yaml"

steps:
  - shared_step: "login_as_admin"
    parameters:
      admin_url: "${app_url}/admin"
      
  - action: Take screenshot
    name: "logged-in-state"
    
  - shared_step: "logout_user"
```

## 📈 Reporting and Metrics

### Advanced Reporting

```yaml
# Enable detailed reporting
reporting:
  detailed_steps: true
  timing_metrics: true
  memory_usage: true
  screenshot_on_failure: true
  video_recording: true
  
# Custom report formats
report_formats: ["html", "json", "junit"]
export_paths:
  html: "reports/index.html"
  json: "reports/results.json"
  junit: "reports/junit.xml"
```

### Performance Metrics

```yaml
# Automatic performance tracking
metrics:
  page_load_time: true
  action_duration: true
  memory_usage: true
  cpu_usage: true
  
# Performance thresholds
thresholds:
  page_load_max: 5000     # 5 seconds
  action_timeout: 10000   # 10 seconds
  memory_limit: 1024      # 1GB
```

---

*These advanced features provide enterprise-level testing capabilities while maintaining the simplicity of YAML-based test definitions.*