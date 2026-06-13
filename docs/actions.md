# Action Reference Guide

This document provides a comprehensive reference for all available actions in the Easy BDD framework.

## Browser Actions

### Navigation Actions

#### open browser
Opens a browser and navigates to a URL.
```yaml
- action: "open browser"
  url: "https://example.com"
```

#### navigate back
Navigates to the previous page in browser history.
```yaml
- action: "navigate back"
```

#### navigate forward
Navigates to the next page in browser history.
```yaml
- action: "navigate forward"
```

#### refresh browser
Refreshes the current page.
```yaml
- action: "refresh browser"
```

### Element Interaction Actions

#### click element
Clicks on an element using various selector strategies.
```yaml
# By CSS selector
- action: "click element"
  selector: "#submit-button"

# By visible text
- action: "click element"
  text: "Submit"

# By button text (uses get_by_role internally)
- action: "click element"
  button: "Log In"

# By role and name (Playwright native)
- action: "click element"
  role: "link"
  name: "192.168.100.13"
  exact: true  # Optional, for exact match

# By role - common examples
- action: "click element"
  role: "button"
  name: "Submit Form"

- action: "click element"
  role: "heading"
  name: "Dashboard"

- action: "click element"
  role: "checkbox"
  name: "Accept Terms"
```

#### fill field
Fills a form field with text.
```yaml
- action: "fill field"
  field: "username"  # Can use name, id, or label
  value: "john@example.com"
  # Alternative syntax
  selector: "#username"
```

#### hover element
Hovers over an element.
```yaml
- action: "hover element"
  selector: ".dropdown-trigger"
```

#### double click element
Double-clicks on an element.
```yaml
- action: "double click element"
  selector: ".file-item"
```

#### press key
Presses a keyboard key, optionally on a specific element.
```yaml
- action: "press key"
  key: "Enter"
  selector: "#search-input"  # Optional
```

#### get by label
Interacts with elements by their label text.
```yaml
- action: "get by label"
  label: "Email Address"
  action_type: "fill"  # click, fill, etc.
  value: "user@example.com"  # For fill actions
```

### Wait Actions

#### wait for element
Waits for an element to reach a certain state.
```yaml
- action: "wait for element"
  selector: ".loading-spinner"
  state: "hidden"  # visible, hidden, attached, detached
  timeout: 10  # seconds (optional)
```

#### wait
Waits for a specified time.
```yaml
- action: "wait"
  time: 2  # seconds
```

### File Actions

#### upload file
Uploads a file to a file input.
```yaml
- action: "upload file"
  selector: "input[type='file']"
  file_path: "data/test-file.pdf"
```

#### take screenshot
Takes a screenshot for documentation or debugging.
```yaml
- action: "take screenshot"
  name: "login-page"  # Optional name
```

## API Actions

### HTTP Methods

#### api request
Generic API request action supporting all HTTP methods.
```yaml
- action: "api request"
  method: "GET"  # GET, POST, PUT, DELETE, PATCH
  url: "https://api.example.com/users"
  device_id: "device_1001"  # Optional, uses auth config
  headers:  # Optional
    Accept: "application/json"
  params:  # Optional query parameters
    page: 1
    limit: 10
  json_data:  # Optional JSON body
    name: "John Doe"
    email: "john@example.com"
  data:  # Optional form data
    field1: "value1"
```

#### api get
Shorthand for GET requests.
```yaml
- action: "api get"
  url: "https://api.example.com/users/123"
  device_id: "device_1001"
  headers:
    Accept: "application/json"
  params:
    include: "profile"
```

#### api post
Shorthand for POST requests.
```yaml
- action: "api post"
  url: "https://api.example.com/users"
  device_id: "device_1001"
  json_data:
    name: "John Doe"
    email: "john@example.com"
    role: "user"
```

#### api put
Shorthand for PUT requests.
```yaml
- action: "api put"
  url: "https://api.example.com/users/123"
  device_id: "device_1001"
  json_data:
    name: "John Smith"
```

#### api delete
Shorthand for DELETE requests.
```yaml
- action: "api delete"
  url: "https://api.example.com/users/123"
  device_id: "device_1001"
```

