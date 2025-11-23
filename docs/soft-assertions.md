# Soft Assertions Guide

## Overview

Soft assertions allow your tests to continue executing even when assertions fail, collecting all failures to report at the end. This is invaluable when you want to validate multiple conditions without stopping at the first failure.

## Why Use Soft Assertions?

### Traditional (Hard) Assertions
```yaml
steps:
  - action: Verify text
    text: "Welcome"
  
  - action: Verify element
    selector: "#submit-button"  # Test stops here if first verification fails!
  
  - action: Verify text
    text: "Total: $100"  # Never executed if earlier steps fail
```

### With Soft Assertions
```yaml
steps:
  - action: Verify text
    text: "Welcome"
    soft_assert: true  # Continues even if fails
  
  - action: Verify element
    selector: "#submit-button"
    soft_assert: true  # Still executes
  
  - action: Verify text
    text: "Total: $100"
    soft_assert: true  # All validations run
  
  - action: Check soft assertions  # Fails test if any soft assertions failed
```

## Use Cases

### 1. Form Validation
Validate all form fields in one test run:

```yaml
name: Form Validation Test
description: Validate all required form fields

steps:
  - action: Open browser
    url: "https://example.com/form"
  
  - action: Fill form field
    selector: "#name"
    value: ""
  
  - action: Fill form field
    selector: "#email"
    value: "invalid-email"
  
  - action: Click element
    button: "Submit"
  
  # Check all error messages
  - action: Verify text
    text: "Name is required"
    soft_assert: true
  
  - action: Verify text
    text: "Invalid email format"
    soft_assert: true
  
  - action: Verify element
    selector: ".error-icon"
    soft_assert: true
  
  # Fail test if any validations failed
  - action: Check soft assertions
```

### 2. UI Component Verification
Verify multiple elements exist on a dashboard:

```yaml
name: Dashboard UI Verification
description: Verify all dashboard components are present

steps:
  - action: Open browser
    url: "https://app.example.com/dashboard"
  
  # Header components
  - action: Verify element
    selector: ".app-logo"
    soft_assert: true
  
  - action: Verify element
    selector: ".user-menu"
    soft_assert: true
  
  - action: Verify text
    text: "Welcome back"
    soft_assert: true
  
  # Main widgets
  - action: Verify element
    selector: "#sales-widget"
    soft_assert: true
  
  - action: Verify element
    selector: "#analytics-widget"
    soft_assert: true
  
  - action: Verify element
    selector: "#tasks-widget"
    soft_assert: true
  
  # Footer
  - action: Verify element
    selector: ".copyright"
    soft_assert: true
  
  - action: Check soft assertions
```

### 3. API Response Validation
Validate multiple fields in an API response:

```yaml
name: API Response Validation
description: Validate all required fields in API response

steps:
  - action: API request
    method: GET
    url: "/api/user/profile"
    store_response: "profile"
  
  # Verify status code
  - action: Assert
    expression: "${profile.status} == 200"
    message: "Expected status 200"
    soft_assert: true
  
  # Verify response structure
  - action: Assert
    expression: "'id' in ${profile.data}"
    message: "Response must contain 'id' field"
    soft_assert: true
  
  - action: Assert
    expression: "'name' in ${profile.data}"
    message: "Response must contain 'name' field"
    soft_assert: true
  
  - action: Assert
    expression: "'email' in ${profile.data}"
    message: "Response must contain 'email' field"
    soft_assert: true
  
  # Verify data types
  - action: Assert
    expression: "isinstance(${profile.data.id}, int)"
    message: "ID must be an integer"
    soft_assert: true
  
  - action: Assert
    expression: "isinstance(${profile.data.name}, str)"
    message: "Name must be a string"
    soft_assert: true
  
  - action: Check soft assertions
```

### 4. Multi-Page Workflow
Continue testing workflow even if validations fail:

```yaml
name: E-Commerce Checkout Flow
description: Test complete checkout process with validations

steps:
  # Step 1: Product page
  - action: Open browser
    url: "https://shop.example.com/product/123"
  
  - action: Verify text
    text: "Product Name"
    soft_assert: true
  
  - action: Verify text
    text: "$99.99"
    soft_assert: true
  
  - action: Click element
    button: "Add to Cart"
  
  # Step 2: Cart page
  - action: Verify text
    text: "Shopping Cart"
    soft_assert: true
  
  - action: Verify text
    text: "Subtotal: $99.99"
    soft_assert: true
  
  - action: Click element
    button: "Proceed to Checkout"
  
  # Step 3: Checkout page
  - action: Verify text
    text: "Checkout"
    soft_assert: true
  
  - action: Verify element
    selector: "#shipping-address"
    soft_assert: true
  
  - action: Verify element
    selector: "#payment-method"
    soft_assert: true
  
  # Check all validations at the end
  - action: Check soft assertions
```

## Supported Actions

Currently, the following actions support the `soft_assert` parameter:

### Browser Actions
- **Verify text** - Check if text appears on page
- **Verify element** - Check if element exists and is visible

### Custom Assertions (Future)
- **Assert** - Custom expression evaluation
- **Assert JSON schema** - JSON schema validation
- **Assert response** - API response validation

## Output Examples

### Console Output
When a soft assertion fails, you'll see a warning in the console:

