# Syntax Reference Guide

## YAML Test Structure

### Required Fields

```
name: "Test Name"
steps:
- service.verb:
param: value
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

---

## TestRail Preconditions Format

Steps are written directly in the **Preconditions** field of a TestRail `Feature:` case. Parameters are **flush-left** — the runner re-indents them automatically. No manual alignment needed.

### Flush-left format (TestRail Preconditions)

```
# 1. Open browser
- browser.open:
url: ${base_url}
# 2. Fill username
- browser.fill:
selector: input[type="text"]
value: ${username}
# 3. Submit
- browser.click:
role: button
name: Log In
# 4. Assert login succeeded
- test.assert:
value: ${last_status_code}
equals: 200
```

### Flow-style format (recommended for complex params in TestRail)

Single-line flow style avoids indentation issues in TestRail's rich-text editor:

```
- api.request: {method: POST, url: "${api_url}/system/login", body: {user: "${username}", password: "${password}"}}
- test.assert: {value: ${last_status_code}, equals: 200}
- api.request: {method: GET, url: "${api_url}/system/status", headers: {Authorization: "Bearer ${token}"}}
- test.assert: {expression: "'systemInfo' in last_json"}
```

### With variables block

```
variables:
base_url: https://staging.example.com

steps:
- browser.open:
url: ${base_url}/login
- browser.fill:
selector: input[type="text"]
value: ${username}
- test.assert:
value: ${last_status_code}
equals: 200
```

---

## Variable Syntax

### Variable Definition

```
variables:
username: "admin"
password: "secret123"
base_url: "https://api.example.com"
timeout: 30
```

### Variable Usage

Use `${variable_name}` syntax anywhere in your test:

```
steps:
- browser.open:
url: ${base_url}/login
- browser.fill:
selector: "#username"
value: ${username}
- browser.wait_for:
selector: ".dashboard"
timeout: ${timeout}
```

### Variable Scope

Variables are resolved in this order:
1. Data iteration variables (highest priority)
2. Test-level variables
3. Global configuration variables

---

## Data-Driven Testing Syntax

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
- endpoint: "/api/users"
  method: "GET"
  expected_status: 200
- endpoint: "/api/users/999"
  method: "GET"
  expected_status: 404
```

### Async Execution

```yaml
async_execution: true
max_workers: 3

data:
- device_id: "device1"
- device_id: "device2"
- device_id: "device3"
```

---

## Step Action Syntax

### Basic Step Structure

```
# Preferred — flush-left params
- service.verb:
param1: value
param2: 123

# Flow style — single line (great for TestRail)
- service.verb: {param1: value, param2: 123}
```

### Browser Actions

```
# Open browser
- browser.open:
url: "https://example.com"

# Click element by CSS selector
- browser.click:
selector: "#submit-button"

# Click by role and name (more resilient — preferred)
- browser.click:
role: button
name: Submit

# Fill form field by selector
- browser.fill:
selector: "[name='email']"
value: "user@example.com"

# Fill by label text
- browser.fill:
label: Username
value: ${username}

# Take screenshot
- browser.screenshot:
name: "login-page"

# Wait for element
- browser.wait_for:
selector: ".loading"
timeout: 10

# Verify text on page
- browser.verify_text:
selector: ".page-title"
text: "Welcome"

# Verify element visibility
- browser.verify_element:
selector: ".dashboard"
visible: true

# Navigate
- browser.back: {}
- browser.forward: {}
- browser.refresh: {}
- browser.close: {}
```

### API Actions

```
# GET request
- api.get:
url: ${base_url}/api/users
headers: {Authorization: "Bearer ${token}"}
store_as: users_response

# POST request
- api.post:
url: ${base_url}/api/login
body: {username: "${username}", password: "${password}"}
store_as: login_response

# PUT request
- api.put:
url: ${base_url}/api/devices/${device_id}
body: {status: active}
headers: {Authorization: "Bearer ${token}"}

# DELETE request
- api.delete:
url: ${base_url}/api/sessions/${session_id}
headers: {Authorization: "Bearer ${token}"}
expected_status: 204

# Generic request (use when method is a variable)
- api.request:
method: GET
url: ${base_url}/api/status
headers: {Authorization: "Bearer ${token}"}
store_as: status_response
```

After any API step: `${last_status_code}` holds the HTTP status, `${last_response}` the raw body, and `${last_response_dict}` the parsed JSON.

### Assertion Actions

