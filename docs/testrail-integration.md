# TestRail Integration Guide

Run Easy BDD tests directly from TestRail — no local YAML files required for simple tests, full YAML support for complex ones.

---

## Table of Contents

1. [Quick Setup](#quick-setup)
2. [Run Configuration](#run-configuration)
3. [Case Prefix Taxonomy](#case-prefix-taxonomy)
4. [Var: Cases — Variable Injection](#var-cases--variable-injection)
5. [Inline: Cases — Writing Steps in TestRail](#inline-cases--writing-steps-in-testrail)
6. [Parameterized Tests — Multiple Devices / SKUs](#parameterized-tests--multiple-devices--skus)
7. [Loops and Iteration](#loops-and-iteration)
8. [Fault Insertion and Timed Delays](#fault-insertion-and-timed-delays)
9. [Test: Cases — Pointing to Local YAML](#test-cases--pointing-to-local-yaml)
10. [Setup: and Teardown: Cases](#setup-and-teardown-cases)
11. [Scheduling with Cron](#scheduling-with-cron)
12. [Retry on Failure](#retry-on-failure)
13. [Running from the CLI](#running-from-the-cli)

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
| `Setup: Name` | Pre-test setup | Before any Test:/Inline: case |
| `Test: Name` | Points to a local YAML file or tag | In order, if status is Untested/Retest |
| `Inline: Name` | Steps written directly in TestRail | In order, if status is Untested/Retest |
| `Teardown: Name` | Post-test cleanup | After all Test:/Inline: cases |
| `Keyword: Name` | Shared step definition | Referenced by other cases via `shared_step` |

Example run layout:
```
Var: Environment Config
Var: AWS Credentials
Setup: Connect to Device
Inline: Firmware Manager
Inline: Verify Device Status
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

Variables from Var: cases are available in all Inline: and Test: cases as `${variable_name}`.

---

## Inline: Cases — Writing Steps in TestRail

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

- **Setup:** cases run before all Test:/Inline: cases, regardless of their status.
- **Teardown:** cases run after all Test:/Inline: cases, regardless of pass/fail.
- Both use the same step formats as Inline: cases.

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
