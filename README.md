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
- api.post:
url: ${base_url}/auth/login
body: {username: "${API_USERNAME}", password: "${API_PASSWORD}"}
store_as: auth_response
- test.assert:
value: ${last_status_code}
equals: 200
- test.extract:
from: ${auth_response}
path: access_token
store_as: token
- api.get:
url: ${base_url}/devices/${device_id}
headers: {Authorization: "Bearer ${token}"}
store_as: device
- test.assert:
value: ${device.status}
equals: online
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
  password: ${DEVICE_PASSWORD}
  api_key: ${API_GATEWAY_KEY}
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
host: ${mac}
username: ${device_user}
password: ${device_pass}
- test.log:
message: "Testing ${product} at ${mac}"
- ssh.disconnect: {}
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
| `browser.upload` | `selector`, `file_path` |
| `browser.wait_for` | `selector`, `timeout` |
| `browser.verify_text` | `selector`, `text` or `contains` |
| `browser.verify_element` | `selector`, `visible` |
| `browser.screenshot` | `name` |
| `browser.scroll` | `selector` |
| `browser.back` | — |
| `browser.forward` | — |
| `browser.refresh` | — |
| `browser.close` | — |

**Examples:**

```
- browser.open:
url: ${base_url}/login
- browser.fill:
selector: "input[name=email]"
value: ${username}
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
file_path: Firmware/update.bin
```

### API

| Action | Key Parameters |
|---|---|
| `api.get` | `url`, `headers`, `store_as` |
| `api.post` | `url`, `body`, `headers`, `store_as` |
| `api.put` | `url`, `body`, `headers`, `store_as` |
| `api.patch` | `url`, `body`, `headers`, `store_as` |
| `api.delete` | `url`, `headers`, `store_as` |
| `api.request` | `method`, `url`, `body`, `headers`, `store_as` |

**Examples:**

```
# POST with JSON body
- api.post:
url: ${base_url}/auth/login
body: {username: "${username}", password: "${password}"}
store_as: login_response
- test.assert:
value: ${last_status_code}
equals: 200
# GET with auth header
- api.get:
url: ${base_url}/devices/${device_id}
headers: {Authorization: "Bearer ${token}"}
store_as: device
# Extract a value from the response
- test.extract:
from: ${login_response}
path: access_token
store_as: token
# Expect a specific status (assertion built-in)
- api.delete:
url: ${base_url}/sessions/${session_id}
headers: {Authorization: "Bearer ${token}"}
expected_status: 204
```

After any API step: `${last_status_code}` holds the HTTP status, `${last_response}` the raw body text, and `${last_response_dict}` the parsed JSON.

### SSH

Stateful SSH sessions persist across steps within the same test. Use `ssh.*` for interactive sessions (firmware testing, device CLI).

| Action | Key Parameters |
|---|---|
| `ssh.connect` | `host`, `username`, `password`, `timeout`, `retry`, `retry_delay` |
| `ssh.command` | `command`, `store_as`, `timeout`, `ignore_error` |
| `ssh.disconnect` | — |

**Example:**

```
- ssh.connect:
host: ${device_ip}
username: ${device_user}
password: ${device_pass}
timeout: 30
retry: 3
retry_delay: 10
- ssh.command:
command: cat /etc/firmware_version
store_as: fw_version
- test.assert:
value: ${fw_version}
contains: "2."
- ssh.disconnect: {}
```

For one-shot commands without session state, use `command.ssh`:

```
- command.ssh:
host: ${device_ip}
username: ${device_user}
password: ${device_pass}
command: "uptime"
store_as: uptime
```

### Telnet

| Action | Key Parameters |
|---|---|
| `telnet.connect` | `host`, `port`, `username`, `password` |
| `telnet.command` | `command`, `store_as`, `timeout` |
| `telnet.send` | `data`, `store_as` |
| `telnet.disconnect` | — |

**Example:**

```
- telnet.connect:
host: ${device_ip}
port: 23
username: ${device_user}
password: ${device_pass}
- telnet.command:
command: "show version"
store_as: version_output
- test.assert:
value: ${version_output}
contains: ${expected_version}
- telnet.disconnect: {}
```

### Serial

| Action | Key Parameters |
|---|---|
| `serial.connect` | `port`, `baudrate` |
| `serial.send` | `data`, `store_as` |
| `serial.disconnect` | — |

