# OvrC WebSocket Integration

This document describes how to use the OvrC WebSocket (and HTTP) integration within the Easy BDD framework. These actions allow tests to connect to OvrC-managed devices, send JSON-RPC commands, and inspect responses.

---

## Overview

The OvrC integration provides a thin test-level interface over the OvrC device WebSocket protocol (JSON-RPC 2.0). It supports two distinct connection modes:

| Mode | Connect param | Use case |
|---|---|---|
| WebSocket | `url: wss://...` | Send JSON-RPC commands over a persistent WebSocket connection |
| HTTP REST | `api_base_url: https://...` | Make one-off REST calls to an HTTP endpoint |

These two modes are **mutually exclusive per connection**. Do not mix `url` and `api_base_url` in the same connect step — see [Connection Types](#connection-types) for details.

The active connection is stored internally as `_ovrc_service` and is automatically disconnected at the end of each test scenario, even if no explicit `ovrc disconnect` step is present.

---

## Connection Types

### WebSocket Connection

Use `url:` (a `wss://` or `ws://` URI) when you want to send JSON-RPC commands over a persistent WebSocket.

```yaml
- action: ovrc connect
  url: wss://device.example.com/ws
  device_id: abc123
  subprotocols: firmware-protocol
```

### HTTP REST Connection

Use `api_base_url:` (an `https://` or `http://` base URL) when you want to make REST HTTP calls via `ovrc http request`. Do **not** supply `url:` for this mode.

```yaml
- action: ovrc connect
  api_base_url: https://api.example.com
  device_id: abc123
```

---

## Actions Reference

All actions accept either the `ovrc` or `ovrc.` prefix (e.g. `ovrc connect` and `ovrc.connect` are equivalent).

---

### `ovrc connect` / `ovrc.connect`

Establishes a connection to the device. Must be called before any send/call/get actions.

| Parameter | Required | Default | Description |
|---|---|---|---|
| `url` | No* | — | WebSocket URI (`wss://...`). Required for WebSocket mode. |
| `api_base_url` | No* | — | HTTP base URL. Required for HTTP REST mode. |
| `device_id` | Yes | — | OvrC device identifier |
| `subprotocols` | No | `firmware-protocol` | WebSocket subprotocol header |
| `session_id` | No | — | Optional session identifier |
| `verify_ssl` | No | `true` | Set `false` to skip SSL certificate verification |
| `headers` | No | — | Dict of extra HTTP headers to include in the upgrade request |
| `verbose_logging` | No | `false` | Enables detailed WebSocket frame logging |
| `method` | No | — | If provided, calls this JSON-RPC method immediately after connecting and stores the result |
| `params` | No | — | Parameters for the inline `method` call |
| `store_as` | No | — | Variable name to store the result of the inline `method` call |

*Exactly one of `url` or `api_base_url` must be supplied.

**Example — plain WebSocket connect:**
```yaml
- action: ovrc connect
  url: wss://192.168.1.50/ws
  device_id: my-device-001
  verify_ssl: false
```

**Example — connect and immediately call a method:**
```yaml
- action: ovrc connect
  url: wss://192.168.1.50/ws
  device_id: my-device-001
  verify_ssl: false
  method: dxGetAbout
  store_as: about_info
```

---

### `ovrc disconnect` / `ovrc.disconnect`

Closes the active WebSocket connection. Optional — the framework disconnects automatically at the end of each test.

```yaml
- action: ovrc disconnect
```

No parameters.

---

### `ovrc send` / `ovrc.send` / `ovrc call` / `ovrc.call`

Sends a JSON-RPC request over the active WebSocket connection and waits for the response.

| Parameter | Required | Default | Description |
|---|---|---|---|
| `method` | Yes | — | JSON-RPC method name (e.g. `dxGetAbout`) |
| `params` | No | `{}` | Dict of parameters to pass to the method |
| `store_as` | No | — | Variable name to store the response dict |

The response is always stored in `last_response` automatically, regardless of whether `store_as` is set.

**Example:**
```yaml
- action: ovrc send
  method: dxSetConfig
  params:
    key: brightness
    value: 75
  store_as: set_result
```

---

### `ovrc get about` / `ovrc.get about`

Convenience wrapper for `dxGetAbout`. Retrieves full device information.

| Parameter | Required | Default | Description |
|---|---|---|---|
| `store_as` | No | — | Variable name to store the response |

```yaml
- action: ovrc get about
  store_as: device_info
```

---

### `ovrc get network settings` / `ovrc.get network settings`

Convenience wrapper for `dxGetNetworkSettings`.

| Parameter | Required | Default | Description |
|---|---|---|---|
| `store_as` | No | — | Variable name to store the response |

```yaml
- action: ovrc get network settings
  store_as: net_settings
```

---

### `ovrc reset device` / `ovrc.reset device`

Calls `dxResetDevice` on the connected device.

```yaml
- action: ovrc reset device
```

---

### `ovrc start device updates` / `ovrc.start device updates`

Calls `dxStartDeviceUpdates` to begin receiving device update notifications.

```yaml
- action: ovrc start device updates
```

---

### `ovrc stop device updates` / `ovrc.stop device updates`

Calls `dxStopDeviceUpdates` to stop receiving device update notifications.

```yaml
- action: ovrc stop device updates
```

---

### `ovrc http request` / `ovrc.http.request`

Performs an HTTP REST request against the `api_base_url` set during connect. This action requires that the connect step used `api_base_url`, **not** `url`.

| Parameter | Required | Default | Description |
|---|---|---|---|
| `method` | Yes | — | HTTP verb: `GET`, `POST`, `PUT`, `DELETE`, etc. |
| `endpoint` | Yes | — | Path appended to `api_base_url` (e.g. `/v1/status`) |
| `body` | No | — | Request body (dict, serialized as JSON) |
| `store_as` | No | — | Variable name to store the response |

```yaml
- action: ovrc connect
  api_base_url: https://api.example.com
  device_id: my-device-001

- action: ovrc http request
  method: GET
  endpoint: /v1/device/status
  store_as: status_response
```

---

## Variable Storage

| Variable | Set by | Contents |
|---|---|---|
| `last_response` | Every send/call/get action | The most recent JSON-RPC response dict |
| `<store_as value>` | Any action with `store_as` | The response dict for that specific call |
| `_ovrc_service` | `ovrc connect` | Internal — the active connection object. Do not overwrite. |

To read a field from a stored response in a subsequent step, use the standard Easy BDD variable syntax:

```yaml
- action: assert equals
  value: "{{ device_info.result.model }}"
  expected: AK-SW-8-POE
```

---

## Common Patterns

### Connect, send a command, assert on the response

```yaml
steps:
  - action: ovrc connect
    url: wss://192.168.1.50/ws
    device_id: my-switch
    verify_ssl: false

  - action: ovrc send
    method: dxGetAbout
    store_as: about

  - action: assert equals
    value: "{{ about.result.firmwareVersion }}"
    expected: 2.4.1
```

---

### Inline method call at connect time

When you only need one call right after connecting, you can collapse the connect and call into a single step:

```yaml
steps:
  - action: ovrc connect
    url: wss://192.168.1.50/ws
    device_id: my-switch
    verify_ssl: false
    method: dxGetAbout
    store_as: about

  - action: assert equals
    value: "{{ about.result.model }}"
    expected: AK-SW-8-POE
```

---

### Multi-command session

```yaml
steps:
  - action: ovrc connect
    url: wss://192.168.1.50/ws
    device_id: my-switch
    verify_ssl: false

  - action: ovrc get about
    store_as: about

  - action: ovrc get network settings
    store_as: net

  - action: ovrc send
    method: dxSetConfig
    params:
      vlan_enabled: true

  - action: assert equals
    value: "{{ last_response.result.status }}"
    expected: ok

  - action: ovrc disconnect
```

---

### Reading nested response fields

JSON-RPC responses are nested dicts. Use dot notation inside `{{ }}` to reach nested keys:

```yaml
- action: ovrc send
  method: dxGetAbout
  store_as: info

# Access info.result.networkInfo.ipAddress
- action: log
  message: "Device IP is {{ info.result.networkInfo.ipAddress }}"
```

---

### HTTP REST session

```yaml
steps:
  - action: ovrc connect
    api_base_url: https://ovrc-api.example.com
    device_id: my-device

  - action: ovrc http request
    method: GET
    endpoint: /v1/devices/my-device/status
    store_as: status

  - action: assert equals
    value: "{{ status.online }}"
    expected: true
```

---

## Gotchas / Lessons Learned

These are real bugs that were discovered and fixed during development. They are documented here so the same mistakes are not repeated in tests.

### 1. `ovrc disconnect` was incorrectly routed to the connect handler

**Problem:** The action router checked `"connect" in action_lower`, which matched both `"ovrc connect"` and `"ovrc disconnect"` (because the string `"connect"` appears inside `"disconnect"`).

**Fix:** The check was updated to `"connect" in action_lower and "disconnect" not in action_lower`.

**Impact on test writing:** None — this is fixed in the framework. However, if you ever add a new action containing the word "connect" in its name, be aware of this substring matching pattern and ensure the routing logic handles it explicitly.

---

### 2. The `method:` param in `ovrc connect` was silently ignored

**Problem:** If you passed `method:` in the connect step, the framework accepted it without error but never actually called it. The result variable would be unset, causing downstream assertions to fail in confusing ways.

**Fix:** The connect handler now detects the presence of `method` after the WebSocket handshake and calls `send_request(method_name, params)` before returning, storing the result in `store_as`.

**Impact on test writing:** The inline `method:` pattern is now reliable. If a test was previously working around this by adding a separate `ovrc send` step, that workaround can now be simplified.

---

### 3. `ovrc http request` requires `api_base_url`, not `url`

**Problem:** `url` is the WebSocket URI parameter. `api_base_url` is the HTTP base URL. They serve different purposes and are not interchangeable. Using `url` when intending to make HTTP REST calls causes the connection to be set up as a WebSocket, and `ovrc http request` has no HTTP base to call against.

**Impact on test writing:** This is a design constraint, not a bug fix. Always follow this rule:

- Sending JSON-RPC over WebSocket → use `url: wss://...` in connect
- Making REST HTTP calls → use `api_base_url: https://...` in connect, never `url:`

Do not put both `url` and `api_base_url` in the same connect step.

---

## Troubleshooting

### Connection fails immediately

- Check that `url` is a valid `wss://` or `ws://` URI and that the device is reachable from the test runner host.
- If the device uses a self-signed certificate, set `verify_ssl: false`.
- Check `subprotocols` — the default is `firmware-protocol`. Some devices may require a different value.

### `last_response` or `store_as` variable is empty / undefined

- Confirm the connect step succeeded before the send step. If connect fails, subsequent steps may be skipped or may run against no connection.
- If you used the inline `method:` param in `ovrc connect`, make sure the fix described in Gotcha #2 above is present in your version of the framework.

### Assertions on response fields fail with key errors

- Print or log `last_response` to inspect the actual structure: `action: log` with `message: "{{ last_response }}"`.
- JSON-RPC errors are returned in `last_response.error`, not `last_response.result`. Check for this field if the device rejects your command.

### `ovrc http request` fails with "no base URL" or similar

- Verify the connect step uses `api_base_url:`, not `url:`. See Gotcha #3 above.

### Disconnect step triggers connect logic

- This was Gotcha #1, fixed in the framework. If you are on an older version and see connect behavior triggered by a disconnect step, update to the latest framework version.

### WebSocket auto-disconnect timing

- The framework disconnects at the end of each test scenario. If a test needs to assert on events received after disconnect, restructure to perform all assertions before the scenario ends, or add an explicit `ovrc disconnect` step at the point where cleanup should happen.
