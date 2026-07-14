"""
Registry sweep: every action emitted by an import converter must be
registered in the validator's ACTION_SCHEMA (and carry its required
params), otherwise imported cases fail builder lint and cannot run.

Covers:
  - easybdd/crawler/playwright_importer.py  (JS/TS Playwright tests)
  - easybdd/crawler/crx_converter.py        (Playwright codegen TS)
  - easybdd/crawler/rule_based_analyzer.py  (DOM-pattern case generator)
  - easybdd/core/recorder_converter.py      (UI recorder formats)
  - frontend/robot_migrator.py              (Robot Framework)
  - frontend/bdd_migrator.py                (legacy mybdd pipe format)
"""

import pytest

from easybdd.core.validator import ACTION_SCHEMA, _resolve_schema
from easybdd.core.recorder_converter import RecorderConverter
from easybdd.crawler.crx_converter import PlaywrightTsConverter
from easybdd.crawler.models import ElementSnapshot, PageSnapshot
from easybdd.crawler import rule_based_analyzer as rba
from easybdd.crawler.playwright_importer import parse_playwright_code
from frontend.robot_migrator import _KEYWORD_MAP, _map_keyword
from frontend.bdd_migrator import _map_browser


def _assert_step_valid(action: str, params: dict, origin: str):
    """Action must be registered and carry all schema-required params."""
    schema = _resolve_schema(action)
    assert schema is not None, (
        f"[{origin}] action '{action}' is not registered in ACTION_SCHEMA"
    )
    params = params or {}
    missing = [p for p in schema.get("required", []) if not params.get(p) and params.get(p) != 0]
    assert not missing, (
        f"[{origin}] action '{action}' missing required params {missing}: {params}"
    )


def _sweep_nested_steps(steps, origin):
    """Steps in the nested {action: params} format (crx / recorder)."""
    assert steps, f"[{origin}] fixture produced no steps"
    for step in steps:
        action = next(iter(step))
        _assert_step_valid(action, step[action] or {}, origin)


def _sweep_flat_steps(steps, origin):
    """Steps in the flat {'action': ..., 'params': {...}} format."""
    assert steps, f"[{origin}] fixture produced no steps"
    for step in steps:
        _assert_step_valid(step["action"], step.get("params", {}), origin)


# ── playwright_importer ───────────────────────────────────────────────────────

PLAYWRIGHT_JS = """
import { test, expect } from '@playwright/test';
test('full coverage', async ({ page }) => {
  await page.goto('https://example.com/login');
  await page.getByLabel('Email').fill('user@test.com');
  await page.locator('#password').type('secret');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.locator('#row').dblclick();
  await page.locator('#agree').check();
  await page.locator('#promo').uncheck();
  await page.locator('#country').selectOption('US');
  await page.locator('#search').press('Enter');
  await page.locator('#menu').hover();
  await page.locator('#comment').clear();
  await page.screenshot({ path: 'shots/final.png' });
  await page.waitForURL('**/dashboard');
  await page.waitForSelector('#main');
  await page.waitForTimeout(500);
  await expect(page.locator('#header')).toBeVisible();
  await expect(page.locator('#spinner')).toBeHidden();
  await expect(page.locator('#msg')).toContainText('Welcome');
  await expect(page.locator('#hdr')).toHaveText('Dashboard');
  await expect(page.locator('#email')).toHaveValue('user@test.com');
  await expect(page).toHaveURL('https://example.com/dashboard');
  await expect(page).toHaveTitle('Dashboard');
  await expect(page.locator('#agree')).toBeChecked();
  await expect(page.locator('#submit')).toBeEnabled();
  await expect(page.locator('#legacy')).toBeDisabled();
});
"""


