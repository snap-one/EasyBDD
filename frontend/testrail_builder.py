"""Easy BDD TestRail Test Builder — backend.

A focused web app for authoring TestRail test cases visually:

  * Create Var:, Shared:, Setup:, Teardown: and Feature: cases from guided
    forms — no YAML syntax or action-name spelling to get wrong.
  * The step palette is generated from frontend/action_definitions.py merged
    with easybdd.core.validator.ACTION_SCHEMA, so every action the runner
    supports is available.
  * The Preconditions body is generated server-side in the flush-left
    dot-notation format the runner expects, then round-trip validated with
    the exact same parser the runner uses (fix_step_list_indent +
    parse_yaml_lenient).
  * Cases publish straight into a TestRail suite/section, and runs can be
    assembled from published cases (EASY_BDD: prefix) ready for
    `python -m easybdd testrail-run`.

Start with:  python frontend/start_testrail_builder.py   (default port 8091)
"""

from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from action_definitions import ACTION_DEFINITIONS  # noqa: E402

from easybdd.core.parser import (  # noqa: E402
    fix_step_list_indent,
    parse_yaml_lenient,
    strip_html_to_text,
)
from easybdd.core.testrail_utils import _needs_quoting  # noqa: E402
from easybdd.core.validator import ACTION_SCHEMA  # noqa: E402
from easybdd.services.testrail_service import (  # noqa: E402
    TestRailError,
    TestRailService,
)

