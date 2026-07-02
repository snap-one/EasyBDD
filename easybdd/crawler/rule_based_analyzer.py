"""
Rule-based page analyzer — generates Easy BDD test cases purely from DOM structure.

No AI, no API keys, no cost. Works by detecting well-known UI patterns in the
element list and emitting a standard set of test steps for each.

Patterns detected (in priority order):
  1. Login form          — email/username + password + submit
  2. Registration form   — email + password + confirm + submit
  3. Search form         — search input + submit
  4. Settings/config form— any multi-field form that isn't login/registration
  5. Navigation menu     — nav links / tab bars
  6. Data table          — table with rows (generate a "verify table renders" test)
  7. File upload         — input[type=file]
  8. Modal triggers      — buttons whose text suggests opening a dialog
  9. Generic buttons     — any remaining prominent buttons

For settings forms the analyzer also generates a before/after config-change pattern:
  1. get_text (store current value)
  2. fill new value
  3. submit
  4. assert_text (verify the new value persisted)

Output: list of GeneratedTestCase — same type used by the AI path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import ElementSnapshot, GeneratedStep, GeneratedTestCase, PageSnapshot
from .selector_ranker import best_selector, rank_selectors


# ── Keyword sets ──────────────────────────────────────────────────────────────

_LOGIN_KEYWORDS    = {"login", "log in", "sign in", "signin", "email", "username", "user name"}
_PASSWORD_KEYWORDS = {"password", "pass", "passwd", "secret", "passphrase"}
_CONFIRM_KEYWORDS  = {"confirm", "repeat", "retype", "re-enter", "verify"}
_SEARCH_KEYWORDS   = {"search", "query", "find", "filter", "keyword", "q"}
_SUBMIT_KEYWORDS   = {"submit", "save", "apply", "update", "create", "add", "ok", "confirm",
                      "continue", "next", "proceed", "send", "upload", "login", "log in",
                      "sign in", "register", "sign up"}
_MODAL_KEYWORDS    = {"new", "add", "create", "edit", "delete", "remove", "configure",
                      "settings", "manage", "import", "export"}
_NAV_KEYWORDS      = {"nav", "navigation", "menu", "sidebar", "tab", "tabs", "header"}

# Common success message patterns seen after form saves
_SUCCESS_SELECTOR = (
    "text=/saved|applied|success|updated|complete|enabled|disabled/i, "
    ".success, .alert-success, .toast, .notification, [role='status'], [role='alert']"
)
_ERROR_SELECTOR = (
    ".error, .alert-danger, .alert-error, [role='alert'], "
    "text=/error|failed|invalid|required/i"
)


def _infer_test_value(el: ElementSnapshot) -> str:
    """Return a realistic test value based on the element's label, type, and context."""
    hint = _el_hint(el)
    el_type = (el.type or el.tag or "text").lower()

    # Type-driven first
    if el_type == "email":
        return "testuser@example.com"
    if el_type == "password":
        return "TestPass123!"
    if el_type == "url":
        return "https://example.com"
    if el_type == "tel":
        return "555-0100"
    if el_type == "color":
        return "#336699"

    # Number types — infer from hint
    if el_type in ("number", "range"):
        if any(k in hint for k in ("port",)):
            return "8080"
        if any(k in hint for k in ("vlan",)):
            return "100"
        if any(k in hint for k in ("timeout", "interval", "ttl", "retry", "retries")):
            return "30"
        if any(k in hint for k in ("mtu",)):
            return "1500"
        if any(k in hint for k in ("channel",)):
            return "6"
        return "1"

    # Label/hint-driven for text-like types
    if any(k in hint for k in ("ssid", "network name", "wifi name", "wlan name")):
        return "TestNetwork_5G"
    if any(k in hint for k in ("psk", "pre-shared", "wifi password", "wi-fi password", "passphrase")):
        return "TestWifi@Pass1"
    if any(k in hint for k in ("hostname", "host name", "device name", "system name")):
        return "test-device-01"
    if any(k in hint for k in ("ip address", "ipv4", "ip addr")):
        return "192.168.1.100"
    if any(k in hint for k in ("gateway", "default gateway", "router ip")):
        return "192.168.1.1"
    if any(k in hint for k in ("subnet", "netmask", "network mask")):
        return "255.255.255.0"
    if any(k in hint for k in ("dns", "nameserver", "name server")):
        return "8.8.8.8"
    if any(k in hint for k in ("ntp", "time server")):
        return "pool.ntp.org"
    if any(k in hint for k in ("username", "user name", "login name", "account")):
        return "testuser"
    if any(k in hint for k in ("password", "pass", "passwd", "secret")):
        return "TestPass123!"
    if any(k in hint for k in ("email",)):
        return "test@example.com"
    if any(k in hint for k in ("port",)):
        return "8080"
    if any(k in hint for k in ("vlan",)):
        return "100"
    if any(k in hint for k in ("mtu",)):
        return "1500"
    if any(k in hint for k in ("timeout", "interval")):
        return "30"
    if any(k in hint for k in ("name", "label", "title", "description")):
        return "Test Item"
    if any(k in hint for k in ("path", "directory", "folder")):
        return "/test/path"
    if any(k in hint for k in ("url", "endpoint", "address")):
        return "https://example.com"
    if any(k in hint for k in ("key", "token", "secret", "api")):
        return "test_api_key_12345"
    if any(k in hint for k in ("comment", "note", "description", "message", "body")):
        return "Automated test comment"

    # Fallback
    return "test_value"