### Response Validation

#### validate status
Validates the HTTP status code of the last API response.
```yaml
- action: "validate status"
  status: 200  # Expected status code
```

#### validate json
Validates a field in the JSON response.
```yaml
- action: "validate json"
  field: "user.name"  # Supports dot notation for nested fields
  value: "John Doe"
```

## Selector Strategies

The framework supports multiple ways to identify elements:

### 1. CSS Selectors
```yaml
selector: "#username"           # ID
selector: ".btn-primary"        # Class  
selector: "input[type='email']" # Attribute
selector: "div > p:first-child" # Complex selectors
```

### 2. Text Content
```yaml
text: "Click Here"              # Exact text
text: "Submit"                  # Button text
```

### 3. Label Association
```yaml
label: "Email Address"          # Associated label
field: "username"               # Form field name/id
```

### 4. Smart Fallbacks
The framework automatically tries multiple strategies:
1. CSS selector
2. Text content matching
3. Label association
4. Name/ID attributes
5. Placeholder text

## Variable Usage

All actions support variable substitution using `${variable}` syntax:

```yaml
variables:
  base_url: "https://api.example.com"
  user_id: "12345"

steps:
  - action: "api get"
    url: "${base_url}/users/${user_id}"

  - action: "fill field"
    field: "email"
    value: "${user_email}"
```

## Authentication Context

API actions support device-specific authentication through the `device_id` parameter:

```yaml
- action: "api request"
  method: "GET"
  url: "https://api.example.com/protected"
  device_id: "device_1001"  # Uses auth config for this device
```

Each device can have different:
- Authentication endpoints
- Token formats
- Expiration handling
- Credentials

See [API Authentication Guide](api-authentication.md) for configuration details.

## Error Handling

Actions automatically handle common scenarios:
- **Element not found**: Retries with different selector strategies
- **Network errors**: Retries API requests with exponential backoff
- **Authentication failures**: Automatically refreshes tokens
- **Timeouts**: Configurable timeout values per action

## Best Practices

1. **Use descriptive selectors**: Prefer IDs and stable classes over complex CSS paths
2. **Leverage smart selectors**: Use text and labels when possible for maintainability
3. **Handle dynamic content**: Use wait actions for elements that load asynchronously
4. **Organize API tests**: Group related API calls and use consistent device_ids
5. **Validate responses**: Always validate both status codes and response content
6. **Use variables**: Parameterize URLs, credentials, and test data

### Click Element
Clicks on a web element.

```yaml
- action: Click element
  selector: "#submit-button"
  description: Click the submit button
```

**Parameters:**
- `selector` (required): CSS/XPath selector for the element
- `description` (optional): Step description

**Selector Examples:**
```yaml
selector: "#button-id"                    # ID
selector: ".btn.primary"                  # Class
selector: "[data-testid='submit']"        # Attribute
selector: "button:has-text('Save')"       # Text content
selector: "//button[@type='submit']"      # XPath
```

### Fill Form Field
Fills an input field with text.

```yaml
- action: Fill form field
  field: "[name='email']"
  value: "user@example.com"
  description: Enter email address
```

**Parameters:**
- `field` (required): Selector for the input field
- `value` (required): Text to enter
- `description` (optional): Step description

**Advanced Examples:**
```yaml
# Clear field before typing
- action: Fill form field
  field: "#username"
  value: "${user_name}"
  clear: true

# Special characters
- action: Fill form field
  field: "#password"
  value: "P@ssw0rd!"
```

### Take Screenshot
Captures a screenshot of the current page.

```yaml
- action: Take screenshot
  name: "login-page"
  description: Capture login page state
```

**Parameters:**
- `name` (optional): Screenshot filename (default: "screenshot")
- `description` (optional): Step description

**Variable Support:**
```yaml
- action: Take screenshot
  name: "device-${device_id}-status"
```

### Wait for Element
Waits for an element to reach a specific state.

```yaml
- action: Wait for element
  selector: ".loading-spinner"
  state: "hidden"
  timeout: 10000
  description: Wait for loading to complete
```

