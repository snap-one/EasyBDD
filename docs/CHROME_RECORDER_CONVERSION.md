# Converting Chrome Recorder Tests to Easy BDD

## Overview

This guide explains how to convert Chrome DevTools Recorder exports into executable Easy BDD tests.

## Quick Start

### Step 1: Record in Chrome

1. Open Chrome DevTools (F12 or Cmd+Option+I)
2. Go to the **Recorder** tab
3. Click **Create a new recording**
4. Perform your test actions on the website
5. Click **Export** → **Export as JSON**
6. Save the file (e.g., `my-test.json`)

### Step 2: Convert to YAML

Run the converter script:

```bash
python convert_chrome_recording.py your-recording.json
```

This creates `tests/cases/your-recording.yaml`

### Step 3: Review & Edit

Open the generated YAML file and:
- Add variables for reusable values (URLs, credentials)
- Add assertions/verifications
- Clean up selectors if needed
- Add waits where necessary

### Step 4: Run Your Test

```bash
python -m easy_bdd run tests/cases/your-recording.yaml
```

## Example Conversion

### Input (Chrome Recorder JSON)

```json
{
    "title": "Login Test",
    "steps": [
        {
            "type": "navigate",
            "url": "https://example.com/login"
        },
        {
            "type": "click",
            "selectors": [["aria/Email"]]
        },
        {
            "type": "change",
            "value": "user@example.com",
            "selectors": [["aria/Email"]]
        }
    ]
}
```

### Output (Easy BDD YAML)

```yaml
name: Login Test
description: Auto-converted from Chrome Recorder
tags:
  - browser
  - recorded
steps:
  - action: Open browser
    url: https://example.com/login
  
  - action: Click element
    selector: aria/Email
    description: 'Click: Email'
  
  - action: Fill form field
    field: aria/Email
    value: user@example.com
    description: Enter "user@example.com" into Email
```

## Supported Chrome Recorder Actions

| Chrome Recorder | Easy BDD Action | Notes |
|-----------------|-----------------|-------|
| `navigate` | `Open browser` | Navigates to URL |
| `click` | `Click element` | Clicks element using selector |
| `change` / `fill` | `Fill form field` | Enters text into input |
| `keyUp` | `Press key` | Simulates keyboard input |
| `setViewport` | `Set viewport` | Sets browser window size |
| `waitForElement` | `Wait for element` | Waits for element visibility |

## Improving Converted Tests

### 1. Add Variables

**Before:**
```yaml
steps:
  - action: Open browser
    url: https://app.ovrc.com/#/login
  - action: Fill form field
    field: aria/Email
    value: jpdsauto@gmail.com
```

**After (with variables):**
```yaml
variables:
  base_url: "https://app.ovrc.com"
  test_email: "jpdsauto@gmail.com"
  test_password: "Snapone704!"

steps:
  - action: Open browser
    url: "${base_url}/#/login"
  
  - action: Fill form field
    field: aria/Email
    value: "${test_email}"
  
  - action: Fill form field
    field: aria/Password
    value: "${test_password}"
```

### 2. Add Verifications

Chrome Recorder doesn't capture assertions - add them manually:

```yaml
steps:
  - action: Click element
    selector: aria/LOG IN
    description: 'Click: LOG IN'
  
  # Add verification after login
  - action: Verify text
    text: "Welcome"
    description: "Verify successful login"
  
  - action: Verify element visible
    selector: ".user-profile"
```

### 3. Add Waits

Chrome Recorder timing may not be reliable - add explicit waits:

```yaml
steps:
  - action: Click element
    selector: aria/Submit
  
  # Add wait for page to load
  - action: Wait for element
    selector: ".dashboard"
    timeout: 10
```

### 4. Clean Up Selectors

Chrome Recorder may generate fragile selectors:

**Before:**
```yaml
- action: Click element
  selector: '#root > div.MuiBox-root > div > button'
```

**After (more robust):**
```yaml
- action: Click element
  selector: aria/Submit Button
  # or
  selector: 'button:has-text("Submit")'
```

### 5. Remove Redundant Steps

Chrome Recorder captures every action:

**Before:**
```yaml
- action: Click element
  selector: aria/Password
- action: Fill form field
  field: aria/Password
  value: S
- action: Press key
  key: s
- action: Fill form field
  field: aria/Password
  value: Snapone704!
```

**After (cleaned up):**
```yaml
- action: Fill form field
  field: aria/Password
  value: Snapone704!
```

## Advanced: Custom Converter Usage

You can customize the conversion script for your needs:

```python
from convert_chrome_recording import convert_chrome_recorder

# Convert with custom output path
convert_chrome_recorder(
    'my-recording.json',
    'tests/cases/custom/my-test.yaml'
)

# Or use as a library
test_def = convert_chrome_recorder('recording.json')
# Modify test_def dict as needed
```

## Selector Types in Converted Tests

| Selector Type | Example | Notes |
|---------------|---------|-------|
| ARIA Label | `aria/Email` | Best for accessibility |
| ID | `#login-button` | Fast and reliable |
| CSS | `.submit-btn` | Flexible |
| Text | `text/Submit` | Readable but can break |
| XPath | `xpath///*[@id="btn"]` | Powerful but verbose |

## Best Practices

1. **Review Before Running**: Always check converted tests before execution
2. **Use Variables**: Extract reusable values (URLs, credentials, test data)
3. **Add Assertions**: Verify expected outcomes explicitly
4. **Prefer ARIA Selectors**: They're more stable and accessible
5. **Add Comments**: Document complex workflows
6. **Test Incrementally**: Run small sections to debug issues
7. **Version Control**: Commit both JSON and YAML for traceability

## Common Issues

### Issue: Selectors Don't Work

**Symptom**: Element not found errors

**Solution**: Update selectors to be more robust:
```yaml
# Instead of generated:
selector: '#root > div:nth-child(2) > button'

# Use:
selector: 'button:has-text("Login")'
# or
selector: 'aria/Login Button'
```

### Issue: Timing Problems

**Symptom**: Tests fail intermittently

**Solution**: Add explicit waits:
```yaml
- action: Click element
  selector: aria/Submit

- action: Wait for element
  selector: '.success-message'
  timeout: 10
```

### Issue: Dynamic IDs

**Symptom**: Selectors with `:r0:`, `:r1:` fail

**Solution**: Use stable attributes:
```yaml
# Instead of:
selector: '#:r0:'

# Use:
selector: 'input[placeholder="Email"]'
# or
selector: 'aria/Email'
```

## Integration with Test Suites

### Organize Converted Tests

```
tests/cases/
├── recorded/           # All Chrome Recorder conversions
│   ├── login_flow.yaml
│   ├── checkout.yaml
│   └── search.yaml
├── api/               # API tests
└── manual/            # Hand-written tests
```

### Tag Appropriately

```yaml
name: OvrC Login Flow
tags:
  - browser
  - recorded          # Indicates it's a converted test
  - chrome           # Source tool
  - smoke            # Test type
  - authentication   # Feature area
```

## See Also

- [Browser Actions Reference](./actions.md#browser-actions)
- [Variables Guide](./CENTRALIZED_VARIABLES.md)
- [Selector Strategies](./BROWSER_CONFIG.md#selectors)
- [Troubleshooting Guide](./troubleshooting.md)
