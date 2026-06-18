# Telnet Service

**Send commands to network devices over Telnet from your test steps**

---

## Table of Contents

1. [Overview](#overview)
2. [Actions](#actions)
3. [Multi-Command Navigation](#multi-command-navigation)
4. [Login Shortcut](#login-shortcut)
5. [Gotchas and Common Errors](#gotchas-and-common-errors)

---

## Overview

The Telnet service lets you open Telnet sessions to network devices, send commands, and capture responses — all from YAML test steps. Connections are managed by a shared `ConnectionPool`, so a session opened in one step stays alive across subsequent steps without re-authentication.

Supported actions:

| Action | Purpose |
|--------|---------|
| `telnet.connect` | Open a Telnet connection (optional — auto-opened on first `telnet.send`) |
| `telnet.send` | Send one or more commands and wait for a prompt |
| `telnet.receive` | Read available output up to a prompt or timeout |
| `telnet.close` | Close the connection and remove it from the pool |

---

## Actions

### telnet.connect

Opens a Telnet connection and performs login. This step is optional — `telnet.send` will open and authenticate the connection automatically if credentials are provided.

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `host` | Yes | — | Hostname or IP address |
| `port` | No | `23` | TCP port |
| `username` | No | — | Login username |
| `password` | No | — | Login password |
| `username_prompt` | No | `"Username:"` | String to wait for before sending username |
| `password_prompt` | No | `"Password:"` | String to wait for before sending password |
| `timeout` | No | `15.0` | Connection timeout in seconds |
| `encoding` | No | `"utf-8"` | Character encoding |

**Example:**

```yaml
- telnet.connect:
    host: 192.168.1.1
    port: 23
    username: admin
    password: secret
    username_prompt: 'User:'
    password_prompt: 'Password:'
    timeout: 10.0
```

---

### telnet.send

Sends one or more commands and waits for the device prompt after each one. Use `command:` for a single command or `commands:` for a sequence.

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `host` | Yes | — | Target host (must match a connected session) |
| `port` | No | `23` | TCP port |
| `command` | No | — | Single command string (or a list — auto-promoted to `commands:`) |
| `commands` | No | — | List of commands to send in sequence |
| `prompt` | No | `"#"` | String to wait for after each command |
| `username` | No | — | Username (used for auto-login if not yet connected) |
| `password` | No | — | Password (used for auto-login) |
| `username_prompt` | No | `"Username:"` | Username prompt to wait for during auto-login |
| `password_prompt` | No | `"Password:"` | Password prompt to wait for during auto-login |
| `timeout` | No | `15.0` | Seconds to wait for each prompt |
| `encoding` | No | `"utf-8"` | Character encoding |
| `store_as` | No | — | Variable name to store the output of the **last** command |

**Notes:**

- Each command is sent with `\r\n` (CR+LF) line endings — required by most Telnet devices.
- When `commands:` is a list, each command waits for `prompt` before the next one is sent.
- `store_as` captures the output of the **final** command only.
- If `command:` is given a YAML list value, it is automatically promoted to `commands:`.

**Single command example:**

```yaml
- telnet.send:
    host: ${net_host}
    port: ${net_port}
    username: admin
    password: secret
    prompt: '#'
    command: show version
    store_as: version_output
```

**Multi-command example:**

```yaml
- telnet.send:
    host: ${net_host}
    port: ${net_port}
    username_prompt: 'User:'
    password_prompt: 'Password:'
    username: araknis
    password: SnapAV704
    prompt: '#'
    commands:
      - configure
      - interface 1/0/2-1/0/18
      - poe reset
    store_as: poe_reset_response
```

---

### telnet.receive

Reads buffered output from an open connection, optionally waiting until a prompt string appears.

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `host` | Yes | — | Target host |
| `port` | No | `23` | TCP port |
| `prompt` | No | `""` | Wait until this string appears; if empty, returns available data |
| `timeout` | No | `15.0` | Seconds to wait |
| `encoding` | No | `"utf-8"` | Character encoding |
| `store_as` | No | — | Variable to store the received output |

**Example:**

```yaml
- telnet.receive:
    host: ${net_host}
    prompt: '#'
    timeout: 10
    store_as: banner_text
```

---

### telnet.close

Closes the Telnet connection and removes it from the pool.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `host` | Yes | Target host to disconnect |
| `port` | No | TCP port (default: `23`) |

**Example:**

```yaml
- telnet.close:
    host: ${net_host}
```

---

## Multi-Command Navigation

Use `commands:` when you need to navigate through multiple interactive prompts before reaching the final command. Each entry in the list is sent after the previous command's prompt is received.

```yaml
- telnet.send:
    host: ${net_host}
    port: ${net_port}
    username_prompt: 'User:'
    password_prompt: 'Password:'
    username: araknis
    password: SnapAV704
    prompt: '#'
    commands:
      - configure
      - interface 1/0/2-1/0/18
      - poe reset
    store_as: poe_reset_response

- test.assert:
    expression: "'error' not in poe_reset_response"
```

**Execution flow:**

1. Connect (auto-login if not already connected).
2. Send `configure\r\n`, wait for `#`.
3. Send `interface 1/0/2-1/0/18\r\n`, wait for `#`.
4. Send `poe reset\r\n`, wait for `#`.
5. Capture final output into `poe_reset_response`.

---

## Login Shortcut

You can skip a separate `telnet.connect` step and pass credentials directly to `telnet.send`. The runner will open the connection, log in, and then send your commands in one step.

```yaml
- telnet.send:
    host: 192.168.1.1
    port: 23
    username: admin
    password: secret
    username_prompt: 'User:'
    password_prompt: 'Password:'
    command: show version
    prompt: '>'
    store_as: fw_response
```

---

## Gotchas and Common Errors

### Prompt characters must be quoted

YAML gives special meaning to `>` and `#`. Always quote the `prompt:` value:

```yaml
# WRONG — > starts a YAML block scalar, # starts a comment
prompt: >
prompt: #

# CORRECT
prompt: '>'
prompt: '#'
```

### Responses are plain strings — do not use `["body"]`

Unlike HTTP responses, `store_as` on a Telnet send stores a plain string (the raw terminal output), not a response object. Do not use subscript access:

```yaml
# WRONG
- test.assert:
    expression: "'error' not in poe_reset_response['body']"

# CORRECT
- test.assert:
    expression: "'error' not in poe_reset_response"
```

### Action and first parameter must be on separate lines

```yaml
# WRONG — host must be on the next line, indented
- telnet.send: host: 192.168.1.1

# CORRECT
- telnet.send:
    host: 192.168.1.1
    command: show version
    prompt: '#'
```

### Multiple parameters must not share a line

```yaml
# WRONG — YAML parse error
password: SnapAV704 prompt: >

# CORRECT — each parameter on its own line
password: SnapAV704
prompt: '>'
```

### `\r\n` line endings

The service automatically appends `\r\n` (CR+LF) to every command. Do not add `\n` manually to command strings — it results in double line endings and may confuse the device.

```yaml
# WRONG
command: "show version\n"

# CORRECT
command: show version
```

### `test.assert` must be a sibling step, not nested inside `telnet.send`

A common TestRail YAML mistake is accidentally indenting `test.assert` under the `telnet.send` block. This makes the runner treat `test.assert` as a command to send to the device and `expression` as a stray parameter — neither runs correctly.

```yaml
# WRONG — test.assert is indented under telnet.send
- telnet.send:
    host: ${net_host}
    prompt: '#'
    commands:
      - configure
      - shutdown
      - test.assert:         # ← this is sent as a literal command to the device!
    expression: "'error' not in str(last_response)"

# CORRECT — test.assert is a separate step at the same level
- telnet.send:
    host: ${net_host}
    prompt: '#'
    commands:
      - configure
      - shutdown
- test.assert:
    expression: "'error' not in str(last_response)"
```

### Authenticated devices require credentials in every `telnet.send` step

Devices that require login (e.g. Araknis switches) will not send the `Username:` prompt until the Telnet IAC negotiation handshake is complete. If `username` and `password` are missing from the step, the connection will time out waiting for the login prompt even though TCP is connected.

Always pass credentials (or use variables from the run's variable set):

```yaml
- telnet.send:
    host: ${net_host}
    username: ${net_user}
    password: ${net_password}
    prompt: '#'
    commands:
      - configure
      - interface GigabitEthernet ${net_port}
      - shutdown
- test.assert:
    expression: "'error' not in str(last_response)"
```
