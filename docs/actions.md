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

## ☁️ AWS Actions (Future)

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

*For more action examples, see the [Examples Directory](./examples/)*