app = FastAPI(
    title="Easy BDD TestRail Test Builder",
    description="Author Var/Shared/Setup/Teardown/Feature cases visually and publish to TestRail",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

CASE_PREFIXES = {
    "feature": "Feature:",
    "var": "Var:",
    "shared": "Shared:",
    "setup": "Setup:",
    "teardown": "Teardown:",
    "test": "Test:",
}

_ROLE_BY_PREFIX = {v: k for k, v in CASE_PREFIXES.items()}

# Categories for actions that exist in the runner's ACTION_SCHEMA but have no
# rich definition in action_definitions.py
_PREFIX_CATEGORY = {
    "telnet": "Telnet",
    "serial": "Serial",
    "websocket": "WebSocket",
    "eval": "Eval",
    "command": "Command",
    "test": "Test",
    "aws": "AWS",
    "browser": "Browser",
    "api": "API",
    "ssh": "SSH",
    "jsonrpc": "JSON-RPC",
    "ovrc": "OvrC API",
    "pagerduty": "PagerDuty",
}

_PREFIX_ICON = {
    "telnet": "📟",
    "serial": "🔌",
    "websocket": "🔄",
    "eval": "🐍",
    "command": "💻",
}


# --------------------------------------------------------------------------- #
# Action catalog                                                               #
# --------------------------------------------------------------------------- #

# Definitions that override / extend action_definitions.py where it disagrees
# with what the runner actually dispatches (see runner._handle_assert_action
# and runner._handle_extract_action).
def _sel_param(help_text: str = "CSS selector for the element") -> Dict[str, Any]:
    return {"type": "text", "required": False, "label": "Selector",
            "placeholder": "#element or .class", "help": help_text}


def _timeout_param() -> Dict[str, Any]:
    return {"type": "number", "required": False, "label": "Timeout (ms)", "placeholder": "10000"}


def _browser_assert(label: str, desc: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"selector": {**_sel_param(), "required": True}}
    params.update(extra or {})
    params["timeout"] = _timeout_param()
    return {"category": "Browser", "label": label, "description": desc, "icon": "✅", "parameters": params}


_CATALOG_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "browser.fill": {
        "category": "Browser",
        "label": "Fill Input Field",
        "description": "Fill a form field with text — target it by CSS selector, role+name, or label",
        "icon": "✏️",
        "_one_of": [["selector", "field", "role", "label"]],
        "parameters": {
            "selector": _sel_param("CSS selector for the input field"),
            "value": {"type": "text", "required": True, "label": "Value",
                      "placeholder": "testuser", "help": "Text to fill in the field"},
            "role": {"type": "text", "required": False, "label": "Role",
                     "placeholder": "textbox", "help": "ARIA role (use with Name)"},
            "name": {"type": "text", "required": False, "label": "Name",
                     "help": "Accessible name (use with Role)"},
            "label": {"type": "text", "required": False, "label": "Label",
                      "help": "Target by form label text"},
            "field": {"type": "text", "required": False, "label": "Field (alias)",
                      "help": "Alias of Selector — kept for older cases"},
            "clear": {"type": "boolean", "required": False, "label": "Clear first",
                      "help": "Clear the field before typing"},
        },
    },
    "browser.assert_checked": _browser_assert(
        "Assert Checkbox Checked", "Assert a checkbox/toggle is checked"),
    "browser.assert_unchecked": _browser_assert(
        "Assert Checkbox Unchecked", "Assert a checkbox/toggle is NOT checked"),
    "test.assert_text_contains": _browser_assert(
        "Assert Text Contains", "Assert an element's text contains a substring",
        {"text": {"type": "text", "required": True, "label": "Text"}}),
    "test.assert_text_equals": _browser_assert(
        "Assert Text Equals", "Assert an element's text equals a value",
        {"text": {"type": "text", "required": True, "label": "Text"}}),
    "test.assert_element_visible": _browser_assert(
        "Assert Element Visible", "Assert an element is visible on the page"),
    "test.assert_element_not_visible": _browser_assert(
        "Assert Element Not Visible", "Assert an element is not visible"),
    "test.assert_element_enabled": _browser_assert(
        "Assert Element Enabled", "Assert an element is enabled"),
    "test.assert_element_disabled": _browser_assert(
        "Assert Element Disabled", "Assert an element is disabled"),
    "test.assert_element_count": _browser_assert(
        "Assert Element Count", "Assert how many elements match a selector",
        {"count": {"type": "number", "required": True, "label": "Count", "placeholder": "1"}}),
    "test.assert": {
        "category": "Test",
        "label": "Assert Condition",
        "description": "Assert a Python expression is true (e.g. last_status_code == 200)",
        "icon": "✅",
        "parameters": {
            "expression": {
                "type": "text",
                "required": True,
                "label": "Expression",
                "placeholder": "last_status_code == 200",
                "help": "Python expression evaluated against test variables",
            },
            "message": {
                "type": "text",
                "required": False,
                "label": "Failure message",
                "help": "Custom message shown when the assertion fails",
            },
        },
    },
    "websocket.connect": {
        "category": "WebSocket",
        "label": "WebSocket Connect",
        "description": "Open a WebSocket connection (pooled by URL — later send/receive steps reuse it)",
        "icon": "🔄",
        "parameters": {
            "url": {"type": "text", "required": True, "label": "URL",
                    "placeholder": "wss://host:port/path", "help": "WebSocket endpoint (ws:// or wss://)"},
            "timeout": {"type": "number", "required": False, "label": "Timeout (s)", "placeholder": "10"},
            "headers": {"type": "json", "required": False, "label": "Headers",
                        "help": "e.g. {header: '${mac},127.0.0.1,80,plain'}"},
            "subprotocols": {"type": "list", "required": False, "label": "Subprotocols"},
            "verify_ssl": {"type": "boolean", "required": False, "label": "Verify SSL"},
            "session_token": {"type": "text", "required": False, "label": "Session token"},
            "auth_url": {"type": "text", "required": False, "label": "Auth URL",
                         "help": "Optional HTTP auth endpoint called before connecting"},
            "auth_username": {"type": "text", "required": False, "label": "Auth username"},
            "auth_password": {"type": "text", "required": False, "label": "Auth password"},
        },
    },
    "websocket.send": {
        "category": "WebSocket",
        "label": "WebSocket Send",
        "description": "Send a message and read the reply. With Method set, sends a JSON-RPC envelope; extra parameters become the JSON-RPC params.",
        "icon": "📨",
        "parameters": {
            "url": {"type": "text", "required": True, "label": "URL",
                    "placeholder": "wss://host:port/path",
                    "help": "Identifies the pooled connection (reconnects automatically)"},
            "method": {"type": "text", "required": False, "label": "JSON-RPC method",
                       "placeholder": "dxGetAbout",
                       "help": "When set, the message is wrapped in a JSON-RPC 2.0 envelope"},
            "data": {"type": "json", "required": False, "label": "Data / params",
                     "help": "Raw message, or the params dict in JSON-RPC mode"},
            "wait_for": {"type": "text", "required": False, "label": "Wait for",
                         "help": "Keep reading until the response contains this text"},
            "timeout": {"type": "number", "required": False, "label": "Timeout (s)", "placeholder": "10"},
            "store_as": {"type": "text", "required": False, "label": "Store as",
                         "help": "Variable name to store the response"},
        },
    },
    "websocket.receive": {
        "category": "WebSocket",
        "label": "WebSocket Receive",
        "description": "Read the next message from an open WebSocket connection",
        "icon": "📥",
        "parameters": {
            "url": {"type": "text", "required": True, "label": "URL",
                    "help": "Identifies the pooled connection"},
            "wait_for": {"type": "text", "required": False, "label": "Wait for",
                         "help": "Keep reading until the response contains this text"},
            "timeout": {"type": "number", "required": False, "label": "Timeout (s)", "placeholder": "10"},
            "store_as": {"type": "text", "required": False, "label": "Store as"},
        },
    },
    "websocket.disconnect": {
        "category": "WebSocket",
        "label": "WebSocket Disconnect",
        "description": "Close a pooled WebSocket connection",
        "icon": "🔌",
        "parameters": {
            "url": {"type": "text", "required": False, "label": "URL",
                    "help": "Connection to close (omit to no-op)"},
        },
    },
    "test.extract": {
        "category": "Test",
        "label": "Extract Value",
        "description": "Extract a field from a stored response (dict dot-notation or CLI 'Key : Value' text)",
        "icon": "🔍",
        "parameters": {
            "field": {
                "type": "text",
                "required": True,
                "label": "Field",
                "placeholder": "access_token or data.user.id",
                "help": "Field name — dot-notation for dict responses, key substring for CLI text",
            },
            "from": {
                "type": "text",
                "required": False,
                "label": "From variable",
                "placeholder": "last_response",
                "help": "Variable to read from (default: last_response)",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Store as",
                "help": "Variable name to store the extracted value",
            },
            "equals": {
                "type": "text",
                "required": False,
                "label": "Assert equals",
                "help": "Optionally assert the extracted value equals this",
            },
            "contains": {
                "type": "text",
                "required": False,
                "label": "Assert contains",
                "help": "Optionally assert the extracted value contains this string",
            },
            "message": {
                "type": "text",
                "required": False,
                "label": "Failure message",
            },
        },
    },
}


