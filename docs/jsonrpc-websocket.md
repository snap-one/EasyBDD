# JSON-RPC WebSocket API Testing Guide

The Easy BDD Framework now supports JSON-RPC 2.0 communication over WebSocket for device management and IoT testing.

## 🚀 Quick Start

### Basic Connection Test

```yaml
name: "Connect to Device"
description: "Establish WebSocket connection and verify device status"
tags: ["jsonrpc", "device", "connection"]

variables:
  server_url: "ws://localhost:8080"
  device_id: "4B:00:00:00:00:15"
  
steps:
  - action: "JSONRPC connect"
    server_url: "${server_url}"
    device_id: "${device_id}"
    protocol: "firmware-protocol"
  
  - action: "JSONRPC start device updates"
  
  - action: "JSONRPC get about"
    store_as: "device_info"
  
  - action: "Assert"
    expression: "device_info['firmware'] != ''"
    message: "Device should have firmware version"
  
  # Optional: Explicitly disconnect (automatic if omitted)
  - action: "JSONRPC disconnect"
```

> **Note:** The service automatically disconnects when tests complete or if an error occurs. Explicit disconnect is optional but recommended for clarity.

## 📋 Available Actions

### Connection Management

**JSONRPC connect**
```yaml
- action: "JSONRPC connect"
  server_url: "ws://server:port"
  device_id: "MAC_ADDRESS"
  protocol: "firmware-protocol"  # Optional, default: firmware-protocol
  session_id: "custom-session"   # Optional, auto-generated if not provided
```

**JSONRPC disconnect**
```yaml
- action: "JSONRPC disconnect"
```
> **Automatic Disconnect:** The service automatically disconnects when:
> - Test completes (success or failure)
> - Python script exits
> - Object is garbage collected
> - Context manager exits (when used in Python)
>
> Explicit disconnect is optional but recommended for immediate cleanup.

### Device Management

**JSONRPC start device updates**
```yaml
- action: "JSONRPC start device updates"
# Starts receiving device status updates
# Sets device_online variable to true/false
```

**JSONRPC stop device updates**
```yaml
- action: "JSONRPC stop device updates"
```

**JSONRPC get about**
```yaml
- action: "JSONRPC get about"
  store_as: "device_info"
# Returns: firmware, platform, model, serialNum, serviceTag, lanAddress
```

**JSONRPC reset device**
```yaml
- action: "JSONRPC reset device"
# Factory reset the device
```

### Network Configuration

**JSONRPC get network settings**
```yaml
- action: "JSONRPC get network settings"
  store_as: "network"
# Returns: deviceName, deviceIpAddress, deviceSubnetMask, 
#          deviceDefaultGateway, dhcpEnabled, dnsServer1, 
#          dnsServer2, webPagePort
```

**JSONRPC set network settings**
```yaml
- action: "JSONRPC set network settings"
  device_name: "My Device"
  device_ip: "192.168.1.100"
  subnet_mask: "255.255.255.0"
  gateway: "192.168.1.1"
  dhcp_enabled: false
  dns_server1: "8.8.8.8"
  dns_server2: "8.8.4.4"
  web_port: 80
# All parameters are optional
```

### Time Settings

**JSONRPC get time settings**
```yaml
- action: "JSONRPC get time settings"
  store_as: "time_config"
# Returns: name, notes, offset, currentTime
```

**JSONRPC set time settings**
```yaml
- action: "JSONRPC set time settings"
  timezone_name: "America/New_York"
  timezone_notes: "Eastern Time (US & Canada)"
  utc_offset_minutes: 300
  current_time: "2024-01-15T10:30:00-05:00"
# timezone_name is required, others optional
```

### Status Update Frequency

**JSONRPC get status update frequency**
```yaml
- action: "JSONRPC get status update frequency"
  store_as: "frequency"
# Returns frequency in seconds
```

