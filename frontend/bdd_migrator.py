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
  browser | {"command": "open", "param": "url"} |   → browser.open
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
  function | {"name":"browser"} | [{"command":...}] | → one browser.* step per array entry
                                                        (Selenium IDE-style export). "pause" →
                                                        browser.wait; id=/link=/name=/css=
                                                        locators are translated to real
                                                        selectors (xpath= passes through as-is)
  Shared: name                                      → shared_step: name
  $variable                                         → ${variable}
  gv.log[-1]['response_txt']  (YAML param context)  → ${last_response}
  gv.log[-1]['response']      (YAML param context)  → ${last_response}
  gv.log[-1]['response_dict'] (YAML param context)  → ${last_response_dict}
  gv.log[-1]['response_code'] (YAML param context)  → ${last_response_code}
  gv.<attr>                   (YAML param context)  → ${attr}
  gv.tests['variables']['k']  (YAML param context)  → ${k}  (k may contain hyphens)
  gv.log[-1]['response_txt']  (Python code context) → str(last_response)
  gv.log[-1]['response']      (Python code context) → str(last_response)
  gv.log[-1]['response_dict'] (Python code context) → last_response_dict
  gv.tests['variables']['k']  (Python code context) → k  (identifier) or variables['k'] (hyphenated)
  gv.<attr>                   (Python code context) → attr  (plain name)
  str2dict(...)               (Python code context) → json.loads(...)
  get_text(...)               (Python code context) → str(...)
  prev_response               (Python/YAML context) → last_response
  gv.tests['variables']['k']=v (Python assignment)  → eval.exec: "k = v" + store_as: k
  gv.tests['variables']['a-b']=v (Python assignment) → eval.exec: "variables['a-b'] = v" + store_as: a-b
  gv.message = v              (Python assignment)   → eval.exec: "message = v" + store_as: message
  gv.attr = v                 (Python assignment)   → eval.exec: "attr = v" + store_as: attr
  pure boolean Python expression                    → test.assert: expression
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Optional, Tuple


def _ensure_base_url(url: str) -> str:
    """Prepend ${url} to relative paths that have no base URL.

    Relative paths start with '/' and contain no existing base variable or
    scheme.  Absolute URLs (http://, wss://, ...) and paths already using a
    ${...} variable prefix are left unchanged.
    """
    if not url:
        return url
    if url.startswith("/") and not url.startswith("//"):
        return "${url}" + url
    return url


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
    text = re.sub(r"gv\.log\[-2\]\['response_txt'\]",   "${last_response}",      text)
    text = re.sub(r"gv\.log\[-2\]\['response'\]",        "${last_response}",      text)
    text = re.sub(r"gv\.log\[(-?\d+)\]\['response(?:_txt)?'\]", r"${response_\1}", text)

    # gv.log indexed access — response dict
    text = re.sub(r"gv\.log\[-1\]\['response_dict'\]",  "${last_response_dict}", text)
    text = re.sub(r"gv\.log\[-2\]\['response_dict'\]",  "${prev_response_dict}", text)
    text = re.sub(r"gv\.log\[(-?\d+)\]\['response_dict'\]", r"${response_dict_\1}", text)

    # gv.log — response code / status
    text = re.sub(r"gv\.log\[-1\]\['(?:response_code|status_code)'\]",  "${last_response_code}",    text)
    text = re.sub(r"gv\.log\[-1\]\['(?:response_headers?|headers?)'\]", "${last_response_headers}", text)

    # gv.tests['variables']['key'] / gv.tests['variables']['$key'] access
    # Supports both simple identifiers and hyphenated names like B-900-MOIP-4K-RX_dict
    text = re.sub(r"gv\.tests\['variables'\]\['\$?([\w][\w\-]*)'\]", r"${\1}", text)
    text = re.sub(r'gv\.tests\["variables"\]\["\$?([\w][\w\-]*)"\]', r"${\1}", text)

    # gv.<attr> — generalized to ${attr} for any attribute (not log/tests shim objects)
    text = re.sub(r"\bgv\.(?!log\b|tests\b)(\w+)\b", r"${\1}", text)

    # <$varname$> or <${varname}$> or <${varname}> — Gherkin Scenario Outline params
    text = re.sub(r"<\$\{([A-Za-z_][A-Za-z0-9_]*)\}\$?>", r"${\1}", text)
    text = re.sub(r"<\$([A-Za-z_][A-Za-z0-9_]*)\$>",       r"${\1}", text)

    # $variable → ${variable}  (dollar-sign variables, not already in ${...})
    # Allow hyphens inside names (e.g. $unit_id_B-900-MOIP-4K-RX_...) but not
    # trailing hyphens, so arithmetic like $count-1 is not consumed.
    def dollar_sub(m):
        return "${" + m.group(1) + "}"
    text = re.sub(r"\$(?!\{)([A-Za-z_][\w]*(?:-[\w]+)*)", dollar_sub, text)

    return text


