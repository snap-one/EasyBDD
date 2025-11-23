# API Authentication System - Complete Guide

This document explains how the Easy BDD framework handles API authentication for devices that require tokens, different endpoints, and automatic token refresh.

## Problem Solved

Your requirement was to handle devices where you need to:
1. ✅ Use POST authentication endpoints to generate tokens
2. ✅ Use those tokens for subsequent API calls  
3. ✅ Handle token expiration and automatic refresh
4. ✅ Support different auth endpoints for different devices
5. ✅ Manage multiple authentication types (bearer, API key, basic auth, OAuth2)

## Architecture Overview

```
Test YAML → Runner → API Service → Auth Manager → Device-Specific Auth
                         ↓
                   Automatic Token Management
                         ↓
                   HTTP Requests with Headers
```

### Key Components

1. **APIAuthManager** - Manages authentication tokens per device
2. **APIService** - Main interface for making authenticated requests  
3. **Device Configurations** - Per-device auth settings in `framework.yaml`
4. **Action Integration** - New API actions in test runner

## Authentication Flow

### 1. Initial Authentication
```yaml
# First API request for device_1001
- action: "api get"
  url: "https://api.example.com/users"
  device_id: "device_1001"
```

Behind the scenes:
1. Framework checks if `device_1001` has valid token
2. No token exists, so it reads auth config for `device_1001`
3. Makes POST request to auth endpoint with credentials
4. Extracts token from response using configured field name
5. Stores token with expiration time
6. Makes the actual API request with `Authorization: Bearer <token>` header

### 2. Token Reuse
```yaml
# Second API request for same device
- action: "api post"  
  url: "https://api.example.com/users"
  device_id: "device_1001"  # Same device
  json_data:
    name: "John Doe"
```

Behind the scenes:
1. Framework checks existing token for `device_1001`
2. Token is still valid (not expired)
3. Reuses existing token in Authorization header
4. Makes API request immediately

### 3. Automatic Token Refresh
```yaml
# API request after token expires
- action: "api get"
  url: "https://api.example.com/protected"
  device_id: "device_1001"
```

Behind the scenes:
1. Framework checks token - it's expired or will expire soon
2. Automatically calls auth endpoint again to get new token
3. Stores new token with new expiration time
4. Makes the actual API request with fresh token

### 4. Authentication Error Recovery
If the API returns 401 (Unauthorized):
1. Framework assumes token is invalid
2. Forces token refresh by calling auth endpoint
3. Retries the original request with new token
4. If still fails, reports error to test

## Configuration Examples

### Bearer Token Authentication
Most common for modern APIs - POST credentials to get token:

```yaml
api:
  auth_configs:
    device_1001:
      type: "bearer_token"
      endpoint: "https://api.example.com/auth/login"
      credentials:
        username: "${API_USERNAME}"
        password: "${API_PASSWORD}"
      username_field: "email"      # Field name for username in request  
      password_field: "password"   # Field name for password in request
      token_field: "access_token"  # Field name for token in response
      default_expiry: 3600        # Default expiry if not in response
      headers:
        Content-Type: "application/json"
      additional_fields:           # Extra fields in auth request
        client_id: "mobile_app"
```

**Authentication Request:**
```json
POST https://api.example.com/auth/login
{
  "email": "test@example.com",
  "password": "secure123", 
  "client_id": "mobile_app"
}
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600,
  "refresh_token": "refresh_123..."
}
```

### Different Device, Different Endpoint
```yaml
device_1002:
  type: "bearer_token"
  endpoint: "https://staging-api.example.com/v2/authenticate"  # Different URL
  credentials:
    username: "${STAGING_USER}"
    password: "${STAGING_PASS}"
  username_field: "user"        # Different field names
  password_field: "pass"  
  token_field: "token"         # Different response structure
  timeout: 45                  # Custom timeout
```

### API Key Authentication
Simple key-based auth:

```yaml
api_gateway:
  type: "api_key"
  api_key: "${API_GATEWAY_KEY}"
  header_name: "X-API-Key"     # Custom header name
```

Results in: `X-API-Key: gw_12345abcdef`

### Basic Authentication  
HTTP Basic Auth:

```yaml
legacy_system:
  type: "basic_auth"
  credentials:
    username: "${LEGACY_USER}"
    password: "${LEGACY_PASS}"
```

Results in: `Authorization: Basic YWRtaW46bGVnYWN5MTIz`

### OAuth2 Client Credentials
```yaml
oauth_service:
  type: "oauth2"
  token_endpoint: "https://auth.example.com/oauth/token"
  client_id: "${OAUTH_CLIENT_ID}" 
  client_secret: "${OAUTH_CLIENT_SECRET}"
  scope: "read write"
```

## Available Actions

### Basic HTTP Methods
```yaml
# Generic request (supports all HTTP methods)
- action: "api request"
  method: "GET"  # GET, POST, PUT, DELETE, PATCH
  url: "https://api.example.com/endpoint"
  device_id: "device_1001"
  headers:
    Accept: "application/json"
  params:
    page: 1
  json_data:
    field: "value"

# Shorthand methods
- action: "api get"
  url: "https://api.example.com/users"
  device_id: "device_1001"

- action: "api post" 
  url: "https://api.example.com/users"
  device_id: "device_1001"
  json_data:
    name: "John Doe"

- action: "api put"
  url: "https://api.example.com/users/123" 
  device_id: "device_1001"
  json_data:
    name: "John Smith"

- action: "api delete"
  url: "https://api.example.com/users/123"
  device_id: "device_1001"
```

