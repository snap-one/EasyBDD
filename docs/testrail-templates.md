# TestRail Case Templates

Copy-paste boilerplates for the test workflows we actually run in production, modeled on
real cases from suite `S106658` (WattBox firmware smoke suite, run 195198). Credentials,
device IPs, and account keys from those cases are replaced with `${variable}` placeholders
below — never paste real secrets into a template or commit them to this repo.

Each template is a **Preconditions field** body — paste it directly into the Preconditions
field of a new case with the matching title prefix. See
[writing-test-cases.md](./writing-test-cases.md) for the full prefix taxonomy and the
flush-left formatting rule these templates follow (params go flush-left under the action,
not indented — TestRail's rich text editor strips leading whitespace on save).

---

## Table of contents

1. [Var: Device & cloud config](#1-var-device--cloud-config)
2. [Shared: Telnet command + validate](#2-shared-telnet-command--validate)
3. [Shared: SSH command + validate](#3-shared-ssh-command--validate)
4. [Shared: WebSocket API call (OvrC-style)](#4-shared-websocket-api-call-ovrc-style)
5. [Shared: Browser login / navigate](#5-shared-browser-login--navigate)
6. [Feature: Firmware upgrade/downgrade orchestration](#6-feature-firmware-upgradedowngrade-orchestration)
7. [Feature: Resiliency fault-injection loop](#7-feature-resiliency-fault-injection-loop)
8. [Feature: Data-driven UI loop](#8-feature-data-driven-ui-loop)
9. [Var: Firmware discovery (AWS S3 + CloudFront)](#9-var-firmware-discovery-aws-s3--cloudfront)

---

## 1. Var: Device & cloud config

**Case title:** `Var: <Product Name>`
**Purpose:** one place for every credential, IP, and selector the rest of the run
references via `${...}`. Put this case first in the run.

```
device_ip: 192.168.10.3
device_username: admin
device_password: ${DEVICE_PASSWORD}
mac: AA:BB:CC:DD:EE:FF
product: <product-model>
web_url: http://${device_username}:${device_password}@${device_ip}
ui_url: http://${device_ip}/main/
telnet_port: 23
net_host: 192.168.100.10
net_user: ${NET_USERNAME}
net_password: ${NET_PASSWORD}
ovrc_ws_url: wss://your-ovrc-endpoint:10444
log_level: debug
```

> Reference an env var instead of a literal value with `${ENV_VAR_NAME}` — the runner
> falls back to `.env` when a `Var:` case doesn't define a key. Keep real passwords out
> of TestRail where possible; put them in `.env` and reference them here.

---

## 2. Shared: Telnet command + validate

**Case title:** `Shared: Telnet_Validation`
**Purpose:** send a device query over telnet and assert the response is well-formed —
the pattern used for WattBox/Araknis-style `?Command` / `!Command=value` protocols.

```
steps:
# 1. Send query
- telnet.send:
host: ${device_ip}
port: ${telnet_port}
username: ${device_username}
password: ${device_password}
command: "?Firmware"
prompt: '>'
# 2. Assert no error and expected key present
- test.assert:
expression: "not_contains(last_response, 'Errno')"
- test.assert:
expression: "contains(last_response, '?Firmware=')"
```

For a multi-command sequence against a switch/router (e.g. enabling an interface), pass
`commands:` instead of `command:`:

```
steps:
# 1. Run a command sequence
- telnet.send:
host: ${net_host}
username: ${net_user}
password: ${net_password}
prompt: '#'
commands: [configure, 'interface GigabitEthernet ${net_port}', 'no shutdown', end]
# 2. Assert success
- test.assert:
expression: "not_contains(last_response, 'error')"
```

---

## 3. Shared: SSH command + validate

**Case title:** `Shared: SSH_Validation`
**Purpose:** same idea as telnet, over a persistent SSH session — use when the device
exposes a shell prompt instead of a raw command protocol.

```
steps:
# 1. Run command over SSH
- ssh.command:
host: ${device_ip}
username: ${device_username}
password: ${device_password}
prompt: '>'
command: '?Model'
store_as: ssh_response
# 2. Log the raw response
- test.log:
message: "SSH response: ${ssh_response}"
# 3. Assert expected content
- test.assert:
expression: "'${product}' in ssh_response"
message: "SSH response should contain product model ${product}"
# 4. Close the session
- ssh.disconnect:
host: ${device_ip}
```

---

## 4. Shared: WebSocket API call (OvrC-style)

**Case title:** `Shared: <Method_Name>` (e.g. `Shared: dxGetAbout`, `Shared: Firmware_Upgrade`)
**Purpose:** call a JSON-RPC-over-WebSocket device management API (OvrC `dx*` methods)
and assert on the response. See [jsonrpc-websocket.md](./jsonrpc-websocket.md) and
[ovrc-websocket.md](./ovrc-websocket.md) for the full protocol reference.

```
steps:
# 1. Call the API method
- websocket.send:
url: ${ovrc_ws_url}
subprotocols: firmware-protocol
method: dxGetAbout
data:
deviceId: ${mac}
version: 0
store_as: last_response
# 2. Assert no error in the response
- test.assert:
expression: "not_contains(last_response, 'error')"
# 3. Assert the response references this device
- test.assert:
expression: "contains(last_response, '${mac}')"
```

For a call that takes a payload (e.g. triggering a firmware update), add the extra field
under `data:` — everything else stays the same:

```
steps:
- websocket.send:
url: ${ovrc_ws_url}
subprotocols: firmware-protocol
method: dxUpdateFirmware
data:
deviceId: ${mac}
version: 0
url: ${upgrade_file}
store_as: last_response
- test.assert:
expression: "not_contains(last_response, 'error')"
```

---

## 5. Shared: Browser login / navigate

**Case title:** `Shared: Open_Webpage`, `Shared: Configure_Page`, etc. — keep each
navigation step as its own tiny `Shared:` case so `Feature:` cases can compose them.

```
steps:
# 1. Open the device web UI
- browser.open:
url: ${web_url}
# 2. Give the page a moment to settle
- test.sleep:
seconds: 2.0
```

```
steps:
# 1. Navigate to a sub-page from the landing page
- browser.click:
selector: //a[contains(text(),'CONFIGURE')]
```

Compose them from a `Feature:` case with `shared_step`:

```
steps:
- shared_step: Open_Webpage
- shared_step: Configure_Page
```

---

## 6. Feature: Firmware upgrade/downgrade orchestration

**Case title:** `Feature: Upgrade/Downgrade`
**Purpose:** the standard shape for a firmware regression run — read the current
version, decide whether an upgrade/downgrade is actually needed, run it via a `Shared:`
step, and confirm the version changed. Depends on `Shared: Get_Firmware_Version` and
`Shared: Upgrade` (or your device-specific equivalents) already existing in the suite.

```
steps:
# 1. Read current version
- shared_step: Get_Firmware_Version
# 2. Skip the upgrade if already on the target build
- eval.exec:
code: 'if message in upgrade_file: execute = False'
store_as: execute
# 3. Run the upgrade
- shared_step: Upgrade
# 4. Read the version again to confirm it changed
- shared_step: Get_Firmware_Version
```

`upgrade_file` here comes from a `Var:` firmware-discovery case (template 9 below) — keep
that case earlier in the run so `upgrade_file` is populated before this one executes.

---

## 7. Feature: Resiliency fault-injection loop

**Case title:** `Feature: Power Fault Insertion` / `Feature: Network Fault Insertion`
**Purpose:** repeat a fault (power cycle, network drop) at a series of timing offsets
during an operation, and confirm the device recovers each time. Depends on `Shared:`
steps for the fault itself (e.g. `Power_Fault`, `Network_Fault`) and for reading device
state (`Get_Firmware_Version`).

```
for_each: "[1, 10, 30, 50, 70]"
as: fault_offset_seconds
steps:
# 1. Start the long-running operation
- shared_step: Firmware_Dummy_Upgrade
- test.assert:
expression: "not_contains(last_response, 'error')"
# 2. Wait for the configured offset, then inject the fault
- test.sleep:
seconds: "${fault_offset_seconds}"
- shared_step: Power_Fault
# 3. Give the device time to recover
- test.sleep:
seconds: 300.0
# 4. Confirm it's back and responsive
- shared_step: Get_Firmware_Version
```

Swap `Power_Fault` for `Network_Fault` (or `ISP_Network_Fault`) to test the other fault
class with the same loop shape.

---

## 8. Feature: Data-driven UI loop

**Case title:** `Feature: Change Password` (or any "try N inputs, assert the same
outcome each time" UI test — negative-input validation, boundary testing, etc.)

```
steps:
- for_each: "['too-short', 'nouppercase1', 'NOLOWERCASE1', 'NoNumbersHere', 'valid-Pass1']"
loop_var: input_value
steps:
# 1. Navigate to the form
- shared_step: Open_Webpage
- shared_step: Configure_Page
# 2. Fill the field under test
- browser.fill:
value: ${input_value}
selector: input[type='password']
# 3. Submit
- browser.click:
role: button
name: Apply
- test.sleep:
seconds: 3.0
# 4. Assert the expected validation message (or success) appears
- browser.verify_text:
text: Password must contain at least three character types
selector: b
```

`for_each` + `as` (template 7) and `for_each` + `loop_var` (this template) are equivalent
— `as` reads slightly better for numeric ranges, `loop_var` for string lists. Either
form works; see [data-driven.md](./data-driven.md) for the full syntax.

---

## 9. Var: Firmware discovery (AWS S3 + CloudFront)

**Case title:** `Var: Firmware Manager`
**Purpose:** list available firmware builds in S3 (and their CloudFront-mirrored URLs),
pick the upgrade/downgrade candidates, and extract a version string for the run name —
so the TestRail run title records exactly which firmware was under test.

```
steps:
# 1. List firmware files in S3
- aws.list_files:
bucket_name: ${aws_bucket}
filename_pattern: ${filename_pattern}
folder_prefix: ${folder_prefix}
store_as: firmware_files
# 2. Pick the upgrade and downgrade candidates
- eval.run:
expression: firmware_files[0]
store_as: upgrade_file
- eval.run:
expression: firmware_files[1]
store_as: downgrade_file
# 3. Also resolve the CloudFront-mirrored URLs
- aws.list_files:
bucket_name: ${aws_bucket}
filename_pattern: ${filename_pattern}
folder_prefix: ${folder_prefix}
cloudfront_url: ${cloudfront_url}
store_as: cloudfront_firmwares
# 4. Extract a version string and stamp it into the run name
- eval.extract_version:
from_var: firmware_files
pattern: '<product>_(.*?)\.sec\.bin'
store_as: firmware_version
run_name: 'EASY_BDD: ${product} Smoke Test - ${firmware_version}'
```

Credentials for the S3 bucket (`aws_access_key_id` / `aws_secret_access_key`) belong in
`.env`, not in this case — see [aws-s3-integration.md](./aws-s3-integration.md).

---

## Notes on the source cases

These templates were generalized from real `Var:`/`Shared:`/`Feature:` cases in TestRail
suite `S106658` — real device IPs, passwords, and AWS keys have been replaced with
`${variable}` placeholders. If you pull a case from that suite directly as a starting
point instead of using these templates, **redact any literal credential before reusing
it elsewhere** — several of the source cases have real passwords typed directly into the
Preconditions field rather than referenced via `${...}` or `.env`. Prefer the `${...}`
form going forward so credentials live in one place.