# ── patterns applied to Python code strings (eval.exec, test.assert, etc.) ──
# Maps (pattern, replacement) where replacement can be a string or callable.
# Bare JSON-RPC method name (dxGetAbout, wbSetUnderOverSettings, …) as opposed
# to a URL path segment — used to route webservice|send position 3 correctly.
_RPC_METHOD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_CODE_PATTERNS: List[Tuple[str, Any]] = [
    # gv.log response text — Easy BDD stores the full response dict under store_as;
    # the body JSON string lives in last_response["body"].
    (r"gv\.log\[-1\]\['response_txt'\]",    'last_response["body"]'),
    (r"gv\.log\[-1\]\['response'\]",         'last_response["body"]'),
    (r"gv\.log\[-2\]\['response_txt'\]",    'last_response["body"]'),
    (r"gv\.log\[-2\]\['response'\]",         'last_response["body"]'),
    # gv.log response dict
    (r"gv\.log\[-1\]\['response_dict'\]",   "last_response_dict"),
    (r"gv\.log\[-2\]\['response_dict'\]",   "last_response_dict"),
    # gv.log response code / headers
    (r"gv\.log\[-1\]\['(?:response_code|status_code)'\]",  "last_response['status']"),
    (r"gv\.log\[-1\]\['(?:response_headers?|headers?)'\]", "last_response['headers']"),
    # Numeric-indexed log entries
    (r"gv\.log\[(-?\d+)\]\['response(?:_txt)?'\]",
        lambda m: 'last_response["body"]' if m.group(1) in ("-1",)
                  else f"log_response_{m.group(1).lstrip('-')}['body']"),
    (r"gv\.log\[(-?\d+)\]\['response_dict'\]",
        lambda m: "last_response_dict" if m.group(1) in ("-1",)
                  else f"log_response_dict_{m.group(1).lstrip('-')}"),
    # gv.tests['variables']['key'] / ['$key'] reads
    # Simple identifiers (all word chars) → bare name; hyphenated names → variables['name']
    (r"gv\.tests\['variables'\]\['\$?([\w][\w\-]*)'\]",
        lambda m: m.group(1) if re.match(r'^\w+$', m.group(1)) else f"variables['{m.group(1)}']"),
    (r'gv\.tests\["variables"\]\["\$?([\w][\w\-]*)"\]',
        lambda m: m.group(1) if re.match(r'^\w+$', m.group(1)) else f"variables['{m.group(1)}']"),
    # gv.message / gv.<attr> reads (not log/tests — those are handled above) → plain name
    (r"gv\.(?!log\b|tests\b)(\w+)\b", r"\1"),
    # mybdd helper functions → Easy BDD / stdlib equivalents
    (r"\bgv\.str2dict\b", "json.loads"),
    (r"\bstr2dict\b",     "json.loads"),
    (r"\bgv\.get_text\b", "str"),
    (r"\bget_text\b",     "str"),
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
      1. gv.tests['variables']['key'] = <expr>
         → eval.exec: "key = <expr_translated>"  store_as: key
      2. gv.<attr> = <expr>  (gv.message, etc.)
         → eval.exec: "<attr> = <expr_translated>"  store_as: attr
      3. Pure boolean / comparison expression (no assignment, no side-effect call)
         → test.assert: expression
      4. Everything else → eval.exec.

    Rules 1 & 2 are detected BEFORE _translate_code so the gv. prefix is still
    present in the raw string; the RHS is translated separately to eliminate any
    nested gv.* references.
    """
    raw = code.strip()

    # Rule 1 — gv.tests['variables']['key'] = expr  (single or double quotes)
    # Supports both simple identifiers and hyphenated names like B-900-MOIP-4K-RX_dict.
    m = re.match(
        r"^gv\.tests\[(?:'variables'|\"variables\")\]\[(?:'\$?([\w][\w\-]*)'|\"\$?([\w][\w\-]*)\")\]\s*=\s*(.+)$",
        raw, re.DOTALL,
    )
    if m:
        var_name = m.group(1) or m.group(2)
        rhs = _translate_code(m.group(3).strip())
        # Use bare name for valid Python identifiers; dict access for hyphenated names
        lhs = var_name if re.match(r'^\w+$', var_name) else f"variables['{var_name}']"
        return {"action": "eval.exec", "code": f"{lhs} = {rhs}", "store_as": var_name}

    # Rule 2 — gv.<attr> = expr  (e.g. gv.message = ..., gv.result = ...)
    # Excludes gv.log and gv.tests which are shim objects, not settable scalars.
    m = re.match(r"^gv\.(?!log\b|tests\b)(\w+)\s*=\s*(.+)$", raw, re.DOTALL)
    if m:
        var_name = m.group(1)
        rhs = _translate_code(m.group(2).strip())
        return {"action": "eval.exec", "code": f"{var_name} = {rhs}", "store_as": var_name}

    # All other code — apply full translation now
    code = _translate_code(raw)

    # Rule 3 — bare variable reference after translation (no operators, no calls).
    # These are no-ops in Python; convert to test.print so the value is at least
    # visible in the test log rather than silently discarded.
    if re.match(r'^[A-Za-z_]\w*$', code.strip()):
        return {"action": "test.print", "message": f"${{{code.strip()}}}"}

    # Rule 4 — pure boolean expression (no assignment, no side-effect call)
    # Heuristic: contains a comparison / containment operator and no bare '='.
    _no_assign = not re.search(r"(?<![=!<>])=(?!=)", code)  # lone = but not == != <= >=
    _is_bool   = bool(re.search(
        r"\bin\b|\bnot\s+in\b|\b(?:is|is\s+not)\b|==|!=|<=|>=|<(?!=)|>(?!=)|"
        r"\bre\.(?:search|match|fullmatch)\b",
        code
    ))
    if _no_assign and _is_bool and "(" not in code.split("in")[0]:
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


def _expand_json_payload(raw: str) -> Any:
    """Try to parse a JSON/Python-dict payload string into a native dict.

    If parsing succeeds, applies _sub_vars to every string value so that
    ``$variable`` references become ``${variable}`` in the output YAML.
    Non-string values (int, float, bool, None) are preserved as-is so they
    render as native YAML scalars rather than quoted strings.

    Returns the expanded dict on success, or the original (var-substituted)
    string if the input cannot be parsed as a dict.
    """
    if not raw or raw in ("{}", ""):
        return None

    d = _parse_json(raw)
    if not isinstance(d, dict):
        # Not a JSON object — return the string with vars substituted
        return _sub_vars(raw)

    def _convert_value(v: Any) -> Any:
        if isinstance(v, str):
            return _sub_vars(v)
        if isinstance(v, dict):
            return {k: _convert_value(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_convert_value(i) for i in v]
        # int, float, bool, None — keep native
        return v

    return {k: _convert_value(v) for k, v in d.items()}


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

_SELENIUM_LOCATOR_RE = re.compile(
    r"^(xpath|id|css|name|classname|class|linktext|link|partiallinktext)=(.*)$", re.I
)


def _selenium_locator_kwargs(raw: str) -> Dict[str, str]:
    """Translate a Selenium IDE locator string into browser.* action kwargs.

    xpath= passes through unchanged — the runtime browser service already
    strips that prefix. id=/name=/css=/className= aren't selector engines
    Playwright understands, so they're rewritten into real CSS. link=/
    linkText=/partialLinkText= become a text-based match (the framework's
    text= click already does substring matching, covering both exact and
    partial link text). A bare string with no recognized prefix passes
    through unchanged as a selector (already CSS/XPath-shaped, or a plain
    ${var} reference).
    """
    if not raw:
        return {}
    m = _SELENIUM_LOCATOR_RE.match(raw.strip())
    if not m:
        return {"selector": raw}
    strategy, value = m.group(1).lower(), m.group(2)
    if strategy == "xpath":
        return {"selector": f"xpath={value}"}
    if strategy == "id":
        return {"selector": f"#{value}"}
    if strategy == "css":
        return {"selector": value}
    if strategy in ("classname", "class"):
        return {"selector": f".{value}"}
    if strategy == "name":
        return {"selector": f"[name='{value}']"}
    if strategy in ("link", "linktext", "partiallinktext"):
        return {"text": value}
    return {"selector": raw}


def _selenium_selector_string(raw: str) -> str:
    """Like _selenium_locator_kwargs, but always returns a plain selector
    string — for params (e.g. drag-and-drop source/target) that have no
    separate text= alternative to fall back to."""
    if not raw:
        return raw
    kwargs = _selenium_locator_kwargs(raw)
    if "selector" in kwargs:
        return kwargs["selector"]
    if "text" in kwargs:
        return f"xpath=//*[normalize-space(text())='{kwargs['text']}']"
    return raw


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
        step = {"action": "browser.open", "url": param or target}
    elif cmd in ("close",):
        step = {"action": "browser.close"}
    elif cmd in ("refresh",):
        step = {"action": "browser.refresh"}
    elif cmd in ("pause",):
        # Selenium's timed pause — target/param/value carries milliseconds.
        ms_raw = target or param or value or "0"
        try:
            ms = float(ms_raw)
        except (TypeError, ValueError):
            ms = 0.0
        step = {"action": "browser.wait", "timeout": ms / 1000}
    elif cmd in ("type", "fill", "input"):
        s = {"action": "browser.fill", "value": text or value}
        sel = target or param
        if sel:
            s.update(_selenium_locator_kwargs(sel))
        step = s
    elif cmd in ("click",):
        s = {"action": "browser.click"}
        sel = target or param
        if sel:
            s.update(_selenium_locator_kwargs(sel))
        elif text:
            s["text"] = text
        step = s
    elif cmd in ("press",):
        step = {"action": "browser.press_key", "key": key}
        sel = target or param
        if sel:
            step.update(_selenium_locator_kwargs(sel))
    elif cmd in ("gettext", "get_text", "innertext"):
        s = {"action": "browser.get_text", "store_as": name or "last_text"}
        sel = target or param
        if sel:
            s.update(_selenium_locator_kwargs(sel))
        step = s
    elif cmd in ("screenshot", "capture"):
        step = {"action": "browser.screenshot", "name": name or param or "screenshot"}
    elif cmd in ("wait", "waitfor", "wait_for_element"):
        sel = target or param
        # A bare wait with no target is a timed pause, not an element wait
        s = {"action": "browser.wait_for", **_selenium_locator_kwargs(sel)} if sel else {"action": "browser.wait"}
        if timeout:
            s["timeout"] = timeout
        step = s
    elif cmd in ("wait_for_text", "waitfortext"):
        step = {"action": "browser.wait_for_text", "text": text or param}
    elif cmd in ("evaluate", "eval", "execute_script"):
        step = {"action": "eval.exec", "code": param or text}
    elif cmd in ("select",):
        s = {"action": "browser.select", "value": value or text}
        sel = target or param
        if sel:
            s.update(_selenium_locator_kwargs(sel))
        step = s
    elif cmd in ("hover",):
        step = {"action": "browser.hover", **_selenium_locator_kwargs(target or param)}
    elif cmd in ("check", "uncheck"):
        step = {"action": f"browser.{cmd}", **_selenium_locator_kwargs(target or param)}
    elif cmd in ("scroll",):
        step = {"action": "browser.scroll", **_selenium_locator_kwargs(target or param)}
    elif cmd in ("assertelementpresent", "assert_element_present", "verifyelementpresent", "waitforelementpresent"):
        # Closest declarative equivalent — Selenium's presence check doesn't
        # distinguish "in the DOM" from "visible", and confirming visibility
        # is the more useful signal for a page-loaded check anyway.
        step = {"action": "test.assert_element_visible", **_selenium_locator_kwargs(target or param)}
    elif cmd in ("validate_checkbox_enabled", "assert_checked"):
        s = {"action": "browser.assert_checked"}
        sel = param or target
        if sel:
            s.update(_selenium_locator_kwargs(sel))
        step = s
    elif cmd in ("validate_checkbox_disabled", "assert_not_checked", "assert_unchecked"):
        s = {"action": "browser.assert_unchecked"}
        sel = param or target
        if sel:
            s.update(_selenium_locator_kwargs(sel))
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
        # With a selector, test.assert_text_contains scopes the substring
        # check to that element; without one, browser.verify_text checks
        # the whole page (both are contains-semantics like the legacy cmd).
        sel = param or target
        if sel:
            step = {"action": "test.assert_text_contains",
                    **_selenium_locator_kwargs(sel),
                    "text": cmd_dict.get("text", text)}
        else:
            step = {"action": "browser.verify_text", "text": cmd_dict.get("text", text)}
    elif cmd in ("gettitle", "get_title", "asserttitle", "assert_title"):
        store = cmd_dict.get("store_as", "page_title")
        step = {"action": "browser.get_title", "store_as": store}
    elif cmd in ("assert_value", "assertvalue"):
        s = {"action": "test.assert_value", "value": value or text}
        sel = param or target
        if sel:
            s.update(_selenium_locator_kwargs(sel))
        step = s
    elif cmd in ("waitfornavigation", "wait_for_navigation", "wait_for_load"):
        # browser.wait_for_url with no url waits for the page load state
        step = {"action": "browser.wait_for_url"}
    elif cmd in ("dragdrop", "drag_drop", "drag_and_drop"):
        step = {"action": "browser.drag_and_drop",
                "source_selector": _selenium_selector_string(target or param),
                "target_selector": _selenium_selector_string(_sub_vars(str(cmd_dict.get("destination", ""))))}
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


def _firmware_manager_steps(param_dict: Optional[Dict] = None) -> List[Dict]:
    """Return the canonical firmware-manager Var-case step sequence.

    Produces ten steps covering local firmware download, file classification,
    path extraction, CloudFront URL fetching, and version extraction / run rename.
    Callers must flatten the returned list into the surrounding step list.
    """
    p = param_dict or {}
    bucket  = _sub_vars(str(p.get("aws_bucket",       "${aws_bucket}")))
    pattern = _sub_vars(str(p.get("filename_pattern",  "${filename_pattern}")))
    folder  = _sub_vars(str(p.get("folder_prefix",     "${folder_prefix}")))
    cf_url  = _sub_vars(str(p.get("cloudfront_url",    "${cloudfront_url}")))
    ver_pat = str(p.get("version_pattern", r"wattboxvps_(.*?)\.sec\.bin"))

    return [
        {
            "action":           "aws.list_files",
            "bucket_name":      bucket,
            "filename_pattern": pattern,
            "folder_prefix":    folder,
            "local_paths_as":   "firmware_local_paths",
            "store_as":         "firmware_files",
        },
        {
            "action": "eval.exec",
            "code": "upgrade_file = next((f for f in firmware_files if '-DM' not in f), None); dm_file = next((f for f in firmware_files if '-DM' in f), None)",
        },
        {"action": "eval.run", "expression": "firmware_files[0]",       "store_as": "upgrade_file"},
        {"action": "eval.run", "expression": "firmware_files[1]",       "store_as": "downgrade_file"},
        {"action": "eval.run", "expression": "firmware_local_paths[0]", "store_as": "firmware_upgrade_path"},
        {"action": "eval.run", "expression": "firmware_local_paths[1]", "store_as": "firmware_downgrade_path"},
        {
            "action":           "aws.list_files",
            "bucket_name":      bucket,
            "filename_pattern": pattern,
            "folder_prefix":    folder,
            "cloudfront_url":   cf_url,
            "store_as":         "cloudfront_firmwares",
        },
        {"action": "eval.run", "expression": "cloudfront_firmwares[0]", "store_as": "cloudfront_upgrade_file"},
        {"action": "eval.run", "expression": "cloudfront_firmwares[1]", "store_as": "cloudfront_downgrade_file"},
        {
            "action":   "eval.extract_version",
            "from_var": "firmware_files",
            "pattern":  ver_pat,
            "store_as": "firmware_version",
            "run_name": "EASY_BDD: ${product} Smoke Test - ${firmware_version}",
        },
    ]


# Recognizes the specific retry-until-connected idiom used repeatedly in
# the legacy suite (see _match_dxgetabout_retry_loop below).
_ROOT_FUNCTION_DXGETABOUT_RETRY_RE = re.compile(
    r"root_function\s*\(\s*param\s*=\s*\{[^}]*['\"]command['\"]\s*:\s*['\"]dxGetAbout['\"]"
)


def _match_dxgetabout_retry_loop(code: str) -> Optional[Dict]:
    """Recognizes this exact retry-until-connected idiom, used identically
    four times across the legacy suite (e.g. Feature: Network Interruption,
    Feature: Boot Without Power + Network):

        _i=0; _ok=False; _resp=''
        while _i<6 and not _ok:
            _resp = root_function(param={'name':'webservice', ..., 'command':'dxGetAbout'}, data={...}, nested=True)
            _ok = ('deviceId' in str(_resp) and 'firmware' in str(_resp) and 'error' not in str(_resp))
            _i += 1
            (_ok or time.sleep(15))
        assert _ok, '...'

    root_function is an internal helper from the old framework that has no
    equivalent in Easy BDD's eval context at all — migrated as raw
    eval.exec, this fails outright with a NameError at test-run time, not
    just an inelegant TODO. Rather than structurally reconstructing this
    exact while-loop from its Python (a lot of brittle AST matching for
    something whose scratch variable names are author-chosen and could
    differ trivially), this checks for the one load-bearing marker that
    can't vary — a root_function(...) call whose command is 'dxGetAbout' —
    and replaces the whole block with the pre-built Shared: step that does
    the same retry (Shared: wait_for_dxGetAbout_ready). Deliberately narrow:
    only fires for this exact command, not a general "any dx* retry loop"
    pattern — there's no evidence yet that idiom is reused for other
    commands, and guessing wrong here would silently point a case at the
    wrong device call.
    """
    if "root_function" not in code:
        return None
    if not _ROOT_FUNCTION_DXGETABOUT_RETRY_RE.search(code):
        return None
    return {"shared_step": "wait_for_dxGetAbout_ready"}


def _map_function(param_dict: Dict, data_str: str) -> Any:
    name = param_dict.get("name", "").lower()
    raw_data_str = data_str.strip()   # keep original for JSON re-parsing (before _sub_vars mangles $ vars)
    data_str = _sub_vars(raw_data_str)

    if name == "sleep":
        sec = param_dict.get("sec", param_dict.get("seconds", 1))
        return {"action": "test.sleep", "seconds": float(sec)}

    if name == "browser":
        # Selenium IDE-style export: data_str is a JSON array of
        # {"command":..., "target":..., "value":...} steps, one Selenium
        # command per entry. Parse from raw_data_str (pre-_sub_vars, same
        # convention as the "eval" paired-conditional case above) since the
        # array is JSON syntax, not a value to substitute — _map_browser
        # already runs _sub_vars on each individual field it reads.
        commands = _parse_json(raw_data_str)
        if not isinstance(commands, list):
            return {"action": "test.log",
                    "message": f"TODO function browser (expected a JSON array): {data_str[:120]}"}
        return [_map_browser(c) for c in commands if isinstance(c, dict)]

    if name in ("exec", "execute"):
        raw_code = str(param_dict.get("string", ""))
        retry_step = _match_dxgetabout_retry_loop(raw_code)
        if retry_step is not None:
            return retry_step
        # Use _translate_code (not _sub_vars) — Python code context, not a YAML string value.
        return _smart_eval_step(raw_code)

    if name == "eval":
        # Detect paired conditional: {"name":"eval","string":"condition"} | {"name":"exec","string":"code"}
        # This is the old framework's inline if-then pattern: if condition → run code.
        # Use raw_data_str (pre-_sub_vars) so gv.tests variable names are still recognisable.
        paired = _parse_json(raw_data_str) if raw_data_str else None
        if paired and paired.get("name", "").lower() in ("exec", "execute"):
            condition_raw = str(param_dict.get("string", param_dict.get("expression", "")))
            condition     = _translate_code(condition_raw)
            exec_raw      = str(paired.get("string", ""))
            exec_step     = _smart_eval_step(exec_raw)
            exec_code     = exec_step.get("code", _translate_code(exec_raw))
            store_var     = exec_step.get("store_as", "")
            combined      = f"if {condition}: {exec_code}"
            step: Dict[str, Any] = {"action": "eval.exec", "code": combined}
            if store_var:
                step["store_as"] = store_var
            return step
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
        full_url = (url.rstrip("/") + "/" + path.lstrip("/")) if path else url
        full_url = _ensure_base_url(full_url)
        # "url" here is almost always a ${var} (e.g. "$url" resolving to
        # wss://... at runtime), so checking its literal prefix at migration
        # time never fires — and "method":"send" is set inconsistently in
        # this codebase (present on some otherwise-identical OvrC calls,
        # omitted on others). The one reliable signal this codebase actually
        # uses consistently is the "command" key itself (vs "path") — every
        # OvrC dx* call in the real suite uses "command", never "path".
        is_ws = (
            method == "SEND"
            or full_url.startswith("wss://") or full_url.startswith("ws://")
            or "command" in param_dict
        )
        if is_ws:
            body_val = _expand_json_payload(data_str) if data_str and data_str not in ("{}", "") else None
            ws_step: Dict[str, Any] = {"action": "websocket.send", "url": _ensure_base_url(url), "store_as": "last_response"}
            if path and _RPC_METHOD_RE.match(path):
                # path is a JSON-RPC method name, not a URL segment
                ws_step["method"] = path
            else:
                ws_step["url"] = full_url
            if body_val is not None:
                ws_step["data"] = body_val
            return ws_step
        step: Dict[str, Any] = {"action": "api.request", "method": method, "url": full_url, "store_as": "last_response"}
        payload = _expand_json_payload(data_str)
        if payload is not None:
            step["body"] = payload
        headers = param_dict.get("headers")
        if headers:
            step["headers"] = headers
        return step

    if name == "device":
        method  = param_dict.get("method", "get").upper()
        url     = _sub_vars(str(param_dict.get("url", "")))
        path    = _sub_vars(str(param_dict.get("path", "")))
        full_url = _ensure_base_url(f"{url}{path}")
        step = {"action": "api.request", "method": method, "url": full_url, "store_as": "last_response"}
        payload = _expand_json_payload(data_str)
        if payload is not None:
            step["body"] = payload
        return step

    if name == "control4":
        method  = param_dict.get("method", "post").upper()
        path    = _sub_vars(str(param_dict.get("path", "")))
        step = {"action": "api.request", "method": method, "url": "${control4_url}" + path, "store_as": "last_response"}
        payload = _expand_json_payload(data_str)
        if payload is not None:
            step["body"] = payload
        return step

    if name == "telnet":
        return {
            "action":  "telnet.send",
            "host":    _sub_vars(str(param_dict.get("host", ""))),
            "port":    _int_or_var(param_dict.get("port", 23), 23),
            "command": _sub_vars(str(param_dict.get("command", ""))),
            "prompt":  param_dict.get("prompt", ">"),
        }

    if name == "ssh":
        step = {
            "action":   "ssh.command",
            "host":     _sub_vars(str(param_dict.get("host", ""))),
            "username": _sub_vars(str(param_dict.get("user", param_dict.get("username", "")))),
            "password": _sub_vars(str(param_dict.get("password", ""))),
            "command":  _sub_vars(str(param_dict.get("command", ""))),
        }
        if param_dict.get("prompt"):
            step["prompt"] = param_dict["prompt"]
        return step

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

    if name == "find_firmware_in_location":
        # Scans a local/S3 folder for firmware files matching a pattern
        folder  = _sub_vars(str(param_dict.get("location_path", param_dict.get("folder_prefix", ""))))
        ftype   = _sub_vars(str(param_dict.get("file_type", "*.imag")))
        store   = param_dict.get("store_as", "firmware_files")
        # Convert glob pattern to regex-style for aws.list_files filename_pattern
        pattern = ftype.replace("*.", "").strip("*")
        step: Dict = {
            "action": "aws.list_files",
            "bucket_name": "${aws_bucket}",
            "folder_prefix": folder,
            "store_as": store,
        }
        if pattern and pattern != ftype:
            step["filename_pattern"] = f".{pattern}$"
        return step

    if name == "upload_cloud_firmware":
        # Expand to the full firmware-manager Var-case template sequence.
        merged = {
            "aws_bucket":      param_dict.get("aws_bucket", ""),
            "filename_pattern": param_dict.get("regex_pattern", ""),
            "folder_prefix":   param_dict.get("download_dir", ""),
            "cloudfront_url":  param_dict.get("cloudfront_url", ""),
        }
        return _firmware_manager_steps(merged)

    if name == "extract_firmware_version":
        # Covered by eval.extract_version at the end of _firmware_manager_steps.
        # Emit a single step so standalone calls still produce something useful.
        return {
            "action":   "eval.extract_version",
            "from_var": "firmware_files",
            "pattern":  r"wattboxvps_(.*?)\.sec\.bin",
            "store_as": "firmware_version",
            "run_name": "EASY_BDD: ${product} Smoke Test - ${firmware_version}",
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
        return {"action": "test.sleep", "seconds": sec}

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
            "prompt":   d.get("prompt", ">"),
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
        is_ws = method == "SEND" or url.startswith("wss://") or url.startswith("ws://")
        if is_ws:
            # In "send" mode position 3 is the JSON-RPC method (dxGetAbout,
            # wbSetUnderOverSettings, …), not a URL path — websocket_service
            # wraps it in a JSON-RPC envelope with position 4 as params.
            body_val = _expand_json_payload(data) if data and data not in ("{}", "") else None
            ws_step: Dict[str, Any] = {"action": "websocket.send", "url": _ensure_base_url(url), "store_as": "last_response"}
            if path and _RPC_METHOD_RE.match(path):
                ws_step["method"] = path
            elif path:
                # A real path (contains / or vars) — keep it on the URL
                ws_step["url"] = _ensure_base_url(url.rstrip("/") + "/" + path.lstrip("/"))
            if body_val is not None:
                ws_step["data"] = body_val
            return ws_step
        # Plain HTTP: append path to URL with a proper separator
        full_url = (url.rstrip("/") + "/" + path.lstrip("/")) if path else url
        full_url = _ensure_base_url(full_url)
        step: Dict[str, Any] = {"action": "api.request", "method": method, "url": full_url, "store_as": "last_response"}
        payload = _expand_json_payload(data)
        if payload is not None:
            step["body"] = payload
        return step

    # ── device | url | path | method | params | data | ────────────────────
    m = re.match(r"^device\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|\s*([^|]*)\|", line, re.I)
    if m:
        url    = _sub_vars(m.group(1).strip())
        path   = _sub_vars(m.group(2).strip())
        method = m.group(3).strip().upper()
        data   = m.group(5).strip()
        step = {"action": "api.request", "method": method, "url": _ensure_base_url(f"{url}{path}"), "store_as": "last_response"}
        payload = _expand_json_payload(data)
        if payload is not None:
            step["body"] = payload
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
            payload = _expand_json_payload(json.dumps(data)) if isinstance(data, dict) else _expand_json_payload(str(data))
            if payload is not None:
                step["body"] = payload
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
        payload = _expand_json_payload(data)
        if payload is not None:
            step["body"] = payload
        return step

    # ── luma_ovrc / device_luma | method | path | data | ─────────────────
    m = re.match(r"^(?:luma_ovrc|device_luma|ovrc)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|", line, re.I)
    if m:
        method = m.group(1).strip().upper()
        path   = _sub_vars(m.group(2).strip())
        data   = m.group(3).strip()
        step = {"action": "api.request", "method": method, "url": "${base_url}" + path, "store_as": "last_response"}
        payload = _expand_json_payload(data)
        if payload is not None:
            step["body"] = payload
        return step

    # ── ws | data | (WebSocket tunHttp) ───────────────────────────────────
    m = re.match(r"^ws\s*\|\s*(.+)\s*\|", line, re.I)
    if m:
        raw = m.group(1).strip()
        data = _expand_json_payload(raw)
        if data is None:
            data = _sub_vars(raw)
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

def _build_data_list(headers: List[str], rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Convert an Examples table into a data: list of variable dicts."""
    if len(headers) == 1:
        key = headers[0]
        result = []
        for row in rows:
            v = row[0] if row else ""
            try:
                result.append({key: int(v)})
            except ValueError:
                try:
                    result.append({key: float(v)})
                except ValueError:
                    result.append({key: v})
        return result
    else:
        return [dict(zip(headers, row)) for row in rows]


def parse_step_block(text: str) -> tuple:
    """Parse a raw step block into (steps, data).

    steps — list of Easy BDD step dicts
    data  — list of variable dicts from an Examples table, or empty list
    """
    steps: List[Dict] = []
    data: List[Dict] = []
    in_examples = False
    ex_headers: List[str] = []
    ex_rows: List[List[str]] = []

    def _flush_examples():
        nonlocal data, in_examples, ex_headers, ex_rows
        if in_examples and ex_headers and ex_rows:
            data = _build_data_list(ex_headers, ex_rows)
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
            if isinstance(step, list):
                steps.extend(_to_dot_notation(s) for s in step)
            else:
                steps.append(_to_dot_notation(step))

    # Handle Examples: at end of block
    _flush_examples()
    return steps, data


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
                if isinstance(step, list):
                    current_test["steps"].extend(_to_dot_notation(s) for s in step)
                else:
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
    steps, _ = parse_step_block(body)
    steps = _simplify_eval_steps(steps)
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
            entry = parse_shared_step(sh_name, sh_body)  # already eval-simplified internally
            if entry:
                _flag_unsimplified_eval(entry["steps"], f"Shared: {entry['name']}", warnings)
                shared_out[entry["name"]] = {
                    "description": entry["description"],
                    "steps": entry["steps"],
                }
        for feat_name, feat_body in (doc.get("feature", {}) or {}).items():
            steps, data = parse_step_block(feat_body)
            steps = _simplify_eval_steps(steps)
            _flag_unsimplified_eval(steps, feat_name, warnings)
            test_dict = {"name": feat_name, "variables": variables_out.copy(), "steps": steps}
            if data:
                test_dict["data"] = data
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
            test_dict["steps"] = _simplify_eval_steps(t["steps"])

            if t.get("loop_count", 0) > 1:
                test_dict["data"] = [
                    {"loop_iteration": i} for i in range(1, t["loop_count"] + 1)
                ]
                warnings.append(f"Test '{name}' had {t['loop_count']} loop iterations — added data: list.")

            _flag_unsimplified_eval(test_dict["steps"], name, warnings)
            _flag_todos(test_dict["steps"], name, warnings)
            tests_out.append({"name": slug, "display_name": name,
                               "yaml": yaml.dump(test_dict, sort_keys=False, allow_unicode=True)})

    else:
        # Raw step block (e.g., content of custom_preconds)
        steps, data = parse_step_block(content)
        steps = _simplify_eval_steps(steps)
        test_dict = {"name": "Migrated Test", "steps": steps}
        if data:
            test_dict["data"] = data
        _flag_unsimplified_eval(steps, "Migrated Test", warnings)
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


# ────────────────────────────────────────────────────────────────────────────
# eval.exec / eval.run simplification — recognize common Python idioms and
# rewrite them as declarative list.pick/text.replace/text.regex_extract/
# text.format actions instead. Conservative by design: if any statement in
# a code block doesn't match a known idiom, the WHOLE block is left as the
# original eval.exec/eval.run rather than partially transformed — a partial
# rewrite risks silently breaking variable flow the untransformed statement
# depended on (e.g. a helper variable a later real eval.exec still reads).
# ────────────────────────────────────────────────────────────────────────────

def _expr_to_template(node: ast.AST) -> Optional[str]:
    """Convert a simple AST expression into a ${var}-interpolated string
    (or a literal) for use as a declarative action's string param. Returns
    None if the expression is too complex to represent this way — e.g. a
    function call, comprehension, or anything beyond a name/literal/+."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Name):
        return f"${{{node.id}}}"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _expr_to_template(node.left)
        right = _expr_to_template(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _index_value(node: ast.AST) -> Optional[int]:
    """Extract a literal integer index, including negative literals
    (-1, -2, ...), which the Python parser represents as UnaryOp(USub)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, int)):
        return -node.operand.value
    return None