**Example:**

```
- serial.connect:
port: COM3
baudrate: 115200
- serial.send:
data: "?status\r\n"
store_as: serial_response
- test.assert:
value: ${serial_response}
contains: OK
```

### WebSocket / OVRC / JSON-RPC

| Action | Key Parameters |
|---|---|
| `websocket.send` | `url`, `data`, `store_as` |
| `websocket.connect` | `url` |
| `websocket.disconnect` | — |
| `ovrc.connect` | `device_id`, `account_id` |
| `ovrc.command` | `method`, `params`, `store_as` |
| `jsonrpc.call` | `method`, `params`, `store_as` |

**Example:**

```
- websocket.send:
url: ${ws_url}
data: {deviceId: "${mac}", version: 0}
store_as: ws_response
- test.assert:
value: ${ws_response}
not_contains: error
```

### AWS S3

| Action | Key Parameters |
|---|---|
| `aws.list_files` | `bucket_name`, `folder_prefix`, `file_extension`, `filename_pattern`, `store_as` |
| `aws.get_latest` | `files`, `store_as` |
| `aws.download` | `bucket_name`, `key`, `dest_path` |

**Example:**

```
- aws.list_files:
bucket_name: firmware-releases
folder_prefix: product-x/stable
file_extension: .bin
store_as: firmware_files
- aws.get_latest:
files: ${firmware_files}
store_as: latest_firmware
- test.log:
message: "Latest firmware: ${latest_firmware.version} at ${latest_firmware.url}"
```

### Assertions and extraction

| Action | Key Parameters |
|---|---|
| `test.assert` | `value`, `equals` / `contains` / `not_contains` / `not_empty` / `greater_than` / `in` |
| `test.assert_schema` | `value`, `schema` (JSON Schema object) |
| `test.assert_response` | `status`, `contains` |
| `test.extract` | `from`, `path`, `store_as` |
| `test.check_assertions` | — (flush soft assertions) |

**Examples:**

```
# Equality
- test.assert:
value: ${last_status_code}
equals: 200
# Contains substring
- test.assert:
value: ${response_body}
contains: "access_token"
# Does not contain
- test.assert:
value: ${device.status}
not_contains: error
# Non-empty
- test.assert:
value: ${fw_version}
not_empty: true
# Membership in a list
- test.assert:
value: ${last_status_code}
in: [200, 201, 204]
# Greater than
- test.assert:
value: ${process_count}
greater_than: 0
# JSON schema validation
- test.assert_schema:
value: ${device}
schema: {type: object, required: [id, status, name], properties: {id: {type: integer}, status: {type: string}, name: {type: string}}}
# Soft assertion — test continues; failures reported at end
- test.assert:
value: ${metric}
greater_than: 0
soft: true
# Flush soft assertions (fail the test if any soft assertion failed)
- test.check_assertions: {}
# Extract a nested value from a response dict
- test.extract:
from: ${login_response}
path: data.user.id
store_as: user_id
```

### Test utilities