**Parameters:**
- `selector` (required): Element selector
- `state` (optional): "visible" | "hidden" | "enabled" | "disabled" (default: "visible")
- `timeout` (optional): Timeout in milliseconds (default: 5000)
- `description` (optional): Step description

**State Options:**
```yaml
state: "visible"    # Element is visible
state: "hidden"     # Element is not visible
state: "enabled"    # Element is enabled
state: "disabled"   # Element is disabled
```

### Verify Text
Verifies that specific text appears on the page.

```yaml
- action: Verify text
  text: "Welcome back!"
  description: Verify welcome message
```

**Parameters:**
- `text` (required): Text to search for
- `description` (optional): Step description

**Variable Support:**
```yaml
- action: Verify text
  text: "${expected_message}"
```

### Navigate Back
Navigates to the previous page in browser history.

```yaml
- action: Navigate back
  description: Return to previous page
```

**Parameters:**
- `description` (optional): Step description

### Navigate Forward
Navigates to the next page in browser history.

```yaml
- action: Navigate forward
  description: Go to next page
```

**Parameters:**
- `description` (optional): Step description

## 🔄 Test Actions

### test.run

Execute another test as a reusable step within your current test. This enables modular test composition and code reuse.

**Parameters:**
- `test_path` (required): Path to the test file relative to `tests/cases/` directory (e.g., `OvrC/ovrc_api_websocket_test.yaml`)
- `variables` (optional): Key-value pairs of variables to pass to the called test
- `store_variables` (optional): Variables to extract from the called test's results. Format: `{"variable_name": "path.to.value"}` (e.g., `{"fw_version": "about_result.firmware"}`)
- `continue_on_failure` (optional, default: false): If true, continue test execution even if the called test fails

**Example:**
```yaml
steps:
  # Run another test as a step
  - test.run:
      test_path: "OvrC/dxGetAbout.yaml"
      variables:
        device_ip: "192.168.1.100"
        device_id: "4B:00:00:00:00:15"
      store_variables:
        firmware_version: "about_result.firmware"
        device_model: "about_result.model"

  # Use extracted variables in subsequent steps
  - test.assert:
      expression: "'firmware_version' in locals()"
      message: "Firmware version should be extracted"
```

**Use Cases:**
- Extract firmware version from a device and use it in subsequent steps
- Reuse common test sequences (e.g., login, device setup) across multiple tests
- Create modular test libraries for maintainability
- Pass variables between tests for data flow

**Note:** The called test runs in the same execution context, so variables can be shared. Use `store_variables` to extract specific values from the called test's execution results.

## ⏱ Utility Actions

### Wait
Pauses execution for a specified time.

```yaml
- action: Wait
  time: 2
  description: Wait for page to stabilize
```

**Parameters:**
- `time` (required): Time to wait in seconds
- `description` (optional): Step description

**Variable Support:**
```yaml
- action: Wait
  time: ${wait_duration}
```

## 🔧 Advanced Browser Actions

### Hover Element
Hovers over an element (triggers mouseover events).

```yaml
- action: Hover element
  selector: ".dropdown-trigger"
  description: Show dropdown menu
```

**Parameters:**
- `selector` (required): Element selector
- `description` (optional): Step description

### Press Key
Presses a keyboard key or key combination.

```yaml
- action: Press key
  key: "Enter"
  description: Submit form with Enter key
```

**Parameters:**
- `key` (required): Key name (Enter, Tab, Escape, etc.)
- `description` (optional): Step description

**Key Examples:**
```yaml
key: "Enter"        # Enter key
key: "Tab"          # Tab key
key: "Escape"       # Escape key
key: "Control+A"    # Ctrl+A combination
key: "Meta+C"       # Cmd+C (Mac) / Win+C (Windows)
```

### Select Option
Selects an option from a dropdown.

```yaml
- action: Select option
  selector: "#country-select"
  value: "United States"
  description: Select country
```

**Parameters:**
- `selector` (required): Dropdown selector
- `value` (required): Option text or value to select
- `description` (optional): Step description

### Upload File
Uploads a file to a file input.