class TestPlaywrightImporterActions:
    def test_all_emitted_actions_registered(self):
        results = parse_playwright_code(PLAYWRIGHT_JS)
        assert results
        for name, steps in results:
            _sweep_flat_steps(steps, f"playwright_importer:{name}")

    def test_assertions_map_to_canonical_actions(self):
        (_, steps), = parse_playwright_code(PLAYWRIGHT_JS)
        actions = {s["action"] for s in steps}
        assert "test.assert_element_visible" in actions
        assert "test.assert_element_not_visible" in actions
        assert "test.assert_value" in actions
        assert "test.assert_url" in actions
        assert "test.assert_element_enabled" in actions
        assert "test.assert_element_disabled" in actions
        assert "browser.double_click" in actions
        assert "browser.wait_for_url" in actions
        # None of the legacy invalid spellings survive
        assert not [a for a in actions if a.startswith("browser.assert_")
                    and a not in ("browser.assert_checked", "browser.assert_unchecked")]
        assert "browser.dblclick" not in actions


# ── crx_converter ─────────────────────────────────────────────────────────────

CRX_TS = """
import { test, expect } from '@playwright/test';

test('recorded flow', async ({ page }) => {
  await page.goto('https://example.com/settings');
  await page.getByRole('button', { name: 'Save' }).click();
  await page.locator('#row').dblclick();
  await page.getByLabel('Email').fill('user@test.com');
  await page.locator('#comment').clear();
  await page.locator('#country').selectOption('US');
  await page.locator('#search').press('Enter');
  await page.locator('#menu').hover();
  await page.keyboard.press('Enter');
  await page.waitForURL('**/dashboard');
  await page.waitForSelector('#main', { state: 'visible' });
  await expect(page).toHaveTitle('Dashboard');
  await expect(page).toHaveURL('**/dashboard');
  await expect(page.getByRole('link', { name: 'Devices' })).toBeVisible();
  await expect(page.getByText('Saved')).toBeHidden();
  await expect(page.locator('#chk')).toBeChecked();
  await expect(page.getByLabel('Agree')).toBeChecked();
  await expect(page.getByLabel('Email')).toBeEnabled();
  await expect(page.locator('#legacy')).toBeDisabled();
  await expect(page.locator('#msg')).toContainText('Welcome');
  await expect(page.locator('#hdr')).toHaveText('Dashboard');
  await expect(page.locator('#email')).toHaveValue('user@test.com');
});
"""


class TestCrxConverterActions:
    def test_all_emitted_actions_registered(self):
        result = PlaywrightTsConverter().convert(CRX_TS, "recorded-flow")
        _sweep_nested_steps(result["steps"], "crx_converter")

    def test_locator_fields_collapse_to_selector(self):
        result = PlaywrightTsConverter().convert(CRX_TS, "recorded-flow")
        by_action = {}
        for step in result["steps"]:
            action = next(iter(step))
            by_action.setdefault(action, []).append(step[action] or {})
        # double_click / select / assert_checked / text assertions require a
        # selector string — no role/name/label fields may leak through
        for action in ("browser.double_click", "browser.select",
                       "browser.assert_checked", "test.assert_text_contains",
                       "test.assert_value"):
            assert action in by_action, f"fixture did not produce {action}"
            for params in by_action[action]:
                assert params.get("selector"), f"{action} missing selector: {params}"
                assert not set(params) & {"role", "name", "label"}, (
                    f"{action} leaked locator fields: {params}"
                )

    def test_clear_becomes_empty_fill(self):
        result = PlaywrightTsConverter().convert(CRX_TS, "recorded-flow")
        fills = [s["browser.fill"] for s in result["steps"] if "browser.fill" in s]
        assert any(p.get("value") == "" for p in fills), "clear() did not map to empty fill"


# ── rule_based_analyzer ───────────────────────────────────────────────────────

def _el(**kw) -> ElementSnapshot:
    kw.setdefault("tag", "input")
    kw.setdefault("selectors", ["#" + (kw.get("id") or kw.get("name") or "el")])
    return ElementSnapshot(**kw)


