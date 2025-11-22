# Examples Gallery

Real-world examples demonstrating Easy BDD Framework capabilities.

## 🌟 Basic Examples

### Simple Web Test
```yaml
name: Basic Web Navigation
description: Navigate website and verify content
tags: [web, basic]

variables:
  site_url: "https://example.com"

steps:
  - action: Open browser
    url: ${site_url}
    
  - action: Take screenshot
    name: "homepage"
    
  - action: Verify text
    text: "Example Domain"
```

### Login Test
```yaml
name: User Login Test
description: Test user authentication flow
tags: [auth, critical]

variables:
  app_url: "https://app.example.com"
  username: "test@example.com"
  password: "TestPass123"

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
    
  - action: Wait for element
    selector: ".dashboard"
    state: "visible"
    
  - action: Verify text
    text: "Welcome"
    
  - action: Take screenshot
    name: "dashboard"
```

## 📊 Data-Driven Examples

### Multi-User Testing
```yaml
name: Multi-User Account Test
description: Test multiple user roles and permissions
tags: [users, data-driven]

async_execution: false

variables:
  app_url: "https://admin.example.com"

data:
  - username: "admin@company.com"
    password: "admin123"
    role: "administrator"
    expected_menu: "Admin Panel"
    
  - username: "manager@company.com"
    password: "manager123"
    role: "manager"
    expected_menu: "Management"
    
  - username: "user@company.com"
    password: "user123"
    role: "user"
    expected_menu: "Dashboard"

steps:
  - action: Open browser
    url: ${app_url}
    
  - action: Fill form field
    field: "#username"
    value: ${username}
    
  - action: Fill form field
    field: "#password"
    value: ${password}
    
  - action: Click element
    selector: "#login-btn"
    
  - action: Take screenshot
    name: "${role}-dashboard"
    
  - action: Verify text
    text: ${expected_menu}
```

### Device Configuration (Async)
```yaml
name: Multi-Device Configuration
description: Configure multiple devices simultaneously
tags: [devices, async]

async_execution: true
max_workers: 3

variables:
  admin_url: "http://192.168.1.100"

data:
  - device_id: "DEV001"
    device_name: "Living Room TV"
    location: "Living Room"
    
  - device_id: "DEV002"
    device_name: "Bedroom TV"
    location: "Bedroom"
    
  - device_id: "DEV003"
    device_name: "Kitchen Display"
    location: "Kitchen"

setup:
  - action: Take screenshot
    name: "pre-config-${device_id}"

steps:
  - action: Open browser
    url: ${admin_url}/devices/${device_id}
    
  - action: Fill form field
    field: "[name='device_name']"
    value: ${device_name}
    
  - action: Fill form field
    field: "[name='location']"
    value: ${location}
    
  - action: Click element
    selector: ".save-btn"
    
  - action: Take screenshot
    name: "configured-${device_id}"

cleanup:
  - action: Navigate back
  - action: Take screenshot
    name: "post-config-${device_id}"
```

## 🎯 Advanced Examples

### E-commerce Testing
```yaml
name: E-commerce Purchase Flow
description: Complete purchase workflow test
tags: [ecommerce, integration]

variables:
  shop_url: "https://shop.example.com"
  customer_email: "customer@example.com"
  credit_card: "4111111111111111"

setup:
  - action: Open browser
    url: ${shop_url}
    
  - action: Take screenshot
    name: "store-homepage"

steps:
  - action: Click element
    selector: ".product-card:first-child"
    description: "Select first product"
    
  - action: Wait for element
    selector: ".product-details"
    
  - action: Click element
    selector: ".add-to-cart"
    
  - action: Wait for element
    selector: ".cart-notification"
    
  - action: Click element
    selector: ".cart-icon"
    
  - action: Click element
    selector: ".checkout-btn"
    
  - action: Fill form field
    field: "[name='email']"
    value: ${customer_email}
    
  - action: Fill form field
    field: "[name='card_number']"
    value: ${credit_card}
    
  - action: Select option
    selector: "[name='exp_month']"
    value: "12"
    
  - action: Select option
    selector: "[name='exp_year']"
    value: "2025"
    
  - action: Fill form field
    field: "[name='cvv']"
    value: "123"
    
  - action: Click element
    selector: ".place-order"
    
  - action: Wait for element
    selector: ".order-confirmation"
    timeout: 15000
    
  - action: Verify text
    text: "Order confirmed"
    
  - action: Take screenshot
    name: "order-confirmation"

cleanup:
  - action: Take screenshot
    name: "final-state"
```

### Form Validation Testing
```yaml
name: Form Validation Test
description: Test form validation rules
tags: [forms, validation]

variables:
  form_url: "https://forms.example.com/contact"

data:
  - test_case: "empty_fields"
    name: ""
    email: ""
    message: ""
    expected_error: "All fields are required"
    
  - test_case: "invalid_email"
    name: "John Doe"
    email: "invalid-email"
    message: "Test message"
    expected_error: "Please enter a valid email"
    
  - test_case: "valid_submission"
    name: "John Doe"
    email: "john@example.com"
    message: "This is a test message"
    expected_error: null

steps:
  - action: Open browser
    url: ${form_url}
    
  - action: Fill form field
    field: "[name='name']"
    value: ${name}
    
  - action: Fill form field
    field: "[name='email']"
    value: ${email}
    
  - action: Fill form field
    field: "[name='message']"
    value: ${message}
    
  - action: Click element
    selector: ".submit-btn"
    
  - action: Take screenshot
    name: "${test_case}-result"
    
  # Conditional verification based on test case
  - action: Verify text
    text: ${expected_error}
    # Only verify error if expected_error is not null
```

