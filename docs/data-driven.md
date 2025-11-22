# Data-Driven Testing Guide

Learn how to run the same test with multiple data sets using Easy BDD's data-driven testing features.

## 🎯 Overview

Data-driven testing allows you to:
- Run the same test logic with different input values
- Test multiple user accounts, devices, or configurations
- Validate various scenarios efficiently
- Execute tests sequentially or concurrently

## 📊 Basic Data-Driven Test

### Simple Data Array
```yaml
name: Multi-User Login Test
description: Test login with different user accounts

variables:
  app_url: "https://app.example.com"

# Data array - each item is one test iteration
data:
  - username: "alice@example.com"
    password: "alice123"
    expected_name: "Alice Johnson"
  
  - username: "bob@example.com" 
    password: "bob456"
    expected_name: "Bob Smith"
  
  - username: "charlie@example.com"
    password: "charlie789"
    expected_name: "Charlie Brown"

steps:
  - action: Open browser
    url: ${app_url}/login
    
  - action: Fill form field
    field: "[name='email']"
    value: ${username}
    
  - action: Fill form field
    field: "[name='password']"
    value: ${password}
    
  - action: Click element
    selector: "[type='submit']"
    
  - action: Verify text
    text: ${expected_name}
```

**Result:** This test will run 3 times - once for each user.

## 🚀 Async vs Sequential Execution

### Sequential Execution (Default)
Tests run one after another:

```yaml
name: Sequential Device Test
async_execution: false  # Default setting
max_workers: 1

data:
  - device_id: "device-001"
  - device_id: "device-002" 
  - device_id: "device-003"

# Takes: 30s + 30s + 30s = 90 seconds total
```

### Async Execution (Concurrent)
Tests run simultaneously:

```yaml
name: Concurrent Device Test
async_execution: true     # Enable async
max_workers: 3           # Run up to 3 concurrent

data:
  - device_id: "device-001"
  - device_id: "device-002"
  - device_id: "device-003"

# Takes: max(30s, 30s, 30s) = 30 seconds total
```

## 🏗 Data Structure Examples

### Device Configuration Testing
```yaml
name: Multi-Device Configuration Test

variables:
  base_url: "http://admin.local"

data:
  - endpoint_id: "1204"
    device_name: "RX-D46A9121077B"
    expected_model: "B-900-MOIP-4K-RX"
    location: "Living Room"
  
  - endpoint_id: "1012"
    device_name: "RX-D46A9121E8C0" 
    expected_model: "B-900-MOIP-4K-RX"
    location: "Bedroom"
    
  - endpoint_id: "1156"
    device_name: "RX-D46A91272239"
    expected_model: "B-960-MOIP-4K-RX"
    location: "Kitchen"

steps:
  - action: Open browser
    url: ${base_url}/device/${endpoint_id}
    
  - action: Take screenshot
    name: ${device_name}-initial
    
  - action: Fill form field
    field: "[name='device_name']"
    value: ${device_name}
    
  - action: Fill form field
    field: "[name='location']"
    value: ${location}
    
  - action: Verify text
    text: ${expected_model}
```

### API Testing with Different Endpoints
```yaml
name: API Endpoint Validation

variables:
  api_base: "https://api.example.com"
  auth_token: "Bearer xyz123"

data:
  - endpoint: "/users"
    method: "GET"
    expected_status: 200
    expected_field: "users"
  
  - endpoint: "/users/123"
    method: "GET" 
    expected_status: 200
    expected_field: "id"
    
  - endpoint: "/users/999"
    method: "GET"
    expected_status: 404
    expected_field: "error"
    
  - endpoint: "/users"
    method: "POST"
    body: '{"name":"Test User"}'
    expected_status: 201
    expected_field: "id"

steps:
  - action: API request
    url: ${api_base}${endpoint}
    method: ${method}
    headers:
      Authorization: ${auth_token}
    body: ${body}
    
  - action: Verify status
    status: ${expected_status}
    
  - action: Verify field
    field: ${expected_field}
```

### Browser Testing Across Environments
```yaml
name: Cross-Environment Testing

data:
  - environment: "staging"
    base_url: "https://staging.example.com"
    username: "stage_user"
    password: "stage_pass"
    
  - environment: "production"
    base_url: "https://example.com"
    username: "prod_user"
    password: "prod_pass"
    
  - environment: "development"
    base_url: "http://localhost:3000"
    username: "dev_user"
    password: "dev_pass"

steps:
  - action: Open browser
    url: ${base_url}/admin
    
  - action: Take screenshot
    name: ${environment}-login-page
    
  - action: Fill form field
    field: "#username"
    value: ${username}
    
  - action: Fill form field
    field: "#password" 
    value: ${password}
    
  - action: Click element
    selector: "#login-button"
    
  - action: Take screenshot
    name: ${environment}-dashboard
```

## 🔧 Advanced Data Patterns

### Nested Data Structures
```yaml
data:
  - user_info:
      name: "John Doe"
      email: "john@example.com"
      role: "admin"
    settings:
      theme: "dark"
      notifications: true
    test_actions:
      - "login"
      - "change_theme"
      - "logout"
```

