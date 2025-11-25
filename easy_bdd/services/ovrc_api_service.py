"""
OvrC API Service for Easy BDD Framework

Handles both WebSocket (JSON-RPC 2.0) and HTTP REST API communication for OvrC device management.
Supports automatic authentication for HTTP requests (GET/POST/PUT/PATCH/DELETE).
"""

import json
import uuid
import asyncio
import time
import atexit
import weakref
import ssl
import aiohttp
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol


@dataclass
class OvrCRequest:
    """JSON-RPC 2.0 request structure (for WebSocket)"""

    jsonrpc: str = "2.0"
    method: str = ""
    id: str = ""
    params: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "id": self.id,
            "params": self.params or {},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class OvrCResponse:
    """JSON-RPC 2.0 response structure (for WebSocket)"""

    jsonrpc: str = "2.0"
    id: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def from_json(cls, json_str: str) -> "OvrCResponse":
        data = json.loads(json_str)
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id", ""),
            result=data.get("result"),
            error=data.get("error"),
        )


class OvrCApiService:
    """
    Service for OvrC API communication via WebSocket (JSON-RPC) and HTTP REST.
    
    Supports:
    - WebSocket: JSON-RPC 2.0 communication over WebSocket
    - HTTP REST: GET/POST/PUT/PATCH/DELETE with automatic authentication
    - Session management with unique session IDs
    - Device connection and monitoring
    - Automatic status updates
    - Request/response tracking
    - Event handling (uiDeviceUpdate, uiDeviceEvent)
    """

    def __init__(
        self,
        server_url: str = None,
        device_id: str = None,
        session_id: str = None,
        protocol: str = "firmware-protocol",
        extra_headers: Dict[str, str] = None,
        verify_ssl: bool = True,
        # HTTP API authentication
        api_base_url: str = None,
        auth_type: str = "bearer",  # "bearer", "basic", "api_key", "custom"
        auth_token: str = None,
        auth_username: str = None,
        auth_password: str = None,
        api_key: str = None,
        api_key_header: str = "X-API-Key",
        custom_auth_headers: Dict[str, str] = None,
        # Logging
        verbose_logging: bool = False,  # Show full request/response details
        show_full_response: bool = False,  # Alias for verbose_logging
    ):
        """
        Initialize OvrC API service.

        Args:
            server_url: WebSocket server URL (e.g., 'ws://server:port')
            device_id: Device MAC address (e.g., '4B:00:00:00:00:15')
            session_id: Optional session ID (generates UUID if not provided)
            protocol: WebSocket subprotocol name
            extra_headers: Additional HTTP headers for WebSocket handshake
            verify_ssl: Whether to verify SSL certificates (default: True)
            api_base_url: Base URL for HTTP REST API (e.g., 'https://api.ovrc.com')
            auth_type: Authentication type: "bearer", "basic", "api_key", "custom"
            auth_token: Bearer token for authentication
            auth_username: Username for basic auth
            auth_password: Password for basic auth
            api_key: API key for API key authentication
            api_key_header: Header name for API key (default: "X-API-Key")
            custom_auth_headers: Custom authentication headers
        """
        # WebSocket settings
        self.server_url = server_url
        self.device_id = device_id or "00:00:00:00:00:00"
        self.session_id = session_id or str(uuid.uuid4())
        self.protocol = protocol
        self.extra_headers = extra_headers or {}
        self.verify_ssl = verify_ssl

        # HTTP API settings
        self.api_base_url = api_base_url
        self.auth_type = auth_type
        self.auth_token = auth_token
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.api_key = api_key
        self.api_key_header = api_key_header
        self.custom_auth_headers = custom_auth_headers or {}

        # WebSocket connection
        self.connection: Optional[WebSocketClientProtocol] = None
        self.message_num = 0
        self.pending_requests: Dict[str, OvrCRequest] = {}
        self.responses: Dict[str, OvrCResponse] = {}
        self.events: List[Dict[str, Any]] = []
        self.device_updates: List[Dict[str, Any]] = []

        # HTTP session
        self.http_session: Optional[aiohttp.ClientSession] = None

        # Logging settings
        self.verbose_logging = verbose_logging or show_full_response

        # Callbacks for event handling
        self.on_device_update: Optional[Callable] = None
        self.on_device_event: Optional[Callable] = None
        self.on_message: Optional[Callable] = None

        self.connected = False
        self.device_online = False
        self.update_monitoring_active = False
        self._listener_task = None
        self._cleanup_registered = False

        print(f"    🔧 OvrC API Service initialized")
        print(f"       Session ID: {self.session_id}")
        if self.device_id:
            print(f"       Device ID: {self.device_id}")
        if self.api_base_url:
            print(f"       API Base URL: {self.api_base_url}")
            print(f"       Auth Type: {self.auth_type}")

        # Register cleanup on exit
        self._register_cleanup()

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for HTTP requests"""
        headers = {}
        
        if self.auth_type == "bearer" and self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.auth_type == "api_key" and self.api_key:
            headers[self.api_key_header] = self.api_key
        elif self.auth_type == "custom":
            headers.update(self.custom_auth_headers)
        
        return headers

    def _get_auth(self) -> Optional[aiohttp.BasicAuth]:
        """Get basic auth credentials if needed"""
        if self.auth_type == "basic" and self.auth_username and self.auth_password:
            return aiohttp.BasicAuth(self.auth_username, self.auth_password)
        return None

    async def http_request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        json_data: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request to OvrC API with automatic authentication.
        
        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint: API endpoint (e.g., '/api/v1/devices')
            params: Query parameters
            json_data: JSON body for POST/PUT/PATCH
            headers: Additional headers
            timeout: Request timeout in seconds
            
        Returns:
            Response JSON data or None if error
        """
        if not self.api_base_url:
            raise ValueError("API base URL not configured. Set api_base_url in service initialization.")
        
        # Initialize HTTP session if needed
        if not self.http_session:
            self.http_session = aiohttp.ClientSession()
        
        # Build full URL
        url = f"{self.api_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # Prepare headers
        request_headers = self._get_auth_headers()
        if headers:
            request_headers.update(headers)
        request_headers.setdefault("Content-Type", "application/json")
        
        # Get auth for basic auth
        auth = self._get_auth()
        
        try:
            print(f"    📡 HTTP {method.upper()} {endpoint}")
            if self.verbose_logging:
                print(f"       URL: {url}")
                print(f"       Headers: {json.dumps({k: v if 'auth' not in k.lower() else '***' for k, v in request_headers.items()}, indent=2)}")
            if params:
                print(f"       Query Params: {json.dumps(params, indent=2)}")
            if json_data:
                body_str = json.dumps(json_data, indent=2)
                if self.verbose_logging:
                    print(f"       Request Body:")
                    for line in body_str.split("\n"):
                        print(f"         {line}")
                else:
                    print(f"       Body: {body_str[:200]}{'...' if len(body_str) > 200 else ''}")
            
            async with self.http_session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                headers=request_headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=ssl.create_default_context() if self.verify_ssl else False,
            ) as response:
                response_text = await response.text()
                response_headers = dict(response.headers)
                
                if response.status >= 200 and response.status < 300:
                    try:
                        result = json.loads(response_text) if response_text else {}
                        print(f"    ✅ Response received: {response.status} {response.reason}")
                        
                        if self.verbose_logging:
                            print(f"       Response Headers: {json.dumps(response_headers, indent=2)}")
                            print(f"       Response Body:")
                            if result:
                                result_str = json.dumps(result, indent=2)
                                for line in result_str.split("\n"):
                                    print(f"         {line}")
                            else:
                                print(f"         (empty)")
                        else:
                            if result:
                                result_str = json.dumps(result, indent=2)
                                # Truncate if too long
                                if len(result_str) > 500:
                                    lines = result_str.split("\n")
                                    for line in lines[:10]:
                                        print(f"       {line}")
                                    print(f"       ... ({len(lines) - 10} more lines)")
                                else:
                                    for line in result_str.split("\n"):
                                        print(f"       {line}")
                        
                        return result
                    except json.JSONDecodeError:
                        print(f"    ✅ Response received: {response.status} {response.reason}")
                        if self.verbose_logging:
                            print(f"       Response Headers: {json.dumps(response_headers, indent=2)}")
                            print(f"       Response Body (non-JSON):")
                            print(f"         {response_text}")
                        else:
                            print(f"       {response_text[:500]}{'...' if len(response_text) > 500 else ''}")
                        return {"text": response_text, "status": response.status}
                else:
                    print(f"    ❌ HTTP Error {response.status} {response.reason}")
                    if self.verbose_logging:
                        print(f"       Response Headers: {json.dumps(response_headers, indent=2)}")
                        print(f"       Error Response Body:")
                        print(f"         {response_text}")
                    else:
                        print(f"       {response_text[:500]}{'...' if len(response_text) > 500 else ''}")
                    try:
                        error_data = json.loads(response_text)
                        return {"error": error_data, "status": response.status}
                    except:
                        return {"error": response_text, "status": response.status}
        
        except aiohttp.ClientError as e:
            print(f"    ❌ HTTP Request failed: {e}")
            return None
        except Exception as e:
            print(f"    ❌ Unexpected error: {e}")
            return None

    async def http_get(
        self,
        endpoint: str,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Make GET request"""
        return await self.http_request("GET", endpoint, params=params, headers=headers, timeout=timeout)

    async def http_post(
        self,
        endpoint: str,
        json_data: Dict[str, Any] = None,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Make POST request"""
        return await self.http_request("POST", endpoint, json_data=json_data, params=params, headers=headers, timeout=timeout)

    async def http_put(
        self,
        endpoint: str,
        json_data: Dict[str, Any] = None,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Make PUT request"""
        return await self.http_request("PUT", endpoint, json_data=json_data, params=params, headers=headers, timeout=timeout)

    async def http_patch(
        self,
        endpoint: str,
        json_data: Dict[str, Any] = None,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Make PATCH request"""
        return await self.http_request("PATCH", endpoint, json_data=json_data, params=params, headers=headers, timeout=timeout)

    async def http_delete(
        self,
        endpoint: str,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Make DELETE request"""
        return await self.http_request("DELETE", endpoint, params=params, headers=headers, timeout=timeout)

    # ========== WebSocket Methods (same as before, renamed) ==========
    
    def generate_message_id(self) -> str:
        """Generate unique message ID: sessionId|sessionId|messageNum"""
        msg_id = f"{self.session_id}|{self.session_id}|{self.message_num}"
        self.message_num += 1
        return msg_id

    async def connect(self) -> bool:
        """
        Connect to WebSocket server with session protocol.

        Returns:
            True if connected successfully, False otherwise
        """
        if not self.server_url:
            raise ValueError("WebSocket server URL not configured")
            
        try:
            print(f"    🔌 Connecting to {self.server_url}")
            print(f"       Protocol: {self.protocol}")
            print(f"       Session: {self.session_id}")
            if self.extra_headers:
                print(f"       Headers: {list(self.extra_headers.keys())}")

            # Configure SSL for wss:// connections
            ssl_context = None
            if self.server_url.startswith("wss://"):
                ssl_context = ssl.create_default_context()
                if not self.verify_ssl:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    print("       SSL verification: Disabled")

            # Add Origin header (required by some servers)
            headers = self.extra_headers.copy() if self.extra_headers else {}
            if "Origin" not in headers and "origin" not in headers:
                from urllib.parse import urlparse
                parsed = urlparse(self.server_url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                if parsed.scheme == "wss":
                    origin = f"https://{parsed.netloc}"
                elif parsed.scheme == "ws":
                    origin = f"http://{parsed.netloc}"
                headers["Origin"] = origin
                print(f"       Origin: {origin}")
            
            # Add authentication headers if provided (for WebSocket authentication)
            if self.auth_token and self.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {self.auth_token}"
                print("       Authentication: Bearer token added")
            elif self.api_key and self.auth_type == "api_key":
                header_name = self.api_key_header or "X-API-Key"
                headers[header_name] = self.api_key
                print(f"       Authentication: API key added ({header_name})")
            elif self.auth_username and self.auth_password and self.auth_type == "basic":
                import base64
                credentials = base64.b64encode(
                    f"{self.auth_username}:{self.auth_password}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {credentials}"
                print("       Authentication: Basic auth added")
            elif self.custom_auth_headers:
                headers.update(self.custom_auth_headers)
                print(f"       Authentication: Custom headers added ({list(self.custom_auth_headers.keys())})")

            # Build connection parameters
            connect_params = {
                "subprotocols": [self.protocol, self.session_id],
                "ssl": ssl_context,
                "ping_interval": 30,
                "ping_timeout": 10,
            }

            if headers:
                connect_params["additional_headers"] = headers

            # Connect with subprotocol [protocol, sessionId]
            self.connection = await websockets.connect(
                self.server_url, **connect_params
            )

            self.connected = True
            print("    ✅ WebSocket connection established")

            # Start message listener
            self._listener_task = asyncio.create_task(self._listen_for_messages())

            return True

        except websockets.exceptions.InvalidHandshake as e:
            print(f"    ❌ WebSocket handshake failed: {e}")
            self.connected = False
            return False
        except Exception as e:
            print(f"    ❌ Connection failed: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        """Disconnect from WebSocket server and close HTTP session"""
        if self.connection and self.connected:
            try:
                if self.update_monitoring_active:
                    await self.stop_device_updates()

                if self._listener_task and not self._listener_task.done():
                    self._listener_task.cancel()
                    try:
                        await self._listener_task
                    except asyncio.CancelledError:
                        pass

                await self.connection.close()
                self.connected = False
                self.connection = None
                print(f"    🔌 Disconnected from server")
            except Exception as e:
                print(f"    ⚠️  Disconnect error: {e}")
            finally:
                self.connected = False
                self.connection = None
        
        # Close HTTP session
        if self.http_session:
            await self.http_session.close()
            self.http_session = None

    async def _listen_for_messages(self):
        """Background task to listen for incoming WebSocket messages"""
        try:
            async for message in self.connection:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            print(f"    🔌 Connection closed")
            self.connected = False
            self.device_online = False
        except Exception as e:
            print(f"    ⚠️  Message listener error: {e}")

    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            received_at = datetime.now().strftime("%H:%M:%S")

            if "id" in data:
                msg_id = data["id"]
                response = OvrCResponse.from_json(message)
                self.responses[msg_id] = response

                if msg_id in self.pending_requests:
                    request = self.pending_requests[msg_id]

                    if request.method == "dsStartDeviceUpdates":
                        if response.result and "updates" in response.result:
                            self.device_online = response.result["updates"].get("connected", False)
                            if self.device_online:
                                print(f"    ✅ Device is online and connected")
                            else:
                                print(f"    ⚠️  Device is offline")

                print(f"    📩 Response received [{received_at}]: {data.get('id', 'unknown')}")
                
                if self.verbose_logging:
                    print(f"       Full Message: {json.dumps(data, indent=2)}")

            elif "method" in data:
                method = data["method"]

                if method == "uiDeviceUpdate":
                    self.device_updates.append(data)
                    if self.on_device_update:
                        await self.on_device_update(data)
                    print(f"    📊 Device update received [{received_at}]")
                    if self.verbose_logging:
                        print(f"       Update Data: {json.dumps(data, indent=2)}")

                elif method == "uiDeviceEvent":
                    self.events.append(data)
                    if self.on_device_event:
                        await self.on_device_event(data)
                    print(f"    📢 Device event received [{received_at}]")
                    if self.verbose_logging:
                        print(f"       Event Data: {json.dumps(data, indent=2)}")

            if self.on_message:
                await self.on_message(data)

        except json.JSONDecodeError as e:
            print(f"    ⚠️  Invalid JSON received: {e}")
            if self.verbose_logging:
                print(f"       Raw Message: {message}")
        except Exception as e:
            print(f"    ⚠️  Message handling error: {e}")

    async def send_request(
        self,
        method: str,
        params: Dict[str, Any] = None,
        wait_for_response: bool = True,
        timeout: float = 10.0,
    ) -> Optional[OvrCResponse]:
        """
        Send JSON-RPC request via WebSocket and optionally wait for response.
        """
        if not self.connected:
            raise ConnectionError("Not connected to WebSocket server")

        msg_id = self.generate_message_id()
        request = OvrCRequest(method=method, id=msg_id, params=params or {})
        self.pending_requests[msg_id] = request

        json_str = request.to_json()
        sent_at = datetime.now().strftime("%H:%M:%S")

        await self.connection.send(json_str)
        print(f"    📤 Request sent [{sent_at}]: {method}")
        
        if self.verbose_logging:
            request_dict = request.to_dict()
            print(f"       Request ID: {msg_id}")
            print(f"       Request Params: {json.dumps(request_dict.get('params', {}), indent=2)}")
            print(f"       Full Request: {json_str}")

        if wait_for_response:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if msg_id in self.responses:
                    response = self.responses[msg_id]
                    del self.responses[msg_id]
                    del self.pending_requests[msg_id]

                    if response.error:
                        print(f"    ❌ Error response: {response.error}")
                        if self.verbose_logging:
                            print(f"       Full Error Response: {json.dumps({'id': response.id, 'error': response.error}, indent=2)}")
                    else:
                        print(f"    ✅ Response received: {method}")
                        if self.verbose_logging:
                            print(f"       Response ID: {response.id}")
                            print(f"       Full Response: {json.dumps({'id': response.id, 'result': response.result}, indent=2)}")
                        elif response.result:
                            # Show result summary when not in verbose mode
                            result_str = json.dumps(response.result, indent=2)
                            if len(result_str) > 300:
                                lines = result_str.split("\n")
                                print(f"       Result (first 5 lines):")
                                for line in lines[:5]:
                                    print(f"         {line}")
                                print(f"       ... ({len(lines) - 5} more lines)")
                            else:
                                print(f"       Result:")
                                for line in result_str.split("\n"):
                                    print(f"         {line}")

                    return response

                await asyncio.sleep(0.1)

            print(f"    ⏱️  Timeout waiting for response: {method}")
            return None

        return None

    # ========== Device Management Methods (WebSocket) ==========

    async def start_device_updates(self) -> bool:
        """Start receiving device status updates"""
        response = await self.send_request(
            method="dsStartDeviceUpdates", params={"deviceId": self.device_id}
        )

        if response and response.result:
            self.update_monitoring_active = True
            return self.device_online

        return False

    async def stop_device_updates(self) -> bool:
        """Stop receiving device status updates"""
        response = await self.send_request(
            method="dsStopDeviceUpdates",
            params={"deviceIds": [self.device_id]},
            wait_for_response=False,
        )

        self.update_monitoring_active = False
        return True

    async def get_about(self) -> Optional[Dict[str, Any]]:
        """Get device information (firmware, model, serial, etc.)"""
        response = await self.send_request(
            method="dxGetAbout", params={"deviceId": self.device_id, "version": 0}
        )

        return response.result if response else None

    async def reset_device(self) -> bool:
        """Reset device to factory defaults"""
        response = await self.send_request(
            method="dxResetDevice", params={"deviceId": self.device_id, "version": 0}
        )

        return response is not None and response.result is not None

    async def get_network_settings(self) -> Optional[Dict[str, Any]]:
        """Get network configuration"""
        response = await self.send_request(
            method="dxGetNetworkSettings",
            params={"deviceId": self.device_id, "version": 1},
        )

        return response.result if response else None

    async def set_network_settings(
        self,
        device_name: str = None,
        device_ip: str = None,
        subnet_mask: str = None,
        gateway: str = None,
        dhcp_enabled: bool = None,
        dns_server1: str = None,
        dns_server2: str = None,
        web_port: int = None,
    ) -> bool:
        """Set network configuration"""
        params = {"deviceId": self.device_id, "version": 1}

        if device_name is not None:
            params["deviceName"] = device_name
        if device_ip is not None:
            params["deviceIpAddress"] = device_ip
        if subnet_mask is not None:
            params["deviceSubnetMask"] = subnet_mask
        if gateway is not None:
            params["deviceDefaultGateway"] = gateway
        if dhcp_enabled is not None:
            params["dhcpEnabled"] = dhcp_enabled
        if dns_server1 is not None:
            params["dnsServer1"] = dns_server1
        if dns_server2 is not None:
            params["dnsServer2"] = dns_server2
        if web_port is not None:
            params["webPagePort"] = web_port

        response = await self.send_request(method="dxSetNetworkSettings", params=params)

        return response is not None and response.result is not None

    # ========== Helper Methods ==========

    def get_latest_device_update(self) -> Optional[Dict[str, Any]]:
        """Get most recent device update"""
        return self.device_updates[-1] if self.device_updates else None

    def get_latest_event(self) -> Optional[Dict[str, Any]]:
        """Get most recent device event"""
        return self.events[-1] if self.events else None

    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self.connected

    def is_device_online(self) -> bool:
        """Check if device is online"""
        return self.device_online

    def clear_history(self):
        """Clear stored updates and events"""
        self.device_updates.clear()
        self.events.clear()
        self.responses.clear()
        print(f"    🗑️  Cleared message history")

    def _register_cleanup(self):
        """Register automatic cleanup on program exit"""
        if not self._cleanup_registered:
            atexit.register(self._cleanup_on_exit)
            self._cleanup_registered = True

    def _cleanup_on_exit(self):
        """Cleanup method called on program exit"""
        if self.connected or self.http_session:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.disconnect())
                else:
                    loop.run_until_complete(self.disconnect())
            except Exception:
                self.connected = False
                if self.connection:
                    try:
                        self.connection.close()
                    except:
                        pass

    def close(self):
        """Close connection (sync wrapper for async disconnect)"""
        if self.connected or self.http_session:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.disconnect())
                else:
                    loop.run_until_complete(self.disconnect())
            except RuntimeError:
                asyncio.run(self.disconnect())
            except Exception as e:
                print(f"    ⚠️  Close error: {e}")
                self.connected = False


# Backward compatibility aliases
JSONRPCWebSocketService = OvrCApiService
JSONRPCRequest = OvrCRequest
JSONRPCResponse = OvrCResponse

