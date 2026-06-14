# TestRail Integration Guide

Run Easy BDD tests directly from TestRail — no local YAML files required for simple tests, full YAML support for complex ones.

---

## Table of Contents

1. [Quick Setup](#quick-setup)
2. [TestRail Author Checklist](#testrail-author-checklist)
3. [Run Configuration](#run-configuration)
4. [Case Prefix Taxonomy](#case-prefix-taxonomy)
5. [Var: Cases — Variable Injection](#var-cases--variable-injection)
6. [Feature: Cases — Writing Steps in TestRail](#feature-cases--writing-steps-in-testrail)
7. [TestRail-Safe Syntax (Recommended)](#testrail-safe-syntax-recommended)
8. [API + Token + Assert Recipes](#api--token--assert-recipes)
9. [Response Variables and Extraction Rules](#response-variables-and-extraction-rules)
10. [TestRail Feature Templates](#testrail-feature-templates)
11. [YAML File Format vs TestRail Feature Format](#yaml-file-format-vs-testrail-feature-format)
12. [Parameterized Tests — Multiple Devices / SKUs](#parameterized-tests--multiple-devices--skus)
13. [Loops and Iteration](#loops-and-iteration)
14. [Fault Insertion and Timed Delays](#fault-insertion-and-timed-delays)
15. [Test: Cases — Pointing to Local YAML](#test-cases--pointing-to-local-yaml)
16. [Setup: and Teardown: Cases](#setup-and-teardown-cases)
17. [Scheduling with Cron](#scheduling-with-cron)
18. [Retry on Failure](#retry-on-failure)
19. [Running from the CLI](#running-from-the-cli)

---

## Quick Setup

1. In TestRail, create a test run with a name starting with `EASY_BDD:`:
   ```
   EASY_BDD: BDD: Wattbox Firmware
   ```

2. Add test cases to the run using the prefix taxonomy below.

3. Run from the CLI:
   ```bash
   python -m easy_bdd testrail-run <project_id>
   # or target a specific run by ID:
   python -m easy_bdd testrail-run <project_id> --run-id <run_id>
   ```

---

## TestRail Author Checklist

Use this checklist before saving any Feature case in TestRail.

- Prefer flow-style YAML in TestRail fields to avoid indentation breakage.
- Keep one step per line starting with `- action.name: {...}`.
- Quote variable substitutions and expressions, for example `"${token}"` and `"'systemInfo' in last_json"`.
- Put `store_as` and `store_response` at step level, not inside `headers` or `body`.
- For JSON extraction, use dot-notation: `last_json.restful_res.token` — bracket access also works but is more verbose.
- For authenticated requests, set header as `Authorization: "Bearer ${token}"`.
- Avoid `Content-Type` on GET requests unless endpoint requires it.
- Ensure keys in assert expressions are quoted, for example `'errCode'`.
- Run one smoke case first (`Feature: Token`) before larger suites.
- If parsing fails, convert multiline nested maps to flow-style objects.

Quick validation snippet:

```yaml
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}}
- eval.run: {expression: "last_json.restful_res.token", store_as: token}
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}"}}
- assert: {expression: "last_status == 200"}
```

---

## Run Configuration

Store a JSON object in the **run description** field to configure scheduling, retries, and shared variables:

```json
{
  "cron": "0 9 * * MON-FRI",
  "retry": 2,
  "data": {
    "base_url": "https://staging.example.com",
    "environment": "staging"
  }
}
```

| Field | Description |
|-------|-------------|
| `cron` | 5-field cron expression — run only fires when matching (±5 min window) |
| `retry` | Number of times to retry failed tests before giving up |
| `data` | Extra key/value variables injected into every test in the run |

---

## Case Prefix Taxonomy

Every case title must begin with one of these prefixes:

| Prefix | Role | Runs when |
|--------|------|-----------|
| `Var: Name` | Variable definitions | Always (variables injected into all tests) |
| `Setup: Name` | Pre-test setup | Before any Test:/Feature: case |
| `Test: Name` | Points to a local YAML file or tag | In order, if status is Untested/Retest |
| `Feature: Name` | Steps written directly in TestRail | In order, if status is Untested/Retest |
| `Teardown: Name` | Post-test cleanup | After all Test:/Feature: cases |
| `Shared: Name` | Shared step definition | Referenced by other cases via `shared_step` |

Example run layout:
```
Var: Environment Config
Var: AWS Credentials
Setup: Connect to Device
Feature: Firmware Manager
Feature: Verify Device Status
Teardown: Disconnect
```

---

## Var: Cases — Variable Injection

Put `key: value` pairs in the **Preconditions** or **Steps** field. These are injected as variables into every test in the run.

```
aws_access_key_id: AKIAIOSFODNN7EXAMPLE
aws_secret_access_key: wJalrXUtnFEMI/K7MDENG
server_url: wss://firmware.testing.ovrc.com:10444
environment: staging
```

Variables from Var: cases are available in all Feature: and Test: cases as `${variable_name}`.

Special control variables recognized by the runner:

| Variable | Effect |
|----------|--------|
| `no_datalake: True` | Skips posting results to the data lake for this run |
| `no_teams: True` | Suppresses the Teams notification after this run completes |
| `async_execution: true` | Runs all data-driven iterations in parallel |
| `max_workers: N` | Maximum parallel workers when `async_execution` is enabled |

---

## Feature: Cases — Writing Steps in TestRail

Write steps directly in the **Preconditions** field. Parameters can be flush-left — the runner re-indents them automatically.

### Format 1 — Dot-notation (preferred, same as local YAML)

```
- aws.list_files:
bucket_name: ${bucket_name}
folder_prefix: vps/
file_extension: .bin
store_as: firmware_files

- ovrc.connect:
auth_type: bearer
server_url: ${server_url}
device_id: ${mac}

- ovrc.get about:
store_as: device_info

- ovrc.disconnect: {}
```

### Format 2 — With a variables block

```yaml
variables:
  base_url: https://staging.example.com
steps:
  - api.request:
      method: GET
      url: ${base_url}/status
      store_as: response
  - test.assert_response:
      status: 200
```

### Format 3 — Flat action: shorthand (single step)

```
action: aws.list_files
bucket_name: jpdsauto-wattbox
folder_prefix: vps/
file_extension: .bin
store_as: firmware_files
```

---

## TestRail-Safe Syntax (Recommended)

TestRail text fields can flatten indentation, merge lines, or replace spaces with non-standard whitespace. To avoid parse issues, prefer **flow-style YAML** in Feature cases.

### Best-practice pattern (flow style)

```yaml
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}}
- eval.run: {expression: "last_json.restful_res.token", store_as: token}
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}", Accept: application/json}}
- assert: {expression: "'systemInfo' in last_json"}
```

### Why this format is safer in TestRail

- No dependency on indentation for nested objects.
- Avoids common parse failures like `expected <block end>`.
- Avoids line merge problems such as `Authorization: Bearer ${token}store_as: last_response`.

### Rules for robust Feature steps

- Quote expressions and interpolated values: `"${var}"`, `"'key' in last_json"`.
- Keep `store_as` and `store_response` as top-level step params, not inside `headers` or `body`.
- For GET requests, do not send `Content-Type` unless the endpoint explicitly requires it.

---

## API + Token + Assert Recipes

### Recipe 1: Login and extract token

```yaml
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}}
- eval.run: {expression: "last_json.restful_res.token", store_as: token}
- assert: {expression: "token is not None and len(token) > 10"}
```

### Recipe 2: Authenticated status call

```yaml
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}", Accept: application/json}}
- assert: {expression: "last_status == 200"}
- assert: {expression: "'systemInfo' in last_json"}
```

### Recipe 3: Validate key/value pairs

```yaml
- assert: {expression: "last_json.restful_res.errCode == 0"}
- assert: {expression: "last_json.restful_res.message == 'OK'"}
- assert: {expression: "'token' in last_json.restful_res"}
```

### Recipe 4: Reuse login via shared step

```yaml
- shared_step: Token
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}"}}
- assert: {expression: "last_status == 200"}
```

---

## Response Variables and Extraction Rules

After each `api.request`, the runner provides these automatic variables:

| Variable | Type | Use |
|----------|------|-----|
| `last_response` | `requests.Response` | Raw response object |
| `last_status` | `int` | HTTP status code |
| `last_json` | `dict \| None` | Parsed JSON body — use dot-notation directly |

When you use `store_as: my_response`, the runner wraps the response in an envelope:

| Key | Contents |
|-----|---------|
| `my_response.status` | HTTP status code |
| `my_response.data` | Parsed JSON body — navigate with dot-notation from here |
| `my_response.body` | Raw response text |
| `my_response.headers` | Response headers dict |
| `my_response.response_time` | Elapsed time (ms) |

### Dot-notation access (preferred)

```yaml
# last_json — JSON is at the top level, no .data needed
- eval.run: {expression: "last_json.restful_res.token", store_as: token}
- assert: {expression: "last_json.restful_res.errCode == 0"}
- assert: {expression: "'systemInfo' in last_json"}

# store_as — JSON is under .data
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}, store_as: login_response}
- assert: {expression: "login_response.data.restful_res.errCode == 0"}
- assert: {expression: "'token' in login_response.data.restful_res"}
```

### Bracket-access also works but is verbose

```yaml
# Also valid, but prefer dot-notation
- assert: {expression: "last_json['restful_res']['errCode'] == 0"}
```

---

## TestRail Feature Templates

Copy/paste these patterns into a Feature case Preconditions field.

### 1) Login and save token

```yaml
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}}
- assert: {expression: "last_status == 200"}
- eval.run: {expression: "last_json.restful_res.token", store_as: token}
```

### 2) Token reuse for authenticated GET

```yaml
- shared_step: Token
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}", Accept: application/json}}
- assert: {expression: "last_status == 200"}
```

### 3) JSON schema validation

```yaml
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}"}}
- test.assert_schema:
    data: last_json
    schema:
      type: object
      required: [restful_res]
      properties:
        restful_res:
          type: object
          required: [errCode, message]
          properties:
            errCode: {type: integer}
            message: {type: string}
```

### 4) List extraction by index (for firmware URLs/files)

```yaml
- aws.list_files: {bucket_name: "${aws_bucket}", folder_prefix: "${folder_prefix}", store_as: last_response}
- eval.run: {expression: "last_response[0]", store_as: first_item}
- eval.run: {expression: "last_response[-1]", store_as: latest_item}
```

Optional version extraction from selected item:

```yaml
- eval.extract_version: {from_var: latest_item, pattern: "(\\d+\\.\\d+[\\.\\d]*)", store_as: firmware_version}
```

### 5) Shared-step call chain

```yaml
- shared_step: Token
- shared_step: Device Precheck
- api.request: {method: GET, url: "${url}/system/info", headers: {Authorization: "Bearer ${token}"}}
- assert: {expression: "'systemInfo' in last_json"}
```

Template notes:

- Keep expressions quoted.
- Use last_json for key/value lookups.
- Prefer flow-style maps in TestRail fields.

---

## YAML File Format vs TestRail Feature Format

Use whichever format fits your workflow. Both run through the same action engine.

### A) Local YAML file (`Test:` case)

```yaml
name: Token and System Status
variables:
  url: http://192.168.30.117:8001/api

steps:
  - api.request:
      method: POST
      url: ${url}/system/login
      body:
        user: ${username}
        password: ${password}

  - eval.run:
      expression: last_json.restful_res.token
      store_as: token

  - api.request:
      method: GET
      url: ${url}/system/status
      headers:
        Authorization: Bearer ${token}

  - assert:
      expression: "'systemInfo' in last_json"
```

### B) TestRail Feature (`Feature:` case)

```yaml
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}}
- eval.run: {expression: "last_json.restful_res.token", store_as: token}
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}"}}
- assert: {expression: "'systemInfo' in last_json"}
```

### Common parse/runtime pitfalls

- Bad indentation under `body:` causes `body: None` and credentials appear as top-level keys.
- Non-breaking spaces in pasted text can break YAML parse.
- Missing newline between fields merges values (for example token + `store_as`).
- In assert expressions, quote dictionary keys (`'systemInfo'`) to avoid `NameError`.

---

## Parameterized Tests — Multiple Devices / SKUs

Run the same test for multiple devices by supplying a data array. The test executes **once per row**, substituting that row's variables into every step.

### JSON prefix format (easiest to type in TestRail)

Put `JSON:` on the first line, the JSON array on the second, then your steps after a blank line:

```
JSON:
[
  {"mac": "D4:6A:91:29:0F:5A", "product": "WB-900CH1U", "bucket_name": "jpdsauto-wattbox", "folder_prefix": "ns/"},
  {"mac": "A1:B2:C3:D4:E5:F6", "product": "WB-800",     "bucket_name": "jpdsauto-wattbox", "folder_prefix": "wb800/"},
  {"mac": "11:22:33:44:55:66", "product": "WB-300",     "bucket_name": "jpdsauto-wattbox", "folder_prefix": "wb300/"}
]

- aws.list_files:
bucket_name: ${bucket_name}
folder_prefix: ${folder_prefix}
file_extension: .bin
store_as: firmware_files

- ovrc.connect:
auth_type: bearer
server_url: ${server_url}
device_id: ${mac}

- ovrc.get about:
store_as: device_info

- ovrc.disconnect: {}
```

**Output:**
```
=== Data Iteration 1/3 === (WB-900CH1U)
=== Data Iteration 2/3 === (WB-800)
=== Data Iteration 3/3 === (WB-300)
```

### Full YAML format (data: + steps:)

```yaml
data:
  - mac: D4:6A:91:29:0F:5A
    product: WB-900CH1U
    folder_prefix: ns/
  - mac: A1:B2:C3:D4:E5:F6
    product: WB-800
    folder_prefix: wb800/

steps:
  - ovrc.connect:
      device_id: ${mac}
  - ovrc.get about:
      store_as: device_info
  - ovrc.disconnect: {}
```

### Parallel execution (run all devices simultaneously)

Add `async_execution` and `max_workers` to a Var: case:

```
async_execution: true
max_workers: 3
```

All devices will run concurrently with up to 3 threads.

---

## Loops and Iteration

### for_loop — iterate over a fixed list

Use `for_each` with a Python list literal or expression:

```
- for_loop:
for_each: "[1, 124, 373, 475]"
loop_var: fault_delay
loop_steps:
  - wait:
      time: ${fault_delay}
  - fault.insert:
      type: power_cycle
  - ovrc.get about:
      store_as: device_info
  - test.assert:
      expression: device_info.status == "online"
```

**Iteration order:** iteration 1 runs completely (1s delay), then iteration 2 (124s), then 3 (373s), then 4 (475s). Each iteration runs all loop steps before the next begins.

Other useful `for_each` expressions:

```yaml
for_each: "range(5)"                     # 0, 1, 2, 3, 4
for_each: "range(0, 500, 50)"            # 0, 50, 100, ... 450
for_each: "firmware_files"               # iterate over a stored list
for_each: "fault_intervals.split(',')"   # split a Var: string "1,124,373,475"
```

Optional loop parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `loop_var` | Variable name bound to each item | `item` |
| `loop_limit` | Safety cap on iterations | `1000` |
| `break_if` | Python expression — exits the loop early if True | — |
| `continue_if` | Python expression — skips to next iteration if True | — |

### while_loop — repeat until a condition is false

```
- while_loop:
while_condition: retry_count < 10
loop_limit: 10
loop_steps:
  - wait:
      time: 5
  - ovrc.get about:
      store_as: device_info
  - break:
      condition: device_info.status == "online"
```

### Repeat N times (for_loop with range)

```
- for_loop:
for_each: "range(5)"
loop_var: attempt
loop_steps:
  - ovrc.connect:
      device_id: ${mac}
  - ovrc.get about:
      store_as: device_info
  - ovrc.disconnect: {}
```

---

## Fault Insertion and Timed Delays

### sleep / wait

Any action whose name contains `wait` sleeps for `time` seconds:

```
- wait:
time: 30
```

Or with a variable:

```
- wait:
time: ${fault_delay}
```

### Fault insertion at specific intervals (data array)

Use the JSON data prefix to try the same fault at 10s, 20s, and 30s — each runs the full test:

```
JSON:
[{"fault_delay": 10}, {"fault_delay": 20}, {"fault_delay": 30}]

- ovrc.connect:
device_id: ${mac}

- wait:
time: ${fault_delay}

- fault.insert:
type: power_cycle

- ovrc.get about:
store_as: device_info

- test.assert:
expression: device_info.status == "online"

- ovrc.disconnect: {}
```

### Fault insertion at specific non-uniform intervals (for_loop)

```
- ovrc.connect:
device_id: ${mac}

- for_loop:
for_each: "[1, 124, 373, 475]"
loop_var: fault_delay
loop_steps:
  - wait:
      time: ${fault_delay}
  - fault.insert:
      type: power_cycle
  - ovrc.get about:
      store_as: device_info
  - test.assert:
      expression: device_info.status == "online"
      message: Device should recover after fault at ${fault_delay}s

- ovrc.disconnect: {}
```

The difference from the data array approach: here the device connects **once** and faults are inserted in sequence within a single session. With the data array, each row is a completely independent test run (connect → wait → fault → disconnect).

---

## Test: Cases — Pointing to Local YAML

Put one of these in the **Steps** field:

```
tag: firmware          # runs all YAMLs in tests/cases/ with this tag
file: download_wattbox_firmware_files.yaml  # runs a specific file
```

Variables from Var: cases are injected into the YAML test automatically.

---

## Setup: and Teardown: Cases

- **Setup:** cases run before all Test:/Feature: cases, regardless of their status.
- **Teardown:** cases run after all Test:/Feature: cases, regardless of pass/fail.
- Both use the same step formats as Feature: cases.

```
Setup: Connect to OvrC Server

Preconditions:
- ovrc.connect:
auth_type: bearer
server_url: ${server_url}
device_id: ${mac}
```

```
Teardown: Disconnect from OvrC

Preconditions:
- ovrc.disconnect: {}
```

---

## Scheduling with Cron

Set a cron expression in the run description to make the run fire only during a specific window. The runner checks whether the current time falls within ±5 minutes of a scheduled firing time; if not, all tests are marked Blocked and skipped.

**Run description:**
```json
{"cron": "0 9 * * MON-FRI"}
```

This fires at 9:00 AM, Monday through Friday.

### Cron expression format

```
┌──────── minute  (0-59)
│  ┌───── hour    (0-23)
│  │  ┌── day     (1-31)
│  │  │  ┌─ month (1-12)
│  │  │  │  ┌ weekday (0-7, MON-SUN)
│  │  │  │  │
0  9  *  *  MON-FRI
```

### Common schedules

| Expression | Meaning |
|------------|---------|
| `0 9 * * MON-FRI` | 9:00 AM weekdays |
| `0 */4 * * *` | Every 4 hours |
| `30 6 * * *` | 6:30 AM daily |
| `0 9,17 * * MON-FRI` | 9 AM and 5 PM on weekdays |
| `0 2 * * SUN` | 2:00 AM every Sunday |
| `*/15 * * * *` | Every 15 minutes |

### Automating the trigger

Run this from a cron job on your CI/CD server or any machine:

```bash
# /etc/cron.d/easy_bdd  (Linux)
0 9 * * MON-FRI cd /path/to/easy_bdd && python -m easy_bdd testrail-run 77

# Windows Task Scheduler command:
python -m easy_bdd testrail-run 77
```

The TestRail run description's `cron` field is the source of truth — the machine just calls the command, and Easy BDD decides whether it's the right time to run.

---

## Retry on Failure

Set `retry` in the run description to automatically re-run failed tests:

```json
{"retry": 2}
```

After each pass through the run, failed tests are marked **Retest** and re-executed up to `retry` times. The final result reflects the last execution.

Combine with cron:

```json
{"cron": "0 9 * * MON-FRI", "retry": 1}
```

---

## Running from the CLI

```bash
# Scan a project for the next EASY_BDD: run with pending tests
python -m easy_bdd testrail-run 77

# Target a specific run by ID
python -m easy_bdd testrail-run 77 --run-id 194436

# List all EASY_BDD: runs in a project
python -m easy_bdd testrail-list 77
```

Required environment variables (or `.env` file):

```bash
TESTRAIL_URL=https://yourcompany.testrail.io
TESTRAIL_EMAIL=user@example.com
TESTRAIL_API_KEY=your_api_key_here
```

---

## Creating Test Runs from the CLI

The `testrail-create-run` command creates one or more TestRail test runs from the command line. Use it from CI/CD pipelines, GitHub Actions, or Jenkinsfiles to create runs automatically on push or firmware detection.

```bash
python -m easy_bdd testrail-create-run <project_id> <suite_id> [options]
```

### Arguments

| Argument / Flag | Description |
|----------------|-------------|
| `project_id` | TestRail project ID |
| `suite_id` | TestRail suite ID |
| `--name` | Run name (required for single run mode) |
| `--sections` | One or more section labels to include (substring match; descendants auto-included) |
| `--given-section` | Section label to search for `Given:` cases — enables per-SKU mode |
| `--prefix` | Prefix prepended to every run name (default: `"EASY_BDD:"`) |
| `--description` | Run description text |
| `--milestone-id` | Optional TestRail milestone ID |
| `--dry-run` | Print what would be created without actually creating anything |

### Single run mode

Creates one run containing all cases from the specified sections.

```bash
python -m easy_bdd testrail-create-run 59 106662 \
  --name "EASY_BDD: Regression Smoke Test" \
  --sections "Functions" "Firmware Resiliency" "VPS API" \
  --description "Triggered by commit abc1234"
```

### Per-SKU mode (`--given-section`)

Searches the given section for cases whose titles start with `Given:`. Creates one run per `Given:` case found. The `Given:` prefix is stripped to produce the SKU name; the run is titled `EASY_BDD: {sku} Smoke Test`.

This is useful when multiple device SKUs share the same test sections but each needs its own TestRail run.

```bash
python -m easy_bdd testrail-create-run 77 52630 \
  --given-section "VPS" \
  --sections "Functions" "Firmware Resiliency" "VPS Web UI" "VPS API"
```

If the "VPS" section contains cases titled `Given: WB-300`, `Given: WB-800`, and `Given: WB-900CH1U`, this creates three runs:

```
EASY_BDD: WB-300 Smoke Test
EASY_BDD: WB-800 Smoke Test
EASY_BDD: WB-900CH1U Smoke Test
```

### Dry run (preview without creating)

```bash
python -m easy_bdd testrail-create-run 77 52630 \
  --given-section "VPS" \
  --sections "Functions" "Firmware Resiliency" \
  --dry-run
```

Always use `--dry-run` first when adding a new suite or section configuration to verify the run layout before committing.

---

## HTML Reports Attached to TestRail Results

After each test completes, the HTML report is automatically uploaded to the TestRail result as an attachment via the `add_attachment_to_result` API. The report is then accessible directly from the TestRail result view — no need to dig through Jenkins artifacts.

Report filenames follow the pattern:

```
{RunTitle}_build{BUILD_NUMBER}_{CaseTitle}_report_{timestamp}.html
```

Example:
```
EASY_BDD__WattBox_VPS_Smoke_Test_build47_VPS_FW_Upgrade_report_20260613_143022.html
```

Notes:
- Special characters in the name are replaced with underscores.
- Name is capped at 80 characters.
- When running standalone (no TestRail), the name falls back to the YAML file stem.
- If the attachment upload fails (for example, due to API permissions), a warning is printed but the test result is not affected.

---

## Teams Notifications

After each TestRail run completes, Easy BDD posts an Adaptive Card to Microsoft Teams summarizing the results.

### What the card shows

- Status emoji (pass / fail)
- Passed, Failed, and Skipped counts
- Total duration
- Two action buttons: **View TestRail Run** and **View Jenkins Log** (populated from the `BUILD_URL` environment variable)

### Setup

Add the webhook URL to your `.env` file:

```bash
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
```

The notification fires only when `(passed + failed) > 0`. Runs where all tests were skipped or blocked do not trigger a notification.

### Suppressing notifications for a specific run

Add a `Var:` case to the run with:

```
no_teams: True
```

This is useful for development runs, dry runs, or any run where you do not want channel noise.