def _infer_invalid_value(el: ElementSnapshot) -> str:
    """Return a value that should fail validation for this field."""
    hint = _el_hint(el)
    el_type = (el.type or el.tag or "text").lower()

    if el_type == "email":
        return "not-an-email"
    if el_type == "number":
        return "abc"
    if el_type == "url":
        return "not-a-url"

    if any(k in hint for k in ("ip address", "ipv4", "ip addr")):
        return "999.999.999.999"
    if any(k in hint for k in ("port",)):
        return "99999"
    if any(k in hint for k in ("subnet", "netmask")):
        return "999.0.0.0"
    if any(k in hint for k in ("vlan",)):
        return "9999"

    return ""  # empty = common invalid value for required fields


def _el_hint(el: ElementSnapshot) -> str:
    """Combine all text clues into a lower-case hint string."""
    parts = [
        el.name or "",
        el.label or "",
        el.placeholder or "",
        el.aria_label or "",
        el.text or "",
        el.id or "",
        el.css_class or "",
        el.data_testid or "",
    ]
    return " ".join(p for p in parts if p).lower()


def _matches(el: ElementSnapshot, keywords: set) -> bool:
    hint = _el_hint(el)
    return any(kw in hint for kw in keywords)


def _is_input(el: ElementSnapshot, *types) -> bool:
    if el.tag not in ("input", "textarea", "select"):
        return False
    if not types:
        return True
    el_type = (el.type or "text").lower()
    return el_type in types


def _is_button(el: ElementSnapshot) -> bool:
    if el.tag == "button":
        return True
    if el.tag == "input" and (el.type or "").lower() in ("submit", "button"):
        return True
    if el.role in ("button",):
        return True
    return False


def _sel(el: ElementSnapshot) -> str:
    return best_selector(el)


def _step(
    action: str,
    el: ElementSnapshot,
    extra_params: Optional[Dict] = None,
    description: str = "",
) -> GeneratedStep:
    """
    Build a GeneratedStep for *el* and populate ALL ranked selector candidates
    so the test runner (and TestRail) can cycle through fallbacks automatically.
    """
    ranked = rank_selectors(el)
    primary = _sel(el)   # already handles iframe prefix
    params: Dict = {"selector": primary}
    if extra_params:
        params.update(extra_params)
    return GeneratedStep(
        action=action,
        params=params,
        description=description,
        selectors=ranked,
    )


# ── Pattern detectors ─────────────────────────────────────────────────────────

@dataclass
class _PatternMatch:
    name: str
    elements: List[ElementSnapshot] = field(default_factory=list)
    score: int = 0  # higher = more confident match


