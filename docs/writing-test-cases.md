# Writing Test Cases — Quick Reference

A practical guide for authoring Easy BDD test cases in TestRail. Covers naming conventions, browser and API steps, variable setup, and common pitfalls.

---

## Table of Contents

1. [Case Naming — Prefix Taxonomy](#1-case-naming--prefix-taxonomy)
2. [Var: Cases — Shared Variables](#2-var-cases--shared-variables)
3. [Preconditions Field Format](#3-preconditions-field-format)
4. [Browser (UI) Tests](#4-browser-ui-tests)
5. [API Tests with Bearer Tokens](#5-api-tests-with-bearer-tokens)
6. [Assertions](#6-assertions)
7. [Logging and Debugging Steps](#7-logging-and-debugging-steps)
8. [Common Pitfalls and Fixes](#8-common-pitfalls-and-fixes)
9. [Variables — Resolution Order](#9-variables--resolution-order)
10. [Selector Strategies (Browser)](#10-selector-strategies-browser)

---

## 1. Case Naming — Prefix Taxonomy

Every case title **must** start with a recognised prefix. The prefix tells the runner what to do with the case.

| Prefix | Purpose |
|--------|---------|
| `Var: Name` | Key/value variables injected into every other case in the run |
| `Feature: Name` | Steps written directly in the Preconditions field |
| `Test: Name` | Points to a local YAML file or tag |
| `Shared: Name` | Reusable step block referenced by other cases |
| `Setup: Name` | Runs before all Feature/Test cases |
| `Teardown: Name` | Runs after all Feature/Test cases |

**Example run layout:**
```
Var: Araknis AP
Feature: api.post - Get Bearer Token
Feature: api.get - Firmware Partition Versions
Feature: Browser - Login Flow
Feature: Browser - Navigation Smoke Test
```

---

## 2. Var: Cases — Shared Variables

Put shared variables in a `Var:` case so every other case in the run can reference them.  
Write one `key: value` pair per line in the Preconditions field — no special formatting needed.

```
base_url: http://192.168.100.3/cgi-bin/luci
username: araknis
password: SnapAV704
api_url: http://192.168.30.117:8001/api
api_username: araknis
api_password: SnapAV704!
product: AN-810-AP-I-AC
expected_firmware: 2.2.00
ping_target: 192.168.100.1
```

**Rules:**
- The `Var:` case must be **included in the run** (status Untested or Retest) — excluded cases are not read.
- Variables are available in all Feature cases as `${variable_name}`.
- If a URL value contains `://`, the parser still handles it correctly.

**Special control variables:**

| Variable | Effect |
|----------|--------|
| `no_datalake: True` | Skip posting results to the data lake |
| `retry: 0` | Disable automatic retries for this run |

---

## 3. Preconditions Field Format

Steps are written in the Preconditions field using a **flush-left** format. The runner automatically re-indents parameters — you do not need to manually align them.

### Correct format (flush-left params)

```
steps:
# 1. Open browser
- browser.open:
url: ${base_url}
# 2. Fill username
- browser.fill:
selector: input[type="text"]
value: ${username}
```

### What NOT to do (over-indented params — will break parsing)

```
steps:
- browser.open:
    url: ${base_url}    ← do NOT indent under the action
```

### Step numbering

Add `# N. description` comment lines before each step. They appear in TestRail as human-readable labels and are ignored by the parser.

```
# 1. Open browser
- browser.open:
url: ${base_url}
# 2. Login
- browser.fill:
selector: input[type="text"]
value: ${username}
```

---

## 4. Browser (UI) Tests

### Available browser actions

| Action | Required params | Optional params |
|--------|----------------|-----------------|
| `browser.open` | `url` | — |
| `browser.fill` | `value` + one of: `selector`, `label`, `role`+`name` | — |
| `browser.click` | one of: `selector`, `role`+`name`, `label`, `text` | `exact` |
| `browser.wait_for` | — | `selector`, `timeout`, `state` |
| `browser.verify_text` | `text` | — |
| `browser.screenshot` | `filename` | — |
| `browser.hover` | `selector` | — |
| `browser.select` | `selector` | `value`, `label`, `index` |
| `browser.press_key` | `key` | `selector` |

### Login flow example

```
# 1. Open browser
- browser.open:
url: ${base_url}
# 2. Fill username (use selector when no <label> element exists)
- browser.fill:
selector: input[type="text"]
value: ${username}
# 3. Fill password
- browser.fill:
selector: input[type="password"]
value: ${password}
# 4. Submit
- browser.click:
role: button
name: Log In
# 5. Confirm dashboard loaded
- browser.wait_for:
selector: "text=SYSTEM STATUS"
```

### Clicking elements

**By role and name (preferred when aria labels exist):**
```
- browser.click:
role: button
name: Save
```

**By CSS selector (when role is ambiguous or element has no label):**
```
- browser.click:
selector: "#fun_1_0"
```
> ⚠️ Always wrap selectors containing `#` in double quotes — YAML treats `#` as a comment character without quotes.

**Exact match (when multiple elements share the same name):**
```
- browser.click:
role: link
name: System
exact: true
```

**Strict mode violation (two elements match):**  
If Playwright reports `strict mode violation: resolved to 2 elements`, either add `exact: true` or switch to a `selector:` with the element's unique ID.

### Filling fields

| Scenario | Use |
|----------|-----|
| Form has `<label>` elements | `label: Username` |
| Form has no labels (e.g. bare `<input>`) | `selector: input[type="text"]` |
| Input identified by role | `role: textbox`, `name: Search` |

### Waiting for elements

```
- browser.wait_for:
selector: "text=SYSTEM STATUS"
```
```
- browser.wait_for:
selector: "#devices__tab"
```
```
- browser.wait_for:
selector: "role=button[name='Log In']"
```

### Test variables for browser behaviour

Add these to your `Var:` case or test variables to control the browser:

| Variable | Example | Effect |
|----------|---------|--------|
| `headless` | `False` | Show the browser window (headed mode) |
| `slow_mo` | `1000` | Add 1000ms delay between each action (ms) |
| `retry` | `0` | Disable step retries |

---

## 5. API Tests with Bearer Tokens

### store_as response structure

`store_as` wraps the HTTP response in a dict with these keys:

| Key | Contents |
|-----|---------|
| `status` | HTTP status code (integer) |
| `data` | Parsed JSON body (dict/list), or raw text if not JSON |
| `body` | Raw response text (string) |
| `headers` | Response headers dict |
| `response_time` | Elapsed time in milliseconds |

The JSON body lives under `.data`. Use dot-notation to navigate it directly in both expressions and `${...}` substitutions.

### Step 1 — Login and get token

```
# 1. POST login
- api.request:
method: POST
url: ${api_url}/system/login
body: {'user': '${api_username}', 'password': '${api_password}'}
store_as: login_response
# 2. Verify login succeeded
- test.assert:
expression: login_response.data.restful_res.errCode == 0
message: Login should return errCode 0
```

### Step 2 — Use token in subsequent requests

```
# 3. GET endpoint with bearer token
- api.request:
method: GET
url: ${api_url}/system/firmware
headers: {'Authorization': 'Bearer ${login_response.data.restful_res.token}'}
store_as: firmware_response
# 4. Check key is present in response
- test.assert:
expression: "'partition1Version' in firmware_response.data.restful_res.fwConfs"
message: Firmware response should contain partition1Version
```

### Token response structure mapping (device config `token_field`)

| Device response shape | `token_field` value | In-step dot path |
|----------------------|--------------------|--------------------|
| `{"token": "..."}` | `token` | `login_response.data.token` |
| `{"data": {"token": "..."}}` | `data.token` | `login_response.data.data.token` |
| `{"restful_res": {"token": "..."}}` | `restful_res.token` | `login_response.data.restful_res.token` |

The `token_field` in the device config file describes the *device's* JSON structure (no `data` wrapper — that's the framework's). The in-step `${...}` substitution always needs the `data.` prefix.

### Device config file (for reusable auth)

Create `config/devices/my_device.yaml` to avoid repeating login steps in every case:

```yaml
device_info:
  name: "Araknis 810 AP"

network:
  base_url: "http://192.168.30.117:8001"

authentication:
  type: "bearer_token"
  auth_endpoint: "/api/system/login"
  username: "araknis"
  password: "SnapAV704!"
  username_field: "user"
  password_field: "password"
  token_field: "restful_res.token"
  token_expires_field: "restful_res.timeout"
  success_codes: [200]
  verify_ssl: false
```

Then reference it in steps:
```
- api.request:
method: GET
url: http://192.168.30.117:8001/api/system/firmware
device: my_device
store_as: firmware_response
```

---

## 6. Assertions

### test.assert — dot-notation (preferred)

Use dot-notation to navigate nested response data. No quoting needed unless the expression contains single quotes.

```
- test.assert:
expression: login_response.data.restful_res.errCode == 0
message: Login should return errCode 0
```

```
- test.assert:
expression: firmware_response.data.restful_res.fwConfs.partition1Version == 'IMG-1.0.23.01'
message: Firmware version should match expected
```

### test.assert — `in` checks

When checking for a key inside a dict, the `'key' in dict` expression contains single quotes, so wrap the whole expression in double quotes:

```
- test.assert:
expression: "'token' in login_response.data.restful_res"
message: Response should contain a token
```

```
- test.assert:
expression: "'partition1Version' in firmware_response.data.restful_res.fwConfs"
message: Firmware response should contain partition1Version
```

### Expression quoting rule

| Expression type | Quoting needed | Example |
|----------------|---------------|---------|
| Comparison with numbers or booleans | None | `expression: response.data.errCode == 0` |
| Comparison with string literal | None (if no special chars) | `expression: response.data.status == OK` |
| `in` check (contains single quotes) | Wrap in double quotes | `expression: "'key' in response.data.items"` |
| Contains `[`, `]`, `{`, `}` | Wrap in double quotes | `expression: "response.data.get('key', {}) == {}"` |

**Bottom line:** prefer dot-notation to avoid special characters entirely. Only reach for `.get()` when you need a fallback default if a key might be absent.

### browser.verify_text — check text appears on page

```
- browser.verify_text:
text: AN-810-AP-I-AC
```

```
- browser.verify_text:
text: ${product}
```

---

## 7. Logging and Debugging Steps

### test.log — print a message in the output

```
- test.log:
message: "Starting firmware verification"
```

Use it to label sections of a long test without affecting execution.

### browser.screenshot — capture the current page state

```
- browser.screenshot:
filename: before_click_debug
```

Screenshots are saved to `reports/` and attached to the TestRail result automatically.

### Debugging a failing step

1. Add `headless: False` and `slow_mo: 1000` to the Var case — watch the browser live.
2. Add `browser.screenshot` before the failing step to see what the page looked like.
3. Check that the element isn't covered by a modal or banner.
4. If Playwright says "strict mode violation", the selector matched multiple elements — use `exact: true` or switch to a unique `selector: "#element-id"`.

---

## 8. Common Pitfalls and Fixes

### SSH/Telnet — `command:` or `prompt:` shows as `null` at runtime

**Symptom:** `SSH command requires 'command' — got None` or the step fails with `step returned False` and params show `command: None`.  
**Cause:** A YAML value that contains `#`, or a key with no value, becomes `null`.

The parser now warns about null parameters when it loads the file — look for `UserWarning: Step '...': parameter(s) [...] are null/None` in the output before the run starts.

```yaml
# WRONG — '#' after a space is a YAML comment; prompt becomes null
- ssh.command:
    prompt: AN-210-SW-16-POE#

# WRONG — standalone '#' value is entirely a comment; prompt becomes null
- ssh.command:
    prompt: #

# WRONG — empty key; command becomes null
- ssh.command:
    command:

# CORRECT — quote any value that contains or starts with a special character
- ssh.command:
    prompt: 'AN-210-SW-16-POE#'
    command: '?Model'
```

Characters that must be quoted when they appear in a value: `#` (preceded by space), `?` `!` `*` `&` `|` at the start of a value.

---

### YAML breaks on expressions with single quotes

**Symptom:** `Could not parse Preconditions as YAML: expected <block end>`  
**Cause:** An expression containing `'key' in ...` has unbalanced quotes when YAML reads the line.  
**Fix:** Wrap the entire expression in double quotes.

```
# Wrong
expression: 'token' in login_response.data.restful_res

# Correct
expression: "'token' in login_response.data.restful_res"
```

### Selector with `#` is ignored

**Symptom:** `waiting for locator("fun_1_0")` (the `#` was stripped)  
**Fix:** Quote the selector value.

```
# Wrong
selector: #fun_1_0

# Correct
selector: "#fun_1_0"
```

### Variables not resolving (`${base_url}` stays literal)

**Causes:**
- Var case not included in the run — add it and set status to Untested.
- Steps have over-indented params — use flush-left format.
- Variable defined in one Var case but used in a different suite's run.

### `fill_element` / unknown action errors

**Symptom:** `BrowserService has no attribute 'fill_element'`  
**Fix:** Use `browser.fill` with `selector:`, `label:`, or `role:`+`name:`. Do not use `fill_element` directly.

### `headless: False` has no effect

**Symptom:** Browser still launches headless.  
**Fix:** The value must be a boolean, not a string. Write `headless: False` (capital F, no quotes). Strings `"false"` and `"False"` are coerced automatically, but the boolean form is clearest.

### Login lock-out from too many failed attempts

**Symptom:** Device locks after running the test suite.  
**Cause:** Each test case tried to log in but `label: Username` failed silently (no `<label>` elements), submitting empty credentials.  
**Fix:** Use `selector: input[type="text"]` and `selector: input[type="password"]` for forms without label elements. Add `retry: 0` to the Var case to prevent retries on login steps.

### Strict mode violation — two elements match

**Symptom:** `get_by_role("link", name="System") resolved to 2 elements`  
**Fix:**
```
# Add exact: true to require exact text match
- browser.click:
role: link
name: System
exact: true

# Or use the element's unique ID
- browser.click:
selector: "#fun_1_0"
```

### Nested body/headers dict causes YAML parse error

**Symptom:** `mapping values are not allowed here` pointing at a param like `store_as:`  
**Cause:** A `body:` or `headers:` param with indented children breaks the flush-left re-indentation scheme.

```
# Wrong — indented children confuse the parser
body:
  user: ${api_username}
  password: ${api_password}
store_as: login_response

# Correct — use inline flow-style dict
body: {'user': '${api_username}', 'password': '${api_password}'}
store_as: login_response
```

Same applies to `headers:` with multiple values:
```
headers: {'Authorization': 'Bearer ${login_response.data.restful_res.token}'}
```

### YAML parse error in long navigation tests

**Symptom:** `expected <block end>, but found '<block sequence start>'`  
**Cause:** A stray leading space before a `- ` step line, usually introduced by manual editing.  
**Fix:** Ensure every step's `- action:` starts at column 0 with no leading whitespace.

### API returns 401 immediately

**Causes:**
- Wrong `username_field` / `password_field` names (device expects `user` not `username`).
- Framework auto-auth is retrying with stale credentials — check device config file.
- Token response field path is wrong — verify with `store_as` and `test.log`.

---

## 9. Variables — Resolution Order

When the same variable is defined in multiple places, this priority applies (highest wins):

1. `session_overrides` (CLI flags, runtime overrides)
2. `runtime_data` (values set by `store_as` during execution)
3. `test_variables` (variables from the current test's Preconditions `variables:` block)
4. `test_variables` (also populated from the Var: case at run start)
5. `collection_vars` (injected from TestRail Var: cases)
6. `config_file` (values in `config/framework.yaml`)
7. `framework_defaults`

**Practical takeaway:** Var: case variables can be overridden by a `variables:` block inside a specific Feature case's Preconditions. Use this to specialise one case without changing shared config.

---

## 10. Selector Strategies (Browser)

Choose the most stable selector for each element. From most to least stable:

| Priority | Strategy | Example |
|----------|----------|---------|
| 1 (best) | Role + accessible name | `role: button, name: Save` |
| 2 | Label text | `label: Username` |
| 3 | Unique element ID | `selector: "#devices__tab"` |
| 4 | Input type | `selector: input[type="password"]` |
| 5 | CSS class | `selector: ".submit-btn"` |
| 6 (worst) | XPath | `selector: //button[@id='save']` |

**When to use `selector:` instead of `role:`:**
- The form has no `<label>` elements (use `input[type="text"]`).
- Two elements share the same role and name (use unique `#id`).
- The element has no meaningful accessible name.

**Self-healing:** If a CSS selector fails at runtime, the runner automatically tries `get_by_label`, `get_by_role`, and `get_by_text` fallbacks and logs `[HEALED]` when one succeeds. Update the test to use the healed selector going forward.
