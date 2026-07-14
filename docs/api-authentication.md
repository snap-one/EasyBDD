# API Testing Configuration Examples

This file shows how to configure different authentication types for your API testing.

## Configuration Structure

Add API configurations to your `config/framework.yaml`:

```yaml
api:
  # Default timeout for all API requests
  default_timeout: 30
  
  # Base URLs for different environments
  base_urls:
    development: "https://dev-api.example.com"
    staging: "https://staging-api.example.com"
    production: "https://api.example.com"
  
  # Authentication configurations for different devices/endpoints
  auth_configs:
    # Default configuration used when device_id not specified
    default:
      type: "none"  # No authentication
    
    # Device-specific configurations
    device_1001:
      type: "bearer_token"
      endpoint: "https://dev-api.example.com/auth/login"
      credentials:
        username: "${API_USERNAME}"
        password: "${API_PASSWORD}"
      username_field: "email"
      password_field: "password"
      token_field: "access_token"  # Field in response containing token
      default_expiry: 3600  # Default expiry in seconds if not in response
      headers:
        Content-Type: "application/json"
      additional_fields:
        client_id: "mobile_app"
        grant_type: "password"
    
    device_1002:
      type: "bearer_token"
      endpoint: "https://staging-api.example.com/v2/authenticate"
      credentials:
        username: "${STAGING_USER}"
        password: "${STAGING_PASS}"
      username_field: "user"
      password_field: "pass"
      token_field: "token"
      timeout: 45
      
    api_gateway:
      type: "api_key"
      api_key: "${API_GATEWAY_KEY}"
      header_name: "X-API-Key"
      
    legacy_system:
      type: "basic_auth"
      credentials:
        username: "${LEGACY_USER}"
        password: "${LEGACY_PASS}"
        
    oauth_service:
      type: "oauth2"
      token_endpoint: "https://auth.example.com/oauth/token"
      client_id: "${OAUTH_CLIENT_ID}"
      client_secret: "${OAUTH_CLIENT_SECRET}"
      scope: "read write"

# Environment variables (can also be set in shell)
environment:
  API_USERNAME: "test_user@example.com"
  API_PASSWORD: "secure_password_123"
  STAGING_USER: "staging_user"
  STAGING_PASS: "staging_pass"
  API_GATEWAY_KEY: "gw_12345abcdef"
  LEGACY_USER: "admin"
  LEGACY_PASS: "legacy123"
  OAUTH_CLIENT_ID: "client_abc123"
  OAUTH_CLIENT_SECRET: "secret_xyz789"
```

## Authentication Types

### 1. Bearer Token Authentication
Most common for modern APIs. Posts credentials to an endpoint to get a token.

```yaml
auth_config:
  type: "bearer_token"
  endpoint: "https://api.example.com/auth/login"
  credentials:
    username: "${USERNAME}"
    password: "${PASSWORD}"
  username_field: "email"      # Field name for username in request
  password_field: "password"   # Field name for password in request
  token_field: "access_token"  # Field name for token in response
  default_expiry: 3600        # Default expiry if not in response
```

### 2. API Key Authentication
Simple key-based authentication.

```yaml
auth_config:
  type: "api_key"
  api_key: "${API_KEY}"
  header_name: "X-API-Key"  # Header name (default: X-API-Key)
```

### 3. Basic Authentication
HTTP Basic Auth with base64 encoded credentials.

```yaml
auth_config:
  type: "basic_auth"
  credentials:
    username: "${USERNAME}"
    password: "${PASSWORD}"
```

### 4. OAuth2 Client Credentials
OAuth2 client credentials flow.

```yaml
auth_config:
  type: "oauth2"
  token_endpoint: "https://auth.example.com/oauth/token"
  client_id: "${CLIENT_ID}"
  client_secret: "${CLIENT_SECRET}"
  scope: "read write"  # Optional
```

### 5. No Authentication
For public APIs or when authentication is handled elsewhere.

```yaml
auth_config:
  type: "none"
```

## Auto-Auth via Suite Variables (TestRail)

When running from TestRail, you can configure automatic token injection using three variables in your `Var:` case — no device config file needed:

| Variable | Example | Description |
|----------|---------|-------------|
| `login_path` | `/system/login` | Auth endpoint path (appended to `url`) or full URL |
| `login_json` | `{'user': 'admin', 'password': 'secret'}` | Exact POST body for authentication |
| `token_path` | `restful_res.token` | Dot-notation path to token in the response |

```
login_path: /system/login
login_json: {'user': '${username}', 'password': '${password}'}
token_path: restful_res.token
```

The `login_json` dict is POSTed verbatim — all key names are preserved as-is. This means devices that use non-standard field names like `user` (instead of `username`) work without any extra configuration.

`token_path` supports nested fields using dot-notation:
- `access_token` → `response["access_token"]`
- `restful_res.token` → `response["restful_res"]["token"]`
- `data.auth.jwt` → `response["data"]["auth"]["jwt"]`

The runner caches the token, injects it into every `api.request` as `Authorization: Bearer <token>`, and automatically re-authenticates on 401 responses.

## Token Management Features

- **Automatic Expiry Handling**: Tokens are automatically refreshed when expired
- **Device-Specific Configs**: Different devices can have different auth endpoints
- **Retry Logic**: Failed authentication automatically retries once on 401
- **Variable Substitution**: Use `${VARIABLE}` for sensitive credentials
- **Flexible Response Parsing**: Configure which fields contain tokens and expiry
- **Dot-notation token extraction**: `token_path` navigates nested response objects
- **Verbatim login payload**: `login_json` is sent as-is; no field name assumptions

## Usage in Tests

Set `login_path`, `login_json`, and `token_path` in a `Var:` case (or the equivalent
`variables:` block for local YAML) as shown above — the runner acquires and injects the
token automatically, so individual test steps don't need to reference `device_id` or an
`api_request`-style action.