### Response Validation
```yaml
# Validate HTTP status code
- action: "validate status"
  status: 200

# Validate JSON response fields (supports dot notation)
- action: "validate json"
  field: "user.profile.name" 
  value: "John Doe"

# Validate nested arrays
- action: "validate json"
  field: "users.0.email"  # First user's email
  value: "john@example.com"
```

## Advanced Features

### Automatic Token Management
- **Expiry Tracking**: Framework tracks when tokens expire
- **Proactive Refresh**: Refreshes tokens 60 seconds before expiry
- **Error Recovery**: Auto-refreshes on 401 responses
- **Per-Device Isolation**: Each device has independent token storage

### Variable Support
All configurations support variable substitution:

```yaml
variables:
  api_user: "test@example.com"
  device_name: "device_1001"

steps:
  - action: "api get"
    url: "${base_api}/users"
    device_id: "${device_name}"
```

Environment variables can be set in:
- `framework.yaml` under `environment:`
- Shell environment  
- CI/CD pipeline secrets

### Response Data Access
API responses are automatically stored in variables:

```yaml
- action: "api get"
  url: "https://api.example.com/users/123"
  device_id: "device_1001"

# These variables are now available:
# ${last_response}   - Full response object
# ${last_status}     - HTTP status code  
# ${last_json}       - Parsed JSON response

- action: "validate status" 
  status: 200  # Validates ${last_status}

- action: "validate json"
  field: "name"  # Validates ${last_json}.name
  value: "Expected Name"
```

## Best Practices

### 1. Organize Device Configurations
```yaml
# Group related devices
auth_configs:
  # Production environment
  prod_api:
    type: "bearer_token"
    endpoint: "https://api.example.com/auth"
  
  prod_legacy:
    type: "basic_auth"
    
  # Staging environment  
  staging_api:
    type: "bearer_token"
    endpoint: "https://staging-api.example.com/auth"
```

### 2. Use Descriptive Device IDs
```yaml
# Good
device_id: "main_api_server"
device_id: "legacy_billing_system"
device_id: "third_party_gateway"

# Avoid
device_id: "device1" 
device_id: "system_a"
```

### 3. Environment-Specific Credentials
```yaml
# framework.yaml
environment:
  API_USERNAME: "test_user@example.com"      # Development
  STAGING_USERNAME: "staging@example.com"   # Staging
  PROD_USERNAME: "${PRODUCTION_USER}"       # From CI/CD secrets
```

### 4. Validation Patterns
```yaml
# Always validate status first
- action: "api post"
  url: "https://api.example.com/users"
  device_id: "main_api"
  json_data:
    name: "Test User"

- action: "validate status"
  status: 201  # Created

- action: "validate json"
  field: "name"
  value: "Test User"

- action: "validate json"  
  field: "id"  # Ensure ID was assigned
  # Don't specify value - just ensure field exists
```

## Troubleshooting

### Common Issues

1. **Authentication Fails**
   - Check credentials in environment variables
   - Verify auth endpoint URL
   - Check username/password field names match API
   - Review API documentation for required fields

2. **Token Expires Too Quickly**
   - Check `expires_in` field in auth response
   - Set `default_expiry` in config if API doesn't provide it
   - Monitor token refresh logs

3. **401 Errors After Working**
   - Token may be revoked server-side
   - Check if API requires periodic re-authentication
   - Verify token format and header name

4. **Wrong Authentication Type**
   - Some APIs require specific Content-Type headers
   - Some use custom header names for tokens
   - Some require tokens in URL parameters instead of headers

### Debug Tips

1. **Enable Detailed Logging**
```python
# The API service prints auth status:
# 🔐 Authenticated device device_1001 - token expires at 2024-01-01 15:30:00
# 🔄 Auth failed, refreshing token for device_1001  
# 📡 GET https://api.example.com/users -> 200
```

2. **Test Auth Endpoint Manually**
```bash
curl -X POST https://api.example.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"secure123"}'
```

3. **Check Response Format**
Ensure your `token_field` configuration matches the actual response:
```json
{
  "access_token": "...",  # Use token_field: "access_token"
  "token": "...",         # Use token_field: "token"  
  "data": {
    "auth_token": "..."   # Use token_field: "data.auth_token"
  }
}
```

## Example Test Files

See the provided example files:
- `tests/cases/api_authentication_demo.yaml` - Basic API auth patterns
- `tests/cases/multi_device_auth_demo.yaml` - Complex multi-device scenario
- `config/framework.yaml` - Complete auth configuration examples

## Next Steps

1. Copy the auth configuration examples to your `config/framework.yaml`
2. Set your actual API credentials in environment variables
3. Update device configurations to match your API endpoints
4. Create test files using the provided actions
5. Run tests: `python -m easy_bdd run tests/cases/your_api_test.yaml`

The framework handles all the complex authentication logic automatically, so you can focus on writing business logic tests!