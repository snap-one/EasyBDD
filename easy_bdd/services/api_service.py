"""
API Service for handling various authentication types and API requests
Enhanced with centralized variable management
"""

import requests
from typing import Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from ..core.variable_manager import GlobalConfigManager


@dataclass
class AuthToken:
    """Represents an authentication token"""

    token: str
    expires_at: datetime
    refresh_token: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        """Check if token is expired or will expire in next 60 seconds"""
        return datetime.now() >= (self.expires_at - timedelta(seconds=60))


class APIAuthManager:
    """Manages API authentication tokens for different devices/endpoints"""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.tokens: Dict[str, AuthToken] = {}  # device_id -> AuthToken
        self.session = requests.Session()

    def get_auth_config(self, device_id: str) -> Dict[str, Any]:
        """Get authentication configuration for a specific device"""

        # Handle both new GlobalConfigManager and old dict format
        if hasattr(self.config_manager, "get_raw_config"):
            # New GlobalConfigManager - access device-specific auth configs
            api_config = self.config_manager.get_api_config()
            return api_config.get_auth_config(device_id)
        else:
            # Old dict format - but it might return APIConfig dataclass
            api_config = self.config_manager.get("api", {})

            # Check if it's the old dataclass format which doesn't have auth configs
            if hasattr(api_config, "timeout"):
                # APIConfig dataclass doesn't have auth configs, return empty
                return {}

            # If it's a dict, handle normally
            auth_configs = api_config.get("auth_configs", {})

            # Try device-specific config first
            if device_id in auth_configs:
                return auth_configs[device_id]

            # Fall back to default config
            return auth_configs.get("default", {})

    def authenticate(self, device_id: str, force_refresh: bool = False) -> str:
        """Get valid authentication token for device"""

        # Check if we have valid token
        if not force_refresh and device_id in self.tokens:
            token = self.tokens[device_id]
            if not token.is_expired:
                return token.token

        # Need to authenticate
        auth_config = self.get_auth_config(device_id)
        auth_type = auth_config.get("type", "none")

        if auth_type == "bearer_token":
            return self._authenticate_bearer_token(device_id, auth_config)
        elif auth_type == "basic_auth":
            return self._authenticate_basic_auth(device_id, auth_config)
        elif auth_type == "api_key":
            return self._authenticate_api_key(device_id, auth_config)
        elif auth_type == "oauth2":
            return self._authenticate_oauth2(device_id, auth_config)
        else:
            return ""  # No authentication

    def _authenticate_bearer_token(self, device_id: str, config: Dict[str, Any]) -> str:
        """Authenticate using POST endpoint to get bearer token"""
        # Handle both old and new config formats
        if "credentials" in config:
            # Old format with nested credentials
            auth_endpoint = config["endpoint"]
            credentials = config.get("credentials", {})
            username = credentials.get("username")
            password = credentials.get("password")
            print(f"    🔍 Using old format with credentials")
        else:
            # New device config format with direct username/password
            auth_endpoint = config.get("endpoint") or config.get(
                "auth_endpoint", "/auth/login"
            )
            # Add base URL if not present
            if not auth_endpoint.startswith("http"):
                base_url = config.get("base_url", "")
                if not base_url and hasattr(self.config_manager, "get_variable"):
                    base_url = self.config_manager.get_variable("device_base_url", "")
                auth_endpoint = f"{base_url}{auth_endpoint}"

            username = config.get("username")
            password = config.get("password")

            print(
                f"    🔍 Using new device format - Retrieved username: '{username}', password: '***'"
            )

        # Prepare authentication request
        auth_data = {}
        username_field = config.get("username_field", "username")
        password_field = config.get("password_field", "password")

        if username:
            auth_data[username_field] = username
        if password:
            auth_data[password_field] = password

        # Add any additional fields
        auth_data.update(config.get("additional_fields", {}))

        try:
            print(f"    🔑 Authenticating to {auth_endpoint}")
            print(
                f"    📝 Auth payload: {username_field}='{username}', {password_field}='***'"
            )

            # Make authentication request
            response = self.session.post(
                auth_endpoint,
                json=auth_data,
                headers=config.get("headers", {}),
                timeout=config.get("timeout", 30),
                verify=config.get("verify_ssl", True),
            )

            print(f"    📡 Auth response: {response.status_code}")

            # Accept any 2xx status code by default, or specific codes if configured
            success_codes = config.get("success_codes", list(range(200, 300)))
            if response.status_code in success_codes:
                data = response.json()
                token_field = config.get("token_field", "access_token")

                if token_field in data:
                    token = data[token_field]
                    print(f"    ✅ Got {token_field}: {token[:10]}...")

                    # Calculate expiry
                    expires_field = config.get("token_expires_field", "expires_in")
                    default_expiry = config.get("default_expiry", 3600)

                    if expires_field in data:
                        expires_in = int(data[expires_field])
                        expires_at = datetime.now() + timedelta(seconds=expires_in)
                    else:
                        expires_at = datetime.now() + timedelta(seconds=default_expiry)

                    # Store token
                    self.tokens[device_id] = AuthToken(
                        token=token, expires_at=expires_at
                    )

                    return token
                else:
                    print(f"    ❌ Token field '{token_field}' not found in response")
                    print(f"    📄 Response data: {data}")
                    return ""
            else:
                print(f"    ❌ Authentication failed: {response.status_code}")
                if response.text:
                    print(f"    📄 Error response: {response.text}")
                return ""

        except Exception as e:
            print(f"    ❌ Authentication error: {e}")
            return ""
            response.raise_for_status()

            # Extract token from response
            response_data = response.json()
            token_field = config.get("token_field", "access_token")
            token = response_data[token_field]

            # Calculate expiration
            expires_in = response_data.get(
                "expires_in", config.get("default_expiry", 3600)
            )
            expires_at = datetime.now() + timedelta(seconds=expires_in)

            # Store token
            refresh_token = response_data.get("refresh_token")
            auth_token = AuthToken(token, expires_at, refresh_token)
            self.tokens[device_id] = auth_token

            print(f"    🔐 Authenticated device {device_id}")
            print(f"    Token expires at {expires_at}")
            return token

        except Exception as e:
            print(f"    ❌ Authentication failed for device {device_id}: {e}")
            raise

    def _authenticate_basic_auth(self, device_id: str, config: Dict[str, Any]) -> str:
        """Handle basic authentication (returns base64 encoded credentials)"""
        import base64

        credentials = config.get("credentials", {})
        username = credentials.get("username", "")
        password = credentials.get("password", "")

        # Create basic auth token
        token = base64.b64encode(f"{username}:{password}".encode()).decode()

        # Basic auth doesn't typically expire, but set a reasonable default
        expires_at = datetime.now() + timedelta(hours=24)
        auth_token = AuthToken(token, expires_at)
        self.tokens[device_id] = auth_token

        print(f"    🔐 Basic auth configured for device {device_id}")
        return token

    def _authenticate_api_key(self, device_id: str, config: Dict[str, Any]) -> str:
        """Handle API key authentication"""
        api_key = config.get("api_key", "")

        # API keys don't typically expire
        expires_at = datetime.now() + timedelta(days=365)
        auth_token = AuthToken(api_key, expires_at)
        self.tokens[device_id] = auth_token

        print(f"    🔐 API key configured for device {device_id}")
        return api_key

    def _authenticate_oauth2(self, device_id: str, config: Dict[str, Any]) -> str:
        """Handle OAuth2 client credentials flow"""
        token_endpoint = config["token_endpoint"]
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        scope = config.get("scope", "")

        auth_data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }

        if scope:
            auth_data["scope"] = scope

        try:
            response = self.session.post(token_endpoint, data=auth_data)
            response.raise_for_status()

            response_data = response.json()
            token = response_data["access_token"]
            expires_in = response_data.get("expires_in", 3600)
            expires_at = datetime.now() + timedelta(seconds=expires_in)

            auth_token = AuthToken(token, expires_at)
            self.tokens[device_id] = auth_token

            print(f"    🔐 OAuth2 authenticated device {device_id}")
            return token

        except Exception as e:
            print(f"    ❌ OAuth2 auth failed for {device_id}: {e}")
            raise

    def get_headers(
        self, device_id: str, force_refresh: bool = False
    ) -> Dict[str, str]:
        """Get authentication headers for API requests"""
        auth_config = self.get_auth_config(device_id)
        auth_type = auth_config.get("type", "none")

        headers = {}

        if auth_type == "bearer_token":
            token = self.authenticate(device_id, force_refresh=force_refresh)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                print(f"    🔑 Added Bearer token: {token[:10]}...")
            else:
                print(f"    ❌ No token received for device: {device_id}")
        elif auth_type == "basic_auth":
            token = self.authenticate(device_id, force_refresh=force_refresh)
            headers["Authorization"] = f"Basic {token}"
        elif auth_type == "api_key":
            token = self.authenticate(device_id, force_refresh=force_refresh)
            header_name = auth_config.get("header_name", "X-API-Key")
            headers[header_name] = token
        elif auth_type == "oauth2":
            token = self.authenticate(device_id, force_refresh=force_refresh)
            headers["Authorization"] = f"Bearer {token}"

        # Add any additional headers
        headers.update(auth_config.get("additional_headers", {}))

        return headers