def _detect_login(elements: List[ElementSnapshot]) -> Optional[_PatternMatch]:
    """Find username/email + password inputs + submit button."""
    username_el: Optional[ElementSnapshot] = None
    password_el: Optional[ElementSnapshot] = None
    submit_el:   Optional[ElementSnapshot] = None

    for el in elements:
        if _is_input(el, "email", "text") and _matches(el, _LOGIN_KEYWORDS) and not username_el:
            username_el = el
        elif _is_input(el, "password") and not password_el:
            password_el = el
        elif _is_button(el) and _matches(el, {"login", "log in", "sign in", "signin", "submit"}) and not submit_el:
            submit_el = el

    if username_el and password_el:
        matched = [e for e in (username_el, password_el, submit_el) if e]
        return _PatternMatch(name="Login form", elements=matched, score=10)
    return None


def _detect_registration(elements: List[ElementSnapshot]) -> Optional[_PatternMatch]:
    email_el:    Optional[ElementSnapshot] = None
    password_el: Optional[ElementSnapshot] = None
    confirm_el:  Optional[ElementSnapshot] = None
    submit_el:   Optional[ElementSnapshot] = None

    for el in elements:
        if _is_input(el, "email", "text") and _matches(el, {"email"}) and not email_el:
            email_el = el
        elif _is_input(el, "password"):
            if _matches(el, _CONFIRM_KEYWORDS) and not confirm_el:
                confirm_el = el
            elif not password_el:
                password_el = el
        elif _is_button(el) and _matches(el, {"register", "sign up", "create account", "join"}) and not submit_el:
            submit_el = el

    if email_el and password_el and confirm_el:
        matched = [e for e in (email_el, password_el, confirm_el, submit_el) if e]
        return _PatternMatch(name="Registration form", elements=matched, score=9)
    return None


def _detect_search(elements: List[ElementSnapshot]) -> Optional[_PatternMatch]:
    search_el: Optional[ElementSnapshot] = None
    submit_el: Optional[ElementSnapshot] = None

    for el in elements:
        if _is_input(el, "search", "text") and _matches(el, _SEARCH_KEYWORDS) and not search_el:
            search_el = el
        elif _is_button(el) and _matches(el, {"search", "find", "go", "submit"}) and not submit_el:
            submit_el = el

    if search_el:
        matched = [e for e in (search_el, submit_el) if e]
        return _PatternMatch(name="Search", elements=matched, score=7)
    return None


def _detect_nav(elements: List[ElementSnapshot]) -> Optional[_PatternMatch]:
    nav_links = [
        el for el in elements
        if el.tag == "a" and el.href and el.text and len(el.text.strip()) > 1
        and not el.text.strip().lower() in ("back", "cancel", "close", "home")
    ]
    if len(nav_links) >= 3:
        return _PatternMatch(name="Navigation links", elements=nav_links[:8], score=5)
    return None


def _detect_settings_form(
    elements: List[ElementSnapshot],
    exclude_els: set,
) -> Optional[_PatternMatch]:
    """Any multi-field form that wasn't already matched as login/registration."""
    form_inputs = [
        el for el in elements
        if _is_input(el) and id(el) not in exclude_els
        and (el.type or "text").lower() not in ("hidden", "file")
    ]
    submit_el = next(
        (el for el in elements
         if _is_button(el) and _matches(el, _SUBMIT_KEYWORDS) and id(el) not in exclude_els),
        None,
    )
    if len(form_inputs) >= 2:
        matched = form_inputs[:6] + ([submit_el] if submit_el else [])
        return _PatternMatch(name="Settings / config form", elements=matched, score=6)
    return None


def _detect_file_upload(elements: List[ElementSnapshot]) -> Optional[_PatternMatch]:
    uploads = [el for el in elements if el.tag == "input" and (el.type or "").lower() == "file"]
    if uploads:
        return _PatternMatch(name="File upload", elements=uploads[:2], score=4)
    return None


def _detect_modal_triggers(elements: List[ElementSnapshot]) -> Optional[_PatternMatch]:
    triggers = [
        el for el in elements
        if _is_button(el) and _matches(el, _MODAL_KEYWORDS)
    ]
    if triggers:
        return _PatternMatch(name="Modal / dialog triggers", elements=triggers[:5], score=3)
    return None


