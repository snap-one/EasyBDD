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
from .selector_ranker import best_selector


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
        GeneratedStep(action="browser.fill",
                      params={"selector": _sel(username_el), "value": "${username}"},
                      description="Enter username / email"),
        GeneratedStep(action="browser.fill",
                      params={"selector": _sel(password_el), "value": "${password}"},
                      description="Enter password"),
    ]
    if submit_el:
        happy_steps.append(
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(submit_el)},
                          description="Click login button")
        )
    happy_steps.append(_screenshot_step("after-login"))
    happy_steps.append(
        GeneratedStep(action="browser.assert_text",
                      params={"selector": "body", "text": "${expected_title}"},
                      description="Verify successful login")
    )

    # Empty fields validation
    empty_steps = [
        _open_step(url),
    ]
    if submit_el:
        empty_steps.append(
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(submit_el)},
                          description="Click login without filling fields")
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
        GeneratedStep(action="browser.fill",
                      params={"selector": _sel(email_el), "value": "${new_email}"},
                      description="Enter email address"),
        GeneratedStep(action="browser.fill",
                      params={"selector": _sel(password_el), "value": "${new_password}"},
                      description="Enter password"),
    ]
    if confirm_el:
        steps.append(
            GeneratedStep(action="browser.fill",
                          params={"selector": _sel(confirm_el), "value": "${new_password}"},
                          description="Confirm password")
        )
    if submit_el:
        steps.append(
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(submit_el)},
                          description="Submit registration")
        )
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
        GeneratedStep(action="browser.fill",
                      params={"selector": _sel(search_el), "value": "${search_term}"},
                      description="Enter search term"),
    ]
    if submit_el:
        steps.append(
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(submit_el)},
                          description="Submit search")
        )
    else:
        steps.append(
            GeneratedStep(action="browser.press_key",
                          params={"key": "Enter", "selector": _sel(search_el)},
                          description="Submit search via Enter")
        )
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
        steps = [
            _open_step(url),
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(el)},
                          description=f"Click '{label}' navigation link"),
            GeneratedStep(action="browser.get_title",
                          params={"store_as": "page_title"},
                          description="Capture page title"),
            _screenshot_step(f"nav-{re.sub(r'[^a-z0-9]', '-', label.lower())[:20]}"),
        ]
        cases.append(
            GeneratedTestCase(
                name=f"Navigation — {label}",
                description=f"Verify '{label}' navigation link loads the correct page",
                tags=["browser", "navigation"],
                url=url,
                steps=steps,
            )
        )
    return cases


def _build_settings_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    """
    For settings forms: generate a before/after assertion pattern for each field.
    Also generates a "save all fields" happy-path test.
    """
    input_els = [el for el in pattern.elements if _is_input(el)]
    submit_el = next((el for el in pattern.elements if _is_button(el)), None)

    # Happy path — fill all fields + save
    fill_steps = [_open_step(url)]
    for i, el in enumerate(input_els):
        var = f"${{field_{i+1}_value}}"
        if (el.type or "text").lower() == "select":
            fill_steps.append(
                GeneratedStep(action="browser.select",
                              params={"selector": _sel(el), "value": var},
                              description=f"Set field {i+1}")
            )
        else:
            fill_steps.append(
                GeneratedStep(action="browser.fill",
                              params={"selector": _sel(el), "value": var},
                              description=f"Fill field {i+1}")
            )
    if submit_el:
        fill_steps.append(
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(submit_el)},
                          description="Save settings")
        )
    fill_steps.append(_screenshot_step("settings-saved"))
    cases = [
        GeneratedTestCase(
            name="Settings — save all fields",
            description="Verify settings form submits successfully with valid values",
            tags=["browser", "settings", "smoke"],
            url=url,
            steps=fill_steps,
        )
    ]

    # Before/after pattern for the first editable text field
    text_inputs = [el for el in input_els if (el.type or "text").lower() in ("text", "number", "email", "url", "tel")]
    if text_inputs and submit_el:
        el = text_inputs[0]
        ba_steps = [
            _open_step(url),
            GeneratedStep(action="browser.get_text",
                          params={"selector": _sel(el), "store_as": "original_value"},
                          description="Capture current field value before change"),
            GeneratedStep(action="browser.fill",
                          params={"selector": _sel(el), "value": "${new_value}"},
                          description="Enter new value"),
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(submit_el)},
                          description="Save the change"),
            GeneratedStep(action="browser.assert_text",
                          params={"selector": _sel(el), "text": "${new_value}"},
                          description="Verify new value persisted after save"),
            _screenshot_step("after-config-change"),
        ]
        cases.append(
            GeneratedTestCase(
                name="Settings — before/after config change",
                description="Verify a config field value updates correctly after save",
                tags=["browser", "settings", "regression"],
                url=url,
                steps=ba_steps,
            )
        )
    return cases


def _build_file_upload_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    el = pattern.elements[0]
    steps = [
        _open_step(url),
        GeneratedStep(action="browser.upload",
                      params={"selector": _sel(el), "file_path": "${upload_file_path}"},
                      description="Upload a test file"),
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
        steps = [
            _open_step(url),
            GeneratedStep(
                action="browser.click",
                params={"selector": _sel(el)},
                description=f"Click '{label}'",
            ),
            _screenshot_step(f"after-{slug}"),
        ]
        cases.append(
            GeneratedTestCase(
                name=f"Click — {label}",
                description=f"Verify clicking '{label}' works without errors",
                tags=["browser", "smoke"],
                url=url,
                steps=steps,
            )
        )
    return cases


def _build_generic_input_cases(pattern: _PatternMatch, url: str) -> List[GeneratedTestCase]:
    """Generate a single 'fill all inputs' interaction test."""
    fill_steps = [_open_step(url)]
    for i, el in enumerate(pattern.elements):
        label = (el.name or el.placeholder or el.label or el.aria_label or f"field {i+1}").strip()
        var = f"${{field_{i+1}_value}}"
        tag_type = (el.type or el.tag or "text").lower()
        if tag_type == "select" or el.tag == "select":
            fill_steps.append(
                GeneratedStep(
                    action="browser.select",
                    params={"selector": _sel(el), "value": var},
                    description=f"Select value for '{label}'",
                )
            )
        elif tag_type in ("checkbox", "radio"):
            fill_steps.append(
                GeneratedStep(
                    action="browser.click",
                    params={"selector": _sel(el)},
                    description=f"Toggle '{label}'",
                )
            )
        else:
            fill_steps.append(
                GeneratedStep(
                    action="browser.fill",
                    params={"selector": _sel(el), "value": var},
                    description=f"Fill '{label}'",
                )
            )
    fill_steps.append(_screenshot_step("inputs-filled"))
    return [
        GeneratedTestCase(
            name="Form — fill all inputs",
            description="Verify all form inputs accept values without errors",
            tags=["browser", "smoke"],
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
            GeneratedStep(action="browser.click",
                          params={"selector": _sel(el)},
                          description=f"Open '{label}' dialog"),
            GeneratedStep(action="browser.wait_for_element",
                          params={"selector": "[role='dialog'], .modal, .dialog",
                                  "timeout": 5},
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
                action="browser.assert_text",
                params={"selector": "h1, h2, title", "text": expected},
                description=f"Verify page heading: '{expected}'",
            )
            if expected
            else GeneratedStep(
                action="browser.assert_url",
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
