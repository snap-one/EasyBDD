# Using Katalon JSON with Easy BDD Framework

## Quick Start

You can now directly use your Katalon JSON data with the Easy BDD Framework in three ways:

### Method 1: Direct JSON Processing (Recommended)

Put your Katalon JSON in the test cases folder and run directly:

```bash
# 1. Save your JSON as tests/cases/my_katalon_test.json
# 2. Generate and run directly
python -m easy_bdd generate tests/cases/my_katalon_test.json
python -m easy_bdd run tests/cases/my_katalon_test.json
```

### Method 2: Convert to YAML First

```bash
# Convert to YAML for editing
python -m easy_bdd convert tests/cases/my_katalon_test.json

# This creates: tests/cases/my_katalon_test_converted.yaml
# Then generate and run
python -m easy_bdd generate tests/cases/my_katalon_test_converted.yaml
```

### Method 3: Specify Format Explicitly

```bash
# If auto-detection fails, specify Katalon format
python -m easy_bdd convert tests/cases/my_test.json --format-type katalon
```

## Your Specific Test

Your Katalon JSON has been converted to:

**Original JSON Structure:**
- `open` command → Opens browser to http://192.168.100.8/group_tx/1038
- Multiple `click` commands → Clicks on various XPath elements
- `type` commands → Fills form fields with "B-960-MOIP-4K-TR"

**Converted to Easy BDD:**
```yaml
name: Katalon Test
description: Auto-generated from Katalon Studio recording
tags:
  - browser
  - recorded  
  - katalon
variables:
  base_url: http://192.168.100.8
steps:
  - action: Open browser
    url: http://192.168.100.8/group_tx/1038
  - action: Click element
    selector: (.//*[normalize-space(text()) and normalize-space(.)='STOPPED'])[13]/following::a[3]
  # ... more click actions
  - action: Fill form field
    field: field_with_value_b_960_moip_4k_tr
    value: B-960-MOIP-4K-TR
  # ... more actions
```

**Generated Gherkin:**
```gherkin
Feature: Katalon Test
  
  Auto-generated from Katalon Studio recording
  
  @browser @recorded @katalon
  Scenario: Katalon Test
    Given I open a browser to "http://192.168.100.8/group_tx/1038"
    When I click on element "(.//*[normalize-space(text()) and normalize-space(.)='STOPPED'])[13]/following::a[3]"
    When I fill the "field_with_value_b_960_moip_4k_tr" field with "B-960-MOIP-4K-TR"
    # ... more steps
```

## Supported Katalon Commands

The framework automatically converts these Katalon commands:

| Katalon Command | Easy BDD Action | Notes |
|-----------------|-----------------|-------|
| `open` | `Open browser` | Extracts base URL as variable |
| `click` | `Click element` | Preserves XPath selectors |
| `type` | `Fill form field` | Smart field name extraction |
| `waitForElementPresent` | `Wait for element` | 30 second default timeout |
| `assertElementPresent` | `Verify element exists` | Element verification |
| `assertText` | `Verify text` | Text content verification |

## Next Steps

1. **Review the converted YAML** - Edit field names, add descriptions, group related steps
2. **Add assertions** - Include verification steps for expected results  
3. **Use variables** - Replace hard-coded values with `${variable}` syntax
4. **Run tests** - Execute with `python -m easy_bdd run tests/cases/`

## Example Enhanced Version

```yaml
name: "Device Configuration Test"
description: "Test configuring B-960-MOIP-4K-TR device in group TX"
tags: ["browser", "device-config", "regression"]

variables:
  base_url: "http://192.168.100.8"
  device_name: "B-960-MOIP-4K-TR"
  group_id: "1038"

steps:
  - action: "Open browser"
    url: "${base_url}/group_tx/${group_id}"
    
  - action: "Click element"
    selector: "(.//*[normalize-space(text()) and normalize-space(.)='STOPPED'])[13]/following::a[3]"
    description: "Click on device configuration button"
    
  - action: "Fill form field" 
    field: "device_name"
    value: "${device_name}"
    description: "Enter device name"
    
  - action: "Click element"
    selector: "(.//*[normalize-space(text()) and normalize-space(.)='Name'])[1]/following::*[name()='svg'][1]"
    description: "Save configuration"
    
  - action: "Verify text"
    text: "Configuration saved successfully"
    description: "Confirm save was successful"
```

The framework handles all the conversion automatically - just save your Katalon JSON and run!