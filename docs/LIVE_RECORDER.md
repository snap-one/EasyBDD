# Easy BDD Live UI Recorder

Record browser interactions and automatically convert them to Easy BDD YAML format.

## Quick Start

### Method 1: Interactive Recording (Recommended)

```bash
python record_test.py -i https://app.ovrc.com
```

This will:
1. Open Playwright Inspector at your URL
2. Let you perform actions in the browser
3. Copy the generated Playwright code
4. Paste it into the terminal
5. Automatically convert to Easy BDD YAML

### Method 2: Python Module

```bash
python -m easy_bdd.tools.live_recorder -i https://yourapp.com -o tests/cases/my_test.yaml
```

## Usage Examples

### Record Login Flow
```bash
python record_test.py -i https://app.ovrc.com -o tests/cases/ovrc-login.yaml
```

### Record Device Configuration
```bash
python record_test.py -i https://app.ovrc.com/#/devices -o tests/cases/device-config.yaml
```

### Record Without Starting URL
```bash
python record_test.py -i -o tests/cases/my_test.yaml
```

## How It Works

1. **Launch Playwright Inspector**: Opens browser with recording tools
2. **Perform Actions**: Click, fill forms, navigate - all recorded
3. **Generate Code**: Playwright creates Python code for your actions
4. **Auto-Convert**: Code is parsed and converted to Easy BDD YAML
5. **Save Test**: YAML test file is saved and ready to run

## Supported Actions

The recorder automatically converts these Playwright actions:

- ✅ `goto(url)` → Open browser
- ✅ `get_by_role(role, name).click()` → Click element with role/name
- ✅ `get_by_text(text).click()` → Click text
- ✅ `get_by_label(label).fill(value)` → Fill form field by label
- ✅ `get_by_placeholder(text).fill(value)` → Fill by placeholder
- ✅ `locator(selector).click()` → Click element
- ✅ `locator(selector).fill(value)` → Fill form field
- ✅ `locator(selector).select_option(value)` → Select dropdown option
- ✅ `press(key)` → Press keyboard key
- ✅ `wait_for_selector(selector)` → Wait for element
- ✅ `screenshot()` → Take screenshot

## Interactive Mode Workflow

```bash
$ python record_test.py -i https://app.ovrc.com

🎬 Starting Interactive Easy BDD Recorder
============================================================
📝 Recording to: tests/cases/recorded_test.yaml

Instructions:
1. Browser will open
2. Perform your test actions
3. Copy the generated Playwright code when done
4. Paste it here to convert to YAML
============================================================

🌐 Opening: https://app.ovrc.com

⏳ Waiting for recording...
When done, paste the Playwright code here (Ctrl+D when finished):

[paste your Playwright code]
[press Ctrl+D]

✅ Test saved to: tests/cases/recorded_test.yaml
📊 Recorded 8 steps

Preview:
------------------------------------------------------------
  1. Open browser: https://app.ovrc.com
  2. Fill form field: Fill field with placeholder: Email
  3. Fill form field: Fill field with placeholder: Password
  4. Click element: Click button: Log In
  5. Click element: Click text: Devices
  ... and 3 more steps
------------------------------------------------------------
```

## Tips

### 1. Use Playwright Inspector Features
- **Explore mode**: Click the "Explore" button to test selectors
- **Pick locator**: Use the target icon to find best selectors
- **Copy selector**: Right-click elements to copy various selector types

### 2. Clean Up After Recording
The generated YAML might need minor adjustments:
- Add meaningful test name and description
- Extract repeated values to variables
- Add waits if needed for dynamic content
- Group related actions with comments

### 3. Combine with Shared Steps
After recording, you can extract common flows:

```yaml
# Original recorded test
steps:
  - action: Fill form field
    field: 'input[placeholder="Email"]'
    value: "user@example.com"
  - action: Fill form field
    field: 'input[placeholder="Password"]'
    value: "password123"
  - action: Click element
    role: "button"
    name: "Log In"
```

Extract to shared step:
```yaml
# In shared_steps.yaml
login_flow:
  steps:
    - action: Fill form field
      field: 'input[placeholder="Email"]'
      value: "${email}"
    # ... etc
```

Then use in your test:
```yaml
steps:
  - shared_step: "login_flow"
    parameters:
      email: "${email}"
      password: "${password}"
```

## Command Line Options

```
python record_test.py [-h] [-o OUTPUT] [-i] [url]

positional arguments:
  url                   Starting URL (optional)

options:
  -h, --help            Show help message
  -o, --output OUTPUT   Output YAML file path
  -i, --interactive     Interactive mode (paste Playwright code)
```

## Troubleshooting

### Playwright Not Found
```bash
pip install playwright
playwright install
```

### No Actions Recorded
Make sure you're copying the Playwright code that includes `page.` methods:
```python
await page.goto("https://example.com")
await page.get_by_label("Email").fill("test@example.com")
await page.get_by_role("button", name="Submit").click()
```

### Selector Not Working
Use Playwright Inspector's "Pick locator" feature to find more reliable selectors. The recorder will convert them automatically.

## Advanced: Custom Parsing

You can extend the parser for custom actions by editing:
`easy_bdd/tools/live_recorder.py`

Add new patterns to the `parse_playwright_line()` method.

## Examples

### Example 1: Record Complete Login Test
```bash
python record_test.py -i https://app.ovrc.com -o tests/cases/login-test.yaml
```

In browser:
1. Fill email field
2. Fill password field
3. Click "Log In" button
4. Wait for dashboard
5. Close browser

Result: `tests/cases/login-test.yaml` with all steps

### Example 2: Record Device Configuration
```bash
python record_test.py -i -o tests/cases/device-setup.yaml
```

1. Navigate to device page
2. Click device
3. Fill configuration form
4. Select dropdown options
5. Click Save
6. Close browser

Result: Complete device configuration test

## Integration with Easy BDD

After recording, run your test:
```bash
python -m easy_bdd run tests/cases/recorded_test.yaml --headed
```

Or add to test suite:
```bash
python -m easy_bdd run tests/cases/ --tags recorded
```

## See Also

- [Chrome Recorder Conversion](../docs/CHROME_RECORDER_CONVERSION.md)
- [Browser Actions Reference](../docs/actions.md)
- [Test Syntax Guide](../docs/syntax.md)
