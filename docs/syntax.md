# Syntax Reference Guide

## 📋 YAML Test Structure

### Required Fields

```yaml
name: "Test Name"           # String: Human-readable test name
steps:                      # Array: List of test actions
  - action: "Action Name"
    parameter: "value"
```

### Optional Fields

```yaml
description: "Test description"  # String: What the test does
tags: ["tag1", "tag2"]          # Array: Tags for test organization
variables: {}                   # Object: Test variables
data: []                       # Array: Data-driven test data
setup: []                      # Array: Setup steps
cleanup: []                    # Array: Cleanup steps
async_execution: false         # Boolean: Enable async execution
max_workers: 1                 # Number: Concurrent workers
```

## 🔧 Variable Syntax

### Variable Definition
```yaml
variables:
  username: "admin"
  password: "secret123"
  base_url: "https://api.example.com"
  timeout: 5000
```

### Variable Usage
Use `${variable_name}` syntax anywhere in your test:

```yaml
steps:
  - action: Open browser
    url: ${base_url}/login
  
  - action: Fill form field
    field: "#username"
    value: ${username}
  
  - action: Wait for element
    timeout: ${timeout}
```

### Variable Scope
Variables are resolved in this order:
1. Data iteration variables (highest priority)
2. Test-level variables
3. Global configuration variables

## 📊 Data-Driven Testing Syntax

### Simple Data Array
```yaml
data:
  - username: "user1"
    password: "pass1"
  - username: "user2"
    password: "pass2"
```

### Complex Data Sets
```yaml
data:
  - endpoint: "api/users"
    method: "GET"
    expected_status: 200
    expected_field: "id"
  
  - endpoint: "api/users/123"
    method: "DELETE"
    expected_status: 404
    expected_field: "error"
```

### Async Execution
```yaml
# Run data iterations concurrently
async_execution: true
max_workers: 3

data:
  - device_id: "device1"
  - device_id: "device2" 
  - device_id: "device3"
```

## 🎭 Step Action Syntax

### Basic Step Structure
```yaml
- action: "Action Name"           # Required: Action to perform
  parameter1: "value"             # Parameters vary by action
  parameter2: 123
  description: "What this does"   # Optional: Step description
```

### Browser Actions
```yaml
# Open browser
- action: Open browser
  url: "https://example.com"

# Click element
- action: Click element
  selector: "#submit-button"

# Fill form field
- action: Fill form field
  field: "[name='email']"
  value: "user@example.com"

# Take screenshot
- action: Take screenshot
  name: "login-page"

# Wait for element
- action: Wait for element
  selector: ".loading"
  state: "hidden"
  timeout: 10000

# Verify text
- action: Verify text
  text: "Welcome"

# Navigate
- action: Navigate back
- action: Navigate forward
```

### Utility Actions
```yaml
# Wait/pause
- action: Wait
  time: 2

# API request
- action: API request
  method: "GET"
  url: "/api/users"
  headers:
    Authorization: "Bearer ${token}"
```

## 📝 Comments and Documentation

### YAML Comments
```yaml
# This is a comment
name: Test Name  # Inline comment

# Multi-line comment explaining
# the purpose of this section
steps:
  - action: Open browser
    url: ${base_url}
    # This step opens the main page
```

### Step Descriptions
```yaml
steps:
  - action: Open browser
    url: ${login_url}
    description: Navigate to the login page
    
  - action: Fill form field
    field: "#username"
    value: ${username}
    description: Enter the username credential
```

## 🎯 Selector Syntax

### CSS Selectors
```yaml
selector: "#element-id"              # ID selector
selector: ".class-name"              # Class selector
selector: "[data-testid='submit']"   # Attribute selector
selector: "button.primary"           # Element + class
selector: "form input[type='email']" # Nested selectors
```

### Playwright Selectors
```yaml
selector: "text=Click me"                    # Text content
selector: "button:has-text('Submit')"        # Element with text
selector: "[role='button'][name='save']"     # ARIA selectors
selector: "input:near(:text('Email'))"       # Proximity selectors
```

### XPath Selectors
```yaml
selector: "//button[@id='submit']"           # XPath syntax
selector: "//div[contains(@class, 'error')]" # XPath functions
```

## ⚙️ Configuration Syntax

### Test-Level Configuration
```yaml
# Execution mode
async_execution: true     # Run data iterations concurrently
max_workers: 5           # Number of concurrent workers

# Timeouts
default_timeout: 10000   # Default element timeout (ms)
page_timeout: 30000      # Page load timeout (ms)

# Browser settings
headless: false          # Show browser during test
browser: "chromium"      # Browser engine
```

### File Organization
```yaml
# Reference external files
data_source: "./data/users.csv"     # CSV data source
shared_steps: "./shared/login.yaml" # Shared step definitions
```

## 🏗 Advanced Syntax Patterns

### Conditional Logic
```yaml
# Use tags for conditional execution
tags: ["smoke", "regression", "api"]

# Environment-specific variables
variables:
  base_url: "${ENV_URL:https://staging.example.com}"
  api_key: "${API_KEY:default-key}"
```

### Dynamic Content
```yaml
# Timestamp in screenshots
- action: Take screenshot
  name: "test-${timestamp}"

# Random data generation (if supported)
variables:
  random_email: "${random.email}"
  uuid: "${random.uuid}"
```

### Error Handling
```yaml
# Continue on failure
- action: Click element
  selector: "#optional-button"
  continue_on_error: true

# Retry logic
- action: Wait for element
  selector: ".dynamic-content"
  timeout: 30000
  retry_count: 3
```

## 📚 Best Practices

### Naming Conventions
```yaml
# Use descriptive names
name: "User Registration with Email Verification"

# Use snake_case for variables
variables:
  user_email: "test@example.com"
  max_retry_count: 3

# Use kebab-case for file names
# user-registration-test.yaml
```

### Structure Organization
```yaml
# Group related variables
variables:
  # URLs
  login_url: "${base_url}/login"
  dashboard_url: "${base_url}/dashboard"
  
  # Credentials
  admin_username: "admin"
  admin_password: "password"
  
  # Timeouts
  short_timeout: 2000
  long_timeout: 10000
```

### Documentation
```yaml
name: "User Login Test"
description: |
  Tests the user login functionality including:
  - Valid credential authentication
  - Error message display for invalid credentials
  - Redirect to dashboard after successful login
  
tags: ["authentication", "critical", "smoke"]
```

---

*For more examples, see the [Examples Directory](./examples/)*