```yaml
- action: Upload file
  selector: "[type='file']"
  file_path: "./data/test-document.pdf"
  description: Upload test document
```

**Parameters:**
- `selector` (required): File input selector
- `file_path` (required): Path to file to upload
- `description` (optional): Step description

## 🌍 API Actions (Future)

### API Request
Makes an HTTP API request.

```yaml
- action: API request
  method: "GET"
  url: "/api/users"
  headers:
    Authorization: "Bearer ${token}"
  description: Fetch user list
```

**Parameters:**
- `method` (required): HTTP method (GET, POST, PUT, DELETE, etc.)
- `url` (required): API endpoint URL
- `headers` (optional): HTTP headers
- `body` (optional): Request body
- `description` (optional): Step description

## 📱 Mobile Actions (Future)

### Tap Element
Taps on a mobile element.

```yaml
- action: Tap element
  selector: "text=Login"
  description: Tap login button
```

### Swipe
Performs a swipe gesture.

```yaml
- action: Swipe
  direction: "left"
  distance: 200
  description: Swipe left to next page
```

## ☁️ AWS Actions

### AWS S3 Upload
Uploads a file to AWS S3.

```yaml
- action: AWS S3 upload
  bucket: "test-bucket"
  key: "test-files/document.pdf"
  file_path: "./data/document.pdf"
  description: Upload test file to S3
```

## 🎯 Selector Best Practices

### Priority Order
1. **Data attributes** (most stable)
   ```yaml
   selector: "[data-testid='submit-button']"
   ```

2. **ARIA attributes** (semantic)
   ```yaml
   selector: "[role='button'][aria-label='Save']"
   ```

3. **Text content** (readable)
   ```yaml
   selector: "button:has-text('Submit')"
   ```

4. **CSS classes** (if stable)
   ```yaml
   selector: ".btn.btn-primary"
   ```

5. **IDs** (if unique and stable)
   ```yaml
   selector: "#submit-btn"
   ```

### Avoid These Selectors
❌ **Don't use:**
```yaml
# Generic selectors
selector: "div > div > button"

# Auto-generated classes
selector: ".css-abc123-def456"

# Position-based selectors
selector: "button:nth-child(3)"
```

## 🔍 Debugging Actions

### Debug Wait
Extended wait with debug information.

```yaml
- action: Wait for element
  selector: "#dynamic-content"
  timeout: 30000
  description: Wait for dynamic content (debug)
```

### Screenshot on Failure
Automatic screenshots when steps fail:

```yaml
# Framework automatically takes screenshots on failures
# Saved as: reports/screenshots/failed-step-timestamp.png
```

## 📋 Action Chaining Examples

### Login Flow
```yaml
steps:
  - action: Open browser
    url: "${app_url}/login"

  - action: Fill form field
    field: "[name='username']"
    value: "${username}"

  - action: Fill form field
    field: "[name='password']"
    value: "${password}"

  - action: Click element
    selector: "[type='submit']"

  - action: Wait for element
    selector: ".dashboard"
    state: "visible"

  - action: Verify text
    text: "Welcome"
```

### Form Submission with Validation
```yaml
steps:
  - action: Fill form field
    field: "#email"
    value: "invalid-email"

  - action: Click element
    selector: "#submit"

  - action: Wait for element
    selector: ".error-message"
    state: "visible"

  - action: Verify text
    text: "Please enter a valid email"

  - action: Take screenshot
    name: "validation-error"
```

---

## SSH Actions

Stateful SSH sessions using Paramiko. Unlike `command.ssh` (which spawns a one-shot subprocess), `ssh.*` keeps the connection alive across steps, making it suitable for interactive workflows like enabling privileged mode or running a sequence of commands on network gear.

### ssh.connect

Opens an SSH connection and stores it in the session pool, keyed by `host`.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `host` | yes | — | Hostname or IP address |
| `username` | yes | — | SSH username |
| `password` | no | — | Password authentication |
| `key_filename` | no | — | Path to private key file |
| `passphrase` | no | — | Passphrase for encrypted private key |
| `port` | no | `22` | SSH port |
| `timeout` | no | `30` | Connection timeout in seconds |
| `look_for_keys` | no | `True` | Let Paramiko search for keys in `~/.ssh/` |
| `allow_agent` | no | `True` | Allow Paramiko to use the SSH agent |