## 🔄 Setup and Cleanup Examples

### Database Setup Test
```yaml
name: User Management with DB Setup
description: Test user operations with database preparation
tags: [database, users]

variables:
  admin_url: "https://admin.example.com"
  test_user_email: "testuser@example.com"

setup:
  - action: API request
    url: "https://api.example.com/test/reset"
    method: "POST"
    description: "Reset test database"
    
  - action: API request
    url: "https://api.example.com/test/seed"
    method: "POST"
    description: "Seed test data"
    
  - action: Wait
    time: 2
    description: "Wait for database to stabilize"

steps:
  - action: Open browser
    url: ${admin_url}/users
    
  - action: Click element
    selector: ".add-user-btn"
    
  - action: Fill form field
    field: "[name='email']"
    value: ${test_user_email}
    
  - action: Click element
    selector: ".save-btn"
    
  - action: Verify text
    text: "User created successfully"
    
  - action: Take screenshot
    name: "user-created"

cleanup:
  - action: API request
    url: "https://api.example.com/users/${test_user_email}"
    method: "DELETE"
    description: "Clean up test user"
    
  - action: Take screenshot
    name: "cleanup-complete"
```

### Environment Setup Test
```yaml
name: Environment Configuration Test
description: Test with specific environment setup
tags: [environment, config]

variables:
  config_url: "https://config.example.com"

setup:
  - action: Open browser
    url: ${config_url}
    
  - action: Click element
    selector: ".reset-config"
    description: "Reset to default configuration"
    
  - action: Wait for element
    selector: ".config-reset-complete"
    
  - action: Take screenshot
    name: "environment-reset"

steps:
  - action: Click element
    selector: ".advanced-settings"
    
  - action: Fill form field
    field: "[name='timeout']"
    value: "5000"
    
  - action: Click element
    selector: ".apply-settings"
    
  - action: Wait for element
    selector: ".settings-applied"
    
  - action: Take screenshot
    name: "settings-configured"

cleanup:
  - action: Click element
    selector: ".reset-config"
    description: "Restore default settings"
    
  - action: Wait for element
    selector: ".config-reset-complete"
    
  - action: Take screenshot
    name: "environment-restored"
```

## 📱 Mobile Testing Examples

### Mobile App Testing (Future)
```yaml
name: Mobile App Navigation
description: Test mobile app functionality
tags: [mobile, navigation]

variables:
  app_id: "com.example.app"

steps:
  - action: Launch app
    app: ${app_id}
    
  - action: Tap element
    selector: "text=Login"
    
  - action: Fill field
    field: "[placeholder='Email']"
    value: "test@example.com"
    
  - action: Tap element
    selector: "text=Sign In"
    
  - action: Wait for element
    selector: "text=Dashboard"
    
  - action: Swipe
    direction: "left"
    
  - action: Take screenshot
    name: "mobile-dashboard"
```

## 🔗 API Testing Examples

### REST API Testing (Future)
```yaml
name: API Endpoint Validation
description: Test REST API endpoints
tags: [api, rest]

variables:
  api_base: "https://api.example.com"
  auth_token: "Bearer xyz123"

data:
  - endpoint: "/users"
    method: "GET"
    expected_status: 200
    
  - endpoint: "/users/123"
    method: "GET"
    expected_status: 200
    
  - endpoint: "/users/999"
    method: "GET"
    expected_status: 404

steps:
  - action: API request
    url: ${api_base}${endpoint}
    method: ${method}
    headers:
      Authorization: ${auth_token}
    
  - action: Verify status
    status: ${expected_status}
    
  - action: Take screenshot
    name: "api-${endpoint//\//-}-response"
```

## 🎨 Custom Examples

### File Upload Test
```yaml
name: File Upload Test
description: Test file upload functionality
tags: [upload, files]

variables:
  upload_url: "https://upload.example.com"
  test_file: "./data/test-document.pdf"

steps:
  - action: Open browser
    url: ${upload_url}
    
  - action: Upload file
    selector: "[type='file']"
    file_path: ${test_file}
    
  - action: Click element
    selector: ".upload-btn"
    
  - action: Wait for element
    selector: ".upload-success"
    timeout: 30000
    
  - action: Verify text
    text: "File uploaded successfully"
    
  - action: Take screenshot
    name: "upload-complete"
```

### Performance Testing
```yaml
name: Page Load Performance
description: Test page load times
tags: [performance, timing]

variables:
  app_url: "https://app.example.com"

steps:
  - action: Open browser
    url: ${app_url}
    
  - action: Wait for element
    selector: "body"
    state: "visible"
    
  - action: Take screenshot
    name: "page-loaded"
    
  # Framework automatically captures timing metrics
  - action: Verify text
    text: "Welcome"
```

---

*These examples demonstrate the flexibility and power of the Easy BDD Framework. Mix and match patterns to create tests suited to your specific needs.*