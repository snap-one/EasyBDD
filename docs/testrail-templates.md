# TestRail Case Templates

Copy-paste boilerplates for the test workflows we actually run in production, modeled on
real cases from suite `S106658` (WattBox firmware smoke suite). Credentials, device IPs,
and account keys from those cases are replaced with `${variable}` placeholders below —
never paste real secrets into a template or commit them to this repo.

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
6. [Shared: Power & network fault injection](#6-shared-power--network-fault-injection)
7. [Shared: Firmware transport (upgrade + version check)](#7-shared-firmware-transport-upgrade--version-check)
8. [Feature: Firmware upgrade/downgrade orchestration](#8-feature-firmware-upgradedowngrade-orchestration)
9. [Feature: Resiliency fault-injection loop](#9-feature-resiliency-fault-injection-loop)
10. [Feature: Data-driven UI loop](#10-feature-data-driven-ui-loop)
11. [Setup: Firmware discovery (Floci / AWS S3 + CloudFront)](#11-setup-firmware-discovery-floci--aws-s3--cloudfront)

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

# Only needed if this suite also uses the fault-injection templates (section 6) —
# these describe the shared lab rig (PDU + managed switch), not the device under test.
pdu_ip: 192.168.10.5
pdu_username: ${PDU_USERNAME}
pdu_password: ${PDU_PASSWORD}
pdu_telnet_port: 23
dut_outlet_number: 6
switch_host: 192.168.100.10
switch_username: ${NET_USERNAME}
switch_password: ${NET_PASSWORD}
switch_prompt: '#'
dut_port: 2
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
expression: "contains(ssh_response, '${product}')"
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
under `data:` — everything else stays the same. See section 7 below for the full
firmware-upgrade template built on top of this call.

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

## 6. Shared: Power & network fault injection

**Case titles:** `Shared: Power_Fault`, `Shared: Network_Fault`, plus the finer-grained
`Shared: Outlet_ON` / `Shared: Outlet_OFF` / `Shared: Network_ON` / `Shared: Network_OFF`.
**Purpose:** these are lab-rig utilities, not device-under-test logic — they power-cycle
the DUT via a shared WattBox-style PDU outlet and drop/restore its network link via a
shared managed switch port. Any project's resiliency suite (routers, APs, surveillance,
media distribution, etc.) can reuse the same four building blocks against its own DUT by
just pointing `dut_outlet_number` / `dut_port` at the right rig position. Depends on the
`pdu_*` / `switch_*` / `dut_*` variables from section 1.

**`Shared: Power_Fault`** — reset the DUT's outlet (power-cycle in one shot):

```
steps:
- telnet.send:
host: ${pdu_ip}
port: ${pdu_telnet_port}
username: ${pdu_username}
password: ${pdu_password}
command: '!OutletSet=${dut_outlet_number},RESET,1'
prompt: '>'
store_as: last_response
- test.assert:
expression: "not_contains(last_response, 'error')"
```

**`Shared: Outlet_OFF`** / **`Shared: Outlet_ON`** — hold power off for a controlled
duration instead of an instant reset (swap `OFF` for `ON` in the second case):

```
steps:
- telnet.send:
host: ${pdu_ip}
port: ${pdu_telnet_port}
username: ${pdu_username}
password: ${pdu_password}
command: '!OutletSet=${dut_outlet_number},OFF'
prompt: '>'
store_as: last_response
- test.assert:
expression: "not_contains(last_response, 'error')"
```

**`Shared: Network_Fault`** — shut the DUT's switch port down, then bring it back up
after a short pause (a full network fault-and-recover cycle in one step):

```
steps:
# 1. Drop the link
- telnet.send:
host: ${switch_host}
username: ${switch_username}
password: ${switch_password}
prompt: '${switch_prompt}'
commands: [configure, 'interface GigabitEthernet ${dut_port}', shutdown, end]
store_as: last_response
- test.assert:
expression: "not_contains(last_response, 'command unknown')"
# 2. Give the switch a moment, then restore the link
- test.sleep:
seconds: 10
- telnet.send:
host: ${switch_host}
username: ${switch_username}
password: ${switch_password}
prompt: '${switch_prompt}'
commands: [configure, 'interface GigabitEthernet ${dut_port}', 'no shutdown', end]
store_as: last_response
- test.assert:
expression: "not_contains(last_response, 'command unknown')"
```

**`Shared: Network_OFF`** / **`Shared: Network_ON`** — the split, one-directional version
for tests that need the link held down across other steps rather than auto-restored:

```
steps:
- telnet.send:
host: ${switch_host}
username: ${switch_username}
password: ${switch_password}
prompt: '${switch_prompt}'
commands: [configure, 'interface GigabitEthernet ${dut_port}', shutdown, end]
store_as: last_response
- test.assert:
expression: "not_contains(last_response, 'error')"
```

---

## 7. Shared: Firmware transport (upgrade + version check)

**Case titles:** `Shared: Firmware_Upgrade`, `Shared: Get_Firmware_Version`
**Purpose:** the two-sided transport used everywhere firmware is exercised — push a build
over the OvrC WebSocket API, then confirm the change over telnet. Split into two `Shared:`
cases because they run over completely different protocols and get composed independently
(e.g. `Get_Firmware_Version` is called both before and after an upgrade).

**`Shared: Firmware_Upgrade`** — trigger the update and confirm the call was accepted
(this does *not* wait for the flash/reboot to finish — pair it with a `test.sleep` and a
`Get_Firmware_Version` re-check, see section 8):

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
- test.assert:
expression: "contains(last_response, '${mac}')"
```

`${upgrade_file}` comes from the firmware-discovery `Setup:` case (section 11) — keep that
case earlier in the run so it's populated before this one executes. Duplicate this case as
`Shared: Firmware_Dummy_Upgrade` pointed at `${downgrade_file}` for the downgrade leg.

**`Shared: Get_Firmware_Version`** — read the currently-running version over telnet:

```
steps:
- telnet.send:
host: ${device_ip}
port: ${telnet_port}
username: ${device_username}
password: ${device_password}
command: "?Firmware"
prompt: '>'
store_as: last_response
- eval.exec:
code: firmware_version = str(last_response).split('?Firmware=')[1] if contains(last_response, '?Firmware=') else None
store_as: firmware_version
- test.print:
message: ${firmware_version}
```

Duplicate this case with a different `store_as`/variable name (e.g. `fw_version_before`,
`fw_version_after`) when a `Feature:` needs to compare the version on both sides of an
upgrade — see section 8.

---

## 8. Feature: Firmware upgrade/downgrade orchestration

**Case title:** `Feature: Upgrade/Downgrade`
**Purpose:** the standard shape for a firmware regression run — read the current
version, decide whether an upgrade/downgrade is actually needed, run it via a `Shared:`
step, and confirm the version changed. Depends on `Shared: Get_Firmware_Version` and
`Shared: Firmware_Upgrade` (section 7, or your device-specific equivalents) already
existing in the suite.

```
steps:
# 1. Read current version
- shared_step: Get_Firmware_Version
# 2. Skip the upgrade if already on the target build
- eval.exec:
code: 'if contains(upgrade_file, firmware_version): execute = False'
store_as: execute
# 3. Run the upgrade
- shared_step: Firmware_Upgrade
# 4. Give the device time to flash and reboot, then read the version again to confirm it changed
- test.sleep:
seconds: 300.0
- shared_step: Get_Firmware_Version
```

`upgrade_file` here comes from a `Setup:` firmware-discovery case (section 11) — keep
that case earlier in the run so `upgrade_file` is populated before this one executes.

---

## 9. Feature: Resiliency fault-injection loop

**Case title:** `Feature: Power Fault Insertion` / `Feature: Network Fault Insertion`
**Purpose:** repeat a fault (power cycle, network drop) at a series of timing offsets
during an operation, and confirm the device recovers each time. Depends on the fault
`Shared:` steps from section 6 (`Power_Fault`, `Network_Fault`) and the firmware-transport
`Shared:` steps from section 7 (`Get_Firmware_Version`, `Firmware_Upgrade`).

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

Swap `Power_Fault` for `Network_Fault` to test the other fault class with the same loop
shape — nothing else in the template changes since both fault steps have the same
"do the fault, assert `not_contains(last_response, ...)`" shape.

---

## 10. Feature: Data-driven UI loop

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

`for_each` + `as` (section 9) and `for_each` + `loop_var` (this template) are equivalent
— `as` reads slightly better for numeric ranges, `loop_var` for string lists. Either
form works; see [data-driven.md](./data-driven.md) for the full syntax.

---

## 11. Setup: Firmware discovery (Floci / AWS S3 + CloudFront)

**Case title:** `Setup: Firmware Manager`
**Purpose:** list available firmware builds, pick the upgrade/downgrade candidates, and
extract a version string for the run name — so the TestRail run title records exactly
which firmware was under test. Use the `Setup:` prefix (not `Var:`) so it always runs
once at the start of the run, before any `Feature:` case needs `${upgrade_file}`.

```
steps:
# 1. List firmware files (Floci local S3-compatible target — see aws-s3-integration.md
#    for the equivalent real-AWS aws.list_files call, same parameters)
- floci.list_files:
bucket_name: ${firmware_bucket}
filename_pattern: ${filename_pattern}
folder_prefix: ${folder_prefix}
store_as: firmware_files
local_paths_as: firmware_local_paths
# 2. Pick the upgrade and downgrade candidates
- eval.run:
expression: firmware_files[0]
store_as: upgrade_file
- eval.run:
expression: firmware_files[1]
store_as: downgrade_file
# 3. Resolve the local filesystem paths for the same two builds (needed if a later
#    step uploads the file directly rather than pointing the device at a URL)
- eval.run:
expression: firmware_local_paths[0]
store_as: firmware_upgrade_path
- eval.run:
expression: firmware_local_paths[1]
store_as: firmware_downgrade_path
# 4. Extract a version string and stamp it into the run name
- eval.extract_version:
from_var: firmware_files
pattern: '<product>_(.*?)\.sec\.bin'
store_as: firmware_version
run_name: 'EASYBDD: ${product} Smoke Test - ${firmware_version}'
```

Credentials for a real S3 bucket (`aws_access_key_id` / `aws_secret_access_key`) belong in
`.env`, not in this case — see [aws-s3-integration.md](./aws-s3-integration.md) for the
`aws.list_files` form and the Floci-vs-real-S3 tradeoffs.

---

## Notes on the source cases

These templates were generalized from real `Var:`/`Setup:`/`Shared:`/`Feature:` cases in
TestRail suite `S106658` — real device IPs, passwords, and AWS keys have been replaced
with `${variable}` placeholders. If you pull a case from that suite directly as a starting
point instead of using these templates, **redact any literal credential before reusing
it elsewhere** — several of the source cases have real passwords typed directly into the
Preconditions field rather than referenced via `${...}` or `.env`. Prefer the `${...}`
form going forward so credentials live in one place.

A working, generalized copy of these same templates also exists as real TestRail cases in
project `JDM Automation` (59), suite `Easy BDD: Common Templates` — duplicate that suite's
cases into your own project instead of retyping from this doc if you'd rather start from
a case TestRail already knows how to validate/run.
