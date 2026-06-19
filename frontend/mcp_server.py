"""
Easy BDD MCP Server

Exposes Easy BDD capabilities to AI assistants via the Model Context Protocol.

Usage (stdio — for Claude Desktop):
    python frontend/mcp_server.py

Claude Desktop config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "easy-bdd": {
          "command": "python",
          "args": ["C:/path/to/Easy_BDD/frontend/mcp_server.py"]
        }
      }
    }
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from mcp.server.fastmcp import FastMCP

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
FRONTEND  = Path(__file__).parent
TESTS_DIR = ROOT / "tests" / "cases"
GLOBAL_SS = ROOT / "shared_steps.yaml"

sys.path.insert(0, str(FRONTEND))
from action_definitions import ACTION_DEFINITIONS

# ── supplemental actions not in action_definitions.py ─────────────────────────
_EXTRA_ACTIONS: Dict[str, Dict[str, Any]] = {
    "api.request": {
        "category": "API",
        "description": "Make an HTTP request (any method) and store the response.",
        "parameters": {
            "method":   {"required": True,  "type": "select", "options": ["GET","POST","PUT","PATCH","DELETE"], "help": "HTTP method"},
            "url":      {"required": True,  "type": "text",   "help": "Full URL"},
            "headers":  {"required": False, "type": "json",   "help": "Request headers dict"},
            "body":     {"required": False, "type": "textarea","help": "Request body (JSON string or plain text)"},
            "timeout":  {"required": False, "type": "number", "help": "Timeout in seconds"},
            "store_as": {"required": False, "type": "text",   "default": "last_response", "help": "Variable to store response text"},
        },
        "example": textwrap.dedent("""\
            - action: api.request
              method: POST
              url: ${base_url}/api/login
              headers:
                Content-Type: application/json
              body: '{"username": "${username}", "password": "${password}"}'
              store_as: login_response
            - action: test.assert
              expression: "last_response_code == 200"
        """),
    },
    "websocket.send": {
        "category": "API",
        "description": "Send a message over a WebSocket connection and store the response.",
        "parameters": {
            "url":      {"required": True,  "type": "text",    "help": "WebSocket URL (ws:// or wss://)"},
            "data":     {"required": True,  "type": "textarea","help": "Message to send (JSON string or plain text)"},
            "store_as": {"required": False, "type": "text",    "default": "last_response", "help": "Variable to store response"},
            "timeout":  {"required": False, "type": "number",  "help": "Timeout in seconds"},
        },
        "example": textwrap.dedent("""\
            - action: websocket.send
              url: ${ws_url}
              data: '{"deviceId": "${mac}", "version": 0}'
              store_as: ws_response
            - action: test.assert
              expression: "'error' not in ws_response"
        """),
    },
    "telnet.send": {
        "category": "Command",
        "description": "Open a Telnet connection, send a command, and store the response. Connections are pooled per host:port.",
        "parameters": {
            "host":     {"required": True,  "type": "text",   "help": "Hostname or IP"},
            "port":     {"required": False, "type": "number", "default": 23,   "help": "TCP port"},
            "command":  {"required": True,  "type": "text",   "help": "Command to send"},
            "username": {"required": False, "type": "text",   "help": "Login username if prompted"},
            "password": {"required": False, "type": "text",   "help": "Login password if prompted"},
            "timeout":  {"required": False, "type": "number", "default": 10,   "help": "Read timeout in seconds"},
            "store_as": {"required": False, "type": "text",   "default": "last_response", "help": "Variable to store response"},
        },
        "example": textwrap.dedent("""\
            - action: telnet.send
              host: ${device_ip}
              port: 23
              command: "?Firmware"
              store_as: telnet_response
            - action: test.assert
              expression: "'Firmware=' in telnet_response"
        """),
    },
    "serial.send": {
        "category": "Command",
        "description": "Open a serial port, send data, and store the response.",
        "parameters": {
            "port":     {"required": True,  "type": "text",   "help": "Serial port (e.g. COM3 or /dev/ttyUSB0)"},
            "data":     {"required": True,  "type": "text",   "help": "Data to send"},
            "baudrate": {"required": False, "type": "number", "default": 115200, "help": "Baud rate"},
            "timeout":  {"required": False, "type": "number", "default": 5,      "help": "Read timeout in seconds"},
            "store_as": {"required": False, "type": "text",   "default": "last_response", "help": "Variable to store response"},
        },
        "example": textwrap.dedent("""\
            - action: serial.send
              port: COM3
              baudrate: 115200
              data: "?status\\r\\n"
              store_as: serial_response
        """),
    },
    "eval.exec": {
        "category": "Test",
        "description": "Execute a Python statement in the test context. Use to store computed values into variables.",
        "parameters": {
            "code":     {"required": True,  "type": "textarea", "help": "Python code to execute"},
            "store_as": {"required": False, "type": "text",     "help": "Variable name to store the result of the last expression"},
        },
        "example": textwrap.dedent("""\
            - action: eval.exec
              code: "auth_token = last_response_dict['data']['token']"
            - action: api.request
              method: GET
              url: ${base_url}/api/profile
              headers:
                Authorization: "Bearer ${auth_token}"
        """),
    },
    "eval.run": {
        "category": "Test",
        "description": "Evaluate a Python expression and store the result.",
        "parameters": {
            "expression": {"required": True,  "type": "text", "help": "Python expression to evaluate"},
            "store_as":   {"required": True,  "type": "text", "help": "Variable name to store the result"},
        },
        "example": textwrap.dedent("""\
            - action: eval.run
              expression: "last_response_dict.get('firmware_version', '')"
              store_as: firmware_version
            - action: test.assert
              expression: "firmware_version.startswith('2.')"
        """),
    },
    "browser.assert_checked": {
        "category": "Browser",
        "description": "Assert that a checkbox or toggle element is checked/enabled.",
        "parameters": {
            "selector": {"required": True, "type": "text", "help": "CSS selector for the checkbox"},
        },
        "example": textwrap.dedent("""\
            - action: browser.assert_checked
              selector: "div.toggle-layout > label"
        """),
    },
    "browser.assert_not_checked": {
        "category": "Browser",
        "description": "Assert that a checkbox or toggle element is unchecked/disabled.",
        "parameters": {
            "selector": {"required": True, "type": "text", "help": "CSS selector for the checkbox"},
        },
        "example": textwrap.dedent("""\
            - action: browser.assert_not_checked
              selector: "div.toggle-layout > label"
        """),
    },
    "browser.assert_text": {
        "category": "Browser",
        "description": "Assert that an element contains specific text.",
        "parameters": {
            "text":     {"required": True,  "type": "text", "help": "Expected text"},
            "selector": {"required": False, "type": "text", "help": "CSS selector; if omitted checks full page"},
        },
        "example": textwrap.dedent("""\
            - action: browser.assert_text
              selector: "h1.title"
              text: "Dashboard"
        """),
    },
    "browser.get_title": {
        "category": "Browser",
        "description": "Store the current page title in a variable.",
        "parameters": {
            "store_as": {"required": False, "type": "text", "default": "page_title", "help": "Variable to store the title"},
        },
        "example": textwrap.dedent("""\
            - action: browser.get_title
              store_as: page_title
            - action: test.assert
              expression: "'Login' in page_title"
        """),
    },
}

# Merge into a single catalog
_ALL_ACTIONS: Dict[str, Dict[str, Any]] = {**ACTION_DEFINITIONS, **_EXTRA_ACTIONS}

# Control flow docs (not actions, but YAML keys)
_CONTROL_FLOW_DOCS = textwrap.dedent("""\
# Control Flow

