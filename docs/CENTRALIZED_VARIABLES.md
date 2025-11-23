# Centralized Variable and API Configuration Management

## Overview

The Easy BDD Framework now features a powerful centralized variable and configuration management system that provides:

- **Hierarchical Variable Scopes**: Priority-based variable resolution
- **Dynamic Variable Substitution**: `${variable}` syntax with nested support
- **Environment Integration**: Automatic loading from environment variables
- **API Authentication Management**: Centralized device-specific auth configs
- **Session State Persistence**: Save/restore variable state between runs
- **Comprehensive Debugging**: Detailed variable inspection and resolution

## Architecture

### Variable Manager (`variable_manager.py`)

The core system provides:

1. **VariableScope**: Individual variable containers with priorities
2. **VariableManager**: Manages multiple scopes and variable resolution
3. **APIConfigManager**: Handles API authentication configurations
4. **GlobalConfigManager**: Main interface combining all components

### Variable Scopes (Priority Order)

1. `framework_defaults` (Priority 1) - Built-in framework variables
2. `config_file` (Priority 2) - Variables from `framework.yaml`
3. `environment_vars` (Priority 3) - Environment variables (prefix: `EASYBDD_`)
4. `test_variables` (Priority 4) - Test-specific variables
5. `runtime_data` (Priority 5) - API responses, calculated values
6. `session_overrides` (Priority 10) - Temporary overrides

**Higher priority wins** - variables in `session_overrides` will override all others.

## Framework Configuration (`config/framework.yaml`)

### Enhanced Structure

```yaml
# Global Variables
variables:
  default_timeout: 30
  base_url: "https://example.com"
  api_base_url: "https://api.example.com"
  test_user_email: "test@example.com"

# Environment-specific overrides
environments:
  development:
    base_url: "https://dev.example.com"
    debug_mode: true
  staging:
    base_url: "https://staging.example.com"
  production:
    base_url: "https://example.com"

# Service Configurations
config:
  # API configuration with centralized auth management
  api:
    timeout: 30
    verify_ssl: true
    auth_configs:
      # Araknis device authentication
      araknis_device:
        type: "bearer_token"
        endpoint: "https://192.168.100.206/api/v1/auth/login"
        username: "araknis"
        password: "SnapAV704!"
        token_field: "access_token"
        verify_ssl: false
      
      # OAuth2 example
      oauth_service:
        type: "oauth2"
        token_endpoint: "https://auth.example.com/oauth/token"
        client_id: "${OAUTH_CLIENT_ID}"
        client_secret: "${OAUTH_CLIENT_SECRET}"
```

## Usage Examples

### 1. Running Tests with Enhanced System

```bash
# Basic test run
python enhanced_cli.py run tests/cases/

# With environment override
EASYBDD_ENVIRONMENT=staging python enhanced_cli.py run tests/cases/

# With custom variables
EASYBDD_API_URL=https://custom.api.com python enhanced_cli.py run tests/

# With debugging
python enhanced_cli.py run tests/cases/ --debug-vars

# With session export
python enhanced_cli.py run tests/cases/ --export-session reports/session.json
```

### 2. Variable Debugging

```bash
# Show all variables and scopes
python enhanced_cli.py debug-vars

# Show framework configuration
python enhanced_cli.py show-config

# Show specific scope
python enhanced_cli.py show-config --scope test_variables
```

### 3. Test Definition with Variables

```yaml
# tests/cases/enhanced_api_test.yaml
name: "Enhanced API Test with Variables"
description: "Demonstrates centralized variable usage"
tags: ["api", "enhanced"]

# Test-level variables (override global ones)
variables:
  device_id: "araknis_device"
  test_endpoint: "/api/v1/device/info"
  expected_status: 200

steps:
  - action: "api_request"
    method: "GET"
    url: "${base_url}${test_endpoint}"
    device: "${device_id}"
    expect:
      status: "${expected_status}"
  
  - action: "api_request" 
    method: "POST"
    url: "${base_url}/api/v1/device/config"
    device: "${device_id}"
    body:
      setting: "updated_value_${timestamp}"
    expect:
      status: 200
```

## API Authentication Management

### Device-Specific Authentication

The system supports multiple authentication types per device:

#### Bearer Token Authentication
```yaml
auth_configs:
  device_name:
    type: "bearer_token"
    endpoint: "https://device.ip/auth/login"
    username: "admin"
    password: "password"
    token_field: "access_token"
    token_expires_field: "expires_in"
    verify_ssl: false
```

#### API Key Authentication
```yaml
auth_configs:
  api_service:
    type: "api_key"
    api_key: "${API_KEY}"
    header_name: "X-API-Key"
```

#### OAuth2 Authentication
```yaml
auth_configs:
  oauth_service:
    type: "oauth2"
    token_endpoint: "https://auth.service.com/oauth/token"
    client_id: "${OAUTH_CLIENT_ID}"
    client_secret: "${OAUTH_CLIENT_SECRET}"
    scope: "read write"
```

### Automatic Token Management

- Tokens are automatically cached and reused
- Automatic refresh when expired
- Token expiration tracking
- Stored in runtime variables for test access

## Variable Substitution

### Syntax
- Basic: `${variable_name}`
- Nested: `${object.property}`
- Environment: `${ENV_VAR}` (auto-loaded with `EASYBDD_` prefix)

