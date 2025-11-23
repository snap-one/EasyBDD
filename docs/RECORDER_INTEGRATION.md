# Easy BDD Framework - UI Recorder Integration

## Overview

The Easy BDD Framework now includes comprehensive UI recorder integration, allowing you to convert recorded browser interactions into Easy BDD test definitions.

## Supported Recording Formats

### Playwright
- **Playwright Test Generator**: JSON format with `actions` array
- **Playwright Codegen**: Code-based recordings with `steps` array

### Selenium
- **Selenium IDE**: JSON format with `tests` and `commands`

### Cypress
- **Cypress Test Runner**: JSON format with `commands` array

### Puppeteer
- **Puppeteer recordings**: JSON format with page interaction steps

## Usage

### Converting Recorder Files

Convert any supported recorder file to Easy BDD format:

```bash
# Auto-detect format and convert
python -m easy_bdd convert recorded_test.json

# Specify format explicitly
python -m easy_bdd convert recorded_test.json --format-type playwright

# Specify output file
python -m easy_bdd convert recorded_test.json --output my_test.yaml
```

### Direct JSON Import

The framework can also directly import and run JSON recorder files:

```bash
# Generate Gherkin from JSON recording
python -m easy_bdd generate tests/recordings/

# Run tests from JSON recordings
python -m easy_bdd run tests/recordings/
```

## Example Conversions

### Playwright Recording Input
```json
{
  "name": "Login Test",
  "actions": [
    {
      "type": "goto",
      "url": "https://example.com/login"
    },
    {
      "type": "fill",
      "selector": "[name=\"email\"]",
      "value": "test@example.com"
    },
    {
      "type": "click",
      "selector": "button[type=\"submit\"]"
    }
  ]
}
```

### Easy BDD Output
```yaml
name: Login Test
description: Auto-generated from recording
tags:
  - browser
  - recorded
  - playwright
variables:
  base_url: https://example.com
steps:
  - action: Open browser
    url: https://example.com/login
  - action: Fill form field
    field: email
    value: test@example.com
  - action: Click element
    selector: button[type="submit"]
```

### Generated Gherkin
```gherkin
Feature: Login Test

  Auto-generated from recording

  @browser @recorded @playwright
  Scenario: Login Test
    Given I open a browser to "https://example.com/login"
    When I fill the "email" field with "test@example.com"
    When I click on element "button[type=\"submit\"]"
```

## Action Mapping

The converter automatically maps recorder actions to Easy BDD actions:

| Recorder Action | Easy BDD Action | Parameters |
|----------------|----------------|------------|
| `goto` | `Open browser` | `url` |
| `click` | `Click element` | `selector` |
| `fill` | `Fill form field` | `field`, `value` |
| `press` | `Press key` | `key` |
| `wait` | `Wait for element` | `selector`, `timeout` |
| `screenshot` | `Take screenshot` | `name` |

## Advanced Features

### Smart Field Detection
The converter automatically detects form field names from selectors:
- `[name="email"]` → `field: email`
- `#username` → `field: username`
- `input[placeholder="Password"]` → `field: password`

### Variable Extraction
Automatically extracts and creates variables for:
- Base URLs
- Common form values
- Repeated selectors

### MCP Integration
Enhanced Playwright integration with Model Context Protocol support:
- Browser automation recording
- Smart element detection
- Network request interception
- Accessibility testing

## CLI Commands

```bash
# Convert recorder file
python -m easy_bdd convert recording.json

# Generate features
python -m easy_bdd generate tests/

# Run tests
python -m easy_bdd run tests/

# Get help
python -m easy_bdd --help
python -m easy_bdd convert --help
```

## File Structure

```
tests/
├── cases/
│   ├── manual_test.yaml           # Hand-written tests
│   ├── recorded_login.json        # Raw recorder file
│   └── recorded_login_converted.yaml  # Converted test
├── features/
│   ├── manual_test.feature        # Generated Gherkin
│   └── recorded_login_converted.feature
└── recordings/
    ├── playwright_recordings/
    ├── selenium_recordings/
    └── cypress_recordings/
```

This integration makes it easy to capture browser interactions and convert them into maintainable, readable test definitions that can be edited and extended by both technical and non-technical team members.