# Conditional Steps Guide

## Overview

Conditional steps allow you to execute different actions based on runtime conditions. This is useful for:
- Version-dependent upgrade logic
- Environment-specific behavior
- Dynamic test flows based on state
- Skipping steps when conditions aren't met

## Syntax

### Basic If/Then

```yaml
- condition: "expression"
  then:
    - action: "Action if true"
      parameter: "value"
```

### If/Then/Else

```yaml
- condition: "expression"
  then:
    - action: "Action if true"
  else:
    - action: "Action if false"
```

### Alternative Syntax (using 'if')

```yaml
- if: "expression"
  then:
    - action: "Action if true"
  else:
    - action: "Action if false"
```

## Expression Syntax

Conditions are Python expressions evaluated with access to all test variables:

### Comparison Operators
```yaml
- condition: "current_version < target_version"
- condition: "device_type == 'AP'"
- condition: "response_code >= 200 and response_code < 300"
- condition: "firmware_version != '1.0.0.0'"
```

### Logical Operators
```yaml
- condition: "is_production and not debug_mode"
- condition: "status == 'ready' or force_upgrade"
```

### String Operations
```yaml
- condition: "'AP' in device_model"
- condition: "device_name.startswith('AN-')"
- condition: "firmware_file.endswith('.bin')"
```

### Numeric Operations
```yaml
- condition: "device_count > 0"
- condition: "timeout >= 5000"
- condition: "retry_count < max_retries"
```

### Existence Checks
```yaml
- condition: "firmware_version is not None"
- condition: "error_message is None"
- condition: "'api_key' in variables"
```

## Examples

### Example 1: Version-Based Firmware Upgrade

```yaml
name: Conditional Firmware Upgrade
description: Only upgrade if device version is below target

variables:
  device_ip: "192.168.100.16"
  target_version: "2.2.01.01"
  current_version: "2.1.00.00"

steps:
  # Check if upgrade is needed
  - condition: "current_version < target_version"
    then:
      - action: Open browser
        url: "http://${device_ip}/admin"
      
      - action: Upload file
        selector: 'iframe >> #image'
        file_path: 'Firmware/latest.bin'
      
      - action: Click element
        selector: 'iframe >> #UploadButton'
      
      - action: Take screenshot
        name: "upgrade-in-progress"
    else:
      - action: Take screenshot
        name: "already-up-to-date"
      
      - action: Assert
        expression: "current_version >= target_version"
        message: "Device already has target version or newer"
```

### Example 2: Environment-Specific Testing

```yaml
name: Environment-Dependent Test
description: Different actions based on environment

variables:
  environment: "staging"
  base_url: "https://staging.example.com"
  use_ssl: true

steps:
  - action: Open browser
    url: "${base_url}"
  
  # SSL verification only in production
  - condition: "environment == 'production'"
    then:
      - action: Assert
        expression: "use_ssl == true"
        message: "SSL must be enabled in production"
      
      - action: Click element
        selector: "#ssl-verify-badge"
    else:
      - action: Take screenshot
        name: "non-production-environment"
  
  - action: Click element
    selector: "#login"
```

### Example 3: Device Type Routing

```yaml
name: Device-Specific Configuration
description: Different setup based on device type

variables:
  device_type: "AP"
  model: "AN-810-AP"
  
steps:
  - action: Open browser
    url: "http://${device_ip}"
  
  # Access Point configuration
  - condition: "device_type == 'AP'"
    then:
      - action: Click element
        role: link
        name: "Wireless Settings"
      
      - action: Fill form field
        field: "#ssid"
        value: "TestNetwork"
      
      - action: Click element
        selector: "#save"
  
  # Switch configuration
  - condition: "device_type == 'Switch'"
    then:
      - action: Click element
        role: link
        name: "VLAN Settings"
      
      - action: Fill form field
        field: "#vlan_id"
        value: "100"
  
  # Router configuration
  - condition: "device_type == 'Router'"
    then:
      - action: Click element
        role: link
        name: "Routing Table"
      
      - action: Click element
        selector: "#add_route"
```

### Example 4: API Response Handling

