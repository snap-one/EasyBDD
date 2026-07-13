# JSON-RPC WebSocket (`websocket.send`)

The `websocket.send` action connects to a WebSocket endpoint and sends a JSON-RPC 2.0
message. A session UUID is automatically generated and appended to the subprotocols list so
the server can track the session across reconnects.

---

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | yes | WebSocket endpoint — **base URL only**, no method path appended |
| `method` | yes* | JSON-RPC method name (e.g. `dxGetAbout`, `dxUpdateFirmware`). Wraps `data` in a `{"jsonrpc":"2.0","id":"…","method":"…","params":{…}}` envelope |
| `subprotocols` | no | Protocol name(s). A UUID session identifier is **automatically appended** as a second subprotocol |
| `data` | no | Params dict (nested YAML mapping) sent as `params` in the JSON-RPC payload. Flat params defined at the step level are also collected automatically |
| `store_as` | no | Variable name to store the raw response JSON string |
| `timeout` | no | Response wait timeout in seconds (default: `10.0`) |
| `wait_for` | no | String that must appear in the response before returning |

> **Note:** Do **not** append the method name to `url` (e.g. `${url}/dxGetAbout` is wrong).
> The method name is sent inside the JSON-RPC payload, not in the WebSocket URL path.

---

## Working Example: `dxGetAbout`

```yaml
- websocket.send:
    url: ${url}
    method: dxGetAbout
    subprotocols: firmware-protocol
    data:
      deviceId: ${mac}
      version: 0
    store_as: dxGetAbout_response
- test.print:
    message: ${dxGetAbout_response}
```

**Variables required:**

```yaml
variables:
  url: wss://firmware.testing.ovrc.com:10444
  mac: D4:6A:91:D0:69:68
```

### Actual log output

```
Step 1/2: websocket.send
    Params:
      url: wss://firmware.testing.ovrc.com:10444
      method: dxGetAbout
      subprotocols: firmware-protocol
      deviceId: D4:6A:91:D0:69:68
      version: 0
      store_as: dxGetAbout_response
      📤 websocket.send → wss://firmware.testing.ovrc.com:10444
         method (JSON-RPC): dxGetAbout
         ✅ WebSocket connected: wss://firmware.testing.ovrc.com:10444
         subprotocols: ['firmware-protocol', '4575700e-0db3-42b9-9cf5-82bb7f13bbc6']
         📨 Sending payload:
         {
           "jsonrpc": "2.0",
           "id": "4575700e-0db3-42b9-9cf5-82bb7f13bbc6|4575700e-0db3-42b9-9cf5-82bb7f13bbc6|1",
           "method": "dxGetAbout",
           "params": {
             "deviceId": "D4:6A:91:D0:69:68",
             "version": 0
           }
         }
         📩 WebSocket frame received:
         {
           "id": "4575700e-0db3-42b9-9cf5-82bb7f13bbc6|4575700e-0db3-42b9-9cf5-82bb7f13bbc6|1",
           "jsonrpc": "2.0",
           "result": {
             "accessories": [],
             "deviceId": "D4:6A:91:D0:69:68",
             "firmware": "2.10.0",
             "hasDisplay": false,
             "interfaces": [
               {
                 "lanAddress": "192.168.10.3",
                 "macAddress": "d4:6a:91:d0:69:68",
                 "name": "eth2"
               }
             ],
             "macAddress": "D4:6A:91:D0:69:68",
             "model": "WB-800-IPVM-6",
             "platform": "wattbox",
             "serviceTag": "ST205013181E842B"
           }
         }
    ✅ Step 1 passed (0.26s)
```

---

## How JSON-RPC payload is built

When `method` is set, the service wraps `data` in a JSON-RPC 2.0 envelope:

```json
{
  "jsonrpc": "2.0",
  "id": "<uuid>|<uuid>|<counter>",
  "method": "<method>",
  "params": { /* data dict */ }
}
```

- `id` format: `{session_uuid}|{session_uuid}|{message_counter}` — matches the OvrC server's expected format.
- If `data` is omitted or `null`, any flat params defined at the step level (e.g. `deviceId:`, `version:`) are collected automatically as the `params` dict.
- The session UUID is auto-generated and also appended to `subprotocols` so the server tracks reconnects.

---

## Firmware upgrade example

```yaml
- websocket.send:
    url: ${url}
    method: dxUpdateFirmware
    subprotocols: firmware-protocol
    data:
      deviceId: ${mac}
      version: 0
      url: ${upgrade_file}
    store_as: last_response
- test.assert:
    expression: "not_contains(last_response, 'error')"
- test.assert:
    expression: "contains(last_response, '${mac}')"
```

---

## Session management

- A UUID is generated once per connection and reused for all messages on that connection.
- Connections are pooled by URL. If the server closes the connection after responding,
  the next `websocket.send` to the same URL automatically reconnects, reusing the
  same session UUID so the server recognises the session.
- To force a fresh connection, use `websocket.disconnect` before the next send.

---

## Common mistakes

| Wrong | Correct |
|-------|---------|
| `url: ${url}/dxGetAbout` | `url: ${url}` + `method: dxGetAbout` |
| `subprotocols:\n  firmware-protocol` (block) | `subprotocols: firmware-protocol` (inline) |
| `data: deviceId: ${mac}, version: 0` (inline string) | `data:\n  deviceId: ${mac}\n  version: 0` (mapping) |
| `test.print: ${response}` | `test.print:\n  message: ${response}` |

---

## Troubleshooting

**"Connection to remote host was lost"**
- Verify `url` is the base WebSocket endpoint with no method path.
- Confirm `subprotocols: firmware-protocol` is present — OvrC servers require this header.
- Ensure the device is already connected to the OvrC server on port 10443 before sending
  API commands on port 10444.

**Empty or missing `params` in payload**
- Use a nested `data:` mapping, not an inline string.
- Flat step params are collected as a fallback when `data` is absent, not when `data` is
  present but empty.

**Response not stored**
- Confirm `store_as` is spelled correctly and the variable is referenced as `${store_as_name}`
  in subsequent steps.