def _build_catalog() -> Dict[str, Dict[str, Any]]:
    """Merge the rich UI catalog with the runner's ACTION_SCHEMA.

    Actions only known to ACTION_SCHEMA get generic text-field parameter
    definitions so nothing the runner supports is missing from the palette.
    Aliases (short names / alias_of entries) are skipped — the builder always
    emits canonical service.verb names.
    """
    catalog: Dict[str, Dict[str, Any]] = {}
    for action_id, definition in ACTION_DEFINITIONS.items():
        catalog[action_id] = {
            "category": definition.get("category", "Other"),
            "label": definition.get("label", action_id),
            "description": definition.get("description", ""),
            "icon": definition.get("icon", "⚙️"),
            "parameters": definition.get("parameters", {}),
        }

    for key, schema in ACTION_SCHEMA.items():
        if "." not in key or "alias_of" in schema or key in catalog:
            continue
        # ws.* / pd.* / s3.* style short prefixes are aliases of canonical ones
        prefix = key.split(".", 1)[0]
        if prefix in ("ws", "pd", "s3"):
            continue
        params: Dict[str, Any] = {}
        for name in schema.get("required", []):
            params[name] = {"type": "text", "required": True, "label": name}
        for name in schema.get("optional", []):
            params[name] = {"type": "text", "required": False, "label": name}
        catalog[key] = {
            "category": _PREFIX_CATEGORY.get(prefix, prefix.title()),
            "label": key,
            "description": "",
            "icon": _PREFIX_ICON.get(prefix, "⚙️"),
            "parameters": params,
        }

    catalog.update(_CATALOG_OVERRIDES)
    return catalog


CATALOG = _build_catalog()


def _schema_for(action: str) -> Optional[Dict[str, Any]]:
    """Resolve an action name in ACTION_SCHEMA, following alias_of."""
    schema = ACTION_SCHEMA.get(action)
    if schema and "alias_of" in schema:
        return ACTION_SCHEMA.get(schema["alias_of"])
    return schema


# --------------------------------------------------------------------------- #
# Case model                                                                    #
# --------------------------------------------------------------------------- #

class StepNode(BaseModel):
    kind: str  # action | shared | for_each | while | condition | try | raw
    action: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = None            # shared step name
    items: Optional[Any] = None           # for_each list (list or "${var}")
    loop_var: Optional[str] = None
    expression: Optional[str] = None      # while / condition
    loop_limit: Optional[int] = None
    steps: List["StepNode"] = Field(default_factory=list)        # for_each / while / try
    then_steps: List["StepNode"] = Field(default_factory=list)   # condition
    else_steps: List["StepNode"] = Field(default_factory=list)   # condition
    except_steps: List["StepNode"] = Field(default_factory=list)  # try
    finally_steps: List["StepNode"] = Field(default_factory=list)  # try
    yaml_text: Optional[str] = None       # raw


StepNode.model_rebuild()


class VarRow(BaseModel):
    key: str
    value: Any = ""


class CaseModel(BaseModel):
    case_type: str  # feature | var | shared | setup | teardown
    name: str = ""
    variables: List[VarRow] = Field(default_factory=list)
    data_rows: Optional[str] = None  # YAML text for parameterized cases
    steps: List[StepNode] = Field(default_factory=list)


class PublishRequest(BaseModel):
    model: CaseModel
    project_id: int
    suite_id: Optional[int] = None
    section_id: Optional[int] = None
    case_id: Optional[int] = None  # update existing case when set


class SectionRequest(BaseModel):
    project_id: int
    suite_id: Optional[int] = None
    name: str
    parent_id: Optional[int] = None


class RunRequest(BaseModel):
    project_id: int
    suite_id: Optional[int] = None
    name: str
    case_ids: List[int]
    description: Optional[str] = None


# --------------------------------------------------------------------------- #
# Serialization — model → TestRail Preconditions text                          #
# --------------------------------------------------------------------------- #

