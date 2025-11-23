"""
JSON-RPC WebSocket Service for Easy BDD Framework

Handles JSON-RPC 2.0 communication over WebSocket for device management and control.
Based on the firmware protocol pattern with session management and device updates.
"""

import json
import uuid
import asyncio
import time
import atexit
import weakref
import ssl
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol


@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request structure"""
    jsonrpc: str = "2.0"
    method: str = ""
    id: str = ""
    params: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "id": self.id,
            "params": self.params or {}
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response structure"""
    jsonrpc: str = "2.0"
    id: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_json(cls, json_str: str) -> 'JSONRPCResponse':
        data = json.loads(json_str)
        return cls(
            jsonrpc=data.get('jsonrpc', '2.0'),
            id=data.get('id', ''),
            result=data.get('result'),
            error=data.get('error')
        )


class JSONRPCWebSocketService:
    """
    Service for JSON-RPC 2.0 communication over WebSocket.
    
    Supports:
    - Session management with unique session IDs
    - Device connection and monitoring
    - Automatic status updates
    - Request/response tracking
    - Event handling (uiDeviceUpdate, uiDeviceEvent)
    """
    
    def __init__(self, server_url: str, device_id: str = None, 
                 session_id: str = None, protocol: str = 'firmware-protocol',
                 extra_headers: Dict[str, str] = None,
                 verify_ssl: bool = True):
        """
        Initialize JSON-RPC WebSocket service.
        
        Args:
            server_url: WebSocket server URL (e.g., 'ws://server:port')
            device_id: Device MAC address (e.g., '4B:00:00:00:00:15')
            session_id: Optional session ID (generates UUID if not provided)
            protocol: WebSocket subprotocol name
            extra_headers: Additional HTTP headers for WebSocket handshake
            verify_ssl: Whether to verify SSL certificates (default: True)
        """
        self.server_url = server_url
        self.device_id = device_id or "00:00:00:00:00:00"
        self.session_id = session_id or str(uuid.uuid4())
        self.protocol = protocol
        self.extra_headers = extra_headers or {}
        self.verify_ssl = verify_ssl
        
        self.connection: Optional[WebSocketClientProtocol] = None
        self.message_num = 0
        self.pending_requests: Dict[str, JSONRPCRequest] = {}
        self.responses: Dict[str, JSONRPCResponse] = {}
        self.events: List[Dict[str, Any]] = []
        self.device_updates: List[Dict[str, Any]] = []
        
        # Callbacks for event handling
        self.on_device_update: Optional[Callable] = None
        self.on_device_event: Optional[Callable] = None
        self.on_message: Optional[Callable] = None
        
        self.connected = False
        self.device_online = False
        self.update_monitoring_active = False
        self._listener_task = None
        self._cleanup_registered = False
        
        print(f"    🔧 JSON-RPC Service initialized")
        print(f"       Session ID: {self.session_id}")
        print(f"       Device ID: {self.device_id}")
        
        # Register cleanup on exit
        self._register_cleanup()
    
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
        try:
            print(f"    🔌 Connecting to {self.server_url}")
            print(f"       Protocol: {self.protocol}")
            print(f"       Session: {self.session_id}")
            if self.extra_headers:
                print(f"       Headers: {list(self.extra_headers.keys())}")
            
            # Configure SSL for wss:// connections
            ssl_context = None
            if self.server_url.startswith('wss://'):
                ssl_context = ssl.create_default_context()
                if not self.verify_ssl:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    print("       SSL verification: Disabled")
            
            # Add Origin header (required by some servers)
            headers = self.extra_headers.copy()
            if 'Origin' not in headers and 'origin' not in headers:
                # Extract origin from server URL
                from urllib.parse import urlparse
                parsed = urlparse(self.server_url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                # Use https for wss, http for ws
                if parsed.scheme == 'wss':
                    origin = f"https://{parsed.netloc}"
                elif parsed.scheme == 'ws':
                    origin = f"http://{parsed.netloc}"
                headers['Origin'] = origin
                print(f"       Origin: {origin}")
            
            # Build connection parameters
            connect_params = {
                'subprotocols': [self.protocol, self.session_id],
                'ssl': ssl_context,
                'ping_interval': 30,
                'ping_timeout': 10
            }
            
            # Add headers using additional_headers (websockets 15.0+)
            if headers:
                connect_params['additional_headers'] = headers
            
            # Connect with subprotocol [protocol, sessionId]
            self.connection = await websockets.connect(
                self.server_url,
                **connect_params
            )
            
            self.connected = True
            print("    ✅ WebSocket connection established")
            
            # Start message listener and keep reference
            self._listener_task = asyncio.create_task(self._listen_for_messages())
            
            return True
            
        except websockets.exceptions.InvalidHandshake as e:
            print(f"    ❌ WebSocket handshake failed: {e}")
            print(f"       Status: {getattr(e, 'status_code', 'unknown')}")
            print(f"       Headers: {getattr(e, 'headers', 'unknown')}")
            self.connected = False
            return False
        except Exception as e:
            print(f"    ❌ Connection failed: {e}")
            print(f"       Error type: {type(e).__name__}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from WebSocket server"""
        if self.connection and self.connected:
            try:
                # Stop device updates if active
                if self.update_monitoring_active:
                    await self.stop_device_updates()
                
                # Cancel listener task if running
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
        """
        Handle incoming WebSocket message.
        
        Processes:
        - JSON-RPC responses (matched by ID)
        - Device update notifications (method: uiDeviceUpdate)
        - Device event notifications (method: uiDeviceEvent)
        """
        try:
            data = json.loads(message)
            received_at = datetime.now().strftime("%H:%M:%S")
            
            # Check if it's a response (has 'id' field)
            if 'id' in data:
                msg_id = data['id']
                response = JSONRPCResponse.from_json(message)
                self.responses[msg_id] = response
                
                # Check for specific response types
                if msg_id in self.pending_requests:
                    request = self.pending_requests[msg_id]
                    
                    # Handle dsStartDeviceUpdates response
                    if request.method == 'dsStartDeviceUpdates':
                        if response.result and 'updates' in response.result:
                            self.device_online = response.result['updates'].get('connected', False)
                            if self.device_online:
                                print(f"    ✅ Device is online and connected")
                            else:
                                print(f"    ⚠️  Device is offline")
                
                print(f"    📩 Response received [{received_at}]: {data.get('id', 'unknown')}")
            
            # Check if it's a notification (has 'method' field)
            elif 'method' in data:
                method = data['method']
                
                if method == 'uiDeviceUpdate':
                    self.device_updates.append(data)
                    if self.on_device_update:
                        await self.on_device_update(data)
                    print(f"    📊 Device update received [{received_at}]")
                
                elif method == 'uiDeviceEvent':
                    self.events.append(data)
                    if self.on_device_event:
                        await self.on_device_event(data)
                    print(f"    📢 Device event received [{received_at}]")
            
            # Call generic message handler if set
            if self.on_message:
                await self.on_message(data)
                
        except json.JSONDecodeError as e:
            print(f"    ⚠️  Invalid JSON received: {e}")
        except Exception as e:
            print(f"    ⚠️  Message handling error: {e}")
    
    async def send_request(self, method: str, params: Dict[str, Any] = None, 
                          wait_for_response: bool = True, 
                          timeout: float = 10.0) -> Optional[JSONRPCResponse]:
        """
        Send JSON-RPC request and optionally wait for response.
        
        Args:
            method: JSON-RPC method name
            params: Method parameters
            wait_for_response: If True, waits for response
            timeout: Response timeout in seconds
            
        Returns:
            JSONRPCResponse if wait_for_response=True, None otherwise
        """
        if not self.connected:
            raise ConnectionError("Not connected to WebSocket server")
        
        # Create request
        msg_id = self.generate_message_id()
        request = JSONRPCRequest(
            method=method,
            id=msg_id,
            params=params or {}
        )
        
        # Store pending request
        self.pending_requests[msg_id] = request
        
        # Send request
        json_str = request.to_json()
        sent_at = datetime.now().strftime("%H:%M:%S")
        
        await self.connection.send(json_str)
        print(f"    📤 Request sent [{sent_at}]: {method}")
        
        # Wait for response if requested
        if wait_for_response:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if msg_id in self.responses:
                    response = self.responses[msg_id]
                    del self.responses[msg_id]
                    del self.pending_requests[msg_id]
                    
                    if response.error:
                        print(f"    ❌ Error response: {response.error}")
                    else:
                        print(f"    ✅ Response received: {method}")
                        if response.result:
                            print(f"    📦 Response data:")
                            result_str = json.dumps(response.result, indent=2)
                            for line in result_str.split('\n'):
                                print(f"       {line}")
                    
                    return response
                
                await asyncio.sleep(0.1)
            
            print(f"    ⏱️  Timeout waiting for response: {method}")
            return None
        
        return None
    
    # ========== Device Management Methods ==========
    
    async def start_device_updates(self) -> bool:
        """
        Start receiving device status updates.
        
        Returns:
            True if device is online, False otherwise
        """
        response = await self.send_request(
            method='dsStartDeviceUpdates',
            params={'deviceId': self.device_id}
        )
        
        if response and response.result:
            self.update_monitoring_active = True
            return self.device_online
        
        return False
    
    async def stop_device_updates(self) -> bool:
        """Stop receiving device status updates"""
        response = await self.send_request(
            method='dsStopDeviceUpdates',
            params={'deviceIds': [self.device_id]},
            wait_for_response=False
        )
        
        self.update_monitoring_active = False
        return True
    
    async def get_about(self) -> Optional[Dict[str, Any]]:
        """Get device information (firmware, model, serial, etc.)"""
        response = await self.send_request(
            method='dxGetAbout',
            params={'deviceId': self.device_id, 'version': 0}
        )
        
        return response.result if response else None
    
    async def reset_device(self) -> bool:
        """Reset device to factory defaults"""
        response = await self.send_request(
            method='dxResetDevice',
            params={'deviceId': self.device_id, 'version': 0}
        )
        
        return response is not None and response.result is not None
    
    # ========== Network Settings ==========
    
    async def get_network_settings(self) -> Optional[Dict[str, Any]]:
        """
        Get network configuration.
        
        Returns:
            Dict with: deviceName, deviceIpAddress, deviceSubnetMask,
            deviceDefaultGateway, dhcpEnabled, dnsServer1, dnsServer2, webPagePort
        """
        response = await self.send_request(
            method='dxGetNetworkSettings',
            params={'deviceId': self.device_id, 'version': 1}
        )
        
        return response.result if response else None
    
    async def set_network_settings(self, 
                                   device_name: str = None,
                                   device_ip: str = None,
                                   subnet_mask: str = None,
                                   gateway: str = None,
                                   dhcp_enabled: bool = None,
                                   dns_server1: str = None,
                                   dns_server2: str = None,
                                   web_port: int = None) -> bool:
        """Set network configuration"""
        params = {'deviceId': self.device_id, 'version': 1}
        
        if device_name is not None:
            params['deviceName'] = device_name
        if device_ip is not None:
            params['deviceIpAddress'] = device_ip
        if subnet_mask is not None:
            params['deviceSubnetMask'] = subnet_mask
        if gateway is not None:
            params['deviceDefaultGateway'] = gateway
        if dhcp_enabled is not None:
            params['dhcpEnabled'] = dhcp_enabled
        if dns_server1 is not None:
            params['dnsServer1'] = dns_server1
        if dns_server2 is not None:
            params['dnsServer2'] = dns_server2
        if web_port is not None:
            params['webPagePort'] = web_port
        
        response = await self.send_request(
            method='dxSetNetworkSettings',
            params=params
        )
        
        return response is not None and response.result is not None
    
    # ========== Time Settings ==========
    
    async def get_time_settings(self) -> Optional[Dict[str, Any]]:
        """
        Get time zone and current time.
        
        Returns:
            Dict with: name, notes, offset, currentTime
        """
        response = await self.send_request(
            method='dxGetTimeSettings',
            params={'deviceId': self.device_id, 'version': 2}
        )
        
        return response.result if response else None
    
    async def set_time_settings(self,
                               timezone_name: str,
                               timezone_notes: str = None,
                               utc_offset_minutes: int = None,
                               current_time: str = None) -> bool:
        """
        Set time zone and current time.
        
        Args:
            timezone_name: e.g., 'America/New_York'
            timezone_notes: e.g., 'Eastern Time (US & Canada)'
            utc_offset_minutes: e.g., 300 for UTC-5
            current_time: ISO format: '2020-05-12T05:41:36-04:00'
        """
        params = {
            'deviceId': self.device_id,
            'version': 2,
            'name': timezone_name
        }
        
        if timezone_notes:
            params['notes'] = timezone_notes
        if utc_offset_minutes is not None:
            params['offset'] = utc_offset_minutes
        if current_time:
            params['currentTime'] = current_time
        
        response = await self.send_request(
            method='dxSetTimeSettings',
            params=params
        )
        
        return response is not None and response.result is not None
    
    # ========== Status Update Frequency ==========
    
    async def get_status_update_frequency(self) -> Optional[int]:
        """Get status update frequency in seconds"""
        response = await self.send_request(
            method='dxGetStatusUpdateFrequency',
            params={'deviceId': self.device_id, 'version': 0}
        )
        
        if response and response.result:
            return response.result.get('frequency')
        return None
    
    async def set_status_update_frequency(self, frequency: int) -> bool:
        """Set status update frequency in seconds"""
        response = await self.send_request(
            method='dxSetStatusUpdateFrequency',
            params={
                'deviceId': self.device_id,
                'version': 0,
                'frequency': frequency
            }
        )
        
        return response is not None and response.result is not None
    
    # ========== Cloud & Remote Access ==========
    
    async def enable_web_connect(self, ssh_server: str, tunnel_port: int) -> bool:
        """Enable remote web UI access via SSH tunnel"""
        response = await self.send_request(
            method='dxEnableWebConnect',
            params={
                'deviceId': self.device_id,
                'version': 0,
                'sshServer': ssh_server,
                'tunnelPort': tunnel_port
            }
        )
        
        return response is not None and response.result is not None
    
    async def disable_web_connect(self, ssh_server: str, tunnel_port: int) -> bool:
        """Disable remote web UI access"""
        response = await self.send_request(
            method='dxDisableWebConnect',
            params={
                'deviceId': self.device_id,
                'version': 0,
                'sshServer': ssh_server,
                'tunnelPort': tunnel_port
            }
        )
        
        return response is not None and response.result is not None
    
    async def set_cloud_server_url(self, url: str, port: int) -> bool:
        """Set cloud server URL and port"""
        response = await self.send_request(
            method='dxSetCloudServerUrl',
            params={
                'deviceId': self.device_id,
                'version': 0,
                'url': url,
                'port': port
            }
        )
        
        return response is not None and response.result is not None
    
    async def disable_cloud(self) -> bool:
        """Disable cloud connectivity"""
        response = await self.send_request(
            method='dxDisableCloud',
            params={'deviceId': self.device_id, 'version': 0}
        )
        
        return response is not None and response.result is not None
    
    # ========== Firmware Update ==========
    
    async def update_firmware(self, firmware_url: str) -> bool:
        """
        Trigger firmware update from URL.
        
        Args:
            firmware_url: URL to firmware file
        """
        response = await self.send_request(
            method='dxUpdateFirmware',
            params={
                'deviceId': self.device_id,
                'version': 0,
                'url': firmware_url
            }
        )
        
        return response is not None and response.result is not None
    
    # ========== Device Search ==========
    
    async def find_device_by_serial(self, serial_num: str) -> Optional[Dict[str, Any]]:
        """Find device by serial number"""
        response = await self.send_request(
            method='dsFindDeviceBySerialNum',
            params={'serialNum': serial_num}
        )
        
        return response.result if response else None
    
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
        if self.connected:
            try:
                # Try to run cleanup in event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule disconnect task
                    asyncio.create_task(self.disconnect())
                else:
                    # Run in new event loop
                    loop.run_until_complete(self.disconnect())
            except Exception as e:
                # Fallback: force close connection
                if self.connection:
                    try:
                        self.connection.close()
                    except:
                        pass
                self.connected = False
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically disconnect"""
        self.close()
        return False
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - automatically disconnect"""
        await self.disconnect()
        return False
    
    def __del__(self):
        """Destructor - ensure cleanup when object is garbage collected"""
        if self.connected:
            try:
                # Best effort cleanup
                self._cleanup_on_exit()
            except:
                pass
    
    def close(self):
        """Close connection (sync wrapper for async disconnect)"""
        if self.connected:
            try:
                # Try to get running event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule disconnect as task
                    asyncio.create_task(self.disconnect())
                else:
                    # Run disconnect in event loop
                    loop.run_until_complete(self.disconnect())
            except RuntimeError:
                # No event loop, create one
                asyncio.run(self.disconnect())
            except Exception as e:
                print(f"    ⚠️  Close error: {e}")
                # Force cleanup
                self.connected = False
                if self.connection:
                    try:
                        asyncio.run(self.connection.close())
                    except:
                        pass