# ── Step builders ─────────────────────────────────────────────────────────────

def _screenshot_step(name: str) -> GeneratedStep:
    return GeneratedStep(action="browser.screenshot", params={"name": name})


def _open_step(url: str) -> GeneratedStep:
    return GeneratedStep(action="browser.open", params={"url": "${base_url}"})


def _build_login_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    els = pattern.elements
    username_el = els[0]
    password_el = els[1]
    submit_el   = els[2] if len(els) > 2 else None

    # Happy path
    happy_steps = [
        _open_step(url),
        _step("browser.fill", username_el, {"value": "${username}"}, "Enter username / email"),
        _step("browser.fill", password_el, {"value": "${password}"}, "Enter password"),
    ]
    if submit_el:
        happy_steps.append(_step("browser.click", submit_el, {}, "Click login button"))
    happy_steps.append(_screenshot_step("after-login"))
    happy_steps.append(
        GeneratedStep(action="test.assert_text_contains",
                      params={"selector": "body", "text": "${expected_title}"},
                      description="Verify successful login")
    )

    # Empty fields validation
    empty_steps = [_open_step(url)]
    if submit_el:
        empty_steps.append(
            _step("browser.click", submit_el, {}, "Click login without filling fields")
        )
    empty_steps.append(_screenshot_step("empty-fields-error"))

    return [
        GeneratedTestCase(
            name="Login — happy path",
            description="Verify a user can log in with valid credentials",
            tags=["browser", "smoke", "auth"],
            url=url,
            steps=happy_steps,
        ),
        GeneratedTestCase(
            name="Login — empty fields validation",
            description="Verify login form shows errors when fields are empty",
            tags=["browser", "validation", "auth"],
            url=url,
            steps=empty_steps,
        ),
    ]


def _build_registration_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    els = pattern.elements
    email_el    = els[0]
    password_el = els[1]
    confirm_el  = els[2] if len(els) > 2 else None
    submit_el   = els[3] if len(els) > 3 else None

    steps = [
        _open_step(url),
        _step("browser.fill", email_el, {"value": "${new_email}"}, "Enter email address"),
        _step("browser.fill", password_el, {"value": "${new_password}"}, "Enter password"),
    ]
    if confirm_el:
        steps.append(_step("browser.fill", confirm_el, {"value": "${new_password}"}, "Confirm password"))
    if submit_el:
        steps.append(_step("browser.click", submit_el, {}, "Submit registration"))
    steps.append(_screenshot_step("after-registration"))

    return [
        GeneratedTestCase(
            name="Registration — create new account",
            description="Verify a new user can register successfully",
            tags=["browser", "smoke", "auth"],
            url=url,
            steps=steps,
        )
    ]


def _build_search_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    search_el = pattern.elements[0]
    submit_el = pattern.elements[1] if len(pattern.elements) > 1 else None

    steps = [
        _open_step(url),
        _step("browser.fill", search_el, {"value": "${search_term}"}, "Enter search term"),
    ]
    if submit_el:
        steps.append(_step("browser.click", submit_el, {}, "Submit search"))
    else:
        steps.append(_step("browser.press_key", search_el, {"key": "Enter"}, "Submit search via Enter"))
    steps.append(_screenshot_step("search-results"))

    return [
        GeneratedTestCase(
            name="Search — basic query",
            description="Verify the search feature returns results",
            tags=["browser", "smoke", "search"],
            url=url,
            steps=steps,
        )
    ]


def _build_nav_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    cases = []
    for el in pattern.elements[:5]:  # cap at 5 nav items
        label = (el.text or el.name or el.aria_label or "unknown").strip()
        slug = re.sub(r"[^a-z0-9]", "-", label.lower())[:20]
        steps = [
            _open_step(url),
            _step("browser.click", el, {}, f"Click '{label}' navigation link"),
            GeneratedStep(
                action="browser.wait_for_url",
                params={"timeout": 5000},
                description="Wait for page navigation to complete",
            ),
            GeneratedStep(
                action="test.assert_element_visible",
                params={"selector": "h1, h2, main, [role='main']"},
                description="Verify page content loaded after navigation",
            ),
            _screenshot_step(f"nav-{slug}"),
        ]
        cases.append(
            GeneratedTestCase(
                name=f"Navigation — {label}",
                description=f"Verify '{label}' navigation link loads the page without errors",
                tags=["browser", "navigation"],
                url=url,
                steps=steps,
            )
        )
    return cases


