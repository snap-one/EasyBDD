# Easy BDD Testing Framework

A TestRail-first test automation framework for web UI, REST API, and firmware resiliency testing. Test cases are authored directly in TestRail using plain dot-notation YAML — no programming required.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Authoring Tests in TestRail](#authoring-tests-in-testrail)
  - [Case prefix taxonomy](#case-prefix-taxonomy)
  - [Feature: case format](#feature-case-format)
  - [Variables in TestRail](#variables-in-testrail)
  - [Running from the CLI](#running-from-the-cli)
  - [Case templates](#case-templates)
- [Actions Reference](#actions-reference)
  - [Browser / Web UI](#browser--web-ui)
  - [API](#api)
  - [SSH](#ssh)
  - [Telnet](#telnet)
  - [Serial](#serial)
  - [WebSocket / OVRC / JSON-RPC](#websocket--ovrc--json-rpc)
  - [AWS S3](#aws-s3)
  - [Assertions and extraction](#assertions-and-extraction)
  - [Test utilities](#test-utilities)
  - [Eval](#eval)
- [Control Flow](#control-flow)
- [Shared Steps in TestRail](#shared-steps-in-testrail)
- [Connections](#connections)
- [Configuration](#configuration)
- [Local YAML (supplemental)](#local-yaml-supplemental)
- [Test Builder UI](#test-builder-ui)
- [AI Assistant Integration (MCP)](#ai-assistant-integration-mcp)
- [Migration Tools](#migration-tools)
- [CLI Reference](#cli-reference)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Installation

```bash
git clone <repository-url>
cd Easy_BDD
python -m venv .venv
source .venv/bin/activate     # macOS/Linux
# .venv\Scripts\activate      # Windows

pip install --upgrade pip
pip install -e .
playwright install chromium
```

Add credentials to `.env` in the project root:

```
TESTRAIL_URL=https://your-instance.testrail.com/
TESTRAIL_USERNAME=automation@example.com
TESTRAIL_API_KEY=your-api-key
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_DEFAULT_REGION=us-east-1
```

---

## Quick Start

**Find and run all pending TestRail tests in a project:**

```bash
python -m easybdd testrail-run --project-id 12
```

**Run a specific TestRail run by ID:**

```bash
python -m easybdd testrail-run --run-id 194434
```

**List runs available to execute:**

```bash
python -m easybdd testrail-list --project-id 12
```

Results are posted back to TestRail automatically — pass/fail/skip per case, plus a run summary. See [Authoring Tests in TestRail](#authoring-tests-in-testrail) for how to write the cases.

> **Running local YAML files:** `python -m easybdd run tests/cases/my_test.yaml` — see [Local YAML (supplemental)](#local-yaml-supplemental).

---

## Authoring Tests in TestRail

All test logic lives in TestRail. The runner discovers cases by their title prefix, reads their Preconditions field as YAML, executes the steps, and posts the result back.

### Case prefix taxonomy

Every case title must begin with one of these prefixes:

| Prefix | Purpose |
|---|---|
| `Feature: <name>` | **Primary test case.** Steps written inline in the Preconditions field as dot-notation YAML. |
| `Var: <name>` | Variable definitions injected into all Feature/Test cases in the run. |
| `Setup: <name>` | Runs before Feature/Test cases — use for authentication, device prep. |
| `Teardown: <name>` | Runs after all Feature/Test cases — use for cleanup and logout. |
| `Shared: <name>` | Reusable step library called by name from Feature: cases. |
| `Test: <name>` | Pointer test — body contains `tag:` or `file:` routing to a local YAML file. |

A typical TestRail run contains:

```
Var:  base_url           ← injects ${base_url} into all cases
Var:  device_ip          ← injects ${device_ip}
Setup: Login             ← auth steps, runs first
Feature: Create device   ← test case 1
Feature: Update firmware ← test case 2
Teardown: Logout         ← cleanup, runs last
```

### Feature: case format

Write dot-notation YAML directly in the **Preconditions** field of a `Feature:` case. No local files needed.

**Step format — dot-notation, flush-left params (paste directly into TestRail Preconditions):**

```
- service.verb:
param1: value1
param2: value2
```

The runner re-indents parameters automatically — no manual alignment needed in TestRail.

**Flow-style (single-line — preferred for complex params in TestRail):**

```
- service.verb: {param1: value1, param2: value2}
```

**Complete example — API test (Preconditions field):**

```
variables:
base_url: https://staging-api.example.com
device_id: 1001

steps:
- websocket.send:
url: "${base_url}/devices/${device_id}"
method: GET
store_as: device
- test.assert:
expression: "${device.status} == 'online'"
- test.log:
message: "Device ${device_id} is ${device.status}"
```

### Variables in TestRail

**Var: cases** — create a case titled `Var: device_ip` with this in the Preconditions field:

```yaml
device_ip: 192.168.1.100
device_user: admin
```

These key-value pairs are injected as variables into every Feature/Test case in the run. Use `Var:` cases for environment-specific values (IPs, URLs, credentials, firmware bucket names).

**Inline variables block** — within a Feature: case's Preconditions field:

```
variables:
timeout: 30
product: WB-800

steps:
- test.log:
message: "Testing ${product} at ${device_ip}"
```

Variables defined inline are scoped to that case. Variables from `Var:` cases are available across all cases.

**Environment variable references** — reference `.env` or shell environment variables:

```yaml
variables:
  password: "${DEVICE_PASSWORD}"
  api_key: "${API_GATEWAY_KEY}"
```

**Parameterized cases** — run the same steps against multiple data rows:

```
data:
- mac: D4:6A:91:29:0F:5A
  product: WB-800
- mac: A8:3B:76:11:CC:22
  product: WB-250

steps:
- ssh.connect:
host: "${mac}"
username: "${device_user}"
password: "${device_pass}"
- test.log:
message: "Testing ${product} at ${mac}"
- ssh.disconnect:
host: "${mac}"
```

### Running from the CLI

```bash
# Run all EASY_BDD: runs with pending tests in a project
python -m easybdd testrail-run --project-id 12

# Run a specific run by ID
python -m easybdd testrail-run --run-id 194434

# Quiet output (errors only)
python -m easybdd testrail-run --project-id 12 --quiet

# Skip datalake reporting for this run
python -m easybdd testrail-run --project-id 12 --no-datalake

# List runs available in a project
python -m easybdd testrail-list --project-id 12
```

The runner scans for runs whose name starts with `EASY_BDD:` (configurable via `TESTRAIL_RUN_PREFIX` in `.env` or `config/framework.yaml`).

### Case templates

Copy-paste templates for the three primary test types are in `examples/testrail/`:

| Template | File | Use for |
|---|---|---|
| API test | `examples/testrail/api_test.yaml` | REST API — auth, GET/PUT, assert, schema validation, 404 test |
| Browser / Web UI | `examples/testrail/browser_test.yaml` | Login flows, form fill, dropdown, cart, verify, screenshot |
| Firmware resiliency | `examples/testrail/firmware_resiliency_test.yaml` | SSH connect, S3 firmware discovery, flash, reboot, health check |

Paste the YAML into the Preconditions field of a `Feature:` case and adjust the variables.

---

## Actions Reference

All actions use `service.verb` dot-notation. In a TestRail `Feature:` case, write them as:

```
- service.verb:
param: value
```

### Browser / Web UI

| Action | Key Parameters |
|---|---|
| `browser.open` | `url`, `browser` (chromium/firefox/webkit), `headless` |
| `browser.navigate` | `url` |
| `browser.fill` | `selector`, `value` |
| `browser.click` | `selector` or `role` + `name` |
| `browser.double_click` | `selector` |
| `browser.hover` | `selector` |
| `browser.select` | `selector`, `value` |
| `browser.press_key` | `selector`, `key` |
| `browser.upload` | `selector`, `file` |
| `browser.wait_for` | `selector`, `timeout` |
| `browser.wait_for_url` | `url` (substring or glob), `timeout`; no `url` waits for page load |
| `browser.verify_text` | `text`, `selector` |
| `browser.verify_element` | `selector` |
| `browser.screenshot` | `filename`, `path` |
| `browser.scroll` | `selector` |
| `browser.back` | — |
| `browser.forward` | — |
| `browser.refresh` | — |
| `browser.close` | — |

**Examples:**

```
- browser.open:
url: "${base_url}/login"
- browser.fill:
selector: "input[name=email]"
value: "${username}"
- browser.click:
selector: "button[type=submit]"
# Role-based selector (preferred — more resilient than CSS)
- browser.click:
role: button
name: Apply
# Wait for element before interacting
- browser.wait_for:
selector: ".dashboard"
timeout: 15
- browser.verify_text:
selector: ".page-title"
text: Dashboard
- browser.screenshot:
name: after-login
# Target elements inside iframes
- browser.upload:
selector: "iframe >> #firmware-input"
file: Firmware/update.bin
```

### API

There is no dedicated REST helper action in this framework. API/JSON-RPC testing is done
over WebSocket via `websocket.send` / `websocket.receive` (see [WebSocket / OVRC / JSON-RPC](#websocket--ovrc--json-rpc)),
and generic response assertions are done with `test.assert_response` / `test.assert_schema`.

| Action | Key Parameters |
|---|---|
| `websocket.send` | `url`, `method`, `data`, `headers`, `store_as` |
| `websocket.receive` | `url`, `wait_for`, `timeout`, `store_as` |
| `test.assert_response` | `status`, `body`, `contains`, `schema`, `headers` |
| `test.assert_schema` | `schema`, `data` |

**Examples:**

```
# Send a JSON-RPC request over WebSocket
- websocket.send:
url: "${base_url}"
method: dxGetAbout
data:
  deviceId: "${device_id}"
store_as: device
# Assert on the response
- test.assert_response:
status: 200
contains: "online"
# JSON schema validation
- test.assert_schema:
schema: {type: object, required: [id, status, name], properties: {id: {type: integer}, status: {type: string}, name: {type: string}}}
data: "${device}"
```

### SSH

Persistent SSH connections are pooled by `host:port` across steps within the same test. Use `ssh.*` for interactive sessions (firmware testing, device CLI). Note that `ssh.command` still takes `host` on every call (it looks up the pooled connection for that host rather than an implicit "current session").

| Action | Key Parameters |
|---|---|
| `ssh.connect` | `host`, `username`, `password`, `timeout` |
| `ssh.command` | `host`, `command`, `store_as`, `timeout` |
| `ssh.disconnect` | `host` |

**Example:**

```
- ssh.connect:
host: "${device_ip}"
username: "${device_user}"
password: "${device_pass}"
timeout: 30
- ssh.command:
host: "${device_ip}"
command: cat /etc/firmware_version
store_as: fw_version
- test.assert:
expression: "'2.' in ${fw_version}"
- ssh.disconnect:
host: "${device_ip}"
```

For one-shot commands without session state, use `command.ssh`:

```
- command.ssh:
host: "${device_ip}"
username: "${device_user}"
password: "${device_pass}"
command: "uptime"
store_as: uptime
```

### Telnet

`telnet.send` is a single stateless action that bundles connect + authenticate + send in one call.

| Action | Key Parameters |
|---|---|
| `telnet.send` | `host`, `port`, `username`, `password`, `command`, `prompt`, `timeout`, `store_as` |

**Example:**

```
- telnet.send:
host: "${device_ip}"
port: 23
username: "${device_user}"
password: "${device_pass}"
command: "show version"
store_as: version_output
- test.assert:
expression: "'${expected_version}' in ${version_output}"
```

### Serial

`serial.send` is a single stateless action — port/baud rate are passed on each call.

| Action | Key Parameters |
|---|---|
| `serial.send` | `command`, `port`, `baud_rate`, `prompt`, `timeout`, `store_as` |

**Example:**

```
- serial.send:
command: "?status\r\n"
port: COM3
baud_rate: 115200
store_as: serial_response
- test.assert:
expression: "'OK' in ${serial_response}"
```

### WebSocket / OVRC / JSON-RPC

`websocket.send` connects to a WebSocket endpoint and, when `method` is given, wraps `data` in a
JSON-RPC 2.0 envelope — this is how OvrC/firmware JSON-RPC calls are made (see
`docs/jsonrpc-websocket.md` for the full payload format). Many `ovrc.*` spellings are aliases for
the equivalent `jsonrpc.*` action (e.g. `ovrc.connect` → `jsonrpc.connect`, `ovrc.call` → `jsonrpc.send`).

| Action | Key Parameters |
|---|---|
| `websocket.send` | `url`, `method`, `data`, `headers`, `timeout`, `wait_for`, `store_as` |
| `websocket.receive` | `url`, `wait_for`, `timeout`, `store_as` |
| `websocket.connect` | `url` |
| `websocket.disconnect` | `url` |
| `jsonrpc.connect` (alias: `ovrc.connect`) | `url`, `device_id`, `timeout` |
| `jsonrpc.send` (alias: `ovrc.call` / `ovrc.send`) | *(any additional parameters accepted)* |
| `jsonrpc.get_about` (alias: `ovrc.get_about`) | `store_as` |
| `jsonrpc.disconnect` (alias: `ovrc.disconnect`) | — |

**Example:**

```
- websocket.send:
url: "${ws_url}"
method: dxGetAbout
data:
  deviceId: "${mac}"
  version: 0
store_as: ws_response
- test.assert:
expression: "'error' not in str(${ws_response})"
```

### AWS S3

| Action | Key Parameters |
|---|---|
| `aws.list_files` | `bucket_name`, `folder_prefix`, `file_extension`, `filename_pattern`, `store_as` |
| `aws.get_latest` | `store_as` |
| `aws.upload` | `bucket_name`, `file_path`, `key`, `store_as` |
| `aws.delete_folder` | `bucket_name`, `folder_prefix` |

**Example:**

```
- aws.list_files:
bucket_name: firmware-releases
folder_prefix: product-x/stable
file_extension: .bin
store_as: firmware_files
- aws.get_latest:
store_as: latest_firmware
- test.log:
message: "Latest firmware: ${latest_firmware.version} at ${latest_firmware.url}"
```

### Assertions and extraction

There is no dedicated `test.extract` action. Pull nested values out of a stored response with
`eval.run` (a single Python expression) instead — see [Eval](#eval).

| Action | Key Parameters |
|---|---|
| `test.assert` | `expression` (Python-style boolean expression string), `message` |
| `test.assert_schema` | `schema` (JSON Schema object), `data` |
| `test.assert_response` | `status`, `body`, `contains`, `schema`, `headers` |
| `test.assert_element_count` | `selector`, `count`, `timeout` |
| `test.assert_element_visible` / `test.assert_element_not_visible` | `selector`, `timeout` |
| `test.assert_element_enabled` / `test.assert_element_disabled` | `selector`, `timeout` |
| `test.assert_text_contains` / `test.assert_text_equals` | `selector`, `text`, `timeout` |
| `test.assert_value` | `selector`, `value`, `timeout` (input/select current value) |
| `test.assert_url` | `url` (substring or glob), `exact`, `timeout` |
| `browser.assert_checked` / `browser.assert_unchecked` | `selector`, `timeout` |
| `test.check_assertions` | — (flush soft assertions) |

**Examples:**

```
# Equality
- test.assert:
expression: "${last_status_code} == 200"
# Contains substring
- test.assert:
expression: "'access_token' in ${response_body}"
# Does not contain
- test.assert:
expression: "'error' not in ${device.status}"
# Non-empty
- test.assert:
expression: "${fw_version} != ''"
# Membership in a list
- test.assert:
expression: "${last_status_code} in [200, 201, 204]"
# Greater than
- test.assert:
expression: "${process_count} > 0"
message: "Expected at least one running process"
# JSON schema validation
- test.assert_schema:
schema: {type: object, required: [id, status, name], properties: {id: {type: integer}, status: {type: string}, name: {type: string}}}
data: "${device}"
# Flush soft assertions (fail the test if any soft assertion failed)
- test.check_assertions:
# Extract a nested value from a stored response with eval.run
- eval.run:
expression: "login_response['data']['user']['id']"
store_as: user_id
```

### Test utilities

| Action | Key Parameters |
|---|---|
| `test.sleep` | `seconds` |
| `test.log` | `message` |
| `test.print` | `message` |
| `test.run` | `path` (run a local YAML test as a step) |

**Examples:**

```
- test.sleep:
seconds: 30
- test.log:
message: "Waiting for device ${device_ip} to reboot..."
# Run a shared local YAML test as a sub-step
- test.run:
path: tests/cases/shared/login.yaml
```

### Eval

Execute Python expressions in the test context. Use for complex data transformations that don't need a dedicated action.

| Action | Key Parameters |
|---|---|
| `eval.exec` | `code` (multi-line Python), `store_as` |
| `eval.run` | `expression` (single expression), `store_as`, `code` |

**Examples:**

```
# Extract nested value with Python
- eval.exec:
code: |
  token = auth_response['data']['access_token']
  expiry = auth_response['data']['expires_in']
# Evaluate an expression and store the result
- eval.run:
expression: "auth_response.get('firmware_version', 'unknown')"
store_as: fw_version
```

---

## Control Flow

Control flow constructs work in both TestRail `Feature:` cases and local YAML files.

### For each (loop over a list)

`for_each` takes an `items:` list and a `steps:` block. Each item is available inside the loop as `${item}`.

```
- for_each:
  items: [1, 10, 30, 60]
  steps:
  - test.sleep:
    seconds: "${item}"
  - test.assert:
    expression: "${device.status} == 'online'"
```

Loop over a list of dicts:

```
- for_each:
  items: [{mac: "D4:6A:91:29:0F:5A", product: "WB-800"}, {mac: "A8:3B:76:11:CC:22", product: "WB-250"}]
  steps:
  - ssh.connect:
    host: "${item.mac}"
    username: "${device_user}"
    password: "${device_pass}"
  - test.log:
    message: "Connected to ${item.product}"
  - ssh.disconnect:
    host: "${item.mac}"
```

### Repeat (poll / retry loop)

There is no `while:` construct. Use `repeat:` with a fixed `count:` to poll — for example, waiting
for a device to become ready:

```
- repeat:
  count: 30
  steps:
  - websocket.send:
    url: "${base_url}"
    method: dxGetAbout
    store_as: device_state
  - test.sleep:
    seconds: 5
```

### Conditional (if / else)

`if:` takes `condition:` + `steps:`, with an optional sibling `else:` list.

```
- if:
  condition: "${current_version} != ${target_version}"
  steps:
  - browser.upload:
    selector: "#firmware-input"
    file: "Firmware/${firmware_file}"
  - browser.click:
    role: button
    name: Upgrade
  else:
  - test.log:
    message: "Firmware already at target version — skipping"
```

### Try / Except / Finally

There is no `try:`/`except:`/`finally:` construct in this framework. Write the steps directly —
if a step is expected to sometimes fail without aborting the test, that must be handled by the
step itself (e.g. via soft assertions), not by a try/except wrapper:

```
- ssh.command:
  host: "${device_ip}"
  command: "reboot"
- test.sleep:
  seconds: 30
```

### Parallel

`parallel:` runs its `steps:` concurrently:

```
- parallel:
  steps:
  - telnet.send:
    host: "${device_ip}"
    command: ping
  - test.sleep:
    seconds: 2
```

---

## Shared Steps in TestRail

Create a case titled `Shared: <step_name>` and write the reusable steps in its Preconditions field. Other `Feature:` cases call it by name.

**Defining a shared step (`Shared: authenticate` in TestRail):**

```
steps:
- websocket.send:
url: "${base_url}"
method: dxLogin
data:
  username: "${API_USERNAME}"
  password: "${API_PASSWORD}"
store_as: auth_response
- test.assert:
expression: "'error' not in str(${auth_response})"
- eval.run:
expression: "auth_response['result']['access_token']"
store_as: token
```

**Calling it from a `Feature:` case:**

```
steps:
- shared_step: authenticate
- websocket.send:
url: "${base_url}"
method: dxListDevices
headers: {Authorization: "Bearer ${token}"}
store_as: devices
- test.assert:
expression: "'error' not in str(${devices})"
```

The runner automatically syncs all `Shared:` cases in the run before executing `Feature:` cases.

---

## Connections

Persistent connections (SSH, Telnet, Serial, WebSocket) are pooled across steps within the same test. Each unique `host:port` combination is reused automatically — you do not need to explicitly open/close connections between steps unless you want to reset state.

---

## Configuration

`config/framework.yaml`:

```yaml
config:
  browser:
    default: chrome
    headless: true
    window_size: [1920, 1080]
    timeout: 30

  api:
    timeout: 30
    verify_ssl: true
    max_retries: 3

  testrail:
    run_prefix: "EASY_BDD:"          # Run name prefix to scan for
    running_status_id: 7              # ID of the "Running" custom status

  reporting:
    output_dir: reports
    screenshots: true
    html_report: true

  parallel:
    workers: 2

environments:
  staging:
    base_url: https://staging.example.com
    api_url: https://api-staging.example.com
  production:
    base_url: https://example.com
    api_url: https://api.example.com
```

Environment variables override `framework.yaml` for sensitive values — see `.env.example`.

---

## Local YAML (supplemental)

> **This section is supplemental.** The primary authoring surface is TestRail.
> Local YAML is useful for: one-off debugging runs, CI pipelines that don't use
> TestRail, or `Test:` cases that point to existing YAML files.

### File format

```
name: Login and verify dashboard
description: Verifies a user can log in and reach the dashboard
tags: [smoke, browser]

variables:
base_url: https://staging.example.com
username: "${STAGING_USER}"
password: "${STAGING_PASS}"

steps:
- browser.open:
url: "${base_url}/login"
- browser.fill:
selector: "#username"
value: "${username}"
- browser.fill:
selector: "#password"
value: "${password}"
- browser.click:
role: button
name: Sign In
- browser.wait_for:
selector: ".dashboard"
- browser.verify_text:
selector: "h1"
text: Dashboard
```

Optional `setup` and `teardown` sections run before/after `steps` regardless of pass/fail:

```
setup:
- browser.open:
url: "${base_url}"

teardown:
- browser.screenshot:
name: final-state
```

### Running local YAML

```bash
# Single test
python -m easybdd run tests/cases/my_test.yaml

# Folder (all tests)
python -m easybdd run tests/cases/networking/

# By tag
python -m easybdd run --tags smoke
python -m easybdd run --tags browser,api

# Visible browser
python -m easybdd run tests/cases/my_test.yaml --headed

# Specific environment
python -m easybdd run --env staging
```

### Shared steps (local)

Global shared steps — `shared_steps.yaml` at the project root:

```
authenticate:
description: Log in and store auth token
steps:
- websocket.send:
  url: "${base_url}"
  method: dxLogin
  data:
    username: "${username}"
    password: "${password}"
  store_as: auth_response
- eval.run:
  expression: "auth_response['result']['access_token']"
  store_as: token
```

Workspace-local — `tests/cases/{workspace}/shared_steps.yaml` (overrides global on name collision).

Call with:

```
steps:
- shared_step: authenticate
```

### Variable scope (local YAML)

Resolution order (highest to lowest priority):

1. Test-level `variables:` block
2. Suite variables
3. Active environment from `--env`
4. `.env` file / shell environment variables

### Test: case (TestRail pointer to local YAML)

A `Test:` case in TestRail routes to a local YAML file via its Preconditions field:

```yaml
# By tag — runs all local YAML tests that have this tag
tag: smoke

# Or by explicit file path
file: tests/cases/networking/login.yaml
```

---

## Test Builder UI

A web interface for authoring TestRail cases without writing YAML by hand. Engineers pick actions from the framework catalog, fill in guided forms, and publish `Var:` / `Shared:` / `Setup:` / `Teardown:` / `Feature:` cases straight into a TestRail suite — no syntax or action-name spelling to get wrong.

```bash
python frontend/start_testrail_builder.py          # http://localhost:8091
python frontend/start_testrail_builder.py --port 9000
```

Uses the same TestRail credentials as the runner (`.env`: `TESTRAIL_URL`, `TESTRAIL_USERNAME`, `TESTRAIL_API_KEY`).

**Production instance:** the builder runs persistently on the main Jenkins server as the `easybdd-testrail-builder` systemd service (enabled at boot) — no need to run it locally. Open **<jenkins_url>:8091**. See [ONBOARDING.md](ONBOARDING.md#production-instance) for service management commands.

What it does:

- **Case types** — build any of the five case types; the correct title prefix is applied automatically.
- **Step palette** — every action the runner supports (Browser, API, SSH, Telnet, Serial, WebSocket, OvrC, AWS, Floci, Eval, Test utilities…), searchable, with per-parameter forms, required-field markers, and help text.
- **Control flow** — for_each / if-else / repeat / parallel blocks with nested steps.
- **Shared steps** — call `Shared:` cases from the selected suite by picking them from a dropdown.
- **Live preview + validation** — the Preconditions body is generated server-side and round-trip parsed with the runner's own parser before publishing, so what lands in TestRail is guaranteed to execute. Typos get "did you mean" suggestions.
- **Publish & run** — create or update cases in a chosen section, then assemble selected cases into a run (run prefix added automatically) ready for `python -m easybdd testrail-run --run-id <id>`.
- **Edit existing cases** — click any case in the suite browser to load it back into the editor. Legacy-format bodies load as a raw step with a warning instead of being silently dropped.

---

## AI Assistant Integration (MCP)

Easy BDD exposes the framework to AI assistants (Claude, Cursor, GitHub Copilot Chat) via the **Model Context Protocol (MCP)**.

### Claude Desktop & Cursor (recommended)

Install the packaged `.mcpb` extension (no manual JSON editing required):

```bash
make build-mcpb   # creates easy-bdd-<version>.mcpb
```

Then open the `.mcpb` file with Claude Desktop or Cursor. You'll be prompted for optional credentials (TestRail URL/API key, Ollama base URL), which the server injects as environment variables.

Requirements: `uv` must be installed on your machine (the extension uses `uv run` to launch the server).

### Manual setup (Claude Code CLI, VS Code, other clients)

Add to your MCP config (`.claude/settings.json` or equivalent):

```json
{
  "mcpServers": {
    "easy-bdd": {
      "command": "/path/to/easybdd/.venv/bin/python",
      "args": ["-m", "easybdd", "mcp-serve"],
      "cwd": "/path/to/easybdd"
    }
  }
}
```

### Available Tools & Prompts

**Tools** — call these directly in your AI chat:
- `list_tests`, `get_test`, `validate_test` — browse and validate YAML
- `run_tests` — execute tests (dry-run by default)
- `preview_fix`, `apply_fix` — auto-correct syntax errors
- `get_failure_trace` — debug the last failure
- `probe_selector`, `fix_test_selectors` — heal broken CSS/ARIA selectors on live pages
- `get_testrail_run_failures`, `validate_testrail_case` — TestRail integration
- `import_playwright_recording`, `ollama_generate_tests`, `ollama_analyze_test` — AI-powered test authoring
- `crawl_device` — auto-generate tests from a live UI

**Prompts** — use these via the MCP client's prompt picker (Claude Desktop `+` menu):
- `generate_tests` — write YAML test cases for a module
- `debug_failure` — diagnose why a test failed
- `validate_and_fix` — interactively fix syntax errors
- `debug_testrail_run` — triage every failure in a TestRail run
- `validate_testrail_suite` — audit all cases in a suite for errors
- `create_test_from_description` — generate tests from plain English + optionally push to TestRail

See [MCP Setup Guide](docs/mcp-setup.md) for detailed setup, remote access (Streamable HTTP), and integration with all major IDEs.

---

## Migration Tools

### From Robot Framework

Converts `.robot` files to Easy BDD dot-notation YAML.

```bash
python frontend/robot_migrator.py input.robot --output tests/cases/converted.yaml
```

| Robot Framework | Easy BDD |
|---|---|
| `Open Browser ${URL}` | `browser.open url: ${URL}` |
| `Input Text locator value` | `browser.fill selector: locator value: value` |
| `Click Element locator` | `browser.click selector: locator` |
| `Sleep 5s` | `test.sleep seconds: 5` |
| `GET ${url}` | `websocket.send url: ${url} method: GET` |
| User-defined keywords | `shared_step: keyword_slug` |

### From Previous BDD Framework (mybdd / pytest-bdd)

Converts pipe-delimited keyword format from the previous custom framework, including `.feature` files and raw TestRail step blocks.

```bash
python frontend/bdd_migrator.py --run-id <testrail_run_id>
```

| mybdd syntax | Easy BDD |
|---|---|
| `browser \| {"command": "open", "param": "url"} \|` | `browser.open url: url` |
| `browser \| {"command": "click_by_role", ...} \|` | `browser.click role: button name: Apply` |
| `sleep \| 15 \|` | `test.sleep seconds: 15` |
| `telnet \| {"host": "h", "command": "cmd"} \|` | `telnet.send host: h command: cmd` |
| `ssh \| {"host": "h", "command": "cmd"} \|` | `ssh.command host: h command: cmd` |
| `webservice \| $url \| GET \| /path \| {} \|` | `websocket.send url: ${url}/path method: GET` |
| `webservice \| $url \| SEND \| method \| {...} \|` | `websocket.send data: {...}` |
| `function \| {"name": "assert", ...} \|` | `test.assert expression: ...` |
| `\| value \| in response` | `test.assert expression: "value in ${last_response}"` |
| `response_code \| 200 \|` | `test.assert expression: "${last_status_code} == 200"` |
| `$variable` | `${variable}` |

---

## CLI Reference

```bash
# TestRail — primary
python -m easybdd testrail-run --project-id 12
python -m easybdd testrail-run --run-id 194434
python -m easybdd testrail-run --project-id 12 --quiet
python -m easybdd testrail-run --project-id 12 --no-datalake
python -m easybdd testrail-list --project-id 12

# Local YAML — supplemental
python -m easybdd run tests/cases/my_test.yaml
python -m easybdd run tests/cases/my_test.yaml --headed
python -m easybdd run tests/cases/ --tags smoke
python -m easybdd run --env staging

# Validation
python -m easybdd validate tests/cases/

# Help
python -m easybdd --help
python -m easybdd testrail-run --help
```

---

## Project Structure

```
Easy_BDD/
├── easybdd/
│   ├── core/
│   │   ├── runner.py              # Execution engine, ActionRegistry, control flow
│   │   ├── testrail_runner.py     # TestRail lifecycle — find, execute, post results
│   │   ├── testrail_reporter.py   # Datalake reporting
│   │   ├── parser.py              # YAML parser, YAML repair utilities
│   │   └── validator.py           # Step schema and syntax validation
│   └── services/
│       ├── browser_service.py
│       ├── api_service.py
│       ├── aws_service.py
│       ├── ssh_service.py
│       ├── serial_service.py
│       ├── telnet_service.py
│       └── testrail_service.py
├── examples/
│   └── testrail/
│       ├── api_test.yaml              # API test template
│       ├── browser_test.yaml          # Browser / web UI test template
│       └── firmware_resiliency_test.yaml  # SSH firmware resiliency template
├── config/
│   └── framework.yaml
├── frontend/
│   ├── mcp_server.py              # MCP server for AI assistant integration
│   ├── bdd_migrator.py            # mybdd → Easy BDD migration
│   ├── robot_migrator.py          # Robot Framework → Easy BDD migration
│   ├── testrail_builder.py        # Test Builder UI backend (publish to TestRail)
│   ├── start_testrail_builder.py  # Test Builder UI launcher (port 8091)
│   ├── static/testrail_builder.html  # Test Builder UI frontend
│   ├── action_definitions.py      # Action catalog (used by Test Builder UI)
│   └── test_builder_app.py        # [DEPRECATED] old local web builder
├── tests/                         # Local YAML test files (supplemental)
│   └── cases/{workspace}/
│       ├── shared_steps.yaml
│       └── *.yaml
├── reports/
├── shared_steps.yaml              # Global shared steps (local YAML)
└── .env
```

---

## Troubleshooting

**No runs found**

Ensure the TestRail run name starts with `EASY_BDD:` (or the configured `run_prefix`). Verify `.env` contains `TESTRAIL_URL`, `TESTRAIL_USERNAME`, and `TESTRAIL_API_KEY`.

**YAML parse errors in TestRail case**

The runner auto-repairs common TestRail rich-text formatting issues (HTML tags, indentation, quoted strings). If a case still fails to parse, paste the Preconditions content into a YAML validator to find the issue. Avoid smart quotes and non-breaking spaces — use plain ASCII.

**Step not recognised / "Unknown action"**

Check the action name uses dot-notation: `browser.click`, not `click element`. Deprecated space-separated names emit a warning and still work, but should be updated.

**Browser does not open**

```bash
playwright install chromium
python -m easybdd run tests/cases/my_test.yaml --headed
```

**SSH connection refused after reboot**

`ssh.connect` has no built-in retry parameters. Wrap it in a `repeat:` block with a `test.sleep`
between attempts to wait for the device to come back:

```
- repeat:
count: 5
steps:
- ssh.connect:
  host: "${device_ip}"
  username: "${device_user}"
  password: "${device_pass}"
- test.sleep:
  seconds: 15
```

**TestRail `running_status_id` error**

Set the correct ID for your TestRail instance's "Running" custom status in `.env`:

```
TESTRAIL_RUNNING_STATUS_ID=7
```

Check the value at **Administration → Statuses** in TestRail.

**Getting help**

```bash
python -m easybdd --help
python -m easybdd testrail-run --help
```
