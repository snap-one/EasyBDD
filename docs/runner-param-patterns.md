# Runner Parameter Patterns — Lessons Learned

This document captures parameter name alignment lessons from debugging sessions.
It is a reference for both **test case authors** (what to write in YAML) and
**framework developers** (what the runner must accept).

---

## Overview

The Easy BDD runner maps dot-notation action names (`api.request`, `ovrc connect`,
etc.) to internal Python handlers. A recurring class of bug is a mismatch between
the parameter name documented for test authors and the name the handler actually
reads with `params.get(...)`. The fixes below establish the canonical names and,
where backward-compatibility matters, the fallback aliases.

---

## Parameter Name Quick Reference

| Action | Canonical param | Alias (also accepted) | Notes |
|---|---|---|---|
| `api.request` | `store_as` | `store_response` | Store response body into a variable |
| `ovrc connect` | `url` | `server_url` | OvrC server address |
| `command.python` | `script` | `code` | Python source to execute |
| `test.assert` | `expression` | — | Must be a **quoted string** in YAML |
| `aws.list_files` | `folder_prefix` | — | Use `discover_prefix: true` for dynamic prefix |
| `no_datalake` variable | in `variables:` block | CLI `--no-datalake` | Disables datalake posting for a test |

---

## Detailed Fix Notes

### 1. `api.request` — `store_as` param

**Bug:** The runner called `params.get("store_response")` only. The documented
param name (and the name all test authors used) is `store_as`.

**Fix:** Runner now checks `store_response` first and falls back to `store_as`,
so both work.

**Canonical usage in YAML:**
```yaml
- action: api.request
  method: GET
  url: ${api_base}/status
  store_as: api_response
```

**Lesson:** `store_as` is the universal param name for storing any action result
into a test variable. Prefer it over action-specific aliases.

---

### 2. `aws.list_files` — empty result is not a failure

**Bug:** The handler returned `len(urls) > 0`, which returned `False` (step
failure) when zero files matched the prefix — even though "no files yet" is a
valid, expected state during polling.

**Fix:** Handler always returns `True` and stores an empty list `[]` when no
files match. The caller is responsible for asserting list length if needed.

**Canonical usage:**
```yaml
- action: aws.list_files
  bucket_name: my-bucket
  folder_prefix: exports/
  store_as: found_files

- action: test.assert
  expression: "len(found_files) > 0"
  message: "Expected at least one exported file"
```

**Lesson:** Action handlers should return `True` for "ran successfully, found
nothing" and let a separate `test.assert` enforce expectations about the result.

---

### 3. `ovrc connect` — `url` param

**Bug:** Handler used `params.get("server_url")` but the documented name is `url`.

**Fix:** Runner checks `url` first, falls back to `server_url`.

**Canonical usage in YAML:**
```yaml
- action: ovrc connect
  url: ${ovrc_server}
```

**Lesson:** Always use `url:` (not `server_url:`) for the OvrC connect action.

---

### 4. `command.python` — `script` param

**Bug:** Handler used `params.get("code")` but the documented name is `script`.

**Fix:** Runner checks `script` first, falls back to `code`.

**Canonical usage in YAML:**
```yaml
- action: command.python
  script: |
    result = some_var * 2
    variables['doubled'] = result
```

**Lesson:** Always use `script:` (not `code:`) for `command.python`.

---

### 5. `ovrc disconnect` routing bug

**Bug:** The routing condition was:

```python
if "connect" in action_lower:
    # connect handler
```

Because `"connect" in "ovrc disconnect"` is `True` in Python, disconnect actions
were silently routed to the connect handler.

**Fix:** Added an explicit exclusion:

```python
if "connect" in action_lower and "disconnect" not in action_lower:
    # connect handler
```

**Lesson:** Substring routing checks must always exclude reverse-matches. Prefer
exact string comparison (`action_lower == "ovrc connect"`) or a dispatch table
over `in` checks whenever action names share substrings.

---

### 6. `test.assert` — expression must be a string

**Bug:** YAML without quotes passes a Python `bool` to the runner:

```yaml
expression: True   # YAML bool — Python bool, not string
```

The runner passes this to `compile()`, which raises:

```
TypeError: compile() arg 1 must be a string, bytes or AST object
```

**Fix:** Always quote `expression` values in YAML.

**Canonical usage:**
```yaml
- action: test.assert
  expression: "True"           # trivial pass

- action: test.assert
  expression: "1 == 1"

- action: test.assert
  expression: "status_code == 200"
```

**Lesson:** YAML bare `True` / `False` / integers become Python native types, not
strings. Any field that the framework passes to `eval()` or `compile()` must be
quoted in YAML.

---

### 7. `test.assert` — method calls are restricted

**Bug:** The expression evaluator blocks method calls for security:

```yaml
expression: "payload.get('status')"  # fails — method call blocked
```

**Fix:** Use subscript (bracket) notation instead:

```yaml
expression: "payload['status'] == 'ok'"
```

**Lesson:** Inside `test.assert` expressions, use `obj[key]` not `obj.method()`.
Attribute access for known safe types (e.g., `len(x)`, comparison operators,
arithmetic) is allowed; `.method()` calls are not.

---

### 8. `no_datalake` variable not honoured

**Bug:** Setting `no_datalake: True` inside a `Var:` case or `variables:` block
had no effect — only the CLI flag `--no-datalake` suppressed datalake posting.
The runner read the CLI flag but never checked test-level variables.

**Fix:** Both `runner.py` and `testrail_runner.py` now check:
1. CLI `--no-datalake` flag
2. `test.variables.get('no_datalake')`
3. The current var-case variables dict

**Canonical usage in YAML:**
```yaml
variables:
  no_datalake: True

steps:
  - ...
```

Or per data row:
```yaml
data:
  - env: staging
    no_datalake: True
```

**Lesson:** `no_datalake: True` anywhere in the variables block (test level or
data row) disables datalake posting for that test run.

---

## When Writing Test Cases — Checklist

Use this checklist before committing a new test case:

- [ ] `api.request` stores results with `store_as:` (not `store_response:`)
- [ ] `ovrc connect` uses `url:` (not `server_url:`)
- [ ] `command.python` uses `script:` (not `code:`)
- [ ] All `test.assert` `expression:` values are **quoted strings** in YAML
- [ ] `test.assert` expressions use `obj['key']` subscript notation, not `.method()` calls
- [ ] "No results" from `aws.list_files` is handled by a follow-up `test.assert` on list length, not assumed to fail the step
- [ ] `no_datalake: True` is set at `variables:` level when the test should not post to datalake
- [ ] Action names with potential substring overlap (connect/disconnect, start/restart) are checked for correct routing in the handler

---

## For Framework Developers

When adding a new handler:

1. **Use exact string comparison** for action routing, not `in` substring checks.
   Prefer a dispatch dict:
   ```python
   ACTION_MAP = {
       "ovrc connect": handle_ovrc_connect,
       "ovrc disconnect": handle_ovrc_disconnect,
   }
   ```

2. **Accept the documented canonical param name first**, then fall back to legacy
   aliases for backward compatibility:
   ```python
   value = params.get("canonical_name") or params.get("legacy_alias")
   ```

3. **Handlers that search or list resources should always return `True`** on
   success (even empty results) and store the result. Let `test.assert` enforce
   non-empty expectations.

4. **Never pass raw YAML values to `compile()` or `eval()` without coercing to
   `str` first.** Add a guard:
   ```python
   expression = str(params.get("expression", ""))
   ```

5. **Document the canonical param name** in the action's docstring and in
   `docs/actions/` so it is the single source of truth.