```
# Equality check
- test.assert:
value: ${last_status_code}
equals: 200

# Contains substring
- test.assert:
value: ${response_body}
contains: "access_token"

# Does not contain
- test.assert:
value: ${device.status}
not_contains: error

# Non-empty
- test.assert:
value: ${fw_version}
not_empty: true

# Membership check
- test.assert:
value: ${last_status_code}
in: [200, 201, 204]

# Greater than
- test.assert:
value: ${process_count}
greater_than: 0

# Expression-based assertion
- test.assert:
expression: login_response.data.restful_res.errCode == 0
message: Login should return errCode 0

# JSON schema validation
- test.assert_schema:
value: ${device}
schema: {type: object, required: [id, status], properties: {id: {type: integer}, status: {type: string}}}

# Soft assertion (test continues; failures collected at end)
- test.assert:
value: ${metric}
greater_than: 0
soft: true

# Flush soft assertions
- test.check_assertions: {}
```

### Utility Actions

```
# Sleep / wait
- test.sleep:
seconds: 30

# Log a message
- test.log:
message: "Waiting for device ${device_ip} to reboot..."

# Extract a nested value from a response
- test.extract:
from: ${login_response}
path: data.access_token
store_as: token

# Run a local YAML test as a sub-step
- test.run:
path: tests/cases/shared/login.yaml
```

### SSH Actions

```
- ssh.connect:
host: ${device_ip}
username: ${device_user}
password: ${device_pass}
timeout: 30
retry: 3
retry_delay: 10

- ssh.command:
command: cat /etc/firmware_version
store_as: fw_version

- ssh.disconnect: {}
```

### Eval Actions

```
# Extract nested value with Python expression
- eval.run:
expression: "last_json.restful_res.token"
store_as: token

# Multi-line Python
- eval.exec:
code: |
  token = last_response_dict['data']['access_token']
  expiry = last_response_dict['data']['expires_in']
```

---

## Comments and Documentation

```
# This is a comment — appears as a label in test output
steps:
# 1. Open the login page
- browser.open:
url: ${base_url}
# 2. Enter credentials
- browser.fill:
selector: "#username"
value: ${username}
```

Step number comments (`# N. description`) are ignored by the parser and appear as human-readable labels in output.

---

## Selector Syntax

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
selector: "iframe >> #firmware-input"        # Inside an iframe
```

### XPath Selectors

```yaml
selector: "//button[@id='submit']"           # XPath syntax
selector: "//div[contains(@class, 'error')]" # XPath functions
```

---

## Configuration Syntax

```yaml
async_execution: true     # Run data iterations concurrently
max_workers: 5            # Number of concurrent workers
headless: false           # Show browser during test
browser: "chromium"       # Browser engine
slow_mo: 1000             # Add 1000ms delay between actions (debug)
```

---

## Control Flow Syntax

### Conditional (if / then / else)

```
- condition: "current_version != target_version"
then:
- browser.upload:
  selector: "#firmware-input"
  file_path: Firmware/${firmware_file}
- browser.click:
  role: button
  name: Upgrade
else:
- test.log:
  message: "Firmware already at target version — skipping"
```

### For Each Loop

```
- for_each: [1, 10, 30, 60]
loop_var: wait_seconds
steps:
- test.sleep:
  seconds: ${wait_seconds}
- test.assert:
  value: ${device.status}
  equals: online
```

Loop over a list of dicts:

```
- for_each: [{mac: "D4:6A:91:29:0F:5A", product: "WB-800"}, {mac: "A8:3B:76:11:CC:22", product: "WB-250"}]
loop_var: device
steps:
- ssh.connect:
  host: ${device.mac}
  username: ${device_user}
  password: ${device_pass}
- test.log:
  message: "Connected to ${device.product}"
- ssh.disconnect: {}
```

### While Loop

```
- while: "device_state != 'ready'"
loop_limit: 30
steps:
- api.get:
  url: ${base_url}/api/status
  store_as: device_state
- test.sleep:
  seconds: 5
```

### Try / Except / Finally

```
- try:
- api.post:
  url: ${base_url}/api/reboot
except:
- test.log:
  message: "Reboot request failed — device may already be rebooting"
finally:
- test.sleep:
  seconds: 30
```

---

## Best Practices

### Use dot-notation for all actions

```
# Correct
- browser.click:
role: button
name: Save

# Deprecated — do not use
- action: Click element
  selector: ".save-btn"
```

### Naming Conventions

```yaml
name: "User Registration with Email Verification"

variables:
  user_email: "test@example.com"
  max_retry_count: 3
```

---

*For more examples, see the [Examples Directory](./examples.md)*
