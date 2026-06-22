# Easy BDD Testing Framework

A TestRail-first test automation framework supporting browser automation, REST APIs, WebSockets, serial/telnet connections, AWS S3, and more. Test cases are authored directly in TestRail and executed via the command line — no programming required.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Test Format](#test-format)
- [Variables](#variables)
- [Actions Reference](#actions-reference)
- [Control Flow](#control-flow)
- [Shared Steps](#shared-steps)
- [Connections](#connections)
- [TestRail Integration](#testrail-integration)
- [Migration Tools](#migration-tools)
- [Test Builder UI (deprecated)](#test-builder-ui-deprecated)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [CLI Reference](#cli-reference)
- [Troubleshooting](#troubleshooting)

---

## Installation

```bash
git clone <repository-url>
cd Easy_BDD
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install --upgrade pip
pip install -e .
playwright install chromium
```

Configure credentials via `.env` in the project root:

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

**Run a test from the command line:**

```bash
python -m easy_bdd run tests/cases/my_test.yaml
python -m easy_bdd run tests/cases/my_test.yaml --headed   # visible browser
python -m easy_bdd run tests/cases/ --tags smoke            # by tag
```

---

## Test Format

Every test is a YAML file with the following structure:

```yaml
name: Login and verify dashboard
description: Verifies a user can log in and reach the dashboard
tags: [smoke, browser]

variables:
  base_url: https://staging.example.com
  username: testuser
  password: ${DEVICE_PASSWORD}   # resolved from .env

steps:
  - action: browser.open
    url: ${base_url}/login

  - action: browser.fill
    selector: "#username"
    value: ${username}

  - action: browser.fill
    selector: "#password"
    value: ${password}

  - action: browser.click
    role: button
    name: Sign In

  - action: test.assert
    expression: "'Dashboard' in page_content"
    message: Expected dashboard after login
```

Optional `setup` and `cleanup` sections run before and after steps regardless of pass/fail:

```yaml
setup:
  - action: browser.open
    url: ${base_url}

cleanup:
  - action: browser.screenshot
    name: final-state
```

---

## Variables

Variables are referenced with `${variable_name}` anywhere in step parameters.

### Scope resolution order (highest to lowest priority)

1. Test-level variables (defined in the test file)
2. Suite variables
3. Workspace/collection variables
4. Environment variables (from active environment or `.env`)
5. Framework defaults

### Environment-specific values

```yaml
variables:
  base_url: ${env.BASE_URL}
  api_key: ${env.API_KEY}
```

### Runtime variable capture

Store a value from one step and use it in later steps:

```yaml
- action: api.request
  method: GET
  url: ${base_url}/api/version
  store_as: version_response

- action: test.assert
  expression: "'2.' in version_response"
```

---

## Actions Reference

All actions use `service.verb` dot notation.

### Browser

| Action | Key Parameters |
|---|---|
| `browser.open` | `url` |
| `browser.navigate` | `url` |
| `browser.fill` | `selector`, `value` |
| `browser.click` | `selector` or `role` + `name` |
| `browser.press_key` | `key`, `selector` |
| `browser.wait` | `seconds` |
| `browser.wait_for_element` | `selector`, `timeout` |
| `browser.wait_for_text` | `text` |
| `browser.get_text` | `selector`, `store_as` |
| `browser.get_title` | `store_as` |
| `browser.assert_text` | `selector`, `text` |
| `browser.assert_checked` | `selector` |
| `browser.assert_not_checked` | `selector` |
| `browser.screenshot` | `name` |
| `browser.upload` | `selector`, `file_path` |
| `browser.select` | `selector`, `value` |
| `browser.hover` | `selector` |
| `browser.scroll` | `selector` |
| `browser.refresh` | — |
| `browser.close` | — |

Use `iframe >> selector` to target elements inside iframes:

```yaml
- action: browser.upload
  selector: "iframe >> #firmware-input"
  file_path: Firmware/update.bin
```

Role-based selectors (preferred over CSS where possible):

```yaml
- action: browser.click
  role: button
  name: Apply
```

### API

```yaml
- action: api.request
  method: POST
  url: ${base_url}/api/v1/login
  body: '{"username": "${username}", "password": "${password}"}'
  headers:
    Content-Type: application/json
  store_as: login_response

- action: test.assert
  expression: "last_response_code == 200"

- action: test.assert
  expression: "'token' in last_response_dict"
```

### WebSocket

```yaml
- action: websocket.send
  url: ${ws_url}
  data: '{"deviceId": "${mac}", "version": 0}'
  store_as: last_response

- action: test.assert
  expression: "'error' not in last_response"
```

### Telnet

```yaml
- action: telnet.send
  host: ${device_ip}
  port: 23
  command: "?Firmware"
  store_as: telnet_response
```

### SSH

```yaml
- action: command.ssh
  host: ${device_ip}
  username: ${ssh_user}
  password: ${ssh_password}
  command: "cat /etc/firmware"
  store_as: ssh_output
```

### Serial

```yaml
- action: serial.send
  port: COM3
  baudrate: 115200
  data: "?status\r\n"
  store_as: serial_response
```

### Assertions

```yaml
# String contains
- action: test.assert
  expression: "'OK' in last_response"

# HTTP status
- action: test.assert
  expression: "last_response_code == 200"

# JSON field access
- action: test.assert
  expression: "last_response_dict['status'] == 'active'"

# Regex match
- action: test.assert
  expression: "re.match(r'\\d+\\.\\d+\\.\\d+', firmware_version) is not None"

# Soft assert — continues on failure, reports at end
- action: test.assert
  expression: "'warning' not in last_response"
  soft: true
```

### Eval

Execute arbitrary Python expressions in the test context:

```yaml
- action: eval.exec
  code: "token = last_response_dict['data']['token']"

- action: eval.run
  expression: "last_response_dict.get('firmware_version', '')"
  store_as: firmware_version
```

### AWS S3

```yaml
- action: aws.s3.get_latest
  bucket_name: my-firmware-bucket
  folder_prefix: firmware/device/
  file_extension: .bin
  store_filename_as: latest_fw_file
  store_version_as: latest_version

- action: browser.upload
  selector: "#firmware-input"
  file_path: Firmware/${latest_fw_file}
```

### Test utilities

```yaml
# Run another test as a step
- action: test.run
  path: tests/cases/shared/login.yaml

# Log a message to the report
- action: test.log
  message: "Starting firmware upgrade sequence"
```

---

## Control Flow

### For each (loop over a list)

```yaml
- for_each: [1, 10, 30, 60]
  loop_var: wait_seconds
  steps:
    - action: browser.wait
      seconds: ${wait_seconds}
    - action: test.assert
      expression: "'online' in last_response"
```

Loop over a list of dicts:

```yaml
- for_each:
    - {username: admin, role: administrator}
    - {username: viewer, role: read-only}
  loop_var: user
  steps:
    - action: api.request
      method: GET
      url: ${base_url}/api/users/${user.username}
    - action: test.assert
      expression: "last_response_dict['role'] == '${user.role}'"
```

### While loop

```yaml
- while: "device_state != 'ready'"
  loop_limit: 30
  steps:
    - action: api.request
      method: GET
      url: ${base_url}/api/status
      store_as: device_state

    - action: browser.wait
      seconds: 5
```

### Try / Except / Finally

```yaml
- try:
    - action: api.request
      method: POST
      url: ${base_url}/api/reboot
  except:
    - action: test.log
      message: Reboot request failed — device may already be rebooting
  finally:
    - action: browser.wait
      seconds: 30
```

### Conditional (if / then / else)

```yaml
- condition: "current_version != target_version"
  then:
    - action: browser.upload
      selector: "#firmware-input"
      file_path: Firmware/${firmware_file}
    - action: browser.click
      role: button
      name: Upgrade
  else:
    - action: test.log
      message: Firmware already at target version — skipping upgrade

```

---

## Shared Steps

Shared steps are reusable step sequences that can be called by name from any test.

### Scopes

- **Global** — stored in `shared_steps.yaml` at the project root, available to all tests
- **Workspace-local** — stored in `tests/cases/{workspace}/shared_steps.yaml`, overrides global on name collision

### Defining shared steps

`tests/cases/networking/shared_steps.yaml`:

```yaml
authenticate:
  description: Log in and store auth token
  steps:
    - action: api.request
      method: POST
      url: ${base_url}/api/login
      body: '{"username": "${username}", "password": "${password}"}'
    - action: eval.exec
      code: "auth_token = last_response_dict['token']"

verify_connectivity:
  description: Ping device and assert it responds
  steps:
    - action: telnet.send
      host: ${device_ip}
      port: 23
      command: "ping"
    - action: test.assert
      expression: "'pong' in last_response"
```

### Using shared steps

```yaml
steps:
  - shared_step: authenticate

  - action: api.request
    method: GET
    url: ${base_url}/api/settings
    headers:
      Authorization: Bearer ${auth_token}

  - shared_step: verify_connectivity
```

### Managing shared steps in the UI

The Test Builder includes a **Shared Steps** view (sidebar) with:

- Scope filter (global / workspace)
- Create, edit, and delete shared steps
- YAML preview before saving

---

## Connections

For protocols requiring persistent sessions (Telnet, Serial), connections are pooled across steps within a test run. Each `host:port` combination is reused automatically — you do not need to open or close connections explicitly.

---

## TestRail Integration

Easy BDD can discover test runs in TestRail, execute the matching tests, and post results back.

### Configuration

Add to `.env`:

```
TESTRAIL_URL=https://your-instance.testrail.com/
TESTRAIL_USERNAME=automation@example.com
TESTRAIL_API_KEY=your-api-key
```

### Discovering and running TestRail-linked tests

Tests tagged with a TestRail case ID are automatically associated:

```yaml
tags: [C12345]
```

Run all TestRail-linked tests in a run:

```bash
python -m easy_bdd testrail-run --run-id 194434
```

List runs that have Easy BDD tests available:

```bash
python -m easy_bdd testrail-list
```

Results are posted back to TestRail automatically on completion.

---

## Migration Tools

Easy BDD includes migration tools for importing tests from other frameworks. Migrations are available both from the CLI and the Test Builder UI (Import / Migrate button in the Shared Steps view).

### From Robot Framework

Converts `.robot` files to Easy BDD YAML. Keywords become shared steps; test cases become test files.

**Via API / UI:** paste or upload a `.robot` file in the Migration modal, select "Robot Framework", optionally choose a target workspace, and click Convert.

**What gets converted:**

| Robot Framework | Easy BDD |
|---|---|
| `Open Browser ${URL}` | `browser.open url: ${URL}` |
| `Input Text locator value` | `browser.fill selector: locator value: value` |
| `Click Element locator` | `browser.click selector: locator` |
| `Sleep 5s` | `browser.wait seconds: 5` |
| `GET ${url}` | `api.request method: GET url: ${url}` |
| User-defined keywords | `shared_step: keyword_slug` |

### From Previous BDD Framework (mybdd / pytest-bdd)

Converts the pipe-delimited keyword format used in the previous custom framework, including `.feature` files and raw TestRail step blocks.

**What gets converted:**

| mybdd syntax | Easy BDD |
|---|---|
| `browser \| {"command": "open", "param": "url"} \|` | `browser.open url: url` |
| `browser \| {"command": "click_by_role", "role": "button", "name": "Apply"} \|` | `browser.click role: button name: Apply` |
| `browser \| {"command": "validate_checkbox_enabled", "param": "sel"} \|` | `browser.assert_checked selector: sel` |
| `browser \| {"command": "containstext", "param": "b", "text": "..."} \|` | `browser.assert_text selector: b text: ...` |
| `sleep \| 15 \|` | `browser.wait seconds: 15` |
| `telnet \| {"host": "h", "command": "cmd"} \|` | `telnet.send host: h command: cmd` |
| `ssh \| {"host": "h", "command": "cmd"} \|` | `command.ssh host: h command: cmd` |
| `webservice \| $url \| GET \| /api/path \| {} \|` | `api.request method: GET url: ${url}/api/path` |
| `webservice \| $url \| SEND \| dxGetAbout \| {...} \|` | `websocket.send url: ${url} data: {...}` |
| `function \| {"name": "assert", "operator": "match", ...} \|` | `test.assert expression: ...` |
| `function \| {"name": "eval", "string": "..."} \|` | `eval.exec code: ...` |
| `\| value \| in response` | `test.assert expression: 'value' in last_response` |
| `\| path == val \| in json_response` | `test.assert expression: last_response_dict['path'] == val` |
| `response_code \| 200 \|` | `test.assert expression: last_response_code == 200` |
| `Shared: name` | `shared_step: name` |
| `$variable` | `${variable}` |
| `gv.log[-1]['response_txt']` | `${last_response}` |
| `Given:` case body (JSON variables) | `variables:` block |
| `Shared:` case body | entry in `shared_steps.yaml` |
| `Examples:` table (`\| val1 \|`) | `for_each:` loop |

**Migrating a TestRail run directly:**

See `_tr_migrate.py` in the project root for a script that fetches an entire TestRail run via API and writes all tests and shared steps to `tests/cases/tr_{run_id}/`.

---

## Test Builder UI (deprecated)

> **The local web builder is deprecated.** TestRail is now the primary authoring
> surface for all test cases. Create and manage test cases directly in TestRail
> using the case prefix taxonomy (`Feature:`, `Test:`, `Var:`, `Setup:`, `Teardown:`,
> `Shared:`) and dot-notation step syntax. See [TestRail Integration](#testrail-integration).
>
> The files in `frontend/test_builder_app.py` and `frontend/action_definitions.py`
> are kept for reference but are not maintained. The MCP server
> (`frontend/mcp_server.py`) and migration tools (`frontend/bdd_migrator.py`,
> `frontend/robot_migrator.py`) remain active.

---

## Configuration

`config/framework.yaml`:

```yaml
config:
  browser:
    default: chrome
    headless: false
    window_size: [1920, 1080]
    timeout: 30

  api:
    timeout: 30
    verify_ssl: true
    max_retries: 3

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

---

## Project Structure

```
Easy_BDD/
├── easy_bdd/
│   ├── core/
│   │   ├── parser.py          # YAML parser, TestStep dataclass, shared step loading
│   │   └── runner.py          # Test executor, control flow, connection pooling
│   └── services/
│       ├── browser_service.py
│       ├── api_service.py
│       ├── aws_service.py
│       ├── serial_service.py
│       ├── telnet_service.py
│       └── ovrc_api_service.py
├── frontend/
│   ├── test_builder_app.py    # FastAPI backend
│   ├── action_definitions.py  # Action catalog
│   ├── robot_migrator.py      # Robot Framework migration
│   ├── bdd_migrator.py        # Previous BDD framework migration
│   ├── static/
│   │   └── test_builder.html  # Vue.js SPA
│   └── start_builder.py
├── tests/
│   ├── cases/                 # YAML test files, organised by workspace
│   │   └── {workspace}/
│   │       ├── shared_steps.yaml
│   │       └── *.yaml
│   └── data/                  # CSV / JSON test data
├── shared_steps.yaml          # Global shared steps
├── config/
│   └── framework.yaml
├── reports/
├── docs/
└── .env
```

---

## CLI Reference

```bash
# Run a single test
python -m easy_bdd run tests/cases/my_test.yaml

# Run with headed browser
python -m easy_bdd run tests/cases/my_test.yaml --headed

# Run all tests in a folder
python -m easy_bdd run tests/cases/networking/

# Run by tag
python -m easy_bdd run --tags smoke
python -m easy_bdd run --tags browser,api

# Run with a specific environment
python -m easy_bdd run --env staging

# Validate test files (checks syntax and structure)
python -m easy_bdd validate tests/cases/

# List TestRail runs that have matching tests
python -m easy_bdd testrail-list

# Execute tests for a TestRail run and post results
python -m easy_bdd testrail-run --run-id 194434

# Convert a Playwright/Selenium recording
python -m easy_bdd convert recorded_test.json --output tests/cases/converted.yaml

# Docker execution
python -m easy_bdd docker-run tests/cases/my_test.yaml --headless
```

---

## Troubleshooting

**Browser does not open**

```bash
playwright install chromium
python -m easy_bdd run tests/cases/my_test.yaml --headed
```

**Element not found**

Add an explicit wait or use a role-based selector, which is more stable than CSS:

```yaml
- action: browser.wait_for_element
  selector: "#target"
  timeout: 10000

- action: browser.click
  role: button
  name: Submit
```

**Variables not substituting**

Use `${variable_name}` with curly braces. Dollar-sign-only syntax (`$variable`) is not supported in Easy BDD.

**TestRail API errors**

Verify `.env` contains `TESTRAIL_URL`, `TESTRAIL_USERNAME`, and `TESTRAIL_API_KEY`, and that the API key has at least read access to the target project.

**Slow AWS operations**

Connection pooling is enabled by default. If you see repeated connection overhead, ensure you are not creating a new action instance per step — the runner handles this automatically.

**Getting help**

```bash
python -m easy_bdd --help
python -m easy_bdd run --help
```

Full documentation is in the `/docs` folder.