def _match_list_pick(value: ast.AST, store_as: str) -> Optional[Dict]:
    """x = y[n]  ->  list.pick"""
    if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
        idx = _index_value(value.slice)
        if idx is not None:
            return {"action": "list.pick", "from_var": value.value.id, "index": idx, "store_as": store_as}
    return None


def _match_text_replace(value: ast.AST, store_as: str) -> Optional[Dict]:
    """x = y.replace(a, b)  ->  text.replace"""
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            and value.func.attr == "replace" and len(value.args) == 2 and not value.keywords):
        receiver = _expr_to_template(value.func.value)
        find = _expr_to_template(value.args[0])
        repl = _expr_to_template(value.args[1])
        if receiver is not None and find is not None and repl is not None:
            return {"action": "text.replace", "value": receiver, "find": find,
                    "replace_with": repl, "store_as": store_as}
    return None


def _match_regex_extract(value: ast.AST, store_as: str) -> Optional[Dict]:
    """x = re.search(pattern, y).group(n)  ->  text.regex_extract

    No None-check on the match here — this only fires for code that already
    assumed the match always succeeds (the pattern this codebase actually
    uses); the safer "or a default" version is _match_regex_ternary_fusion.
    """
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "group"):
        return None
    inner = value.func.value
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "search"
            and isinstance(inner.func.value, ast.Name) and inner.func.value.id == "re"
            and len(inner.args) == 2 and not inner.keywords):
        return None
    pattern = _expr_to_template(inner.args[0])
    source = _expr_to_template(inner.args[1])
    if pattern is None or source is None:
        return None
    group = 0
    if value.args:
        g = _index_value(value.args[0])
        if g is None:
            return None
        group = g
    step = {"action": "text.regex_extract", "value": source, "pattern": pattern, "store_as": store_as}
    if group:
        step["group"] = group
    return step