class APIService:
    """Service for making authenticated API requests"""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.auth_manager = APIAuthManager(config_manager)
        self.session = requests.Session()

        # Handle both new GlobalConfigManager and old dict format
        if hasattr(config_manager, "get_raw_config"):
            # New GlobalConfigManager - use defaults for now
            # We can get auth-specific settings from auth_config
            self.default_timeout = 30
            self.verify_ssl = True
            self.max_retries = 3
            self.retry_delay = 1.0
        else:
            # Old dict format
            api_config = config_manager.get("api", {})

            # Handle APIConfig dataclass or dict
            if hasattr(api_config, "timeout"):
                # APIConfig dataclass
                self.default_timeout = api_config.timeout
                self.verify_ssl = api_config.verify_ssl
                self.max_retries = api_config.max_retries
                self.retry_delay = api_config.retry_delay
            else:
                # Dict format
                self.default_timeout = api_config.get("timeout", 30)
                self.verify_ssl = api_config.get("verify_ssl", True)
                self.max_retries = api_config.get("max_retries", 3)
                self.retry_delay = api_config.get("retry_delay", 1.0)

    def _format_response_body(self, response: requests.Response) -> str:
        """Format response body for logging, attempt to parse JSON first"""
        if not response.text:
            return "(empty)"
        
        try:
            import json
            data = response.json()
            # Pretty-print JSON with indentation
            return json.dumps(data, indent=2)
        except (ValueError, json.JSONDecodeError):
            # Not JSON, return raw text with length limit
            text = response.text
            if len(text) > 500:
                return f"{text[:500]}... (truncated, {len(text)} total chars)"
            return text

    def request(
        self,
        method: str,
        url: str,
        device_id: str = "default",
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        **kwargs,
    ) -> requests.Response:
        """Make authenticated API request"""

        # Get authentication headers (this will trigger auth if needed)
        auth_headers = self.auth_manager.get_headers(device_id)

        # Merge headers
        request_headers = auth_headers.copy()
        if headers:
            request_headers.update(headers)

        # Set default content type for JSON requests
        if json and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json"

        # Get device-specific config for timeout and SSL verification
        auth_config = self.auth_manager.get_auth_config(device_id)
        timeout = kwargs.pop(
            "timeout", auth_config.get("timeout", self.default_timeout)
        )
        verify = kwargs.pop(
            "verify", auth_config.get("verify_ssl", self.session.verify)
        )

        # Disable SSL warnings for self-signed certificates
        if not verify:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            # Make request
            response = self.session.request(
                method=method.upper(),
                url=url,
                data=data,
                json=json,
                headers=request_headers,
                timeout=timeout,
                verify=verify,
                **kwargs,
            )

            print(f"    📡 {method.upper()} {url} -> {response.status_code}")
            # Print response body for debugging
            response_body = self._format_response_body(response)
            print(f"       Response: {response_body}")

            # Handle authentication errors by retrying once with forced refresh
            if response.status_code == 401:
                print(f"    🔄 Auth failed, refreshing token for {device_id}")

                # Force token refresh and retry
                auth_headers = self.auth_manager.get_headers(
                    device_id, force_refresh=True
                )
                request_headers = auth_headers.copy()  # Reset headers completely
                if headers:
                    request_headers.update(headers)
                if json and "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = "application/json"

                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    data=data,
                    json=json,
                    headers=request_headers,
                    timeout=timeout,
                    verify=verify,
                    **kwargs,
                )

                retry_msg = f"    🔄 Retry: {method.upper()} {url}"
                print(f"{retry_msg} -> {response.status_code}")
                # Print retry response body
                response_body = self._format_response_body(response)
                print(f"       Response: {response_body}")

            return response

        except Exception as e:
            print(f"    ❌ API request failed: {e}")
            raise

    def get(self, url: str, device_id: str = "default", **kwargs) -> requests.Response:
        """Make GET request"""
        return self.request("GET", url, device_id, **kwargs)

    def post(self, url: str, device_id: str = "default", **kwargs) -> requests.Response:
        """Make POST request"""
        return self.request("POST", url, device_id, **kwargs)

    def put(self, url: str, device_id: str = "default", **kwargs) -> requests.Response:
        """Make PUT request"""
        return self.request("PUT", url, device_id, **kwargs)

    def delete(
        self, url: str, device_id: str = "default", **kwargs
    ) -> requests.Response:
        """Make DELETE request"""
        return self.request("DELETE", url, device_id, **kwargs)

    def patch(
        self, url: str, device_id: str = "default", **kwargs
    ) -> requests.Response:
        """Make PATCH request"""
        return self.request("PATCH", url, device_id, **kwargs)