def _build_settings_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    """
    Generate functional test cases for settings/config forms:
      1. Per-field test with realistic values + save + success verification
      2. Full-form save with all fields filled
      3. Required-field validation (if required fields found)
      4. Select/dropdown option tests
    """
    input_els = [el for el in pattern.elements if _is_input(el)]
    submit_el = next((el for el in pattern.elements if _is_button(el)), None)
    cases: List[GeneratedTestCase] = []

    # ── Per-field functional tests ────────────────────────────────────────────
    text_inputs = [
        el for el in input_els
        if (el.type or "text").lower() in ("text", "number", "email", "url", "tel", "password", "search")
        and el.tag != "select"
    ]
    for el in text_inputs[:4]:  # cap at 4 individual field tests
        label = (el.name or el.label or el.placeholder or el.aria_label or el.id or "field").strip()
        slug = re.sub(r"[^a-z0-9]", "-", label.lower())[:24]
        test_val = _infer_test_value(el)

        field_steps = [_open_step(url)]
        # Clear and fill the field
        field_steps.append(_step("browser.fill", el, {"value": ""}, f"Clear '{label}' field"))
        field_steps.append(_step("browser.fill", el, {"value": test_val}, f"Enter test value '{test_val}' into '{label}'"))
        if submit_el:
            field_steps.append(_step("browser.click", submit_el, {}, "Click save/apply"))
            field_steps.append(
                GeneratedStep(
                    action="browser.wait_for",
                    params={"selector": _SUCCESS_SELECTOR, "timeout": 10000},
                    description="Wait for save confirmation",
                )
            )
        field_steps.append(_screenshot_step(f"save-{slug}"))
        # Reload and verify value persisted
        if submit_el and el.type not in ("password",):
            field_steps.append(
                GeneratedStep(action="browser.open", params={"url": "${base_url}"}, description="Reload page to verify persistence")
            )
            field_steps.append(
                _step("test.assert_value", el, {"value": test_val}, f"Verify '{label}' value persisted after save")
            )

        cases.append(GeneratedTestCase(
            name=f"Settings — configure {label}",
            description=f"Verify '{label}' can be set to '{test_val}' and saved successfully",
            tags=["browser", "settings", "functional"],
            url=url,
            steps=field_steps,
        ))

    # ── Select / dropdown tests ───────────────────────────────────────────────
    select_els = [el for el in input_els if el.tag == "select" or el.type == "select"]
    for el in select_els[:3]:
        label = (el.name or el.label or el.aria_label or el.id or "dropdown").strip()
        slug = re.sub(r"[^a-z0-9]", "-", label.lower())[:24]
        opts = el.options or []
        # Test with each non-default option (up to 3)
        test_opts = [o for o in opts if o.get("value", "") not in ("", "0", "none", "null")][:3]
        for opt in test_opts:
            opt_val = opt.get("value", "")
            opt_text = opt.get("text", opt_val)
            opt_slug = re.sub(r"[^a-z0-9]", "-", opt_text.lower())[:20]
            sel_steps = [
                _open_step(url),
                _step("browser.select", el, {"value": opt_val}, f"Select '{opt_text}' from '{label}'"),
            ]
            if submit_el:
                sel_steps.append(_step("browser.click", submit_el, {}, "Save selection"))
                sel_steps.append(GeneratedStep(
                    action="browser.wait_for",
                    params={"selector": _SUCCESS_SELECTOR, "timeout": 10000},
                    description="Wait for save confirmation",
                ))
            sel_steps.append(_screenshot_step(f"select-{slug}-{opt_slug}"))
            cases.append(GeneratedTestCase(
                name=f"Settings — set {label} to {opt_text}",
                description=f"Verify selecting '{opt_text}' for '{label}' can be saved",
                tags=["browser", "settings", "functional"],
                url=url,
                steps=sel_steps,
            ))

    # ── Full form save (all fields together) ─────────────────────────────────
    if input_els and submit_el:
        fill_steps = [_open_step(url)]
        for el in input_els:
            label = (el.name or el.label or el.placeholder or el.id or "field").strip()
            el_type = (el.type or el.tag or "text").lower()
            if el.tag == "select" or el_type == "select":
                opts = el.options or []
                first_opt = next((o["value"] for o in opts if o.get("value", "") not in ("", "0")), None)
                if first_opt:
                    fill_steps.append(_step("browser.select", el, {"value": first_opt}, f"Select option for '{label}'"))
            elif el_type in ("checkbox", "radio"):
                fill_steps.append(_step("browser.click", el, {}, f"Check '{label}'"))
            else:
                val = _infer_test_value(el)
                fill_steps.append(_step("browser.fill", el, {"value": val}, f"Fill '{label}' with '{val}'"))
        fill_steps.append(_step("browser.click", submit_el, {}, "Save all settings"))
        fill_steps.append(GeneratedStep(
            action="browser.wait_for",
            params={"selector": _SUCCESS_SELECTOR, "timeout": 10000},
            description="Verify save was successful",
        ))
        fill_steps.append(_screenshot_step("settings-saved-all"))
        cases.append(GeneratedTestCase(
            name="Settings — save all fields",
            description="Verify all form fields accept valid values and save without errors",
            tags=["browser", "settings", "smoke"],
            url=url,
            steps=fill_steps,
        ))

    # ── Required field validation ─────────────────────────────────────────────
    required_els = [el for el in text_inputs if el.required]
    if required_els and submit_el:
        val_steps = [_open_step(url)]
        for el in required_els[:2]:
            label = (el.name or el.label or el.placeholder or el.id or "field").strip()
            val_steps.append(_step("browser.fill", el, {"value": ""}, f"Clear required field '{label}'"))
        val_steps.append(_step("browser.click", submit_el, {}, "Attempt save with empty required fields"))
        val_steps.append(GeneratedStep(
            action="browser.wait_for",
            params={"selector": _ERROR_SELECTOR, "timeout": 5000},
            description="Verify validation error appears for empty required fields",
        ))
        val_steps.append(_screenshot_step("validation-required-empty"))
        cases.append(GeneratedTestCase(
            name="Settings — required field validation",
            description="Verify form shows errors when required fields are left empty",
            tags=["browser", "settings", "validation"],
            url=url,
            steps=val_steps,
        ))

    # ── Invalid value validation ──────────────────────────────────────────────
    invalid_candidates = [
        el for el in text_inputs
        if _infer_invalid_value(el) not in ("", _infer_test_value(el))
    ]
    if invalid_candidates and submit_el:
        inv_el = invalid_candidates[0]
        label = (inv_el.name or inv_el.label or inv_el.placeholder or inv_el.id or "field").strip()
        bad_val = _infer_invalid_value(inv_el)
        inv_steps = [
            _open_step(url),
            _step("browser.fill", inv_el, {"value": bad_val}, f"Enter invalid value '{bad_val}' for '{label}'"),
            _step("browser.click", submit_el, {}, "Attempt save with invalid value"),
            GeneratedStep(
                action="browser.wait_for",
                params={"selector": _ERROR_SELECTOR, "timeout": 5000},
                description=f"Verify error shown for invalid '{label}' value",
            ),
            _screenshot_step(f"validation-invalid-{re.sub(r'[^a-z0-9]', '-', label.lower())[:20]}"),
        ]
        cases.append(GeneratedTestCase(
            name=f"Settings — invalid {label} rejected",
            description=f"Verify the form rejects invalid value '{bad_val}' for '{label}'",
            tags=["browser", "settings", "validation"],
            url=url,
            steps=inv_steps,
        ))

    return cases