def _scalar(v: Any) -> str:
    """Format a scalar param value, quoting only when YAML requires it."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if _needs_quoting(s):
        return "'" + s.replace("'", "''") + "'"
    return s


def _flow(v: Any) -> str:
    """Single-line flow-style YAML for dict/list values (safe to re-indent)."""
    return yaml.safe_dump(v, default_flow_style=True, width=100000).strip()


def _coerce_param(value: Any, ptype: str) -> Any:
    """Coerce a UI-supplied param value to the type the action expects."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if ptype == "number":
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return value
    if ptype == "boolean":
        if text.lower() in ("true", "yes", "1"):
            return True
        if text.lower() in ("false", "no", "0"):
            return False
        return value
    if ptype in ("json", "keyvalue", "list", "object"):
        if text.startswith(("{", "[")):
            try:
                parsed = yaml.safe_load(text)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except yaml.YAMLError:
                pass
    return value


def _clean_params(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Drop empty params and coerce values to their declared types."""
    definition = CATALOG.get(action, {})
    schema = definition.get("parameters", {})
    cleaned: Dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        ptype = schema.get(k, {}).get("type", "text")
        cleaned[k] = _coerce_param(v, ptype)
    return cleaned


def _emit_params(params: Dict[str, Any], lines: List[str], indent: str) -> None:
    for k, v in params.items():
        if isinstance(v, (dict, list)):
            lines.append(f"{indent}{k}: {_flow(v)}")
        else:
            lines.append(f"{indent}{k}: {_scalar(v)}")


def _emit_nested_steps(steps: List[StepNode], lines: List[str]) -> None:
    """Emit steps nested inside a control-flow block.

    Nested blocks are written as properly indented YAML (items at two spaces,
    params at six) — fix_step_list_indent passes indented lines through
    untouched, so the structure survives the runner's re-indent pass.
    """
    for node in steps:
        if node.kind == "action" and node.action:
            params = _clean_params(node.action, node.params)
            if params:
                lines.append(f"  - {node.action}:")
                _emit_params(params, lines, "      ")
            else:
                lines.append(f"  - {node.action}: {{}}")
        elif node.kind == "shared" and node.name:
            lines.append(f"  - shared_step: {_scalar(node.name)}")
        elif node.kind == "raw" and node.yaml_text:
            raw: List[str] = []
            _emit_raw(node.yaml_text, raw)
            lines.extend("  " + ln for ln in raw)
        else:
            raise ValueError(
                "Nested control-flow blocks are not supported — flatten the "
                "inner block or move it to a Shared: case."
            )


def _emit_raw(text: str, lines: List[str]) -> None:
    """Emit a raw YAML step (single list item) exactly as written."""
    raw_lines = [ln for ln in text.splitlines() if ln.strip()]
    if not raw_lines:
        return
    first = raw_lines[0]
    if not first.lstrip().startswith("-"):
        raw_lines[0] = f"- {first.strip()}"
    lines.extend(raw_lines)


def _emit_step(node: StepNode, lines: List[str], number: int) -> None:
    """Emit one top-level step in flush-left dot-notation."""
    if node.kind == "action" and node.action:
        label = node.action
        params = _clean_params(node.action, node.params)
        for hint in ("name", "label", "text", "url", "message"):
            if hint in params and isinstance(params[hint], str):
                label = f"{node.action} ({params[hint]})"
                break
        lines.append(f"# {number}. {label}")
        if params:
            lines.append(f"- {node.action}:")
            _emit_params(params, lines, "")
        else:
            lines.append(f"- {node.action}: {{}}")

    elif node.kind == "shared":
        if not node.name:
            raise ValueError(f"Step {number}: shared step has no name")
        lines.append(f"# {number}. shared_step ({node.name})")
        lines.append(f"- shared_step: {_scalar(node.name)}")

    elif node.kind == "for_each":
        items = node.items
        if isinstance(items, str):
            items = items.strip()
            if items.startswith(("[", "{")):
                items = yaml.safe_load(items)
        lines.append(f"# {number}. for_each loop")
        lines.append(f"- for_each: {_flow(items) if isinstance(items, (list, dict)) else _scalar(items)}")
        if node.loop_var:
            lines.append(f"  loop_var: {node.loop_var}")
        lines.append("  steps:")
        _emit_nested_steps(node.steps, lines)

    elif node.kind == "while":
        if not node.expression:
            raise ValueError(f"Step {number}: while loop has no condition")
        lines.append(f"# {number}. while loop")
        lines.append(f"- while: {_scalar(node.expression)}")
        if node.loop_limit:
            lines.append(f"  loop_limit: {node.loop_limit}")
        lines.append("  steps:")
        _emit_nested_steps(node.steps, lines)

    elif node.kind == "condition":
        if not node.expression:
            raise ValueError(f"Step {number}: condition has no expression")
        lines.append(f"# {number}. condition")
        lines.append(f"- condition: {_scalar(node.expression)}")
        lines.append("  then:")
        _emit_nested_steps(node.then_steps, lines)
        if node.else_steps:
            # Blank line stops the indent fixer's param scan on the previous
            # nested step — without it 'else:' would be swallowed as a param.
            lines.append("")
            lines.append("  else:")
            _emit_nested_steps(node.else_steps, lines)

    elif node.kind == "try":
        lines.append(f"# {number}. try / except / finally")
        lines.append("- try:")
        _emit_nested_steps(node.steps, lines)
        if node.except_steps:
            lines.append("")
            lines.append("  except:")
            _emit_nested_steps(node.except_steps, lines)
        if node.finally_steps:
            lines.append("")
            lines.append("  finally:")
            _emit_nested_steps(node.finally_steps, lines)

    elif node.kind == "raw":
        lines.append(f"# {number}. raw step")
        _emit_raw(node.yaml_text or "", lines)

    else:
        raise ValueError(f"Step {number}: unknown step kind {node.kind!r}")


def _coerce_var_value(value: Any) -> Any:
    """Let engineers type [1, 2] or {a: b} into a variable value field."""
    if isinstance(value, str) and value.strip().startswith(("[", "{")):
        try:
            parsed = yaml.safe_load(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except yaml.YAMLError:
            pass
    return value


def serialize_case_body(model: CaseModel) -> str:
    """Build the TestRail Preconditions text for a case model."""
    if model.case_type == "var":
        lines = []
        for row in model.variables:
            if not row.key.strip():
                continue
            value = _coerce_var_value(row.value)
            if isinstance(value, (dict, list)):
                lines.append(f"{row.key.strip()}: {_flow(value)}")
            else:
                lines.append(f"{row.key.strip()}: {_scalar(value)}")
        return "\n".join(lines)

    lines: List[str] = []
    var_rows = [r for r in model.variables if r.key.strip()]
    if var_rows:
        # Keys must be indented under variables: — flush-left keys become
        # top-level siblings after parsing and the runner would ignore them.
        lines.append("variables:")
        for row in var_rows:
            value = _coerce_var_value(row.value)
            if isinstance(value, (dict, list)):
                lines.append(f"  {row.key.strip()}: {_flow(value)}")
            else:
                lines.append(f"  {row.key.strip()}: {_scalar(value)}")
        lines.append("")

    if model.data_rows and model.data_rows.strip():
        parsed_rows = yaml.safe_load(model.data_rows)
        if not isinstance(parsed_rows, list):
            raise ValueError("Data rows must be a YAML list of mappings")
        lines.append("data:")
        lines.append(yaml.safe_dump(parsed_rows, default_flow_style=False, width=100000).rstrip())
        lines.append("")

    lines.append("steps:")
    for idx, node in enumerate(model.steps, start=1):
        _emit_step(node, lines, idx)
    return "\n".join(lines)


def case_title(model: CaseModel) -> str:
    prefix = CASE_PREFIXES.get(model.case_type)
    if not prefix:
        raise ValueError(f"Unknown case type {model.case_type!r}")
    return f"{prefix} {model.name.strip()}"


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #

# Actions where arbitrary extra params are legitimate (websocket.send folds
# unrecognized params into the JSON-RPC params dict).
_FREEFORM_PARAM_ACTIONS = {"websocket.send"}


def _validate_action_node(node: StepNode, where: str, errors: List[str], warnings: List[str]) -> None:
    action = node.action or ""
    definition = CATALOG.get(action)
    schema = _schema_for(action)
    if not definition and not schema:
        suggestions = difflib.get_close_matches(action, list(CATALOG.keys()), n=3, cutoff=0.6)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        errors.append(f"{where}: unknown action '{action}'.{hint}")
        return
    params = _clean_params(action, node.params)
    if definition:
        for pname, pdef in definition.get("parameters", {}).items():
            if pdef.get("required") and pname not in params:
                errors.append(f"{where}: '{action}' is missing required parameter '{pname}'")
        for group in definition.get("_one_of", []):
            if not any(p in params for p in group):
                errors.append(
                    f"{where}: '{action}' needs one of: {', '.join(group)}"
                )
    if schema and action not in _FREEFORM_PARAM_ACTIONS:
        known = set(schema.get("required", [])) | set(schema.get("optional", []))
        if definition:
            known |= set(definition.get("parameters", {}).keys())
        for pname in params:
            if known and pname not in known:
                warnings.append(f"{where}: '{action}' has unrecognized parameter '{pname}'")


def _walk_nodes(nodes: List[StepNode], prefix: str, errors: List[str], warnings: List[str]) -> None:
    for i, node in enumerate(nodes, start=1):
        where = f"{prefix}step {i}"
        if node.kind == "action":
            _validate_action_node(node, where, errors, warnings)
        elif node.kind == "shared":
            if not (node.name or "").strip():
                errors.append(f"{where}: shared step reference has no name")
        elif node.kind == "for_each":
            if node.items in (None, "", []):
                errors.append(f"{where}: for_each loop has no items")
            if not node.steps:
                errors.append(f"{where}: for_each loop has no steps")
            _walk_nodes(node.steps, f"{where} → ", errors, warnings)
        elif node.kind == "while":
            if not (node.expression or "").strip():
                errors.append(f"{where}: while loop has no condition")
            if not node.steps:
                errors.append(f"{where}: while loop has no steps")
            _walk_nodes(node.steps, f"{where} → ", errors, warnings)
        elif node.kind == "condition":
            if not (node.expression or "").strip():
                errors.append(f"{where}: condition has no expression")
            if not node.then_steps:
                errors.append(f"{where}: condition has no 'then' steps")
            _walk_nodes(node.then_steps, f"{where} then → ", errors, warnings)
            _walk_nodes(node.else_steps, f"{where} else → ", errors, warnings)
        elif node.kind == "try":
            if not node.steps:
                errors.append(f"{where}: try block has no steps")
            _walk_nodes(node.steps, f"{where} try → ", errors, warnings)
            _walk_nodes(node.except_steps, f"{where} except → ", errors, warnings)
            _walk_nodes(node.finally_steps, f"{where} finally → ", errors, warnings)


def validate_case(model: CaseModel) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    if not model.name.strip():
        errors.append("Case name is required")

    if model.case_type == "var":
        if not any(r.key.strip() for r in model.variables):
            errors.append("Var: case needs at least one key/value pair")
        seen = set()
        for row in model.variables:
            key = row.key.strip()
            if key and key in seen:
                errors.append(f"Duplicate variable key '{key}'")
            seen.add(key)
    else:
        if not model.steps:
            errors.append("Add at least one step")
        _walk_nodes(model.steps, "", errors, warnings)

    body = ""
    if not errors:
        try:
            body = serialize_case_body(model)
        except ValueError as exc:
            errors.append(str(exc))

    # Round-trip: parse the generated body with the exact functions the
    # runner uses, to guarantee TestRail content will execute.
    if body and not errors and model.case_type != "var":
        try:
            fixed = fix_step_list_indent(body)
            parsed = parse_yaml_lenient(fixed)
            steps = parsed.get("steps") if isinstance(parsed, dict) else parsed
            if not isinstance(steps, list) or not steps:
                errors.append("Generated body did not parse into a steps list — please report this")
        except Exception as exc:  # parser raises plain Exceptions on bad YAML
            errors.append(f"Generated body failed runner parsing: {exc}")
    elif body and not errors and model.case_type == "var":
        try:
            parsed = yaml.safe_load(body)
            if not isinstance(parsed, dict):
                errors.append("Var: body did not parse as key/value pairs")
        except yaml.YAMLError as exc:
            errors.append(f"Var: body is not valid YAML: {exc}")

    return {"valid": not errors, "errors": errors, "warnings": warnings, "body": body}


# --------------------------------------------------------------------------- #
# Parsing — existing TestRail case → model (for editing)                       #
# --------------------------------------------------------------------------- #

_CONTROL_KEYS = ("for_each", "while", "condition", "try")


def _dict_to_node(step: Dict[str, Any]) -> StepNode:
    if "shared_step" in step:
        return StepNode(kind="shared", name=str(step["shared_step"]))

    if "for_each" in step:
        return StepNode(
            kind="for_each",
            items=step.get("for_each"),
            loop_var=step.get("loop_var"),
            steps=[_dict_to_node(s) for s in step.get("steps", []) if isinstance(s, dict)],
        )
    if "while" in step:
        return StepNode(
            kind="while",
            expression=str(step.get("while", "")),
            loop_limit=step.get("loop_limit"),
            steps=[_dict_to_node(s) for s in step.get("steps", []) if isinstance(s, dict)],
        )
    if "condition" in step or "if" in step:
        return StepNode(
            kind="condition",
            expression=str(step.get("condition", step.get("if", ""))),
            then_steps=[_dict_to_node(s) for s in step.get("then", []) if isinstance(s, dict)],
            else_steps=[_dict_to_node(s) for s in step.get("else", []) if isinstance(s, dict)],
        )
    if "try" in step:
        return StepNode(
            kind="try",
            steps=[_dict_to_node(s) for s in (step.get("try") or []) if isinstance(s, dict)],
            except_steps=[_dict_to_node(s) for s in (step.get("except") or []) if isinstance(s, dict)],
            finally_steps=[_dict_to_node(s) for s in (step.get("finally") or []) if isinstance(s, dict)],
        )

    # action-key format: {"action": "api.get", "url": ...}
    if "action" in step and isinstance(step["action"], str):
        params = {k: v for k, v in step.items() if k != "action"}
        return StepNode(kind="action", action=step["action"], params=params)

    # dot-notation format: {"api.get": {"url": ...}}
    if len(step) == 1:
        key, value = next(iter(step.items()))
        if isinstance(key, str) and "." in key:
            params = value if isinstance(value, dict) else ({} if value in (None, {}) else {"value": value})
            return StepNode(kind="action", action=key, params=params)

    # Anything we can't map cleanly → raw YAML node (still round-trips)
    return StepNode(
        kind="raw",
        yaml_text="- " + yaml.safe_dump(step, default_flow_style=True, width=100000).strip(),
    )


def parse_case_to_model(case: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a TestRail case dict to a builder model (best effort)."""
    title = case.get("title", "") or ""
    role = "feature"
    name = title
    for prefix, r in _ROLE_BY_PREFIX.items():
        if title.startswith(prefix):
            role = r
            name = title[len(prefix):].strip()
            break

    text = strip_html_to_text(str(case.get("custom_preconds") or ""))
    model: Dict[str, Any] = {
        "case_type": role,
        "name": name,
        "variables": [],
        "data_rows": None,
        "steps": [],
    }
    notes: List[str] = []

    if role == "var":
        try:
            parsed = yaml.safe_load(text) if text else {}
        except yaml.YAMLError:
            parsed = None
        if isinstance(parsed, dict):
            model["variables"] = [{"key": str(k), "value": v} for k, v in parsed.items()]
        else:
            for line in text.splitlines():
                line = line.strip()
                if ":" in line and not line.startswith(("#", "-")):
                    k, _, v = line.partition(":")
                    if k.strip():
                        model["variables"].append({"key": k.strip(), "value": v.strip()})
        return {"model": model, "notes": notes, "raw_body": text}

    if role == "test":
        notes.append("Test: pointer cases route to local YAML files and are not editable here.")
        return {"model": model, "notes": notes, "raw_body": text}

    if text:
        try:
            fixed = fix_step_list_indent(text)
            parsed = parse_yaml_lenient(fixed)
        except Exception as exc:
            notes.append(f"Could not parse existing body ({exc}); loaded as a single raw step.")
            model["steps"] = [{"kind": "raw", "yaml_text": text}]
            return {"model": model, "notes": notes, "raw_body": text}

        steps: List[Any] = []
        if isinstance(parsed, list):
            steps = parsed
        elif isinstance(parsed, dict):
            variables = parsed.get("variables")
            if isinstance(variables, dict):
                model["variables"] = [{"key": str(k), "value": v} for k, v in variables.items()]
            data = parsed.get("data")
            if isinstance(data, list):
                model["data_rows"] = yaml.safe_dump(data, default_flow_style=False, width=100000).rstrip()
            if isinstance(parsed.get("steps"), list):
                steps = parsed["steps"]
            elif "action" in parsed:
                steps = [parsed]
        nodes = [_dict_to_node(s) for s in steps if isinstance(s, dict)]
        model["steps"] = [n.model_dump() for n in nodes]
        if any(n.kind == "raw" for n in nodes):
            notes.append("Some steps could not be mapped to forms and were loaded as raw YAML steps.")

        if not model["steps"] and text.strip():
            # Legacy-format body (e.g. old pipe-delimited syntax) — surface it
            # as a raw step so publishing never silently wipes the case.
            notes.append(
                "This case body is not in Easy BDD dot-notation (legacy format?) — "
                "loaded as a raw step. Use the BDD migrator to convert legacy cases."
            )
            model["steps"] = [{"kind": "raw", "yaml_text": text}]

    return {"model": model, "notes": notes, "raw_body": text}


# --------------------------------------------------------------------------- #
# TestRail client                                                               #
# --------------------------------------------------------------------------- #

_tr_service: Optional[TestRailService] = None


def _tr() -> TestRailService:
    global _tr_service
    if _tr_service is None:
        try:
            _tr_service = TestRailService()
        except TestRailError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    return _tr_service


def _tr_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except TestRailError as exc:
        raise HTTPException(status_code=502, detail=f"TestRail error: {exc}")


def _case_link(case_id: int) -> str:
    base = os.getenv("TESTRAIL_URL", "").rstrip("/")
    return f"{base}/index.php?/cases/view/{case_id}" if base else ""


def _run_link(run_id: int) -> str:
    base = os.getenv("TESTRAIL_URL", "").rstrip("/")
    return f"{base}/index.php?/runs/view/{run_id}" if base else ""


# --------------------------------------------------------------------------- #
# Routes                                                                        #
# --------------------------------------------------------------------------- #

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "testrail_builder.html")