Control flow is expressed as special YAML keys rather than action names.

## for_each

Loop over a list. Each value is bound to loop_var.

```yaml
- for_each: [1, 10, 30, 60]
  loop_var: wait_seconds
  steps:
    - action: browser.wait
      seconds: ${wait_seconds}
    - action: test.assert
      expression: "'online' in last_response"
```

Loop over a list of dicts (multi-column Examples table):

```yaml
- for_each:
    - {username: admin, role: administrator}
    - {username: viewer, role: read-only}
  loop_var: user
  steps:
    - action: api.request
      method: GET
      url: ${base_url}/api/users/${user.username}
```

## while

Repeat steps while a condition is true. loop_limit prevents infinite loops (default 1000).

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

## try / except / finally

```yaml
- try:
    - action: api.request
      method: POST
      url: ${base_url}/api/reboot
  except:
    - action: test.log
      message: Reboot failed — device may already be rebooting
  finally:
    - action: browser.wait
      seconds: 30
```

## condition (if / then / else)

```yaml
- condition: "current_version != target_version"
  then:
    - action: browser.click
      role: button
      name: Upgrade
  else:
    - action: test.log
      message: Already on target version
```

## break_if / continue_if

Use inside a for_each or while loop:

```yaml
- for_each: [1, 2, 3, 4, 5]
  loop_var: attempt
  steps:
    - action: api.request
      method: GET
      url: ${base_url}/api/status
      store_as: status
    - break_if: "'ready' in status"
    - action: browser.wait
      seconds: 10
```
""")


# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="easy-bdd",
    instructions=textwrap.dedent("""\
        You are an assistant for the Easy BDD test automation framework.

        Easy BDD uses YAML files to define tests. Each test has:
        - name, description, tags
        - variables (key: value pairs, referenced as ${name})
        - steps (list of action dicts)
        - optional shared_step references

        Use the available tools to:
        - Browse and understand available actions (list_actions, get_action)
        - Create new test files (create_test)
        - Read existing tests (read_test, list_tests)
        - Manage shared steps (list_shared_steps)
        - Run tests (run_test)
        - Validate YAML before saving (validate_yaml)

        Always check required parameters for each action before generating YAML.
        Use ${variable_name} syntax for all variable references.
    """),
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _action_summary(name: str, defn: Dict) -> Dict:
    params = defn.get("parameters", {})
    return {
        "action":      name,
        "category":    defn.get("category", ""),
        "description": defn.get("description", defn.get("label", "")),
        "required":    [k for k, v in params.items() if v.get("required")],
        "optional":    [k for k, v in params.items() if not v.get("required")],
    }


def _load_yaml_file(path: Path) -> Optional[Dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _load_shared_steps_file(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _safe_name(value: str) -> bool:
    # Reject .. segments explicitly before the allowlist check
    if ".." in Path(value).parts:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_\-/\.]+", value))


def _resolve_under(base: Path, rel: str) -> Optional[Path]:
    """Resolve rel under base and verify it stays within base. Returns None on escape."""
    try:
        resolved = (base / rel).resolve()
        resolved.relative_to(base.resolve())  # raises ValueError if outside
        return resolved
    except (ValueError, Exception):
        return None


def _list_workspaces_raw() -> List[str]:
    if not TESTS_DIR.exists():
        return []
    return sorted(
        d.name for d in TESTS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


# ── tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_actions(category: Optional[str] = None) -> str:
    """
    List all available Easy BDD actions, optionally filtered by category.

    Categories: Browser, API, AWS, Command, JSON-RPC, OvrC API, PagerDuty, Test

    Returns action names with required and optional parameter names.
    """
    results = []
    for name, defn in sorted(_ALL_ACTIONS.items()):
        if category and defn.get("category", "").lower() != category.lower():
            continue
        results.append(_action_summary(name, defn))

    categories = sorted(set(d.get("category", "") for d in _ALL_ACTIONS.values()))
    return json.dumps({
        "actions":    results,
        "total":      len(results),
        "categories": categories,
    }, indent=2)


@mcp.tool()
def get_action(action_name: str) -> str:
    """
    Get full details for a specific action including all parameters, types,
    descriptions, defaults, and a usage example.

    Use this before generating YAML for a step to ensure all required fields
    are included and parameters are correctly typed.
    """
    defn = _ALL_ACTIONS.get(action_name)
    if not defn:
        # fuzzy match
        matches = [k for k in _ALL_ACTIONS if action_name.lower() in k.lower()]
        return json.dumps({
            "error":   f"Action '{action_name}' not found.",
            "similar": matches[:8],
        }, indent=2)

    params = defn.get("parameters", {})
    param_details = {}
    for k, v in params.items():
        param_details[k] = {
            "required":    v.get("required", False),
            "type":        v.get("type", "text"),
            "description": v.get("help", v.get("label", "")),
            "default":     v.get("default"),
            "options":     v.get("options"),
        }
        if param_details[k]["default"] is None:
            del param_details[k]["default"]
        if param_details[k]["options"] is None:
            del param_details[k]["options"]

    result = {
        "action":      action_name,
        "category":    defn.get("category", ""),
        "description": defn.get("description", defn.get("label", "")),
        "parameters":  param_details,
    }

    example = defn.get("example")
    if example:
        result["example"] = example

    return json.dumps(result, indent=2)


@mcp.tool()
def list_workspaces() -> str:
    """
    List all test workspaces (subdirectories of tests/cases/).
    Each workspace is a folder that groups related tests.
    """
    workspaces = _list_workspaces_raw()
    details = []
    for ws in workspaces:
        ws_dir = TESTS_DIR / ws
        test_files = list(ws_dir.glob("*.yaml"))
        test_files = [f for f in test_files if f.name != "shared_steps.yaml"]
        has_shared = (ws_dir / "shared_steps.yaml").exists()
        details.append({
            "workspace":    ws,
            "test_count":   len(test_files),
            "has_shared_steps": has_shared,
        })

    return json.dumps({
        "workspaces": details,
        "total":      len(details),
    }, indent=2)


@mcp.tool()
def list_tests(workspace: Optional[str] = None) -> str:
    """
    List YAML test files, optionally filtered to a specific workspace.
    Returns test name, file path, tags, and description for each file.
    """
    results = []
    search_root = (TESTS_DIR / workspace) if workspace else TESTS_DIR
    if not search_root.exists():
        return json.dumps({"error": f"Workspace '{workspace}' not found.", "available": _list_workspaces_raw()})

    for yaml_file in sorted(search_root.rglob("*.yaml")):
        if yaml_file.name == "shared_steps.yaml":
            continue
        data = _load_yaml_file(yaml_file)
        if not isinstance(data, dict):
            continue
        rel = yaml_file.relative_to(ROOT)
        results.append({
            "path":        str(rel).replace("\\", "/"),
            "name":        data.get("name", yaml_file.stem),
            "description": data.get("description", ""),
            "tags":        data.get("tags", []),
            "step_count":  len(data.get("steps", [])),
            "workspace":   yaml_file.parent.name,
        })

    return json.dumps({"tests": results, "total": len(results)}, indent=2)


@mcp.tool()
def read_test(path: str) -> str:
    """
    Read the full content of a test YAML file.
    path is relative to the project root, e.g. 'tests/cases/networking/my_test.yaml'
    """
    if not _safe_name(path):
        return json.dumps({"error": "Invalid path."})

    fpath = _resolve_under(ROOT, path)
    if fpath is None:
        return json.dumps({"error": "Path outside project root."})

    if not fpath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        content = fpath.read_text(encoding="utf-8")
        return json.dumps({"path": path, "content": content})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def create_test(name: str, workspace: str, yaml_content: str) -> str:
    """
    Create a new test YAML file in the specified workspace.

    name      - File name without extension (e.g. 'login_test')
    workspace - Target workspace folder under tests/cases/ (e.g. 'networking')
    yaml_content - Full YAML content of the test

    The YAML must be valid and parseable. Use validate_yaml to check first.
    Returns the path of the created file.
    """
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        return json.dumps({"error": "name must contain only letters, numbers, underscores, hyphens."})
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", workspace):
        return json.dumps({"error": "workspace must contain only letters, numbers, underscores, hyphens."})

    # Validate YAML
    try:
        parsed = yaml.safe_load(yaml_content)
        if not isinstance(parsed, dict):
            return json.dumps({"error": "YAML must be a mapping (dict), not a list or scalar."})
    except yaml.YAMLError as e:
        return json.dumps({"error": f"Invalid YAML: {e}"})

    target_dir = _resolve_under(TESTS_DIR, workspace)
    if target_dir is None:
        return json.dumps({"error": "Invalid workspace path."})

    target_dir.mkdir(parents=True, exist_ok=True)
    fpath = target_dir / f"{name}.yaml"

    if fpath.exists():
        return json.dumps({"error": f"File already exists: {fpath.relative_to(ROOT)}. Use update_test to modify it."})

    fpath.write_text(yaml_content, encoding="utf-8")
    rel = str(fpath.relative_to(ROOT)).replace("\\", "/")
    return json.dumps({
        "status":  "created",
        "path":    rel,
        "name":    parsed.get("name", name),
        "steps":   len(parsed.get("steps", [])),
    })


@mcp.tool()
def update_test(path: str, yaml_content: str) -> str:
    """
    Overwrite an existing test YAML file with new content.
    path is relative to the project root.
    """
    if not _safe_name(path):
        return json.dumps({"error": "Invalid path."})

    fpath = _resolve_under(ROOT, path)
    if fpath is None:
        return json.dumps({"error": "Path outside project root."})
    if not fpath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        parsed = yaml.safe_load(yaml_content)
        if not isinstance(parsed, dict):
            return json.dumps({"error": "YAML must be a mapping."})
    except yaml.YAMLError as e:
        return json.dumps({"error": f"Invalid YAML: {e}"})

    fpath.write_text(yaml_content, encoding="utf-8")
    rel = str(fpath.relative_to(ROOT)).replace("\\", "/")
    return json.dumps({
        "status": "updated",
        "path":   rel,
        "steps":  len(parsed.get("steps", [])),
    })


@mcp.tool()
def validate_yaml(yaml_content: str) -> str:
    """
    Validate Easy BDD test YAML before saving.

    Checks:
    - Valid YAML syntax
    - Required top-level fields (name, steps)
    - Each step has an 'action' key or is a known control-flow key
    - Required parameters are present for each action
    - Variable syntax uses ${name} not $name

    Returns a list of errors and warnings.
    """
    errors = []
    warnings = []

    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return json.dumps({"valid": False, "errors": [f"YAML parse error: {e}"], "warnings": []})

    if not isinstance(parsed, dict):
        return json.dumps({"valid": False, "errors": ["Root must be a YAML mapping."], "warnings": []})

    if not parsed.get("name"):
        errors.append("Missing required field: name")
    if "steps" not in parsed:
        errors.append("Missing required field: steps")
    elif not isinstance(parsed["steps"], list):
        errors.append("'steps' must be a list")
    else:
        _validate_steps(parsed["steps"], errors, warnings, path="steps")

    # Check for bare $variable (should be ${variable})
    content_str = yaml_content
    bare_vars = re.findall(r"\$(?!\{)([A-Za-z_]\w*)", content_str)
    if bare_vars:
        warnings.append(f"Bare dollar variables found (use ${{name}} syntax): {list(set(bare_vars))[:5]}")

    return json.dumps({
        "valid":    len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
    }, indent=2)


def _validate_steps(steps: list, errors: list, warnings: list, path: str = "steps") -> None:
    CONTROL_KEYS = {"for_each", "while", "try", "condition", "shared_step", "break_if", "continue_if"}
    for i, step in enumerate(steps):
        loc = f"{path}[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{loc}: step must be a dict, got {type(step).__name__}")
            continue

        keys = set(step.keys())

        if "shared_step" in keys:
            continue  # shared steps are valid by reference

        if "for_each" in keys:
            if "steps" not in keys:
                errors.append(f"{loc}: for_each requires 'steps'")
            else:
                _validate_steps(step["steps"], errors, warnings, f"{loc}.steps")
            continue

        if "while" in keys:
            if "steps" not in keys:
                errors.append(f"{loc}: while requires 'steps'")
            else:
                _validate_steps(step["steps"], errors, warnings, f"{loc}.steps")
            continue

        if "try" in keys:
            _validate_steps(step.get("try", []), errors, warnings, f"{loc}.try")
            if "except" in step:
                _validate_steps(step["except"], errors, warnings, f"{loc}.except")
            if "finally" in step:
                _validate_steps(step["finally"], errors, warnings, f"{loc}.finally")
            continue

        if "condition" in keys:
            if "then" in step:
                _validate_steps(step["then"], errors, warnings, f"{loc}.then")
            if "else" in step:
                _validate_steps(step["else"], errors, warnings, f"{loc}.else")
            continue

        if "action" not in keys:
            errors.append(f"{loc}: step must have an 'action' key (or be a control-flow key: {sorted(CONTROL_KEYS)})")
            continue

        action = step["action"]
        defn = _ALL_ACTIONS.get(action)
        if defn is None:
            warnings.append(f"{loc}: unknown action '{action}' (may be valid if recently added)")
            continue

        params = defn.get("parameters", {})
        for pname, pdef in params.items():
            if pdef.get("required") and pname not in step:
                # field alias check (e.g. browser.fill uses 'field' but also 'selector')
                errors.append(f"{loc}: action '{action}' missing required parameter '{pname}'")


@mcp.tool()
def list_shared_steps(scope: Optional[str] = None) -> str:
    """
    List available shared steps.

    scope - 'global' for project-wide steps, a workspace name for local steps,
            or omit to list both.

    Shared steps are reusable step sequences referenced in tests with:
      - shared_step: step_name
    """
    results = []

    def _add(path: Path, scope_name: str):
        data = _load_shared_steps_file(path)
        for slug, entry in data.items():
            step_list = entry.get("steps", []) if isinstance(entry, dict) else []
            results.append({
                "name":        slug,
                "scope":       scope_name,
                "description": entry.get("description", "") if isinstance(entry, dict) else "",
                "step_count":  len(step_list),
            })

    if scope in (None, "global"):
        _add(GLOBAL_SS, "global")

    if scope is None:
        for ws in _list_workspaces_raw():
            _add(TESTS_DIR / ws / "shared_steps.yaml", ws)
    elif scope != "global":
        _add(TESTS_DIR / scope / "shared_steps.yaml", scope)

    return json.dumps({"shared_steps": results, "total": len(results)}, indent=2)


@mcp.tool()
def get_shared_step(name: str, scope: Optional[str] = None) -> str:
    """
    Get the full definition of a shared step including all its steps.

    name  - The shared step slug (e.g. 'authenticate')
    scope - 'global' or a workspace name; if omitted, searches all scopes.
    """
    def _search(path: Path, scope_name: str):
        data = _load_shared_steps_file(path)
        if name in data:
            entry = data[name]
            return {"name": name, "scope": scope_name, **entry}
        return None

    if scope in (None, "global"):
        found = _search(GLOBAL_SS, "global")
        if found:
            return json.dumps(found, indent=2)

    if scope is None:
        for ws in _list_workspaces_raw():
            found = _search(TESTS_DIR / ws / "shared_steps.yaml", ws)
            if found:
                return json.dumps(found, indent=2)
    elif scope != "global":
        found = _search(TESTS_DIR / scope / "shared_steps.yaml", scope)
        if found:
            return json.dumps(found, indent=2)

    return json.dumps({"error": f"Shared step '{name}' not found."})


@mcp.tool()
def run_test(path: str, headed: bool = False) -> str:
    """
    Execute a test and return the result summary.

    path   - Relative path to the test YAML (e.g. 'tests/cases/networking/login.yaml')
    headed - If true, run the browser in visible (non-headless) mode.

    Returns pass/fail status, duration, and any error messages.
    """
    if not _safe_name(path):
        return json.dumps({"error": "Invalid path."})

    fpath = _resolve_under(ROOT, path)
    if fpath is None:
        return json.dumps({"error": "Path outside project root."})
    if not fpath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    cmd = [sys.executable, "-m", "easy_bdd", "run", str(fpath)]
    if headed:
        cmd.append("--headed")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(ROOT),
        )
        passed = result.returncode == 0
        return json.dumps({
            "path":    path,
            "passed":  passed,
            "stdout":  result.stdout[-3000:] if result.stdout else "",
            "stderr":  result.stderr[-1000:] if result.stderr else "",
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Test timed out after 5 minutes."})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_examples(category: Optional[str] = None) -> str:
    """
    Get example YAML snippets for common test patterns.

    Categories: browser, api, websocket, telnet, assertions, control_flow, shared_steps, variables
    """
    examples = {
        "browser": textwrap.dedent("""\
            name: Browser login test
            variables:
              base_url: https://example.com
              username: admin
              password: ${DEVICE_PASSWORD}
            steps:
              - action: browser.open
                url: ${base_url}/login
              - action: browser.fill
                field: "#username"
                value: ${username}
              - action: browser.fill
                field: "#password"
                value: ${password}
              - action: browser.click
                role: button
                name: Sign In
              - action: browser.wait_for
                selector: ".dashboard"
                timeout: 10000
              - action: test.assert
                expression: "'Dashboard' in page_content"
                message: Expected dashboard after login
        """),
        "api": textwrap.dedent("""\
            name: API health check
            variables:
              base_url: https://api.example.com
              api_token: ${API_TOKEN}
            steps:
              - action: api.request
                method: GET
                url: ${base_url}/health
                headers:
                  Authorization: Bearer ${api_token}
                store_as: health_response
              - action: test.assert
                expression: "last_response_code == 200"
              - action: test.assert
                expression: "'status' in last_response_dict"
              - action: test.assert
                expression: "last_response_dict['status'] == 'ok'"
        """),
        "websocket": textwrap.dedent("""\
            name: WebSocket device ping
            variables:
              ws_url: wss://device.example.com:10444
              device_mac: "AA:BB:CC:DD:EE:FF"
            steps:
              - action: websocket.send
                url: ${ws_url}
                data: '{"deviceId": "${device_mac}", "method": "ping"}'
                store_as: ws_response
              - action: test.assert
                expression: "'error' not in ws_response"
              - action: test.assert
                expression: "'pong' in ws_response or 'result' in ws_response"
        """),
        "telnet": textwrap.dedent("""\
            name: Telnet device firmware check
            variables:
              device_ip: 192.168.1.100
            steps:
              - action: telnet.send
                host: ${device_ip}
                port: 23
                command: "?Firmware"
                store_as: fw_response
              - action: test.assert
                expression: "'Firmware=' in fw_response"
              - action: eval.exec
                code: "firmware_version = fw_response.split('Firmware=')[1].strip()"
              - action: test.log
                message: "Firmware version: ${firmware_version}"
        """),
        "assertions": textwrap.dedent("""\
            steps:
              # String contains check
              - action: test.assert
                expression: "'OK' in last_response"

              # HTTP status code
              - action: test.assert
                expression: "last_response_code == 200"

              # JSON field value
              - action: test.assert
                expression: "last_response_dict['status'] == 'active'"

              # Regex match
              - action: test.assert
                expression: "re.match(r'\\\\d+\\\\.\\\\d+\\\\.\\\\d+', firmware_version) is not None"

              # Soft assert (test continues even on failure)
              - action: test.assert
                expression: "'warning' not in last_response"
                soft: true

              # Browser element visible
              - action: test.assert_element_visible
                selector: ".success-message"
        """),
        "control_flow": textwrap.dedent("""\
            # for_each loop
            steps:
              - for_each: [1, 5, 10, 30]
                loop_var: retry_seconds
                steps:
                  - action: api.request
                    method: GET
                    url: ${base_url}/api/status
                    store_as: device_state
                  - break_if: "'ready' in device_state"
                  - action: browser.wait
                    seconds: ${retry_seconds}

            # while loop
              - while: "device_state != 'online'"
                loop_limit: 20
                steps:
                  - action: api.request
                    method: GET
                    url: ${base_url}/api/status
                    store_as: device_state
                  - action: browser.wait
                    seconds: 10

            # conditional
              - condition: "firmware_version != target_version"
                then:
                  - action: browser.upload
                    selector: "#firmware-input"
                    file_path: Firmware/${firmware_file}
                  - action: browser.click
                    role: button
                    name: Upgrade
                else:
                  - action: test.log
                    message: Already on target version

            # try / except
              - try:
                  - action: api.request
                    method: POST
                    url: ${base_url}/api/reboot
                except:
                  - action: test.log
                    message: Reboot request failed
                finally:
                  - action: browser.wait
                    seconds: 30
        """),
        "shared_steps": textwrap.dedent("""\
            # shared_steps.yaml (global or workspace-local)
            authenticate:
              description: Log in and store auth token
              steps:
                - action: api.request
                  method: POST
                  url: ${base_url}/api/login
                  body: '{"username": "${username}", "password": "${password}"}'
                - action: eval.exec
                  code: "auth_token = last_response_dict['data']['token']"

            verify_firmware:
              description: Assert firmware matches expected version
              steps:
                - action: telnet.send
                  host: ${device_ip}
                  port: 23
                  command: "?Firmware"
                  store_as: fw_response
                - action: test.assert
                  expression: "expected_version in fw_response"

            ---

            # test.yaml — using shared steps
            name: Full login and firmware check
            steps:
              - shared_step: authenticate
              - action: api.request
                method: GET
                url: ${base_url}/api/profile
                headers:
                  Authorization: Bearer ${auth_token}
              - shared_step: verify_firmware
        """),
        "variables": textwrap.dedent("""\
            # Variable scopes (highest priority first):
            # 1. Test variables   → ${name}
            # 2. Suite variables  → ${suite.name}
            # 3. Workspace vars   → ${collection.name}
            # 4. Environment vars → ${env.name} (from active environment or .env)

            name: Variable scoping example
            variables:
              device_ip:   192.168.1.100
              username:    admin
              password:    ${DEVICE_PASSWORD}    # from .env file
              api_url:     ${env.API_BASE_URL}   # from active environment

            steps:
              - action: api.request
                method: GET
                url: ${api_url}/devices/${device_ip}
                store_as: device_info

              # Store a computed value for later steps
              - action: eval.exec
                code: "firmware = last_response_dict.get('firmware', 'unknown')"

              - action: test.assert
                expression: "firmware != 'unknown'"
                message: "Device should report a firmware version"
        """),
    }

    if category:
        snippet = examples.get(category.lower())
        if snippet:
            return json.dumps({"category": category, "example": snippet})
        return json.dumps({
            "error":      f"Category '{category}' not found.",
            "available":  list(examples.keys()),
        })

    return json.dumps({
        "categories": list(examples.keys()),
        "examples":   examples,
    }, indent=2)


# ── resources ──────────────────────────────────────────────────────────────────

@mcp.resource("easy-bdd://syntax")
def syntax_reference() -> str:
    """Full YAML syntax reference for Easy BDD tests."""
    readme = ROOT / "README.md"
    if readme.exists():
        return readme.read_text(encoding="utf-8")
    return "README.md not found. Use list_actions and get_examples for reference."


@mcp.resource("easy-bdd://control-flow")
def control_flow_reference() -> str:
    """Control flow reference: for_each, while, try/except, condition, break_if, continue_if."""
    return _CONTROL_FLOW_DOCS


@mcp.resource("easy-bdd://actions")
def all_actions_resource() -> str:
    """Complete action catalog with all parameters."""
    result = {}
    for name, defn in sorted(_ALL_ACTIONS.items()):
        params = defn.get("parameters", {})
        result[name] = {
            "category":    defn.get("category", ""),
            "description": defn.get("description", defn.get("label", "")),
            "required":    {k: v.get("help", "") for k, v in params.items() if v.get("required")},
            "optional":    {k: v.get("help", "") for k, v in params.items() if not v.get("required")},
        }
        if defn.get("example"):
            result[name]["example"] = defn["example"]
    return json.dumps(result, indent=2)


@mcp.resource("easy-bdd://shared-steps")
def shared_steps_resource() -> str:
    """All currently defined shared steps (global + all workspaces)."""
    all_steps = {}

    data = _load_shared_steps_file(GLOBAL_SS)
    if data:
        all_steps["global"] = data

    for ws in _list_workspaces_raw():
        path = TESTS_DIR / ws / "shared_steps.yaml"
        data = _load_shared_steps_file(path)
        if data:
            all_steps[ws] = data

    return json.dumps(all_steps, indent=2)


# ── prompts ────────────────────────────────────────────────────────────────────

@mcp.prompt()
def create_test_prompt(
    goal: str,
    workspace: str = "general",
    protocols: str = "browser",
) -> str:
    """
    Generate a guided prompt for creating a new Easy BDD test.

    goal      - What the test should verify (e.g. 'login works and dashboard loads')
    workspace - Target workspace (default: general)
    protocols - Comma-separated protocols needed (browser, api, telnet, websocket, etc.)
    """
    protocol_list = [p.strip() for p in protocols.split(",")]

    protocol_hints = []
    if "browser" in protocol_list:
        protocol_hints.append("- Use browser.open, browser.fill, browser.click, browser.assert_text, browser.screenshot")
    if "api" in protocol_list:
        protocol_hints.append("- Use api.request with method/url/body/headers; check last_response_code and last_response_dict")
    if "websocket" in protocol_list:
        protocol_hints.append("- Use websocket.send with url and data; store_as for the response")
    if "telnet" in protocol_list:
        protocol_hints.append("- Use telnet.send with host/port/command; connections are pooled automatically")
    if "ssh" in protocol_list:
        protocol_hints.append(
            "- For SSH use ssh.command (preferred): host/username/password/command/prompt. "
            "For multi-step sessions: ssh.connect → ssh.command → ssh.disconnect. "
            "Use command.ssh only for one-shot Linux commands that return an exit code."
        )
    if "serial" in protocol_list:
        protocol_hints.append("- Use serial.send with port/baudrate/data")

    return textwrap.dedent(f"""\
        Create an Easy BDD test for the following goal:

        GOAL: {goal}
        TARGET WORKSPACE: {workspace}
        PROTOCOLS: {", ".join(protocol_list)}

        Steps to follow:
        1. Call list_actions to browse available actions for the protocols needed.
        2. Call get_action on any action before using it to check required parameters.
        3. Draft the YAML test structure:
           - name: descriptive test name
           - description: what it verifies
           - tags: relevant categories
           - variables: any values that might change per environment
           - steps: the test logic

        Protocol guidance:
        {chr(10).join(protocol_hints)}

        General rules:
        - Always use ${{variable_name}} syntax for variables, never $variable
        - Add test.assert steps after every significant action to verify correctness
        - Use store_as to capture values you need in later steps
        - Call validate_yaml before calling create_test
        - Use shared_step references where the shared step already exists (call list_shared_steps first)

        4. Call validate_yaml with the YAML content to check for errors.
        5. Fix any validation errors, then call create_test with name, workspace, and yaml_content.
    """)


@mcp.prompt()
def debug_test_prompt(path: str) -> str:
    """
    Generate a prompt to help debug a failing test.

    path - Relative path to the failing test file
    """
    return textwrap.dedent(f"""\
        Help me debug this failing Easy BDD test: {path}

        Steps to follow:
        1. Call read_test("{path}") to see the current test content.
        2. Identify which step is likely failing based on the error message.
        3. Call get_action on the failing action to verify all required parameters are correct.
        4. Check that all variable references use ${{name}} syntax.
        5. Check that selectors or URLs are correct and not hardcoded values that may have changed.
        6. If the fix is clear, call validate_yaml with the corrected YAML, then update_test.
        7. Optionally call run_test("{path}") to verify the fix.
    """)


@mcp.prompt()
def migrate_test_prompt(source_framework: str, source_content: str) -> str:
    """
    Generate a prompt for migrating a test from another framework.

    source_framework - 'robot' for Robot Framework, 'bdd' for the previous mybdd framework
    source_content   - The raw content to migrate
    """
    if source_framework.lower() in ("robot", "robot framework"):
        framework_note = (
            "This is a Robot Framework .robot file. "
            "Use the /api/migrate/robot endpoint (POST with {content, save_to_workspace}) "
            "or call the migration API if available."
        )
    else:
        framework_note = (
            "This is from the previous mybdd/pytest-bdd framework using pipe-delimited keyword syntax. "
            "Use the /api/migrate/bdd endpoint (POST with {content, save_to_workspace}) "
            "or call the migration API if available."
        )

    return textwrap.dedent(f"""\
        Migrate this test from {source_framework} to Easy BDD YAML format.

        {framework_note}

        SOURCE CONTENT:
        {source_content}

        After migration:
        1. Review the generated YAML for any TODO steps that need manual mapping.
        2. Verify that all variable references are correct.
        3. Ensure all required parameters are present for each action.
        4. Call validate_yaml to check the result before saving.
        5. Use create_test to save the migrated test to the appropriate workspace.
    """)


# ── locator debugger tools ─────────────────────────────────────────────────────
#
# These tools use Playwright to test selectors against live pages and
# auto-heal YAML test files by trying fallback_selectors in order.
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import concurrent.futures


def _run_async(coro):
    """Run an async coroutine from a sync context without event-loop conflicts."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _probe_selectors_async(url: str, selectors: List[str], timeout_ms: int) -> List[Dict]:
    """Navigate to url and test each selector; return per-selector results."""
    from playwright.async_api import async_playwright

    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(1500)   # let SPAs settle
        except Exception as e:
            await browser.close()
            return [{"selector": s, "found": False, "error": f"Navigation failed: {e}"} for s in selectors]

        for sel in selectors:
            entry: Dict[str, Any] = {"selector": sel}
            try:
                loc = page.locator(sel)
                count = await loc.count()
                if count == 0:
                    entry["found"] = False
                else:
                    entry["found"] = True
                    entry["count"] = count
                    try:
                        entry["visible"] = await loc.first.is_visible(timeout=2000)
                    except Exception:
                        entry["visible"] = False
                    try:
                        entry["enabled"] = await loc.first.is_enabled(timeout=2000)
                    except Exception:
                        entry["enabled"] = False
                    try:
                        # bounding box — confirms element is rendered, not just in DOM
                        bb = await loc.first.bounding_box(timeout=2000)
                        entry["in_viewport"] = bb is not None
                    except Exception:
                        entry["in_viewport"] = False
            except Exception as e:
                entry["found"] = False
                entry["error"] = str(e)
            results.append(entry)

        await browser.close()
    return results