def _build_file_upload_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    el = pattern.elements[0]
    steps = [
        _open_step(url),
        _step("browser.upload", el, {"file_path": "${upload_file_path}"}, "Upload a test file"),
        _screenshot_step("after-upload"),
    ]
    return [
        GeneratedTestCase(
            name="File upload",
            description="Verify a file can be uploaded via the upload input",
            tags=["browser", "upload"],
            url=url,
            steps=steps,
        )
    ]


def _detect_generic_buttons(
    elements: List[ElementSnapshot], exclude_els: set
) -> Optional[_PatternMatch]:
    """Catch any visible buttons not already consumed by higher-priority patterns."""
    btns = [
        el for el in elements
        if _is_button(el) and id(el) not in exclude_els
        and (el.text or el.name or el.aria_label or "").strip()
    ]
    if btns:
        return _PatternMatch(name="Generic buttons", elements=btns[:6], score=2)
    return None


def _detect_generic_inputs(
    elements: List[ElementSnapshot], exclude_els: set
) -> Optional[_PatternMatch]:
    """Catch any visible inputs / textareas / selects not already consumed."""
    inputs = [
        el for el in elements
        if _is_input(el) and id(el) not in exclude_els
        and (el.type or "text").lower() not in ("hidden", "file")
    ]
    if inputs:
        return _PatternMatch(name="Generic inputs", elements=inputs[:6], score=2)
    return None