def _match_text_format(value: ast.AST, store_as: str) -> Optional[Dict]:
    """x = '{}.{}'.format(a, b)  ->  text.format

    Only handles bare {} placeholders (not {0}/{name}) with an exact
    placeholder/arg count match — anything fancier bails out."""
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "format"
            and isinstance(value.func.value, ast.Constant) and isinstance(value.func.value.value, str)
            and not value.keywords):
        return None
    template_str = value.func.value.value
    placeholders = re.findall(r"\{\}", template_str)
    if len(placeholders) != len(value.args) or not placeholders:
        return None
    arg_reprs = [_expr_to_template(a) for a in value.args]
    if any(r is None for r in arg_reprs):
        return None
    rebuilt = template_str
    for rep in arg_reprs:
        rebuilt = rebuilt.replace("{}", rep, 1)
    return {"action": "text.format", "template": rebuilt, "store_as": store_as}


def _expr_to_source_and_field(node: ast.AST) -> Optional[Tuple[str, str]]:
    """Unwrap a chain of string-keyed subscripts rooted at a plain Name
    (optionally wrapped in an outer str(...) call) into (from_var, dotted
    field path) for test.extract — e.g. last_response['body'] ->
    ('last_response', 'body'), d['a']['b'] -> ('d', 'a.b'). Returns None if
    the chain isn't rooted in a plain Name, or any key isn't a string
    literal (an integer-indexed chain is list.pick's territory, not this)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str" and len(node.args) == 1:
        node = node.args[0]
    parts: List[str] = []
    while isinstance(node, ast.Subscript):
        key = node.slice
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        parts.append(key.value)
        node = node.value
    if not parts or not isinstance(node, ast.Name):
        return None
    parts.reverse()
    return node.id, ".".join(parts)


def _match_dict_path_extract(value: ast.AST, store_as: str) -> Optional[Dict]:
    """x = d['a']['b']  ->  test.extract

    Reuses the existing dot-notation field lookup test.extract already does
    on dict values, rather than inventing a new action for something the
    framework already supports."""
    if not isinstance(value, ast.Subscript):
        return None
    result = _expr_to_source_and_field(value)
    if result is None:
        return None
    from_var, field = result
    return {"action": "test.extract", "field": field, "from": from_var, "store_as": store_as}


def _match_json_parse(value: ast.AST, store_as: str) -> Optional[List[Dict]]:
    """x = json.loads(y)  ->  json.parse.

    If y is a plain name/literal/${var}-representable expression, this is
    one step. If y is itself a dict-key chain that needs test.extract first
    (the common `json.loads(last_response["body"])` shape), this returns
    two steps — extract the field into a synthetic variable, then parse
    that — since a ${var} template can't express "one field of a dict"."""
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "loads"
            and isinstance(value.func.value, ast.Name) and value.func.value.id == "json"
            and len(value.args) == 1 and not value.keywords):
        return None
    arg = value.args[0]
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "str" and len(arg.args) == 1:
        arg = arg.args[0]

    template = _expr_to_template(arg)
    if template is not None:
        return [{"action": "json.parse", "value": template, "store_as": store_as}]

    extracted = _expr_to_source_and_field(arg)
    if extracted is not None:
        from_var, field = extracted
        tmp = f"_{store_as}_raw"
        return [
            {"action": "test.extract", "field": field, "from": from_var, "store_as": tmp},
            {"action": "json.parse", "value": f"${{{tmp}}}", "store_as": store_as},
        ]
    return None