@app.get("/api/catalog")
async def get_catalog():
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for action_id, definition in sorted(CATALOG.items()):
        categories.setdefault(definition["category"], []).append(
            {"id": action_id, **definition}
        )
    return {"categories": categories, "case_types": CASE_PREFIXES}


@app.get("/api/testrail/status")
async def testrail_status():
    url = os.getenv("TESTRAIL_URL", "")
    user = os.getenv("TESTRAIL_USERNAME", "")
    configured = bool(url and user and os.getenv("TESTRAIL_API_KEY"))
    return {"configured": configured, "url": url, "username": user}


@app.get("/api/testrail/projects")
async def testrail_projects():
    projects = _tr_call(_tr().get_projects)
    return [
        {"id": p["id"], "name": p["name"], "suite_mode": p.get("suite_mode")}
        for p in projects
        if not p.get("is_completed")
    ]


@app.get("/api/testrail/suites")
async def testrail_suites(project_id: int = Query(...)):
    suites = _tr_call(_tr().get_suites, project_id)
    return [{"id": s["id"], "name": s["name"]} for s in suites]


@app.get("/api/testrail/sections")
async def testrail_sections(project_id: int = Query(...), suite_id: Optional[int] = Query(None)):
    sections = _tr_call(_tr().get_sections, project_id, suite_id)
    return [
        {"id": s["id"], "name": s["name"], "parent_id": s.get("parent_id"), "depth": s.get("depth", 0)}
        for s in sections
    ]