### Conditional Data
```yaml
data:
  - test_type: "positive"
    username: "valid_user"
    password: "valid_pass"
    should_succeed: true
    
  - test_type: "negative"
    username: "invalid_user"
    password: "wrong_pass"
    should_succeed: false
    expected_error: "Invalid credentials"
```

## 🎭 Setup and Cleanup with Data

### Per-Iteration Setup/Cleanup
Each data iteration gets its own setup and cleanup:

```yaml
name: Device Testing with Setup/Cleanup

data:
  - device_id: "DEV001"
    reset_needed: true
  - device_id: "DEV002"
    reset_needed: false

setup:
  - action: Take screenshot
    name: pre-test-${device_id}
    
  - action: Open browser
    url: ${admin_url}/devices
    
  - action: Wait
    time: 2

steps:
  - action: Click element
    selector: "[data-device='${device_id}']"
    
  - action: Take screenshot
    name: device-${device_id}-config

cleanup:
  - action: Take screenshot
    name: post-test-${device_id}
    
  - action: Navigate back
    
  - action: Wait
    time: 1
```

## ⚡ Performance Considerations

### Optimal Concurrency
```yaml
# For I/O heavy tests (web, API)
async_execution: true
max_workers: 5

# For CPU heavy tests
async_execution: true
max_workers: 2

# For resource-limited environments
async_execution: false
max_workers: 1
```

### Resource Management
```yaml
# Limit concurrent browser instances
async_execution: true
max_workers: 3  # Don't exceed system capacity

# Add delays for stability
cleanup:
  - action: Wait
    time: 1
    description: Cool-down period
```

## 📈 Execution Output Examples

### Sequential Output
```bash
Executing test 1/1: Multi-User Login Test
    Running 3 data iterations...

    === Data Iteration 1/3 ===
    Step 1: Open browser
    Step 2: Fill form field
    Step 3: Click element
    ✅ Data iteration 1 passed

    === Data Iteration 2/3 ===
    Step 1: Open browser
    Step 2: Fill form field 
    Step 3: Click element
    ✅ Data iteration 2 passed

    === Data Iteration 3/3 ===
    Step 1: Open browser
    Step 2: Fill form field
    Step 3: Click element
    ✅ Data iteration 3 passed
```

### Async Output
```bash
Executing test 1/1: Multi-Device Config Test
    Running 3 data iterations...
    ⚡ Running 3 iterations ASYNCHRONOUSLY (max 3 concurrent)...
    
    ⚙️  [Thread-001] Starting iteration 1...
    ⚙️  [Thread-002] Starting iteration 2...  
    ⚙️  [Thread-003] Starting iteration 3...
    
    ✅ [Thread-002] Iteration 2 PASSED (15.2s)
    ✅ [Thread-001] Iteration 1 PASSED (16.1s)
    ✅ [Thread-003] Iteration 3 PASSED (17.3s)

    📈 ASYNC EXECUTION SUMMARY:
       ✅ Passed: 3/3
       ❌ Failed: 0/3
       ⏱️  Avg time per iteration: 16.2s
       ⚡ Concurrency benefit: 2.8x speedup
```

## 🛡 Best Practices

### Data Organization
```yaml
# ✅ Good: Descriptive data names
data:
  - user_type: "admin"
    username: "admin@company.com"
    has_full_access: true
    
  - user_type: "regular"
    username: "user@company.com"
    has_full_access: false

# ❌ Avoid: Generic names
data:
  - item1: "value1"
    item2: "value2"
```

### Variable Naming
```yaml
# ✅ Good: Clear variable names
data:
  - device_serial_number: "ABC123"
    expected_firmware_version: "v2.1.0"
    configuration_timeout: 30

# ❌ Avoid: Unclear abbreviations
data:
  - dsn: "ABC123"
    fw: "v2.1.0"
    timeout: 30
```

### Error Handling
```yaml
# Include error scenarios in data
data:
  - test_case: "valid_login"
    username: "valid@example.com"
    password: "correct_password"
    should_succeed: true
    
  - test_case: "invalid_username"
    username: "invalid@example.com"
    password: "any_password"
    should_succeed: false
    expected_error: "User not found"
    
  - test_case: "wrong_password"
    username: "valid@example.com"
    password: "wrong_password"
    should_succeed: false
    expected_error: "Invalid password"
```

## 📂 External Data Sources (Future)

### CSV File Integration
```yaml
# Reference external CSV file
data_source: "./data/test_users.csv"

# CSV file: test_users.csv
# username,password,role,expected_dashboard
# alice@test.com,pass123,admin,Admin Dashboard
# bob@test.com,pass456,user,User Dashboard
```

### JSON File Integration
```yaml
# Reference external JSON file  
data_source: "./data/api_endpoints.json"

# JSON file structure:
# [
#   {
#     "endpoint": "/api/users",
#     "method": "GET", 
#     "expected_status": 200
#   }
# ]
```

---

*For more data-driven examples, see the [Examples Directory](./examples/)*