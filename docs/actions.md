# Actions Reference Guide

Complete reference for all available test actions in the Easy BDD Framework.

## 🌐 Browser Actions

### Open Browser
Opens a browser and navigates to a URL.

```yaml
- action: Open browser
  url: "https://example.com"
  description: Navigate to the website
```

**Parameters:**
- `url` (required): The URL to navigate to
- `description` (optional): Step description

**Variable Support:** ✅
```yaml
- action: Open browser
  url: "${base_url}/login"
```

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