```
    Step 3/10: Verify text
           → text='Welcome'
    ⚠️  Soft Assertion Failed: Text 'Welcome' not found on page

    Step 4/10: Verify element
           → selector='#submit-button'
    ⚠️  Soft Assertion Failed: Element '#submit-button' not found or not visible

============================================================
SOFT ASSERTION FAILURES: 2 total
============================================================

1. Step 3 (Verify text): Text 'Welcome' not found on page
  Expected: Welcome
  Actual: Empty page

2. Step 4 (Verify element): Element '#submit-button' not found or not visible
  Expected: Element '#submit-button' visible
  Actual: Element not found or not visible
============================================================
```

### HTML Report
In the HTML test report, soft assertion failures are displayed with:
- ⚠️ Warning icon (vs ❌ for hard failures)
- Orange warning box
- List of all failures with step numbers
- Expected vs Actual values

## Best Practices

### 1. Group Related Validations
Use soft assertions for validations that are logically grouped:

```yaml
# ✅ Good: Related field validations
- action: Verify text
  text: "Username is required"
  soft_assert: true

- action: Verify text
  text: "Password is required"
  soft_assert: true

- action: Check soft assertions
```

### 2. Don't Overuse
Not everything should be a soft assertion:

```yaml
# ❌ Bad: Critical action as soft assertion
- action: Click element
  button: "Login"
  soft_assert: true  # Don't do this! Login must succeed

# ✅ Good: Use hard assertions for critical actions
- action: Click element
  button: "Login"  # Fail immediately if this doesn't work
```

### 3. Always Check at End
Remember to check soft assertions:

```yaml
# ❌ Bad: Soft assertions collected but never checked
- action: Verify text
  text: "Welcome"
  soft_assert: true
  # Test passes even though verification failed!

# ✅ Good: Check soft assertions
- action: Verify text
  text: "Welcome"
  soft_assert: true

- action: Check soft assertions  # Fails test if any soft assertions failed
```

### 4. Use Descriptive Test Names
Make it clear when tests use soft assertions:

```yaml
# ✅ Good naming
name: Form Validation - All Fields (Soft Assertions)
description: Validates all form fields without stopping on first error

# ✅ Good naming
name: Dashboard UI - Complete Verification
description: Checks all UI components are present using soft assertions
```

### 5. Strategic Placement
Place "Check soft assertions" at logical checkpoints:

```yaml
steps:
  # Login phase
  - action: Open browser
    url: "https://app.example.com"
  
  - action: Fill form field
    field: "username"
    value: "testuser"
  
  - action: Click element
    button: "Login"
  
  # Validate login page (checkpoint 1)
  - action: Verify text
    text: "Welcome back"
    soft_assert: true
  
  - action: Verify element
    selector: ".user-avatar"
    soft_assert: true
  
  - action: Check soft assertions  # Checkpoint 1
  
  # Navigate to settings
  - action: Click element
    text: "Settings"
  
  # Validate settings page (checkpoint 2)
  - action: Verify text
    text: "Account Settings"
    soft_assert: true
  
  - action: Verify element
    selector: "#profile-form"
    soft_assert: true
  
  - action: Check soft assertions  # Checkpoint 2
```

## Troubleshooting

### Soft Assertions Not Working
If soft assertions aren't being collected:

1. **Check spelling**: Make sure it's `soft_assert: true` (with underscore)
2. **Check indentation**: YAML is indentation-sensitive
3. **Check action support**: Only supported actions can use soft assertions
4. **Check framework version**: Soft assertions require framework v2.0+

### All Tests Passing Despite Failures
If tests pass even though soft assertions failed:

1. **Missing "Check soft assertions"**: You must add this action to fail the test
2. **Incorrect placement**: Must be after soft assertions are added

### Soft Assertions in Setup/Cleanup
Soft assertions work in all phases:

```yaml
setup:
  - action: Verify text
    text: "Test Environment"
    soft_assert: true

steps:
  - action: Check soft assertions  # Checks setup failures too

cleanup:
  - action: Verify text
    text: "Cleanup successful"
    soft_assert: true
```

## Advanced Patterns

### Conditional Checking
Only check soft assertions in certain conditions:

```yaml
variables:
  environment: "staging"

steps:
  - action: Verify text
    text: "Debug Mode"
    soft_assert: true
  
  # Only fail test in production
  - action: Check soft assertions
    condition: "${environment} == 'production'"
```

### Partial Validation
Check soft assertions mid-test:

```yaml
steps:
  # Phase 1 validations
  - action: Verify text
    text: "Step 1 Complete"
    soft_assert: true
  
  - action: Check soft assertions  # Fail if phase 1 issues
  
  # Continue to phase 2
  - action: Click element
    button: "Next"
  
  # Phase 2 validations
  - action: Verify text
    text: "Step 2 Complete"
    soft_assert: true
  
  - action: Check soft assertions  # Fail if phase 2 issues
```

## Comparison: Soft vs Hard Assertions

| Aspect | Hard Assertions | Soft Assertions |
|--------|----------------|-----------------|
| **Test Stops** | Immediately on failure | Continues execution |
| **Failure Info** | First failure only | All failures |
| **Use Case** | Critical validations | Comprehensive checks |
| **Debugging** | Limited info | Complete picture |
| **Report** | Single error | Multiple errors |
| **Test Time** | Shorter (stops early) | Longer (runs all) |

## Future Enhancements

Planned soft assertion features:

- **Soft Assert Limits**: Maximum failures before stopping
- **Soft Assert Groups**: Group related assertions
- **Conditional Soft Asserts**: Enable/disable per environment
- **Soft Assert Severity**: Warning vs Error levels
- **Screenshot on Each Failure**: Capture state at each soft assertion

---

**Updated:** November 22, 2025  
**Version:** 2.0.0  
**Status:** Production Ready
