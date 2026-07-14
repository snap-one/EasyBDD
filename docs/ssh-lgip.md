# SSH and LGIP Service Guide

Focused guide for `ssh.*` and `lgip.*` actions — stateful SSH sessions and LG IP IR control.

---

## Table of Contents

1. [SSH Service — When to Use `ssh.*` vs `command.ssh`](#ssh-service)
2. [SSH Examples](#ssh-examples)
3. [LGIP Service](#lgip-service)
4. [LGIP Examples](#lgip-examples)
5. [Common Keycode Reference](#common-keycode-reference)
6. [Troubleshooting](#troubleshooting)
7. [YAML Pitfalls — Null Parameters and Special Characters](#yaml-pitfalls)

---

## SSH Service

### When to use `ssh.*` vs `command.ssh`

| | `ssh.*` | `command.ssh` |
|--|---------|---------------|
| **How it works** | Paramiko-based; holds the connection open in a session pool keyed by `host` | One-shot subprocess (`ssh host command`) |
| **Connection reuse** | Yes — connect once, run many commands | No — new subprocess per call |
| **Interactive shell** | Yes — `use_shell: true` or `prompt:` | No |
| **Privileged mode (Cisco `enable`)** | Yes | No |
| **When to use** | Multi-command sessions, interactive prompts, network gear | Single remote commands, simple scripts |

Use `ssh.*` any time you need to run more than one command on a device or when the device requires a stateful session (e.g., entering `enable` mode before issuing show commands).

### Parameters — ssh.connect

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `host` | yes | — | Hostname or IP address |
| `username` | yes | — | SSH username |
| `password` | no | — | Password authentication |
| `key_filename` | no | — | Absolute path to a private key file |
| `passphrase` | no | — | Passphrase for an encrypted private key |
| `port` | no | `22` | SSH port |
| `timeout` | no | `30` | Connection timeout in seconds |
| `look_for_keys` | no | `True` | Let Paramiko search `~/.ssh/` for keys |
| `allow_agent` | no | `True` | Allow Paramiko to use the SSH agent |

### Parameters — ssh.command

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `host` | yes | — | Must match a host passed to `ssh.connect` |
| `command` | yes | — | Command string to execute |
| `store_as` | no | — | Store stdout output in this variable; also sets `last_response` |
| `use_shell` | no | `false` | Use an interactive shell instead of `exec_command` |
| `prompt` | no | — | Substring to wait for before returning (implies `use_shell: true`) |
| `timeout` | no | `30` | Command timeout in seconds |

---

## SSH Examples

### Password authentication — read device info

```yaml
- ssh.connect:
    host: 192.168.1.1
    username: admin
    password: admin123

- ssh.command:
    host: 192.168.1.1
    command: show version
    store_as: version_output

- ssh.command:
    host: 192.168.1.1
    command: show ip interface brief
    store_as: interface_output

- ssh.disconnect:
    host: 192.168.1.1
```

### Key file authentication

```yaml
- ssh.connect:
    host: 10.0.0.50
    username: jenkins
    key_filename: /home/jenkins/.ssh/id_rsa

- ssh.command:
    host: 10.0.0.50
    command: cat /proc/version
    store_as: kernel_info

- ssh.command:
    host: 10.0.0.50
    command: df -h
    store_as: disk_usage

- ssh.disconnect:
    host: 10.0.0.50
```

### Interactive shell — Cisco privileged mode

Some devices require entering a privileged shell before accepting show commands. Use `prompt:` to wait for the device's prompt before sending the next command.

```yaml
- ssh.connect:
    host: 192.168.10.5
    username: cisco
    password: cisco123

# Enter enable mode
- ssh.command:
    host: 192.168.10.5
    command: enable
    prompt: "Password:"
    use_shell: true

# Supply the enable password
- ssh.command:
    host: 192.168.10.5
    command: enable_password_here
    prompt: "#"
    use_shell: true

# Now run privileged commands
- ssh.command:
    host: 192.168.10.5
    command: show running-config
    use_shell: true
    store_as: running_config

- ssh.command:
    host: 192.168.10.5
    command: show interfaces
    use_shell: true
    store_as: interfaces

- ssh.disconnect:
    host: 192.168.10.5
```

### Multi-device session (variables)

```yaml
variables:
  router_ip: 192.168.1.1
  switch_ip: 192.168.1.2
  ssh_user: admin
  ssh_pass: admin123

steps:
  - ssh.connect:
      host: ${router_ip}
      username: ${ssh_user}
      password: ${ssh_pass}

  - ssh.connect:
      host: ${switch_ip}
      username: ${ssh_user}
      password: ${ssh_pass}

  - ssh.command:
      host: ${router_ip}
      command: show version
      store_as: router_version

  - ssh.command:
      host: ${switch_ip}
      command: show version
      store_as: switch_version

  - ssh.disconnect:
      host: ${router_ip}

  - ssh.disconnect:
      host: ${switch_ip}
```

---

## LGIP Service

The LGIP service sends IR keycodes to AV displays over TCP using the LG IP protocol. Connections are pooled by `ip:port` — connect once, send multiple keycodes, disconnect.

### Parameters — lgip.connect

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `ip` | yes | — | Device IP address |
| `port` | no | `9761` | TCP port |

### Parameters — lgip.send_keycode

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `ip` | yes | — | Must match a connected device |
| `keycode` | yes | — | Numeric keycode string (see table below) |
| `delay_after` | no | `0` | Seconds to sleep after the keypress |
| `store_as` | no | — | Store the device response in this variable |

### Parameters — lgip.disconnect

| Parameter | Required | Description |
|-----------|----------|-------------|
| `ip` | yes | Device to disconnect |

---

## LGIP Examples

### Single keypress — power on a display

```yaml
- lgip.connect:
    ip: 192.168.1.50

- lgip.send_keycode:
    ip: 192.168.1.50
    keycode: "20"
    delay_after: 3.0

- lgip.disconnect:
    ip: 192.168.1.50
```

### Sequence of keypresses — switch to HDMI 2

```yaml
- lgip.connect:
    ip: 192.168.1.50
    port: 9761

- lgip.send_keycode:
    ip: 192.168.1.50
    keycode: "20"
    delay_after: 3.0

- lgip.send_keycode:
    ip: 192.168.1.50
    keycode: "28"
    delay_after: 1.0
    store_as: hdmi2_result

- lgip.disconnect:
    ip: 192.168.1.50
```

### Power cycle pattern (off → wait → on → switch input)

```yaml
variables:
  display_ip: 192.168.1.50

steps:
  - lgip.connect:
      ip: ${display_ip}

  # Power off
  - lgip.send_keycode:
      ip: ${display_ip}
      keycode: "21"
      delay_after: 5.0

  # Power on
  - lgip.send_keycode:
      ip: ${display_ip}
      keycode: "20"
      delay_after: 5.0

  # Select HDMI 1
  - lgip.send_keycode:
      ip: ${display_ip}
      keycode: "27"
      delay_after: 2.0

  - lgip.disconnect:
      ip: ${display_ip}
```

---

## Common Keycode Reference

| Keycode | Function |
|---------|----------|
| `"20"` | Power On |
| `"21"` | Power Off |
| `"02"` | Volume Up |
| `"03"` | Volume Down |
| `"09"` | Mute |
| `"27"` | HDMI 1 |
| `"28"` | HDMI 2 |
| `"29"` | HDMI 3 |
| `"60"` | HDMI 4 |

---

## Troubleshooting

### Login shortcut — `ssh.command` without a prior `ssh.connect`

If you only need to run one command, pass `username` and `password` directly to `ssh.command`. The service auto-connects, runs the command, and leaves the connection open for reuse.

```yaml
- ssh.command:
    host: ${ip_address}
    username: wattbox
    password: SnapAV704
    command: '?Model'
    prompt: '>'
    store_as: model_response
```

The connection stays in the pool after this step. Add `ssh.disconnect` at the end of the test to close it explicitly.

---

### Wrong `prompt:` causes the step to hang until timeout

`prompt:` must be a substring that appears in the device's output **after** the command completes. Using the wrong device's prompt is the most common mistake when switching between device types.

| Device | Correct `prompt:` |
|--------|------------------|
| WattBox | `'>'` |
| Araknis switch (user exec) | `'>'` |
| Araknis switch (privileged exec) | `'#'` |
| Cisco (privileged exec) | `'#'` |
| Linux shell (root) | `'#'` |
| Linux shell (non-root) | `'$'` |

```yaml
# WRONG — uses the Araknis switch prompt for a WattBox device; hangs until timeout
- ssh.command:
    host: ${wattbox_ip}
    command: '?Model'
    prompt: 'AN-210-SW-16-POE#'

# CORRECT
- ssh.command:
    host: ${wattbox_ip}
    command: '?Model'
    prompt: '>'
```

Prompt matching is a **substring check** — `'#'` matches any prompt ending in `#`, including `AN-210-SW-16-POE#`. Use the shortest unique suffix that reliably identifies the prompt.

---

### `ModuleNotFoundError: No module named 'paramiko'`

The SSH service requires Paramiko. Install it:

```bash
pip install paramiko
```

Or add it to your project requirements:

```
paramiko>=3.0
```

---

### Host key verification fails / `SSHException: Server '...' not found in known_hosts`

Handled automatically by the service's connection pool (`AutoAddPolicy`). If you still see this error, confirm that the host and port are correct and reachable.

---

### Connection timeout

```
socket.timeout: timed out
```

- Confirm the device is reachable: `ping <host>`
- Confirm SSH is listening on the expected port: `nc -zv <host> 22`
- Increase the `timeout` parameter on `ssh.connect`

---

### LGIP — no response from device

- Confirm the device supports LG IP IR control and that the feature is enabled in its settings.
- The default port is `9761`; some devices use a different port.
- Confirm no firewall is blocking TCP to that port.

---

## YAML Pitfalls

These are the most common YAML formatting mistakes that produce `null`/`None` parameter values at runtime. The parser now emits a **warning** listing which parameters are null when it loads a step, so problems appear at parse time rather than mid-run.

### `#` without quotes becomes a YAML comment

In YAML, `#` starts a comment when it is preceded by whitespace (or appears alone after `:`). A value that contains `#` must be quoted.

```yaml
# WRONG — the '#' starts a comment; prompt becomes null
- ssh.command:
    host: ${ip_address}
    prompt: AN-210-SW-16-POE#

# WRONG — standalone '#' is entirely a comment; prompt becomes null
- ssh.command:
    host: ${ip_address}
    prompt: #

# CORRECT — single or double quotes protect the '#'
- ssh.command:
    host: ${ip_address}
    prompt: 'AN-210-SW-16-POE#'
```

The same rule applies to any YAML value, not just `prompt:`.

---

### Commands that start with `?`, `!`, `*`, `&`, or `|`

These characters have special meaning at the start of a YAML scalar. Always quote them.

```yaml
# WRONG — '?' may confuse some YAML parsers or editors
- ssh.command:
    command: ?Model

# CORRECT
- ssh.command:
    command: '?Model'
```

---

### Empty `command:` key becomes null

An indented key with no value is parsed as `null`, not an empty string.

```yaml
# WRONG — command is null
- ssh.command:
    host: ${ip_address}
    command:

# CORRECT
- ssh.command:
    host: ${ip_address}
    command: 'show version'
```

---

### `command.ssh` vs `ssh.command` — wrong action name

These are **different handlers**:

| Action | Handler | Supports `prompt:` | Connection pool |
|--------|---------|-------------------|----------------|
| `ssh.command` | `SSHService` | Yes | Yes — reuses the session |
| `command.ssh` | `CommandService` | No | No — one-shot subprocess |

Use `ssh.command` when the device needs an interactive shell or when you are running multiple commands in the same session. Use `command.ssh` only for simple one-off Linux/Unix shell commands where no interactive prompt is needed.

```yaml
# For interactive devices (switches, WattBox, routers) — use ssh.command
- ssh.command:
    host: ${ip_address}
    username: araknis
    password: SnapAV704!
    prompt: '#'
    command: show version

# For a plain Linux command — command.ssh is fine, but prompt: is ignored
- command.ssh:
    host: ${linux_host}
    username: jenkins
    password: secret
    command: cat /proc/version
```

---

### Real-world device examples

**WattBox — query model**

```yaml
- ssh.command:
    host: ${ip_address}
    username: wattbox
    password: SnapAV704
    prompt: '>'
    command: '?Model'
    store_as: wattbox_model
```

**Araknis switch — privileged mode**

```yaml
- ssh.command:
    host: ${ip_address}
    username: araknis
    password: SnapAV704!
    prompt: '#'
    command: show version
    store_as: switch_version
```

Note: `'#'` works as the prompt here because `AN-210-SW-16-POE#` ends with `#`. You can use the short form unless you have multiple devices with different prompt endings that could collide.