| Action | Key Parameters |
|---|---|
| `test.sleep` | `seconds` |
| `test.log` | `message` |
| `test.print` | `message` |
| `test.run` | `path` (run a local YAML test as a step) |
| `test.data` | inline data loop — see [Control Flow](#control-flow) |

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
| `eval.exec` | `code` (multi-line Python) |
| `eval.run` | `expression` (single expression), `store_as` |

**Examples:**

```
# Extract nested value with Python
- eval.exec:
code: |
  token = last_response_dict['data']['access_token']
  expiry = last_response_dict['data']['expires_in']
# Evaluate an expression and store the result
- eval.run:
expression: "last_response_dict.get('firmware_version', 'unknown')"
store_as: fw_version
```

---

## Control Flow

Control flow constructs work in both TestRail `Feature:` cases and local YAML files.

### For each (loop over a list)

```
- for_each: [1, 10, 30, 60]
loop_var: wait_seconds
steps:
- test.sleep:
  seconds: ${wait_seconds}
- test.assert:
  value: ${device.status}
  equals: online
```

Loop over a list of dicts:

```
- for_each: [{mac: "D4:6A:91:29:0F:5A", product: "WB-800"}, {mac: "A8:3B:76:11:CC:22", product: "WB-250"}]
loop_var: device
steps:
- ssh.connect:
  host: ${device.mac}
  username: ${device_user}
  password: ${device_pass}
- test.log:
  message: "Connected to ${device.product}"
- ssh.disconnect: {}
```

### While loop

```
- while: "device_state != 'ready'"
loop_limit: 30
steps:
- api.get:
  url: ${base_url}/api/status
  store_as: device_state
- test.sleep:
  seconds: 5
```

### Conditional (if / then / else)

```
- condition: "current_version != target_version"
then:
- browser.upload:
  selector: "#firmware-input"
  file_path: Firmware/${firmware_file}
- browser.click:
  role: button
  name: Upgrade
else:
- test.log:
  message: "Firmware already at target version — skipping"
```

### Try / Except / Finally

```
- try:
- api.post:
  url: ${base_url}/api/reboot
except:
- test.log:
  message: "Reboot request failed — device may already be rebooting"
finally:
- test.sleep:
  seconds: 30
```

### Inline data loop (test.data)

Run the same step block against multiple data rows within a single Feature: case:

```
- test.data:
rows:
- mac: D4:6A:91:29:0F:5A
  product: WB-800
- mac: A8:3B:76:11:CC:22
  product: WB-250
steps:
- ssh.connect:
  host: ${mac}
  username: admin
  password: ${DEVICE_PASSWORD}
- ssh.command:
  command: cat /etc/firmware_version
  store_as: fw
- test.assert:
  value: ${fw}
  not_empty: true
- ssh.disconnect: {}
```

---

## Shared Steps in TestRail

Create a case titled `Shared: <step_name>` and write the reusable steps in its Preconditions field. Other `Feature:` cases call it by name.

**Defining a shared step (`Shared: authenticate` in TestRail):**

```
steps:
- api.post:
url: ${base_url}/auth/login
body: {username: "${API_USERNAME}", password: "${API_PASSWORD}"}
store_as: auth_response
- test.assert:
value: ${last_status_code}
equals: 200
- test.extract:
from: ${auth_response}
path: access_token
store_as: token
```

**Calling it from a `Feature:` case:**

```
steps:
- shared_step: authenticate
- api.get:
url: ${base_url}/devices
headers: {Authorization: "Bearer ${token}"}
store_as: devices
- test.assert:
value: ${last_status_code}
equals: 200
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
username: ${STAGING_USER}
password: ${STAGING_PASS}

steps:
- browser.open:
url: ${base_url}/login
- browser.fill:
selector: "#username"
value: ${username}
- browser.fill:
selector: "#password"
value: ${password}
- browser.click:
role: button
name: Sign In
- browser.wait_for:
selector: ".dashboard"
- browser.verify_text:
selector: "h1"
text: Dashboard
```

Optional `setup` and `cleanup` sections run before/after `steps` regardless of pass/fail:

```
setup:
- browser.open:
url: ${base_url}

cleanup:
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
- api.post:
  url: ${base_url}/auth/login
  body: {username: "${username}", password: "${password}"}
  store_as: auth_response
- test.extract:
  from: ${auth_response}
  path: access_token
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
| `GET ${url}` | `api.get url: ${url}` |
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
| `telnet \| {"host": "h", "command": "cmd"} \|` | `telnet.command command: cmd` |
| `ssh \| {"host": "h", "command": "cmd"} \|` | `ssh.command command: cmd` |
| `webservice \| $url \| GET \| /path \| {} \|` | `api.get url: ${url}/path` |
| `webservice \| $url \| SEND \| method \| {...} \|` | `websocket.send data: {...}` |
| `function \| {"name": "assert", ...} \|` | `test.assert value: ...` |
| `\| value \| in response` | `test.assert value: ${last_response} contains: value` |
| `response_code \| 200 \|` | `test.assert value: ${last_status_code} equals: 200` |
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
│   │   ├── testrail_reporter.py   # Datalake + Teams webhook reporting
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
│   ├── test_builder_app.py        # [DEPRECATED] local web builder
│   └── action_definitions.py      # [DEPRECATED] web builder action catalog
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

Use `retry` and `retry_delay` on `ssh.connect` to wait for the device to come back:

```
- ssh.connect:
host: ${device_ip}
username: ${device_user}
password: ${device_pass}
retry: 5
retry_delay: 15
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
