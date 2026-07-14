# Dot Notation Action Reference

The Easy BDD Framework now supports **dot notation** for action names, providing a consistent, typo-resistant naming convention that's easier to remember and use.

## Why Dot Notation?

✅ **Consistent** - All actions follow the same `service.action` pattern  
✅ **Typo-Resistant** - No more "Click element" vs "click element" vs "Click Element"  
✅ **Intuitive** - Service name tells you what it does (browser, aws, jsonrpc)  
✅ **Auto-Complete Friendly** - IDEs can suggest actions by service  
✅ **Professional** - Matches industry standards (like Python's module.function)

## Pattern

```
service.action_name
```

Examples:
- `browser.click` - Click an element in the browser
- `aws.get_latest` - Get latest firmware from AWS S3
- `jsonrpc.connect` - Connect via JSON-RPC WebSocket
- `test.assert` - Assert a condition

## Complete Action Reference

### Browser Actions (`browser.*`)

#### Navigation
```yaml
- action: browser.open
  url: "https://example.com"

- action: browser.back
  # Navigate to previous page

- action: browser.forward
  # Navigate to next page

- action: browser.refresh
  # Reload current page

- action: browser.close
  # Close the browser session
```

#### Element Interaction
```yaml
# Click elements
- action: browser.click
  selector: "#button-id"

- action: browser.click
  role: button
  name: "Submit"

- action: browser.click
  text: "Click Here"

# Fill form fields
- action: browser.fill
  field: "username"
  value: "john@example.com"

- action: browser.fill
  selector: "#email"
  value: "test@example.com"

# Upload files
- action: browser.upload
  selector: "#file-input"
  file: "path/to/file.pdf"

# Upload to iframe
- action: browser.upload
  selector: "iframe >> #file-input"
  file: "Firmware/${firmware_basename}"
```

#### Selection & Dropdown
```yaml
- action: browser.select
  selector: "#dropdown"
  value: "option1"

- action: browser.select
  selector: "#dropdown"
  label: "Option 1"
```

#### Advanced Interactions
```yaml
# Hover over element
- action: browser.hover
  selector: ".menu-item"

# Double click
- action: browser.double_click
  selector: ".file-item"

# Press keyboard key
- action: browser.press_key
  key: "Enter"
  selector: "#search"  # Optional

# Scroll an element into view, or the window to coordinates
- action: browser.scroll
  selector: "#footer"

- action: browser.scroll
  x: 0
  y: 500
```

#### Waiting
```yaml
# Simple wait (milliseconds)
- action: browser.wait
  timeout: 2000

# Wait for specific element
- action: browser.wait_for
  selector: "#loading"
  state: "hidden"
  timeout: 5000

# Wait for the URL to match (substring or glob pattern)
- action: browser.wait_for_url
  url: "**/dashboard"
  timeout: 10000

# Without url, waits for the current navigation to complete
- action: browser.wait_for_url
```

#### Screenshots
```yaml
- action: browser.screenshot
  filename: "login_page"
```

#### Verification
```yaml
- action: browser.verify_text
  text: "Welcome"
  soft_assert: false

- action: browser.verify_element
  selector: "#success-message"
  soft_assert: true

# Assert an input/select's current value
- action: test.assert_value
  selector: "#hostname"
  value: "router-01"

# Assert the current page URL (substring or glob; exact: true for full match)
- action: test.assert_url
  url: "/dashboard"
```

---

### AWS S3 Actions (`aws.*`)

```yaml
# List firmware files
- action: aws.list_files
  bucket_name: "my-bucket"
  folder_prefix: "firmware/device-type"
  file_extension: ".bin"
  download_dir: "Firmware"
  store_as: "firmware_list"

# Get latest firmware
- action: aws.get_latest
  store_as: "latest_fw"

# Upload file to S3
- action: aws.upload
  bucket_name: "my-bucket"
  file_path: "reports/test_results.html"
  key: "results/test_results.html"
  store_as: "upload_result"

# Delete S3 folder
- action: aws.delete_folder
  bucket_name: "my-bucket"
  folder_prefix: "temp/old-files"
```

---

### JSON-RPC WebSocket Actions (`jsonrpc.*`)

```yaml
# Connect to device
- action: jsonrpc.connect
  url: "${device_ws_url}"
  device_id: "${device_id}"
  timeout: 10

# Start receiving device updates
- action: jsonrpc.start_updates

# Get device information
- action: jsonrpc.get_about
  store_as: "device_info"

# Stop device updates
- action: jsonrpc.stop_updates

# Reset device
- action: jsonrpc.reset_device

# Disconnect
- action: jsonrpc.disconnect
```

---

### Test Actions (`test.*`)

```yaml
# Assert condition
- action: test.assert
  expression: "status_code == 200"
  message: "API should return 200"

- action: test.assert
  expression: "'firmware_version' in device_info"
  message: "Device info should contain firmware version"

# Assert JSON schema
- action: test.assert_schema
  data: "${api_response}"
  schema: {type: object, required: [id], properties: {id: {type: integer}}}

# Assert HTTP response
- action: test.assert_response
  status: 200
  headers:
    content-type: "application/json"

# Wait (same as browser.wait for compatibility)
- action: test.wait
  timeout: 1000
```

---

## Backward Compatibility

The framework **fully supports the old format**, so your existing tests will continue to work:

```yaml
# Old format - still works!
- action: "Open browser"
  url: "https://example.com"

- action: "Click element"
  selector: "#button"

- action: "AWS get latest firmware"
  bucket_name: "my-bucket"

# New format - cleaner!
- action: browser.open
  url: "https://example.com"

- action: browser.click
  selector: "#button"

- action: aws.get_latest
  bucket_name: "my-bucket"
```

## Migration Guide

### Quick Conversion Table

| Old Format | New Format |
|------------|------------|
| `Open browser` | `browser.open` |
| `Click element` | `browser.click` |
| `Fill form field` / `Fill field` | `browser.fill` |
| `Upload file` | `browser.upload` |
| `Take screenshot` | `browser.screenshot` |
| `Wait` / `Sleep` | `test.sleep` |
| `Select option` | `browser.select` |
| `AWS list firmware files` | `aws.list_files` |
| `AWS get latest firmware` | `aws.get_latest` |
| `JSONRPC connect` | `jsonrpc.connect` |
| `JSONRPC get about` | `jsonrpc.get_about` |
| `Assert` | `test.assert` |

### Find & Replace

To convert your existing tests:

1. **Browser Actions**
   - `action: "Open browser"` → `action: browser.open`
   - `action: "Click element"` → `action: browser.click`
   - `action: "Fill form field"` → `action: browser.fill`
   - `action: "Upload file"` → `action: browser.upload`
   - `action: "Take screenshot"` → `action: browser.screenshot`
   - `action: "Wait"` → `action: test.sleep`

2. **AWS Actions**
   - `action: "AWS list firmware files"` → `action: aws.list_files`
   - `action: "AWS get latest firmware"` → `action: aws.get_latest`

3. **JSON-RPC Actions**
   - `action: "JSONRPC connect"` → `action: jsonrpc.connect`
   - `action: "JSONRPC get about"` → `action: jsonrpc.get_about`
   - `action: "JSONRPC start device updates"` → `action: jsonrpc.start_updates`

4. **Test Actions**
   - `action: "Assert"` → `action: test.assert`

## Best Practices

### 1. Use Dot Notation for New Tests
```yaml
# ✅ Recommended
- action: browser.click
  selector: "#submit"

# ❌ Old style (still works, but not recommended)
- action: "Click element"
  selector: "#submit"
```

### 2. Be Consistent Within a Test File
Don't mix styles in the same file. Pick one and stick with it.

### 3. No Quotes Needed
```yaml
# ✅ Clean
- action: browser.open
  url: "https://example.com"

# ❌ Unnecessary quotes
- action: "browser.open"
  url: "https://example.com"
```

### 4. Service Names Are Lowercase
```yaml
# ✅ Correct
- action: browser.click

# ❌ Won't work
- action: Browser.click
- action: BROWSER.CLICK
```

## Examples

### Complete Login Test
```yaml
name: "User Login Test"
description: "Test user login with dot notation"

variables:
  base_url: "https://app.example.com"
  username: "testuser"
  password: "testpass123"

steps:
  - action: browser.open
    url: "${base_url}/login"
  
  - action: browser.fill
    field: "username"
    value: "${username}"
  
  - action: browser.fill
    field: "password"
    value: "${password}"
  
  - action: browser.click
    role: button
    name: "Log In"
  
  - action: browser.wait_for
    selector: "#dashboard"
    timeout: 5000
  
  - action: browser.screenshot
    filename: "logged_in"
  
  - action: browser.verify_text
    text: "Welcome back"
```

### Firmware Upgrade Test
```yaml
name: "Firmware Upgrade"
description: "Download and upload firmware using dot notation"

variables:
  device_ip: "192.168.1.100"
  bucket_name: "firmware-bucket"

setup:
  - action: aws.get_latest
    store_as: "firmware_file"

steps:
  - action: browser.open
    url: "http://${device_ip}/admin"
  
  - action: browser.click
    role: link
    name: "Firmware Update"
  
  - action: browser.upload
    selector: "iframe >> #firmware-file"
    file: "Firmware/${firmware_file}"
  
  - action: browser.click
    selector: "iframe >> #upgrade-btn"
  
  - action: browser.wait
    timeout: 30000
```

### JSON-RPC Device Test
```yaml
name: "Device Information Check"
description: "Get device info via JSON-RPC"

variables:
  device_ip: "192.168.1.50"

setup:
  - action: jsonrpc.connect
    url: "${device_ws_url}"
    device_id: "${device_id}"
  
  - action: jsonrpc.get_about
    store_as: "device_info"

steps:
  - action: test.assert
    expression: "'firmware_version' in device_info"
    message: "Device should have firmware version"
  
  - action: test.assert
    expression: "device_info['uptime'] > 0"
    message: "Device should be running"
```

## Troubleshooting

**Q: My old tests stopped working after update**  
A: They shouldn't! The framework fully supports both formats. Check for syntax errors in your YAML.

**Q: Can I mix old and new formats?**  
A: Yes, but it's not recommended. Be consistent within each test file.

**Q: Do I need to update all my tests?**  
A: No, old format still works. Update when convenient.

**Q: Is dot notation case-sensitive?**  
A: No, `browser.click` and `Browser.Click` both work, but lowercase is recommended.

**Q: What if I forget an action name?**  
A: Check this guide or use IDE auto-complete. The pattern is always `service.action_verb`.

---

For more details on specific actions, see:
- [Browser Actions](actions.md#browser-actions)
- [AWS S3 Integration](aws-s3-integration.md)
- [JSON-RPC WebSocket](jsonrpc-websocket.md)
- [Assertions](assertions.md)