def _build_generic_button_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    cases = []
    for el in pattern.elements[:4]:
        label = (el.text or el.name or el.aria_label or "button").strip()
        slug = re.sub(r"[^a-z0-9]", "-", label.lower())[:24]
        hint = _el_hint(el)
        is_save = any(k in hint for k in ("save", "apply", "update", "submit", "confirm"))
        is_delete = any(k in hint for k in ("delete", "remove", "reset", "clear"))

        steps = [
            _open_step(url),
            _step("browser.click", el, {}, f"Click '{label}'"),
        ]
        if is_save:
            steps.append(GeneratedStep(
                action="browser.wait_for",
                params={"selector": _SUCCESS_SELECTOR, "timeout": 10000},
                description="Verify action completed successfully",
            ))
        elif is_delete:
            # Many delete buttons open a confirmation dialog first
            steps.append(GeneratedStep(
                action="browser.wait_for",
                params={"selector": "[role='dialog'], .modal, .confirm-dialog", "timeout": 5000},
                description="Wait for confirmation dialog",
            ))
        else:
            # Generic: assert page has no JS error banner
            steps.append(GeneratedStep(
                action="test.assert_element_not_visible",
                params={"selector": ".error, .alert-danger, [role='alertdialog']"},
                description="Verify no error appeared after action",
            ))
        steps.append(_screenshot_step(f"after-{slug}"))
        cases.append(
            GeneratedTestCase(
                name=f"Button — {label}",
                description=f"Verify '{label}' button performs its action without errors",
                tags=["browser", "functional"],
                url=url,
                steps=steps,
            )
        )
    return cases


def _build_generic_input_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    """Fill each input with a realistic value and verify no error state appears."""
    fill_steps = [_open_step(url)]
    for el in pattern.elements:
        label = (el.name or el.placeholder or el.label or el.aria_label or el.id or "field").strip()
        tag_type = (el.type or el.tag or "text").lower()
        if tag_type == "select" or el.tag == "select":
            opts = el.options or []
            first_opt = next((o["value"] for o in opts if o.get("value", "") not in ("", "0")), None)
            if first_opt:
                fill_steps.append(_step("browser.select", el, {"value": first_opt}, f"Select first option for '{label}'"))
        elif tag_type in ("checkbox", "radio"):
            fill_steps.append(_step("browser.click", el, {}, f"Check '{label}'"))
        else:
            val = _infer_test_value(el)
            fill_steps.append(_step("browser.fill", el, {"value": val}, f"Fill '{label}' with '{val}'"))
    fill_steps.append(GeneratedStep(
        action="test.assert_element_not_visible",
        params={"selector": _ERROR_SELECTOR},
        description="Verify no validation errors appeared after filling fields",
    ))
    fill_steps.append(_screenshot_step("form-filled"))
    return [
        GeneratedTestCase(
            name="Form — fill all inputs",
            description="Verify all form inputs accept valid values without triggering errors",
            tags=["browser", "functional"],
            url=url,
            steps=fill_steps,
        )
    ]