**JSONRPC set status update frequency**
```yaml
- action: "JSONRPC set status update frequency"
  frequency: 30  # seconds
```

### Cloud & Remote Access

**JSONRPC enable web connect**
```yaml
- action: "JSONRPC enable web connect"
  ssh_server: "tunnel.example.com"
  tunnel_port: 2222
```

**JSONRPC disable web connect**
```yaml
- action: "JSONRPC disable web connect"
  ssh_server: "tunnel.example.com"
  tunnel_port: 2222
```

**JSONRPC set cloud server url**
```yaml
- action: "JSONRPC set cloud server url"
  url: "https://cloud.example.com"
  port: 443
```

**JSONRPC disable cloud**
```yaml
- action: "JSONRPC disable cloud"
# Disables cloud connectivity
```

### Firmware Update

**JSONRPC update firmware**
```yaml
- action: "JSONRPC update firmware"
  firmware_url: "https://cdn.example.com/firmware/v2.0.0.bin"
```

### Device Search

**JSONRPC find device by serial**
```yaml
- action: "JSONRPC find device by serial"
  serial_num: "ABC123456"
  store_as: "found_device"
```

## 📝 Complete Example: Device Configuration Test

```yaml
name: "Configure Device Network"
description: "Connect to device, get current config, update settings, verify"
tags: ["jsonrpc", "network", "configuration"]

variables:
  server_url: "ws://192.168.1.1:8080"
  device_id: "4B:00:00:00:00:15"
  new_device_name: "Living Room Device"
  new_dns: "8.8.8.8"
  
  # Datalake tracking
  product: "IoT Device"
  product_category: "Network"
  time_savings: 15.0  # Manual config takes 15 min

setup:
  - action: "JSONRPC connect"
    server_url: "${server_url}"
    device_id: "${device_id}"
  
  - action: "JSONRPC start device updates"

steps:
  # Get device info
  - action: "JSONRPC get about"
    store_as: "device_info"
  
  - action: "Assert"
    expression: "device_info['deviceId'] == device_id"
    message: "Device ID should match"
  
  # Get current network settings
  - action: "JSONRPC get network settings"
    store_as: "current_network"
  
  - action: "Assert"
    expression: "'deviceName' in current_network"
    message: "Network settings should include device name"
  
  # Update network settings
  - action: "JSONRPC set network settings"
    device_name: "${new_device_name}"
    dns_server1: "${new_dns}"
  
  # Wait for changes to apply
  - action: "Wait"
    seconds: 2
  
  # Verify changes
  - action: "JSONRPC get network settings"
    store_as: "updated_network"
  
  - action: "Assert"
    expression: "updated_network['deviceName'] == new_device_name"
    message: "Device name should be updated"
  
  - action: "Assert"
    expression: "updated_network['dnsServer1'] == new_dns"
    message: "DNS server should be updated"

cleanup:
  - action: "JSONRPC stop device updates"
  - action: "JSONRPC disconnect"
```

## 🔄 Multi-Device Testing

Test multiple devices in parallel:

```yaml
name: "Multi-Device Firmware Check"
description: "Check firmware versions across device fleet"
tags: ["jsonrpc", "firmware", "multi-device"]

variables:
  server_url: "ws://central-server:8080"
  
async_execution: true
max_workers: 10

data:
  - device_id: "4B:00:00:00:00:01"
  - device_id: "4B:00:00:00:00:02"
  - device_id: "4B:00:00:00:00:03"
  - device_id: "4B:00:00:00:00:04"
  - device_id: "4B:00:00:00:00:05"

steps:
  - action: "JSONRPC connect"
    server_url: "${server_url}"
    device_id: "${device_id}"
  
  - action: "JSONRPC start device updates"
  
  - action: "JSONRPC get about"
    store_as: "info"
  
  - action: "Assert"
    expression: "info['firmware'].startswith('2.0')"
    message: "Device should be on firmware 2.0.x"
  
  - action: "JSONRPC disconnect"
```

