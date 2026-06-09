"""
Previous BDD Framework (mybdd / pytest-bdd) → Easy BDD migrator.

Converts pipe-delimited keyword steps from the custom mybdd framework into
Easy BDD YAML test files and shared_steps.yaml entries.

Input can be:
  - A full .feature file (Gherkin shell around pipe-delimited steps)
  - A raw step block (just the pipe-delimited lines — e.g. TestRail custom_preconds)
  - A JSON export dict with Given/Shared/Feature sections

Key syntax being migrated
─────────────────────────
  browser | {"command": "open", "param": "url"} |   → browser.navigate
  sleep | 15 |                                       → browser.wait
  telnet | {"host":"h","command":"cmd"} |            → telnet.send
  ssh | {"host":"h","command":"cmd"} |               → command.ssh
  serial | {"port":"COM3","command":"cmd"} |         → serial.send
  webservice | url | method | path | data |          → api.request
  device | url | path | method | params | data |     → api.request
  function | {"name":"requests",...} | data |        → api.request
  function | {"name":"exec","string":"..."} | |      → eval.exec
  function | {"name":"eval","expression":"..."} | |  → eval.run
  function | {"name":"sleep","sec":N} | |            → browser.wait
  function | {"name":"assert",...} | value |         → test.assert
  | value | in response                              → test.assert (contains)
  | value | not in response                         → test.assert (not contains)
  | path | in json_response                         → test.assert (JSON path)
  | path == val | in json_response                  → test.assert (JSON equality)
  response_code | 200 |                             → test.assert_response
  Shared: name                                      → shared_step: name
  $variable                                         → ${variable}
  gv.log[-1]['response_txt']  (YAML param context)  → ${last_response}
  gv.log[-1]['response']      (YAML param context)  → ${last_response}
  gv.log[-1]['response_dict'] (YAML param context)  → ${last_response_dict}
  gv.log[-1]['response_code'] (YAML param context)  → ${last_response_code}
  gv.message                  (YAML param context)  → ${last_eval}
  gv.log[-1]['response_txt']  (Python code context) → str(last_response)
  gv.log[-1]['response']      (Python code context) → str(last_response)
  gv.log[-1]['response_dict'] (Python code context) → last_response_dict
  gv.tests['variables']['k']  (Python code context) → kept as-is (valid Easy BDD runtime)
  gv.tests['variables']['k']  (YAML param context)  → ${k}
  gv.tests['variables']['k']=v (Python assignment)  → eval.exec: code + store_as: k
  pure boolean Python expression                    → test.assert: expression
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def _int_or_var(value, default=0):
    """Return int if value is numeric, otherwise return the var-substituted string."""
    s = str(value).strip()
    if not s:
        return default
    try:
        return int(s)
    except ValueError:
        return _sub_vars(s)


# ────────────────────────────────────────────────────────────────────────────
# Variable translation
# ────────────────────────────────────────────────────────────────────────────

def _sub_vars(text: str) -> str:
    """
    Translate mybdd variable syntax to Easy BDD ${...} syntax.

    Use this for YAML *parameter value* strings (URLs, selectors, command args,
    assertion literals).  Do NOT call this on Python code bodies — use
    _translate_code() instead.
    """
    if not isinstance(text, str):
        return text

    # gv.log indexed access — response text
    text = re.sub(r"gv\.log\[-1\]\['response_txt'\]",   "${last_response}",      text)
    text = re.sub(r"gv\.log\[-1\]\['response'\]",        "${last_response}",      text)
    text = re.sub(r"gv\.log\[-2\]\['response_txt'\]",   "${prev_response}",      text)
    text = re.sub(r"gv\.log\[-2\]\['response'\]",        "${prev_response}",      text)
    text = re.sub(r"gv\.log\[(-?\d+)\]\['response(?:_txt)?'\]", r"${response_\1}", text)

    # gv.log indexed access — response dict
    text = re.sub(r"gv\.log\[-1\]\['response_dict'\]",  "${last_response_dict}", text)
    text = re.sub(r"gv\.log\[-2\]\['response_dict'\]",  "${prev_response_dict}", text)
    text = re.sub(r"gv\.log\[(-?\d+)\]\['response_dict'\]", r"${response_dict_\1}", text)

    # gv.log — response code / status
    text = re.sub(r"gv\.log\[-1\]\['(?:response_code|status_code)'\]",  "${last_response_code}",    text)
    text = re.sub(r"gv\.log\[-1\]\['(?:response_headers?|headers?)'\]", "${last_response_headers}", text)

    # gv.tests['variables']['key'] access (single-quoted and double-quoted)
    text = re.sub(r"gv\.tests\['variables'\]\['(\w+)'\]", r"${\1}", text)
    text = re.sub(r'gv\.tests\["variables"\]\["(\w+)"\]', r"${\1}", text)

    # gv.message — the last eval/message result
    text = re.sub(r"\bgv\.message\b", "${last_eval}", text)

    # <$varname$> or <${varname}$> or <${varname}> — Gherkin Scenario Outline params
    text = re.sub(r"<\$\{([A-Za-z_][A-Za-z0-9_]*)\}\$?>", r"${\1}", text)
    text = re.sub(r"<\$([A-Za-z_][A-Za-z0-9_]*)\$>",       r"${\1}", text)

    # $variable → ${variable}  (dollar-sign variables, not already in ${...})
    def dollar_sub(m):
        return "${" + m.group(1) + "}"
    text = re.sub(r"\$(?!\{)([A-Za-z_][A-Za-z0-9_]*)", dollar_sub, text)

    return text


# ── patterns applied to Python code strings (eval.exec, test.assert, etc.) ──
# Maps (pattern, replacement) where replacement can be a string or callable.
_CODE_PATTERNS: List[Tuple[str, Any]] = [
    # gv.log response text  (old framework used 'response'; Easy BDD uses 'response_txt'
    # but also exposes last_response as a bare name)
    (r"gv\.log\[-1\]\['response_txt'\]",    "str(last_response)"),
    (r"gv\.log\[-1\]\['response'\]",         "str(last_response)"),
    (r"gv\.log\[-2\]\['response_txt'\]",    "str(prev_response)"),
    (r"gv\.log\[-2\]\['response'\]",         "str(prev_response)"),
    # gv.log response dict
    (r"gv\.log\[-1\]\['response_dict'\]",   "last_response_dict"),
    (r"gv\.log\[-2\]\['response_dict'\]",   "prev_response_dict"),
    # gv.log response code / headers
    (r"gv\.log\[-1\]\['(?:response_code|status_code)'\]",  "last_response_code"),
    (r"gv\.log\[-1\]\['(?:response_headers?|headers?)'\]", "last_response_headers"),
    # Numeric-indexed log entries
    (r"gv\.log\[(-?\d+)\]\['response(?:_txt)?'\]",
        lambda m: "str(last_response)" if m.group(1) in ("-1",)
                  else f"str(log_response_{m.group(1).lstrip('-')})"),
    (r"gv\.log\[(-?\d+)\]\['response_dict'\]",
        lambda m: "last_response_dict" if m.group(1) in ("-1",)
                  else f"log_response_dict_{m.group(1).lstrip('-')}"),
    # gv.tests['variables']['key'] — in Python code context keep the gv API;
    # READS: leave as-is so the code is valid Easy BDD Python.
    # (The YAML-string variant is handled by _sub_vars.)
    # gv.message is a valid Easy BDD runtime global — leave it as-is.
]


def _translate_code(code: str) -> str:
    """
    Translate Python code strings from mybdd runtime API to Easy BDD runtime API.

    Called for eval.exec code bodies, eval.run expressions, and test.assert
    expression strings.  Unlike _sub_vars(), this does NOT convert
    gv.tests['variables'][...] → ${...} because ${...} is not valid Python;
    it keeps gv.* references that are valid in the Easy BDD execution context
    and only normalises patterns that were renamed between frameworks.
    """
    if not isinstance(code, str):
        return code

    for pattern, replacement in _CODE_PATTERNS:
        if callable(replacement):
            code = re.sub(pattern, replacement, code)
        else:
            code = re.sub(pattern, replacement, code)

    return code


def _smart_eval_step(code: str) -> Dict:
    """
    Convert a Python code string to the most appropriate Easy BDD step dict.

    Rules (in priority order):
      1. Pure variable assignment  gv.tests['variables']['key'] = <expr>
         → eval.exec with store_as so the intent is visible.
      2. Pure boolean / comparison expression (no assignment, no side-effect call)
         → test.assert so the failure produces a clear message.
      3. Everything else → eval.exec.
    """
    code = _translate_code(code.strip())

    # Rule 1 — variable assignment
    m = re.match(
        r"^gv\.tests\['variables'\]\['(\w+)'\]\s*=\s*(.+)$",
        code, re.DOTALL
    )
    if m:
        return {"action": "eval.exec", "code": code, "store_as": m.group(1)}

    # Rule 2 — pure boolean expression (no assignment, no function call with side effects)
    # Heuristic: if the code contains a comparison / containment operator and no '='
    # (but allow '==' and '!=') then treat as assertion.
    _no_assign = not re.search(r"(?<![=!<>])=(?!=)", code)  # lone = but not == != <= >=
    _is_bool   = bool(re.search(
        r"\bin\b|\bnot\s+in\b|\b(?:is|is\s+not)\b|==|!=|<=|>=|<(?!=)|>(?!=)|"
        r"\bre\.(?:search|match|fullmatch)\b",
        code
    ))
    if _no_assign and _is_bool and "(" not in code.split("in")[0]:
        # Extra guard: don't promote if the expression contains a function call
        # before the first boolean keyword (e.g. `some_fn() in result` is fine,
        # but `fetch_data()` alone is not a boolean).
        return {"action": "test.assert", "expression": code}

    return {"action": "eval.exec", "code": code}


def _strip_dollar(name: str) -> str:
    """Strip leading $ from a variable name for YAML keys."""
    return name.lstrip("$")


# ────────────────────────────────────────────────────────────────────────────
# JSON helper — safe parse of the JSON-ish params used in the old framework
# ────────────────────────────────────────────────────────────────────────────

def _parse_json(text: str) -> Optional[Dict]:
    """Try to parse a JSON/Python-dict string; return None on failure."""
    text = text.strip()
    if not text or text in ("{}", "{}"):
        return {}
    for attempt in (text, text.replace("'", '"')):
        try:
            return json.loads(attempt)
        except Exception:
            pass
    # Last resort: ast.literal_eval (handles Python dict literals safely)
    try:
        import ast
        result = ast.literal_eval(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return None


def _clean_var_key(k: str) -> str:
    """Strip surrounding quotes and leading $ from a variable key."""
    k = k.strip().strip("\"'").lstrip("$")
    return k


def _clean_var_value(v: str) -> str:
    """Strip surrounding quotes and trailing commas from a variable value."""
    v = v.strip().rstrip(",").strip("\"'"
                                    )
    return _sub_vars(v)


# ────────────────────────────────────────────────────────────────────────────
# Browser command mapping
# ────────────────────────────────────────────────────────────────────────────

def _map_browser(cmd_dict: Dict) -> Dict:
    cmd = cmd_dict.get("command", "").lower()
    # Old mybdd format uses both "param" (generic first arg) and explicit keys like "url".
    # Prefer explicit keys; fall back to "param" as the catch-all positional argument.
    param   = _sub_vars(str(cmd_dict.get("param",   cmd_dict.get("url", ""))))
    target  = _sub_vars(str(cmd_dict.get("target",  cmd_dict.get("selector", ""))))
    text    = _sub_vars(str(cmd_dict.get("text",    "")))
    value   = _sub_vars(str(cmd_dict.get("value",   "")))
    key     = cmd_dict.get("key", "")
    name    = cmd_dict.get("name", "")
    timeout = cmd_dict.get("timeout", "")

    step: Dict[str, Any] = {}

    if cmd in ("open",):
        step = {"action": "browser.open", "url": param or target}
    elif cmd in ("goto", "navigate"):
        step = {"action": "browser.navigate", "url": param or target}
    elif cmd in ("close",):
        step = {"action": "browser.close"}
    elif cmd in ("refresh",):
        step = {"action": "browser.refresh"}
    elif cmd in ("type", "fill", "input"):
        s = {"action": "browser.fill", "value": text or value}
        if target:
            s["selector"] = target
        step = s
    elif cmd in ("click",):
        s = {"action": "browser.click"}
        if target:
            s["selector"] = target
        elif text:
            s["text"] = text
        step = s
    elif cmd in ("press",):
        step = {"action": "browser.press_key", "key": key}
        if target:
            step["selector"] = target
    elif cmd in ("gettext", "get_text", "innertext"):
        s = {"action": "browser.get_text", "store_as": name or "last_text"}
        if target:
            s["selector"] = target
        step = s
    elif cmd in ("screenshot", "capture"):
        step = {"action": "browser.screenshot", "name": name or param or "screenshot"}
    elif cmd in ("wait", "waitfor", "wait_for_element"):
        s = {"action": "browser.wait_for_element"}
        if target:
            s["selector"] = target
        if timeout:
            s["timeout"] = timeout
        step = s
    elif cmd in ("wait_for_text", "waitfortext"):
        step = {"action": "browser.wait_for_text", "text": text or param}
    elif cmd in ("evaluate", "eval", "execute_script"):
        step = {"action": "eval.exec", "code": param or text}
    elif cmd in ("select",):
        s = {"action": "browser.select", "value": value or text}
        if target:
            s["selector"] = target
        step = s
    elif cmd in ("hover",):
        step = {"action": "browser.hover", "selector": target or param}
    elif cmd in ("check", "uncheck"):
        step = {"action": f"browser.{cmd}", "selector": target or param}
    elif cmd in ("scroll",):
        step = {"action": "browser.scroll", "selector": target or param}
    elif cmd in ("validate_checkbox_enabled", "assert_checked"):
        s = {"action": "browser.assert_checked"}
        if param or target:
            s["selector"] = param or target
        step = s
    elif cmd in ("validate_checkbox_disabled", "assert_not_checked", "assert_unchecked"):
        s = {"action": "browser.assert_not_checked"}
        if param or target:
            s["selector"] = param or target
        step = s
    elif cmd in ("click_by_role",):
        role = cmd_dict.get("role", "")
        name_attr = cmd_dict.get("name", "")
        exact = cmd_dict.get("exact", True)
        s = {"action": "browser.click", "role": role}
        if name_attr:
            s["name"] = name_attr
        if exact is not True:
            s["exact"] = exact
        step = s
    elif cmd in ("containstext", "contains_text", "assert_text", "asserttext"):
        s = {"action": "browser.assert_text", "text": cmd_dict.get("text", text)}
        if param or target:
            s["selector"] = param or target
        step = s
    elif cmd in ("gettitle", "get_title", "asserttitle", "assert_title"):
        store = cmd_dict.get("store_as", "page_title")
        step = {"action": "browser.get_title", "store_as": store}
    elif cmd in ("assert_value", "assertvalue"):
        s = {"action": "browser.assert_value", "value": value or text}
        if param or target:
            s["selector"] = param or target
        step = s
    elif cmd in ("waitfornavigation", "wait_for_navigation", "wait_for_load"):
        step = {"action": "browser.wait_for_navigation"}
    elif cmd in ("dragdrop", "drag_drop", "drag_and_drop"):
        step = {"action": "browser.drag_drop", "source": target or param,
                "destination": cmd_dict.get("destination", "")}
    elif cmd in ("setlocalStorage", "set_localstorage", "localstorage"):
        step = {"action": "eval.exec",
                "code": f"localStorage.setItem({cmd_dict.get('key','key')!r}, {cmd_dict.get('value',value)!r})"}
    else:
        # Unmapped command — keep as test.log TODO
        step = {"action": "test.log", "message": f"TODO browser.{cmd}: {json.dumps(cmd_dict)}"}

    return step


# ────────────────────────────────────────────────────────────────────────────
# function | ... | dispatch
# ────────────────────────────────────────────────────────────────────────────

_ASSERT_OP_MAP = {
    "match":        "re.match({expected!r}, str({data})) is not None",
    "not_match":    "re.match({expected!r}, str({data})) is None",
    "eq":           "{data} == {expected!r}",
    "ne":           "{data} != {expected!r}",
    "contains":     "{expected!r} in str({data})",
    "not_contains": "{expected!r} not in str({data})",
    "gt":           "float({data}) > {expected}",
    "lt":           "float({data}) < {expected}",
    "gte":          "float({data}) >= {expected}",
    "lte":          "float({data}) <= {expected}",
}


def _map_function(param_dict: Dict, data_str: str) -> Dict:
    name = param_dict.get("name", "").lower()
    data_str = _sub_vars(data_str.strip())

    if name == "sleep":
        sec = param_dict.get("sec", param_dict.get("seconds", 1))
        return {"action": "browser.wait", "seconds": float(sec)}

    if name in ("exec", "execute"):
        # Use _translate_code (not _sub_vars) — Python code context, not a YAML string value.
        return _smart_eval_step(str(param_dict.get("string", "")))

    if name == "eval":
        # "string" key → exec-style, "expression" key → eval-style
        if "string" in param_dict:
            return _smart_eval_step(str(param_dict["string"]))
        # "expression" → evaluate and optionally store result
        expr  = _translate_code(str(param_dict.get("expression", "")))
        store = param_dict.get("store_as", "eval_result")
        return {"action": "eval.run", "expression": expr, "store_as": store}

    if name == "assert":
        op        = param_dict.get("operator", "eq")
        expected  = param_dict.get("expected", "")
        expr_tmpl = param_dict.get("expression", "@")  # "@" means use data arg

        # Resolve data source — translate code-context patterns in data_str
        data_ref = _translate_code(data_str) if data_str and data_str not in ("{}", "") else "str(last_response)"
        # Replace "@" placeholder
        if expr_tmpl == "@":
            data_val = data_ref
        else:
            data_val = _translate_code(expr_tmpl)

        tmpl = _ASSERT_OP_MAP.get(op, "{data} == {expected!r}")
        try:
            expr = tmpl.format(data=data_val, expected=expected)
        except Exception:
            expr = f"{data_val} matches {expected!r}"

        return {"action": "test.assert", "expression": expr}

    if name in ("requests", "webservice"):
        method  = param_dict.get("method", "get").upper()
        url     = _sub_vars(str(param_dict.get("url", "")))
        path    = _sub_vars(str(param_dict.get("path", param_dict.get("command", ""))))
        full_url = f"{url}{path}" if path else url
        if method == "SEND" or full_url.startswith("wss://") or "${url}" in full_url:
            # WebSocket send
            body_val = _sub_vars(data_str) if data_str and data_str not in ("{}", "") else path
            return {"action": "websocket.send", "url": full_url, "data": body_val, "store_as": "last_response"}
        step: Dict[str, Any] = {"action": "api.request", "method": method, "url": full_url, "store_as": "last_response"}
        if data_str and data_str not in ("{}", ""):
            step["body"] = data_str
        headers = param_dict.get("headers")
        if headers:
            step["headers"] = headers
        return step

    if name == "device":
        method  = param_dict.get("method", "get").upper()
        url     = _sub_vars(str(param_dict.get("url", "")))
        path    = _sub_vars(str(param_dict.get("path", "")))
        step = {"action": "api.request", "method": method, "url": f"{url}{path}", "store_as": "last_response"}
        if data_str and data_str not in ("{}", ""):
            step["body"] = data_str
        return step

    if name == "control4":
        method  = param_dict.get("method", "post").upper()
        path    = _sub_vars(str(param_dict.get("path", "")))
        step = {"action": "api.request", "method": method, "url": "${control4_url}" + path, "store_as": "last_response"}
        if data_str and data_str not in ("{}", ""):
            step["body"] = data_str
        return step

    if name == "telnet":
        return {
            "action":  "telnet.send",
            "host":    _sub_vars(str(param_dict.get("host", ""))),
            "port":    _int_or_var(param_dict.get("port", 23), 23),
            "command": _sub_vars(str(param_dict.get("command", ""))),
        }

    if name == "ssh":
        return {
            "action":   "command.ssh",
            "host":     _sub_vars(str(param_dict.get("host", ""))),
            "username": _sub_vars(str(param_dict.get("user", param_dict.get("username", "")))),
            "password": _sub_vars(str(param_dict.get("password", ""))),
            "command":  _sub_vars(str(param_dict.get("command", ""))),
        }

    if name == "serial":
        return {
            "action":   "serial.send",
            "port":     _sub_vars(str(param_dict.get("port", ""))),
            "baudrate": _int_or_var(param_dict.get("baudrate", 115200), 115200),
            "data":     _sub_vars(str(param_dict.get("command", param_dict.get("data", "")))),
        }

    if name == "jmespath":
        expr = _sub_vars(str(param_dict.get("path", param_dict.get("expression", ""))))
        store = param_dict.get("store_as", "jmespath_result")
        return {"action": "eval.exec",
                "code": f"import jmespath; {store} = jmespath.search({expr!r}, last_response_dict)",
                "store_as": store}

    if name in ("testrail",):
        return {"action": "test.log", "message": f"[testrail] {param_dict.get('cmd', '')} (skipped in migration)"}

    if name == "response_like":
        return {"action": "test.assert", "expression": f"str(last_response).__contains__(str({data_str!r}))"}

    if name == "upload_cloud_firmware":
        bucket   = _sub_vars(str(param_dict.get("aws_bucket", "")))
        dl_dir   = _sub_vars(str(param_dict.get("download_dir", "")))
        regex    = _sub_vars(str(param_dict.get("regex_pattern", "")))
        cf_url   = _sub_vars(str(param_dict.get("cloudfront_url", "")))
        step: Dict = {
            "action": "aws.list_files",
            "bucket_name": bucket,
            "folder_prefix": dl_dir,
            "store_as": "last_response",
        }
        if regex:
            step["filename_pattern"] = regex
        if cf_url:
            step["cloudfront_url"] = cf_url
        return step

    if name == "extract_firmware_version":
        bucket  = _sub_vars(str(param_dict.get("aws_bucket", "")))
        file_url = _sub_vars(str(param_dict.get("aws_file_url", "")))
        return {
            "action": "eval.exec",
            "code": (
                f"# extract_firmware_version from S3 bucket '{bucket}'\n"
                f"# file: {file_url}\n"
                f"# result → firmware_version variable"
            ),
        }

    # Fallback
    return {"action": "test.log", "message": f"TODO function.{name}: {json.dumps(param_dict)[:120]}"}


# ────────────────────────────────────────────────────────────────────────────
# Assertion step  |lookup|mode obj
# ────────────────────────────────────────────────────────────────────────────

def _map_assertion(lookup: str, mode: str, obj: str) -> Dict:
    """Convert | lookup | in/not in/like response / json_response."""
    lookup = lookup.strip()
    mode   = mode.strip().lower()
    obj    = obj.strip().lower()
    negated = "not" in mode
    like    = "like" in mode
    is_json = "json" in obj

    # Translate $vars in lookup
    lookup_subst = _sub_vars(lookup)

    if is_json:
        if " == " in lookup:
            path_part, expected_str = lookup_subst.split(" == ", 1)
            path_part    = path_part.strip()
            expected_str = expected_str.strip()
            if negated:
                expr = f"last_response_dict.get({path_part!r}) != {expected_str}"
            else:
                expr = f"last_response_dict.get({path_part!r}) == {expected_str}"
        else:
            if negated:
                expr = f"{lookup_subst!r} not in last_response_dict"
            else:
                expr = f"{lookup_subst!r} in last_response_dict"
    elif like:
        expr = f"{lookup_subst!r} in str(last_response)"
        if negated:
            expr = f"{lookup_subst!r} not in str(last_response)"
    else:
        if negated:
            expr = f"{lookup_subst!r} not in str(last_response)"
        else:
            expr = f"{lookup_subst!r} in str(last_response)"

    return {"action": "test.assert", "expression": expr}


# ────────────────────────────────────────────────────────────────────────────
# Line-level parser
# ────────────────────────────────────────────────────────────────────────────

def _parse_step_line(line: str) -> Optional[Dict]:
    """
    Convert a single mybdd step line to an Easy BDD step dict.
    Returns None for blank / comment / separator lines.
    """
    original = line
    line = line.strip()

    # Skip blanks, the "---" separator, "None", and inline comments
    if not line or line == "---" or line.lower() == "none":
        return None
    if line.startswith("#"):
        return None  # inline comment — skip entirely

    # Strip $execute and / $execute or prefix — always execute in Easy BDD
    line = re.sub(r"^\$execute\s+(and|or)\s+", "", line, flags=re.I)

    # ── Shared: reference ──────────────────────────────────────────────────
    if line.startswith("Shared:"):
        shared_name = line[len("Shared:"):].strip()
        slug = re.sub(r"[^A-Za-z0-9_]+", "_", shared_name).strip("_")
        return {"shared_step": slug}

    # ── Assertion:  | lookup | mode obj ───────────────────────────────────
    if re.match(r"^\s*\|", line):
        # Strip leading/trailing pipes and split
        inner = line.strip().strip("|")
        parts = [p.strip() for p in inner.split("|")]
        if len(parts) >= 2:
            lookup = parts[0]
            rest   = " ".join(parts[1:]).strip()
            # rest is like "in response" / "not in response" / "like response" / "in json_response"
            m = re.match(r"(not\s+in|in|like)\s+(response|json_response|json response)", rest, re.I)
            if m:
                return _map_assertion(lookup, m.group(1), m.group(2))
        return {"action": "test.log", "message": f"TODO assertion: {original.strip()[:120]}"}

    # ── response_code | N | ───────────────────────────────────────────────
    m = re.match(r"^response_code\s*\|\s*(\S+)\s*\|", line, re.I)
    if m:
        code = m.group(1)
        return {"action": "test.assert", "expression": f"last_response_code == {code}",
                "message": f"Expected HTTP {code}"}

    # ── sleep | N | ──────────────────────────────────────────────────────
    m = re.match(r"^sleep\s*\|\s*(\S+)\s*\|", line, re.I)
    if m:
        raw = _sub_vars(m.group(1))
        try:
            sec = float(raw)
        except ValueError:
            sec = raw
        return {"action": "browser.wait", "seconds": sec}

    # ── browser | {...} | ─────────────────────────────────────────────────
    m = re.match(r"^browser\s*\|\s*(\{.+\})\s*\|", line, re.I)
    if m:
        cmd_dict = _parse_json(m.group(1))
        if cmd_dict is None:
            return {"action": "test.log", "message": f"TODO browser (parse error): {line[:120]}"}
        return _map_browser(cmd_dict)

    # ── telnet | {...} | ──────────────────────────────────────────────────
    m = re.match(r"^telnet\s*\|\s*(\{.+\})\s*\|", line, re.I)
    if m:
        d = _parse_json(m.group(1)) or {}
        return {
            "action":   "telnet.send",
            "host":     _sub_vars(str(d.get("host", ""))),
            "port":     _int_or_var(d.get("port", 23), 23),
            "command":  _sub_vars(str(d.get("command", ""))),
        }

    # ── ssh | {...} | ─────────────────────────────────────────────────────
    m = re.match(r"^ssh\s*\|\s*(\{.+\})\s*\|", line, re.I)
    if m:
        d = _parse_json(m.group(1)) or {}
        return {
            "action":   "command.ssh",
            "host":     _sub_vars(str(d.get("host", ""))),
            "username": _sub_vars(str(d.get("user", d.get("username", "")))),
            "password": _sub_vars(str(d.get("password", ""))),
            "command":  _sub_vars(str(d.get("command", ""))),
        }

    # ── serial | {...} | ──────────────────────────────────────────────────
    m = re.match(r"^serial\s*\|\s*(\{.+\})\s*\|", line, re.I)
    if m:
        d = _parse_json(m.group(1)) or {}
        return {
            "action":   "serial.send",
            "port":     _sub_vars(str(d.get("port", ""))),
            "baudrate": _int_or_var(d.get("baudrate", 115200), 115200),
            "data":     _sub_vars(str(d.get("command", d.get("data", "")))),
        }

    # ── webservice | url | method | path | data | ─────────────────────────
    m = re.match(r"^webservice\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|", line, re.I)
    if m:
        url    = _sub_vars(m.group(1).strip())
        method = m.group(2).strip().upper()
        path   = _sub_vars(m.group(3).strip())
        data   = m.group(4).strip()
        full_url = f"{url}{path}"
        if method == "SEND" or url.startswith("wss://") or url.startswith("${url}"):
            body_val = _sub_vars(data) if data and data not in ("{}", "") else path
            return {"action": "websocket.send", "url": full_url if not method == "SEND" else url,
                    "data": body_val, "store_as": "last_response"}
        step: Dict[str, Any] = {"action": "api.request", "method": method, "url": full_url, "store_as": "last_response"}
        if data and data not in ("{}", ""):
            step["body"] = _sub_vars(data)
        return step

    # ── device | url | path | method | params | data | ────────────────────
    m = re.match(r"^device\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|\s*([^|]*)\|", line, re.I)
    if m:
        url    = _sub_vars(m.group(1).strip())
        path   = _sub_vars(m.group(2).strip())
        method = m.group(3).strip().upper()
        data   = m.group(5).strip()
        step = {"action": "api.request", "method": method, "url": f"{url}{path}", "store_as": "last_response"}
        if data and data not in ("{}", ""):
            step["body"] = _sub_vars(data)
        return step

    # ── device_core | {...} | ─────────────────────────────────────────────
    m = re.match(r"^device_core\s*\|\s*(\{.+\})\s*\|", line, re.I)
    if m:
        d = _parse_json(m.group(1)) or {}
        method = d.get("type", "get").upper()
        path   = _sub_vars(str(d.get("path", "")))
        data   = d.get("data", {})
        step = {"action": "api.request", "method": method, "url": "${base_url}" + path, "store_as": "last_response"}
        if data:
            step["body"] = _sub_vars(str(data))
        return step

    # ── control4 | {path} | data | ────────────────────────────────────────
    m = re.match(r"^control4\s*\|(.+)\|(.+)\|", line, re.I)
    if m:
        path_raw = m.group(1).strip()
        data     = m.group(2).strip()
        path_d   = _parse_json(path_raw) or {}
        method   = path_d.get("method", "post").upper()
        path     = _sub_vars(str(path_d.get("path", "")))
        step = {"action": "api.request", "method": method, "url": "${control4_url}" + path, "store_as": "last_response"}
        if data and data not in ("{}", ""):
            step["body"] = _sub_vars(data)
        return step

    # ── luma_ovrc / device_luma | method | path | data | ─────────────────
    m = re.match(r"^(?:luma_ovrc|device_luma|ovrc)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|", line, re.I)
    if m:
        method = m.group(1).strip().upper()
        path   = _sub_vars(m.group(2).strip())
        data   = m.group(3).strip()
        step = {"action": "api.request", "method": method, "url": "${base_url}" + path, "store_as": "last_response"}
        if data and data not in ("{}", ""):
            step["body"] = _sub_vars(data)
        return step

    # ── ws | data | (WebSocket tunHttp) ───────────────────────────────────
    m = re.match(r"^ws\s*\|\s*(.+)\s*\|", line, re.I)
    if m:
        data = _sub_vars(m.group(1).strip())
        return {"action": "websocket.send", "data": data, "store_as": "last_response"}

    # ── function | {param} | data | ───────────────────────────────────────
    m = re.match(r"^function\s*\|([^|]+)\|([^|]*)\|", line, re.I)
    if m:
        param_str = m.group(1).strip()
        data_str  = m.group(2).strip()
        param_dict = _parse_json(param_str)
        if param_dict is None:
            return {"action": "test.log", "message": f"TODO function (parse error): {line[:120]}"}
        return _map_function(param_dict, data_str)

    # ── re | lookup | in response ─────────────────────────────────────────
    m = re.match(r"^re\s*\|\s*(.+)\s*\|\s*in response", line, re.I)
    if m:
        pattern = _translate_code(m.group(1).strip())
        return {"action": "test.assert",
                "expression": f"re.search({pattern!r}, str(last_response)) is not None"}

    # ── Raw Python that contains gv.* or known Easy BDD runtime names ─────
    # Route through _smart_eval_step so patterns are normalised and pure
    # boolean expressions are promoted to test.assert automatically.
    if any(kw in line for kw in ("gv.", "last_response", "last_eval", "variables[")):
        return _smart_eval_step(line)  # caller wraps with _to_dot_notation

    # ── Generic function call: name(args) ─────────────────────────────────
    m = re.match(r"^(\w+)\(([^)]*)\)$", line)
    if m:
        fn   = m.group(1)
        args = _translate_code(m.group(2))
        return {"action": "eval.exec", "code": f"{fn}({args})"}

    # Fallback — keep as a TODO comment
    return {"action": "test.log", "message": f"TODO: {line[:120]}"}


# ────────────────────────────────────────────────────────────────────────────
# Step block parser (list of lines → list of step dicts)
# ────────────────────────────────────────────────────────────────────────────

def _wrap_for_each(steps: List[Dict], headers: List[str], rows: List[List[str]]) -> List[Dict]:
    """Wrap a step list in a for_each loop using an Examples table."""
    if not rows:
        return steps
    if len(headers) == 1:
        loop_var = headers[0]
        typed_values: List[Any] = []
        for row in rows:
            v = row[0] if row else ""
            try:
                typed_values.append(int(v))
            except ValueError:
                try:
                    typed_values.append(float(v))
                except ValueError:
                    typed_values.append(v)
        return [{"for_each": typed_values, "loop_var": loop_var, "steps": steps}]
    else:
        # Multiple columns → list of dicts per iteration
        iterations = [dict(zip(headers, row)) for row in rows]
        return [{"for_each": iterations, "loop_var": "iteration", "steps": steps}]


def parse_step_block(text: str) -> List[Dict]:
    """Parse a raw step block (pipe-delimited lines) into Easy BDD step list."""
    steps: List[Dict] = []
    in_examples = False
    ex_headers: List[str] = []
    ex_rows: List[List[str]] = []

    def _flush_examples():
        nonlocal steps, in_examples, ex_headers, ex_rows
        if in_examples and ex_headers and ex_rows:
            steps = _wrap_for_each(steps, ex_headers, ex_rows)
        in_examples = False
        ex_headers = []
        ex_rows = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---" or stripped.lower() == "none":
            continue

        # Detect Examples: table header
        if re.match(r"^Examples\s*:", stripped, re.I):
            in_examples = True
            ex_headers = []
            ex_rows = []
            continue

        if in_examples:
            # Table row: | col1 | col2 | ...
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                cells = [c for c in cells if c]  # drop empties
                if not ex_headers:
                    # Header row — strip $, <>, spaces from names
                    ex_headers = [re.sub(r"[$<>]", "", c).strip() for c in cells]
                else:
                    ex_rows.append(cells)
                continue
            else:
                # Non-pipe line ends the Examples table
                _flush_examples()
                # Fall through to parse this line as a normal step

        step = _parse_step_line(stripped)
        if step:
            steps.append(_to_dot_notation(step))

    # Handle Examples: at end of block
    _flush_examples()
    return steps


# ────────────────────────────────────────────────────────────────────────────
# .feature file parser
# ────────────────────────────────────────────────────────────────────────────

def parse_feature_file(content: str) -> List[Dict[str, Any]]:
    """
    Parse a full .feature file into a list of test dicts.
    Each test dict: {name, description, tags, loop_count, steps, variables}
    """
    tests = []
    current_test: Optional[Dict] = None
    in_when = False
    in_examples = False
    loop_count = 0

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if line.startswith("Feature:"):
            continue  # top-level feature description

        if line.startswith("Scenario") and ":" in line:
            # Save previous test
            if current_test:
                tests.append(current_test)
            # New test
            title = re.sub(r"^Scenario\s*Outline\s*:\s*", "", line).strip()
            title = re.sub(r"^Scenario\s*:\s*", "", title).strip()
            current_test = {"name": title, "description": "", "tags": [], "steps": [], "loop_count": 0}
            in_when = False
            in_examples = False
            continue

        if not current_test:
            continue

        if line.startswith("@"):
            current_test["tags"].extend(t.strip("@") for t in line.split() if t.startswith("@"))
            continue

        if line.startswith("Given ") or line.startswith("given "):
            # Given test_id | NNNNN |  — just note the test ID
            m = re.match(r"[Gg]iven\s+test_id\s*\|\s*(\d+)\s*\|", line)
            if m:
                current_test["testrail_id"] = m.group(1)
            in_when = False
            continue

        if line.startswith("When ") or line == "When ---" or line.startswith("when "):
            in_when = True
            continue

        if line.startswith("Then ") or line.startswith("then "):
            in_when = False
            continue

        if line.startswith("Examples:"):
            in_examples = True
            in_when = False
            continue

        if in_examples:
            # Count data rows (skip header row with $loop$)
            if "$loop$" in line:
                continue
            if re.match(r"^\|\s*\d+\s*\|", line):
                current_test["loop_count"] += 1
            continue

        if in_when:
            stripped = line.strip()
            if not stripped or stripped == "---":
                continue
            step = _parse_step_line(stripped)
            if step:
                current_test["steps"].append(_to_dot_notation(step))

    if current_test:
        tests.append(current_test)

    return tests


# ────────────────────────────────────────────────────────────────────────────
# Given/Shared/Feature TestRail-style section processor
# ────────────────────────────────────────────────────────────────────────────

def parse_given_variables(text: str) -> Dict[str, Any]:
    """
    Parse a Given: case body (JSON dict of $key: value pairs) into
    an Easy BDD variables dict (keys stripped of $).
    """
    text = text.strip()
    if not text:
        return {}
    d = _parse_json(text)
    if d is not None:
        # JSON parsed successfully — keys are bare strings like "$url"
        return {k.lstrip("$"): _sub_vars(str(v)) for k, v in d.items()}
    # Fallback: line-by-line "key": "value", parsing
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line in ("{", "}"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            clean_k = _clean_var_key(k)
            clean_v = _clean_var_value(v)
            if clean_k:
                result[clean_k] = clean_v
    return result


def parse_shared_step(name: str, body: str) -> Optional[Dict[str, Any]]:
    """
    Parse a Shared: case body into an Easy BDD shared step entry dict.
    Returns None if body is empty.
    """
    body = (body or "").strip()
    if not body:
        return None
    steps = parse_step_block(body)
    slug  = re.sub(r"^Shared:\s*", "", name).strip()
    slug  = re.sub(r"[^A-Za-z0-9_]+", "_", slug).strip("_")
    return {"name": slug, "description": name, "steps": steps}


# ────────────────────────────────────────────────────────────────────────────
# Top-level migrate function
# ────────────────────────────────────────────────────────────────────────────

def migrate(content: str) -> Dict[str, Any]:
    """
    Migrate mybdd content to Easy BDD.

    Accepts:
      - A .feature file (Gherkin shell)
      - A raw step block (pipe-delimited lines)
      - A JSON string with "given", "shared", "feature" sections

    Returns the same shape as robot_migrator.migrate():
    {
        "tests": [{"name", "display_name", "yaml"}, ...],
        "shared_steps": {...},
        "shared_steps_yaml": "...",
        "warnings": [...],
        "summary": {"tests", "shared_steps", "variables"},
    }
    """
    import yaml

    content = content.strip()
    warnings: List[str] = []
    tests_out: List[Dict] = []
    shared_out: Dict[str, Any] = {}
    variables_out: Dict[str, Any] = {}

    # ── Detect format ────────────────────────────────────────────────────
    is_feature  = "Feature:" in content or "Scenario" in content
    is_json_doc = content.startswith("{") and '"given"' in content

    if is_json_doc:
        # Structured JSON with given/shared/feature keys
        doc = _parse_json(content) or {}
        variables_out = parse_given_variables(doc.get("given", "{}"))
        for sh_name, sh_body in (doc.get("shared", {}) or {}).items():
            entry = parse_shared_step(sh_name, sh_body)
            if entry:
                shared_out[entry["name"]] = {
                    "description": entry["description"],
                    "steps": entry["steps"],
                }
        for feat_name, feat_body in (doc.get("feature", {}) or {}).items():
            steps = parse_step_block(feat_body)
            test_dict = {"name": feat_name, "variables": variables_out.copy(), "steps": steps}
            slug = re.sub(r"[^A-Za-z0-9_-]", "_", feat_name).strip("_")
            tests_out.append({"name": slug, "display_name": feat_name,
                               "yaml": yaml.dump(test_dict, sort_keys=False, allow_unicode=True)})

    elif is_feature:
        # Full .feature file
        parsed_tests = parse_feature_file(content)
        for t in parsed_tests:
            name = t["name"]
            slug = re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_")
            test_dict: Dict[str, Any] = {"name": name}
            if t.get("testrail_id"):
                test_dict["description"] = f"TestRail test {t['testrail_id']}"
            if t.get("tags"):
                test_dict["tags"] = t["tags"]
            if variables_out:
                test_dict["variables"] = variables_out
            test_dict["steps"] = t["steps"]

            if t.get("loop_count", 0) > 1:
                # Wrap in for loop
                loop_step = {
                    "for_each": list(range(1, t["loop_count"] + 1)),
                    "loop_var": "loop_iteration",
                    "steps": t["steps"],
                }
                test_dict["steps"] = [loop_step]
                warnings.append(f"Test '{name}' had {t['loop_count']} loop iterations — wrapped in for_each.")

            _flag_todos(test_dict["steps"], name, warnings)
            tests_out.append({"name": slug, "display_name": name,
                               "yaml": yaml.dump(test_dict, sort_keys=False, allow_unicode=True)})

    else:
        # Raw step block (e.g., content of custom_preconds)
        steps = parse_step_block(content)
        test_dict = {"name": "Migrated Test", "steps": steps}
        _flag_todos(steps, "Migrated Test", warnings)
        tests_out.append({"name": "migrated_test", "display_name": "Migrated Test",
                           "yaml": yaml.dump(test_dict, sort_keys=False, allow_unicode=True)})

    if not tests_out:
        warnings.append("No test cases found — content may only contain Given/Shared definitions.")

    return {
        "tests":             tests_out,
        "shared_steps":      shared_out,
        "shared_steps_yaml": yaml.dump(shared_out, sort_keys=False, allow_unicode=True) if shared_out else "",
        "warnings":          warnings,
        "summary": {
            "tests":        len(tests_out),
            "shared_steps": len(shared_out),
            "variables":    len(variables_out),
        },
    }


def _flag_todos(steps: List[Dict], test_name: str, warnings: List[str]) -> None:
    """Add warning for steps that could not be auto-mapped."""
    todos = [s for s in steps if isinstance(s, dict) and
             "test.log" in s and
             str((s.get("test.log") or {}).get("message", "")).startswith("TODO")]
    if todos:
        warnings.append(f"Test '{test_name}': {len(todos)} step(s) need manual review (marked as TODO).")


def _to_dot_notation(step: Dict) -> Dict:
    """Convert flat {'action': 'x.y', 'param': val} → {'x.y': {'param': val}}.

    Recursively converts steps inside loop/conditional bodies.
    Leaves special structures (shared_step, for_each, condition, etc.) untouched.
    """
    if not isinstance(step, dict):
        return step

    step = dict(step)

    # Recurse into nested step lists first
    for key in ("steps", "loop_steps", "then_steps", "else_steps"):
        if isinstance(step.get(key), list):
            step[key] = [_to_dot_notation(s) for s in step[key]]

    action = step.pop("action", None)
    if action is None:
        return step  # already dot-notation or special structure (shared_step, for_each, etc.)

    # Remaining keys are params
    return {action: step} if step else {action: {}}