_SIMPLIFY_MATCHERS = (
    _match_list_pick, _match_text_replace, _match_regex_extract, _match_text_format,
    _match_json_parse, _match_dict_path_extract,
)


# Mirrors easybdd.core.safe_eval.SafeEvaluator's call whitelist — kept as a
# local copy rather than an import so bdd_migrator.py stays self-contained
# regardless of caller sys.path (it has no other easybdd dependency today).
# If that whitelist changes, this must be updated too, or a condition step
# emitted here could fail at test-run time with "Method/Function call not
# allowed" even though it looked fine at migration time.
_SAFE_EVAL_BUILTINS = frozenset({
    "len", "str", "int", "float", "bool", "list", "dict", "tuple", "abs", "min", "max",
    "sum", "round", "range", "enumerate", "zip", "sorted", "reversed", "any", "all",
    "isinstance", "type",
})
_SAFE_EVAL_METHODS = frozenset({
    "get", "keys", "values", "items", "count", "index", "split", "join", "strip",
    "lower", "upper", "replace", "startswith", "endswith", "isdigit", "isalpha", "isalnum",
})


def _is_safe_eval_condition(node: ast.AST) -> bool:
    """Whether `node` would actually be accepted by the runner's condition
    evaluator — checked before committing to a real If/Else step, since
    unparsing an arbitrary test expression (e.g. one calling json.loads,
    which safe_eval explicitly rejects) would otherwise produce a condition
    that looks fine at migration time but fails at test-run time."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                if child.func.id not in _SAFE_EVAL_BUILTINS:
                    return False
            elif isinstance(child.func, ast.Attribute):
                if child.func.attr not in _SAFE_EVAL_METHODS:
                    return False
            else:
                return False
        elif isinstance(child, (ast.Import, ast.ImportFrom, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            return False
    return True


def _match_conditional_action_stmt(stmt: ast.stmt) -> Optional[Dict]:
    """Bare (non-assignment) statement of the shape:

        time.sleep(a) if <condition> else time.sleep(b)

    -> a real If/Else control-flow step with test.sleep in each branch,
    instead of an assignment-shaped rewrite (this is a statement run purely
    for its side effect, not a value being stored). The condition's own
    source text is used as-is — the runner's condition evaluator
    (easybdd.core.safe_eval) already exposes every current variable by its
    plain Python name and explicitly allows isinstance/in/and/or, so no
    ${var} templating is needed or even possible here (safe_eval parses a
    real Python expression, not a pre-substituted string). Only fires when
    ast.unparse is available (Python 3.9+) and the condition doesn't
    reference anything the caller couldn't already see as a variable.
    """
    if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.IfExp)):
        return None
    test, body, orelse = stmt.value.test, stmt.value.body, stmt.value.orelse

    def _as_sleep_step(call: ast.AST) -> Optional[Dict]:
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "sleep" and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "time" and len(call.args) == 1 and not call.keywords):
            return None
        seconds = _expr_to_template(call.args[0])
        if seconds is None:
            return None
        return {"test.sleep": {"seconds": seconds}}

    then_step = _as_sleep_step(body)
    else_step = _as_sleep_step(orelse)
    if then_step is None or else_step is None:
        return None

    if not _is_safe_eval_condition(test):
        return None  # would fail at test-run time — leave the whole block as eval.exec instead

    unparse = getattr(ast, "unparse", None)
    if unparse is None:
        return None
    try:
        condition_src = unparse(test)
    except Exception:
        return None

    return {"condition": condition_src, "then": [then_step], "else": [else_step]}


def _simplify_single_value(value: ast.AST, store_as: str) -> Optional[List[Dict]]:
    for matcher in _SIMPLIFY_MATCHERS:
        result = matcher(value, store_as)
        if result is not None:
            return result if isinstance(result, list) else [result]
    return None


def _name_unsafe_after(stmts_after: List[ast.stmt], name: str) -> bool:
    """True if `name` is read anywhere in stmts_after before being cleanly
    reassigned — i.e. it's not safe to collapse away a fused match/ternary
    that only `name` currently holds.

    This codebase reuses generic scratch names (m/date/body) across
    back-to-back upgrade/downgrade blocks in the same eval.exec — e.g.
    `m = re.search(...)` for downgrade immediately follows the upgrade
    block's fused-away `m`. A plain "is `name` referenced anywhere later"
    check would treat that fresh, unrelated reassignment as a conflicting
    use and refuse to fuse the (perfectly safe) first block. Instead, once
    a later statement rebinds `name` via a plain `name = ...` with no
    self-reference, name's earlier value has no more readers and everything
    after that point is irrelevant to this fusion's safety.
    """
    for s in stmts_after:
        read = any(
            isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)
            for n in ast.walk(s)
        )
        if read:
            return True
        rebinds = (
            isinstance(s, ast.Assign) and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name) and s.targets[0].id == name
        )
        if rebinds:
            return False
    return False


def _match_regex_ternary_fusion(
    stmt_a: ast.stmt, stmt_b: ast.stmt, stmts_after: List[ast.stmt]
) -> Optional[Dict]:
    """m = re.search(pattern, y); x = m.group(n) if m else default
    ->  a single text.regex_extract with a default, consuming both
    statements. Only fires when `m` isn't read again later before being
    reassigned — see _name_unsafe_after for why reassignment (not just any
    later reference) is the real safety boundary."""
    if not (isinstance(stmt_a, ast.Assign) and len(stmt_a.targets) == 1 and isinstance(stmt_a.targets[0], ast.Name)):
        return None
    m_name = stmt_a.targets[0].id
    search_call = stmt_a.value
    if not (isinstance(search_call, ast.Call) and isinstance(search_call.func, ast.Attribute)
            and search_call.func.attr == "search" and isinstance(search_call.func.value, ast.Name)
            and search_call.func.value.id == "re" and len(search_call.args) == 2 and not search_call.keywords):
        return None

    if not (isinstance(stmt_b, ast.Assign) and len(stmt_b.targets) == 1 and isinstance(stmt_b.targets[0], ast.Name)):
        return None
    x_name = stmt_b.targets[0].id
    if not isinstance(stmt_b.value, ast.IfExp):
        return None
    test, body, orelse = stmt_b.value.test, stmt_b.value.body, stmt_b.value.orelse
    if not (isinstance(test, ast.Name) and test.id == m_name):
        return None
    if not (isinstance(body, ast.Call) and isinstance(body.func, ast.Attribute) and body.func.attr == "group"
            and isinstance(body.func.value, ast.Name) and body.func.value.id == m_name):
        return None
    if not isinstance(orelse, ast.Constant):
        return None  # only literal defaults supported

    if _name_unsafe_after(stmts_after, m_name):
        return None  # m is read again before being reassigned — collapsing it away would change behavior

    pattern = _expr_to_template(search_call.args[0])
    source = _expr_to_template(search_call.args[1])
    if pattern is None or source is None:
        return None
    group = 0
    if body.args:
        g = _index_value(body.args[0])
        if g is None:
            return None
        group = g

    step = {"action": "text.regex_extract", "value": source, "pattern": pattern,
            "store_as": x_name, "default": orelse.value}
    if group:
        step["group"] = group
    return step


def _match_regex_strip_fusion(
    stmt_a: ast.stmt, stmt_b: ast.stmt, stmt_c: ast.stmt, stmts_after: List[ast.stmt]
) -> Optional[List[Dict]]:
    """The date-suffix version idiom seen repeatedly in this codebase's
    firmware-parsing cases:

        m = re.search(pattern, y)
        date = m.group(n) if m else default
        body = y.replace('_' + date, '') if date else y

    A regex substitution is already a no-op when nothing matches, so the
    third statement's conditional is unnecessary — this collapses all three
    into a text.regex_extract (for `date`) plus a single regex text.replace
    (for `body`, stripping "_<date>" unconditionally) instead of trying to
    preserve the ternary literally. Only fires when `m`/`date` aren't
    referenced anywhere outside these three statements.
    """
    if not (isinstance(stmt_a, ast.Assign) and len(stmt_a.targets) == 1 and isinstance(stmt_a.targets[0], ast.Name)):
        return None
    m_name = stmt_a.targets[0].id
    search_call = stmt_a.value
    if not (isinstance(search_call, ast.Call) and isinstance(search_call.func, ast.Attribute)
            and search_call.func.attr == "search" and isinstance(search_call.func.value, ast.Name)
            and search_call.func.value.id == "re" and len(search_call.args) == 2 and not search_call.keywords):
        return None
    pattern_node, source_node = search_call.args
    if not isinstance(source_node, ast.Name):
        return None  # need a plain variable name to reuse it in the strip step too
    source_name = source_node.id

    if not (isinstance(stmt_b, ast.Assign) and len(stmt_b.targets) == 1 and isinstance(stmt_b.targets[0], ast.Name)):
        return None
    date_name = stmt_b.targets[0].id
    if not isinstance(stmt_b.value, ast.IfExp):
        return None
    test_b, body_b, orelse_b = stmt_b.value.test, stmt_b.value.body, stmt_b.value.orelse
    if not (isinstance(test_b, ast.Name) and test_b.id == m_name):
        return None
    if not (isinstance(body_b, ast.Call) and isinstance(body_b.func, ast.Attribute) and body_b.func.attr == "group"
            and isinstance(body_b.func.value, ast.Name) and body_b.func.value.id == m_name):
        return None
    if not isinstance(orelse_b, ast.Constant):
        return None
    group = 0
    if body_b.args:
        g = _index_value(body_b.args[0])
        if g is None:
            return None
        group = g

    if not (isinstance(stmt_c, ast.Assign) and len(stmt_c.targets) == 1 and isinstance(stmt_c.targets[0], ast.Name)):
        return None
    body_name = stmt_c.targets[0].id
    if not isinstance(stmt_c.value, ast.IfExp):
        return None
    test_c, body_c, orelse_c = stmt_c.value.test, stmt_c.value.body, stmt_c.value.orelse
    if not (isinstance(test_c, ast.Name) and test_c.id == date_name):
        return None
    if not (isinstance(body_c, ast.Call) and isinstance(body_c.func, ast.Attribute) and body_c.func.attr == "replace"
            and isinstance(body_c.func.value, ast.Name) and body_c.func.value.id == source_name
            and len(body_c.args) == 2 and not body_c.keywords):
        return None
    strip_target = body_c.args[0]
    if not (isinstance(strip_target, ast.BinOp) and isinstance(strip_target.op, ast.Add)
            and isinstance(strip_target.left, ast.Constant) and strip_target.left.value == "_"
            and isinstance(strip_target.right, ast.Name) and strip_target.right.id == date_name):
        return None
    replace_with_node = body_c.args[1]
    if not (isinstance(replace_with_node, ast.Constant) and replace_with_node.value == ""):
        return None
    if not (isinstance(orelse_c, ast.Name) and orelse_c.id == source_name):
        return None

    # Only `m` (the raw match object) needs the safety check — it has no
    # declarative equivalent, so if something later still needed the actual
    # match object we couldn't represent that. `date`/`body` are this
    # fusion's real outputs and survive as run variables via store_as, so a
    # later read of them is exactly what's supposed to happen, not a hazard.
    if _name_unsafe_after(stmts_after, m_name):
        return None

    pattern = _expr_to_template(pattern_node)
    source = _expr_to_template(source_node)
    if pattern is None or source is None:
        return None

    extract_step = {"action": "text.regex_extract", "value": source, "pattern": pattern,
                     "store_as": date_name, "default": orelse_b.value}
    if group:
        extract_step["group"] = group
    strip_step = {"action": "text.replace", "value": source, "find": "_" + pattern,
                  "regex": True, "replace_with": "", "store_as": body_name}
    return [extract_step, strip_step]


def _simplify_exec_code(code: str) -> Optional[List[Dict]]:
    """Try to convert a full eval.exec code block (semicolon-joined
    statements — this codebase's convention for multi-statement eval.exec,
    since embedded newlines get YAML-folded to spaces) into a list of
    declarative steps.

    Returns None (leave the original eval.exec untouched) if ANY statement
    fails to match a known idiom — see the module docstring above this
    section for why partial transformation isn't attempted.
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return None
    stmts = tree.body
    if not stmts:
        return None

    results: List[Dict] = []
    i, n = 0, len(stmts)
    while i < n:
        if i + 2 < n:
            fused3 = _match_regex_strip_fusion(stmts[i], stmts[i + 1], stmts[i + 2], stmts[i + 3:])
            if fused3 is not None:
                results.extend(fused3)
                i += 3
                continue
        if i + 1 < n:
            fused = _match_regex_ternary_fusion(stmts[i], stmts[i + 1], stmts[i + 2:])
            if fused is not None:
                results.append(fused)
                i += 2
                continue
        stmt = stmts[i]
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            simplified = _simplify_single_value(stmt.value, stmt.targets[0].id)
            if simplified is not None:
                results.extend(simplified)
                i += 1
                continue
        cond_step = _match_conditional_action_stmt(stmt)
        if cond_step is not None:
            results.append(cond_step)
            i += 1
            continue
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            # Safe to drop unconditionally: this only reaches the caller as
            # part of a fully-simplified block (we bail on the whole thing
            # below otherwise), so nothing declarative we emitted needs the
            # module — it was only ever needed by raw code we're replacing.
            i += 1
            continue
        return None  # this statement doesn't match anything -- bail on the whole block
    return results