@app.get("/api/testrail/cases")
async def testrail_cases(project_id: int = Query(...), suite_id: Optional[int] = Query(None)):
    cases = _tr_call(_tr().get_cases, project_id, suite_id)
    out = []
    for c in cases:
        title = c.get("title", "")
        role = "other"
        for prefix, r in _ROLE_BY_PREFIX.items():
            if title.startswith(prefix):
                role = r
                break
        out.append(
            {"id": c["id"], "title": title, "section_id": c.get("section_id"), "role": role}
        )
    return out


@app.get("/api/testrail/case/{case_id}")
async def testrail_case(case_id: int):
    case = _tr_call(_tr().get_case, case_id)
    result = parse_case_to_model(case)
    result["case_id"] = case_id
    result["section_id"] = case.get("section_id")
    result["link"] = _case_link(case_id)
    return result


@app.post("/api/preview")
async def preview(model: CaseModel):
    try:
        body = serialize_case_body(model)
    except (ValueError, yaml.YAMLError) as exc:
        return {"title": "", "body": "", "error": str(exc)}
    try:
        title = case_title(model)
    except ValueError as exc:
        return {"title": "", "body": body, "error": str(exc)}
    return {"title": title, "body": body, "error": None}


@app.post("/api/validate")
async def validate(model: CaseModel):
    return validate_case(model)