def _build_modal_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    cases = []
    for el in pattern.elements[:3]:
        label = (el.text or el.name or el.aria_label or "unknown").strip()
        steps = [
            _open_step(url),
            _step("browser.click", el, {}, f"Open '{label}' dialog"),
            GeneratedStep(action="browser.wait_for",
                          params={"selector": "[role='dialog'], .modal, .dialog", "timeout": 5},
                          description="Wait for dialog to appear"),
            _screenshot_step(f"dialog-{re.sub(r'[^a-z0-9]', '-', label.lower())[:20]}"),
        ]
        cases.append(
            GeneratedTestCase(
                name=f"Modal — open '{label}'",
                description=f"Verify clicking '{label}' opens a dialog",
                tags=["browser", "modal"],
                url=url,
                steps=steps,
            )
        )
    return cases


# ── Public entry point ────────────────────────────────────────────────────────

def analyze_snapshot_rules(snapshot: PageSnapshot) -> List[GeneratedTestCase]:
    """
    Deterministically generate test cases from a PageSnapshot with no AI.

    Returns a list of GeneratedTestCase objects — same type as the AI path —
    so the rest of the pipeline (YAML writer, TestRail publisher) works unchanged.
    """
    elements = snapshot.elements
    url = snapshot.url
    cases: List[GeneratedTestCase] = []
    used_els: set = set()  # track element object ids to avoid reuse

    def _use(pattern: _PatternMatch) -> None:
        for el in pattern.elements:
            used_els.add(id(el))

    # Run detectors in priority order
    login = _detect_login(elements)
    if login:
        cases.extend(_build_login_cases(login, url))
        _use(login)

    reg = _detect_registration(elements)
    if reg:
        cases.extend(_build_registration_cases(reg, url))
        _use(reg)

    search = _detect_search(elements)
    if search:
        cases.extend(_build_search_cases(search, url))
        _use(search)

    nav = _detect_nav(elements)
    if nav:
        cases.extend(_build_nav_cases(nav, url))
        _use(nav)

    settings = _detect_settings_form(elements, used_els)
    if settings:
        cases.extend(_build_settings_cases(settings, url))
        _use(settings)

    upload = _detect_file_upload(elements)
    if upload:
        cases.extend(_build_file_upload_cases(upload, url))
        _use(upload)

    modals = _detect_modal_triggers(elements)
    if modals:
        cases.extend(_build_modal_cases(modals, url))
        _use(modals)

    # Generic fallback detectors — catch anything not matched above
    gen_btns = _detect_generic_buttons(elements, used_els)
    if gen_btns:
        cases.extend(_build_generic_button_cases(gen_btns, url))
        _use(gen_btns)

    gen_inputs = _detect_generic_inputs(elements, used_els)
    if gen_inputs:
        cases.extend(_build_generic_input_cases(gen_inputs, url))
        _use(gen_inputs)

    # Absolute last resort — page completely lacks interactive elements
    if not cases:
        # Use real page title or path as the expected text rather than a bare placeholder
        heading_el = next(
            (el for el in elements if el.tag in ("h1", "h2") and (el.text or "").strip()),
            None,
        )
        expected = (heading_el.text or "").strip() if heading_el else (snapshot.title or snapshot.path or "")
        assert_step = (
            GeneratedStep(
                action="test.assert_text_contains",
                params={"selector": "h1, h2, title", "text": expected},
                description=f"Verify page heading: '{expected}'",
            )
            if expected
            else GeneratedStep(
                action="test.assert_url",
                params={"url": url},
                description="Verify expected URL loaded",
            )
        )
        cases.append(
            GeneratedTestCase(
                name=f"Page loads — {snapshot.title or snapshot.path}",
                description=f"Verify the page at {url} loads without errors",
                tags=["browser", "smoke"],
                url=url,
                steps=[
                    _open_step(url),
                    _screenshot_step("page-load"),
                    assert_step,
                ],
            )
        )

    return cases