### Examples

```yaml
# Framework variables
base_url: "${api_base_url}/v1"

# Environment variables
database_url: "${EASYBDD_DB_URL}"

# Nested objects
auth_header: "${auth_config.headers.Authorization}"

# Dynamic values
test_id: "test_${timestamp}_${random_id}"
```

## Programming API

### Getting Global Configuration

```python
from easy_bdd.core.variable_manager import get_global_config

# Get global config instance
config = get_global_config()

# Get variable (with scope priority)
value = config.get_variable('api_url', default='https://api.example.com')

# Set variable in specific scope
config.set_variable('test_result', 'passed', scope='runtime_data')

# Substitute variables in text
url = config.substitute_variables('${base_url}/api/v1/users')

# Substitute in complex data structures
test_data = config.substitute_recursive({
    'url': '${base_url}',
    'auth': {'token': '${auth_token}'},
    'params': ['${user_id}', '${session_id}']
})
```

### API Configuration

```python
# Get API config manager
api_config = config.get_api_config()

# Get device auth configuration
auth_config = api_config.get_auth_config('device_1')

# Store authentication token
api_config.store_token('device_1', {
    'token': 'abc123',
    'expires_at': '2024-12-31T23:59:59'
})

# Get stored token
token_data = api_config.get_token('device_1')
```

### Enhanced Test Runner

```python
from easy_bdd.core.enhanced_runner import EnhancedTestRunner
from easy_bdd.core.config import ConfigManager

# Initialize enhanced runner
config = ConfigManager()
runner = EnhancedTestRunner(config)

# Run tests with enhanced variable management
result = runner.run(test_path=Path('tests/cases/'))

# Debug variables
debug_info = runner.debug_variables()

# Export session state
runner.export_session_state('reports/session.json')
```

## Environment Integration

### Environment Variables

Variables prefixed with `EASYBDD_` are automatically loaded:

```bash
export EASYBDD_ENVIRONMENT=production
export EASYBDD_API_URL=https://prod-api.example.com
export EASYBDD_DEBUG_MODE=false
```

These become available as `ENVIRONMENT`, `API_URL`, `DEBUG_MODE` in tests.

### Environment-Specific Configurations

```yaml
environments:
  development:
    base_url: "https://dev.example.com"
    debug_mode: true
    log_level: "DEBUG"
    
  staging:
    base_url: "https://staging.example.com"  
    debug_mode: false
    log_level: "INFO"
    
  production:
    base_url: "https://example.com"
    debug_mode: false
    log_level: "ERROR"
```

## Session Management

### Persistence

Variables can be persisted between test runs:

```bash
# Session automatically saved to reports/session_state.json
python enhanced_cli.py run tests/cases/ --export-session

# Custom session file
python enhanced_cli.py run tests/cases/ --export-session custom_session.json
```

### Session State File

```json
{
  "timestamp": "2024-11-22T12:06:34",
  "variables": {
    "api_token": "abc123",
    "last_test_result": "passed"
  },
  "scopes": {
    "test_variables": {...},
    "runtime_data": {...}
  }
}
```

## Migration from Old System

### Backward Compatibility

The new system is designed to work alongside the existing framework:

1. **Existing tests work unchanged** - old variable syntax still supported
2. **Gradual migration** - can migrate tests one at a time
3. **Legacy config support** - existing `framework.yaml` files work
4. **API service compatibility** - enhanced but backward compatible

### Migration Steps

1. **Update framework.yaml** to use enhanced structure (optional)
2. **Switch to enhanced CLI** for new features
3. **Update test definitions** to use new variable scopes (optional)
4. **Enable debugging** to understand variable resolution

## Troubleshooting

### Variable Resolution Issues

```bash
# Debug all variables
python enhanced_cli.py debug-vars

# Check specific scope
python enhanced_cli.py show-config --scope test_variables

# Run with variable debugging
python enhanced_cli.py run tests/ --debug-vars
```

### Common Patterns

```yaml
# Use environment-specific values
api_url: "${EASYBDD_API_URL:-https://api.example.com}"

# Dynamic test data
test_user: "user_${timestamp}"
test_data: "data_${random_id}"

# Configuration inheritance
base_config: &base
  timeout: 30
  retries: 3

device_1:
  <<: *base
  endpoint: "https://device1.local"
  
device_2:
  <<: *base
  endpoint: "https://device2.local"
```

## Benefits

### For Test Writers
- **Simple syntax**: `${variable}` just works everywhere
- **No programming required**: Pure YAML configuration
- **Environment flexibility**: Easy switching between dev/staging/prod
- **Auto-completion**: Variables available across all tests

### For Framework Developers
- **Centralized management**: Single source of truth for all variables
- **Extensible**: Easy to add new variable sources
- **Debuggable**: Comprehensive inspection capabilities
- **Performant**: Cached resolution with lazy loading

### For DevOps/CI
- **Environment variables**: Native Docker/K8s integration
- **Configuration as code**: Version controlled settings
- **Session persistence**: Stateful test execution
- **Debugging tools**: Production troubleshooting support

This centralized system transforms the Easy BDD Framework into a truly enterprise-ready testing platform with professional-grade configuration management!