@mcp.tool()
def probe_selector(
    url: str,
    selector: str,
    fallback_selectors=None,
    timeout: int = 20,
) -> str:
    """
    Open *url* in a headless browser and test whether *selector* (and each
    fallback) can locate an element on the page.

    Returns found/visible/enabled status for each selector so you can pick
    the best one to use in the test YAML.

    Parameters
    ----------
    url                 : Full URL to open (e.g. https://192.168.100.145/network)
    selector            : Primary selector to test
    fallback_selectors  : Additional selectors to try (optional list)
    timeout             : Navigation timeout in seconds (default 20)
    """
    all_selectors = [selector] + (fallback_selectors or [])
    try:
        results = _run_async(_probe_selectors_async(url, all_selectors, timeout * 1000))
        best = next((r for r in results if r.get("found") and r.get("visible") and r.get("enabled")), None)
        return json.dumps({
            "url":     url,
            "results": results,
            "best":    best["selector"] if best else None,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def fix_test_selectors(path: str, timeout: int = 20) -> str:
    """
    Open a test YAML file, and for every step that has a *selector* +
    *fallback_selectors*, try each candidate against the live URL.
    The first selector that is found AND visible AND enabled becomes the new
    primary; fallback_selectors is removed from the saved file.

    The URL is taken from the step's variables.base_url + the test's url field
    (or variables.base_url alone if no per-step URL is stored).

    Returns a summary of which selectors were changed and which couldn't be fixed.

    Parameters
    ----------
    path    : Relative path to the test YAML (e.g. tests/cases/crawled/click_apply.yaml)
    timeout : Per-page navigation timeout in seconds (default 20)
    """
    if not _safe_name(path):
        return json.dumps({"error": "Invalid path."})
    fpath = _resolve_under(ROOT, path)
    if fpath is None or not fpath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    data = _load_yaml_file(fpath)
    if not isinstance(data, dict):
        return json.dumps({"error": "Could not parse YAML."})

    variables = data.get("variables") or {}
    base_url = variables.get("base_url", "")
    # page_url is written by the crawler for the specific page each test covers.
    # Fall back to base_url if not present (older test files).
    probe_url = variables.get("page_url") or base_url
    steps = data.get("steps", [])
    changes: List[Dict] = []
    unfixed: List[Dict] = []

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        # Steps are dot-notation dicts: {"browser.click": {"selector": ..., "fallback_selectors": [...]}}
        for action_key, params in step.items():
            if not isinstance(params, dict):
                continue
            primary = params.get("selector")
            fallbacks = params.get("fallback_selectors", [])
            if not primary or not fallbacks:
                continue   # nothing to heal

            page_url = probe_url
            try:
                results = _run_async(
                    _probe_selectors_async(page_url, [primary] + fallbacks, timeout * 1000)
                )
            except Exception as e:
                unfixed.append({"step": i, "action": action_key, "error": str(e)})
                continue

            # Pick best: found + visible + enabled; fall back to just found + visible
            best = (
                next((r for r in results if r.get("found") and r.get("visible") and r.get("enabled")), None)
                or next((r for r in results if r.get("found") and r.get("visible")), None)
                or next((r for r in results if r.get("found")), None)
            )

            if best and best["selector"] != primary:
                changes.append({
                    "step": i,
                    "action": action_key,
                    "old": primary,
                    "new": best["selector"],
                })
                params["selector"] = best["selector"]
                del params["fallback_selectors"]
            elif best and best["selector"] == primary:
                # Primary already works — just drop the fallback list
                del params["fallback_selectors"]
                changes.append({"step": i, "action": action_key, "old": primary, "new": primary, "note": "primary already works"})
            else:
                unfixed.append({"step": i, "action": action_key, "selector": primary, "tried": len(results)})

    if changes:
        import yaml as _yaml
        fpath.write_text(
            _yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    return json.dumps({
        "path":    path,
        "changes": changes,
        "unfixed": unfixed,
        "saved":   bool(changes),
    }, indent=2)


@mcp.tool()
def fix_crawled_tests(
    directory: str = "tests/cases/crawled",
    limit: int = 50,
    timeout: int = 20,
) -> str:
    """
    Batch-fix selectors in all YAML files under *directory*.

    For each file, tries every step's fallback_selectors against the live URL
    and rewrites the file with the first working selector.

    Parameters
    ----------
    directory : Directory relative to project root (default: tests/cases/crawled)
    limit     : Max number of files to process in one call (default 50)
    timeout   : Per-page navigation timeout in seconds (default 20)
    """
    if not _safe_name(directory):
        return json.dumps({"error": "Invalid directory path."})
    dpath = _resolve_under(ROOT, directory)
    if dpath is None or not dpath.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    yaml_files = sorted(dpath.rglob("*.yaml"))[:limit]
    summary = []
    for fpath in yaml_files:
        rel = str(fpath.relative_to(ROOT)).replace("\\", "/")
        result_str = fix_test_selectors(path=rel, timeout=timeout)
        result = json.loads(result_str)
        if "error" not in result:
            summary.append({
                "file":    rel,
                "changes": len(result.get("changes", [])),
                "unfixed": len(result.get("unfixed", [])),
            })

    total_changes = sum(r["changes"] for r in summary)
    total_unfixed = sum(r["unfixed"] for r in summary)
    return json.dumps({
        "files_processed": len(summary),
        "total_changes":   total_changes,
        "total_unfixed":   total_unfixed,
        "details":         summary,
    }, indent=2)


@mcp.tool()
def get_testrail_run_failures(run_id: int, status: str = "failed,retest") -> str:
    """
    Fetch test cases from a TestRail run filtered by status.

    Returns case titles, IDs, and section names so you can match them to
    local YAML files and fix their selectors.

    Parameters
    ----------
    run_id : TestRail run ID (e.g. 195555)
    status : Comma-separated status names to include (default: failed,retest)
    """
    try:
        sys.path.insert(0, str(ROOT))
        from easy_bdd.services.testrail_service import TestRailService
        import re as _re

        tr = TestRailService()

        # Status name → TestRail status ID mapping
        STATUS_IDS = {
            "passed":   TestRailService.STATUS_PASSED,
            "failed":   TestRailService.STATUS_FAILED,
            "retest":   TestRailService.STATUS_RETEST,
            "blocked":  TestRailService.STATUS_BLOCKED,
            "untested": TestRailService.STATUS_UNTESTED,
        }
        wanted_ids = {STATUS_IDS[s.strip().lower()] for s in status.split(",") if s.strip().lower() in STATUS_IDS}

        tests = tr.get_tests(run_id)

        # Build section_id → case lookup from full case list to get section names.
        # get_tests returns section_id per test item.
        all_section_ids = {t.get("section_id") for t in tests if t.get("section_id")}
        section_names: Dict[int, str] = {}
        if all_section_ids:
            # Determine project_id from the run
            try:
                run_info = tr.get_run(run_id)
                project_id = run_info.get("project_id")
                suite_id = run_info.get("suite_id")
                if project_id:
                    secs = tr.get_sections(project_id, suite_id=suite_id)
                    for sec in secs:
                        section_names[sec["id"]] = sec.get("name", "")
            except Exception:
                pass  # section names are optional enrichment

        def _section_to_url_path(section_name: str, base_url: str = "") -> str:
            """
            Convert a section name like 'Crawled / network > wifi' to a URL path
            '/network/wifi' (or a full URL when base_url is provided).
            """
            # Strip the leading prefix (e.g. 'Crawled / ')
            name = _re.sub(r'^[^/]+/\s*', '', section_name)
            # Convert ' > ' separators back to '/'
            path = name.replace(" > ", "/").strip()
            if path == "root":
                path = ""
            return f"{base_url.rstrip('/')}/{path}" if base_url and path else (base_url or f"/{path}")

        def _yaml_filename_hint(title: str) -> str:
            """Guess the YAML filename from a TestRail case title."""
            # Titles are stored as 'Feature: <case_name>'
            name = _re.sub(r'^Feature:\s*', '', title, flags=_re.I)
            name = name.lower()
            name = _re.sub(r'[^a-z0-9_\s-]', '', name)
            name = _re.sub(r'[\s-]+', '_', name).strip('_')
            return (name[:60] or 'test') + '.yaml'

        failures = []
        for t in tests:
            if t.get("status_id") in wanted_ids:
                sec_id = t.get("section_id")
                sec_name = section_names.get(sec_id, "") if sec_id else ""
                failures.append({
                    "test_id":      t.get("id"),
                    "case_id":      t.get("case_id"),
                    "title":        t.get("title", ""),
                    "status":       t.get("status_id"),
                    "section_id":   sec_id,
                    "section_name": sec_name,
                    "yaml_hint":    _yaml_filename_hint(t.get("title", "")),
                    "page_url_hint": _section_to_url_path(sec_name),
                })

        return json.dumps({
            "run_id":   run_id,
            "total":    len(tests),
            "failures": len(failures),
            "cases":    failures,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def repush_yaml_to_testrail(
    path: str,
    case_id=None,
) -> str:
    """
    Re-push a YAML test file's steps to an existing TestRail case.

    Useful after fix_test_selectors has healed the selectors — this updates
    the case's Preconditions field in TestRail with the corrected YAML.

    Parameters
    ----------
    path    : Relative path to the YAML file (e.g. tests/cases/crawled/click_apply.yaml)
    case_id : TestRail case ID to update. If omitted, reads it from the YAML
              variables.testrail_case_id field (written by the crawler's publisher).
    """
    if not _safe_name(path):
        return json.dumps({"error": "Invalid path."})
    fpath = _resolve_under(ROOT, path)
    if fpath is None or not fpath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    data = _load_yaml_file(fpath)
    if not isinstance(data, dict):
        return json.dumps({"error": "Could not parse YAML."})

    # Resolve case_id
    if not case_id:
        case_id = (data.get("variables") or {}).get("testrail_case_id")
    if not case_id:
        return json.dumps({"error": "No case_id provided and none found in YAML variables.testrail_case_id."})

    try:
        sys.path.insert(0, str(ROOT))
        import yaml as _yaml
        from easy_bdd.services.testrail_service import TestRailService

        tr = TestRailService()

        steps_yaml = _yaml.dump(
            {"steps": data.get("steps", [])},
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        result = tr.update_case(case_id, custom_preconds=steps_yaml)
        return json.dumps({"updated": case_id, "title": result.get("title", ""), "ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