class TestRuleBasedAnalyzerActions:
    URL = "https://example.com/app"

    def _all_cases(self):
        pm = rba._PatternMatch
        username = _el(type="email", name="email", id="email")
        password = _el(type="password", name="password", id="password")
        submit = _el(tag="button", text="Save", id="save")
        confirm = _el(type="password", name="confirm", id="confirm")
        search = _el(type="search", name="q", id="q")
        nav = [_el(tag="a", text=f"Item {i}", href=f"/item{i}", id=f"nav{i}") for i in range(3)]
        text_input = _el(type="text", name="hostname", id="hostname", required=True)
        select = _el(
            tag="select", name="mode", id="mode",
            options=[{"value": "auto", "text": "Auto"}, {"value": "manual", "text": "Manual"}],
        )
        upload = _el(type="file", name="firmware", id="firmware")
        modal_btn = _el(tag="button", text="Add Device", id="add-device")
        delete_btn = _el(tag="button", text="Delete", id="delete")
        plain_btn = _el(tag="button", text="Ping", id="ping")
        checkbox = _el(type="checkbox", name="enabled", id="enabled")

        cases = []
        cases += rba._build_login_cases(pm(name="login", elements=[username, password, submit]), self.URL)
        cases += rba._build_registration_cases(pm(name="reg", elements=[username, password, confirm, submit]), self.URL)
        cases += rba._build_search_cases(pm(name="search", elements=[search, submit]), self.URL)
        cases += rba._build_nav_cases(pm(name="nav", elements=nav), self.URL)
        cases += rba._build_settings_cases(pm(name="settings", elements=[text_input, select, submit]), self.URL)
        cases += rba._build_file_upload_cases(pm(name="upload", elements=[upload]), self.URL)
        cases += rba._build_modal_cases(pm(name="modal", elements=[modal_btn]), self.URL)
        cases += rba._build_generic_button_cases(pm(name="buttons", elements=[submit, delete_btn, plain_btn]), self.URL)
        cases += rba._build_generic_input_cases(pm(name="inputs", elements=[text_input, select, checkbox]), self.URL)
        # Bare-page fallback paths (heading present → assert_text; absent → assert_url)
        cases += rba.analyze_snapshot_rules(PageSnapshot(url=self.URL, title="", origin="https://example.com", path="/app"))
        cases += rba.analyze_snapshot_rules(PageSnapshot(url=self.URL, title="Dashboard", origin="https://example.com", path="/app"))
        return cases

    def test_all_emitted_actions_registered(self):
        cases = self._all_cases()
        assert cases
        steps = [(s.action, s.params) for c in cases for s in c.steps]
        assert steps
        for action, params in steps:
            _assert_step_valid(action, params, "rule_based_analyzer")

    def test_canonical_assertion_names(self):
        actions = {s.action for c in self._all_cases() for s in c.steps}
        assert "test.assert_text_contains" in actions
        assert "test.assert_element_visible" in actions
        assert "test.assert_element_not_visible" in actions
        assert "test.assert_value" in actions
        assert "browser.wait_for_url" in actions
        assert not [a for a in actions if a.startswith("browser.assert_")
                    and a not in ("browser.assert_checked", "browser.assert_unchecked")]


# ── recorder_converter ────────────────────────────────────────────────────────