### ssh.command

Runs a command on an already-connected host. Two modes are available:

- **exec_command** (default) — clean, non-interactive; ideal for single commands.
- **interactive shell** — enabled by `use_shell: true` or by providing a `prompt:`; keeps the shell open between calls and is required for things like Cisco `enable` mode.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `host` | yes | — | Must match a host passed to `ssh.connect` |
| `command` | yes | — | Command string to execute |
| `store_as` | no | — | Variable name to store stdout output; also sets `last_response` |
| `use_shell` | no | `false` | Use an interactive shell instead of exec_command |
| `prompt` | no | — | Substring to wait for before returning (implies `use_shell: true`) |
| `timeout` | no | `30` | Command timeout in seconds |

### ssh.disconnect

Closes the SSH connection for the given host.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `host` | yes | Host to disconnect |

### Example — password authentication

```yaml
- ssh.connect:
    host: 192.168.1.1
    username: admin
    password: admin123

- ssh.command:
    host: 192.168.1.1
    command: show version
    store_as: version_output

- ssh.command:
    host: 192.168.1.1
    command: show ip interface brief
    store_as: interface_output

- ssh.disconnect:
    host: 192.168.1.1
```

### Example — key file authentication

```yaml
- ssh.connect:
    host: 192.168.1.1
    username: admin
    key_filename: /home/jenkins/.ssh/id_rsa

- ssh.command:
    host: 192.168.1.1
    command: cat /proc/version
    store_as: kernel_info

- ssh.disconnect:
    host: 192.168.1.1
```

### Example — interactive shell (privileged mode on a network device)

```yaml
- ssh.connect:
    host: 192.168.10.5
    username: cisco
    password: cisco123

- ssh.command:
    host: 192.168.10.5
    command: enable
    prompt: "Password:"
    use_shell: true

- ssh.command:
    host: 192.168.10.5
    command: cisco_enable_password
    prompt: "#"
    use_shell: true

- ssh.command:
    host: 192.168.10.5
    command: show running-config
    use_shell: true
    store_as: running_config

- ssh.disconnect:
    host: 192.168.10.5
```

> **`ssh.*` vs `command.ssh`:** Use `ssh.*` when you need multiple commands in a single session, interactive prompts, or privileged mode. Use `command.ssh` for one-shot remote commands where connection overhead does not matter.

---

## LGIP Actions

LG IP IR control over TCP. Used to send IR keycodes to AV displays and receivers that support the LG IP protocol. Connections are pooled by `ip:port`.

### lgip.connect

Opens a TCP connection to an LG IP IR device.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `ip` | yes | — | Device IP address |
| `port` | no | `9761` | TCP port |

### lgip.send_keycode

Sends an IR keycode packet and returns the device response.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `ip` | yes | — | Must match a connected device |
| `keycode` | yes | — | Numeric keycode string (see table below) |
| `delay_after` | no | `0` | Seconds to sleep after the keypress |
| `store_as` | no | — | Variable name to store the device response |

### lgip.disconnect

Closes the TCP connection to the device.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `ip` | yes | Device to disconnect |

### Common keycodes

| Keycode | Function |
|---------|----------|
| `"20"` | Power On |
| `"21"` | Power Off |
| `"02"` | Volume Up |
| `"03"` | Volume Down |
| `"09"` | Mute |
| `"27"` | HDMI 1 |
| `"28"` | HDMI 2 |
| `"29"` | HDMI 3 |
| `"60"` | HDMI 4 |

### Example

```yaml
- lgip.connect:
    ip: 192.168.1.50
    port: 9761

- lgip.send_keycode:
    ip: 192.168.1.50
    keycode: "20"
    delay_after: 2.0
    store_as: power_on_result

- lgip.send_keycode:
    ip: 192.168.1.50
    keycode: "27"
    delay_after: 1.0

- lgip.disconnect:
    ip: 192.168.1.50
```

---

*For more action examples, see the [Examples Directory](./examples/)*
