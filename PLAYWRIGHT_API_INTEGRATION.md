# Playwright Native API Integration for Easy BDD

The Easy BDD framework now supports all of Playwright's native API patterns through simple YAML syntax. This enables seamless conversion of Playwright recordings and manual test creation using Playwright's powerful selectors.

## 🎯 **Complete Playwright API Coverage**

### **Basic Browser Actions**
```yaml
- action: Open browser
  url: https://example.com
  
- action: Refresh browser

- action: Navigate back

- action: Navigate forward

- action: Take screenshot
  name: page_state
```

### **Playwright Native Locators**
```yaml
# page.get_by_role() equivalent
- action: Get by role
  role: button
  name: Submit
  description: Click button with role and name

# page.get_by_text() equivalent  
- action: Get by text
  text: "Login"
  exact: false
  
# page.get_by_label() equivalent
- action: Get by label
  label: "Username"
  action_type: fill
  value: "myuser"
  
# page.get_by_placeholder() equivalent
- action: Get by placeholder
  placeholder: "Enter email"
  action_type: fill
  value: "test@example.com"
  
# page.get_by_test_id() equivalent
- action: Get by test id
  test_id: login-button
```

### **Mouse Interactions**
```yaml
# page.hover() equivalent
- action: Hover
  selector: ".menu-item"
  
# page.dblclick() equivalent  
- action: Double click
  selector: ".file-item"
  
# page.drag_and_drop() equivalent
- action: Drag and drop
  source: "#item1" 
  target: "#dropzone"
```

### **Keyboard Interactions**
```yaml
# page.press() equivalent
- action: Press key
  key: "Enter"
  selector: "input[name='search']"
  
# page.type() equivalent
- action: Type text
  text: "Hello World"
  selector: ".editor"
```

### **Form Interactions**
```yaml
# Enhanced form filling with smart detection
- action: Fill form field
  field: '[role="textbox"][name="Name"]'
  value: "test-value"
  
# page.select_option() equivalent
- action: Select option
  selector: "select[name='country']"
  value: "US"
  # or
  label: "United States"
  
# page.check() / page.uncheck() equivalent
- action: Check checkbox
  selector: "#agree-terms"
  checked: true
  
- action: Uncheck checkbox  
  selector: "#newsletter"
  checked: false
```

### **File Operations**
```yaml
# page.set_input_files() equivalent
- action: Upload file
  selector: "input[type='file']"
  file_path: "/path/to/file.pdf"
```

### **Waiting and Timing**
```yaml
# page.wait_for_selector() equivalent
- action: Wait for element
  selector: ".loading-spinner"
  state: hidden
  timeout: 5000
  
# Custom text waiting
- action: Wait for text
  text: "Success!"
  timeout: 10000
```

### **Advanced Selectors**
```yaml
# Enhanced click with XPath support
- action: Click element
  selector: "//button[contains(text(), 'Save')]"
  
# CSS selectors with complex attributes
- action: Click element
  selector: '[data-testid="submit"][aria-label*="Save"]'
```

### **Verification (Playwright expect API)**
```yaml
# expect(page.locator("html")).to_contain_text() equivalent
- action: Verify text
  text: "Welcome back!"
  
# Get element information
- action: Get element text
  selector: ".status"
  store_as: status_text
  
- action: Get element attribute
  selector: "#user-id"
  attribute: "data-user-id"
  store_as: user_id
```

### **JavaScript Execution**
```yaml
# page.evaluate() equivalent
- action: Execute script
  script: "document.querySelector('.modal').style.display = 'none'"
  store_as: result
```

### **Browser Management**
```yaml
# Viewport control
- action: Set viewport
  width: 1280
  height: 720
  
# Cookie management  
- action: Add cookie
  name: "session"
  value: "abc123"
  domain: ".example.com"
  
- action: Clear cookies
```

## 🔄 **Conversion from Playwright Recordings**

### **From Playwright Chrome Extension**
Your original Playwright recording:
```javascript
await page.goto("http://192.168.100.8/main");
await page.locator(".flex-none.flex > a").first.click();
await page.get_by_role("textbox", { name: "Name" }).click();
await page.get_by_role("textbox", { name: "Name" }).fill("RX-D46A9121077B");
await page.locator(".btn.btn-outline").first.click();
await page.get_by_role("textbox", { name: "Name" }).click({ button: "right" });
await expect(page.locator("html")).to_contain_text("RX-D46A9121077B");
```

Converts to Easy BDD YAML:
```yaml
name: Device Configuration Test
description: Converted from Playwright recording
tags: [browser, playwright, recorded]

steps:
  - action: Open browser
    url: http://192.168.100.8/main
    
  - action: Click element
    selector: .flex-none.flex > a
    
  - action: Get by role
    role: textbox
    name: Name
    
  - action: Get by role  
    role: textbox
    name: Name
    action_type: fill
    value: RX-D46A9121077B
    
  - action: Click element
    selector: .btn.btn-outline
    
  - action: Get by role
    role: textbox  
    name: Name
    button: right
    
  - action: Verify text
    text: RX-D46A9121077B
```

### **From Katalon Recordings**
Complex XPath selectors are automatically handled:
```yaml
- action: Click element
  selector: (.//*[normalize-space(text()) and normalize-space(.)='STOPPED'])[13]/following::a[3]
```

## 🎪 **Key Features**

✅ **Complete API Coverage**: Every Playwright method has a YAML equivalent  
✅ **Smart Selector Fallbacks**: When exact selectors fail, tries alternatives automatically  
✅ **XPath Support**: Full XPath expression support for complex selectors  
✅ **Variable Integration**: Use `${variable}` syntax in any field  
✅ **Error Recovery**: Helpful debugging when elements aren't found  
✅ **Recording Conversion**: Seamless conversion from Playwright/Katalon recordings  
✅ **Native expect() API**: Text verification uses Playwright's built-in assertions  

## 📝 **Usage Examples**

Create comprehensive tests mixing different API patterns:

```yaml
name: E2E User Registration Flow
variables:
  email: test@example.com
  password: SecurePass123

steps:
  - action: Open browser
    url: https://app.example.com/register
    
  - action: Get by label
    label: Email Address
    action_type: fill
    value: ${email}
    
  - action: Get by placeholder
    placeholder: Password
    action_type: fill  
    value: ${password}
    
  - action: Get by role
    role: button
    name: Create Account
    
  - action: Wait for text
    text: Welcome!
    timeout: 5000
    
  - action: Verify text
    text: ${email}
    
  - action: Take screenshot
    name: registration_success
```

The framework automatically handles all the Playwright API complexity while keeping your tests readable and maintainable!