## 🎯 Advanced: Event Monitoring

Monitor device events during test:

```yaml
name: "Device Event Monitoring"
description: "Monitor device events for 30 seconds"
tags: ["jsonrpc", "events", "monitoring"]

variables:
  server_url: "ws://device:8080"
  device_id: "4B:00:00:00:00:15"

steps:
  - action: "JSONRPC connect"
    server_url: "${server_url}"
    device_id: "${device_id}"
  
  - action: "JSONRPC start device updates"
  
  # Monitor for events
  - action: "Wait"
    seconds: 30
  
  # Events are automatically captured
  # Access via jsonrpc_service.events list
  
  - action: "JSONRPC stop device updates"
  - action: "JSONRPC disconnect"
```

## 📊 Response Structure

All `store_as` responses follow JSON-RPC 2.0 format:

```python
{
    "jsonrpc": "2.0",
    "id": "session-id|session-id|message-num",
    "result": {
        # Method-specific results
        "deviceId": "4B:00:00:00:00:15",
        "firmware": "2.0.5",
        # ... other fields
    }
}
```

Access fields directly:
```yaml
- action: "Assert"
  expression: "device_info['firmware'] == '2.0.5'"
```

## 🔧 Session Management

Each test creates a unique session:
- **Session ID**: Auto-generated UUID
- **Message IDs**: `sessionId|sessionId|messageNum`
- **Protocol**: Specified in connect action (default: `firmware-protocol`)

Sessions are automatically managed:
- Created on connect
- Used for all requests
- Cleaned up on disconnect

### Automatic Cleanup

The service includes comprehensive automatic cleanup:

1. **On Test Completion**
   - Automatically stops device updates if active
   - Closes WebSocket connection
   - Clears message queues

2. **On Python Exit**
   - Registered with `atexit` for cleanup on program termination
   - Ensures connections are closed even on crashes

3. **On Object Destruction**
   - `__del__` destructor provides final cleanup
   - Garbage collection triggers disconnect

4. **Context Manager Support**
   ```python
   # Sync context manager
   with JSONRPCWebSocketService(server_url, device_id) as service:
       service.connect()
       # ... use service
   # Automatically disconnects on exit
   
   # Async context manager
   async with JSONRPCWebSocketService(server_url, device_id) as service:
       await service.connect()
       # ... use service
   # Automatically disconnects on exit
   ```

5. **Exception Safety**
   - Cleanup runs even if test fails
   - Try-finally blocks ensure proper disconnect
   - Connection state tracked and recovered

**Best Practice:** While automatic cleanup is reliable, explicitly calling disconnect in cleanup phase makes test intent clear and ensures immediate resource release.

## ⚡ WebSocket Features

- **Automatic reconnection**: On connection loss
- **Ping/Pong**: Keep-alive every 30 seconds
- **Async messages**: Handle responses and events concurrently
- **Event handling**: Automatic capture of `uiDeviceUpdate` and `uiDeviceEvent`

## 🐛 Troubleshooting

### Connection Fails

```yaml
- action: "JSONRPC connect"
  server_url: "ws://192.168.1.1:8080"
  device_id: "4B:00:00:00:00:15"
# Check: Server running? Port open? Device ID correct?
```

### Device Offline

```yaml
- action: "JSONRPC start device updates"
# Check: Device powered on? Network connected?
# Look for: "Device is offline" message
```

### Timeout Waiting for Response

```yaml
# All requests have 10 second timeout
# Increase if needed (requires code change)
# Or add Wait action between requests
```

## 📚 Related Documentation

- [Data-Driven Testing](data-driven.md) - Multi-device testing patterns
- [Async Execution](advanced.md) - Parallel device testing
- [Custom Assertions](assertions.md) - Validate device responses
- [API Authentication](api-authentication.md) - Other API patterns
