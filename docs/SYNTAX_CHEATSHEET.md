# Easy BDD Framework - Complete Syntax Cheat Sheet

**Quick Reference Guide for All Actions, Configurations, and Options**

---

## Table of Contents

1. [Test File Structure](#test-file-structure)
2. [Browser Actions](#browser-actions)
3. [API Actions](#api-actions)
4. [AWS S3 Actions](#aws-s3-actions)
5. [JSON-RPC WebSocket Actions](#json-rpc-websocket-actions)
6. [Test & Assertion Actions](#test--assertion-actions)
7. [Conditional Logic](#conditional-logic)
8. [Retry Configuration](#retry-configuration)
9. [Data-Driven Testing](#data-driven-testing)
10. [Variables](#variables)
11. [Configuration Options](#configuration-options)

---

## Test File Structure

### Minimal Test
```yaml
name: "Test Name"
steps:
  - action: browser.open
    url: "https://example.com"
```

### Complete Test Structure
```yaml
name: "Complete Test Example"
description: "Full test with all optional sections"
tags: ["smoke", "critical", "api"]

# Test configuration
browser:
  headless: false
  slow_mo: 1000
  timeout: 30000

# Variables
variables:
  base_url: "https://api.example.com"
  username: "testuser"
  password: "${SECURE_PASSWORD}"  # From environment

# Data-driven (optional)
data:
  - user_id: 1
  - user_id: 2

# Setup phase
setup:
  - action: browser.open
    url: "${base_url}/login"

# Main test steps
steps:
  - action: browser.fill
    field: "#username"
    value: "${username}"

# Cleanup phase
cleanup:
  - action: browser.close
```

---

## Browser Actions

### Navigation

#### browser.open / Open browser
Open browser and navigate to URL
```yaml
- action: browser.open
  url: "https://example.com"
  
# Old syntax (still supported)
- action: "Open browser"
  url: "https://example.com"
  browser: "chromium"  # chromium, firefox, webkit
```

#### browser.navigate / Navigate
Navigate to URL in existing browser
```yaml
- action: browser.navigate
  url: "https://example.com/page2"
```

#### browser.back / Navigate back
```yaml
- action: browser.back
```

#### browser.forward / Navigate forward
```yaml
- action: browser.forward
```

#### browser.refresh / Refresh browser
```yaml
- action: browser.refresh
```

#### browser.close / Close browser
```yaml
- action: browser.close
```

### Element Interaction

#### browser.click / Click element
```yaml
# By CSS selector
- action: browser.click
  selector: "#submit-btn"

# By text content
- action: browser.click
  text: "Submit"

# By button name
- action: browser.click
  button: "Log In"

# By role and name (Playwright native - recommended)
- action: browser.click
  role: "button"
  name: "Submit"
  exact: true  # Optional: exact name match

# Common roles:
# button, link, textbox, checkbox, radio, heading, listitem, img

# By placeholder
- action: browser.click
  placeholder: "Enter email"

# Inside iframe
- action: browser.click
  selector: "iframe >> #button-in-iframe"

# With options
- action: browser.click
  selector: "#element"
  force: true           # Force click even if hidden
  timeout: 5000         # Custom timeout in ms
  click_count: 2        # Double click
  button: "right"       # Right click
  modifiers: ["Shift"]  # With keyboard modifier
```

#### browser.fill / Fill form field
```yaml
# Simple fill
- action: browser.fill
  field: "#username"
  value: "john@example.com"

# By label
- action: browser.fill
  field: "input[aria-label='Email']"
  value: "test@example.com"

# By placeholder
- action: browser.fill
  field: "input[placeholder='Password']"
  value: "secret123"

# In iframe
- action: browser.fill
  field: "iframe >> input[name='field']"
  value: "value"

# With clear first
- action: browser.fill
  field: "#input"
  value: "new value"
  clear: true
```

#### browser.upload / Upload file
```yaml
# Simple upload
- action: browser.upload
  selector: "#file-input"
  file_path: "path/to/file.pdf"

# Upload in iframe (handles hidden inputs automatically)
- action: browser.upload
  selector: "iframe >> #file-input"
  file_path: "Firmware/${firmware_file}"

# Multiple files
- action: browser.upload
  selector: "#multi-file"
  file_path: ["file1.txt", "file2.txt"]
```

#### browser.select / Select option
```yaml
# By value
- action: browser.select
  selector: "#dropdown"
  value: "option1"

# By label
- action: browser.select
  selector: "#dropdown"
  label: "Option One"

# By index
- action: browser.select
  selector: "#dropdown"
  index: 0
```

#### browser.check / Check checkbox
```yaml
- action: browser.check
  selector: "#terms-checkbox"
```

#### browser.uncheck / Uncheck checkbox
```yaml
- action: browser.uncheck
  selector: "#newsletter"
```

#### browser.hover / Hover element
```yaml
- action: browser.hover
  selector: ".dropdown-menu"
```

#### browser.drag / Drag and drop
```yaml
- action: browser.drag
  source: "#draggable"
  target: "#drop-zone"
```

### Keyboard Actions

#### browser.press / Press key
```yaml
# Press Enter
- action: browser.press
  key: "Enter"

# Press on specific element
- action: browser.press
  selector: "#search-input"
  key: "Enter"

# Special keys: Enter, Tab, Escape, ArrowLeft, ArrowRight, Backspace, Delete
# Modifiers: Control, Shift, Alt, Meta
```

#### browser.type / Type text
```yaml
- action: browser.type
  selector: "#field"
  text: "Slow typing"
  delay: 100  # Milliseconds between keystrokes
```

### Waiting & Verification

#### browser.wait / Wait
```yaml
# Simple delay (milliseconds)
- action: browser.wait
  timeout: 2000

# Old syntax
- action: Wait
  time: 2  # Seconds
```

#### browser.wait_for / Wait for element
```yaml
# Wait for visible
- action: browser.wait_for
  selector: "#loading"
  state: "visible"
  timeout: 10000

# Wait for hidden
- action: browser.wait_for
  selector: ".spinner"
  state: "hidden"

# States: visible, hidden, attached, detached
```

#### browser.screenshot / Take screenshot
```yaml
# Simple screenshot
- action: browser.screenshot
  name: "homepage"

# Full page
- action: browser.screenshot
  name: "full-page"
  full_page: true

# Element only
- action: browser.screenshot
  selector: "#error-message"
  name: "error"
```

### Content Extraction

#### browser.get_text / Get text content
```yaml
- action: browser.get_text
  selector: "#result"
  store_as: "result_text"
```

#### browser.get_attribute / Get attribute
```yaml
- action: browser.get_attribute
  selector: "#link"
  attribute: "href"
  store_as: "link_url"
```

#### browser.get_value / Get input value
```yaml
- action: browser.get_value
  selector: "#field"
  store_as: "field_value"
```

### Advanced

#### browser.execute / Execute JavaScript
```yaml
- action: browser.execute
  script: "return document.title"
  store_as: "page_title"

# With arguments
- action: browser.execute
  script: "return arguments[0].textContent"
  args: ["#element"]
  store_as: "text"
```

#### browser.set_viewport / Set viewport size
```yaml
- action: browser.set_viewport
  width: 1920
  height: 1080
```

#### browser.cookies / Manage cookies
```yaml
# Get cookies
- action: browser.cookies
  action: "get"
  store_as: "cookies"

# Set cookie
- action: browser.cookies
  action: "set"
  name: "session"
  value: "abc123"
  domain: "example.com"

# Clear cookies
- action: browser.cookies
  action: "clear"
```

---

## API Actions

### api.get / API GET Request
```yaml
- action: api.get
  url: "https://api.example.com/users"
  headers:
    Authorization: "Bearer ${token}"
  params:
    page: 1
    limit: 10
  store_as: "users_response"
```

### api.post / API POST Request
```yaml
- action: api.post
  url: "https://api.example.com/users"
  headers:
    Content-Type: "application/json"
  body:
    name: "John Doe"
    email: "john@example.com"
  store_as: "create_response"
```

### api.put / API PUT Request
```yaml
- action: api.put
  url: "https://api.example.com/users/123"
  body:
    name: "Updated Name"
```

### api.patch / API PATCH Request
```yaml
- action: api.patch
  url: "https://api.example.com/users/123"
  body:
    email: "newemail@example.com"
```

### api.delete / API DELETE Request
```yaml
- action: api.delete
  url: "https://api.example.com/users/123"
```

### API Request Options
```yaml
- action: api.get
  url: "${base_url}/endpoint"
  headers:
    Authorization: "Bearer ${token}"
    X-Custom-Header: "value"
  params:
    filter: "active"
    sort: "name"
  timeout: 30
  verify_ssl: false
  allow_redirects: true
  store_as: "response"
  
  # Authentication shorthand
  auth:
    username: "user"
    password: "pass"
```

---

## AWS S3 Actions

### aws.list_files / List S3 Files
```yaml
- action: aws.list_files
  bucket_name: "my-bucket"
  folder_prefix: "firmware/"
  file_extension: ".bin"
  download_dir: "Firmware"
  store_as: "file_list"
  
  # Optional credentials
  aws_access_key_id: "${AWS_KEY}"
  aws_secret_access_key: "${AWS_SECRET}"
  region_name: "us-east-1"
```

### aws.get_latest / Get Latest Firmware
```yaml
- action: aws.get_latest
  bucket_name: "firmware-bucket"
  folder_prefix: "devices/model-x/"
  file_extension: ".bin"
  download_dir: "Firmware"
  store_filename_as: "latest_firmware"
  store_version_as: "latest_version"
  
  # Optional: get second-to-last
  get_second_to_last: false
```

**Stored Variables:**
- `{store_filename_as}` - Full S3 key (e.g., `firmware/v1.2.3/file.bin`)
- `{store_filename_as}_basename` - Just filename (e.g., `file.bin`)
- `{store_filename_as}_cloudfront_url` - CloudFront URL
- `{store_version_as}` - Extracted version (e.g., `1.2.3`)

### aws.download / Download File
```yaml
- action: aws.download
  bucket_name: "my-bucket"
  s3_key: "path/to/file.bin"
  local_path: "downloads/file.bin"
```

### aws.upload / Upload File
```yaml
- action: aws.upload
  bucket_name: "my-bucket"
  local_path: "file.txt"
  s3_key: "uploads/file.txt"
```

### aws.delete / Delete File
```yaml
- action: aws.delete
  bucket_name: "my-bucket"
  s3_key: "old-file.txt"
```

---

## JSON-RPC WebSocket Actions

### jsonrpc.connect / Connect
```yaml
- action: jsonrpc.connect
  server_url: "wss://server.com:10444"
  device_id: "AA:BB:CC:DD:EE:FF"
  protocol: "firmware-protocol"
  verify_ssl: false
```

### jsonrpc.disconnect / Disconnect
```yaml
- action: jsonrpc.disconnect
```

### jsonrpc.send / Send Request
```yaml
- action: jsonrpc.send
  method: "dxGetAbout"
  params:
    deviceId: "${device_id}"
    version: 0
  store_as: "about_info"
  timeout: 10.0
```

### Device Management

#### jsonrpc.start_updates / Start Device Updates
```yaml
- action: jsonrpc.start_updates
```

#### jsonrpc.stop_updates / Stop Device Updates
```yaml
- action: jsonrpc.stop_updates
```

#### jsonrpc.get_about / Get Device Info
```yaml
- action: jsonrpc.get_about
  store_as: "device_info"
```

#### jsonrpc.reset / Reset Device
```yaml
- action: jsonrpc.reset
```

### Network Settings

#### jsonrpc.get_network / Get Network Settings
```yaml
- action: jsonrpc.get_network
  store_as: "network_config"
```

#### jsonrpc.set_network / Set Network Settings
```yaml
- action: jsonrpc.set_network
  device_name: "MyDevice"
  device_ip: "192.168.1.100"
  subnet_mask: "255.255.255.0"
  gateway: "192.168.1.1"
  dhcp_enabled: false
  dns_server1: "8.8.8.8"
  dns_server2: "8.8.4.4"
  web_port: 80
```

### Firmware Update

#### jsonrpc.update_firmware / Update Firmware
```yaml
- action: jsonrpc.update_firmware
  firmware_url: "${cloudfront_url}"
```

---

## Wake-on-LAN

### wol.send / Send Magic Packet
```yaml
# Wake device using mac_for_report suite variable (simplest)
- wol.send: {}

# Explicit MAC address
- wol.send:
    mac: 'AA:BB:CC:DD:EE:FF'

# All options
- wol.send:
    mac: '${mac_for_report}'      # XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
    broadcast: 255.255.255.255    # default
    port: 9                       # UDP port (default: 9, alt: 7)
    sleep: 5                      # seconds to wait after sending (default: 5)
    store_as: wol_result          # optional
```

---

## Test & Assertion Actions

### test.assert / Assert Condition
```yaml
# Simple assertion
- action: test.assert
  expression: "status_code == 200"
  message: "Status should be 200"

# With Python expressions
- action: test.assert
  expression: "'success' in response_body"
  message: "Response should contain success"

# Soft assertion (continue on failure)
- action: test.assert
  expression: "user_count > 0"
  message: "Should have users"
  soft_assert: true

# Available variables in expressions:
# - last_response, last_status, last_json, last_headers
# - page_content, page_title, page_url
# - All test variables
```

### test.assert_schema / Assert JSON Schema
```yaml
- action: test.assert_schema
  schema:
    type: "object"
    required: ["id", "name"]
    properties:
      id:
        type: "integer"
      name:
        type: "string"
  data: "${last_json}"
```

### test.assert_response / Assert HTTP Response
```yaml
- action: test.assert_response
  status: 200
  headers:
    Content-Type: "application/json"
  body_contains: "success"
```

### test.check_assertions / Check Soft Assertions
```yaml
# After soft assertions, check if any failed
- action: test.check_assertions
```

---

## Conditional Logic

### Basic Condition
```yaml
- condition: "firmware_version >= '2.0.0'"
  then:
    - action: browser.click
      selector: "#upgrade"
  else:
    - action: browser.screenshot
      name: "no-upgrade-needed"
```

### Multiple Conditions
```yaml
- condition: "status == 'ready' and count > 0"
  then:
    - action: api.post
      url: "${api_url}/process"

- condition: "error_count > 5"
  then:
    - action: test.assert
      expression: "False"
      message: "Too many errors"
```

### Available Operators
```yaml
# Comparison: ==, !=, <, >, <=, >=
# Logical: and, or, not
# Membership: in, not in
# Identity: is, is not
# String: startswith(), endswith(), contains()

# Examples:
condition: "version >= '1.0.0'"
condition: "'error' not in response"
condition: "device_id is not None"
condition: "len(users) > 0"
```

---

## Retry Configuration

### Action-Level Retry
```yaml
- action: api.get
  url: "${api_url}/flaky-endpoint"
  retry:
    max_attempts: 3
    delay: 1.0
    backoff_multiplier: 2.0
    max_delay: 10.0
    retry_on_exceptions: ["ConnectionError", "Timeout"]
```

### Retry Parameters
```yaml
retry:
  max_attempts: 3           # Total attempts (1 initial + 2 retries)
  delay: 1.0               # Initial delay in seconds
  backoff_multiplier: 2.0  # Exponential backoff multiplier
  max_delay: 30.0          # Maximum delay between attempts
  retry_on_exceptions:     # List of exceptions to retry
    - "ConnectionError"
    - "TimeoutError"
```

---

## Data-Driven Testing

### Inline Data
```yaml
data:
  - username: "user1"
    password: "pass1"
    expected: "success"
  - username: "user2"
    password: "pass2"
    expected: "success"

steps:
  - action: browser.fill
    field: "#username"
    value: "${username}"  # From data row
```

### External Data - CSV
```yaml
data_source:
  type: "csv"
  file: "tests/data/login_data.csv"

steps:
  - action: browser.fill
    field: "#username"
    value: "${username}"  # From CSV column
```

### External Data - JSON
```yaml
data_source:
  type: "json"
  file: "tests/data/api_tests.json"

steps:
  - action: api.${method}  # Variable in action name
    url: "${endpoint}"
```

### Async Data Execution
```yaml
async_execution: true
max_workers: 3

data:
  - device: "device1"
  - device: "device2"
  - device: "device3"
```

---

## Variables

### Definition
```yaml
variables:
  # Simple values
  username: "admin"
  timeout: 5000
  enabled: true
  
  # Environment variables
  api_key: "${API_KEY}"
  password: "${SECURE_PASSWORD}"
  
  # Nested variables
  api:
    base_url: "https://api.example.com"
    version: "v1"
```

### Usage
```yaml
steps:
  - action: api.get
    url: "${api.base_url}/${api.version}/users"
    headers:
      Authorization: "Bearer ${api_key}"
```

### Dynamic Variables (Stored)
```yaml
# Store API response
- action: api.get
  url: "/users/1"
  store_as: "user"

# Use stored data
- action: test.assert
  expression: "user['name'] == 'John'"

# Store from last response
# Available: last_response, last_status, last_json, last_headers
```

---

## Configuration Options

### Test-Level Browser Config
```yaml
browser:
  headless: false       # Show browser window
  slow_mo: 1000        # Slow down by ms
  timeout: 30000       # Default timeout ms
  viewport:
    width: 1920
    height: 1080
  video: true          # Record video
  screenshot: true     # Screenshot on failure
  browser_type: "chromium"  # chromium, firefox, webkit
```

### Test-Level Options
```yaml
name: "Test Name"
description: "Test description"
tags: ["smoke", "critical"]

# Async execution
async_execution: true
max_workers: 3

# Time tracking
track_time: true

# Soft assertions
soft_assertions: true

# Retry configuration (global for test)
retry:
  max_attempts: 3
  delay: 1.0
```

### Framework Config (config/framework.yaml)
```yaml
browser:
  default_browser: "chromium"
  headless: true
  timeout: 30000
  slow_mo: 0
  screenshots_on_failure: true
  video_on_failure: false

execution:
  max_workers: 1
  async_by_default: false
  continue_on_failure: false

reporting:
  output_dir: "reports"
  generate_html: true
  include_screenshots: true
  include_videos: true
  
aws:
  region: "us-east-1"
  cloudfront_domain: "cdn.example.com"

datalake:
  enabled: false
  s3_bucket: "test-results"
  teams_webhook: "${TEAMS_WEBHOOK_URL}"
```

---

## Quick Examples

### Complete Browser Test
```yaml
name: "Login Test"
tags: ["smoke", "auth"]

variables:
  base_url: "https://app.example.com"
  username: "${TEST_USER}"
  password: "${TEST_PASSWORD}"

browser:
  headless: false

setup:
  - action: browser.open
    url: "${base_url}/login"

steps:
  - action: browser.fill
    field: "#username"
    value: "${username}"
  
  - action: browser.fill
    field: "#password"
    value: "${password}"
  
  - action: browser.click
    role: "button"
    name: "Log In"
  
  - action: browser.wait_for
    selector: ".dashboard"
    state: "visible"
  
  - action: test.assert
    expression: "'Dashboard' in page_content"
    message: "Should show dashboard"
  
  - action: browser.screenshot
    name: "logged-in"

cleanup:
  - action: browser.close
```

### Complete API Test
```yaml
name: "User API Test"
tags: ["api", "crud"]

variables:
  api_url: "https://api.example.com"
  api_key: "${API_KEY}"

steps:
  # Create user
  - action: api.post
    url: "${api_url}/users"
    headers:
      Authorization: "Bearer ${api_key}"
    body:
      name: "Test User"
      email: "test@example.com"
    store_as: "created_user"
  
  # Verify creation
  - action: test.assert
    expression: "last_status == 201"
    message: "Should create user"
  
  - action: test.assert
    expression: "created_user['id'] is not None"
    message: "Should have user ID"
  
  # Get user
  - action: api.get
    url: "${api_url}/users/${created_user[id]}"
    headers:
      Authorization: "Bearer ${api_key}"
  
  - action: test.assert
    expression: "last_json['name'] == 'Test User'"
  
  # Delete user
  - action: api.delete
    url: "${api_url}/users/${created_user[id]}"
    headers:
      Authorization: "Bearer ${api_key}"
```

### Firmware Upgrade with Conditional Logic
```yaml
name: "Conditional Firmware Upgrade"
tags: ["firmware", "device"]

variables:
  device_ip: "192.168.100.16"
  bucket_name: "firmware-bucket"
  folder_prefix: "devices/AN-810/"
  target_version: "2.2.0"

setup:
  # Get latest firmware from S3
  - action: aws.get_latest
    bucket_name: "${bucket_name}"
    folder_prefix: "${folder_prefix}"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_filename_as: "firmware_file"
    store_version_as: "firmware_version"
  
  # Login to device
  - action: browser.open
    url: "http://${device_ip}"
  
  - action: browser.fill
    field: "#username"
    value: "admin"
  
  - action: browser.fill
    field: "#password"
    value: "password"
  
  - action: browser.click
    role: "button"
    name: "Login"

steps:
  # Only upgrade if version is higher
  - condition: "firmware_version >= target_version"
    then:
      - action: browser.click
        role: "link"
        name: "File Management"
      
      - action: browser.wait
        timeout: 2000
      
      - action: browser.upload
        selector: "iframe >> #firmware-input"
        file_path: "Firmware/${firmware_file_basename}"
      
      - action: browser.click
        selector: "iframe >> #upload-button"
      
      - action: browser.wait
        timeout: 10000
    else:
      - action: browser.screenshot
        name: "no-upgrade-needed"
      
      - action: test.assert
        expression: "True"
        message: "Device already on latest firmware"

cleanup:
  - action: browser.screenshot
    name: "final-state"
  - action: browser.close
```

---

## Command Line Usage

```bash
# Run all tests
python -m easybdd run

# Run specific test
python -m easybdd run tests/cases/my_test.yaml

# Run with tags
python -m easybdd run --tags smoke
python -m easybdd run --tags "critical,api"

# Run with browser visible
python -m easybdd run tests/cases/browser_test.yaml --headed

# Generate Gherkin only
python -m easybdd generate tests/cases/

# Validate tests
python -m easybdd validate tests/cases/

# Validate with strict mode
python -m easybdd validate tests/cases/ --strict

# View metrics
make metrics-dashboard
make metrics-flaky
make metrics-export

# Start metrics API
make metrics-api
```

---

## Environment Variables

Create `.env` file:
```bash
# API Credentials
API_KEY=sk_live_abc123xyz
API_SECRET=secret123

# AWS Credentials
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_DEFAULT_REGION=us-east-1

# Test Credentials
TEST_USER=testuser@example.com
TEST_PASSWORD=SecurePassword123!

# Device Credentials
DEVICE_PASSWORD=admin123

# Webhook URLs
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Use in tests:
```yaml
variables:
  api_key: "${API_KEY}"
  password: "${DEVICE_PASSWORD}"
```

---

**For more detailed information, see:**
- [actions.md](actions.md) - Detailed action reference
- [syntax.md](syntax.md) - YAML syntax guide  
- [examples.md](examples.md) - Real-world examples
- [conditional-steps.md](conditional-steps.md) - Conditional logic guide
- [aws-s3-integration.md](aws-s3-integration.md) - AWS integration guide
- [dot-notation-actions.md](dot-notation-actions.md) - New action syntax
