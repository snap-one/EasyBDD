# Flexible Success Code Configuration

The Easy BDD framework now supports flexible HTTP success code configuration for authentication and API calls. This is especially important when working with diverse IoT devices, smart home equipment, and custom APIs that may return different success codes.

## Authentication Success Codes

### Default Behavior
By default, the framework accepts **any 2xx status code** (200-299) as successful authentication. This covers:
- 200 OK (standard REST APIs)
- 201 Created (resource creation APIs)
- 202 Accepted (async processing APIs)
- 204 No Content (successful with no response body)

### Custom Configuration
You can specify exact success codes in your device configuration:

```yaml
authentication:
  type: "bearer_token"
  # ... other config ...
  success_codes: [200, 201, 202]  # Only these codes are considered success
```

### Device Type Examples

#### 1. Standard REST API (e.g., Enterprise Network Equipment)
```yaml
authentication:
  success_codes: [200]  # Only accepts 200 OK
```

#### 2. IoT Devices with Creation Semantics
```yaml
authentication:
  success_codes: [200, 201]  # OK or Created
```

#### 3. Industrial/Legacy Equipment
```yaml
authentication:
  success_codes: [200, 202]  # OK or Accepted (async)
```

#### 4. Custom/WebSocket-style APIs
```yaml
authentication:
  success_codes: [200, 201, 202, 204]  # Very flexible
```

#### 5. Maximum Flexibility (Default)
```yaml
authentication:
  # success_codes: []  # Accept any 2xx code
  # OR omit the success_codes field entirely
```

## Real Device Examples

### Araknis Network Equipment
Returns 201 Created for successful authentication:
```yaml
authentication:
  type: "bearer_token"
  success_codes: [200, 201]  # Accepts both OK and Created
  token_field: "sid"  # Uses 'sid' instead of 'access_token'
```

### Generic Smart Home Hub
May return various codes depending on system state:
```yaml
authentication:
  type: "bearer_token"
  success_codes: [200, 201, 202]  # Flexible for different states
  token_field: "sessionId"
```

### Industrial IoT Sensors
Often use 202 Accepted for async operations:
```yaml
authentication:
  type: "api_key"
  success_codes: [200, 202]  # OK or Accepted
  header_name: "X-Device-Key"
```

## Benefits

1. **Device Agnostic**: Works with any device regardless of HTTP conventions
2. **Future Proof**: Easily adapt to new devices without code changes
3. **Flexible**: Can be as strict or permissive as needed
4. **Documented**: Clear examples for different device types
5. **Backwards Compatible**: Existing configs continue to work

## Usage in Tests

Device-specific configurations are automatically loaded:

```yaml
# test file
name: "Device API Test"
device_config: "araknis_206"  # Loads config/devices/araknis_206.yaml
steps:
  - action: "api get"
    url: "http://192.168.100.206/api/v1/device/info"
    device_id: "araknis_206"  # Uses device-specific auth config
```

The framework automatically:
1. Loads the device configuration
2. Uses the device-specific success_codes
3. Handles authentication with proper status code validation
4. Retries with fresh tokens on 401 errors

This approach makes the framework truly device-agnostic while maintaining the flexibility needed for diverse IoT ecosystems.