class TestRecorderConverterActions:
    # One representative raw step per recorder action.
    RAW_STEPS = [
        {"action": "Wait for element", "selector": "#spinner", "state": "hidden"},
        {"action": "Wait for element", "role": "link", "name": "Devices", "state": "visible"},
        {"action": "Wait for element", "label": "Email"},
        {"action": "Wait for element", "text": "Welcome"},
        {"action": "Open browser", "url": "https://example.com"},
        {"action": "Click element", "role": "button", "name": "Save"},
        {"action": "Double click", "selector": "#row"},
        {"action": "Fill form field", "label": "Email", "value": "user@test.com"},
        {"action": "Hover", "selector": "#menu"},
        {"action": "Press key", "key": "Enter"},
        {"action": "Take screenshot", "name": "final"},
        {"action": "Verify text", "text": "Welcome"},
        {"action": "Select option", "selector": "#country", "value": "US"},
        {"action": "Select option", "label": "Country", "value": "US"},
        {"action": "Select option", "role": "combobox", "name": "Country", "value": "US"},
        {"action": "Scroll", "x": 0, "y": 500},
        {"action": "Switch frame", "selector": "iframe#payment"},
        {"action": "Clear field", "selector": "#comment"},
        {"action": "Drag and drop", "source": "#card", "target": "#done-column"},
    ]

    def test_all_emitted_actions_registered(self):
        conv = RecorderConverter()
        for raw in self.RAW_STEPS:
            step = conv._to_browser_step(dict(raw))
            action = next(iter(step))
            _assert_step_valid(action, step[action] or {}, f"recorder_converter:{raw['action']}")

    def test_select_option_folds_locator_fields_to_selector(self):
        conv = RecorderConverter()
        for raw in self.RAW_STEPS:
            if raw["action"] != "Select option":
                continue
            params = conv._to_browser_step(dict(raw))["browser.select"]
            assert params.get("selector"), f"select missing selector: {params}"
            assert not set(params) & {"role", "name", "label"}

    def test_wait_for_element_folds_locator_fields_to_selector(self):
        conv = RecorderConverter()
        for raw in self.RAW_STEPS:
            if raw["action"] != "Wait for element":
                continue
            step = conv._to_browser_step(dict(raw))
            assert "browser.wait_for" in step, f"expected browser.wait_for, got {step}"
            params = step["browser.wait_for"]
            assert params.get("selector"), f"wait_for missing selector: {params}"
            assert not set(params) - {"selector", "state", "timeout"}, (
                f"wait_for leaked fields the runner ignores: {params}"
            )

    def test_drag_and_drop_param_names(self):
        conv = RecorderConverter()
        step = conv._to_browser_step(
            {"action": "Drag and drop", "source": "#a", "target": "#b"}
        )
        assert step == {"browser.drag_and_drop": {
            "source_selector": "#a", "target_selector": "#b",
        }}


# ── robot_migrator ────────────────────────────────────────────────────────────

class TestRobotMigratorActions:
    def test_every_mapped_keyword_emits_registered_action(self):
        # Two generic args satisfy every handler's positional expectations
        # (sleep parses its arg as a duration, so it gets a numeric one)
        for keyword in _KEYWORD_MAP:
            args = ["2s"] if keyword == "sleep" else ["#target", "value"]
            step = _map_keyword(keyword, args)
            action = step["action"]
            params = {k: v for k, v in step.items() if k != "action"}
            _assert_step_valid(action, params, f"robot_migrator:{keyword}")

    def test_navigation_and_close(self):
        assert _map_keyword("Go To", ["https://example.com"])["action"] == "browser.open"
        assert _map_keyword("Navigate To", ["https://example.com"])["action"] == "browser.open"
        assert _map_keyword("Close Browser", [])["action"] == "browser.close"

    def test_page_should_contain_has_selector(self):
        step = _map_keyword("Page Should Contain", ["Welcome"])
        assert step["action"] == "test.assert_text_contains"
        assert step["selector"] == "body"
        assert step["text"] == "Welcome"


# ── bdd_migrator ──────────────────────────────────────────────────────────────