def _try_simplify_eval_step(step: Dict) -> Optional[List[Dict]]:
    """If `step` is a dot-notation eval.exec/eval.run step that matches a
    known idiom, return the declarative dot-notation step(s) to replace it
    with. Returns None if it doesn't match anything (leave as-is)."""
    if "eval.exec" in step:
        code = str((step.get("eval.exec") or {}).get("code", ""))
        new_steps = _simplify_exec_code(code)
        if new_steps is None:
            return None
        return [_to_dot_notation(s) for s in new_steps]
    if "eval.run" in step:
        params = step.get("eval.run") or {}
        expr = str(params.get("expression") or params.get("code") or "")
        store_as = str(params.get("store_as", ""))
        if not expr or not store_as:
            return None
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError:
            return None
        simplified = _simplify_single_value(tree.body, store_as)
        if simplified is None:
            return None
        return [_to_dot_notation(s) for s in simplified]
    return None


def _simplify_eval_steps(steps: List[Dict]) -> List[Dict]:
    """Walk a step list, recursing into control-flow bodies, replacing any
    eval.exec/eval.run step that matches a recognized idiom with the
    equivalent declarative step(s). Everything else passes through
    unchanged."""
    out: List[Dict] = []
    for step in steps:
        if not isinstance(step, dict):
            out.append(step)
            continue
        for key in ("steps", "loop_steps", "then_steps", "else_steps", "except_steps", "finally_steps"):
            if isinstance(step.get(key), list):
                step[key] = _simplify_eval_steps(step[key])
        replacement = _try_simplify_eval_step(step)
        out.extend(replacement if replacement is not None else [step])
    return out


def _count_unsimplified_eval(steps: List[Dict]) -> int:
    n = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        if "eval.exec" in step or "eval.run" in step:
            n += 1
        for key in ("steps", "loop_steps", "then_steps", "else_steps", "except_steps", "finally_steps"):
            if isinstance(step.get(key), list):
                n += _count_unsimplified_eval(step[key])
    return n


def _flag_unsimplified_eval(steps: List[Dict], test_name: str, warnings: List[str]) -> None:
    n = _count_unsimplified_eval(steps)
    if n:
        warnings.append(
            f"Test '{test_name}': {n} eval.exec/eval.run step(s) didn't match a known "
            f"simplification pattern and were left as-is — review manually."
        )


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
    Leaves special structures (shared_step, condition, etc.) untouched.
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