@app.post("/api/testrail/section")
async def create_section(req: SectionRequest):
    payload: Dict[str, Any] = {"name": req.name}
    if req.suite_id:
        payload["suite_id"] = req.suite_id
    if req.parent_id:
        payload["parent_id"] = req.parent_id
    section = _tr_call(_tr().add_section, req.project_id, **payload)
    return {"id": section["id"], "name": section["name"]}


@app.post("/api/testrail/publish")
async def publish(req: PublishRequest):
    result = validate_case(req.model)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"]})

    title = case_title(req.model)
    body = result["body"]
    tr = _tr()

    if req.case_id:
        case = _tr_call(tr.update_case, req.case_id, title=title, custom_preconds=body)
        case_id = case.get("id", req.case_id) if isinstance(case, dict) else req.case_id
        action = "updated"
    else:
        if not req.section_id:
            raise HTTPException(status_code=422, detail="section_id is required to create a case")
        # custom_automation_status is required in some projects but not all —
        # retry without it if the project rejects it.
        try:
            case = tr.add_case(
                req.section_id, title=title, custom_preconds=body, custom_automation_status=5
            )
        except TestRailError:
            case = _tr_call(tr.add_case, req.section_id, title=title, custom_preconds=body)
        if not isinstance(case, dict) or "id" not in case:
            raise HTTPException(status_code=502, detail=f"add_case returned unexpected response: {case!r}")
        case_id = case["id"]
        action = "created"

    return {
        "case_id": case_id,
        "title": title,
        "action": action,
        "link": _case_link(case_id),
        "warnings": result["warnings"],
    }


@app.post("/api/testrail/run")
async def create_run(req: RunRequest):
    if not req.case_ids:
        raise HTTPException(status_code=422, detail="Select at least one case for the run")
    prefix = os.getenv("TESTRAIL_RUN_PREFIX", "EASY_BDD:")
    name = req.name.strip()
    if not name.startswith(prefix):
        name = f"{prefix} {name}"
    payload: Dict[str, Any] = {
        "name": name,
        "include_all": False,
        "case_ids": req.case_ids,
    }
    if req.suite_id:
        payload["suite_id"] = req.suite_id
    if req.description:
        payload["description"] = req.description
    run = _tr_call(_tr().add_run, req.project_id, **payload)
    return {"run_id": run["id"], "name": run["name"], "link": _run_link(run["id"])}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("BUILDER_PORT", "8091"))
    uvicorn.run(app, host="0.0.0.0", port=port)