```yaml
name: API Error Handling
description: Different actions based on API response

variables:
  api_url: "https://api.example.com"
  
setup:
  - action: API request
    method: GET
    url: "${api_url}/status"
    store_response: "status_response"

steps:
  # Check if API is healthy
  - condition: "status_response.status_code == 200"
    then:
      - action: API request
        method: POST
        url: "${api_url}/data"
        body:
          action: "process"
      
      - action: Assert
        expression: "last_status == 200"
    else:
      - action: Take screenshot
        name: "api-unavailable"
      
      - action: Assert
        expression: "false"
        message: "API is not available"
```

### Example 5: Nested Conditions

```yaml
name: Complex Conditional Logic
description: Multiple levels of conditions

variables:
  device_type: "AP"
  firmware_version: "2.1.0.0"
  target_version: "2.2.0.0"

steps:
  # Check device type first
  - condition: "device_type == 'AP'"
    then:
      # Then check version
      - condition: "firmware_version < target_version"
        then:
          - action: Upload file
            selector: "#firmware"
            file_path: "firmware_AP_${target_version}.bin"
          
          - action: Click element
            selector: "#upgrade"
        else:
          - action: Take screenshot
            name: "ap-already-updated"
    else:
      - action: Take screenshot
        name: "not-an-access-point"
```

### Example 6: Data-Driven with Conditions

```yaml
name: Multi-Device Conditional Upgrade
description: Upgrade multiple devices based on their versions

data:
  - device_ip: "192.168.100.10"
    current_version: "2.0.0.0"
    needs_upgrade: true
  - device_ip: "192.168.100.11"
    current_version: "2.2.0.0"
    needs_upgrade: false
  - device_ip: "192.168.100.12"
    current_version: "2.1.0.0"
    needs_upgrade: true

steps:
  - action: Open browser
    url: "http://${device_ip}/admin"
  
  - condition: "needs_upgrade"
    then:
      - action: Upload file
        selector: "#firmware"
        file_path: "firmware.bin"
      
      - action: Click element
        selector: "#upgrade"
      
      - action: Wait
        timeout: 30000
      
      - action: Take screenshot
        name: "upgraded-${device_ip}"
    else:
      - action: Take screenshot
        name: "skipped-${device_ip}"
```

## Best Practices

### 1. Keep Conditions Simple
```yaml
# Good - clear and simple
- condition: "status == 'ready'"

# Avoid - too complex
- condition: "(status == 'ready' and not error and retries < 3) or force_mode"
```

### 2. Use Descriptive Variable Names
```yaml
variables:
  needs_upgrade: true  # Clear intent

steps:
  - condition: "needs_upgrade"
```

### 3. Add Comments
```yaml
# Check if firmware upgrade is required
- condition: "current_version < target_version"
  then:
    # Upgrade steps...
```

### 4. Handle Both Branches
```yaml
# Provide clear actions for both outcomes
- condition: "device_online"
  then:
    - action: Run test
  else:
    - action: Take screenshot
      name: "device-offline"
    - action: Assert
      expression: "false"
      message: "Cannot proceed - device offline"
```

### 5. Use Setup for Condition Variables
```yaml
setup:
  # Get current state
  - action: API request
    method: GET
    url: "/device/status"
  
  # Store for conditions
  - action: Assert
    expression: "last_status == 200"

steps:
  # Use in conditional
  - condition: "device_status == 'online'"
```

## Common Patterns

### Skip Step if Not Ready
```yaml
- condition: "element_visible"
  then:
    - action: Click element
      selector: "#button"
```

### Execute Only in Debug Mode
```yaml
- condition: "debug_mode"
  then:
    - action: Take screenshot
      name: "debug-checkpoint"
```

### Version Comparison
```yaml
- condition: "firmware_version.split('.')[0] == '2'"
  then:
    # v2.x.x specific steps
```

### Retry Logic
```yaml
- condition: "retry_count < max_retries"
  then:
    - action: API request
      method: GET
      url: "/endpoint"
```

## Troubleshooting

### Condition Always True/False
Check variable values with Assert:
```yaml
- action: Assert
  expression: "current_version is not None"
  message: "Debug: checking variable"
```

### Syntax Errors
Use simple Python expressions:
```yaml
# Good
- condition: "x > 5"

# Bad - undefined function
- condition: "custom_function(x)"
```

### Variable Not Found
Ensure variable is defined or use existence check:
```yaml
- condition: "'variable_name' in variables and variable_name is not None"
```