class TestBddMigratorActions:
    # Every command _map_browser understands, with representative fields
    COMMANDS = [
        {"command": "open", "param": "https://example.com"},
        {"command": "goto", "param": "https://example.com/page"},
        {"command": "navigate", "param": "https://example.com/page"},
        {"command": "close"},
        {"command": "refresh"},
        {"command": "type", "target": "#user", "text": "admin"},
        {"command": "fill", "target": "#user", "value": "admin"},
        {"command": "click", "target": "#save"},
        {"command": "press", "key": "Enter", "target": "#search"},
        {"command": "gettext", "target": "#status", "name": "status_text"},
        {"command": "screenshot", "name": "final"},
        {"command": "wait", "timeout": 2000},
        {"command": "waitfor", "target": "#spinner", "timeout": 5000},
        {"command": "wait_for_text", "text": "Done"},
        {"command": "evaluate", "param": "console.log(1)"},
        {"command": "select", "target": "#mode", "value": "auto"},
        {"command": "hover", "target": "#menu"},
        {"command": "check", "target": "#enabled"},
        {"command": "uncheck", "target": "#enabled"},
        {"command": "scroll", "target": "#footer"},
        {"command": "assert_checked", "target": "#enabled"},
        {"command": "assert_not_checked", "target": "#enabled"},
        {"command": "click_by_role", "role": "button", "name": "Save"},
        {"command": "containstext", "target": "#msg", "text": "Saved"},
        {"command": "containstext", "text": "Saved"},
        {"command": "gettitle"},
        {"command": "assert_value", "target": "#user", "value": "admin"},
        {"command": "wait_for_navigation"},
        {"command": "drag_drop", "target": "#card", "destination": "#done"},
        {"command": "localstorage", "key": "token", "value": "abc"},
        {"command": "made_up_nonsense"},  # unmapped → test.log TODO
    ]

    def test_every_command_emits_registered_action(self):
        for cmd in self.COMMANDS:
            step = _map_browser(dict(cmd))
            action = step["action"]
            params = {k: v for k, v in step.items() if k != "action"}
            _assert_step_valid(action, params, f"bdd_migrator:{cmd['command']}")

    def test_specific_remappings(self):
        assert _map_browser({"command": "navigate", "param": "https://x"})["action"] == "browser.open"
        assert _map_browser({"command": "assert_not_checked", "target": "#c"})["action"] == "browser.assert_unchecked"
        assert _map_browser({"command": "assert_value", "target": "#u", "value": "v"})["action"] == "test.assert_value"
        assert _map_browser({"command": "wait_for_navigation"})["action"] == "browser.wait_for_url"
        dd = _map_browser({"command": "drag_drop", "target": "#a", "destination": "#b"})
        assert dd["action"] == "browser.drag_and_drop"
        assert dd["source_selector"] == "#a"
        assert dd["target_selector"] == "#b"


# ── framework wiring for the newly-registered actions ─────────────────────────

class TestNewActionsAreExecutable:
    """The new registry entries must be wired end-to-end: a runner dispatch
    clause and a browser-service method, not just a validator entry."""

    NEW_ACTIONS = {
        "test.assert_url": "assert_url",
        "test.assert_value": "assert_value",
        "browser.wait_for_url": "wait_for_url",
        "browser.scroll": "scroll",
        "browser.close": "close_browser",
        "browser.drag_and_drop": "drag_and_drop",
    }

    def test_registered_in_schema(self):
        for action in self.NEW_ACTIONS:
            assert _resolve_schema(action) is not None, action
        # Aliases resolve to the canonical entries
        assert _resolve_schema("browser.assert_url") == _resolve_schema("test.assert_url")
        assert _resolve_schema("browser.assert_value") == _resolve_schema("test.assert_value")
        assert _resolve_schema("browser.navigate") == _resolve_schema("browser.open")

    def test_browser_service_methods_exist(self):
        from easybdd.services.browser_service import BrowserService
        for action, method in self.NEW_ACTIONS.items():
            assert callable(getattr(BrowserService, method, None)), (
                f"BrowserService.{method} missing for {action}"
            )

    def test_runner_dispatches_new_actions(self):
        import inspect
        from easybdd.core.runner import TestRunner
        src = inspect.getsource(TestRunner._execute_step_internal)
        for action in self.NEW_ACTIONS:
            assert f'"{action}"' in src, f"runner has no dispatch for {action}"
