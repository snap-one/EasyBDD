"""
Regression tests: converters must emit the canonical `browser.wait_for`
action, never the nonexistent `browser.wait_for_element` (which fails
builder validation — seen in TestRail case C18691794), and every wait
step must carry a `selector` param since browser.wait_for does not
understand role/name/text/label fields at runtime.
"""

import pytest

from easybdd.core.validator import ACTION_SCHEMA
from easybdd.crawler.crx_converter import PlaywrightTsConverter
from easybdd.crawler.models import ElementSnapshot
from easybdd.crawler.rule_based_analyzer import _build_modal_cases, _PatternMatch
from frontend.robot_migrator import _map_keyword
from frontend.bdd_migrator import _map_browser


def _assert_valid_action(action: str):
    assert action in ACTION_SCHEMA, f"action '{action}' is not registered in the validator"


class TestCrxConverterWaits:
    CODE = """
import { test, expect } from '@playwright/test';
test('sample', async ({ page }) => {
  await page.goto('https://example.com');
  await page.waitForSelector('#spinner', { state: 'hidden' });
  await page.waitForURL('**/dashboard');
  await expect(page.getByRole('link', { name: 'Devices' })).toBeVisible();
  await expect(page.getByText('Saved')).toBeHidden();
  await expect(page.getByLabel('Email')).toBeEnabled();
  await page.locator('#modal').waitFor({ state: 'visible' });
});
"""

    def test_no_wait_for_element_emitted(self):
        result = PlaywrightTsConverter().convert(self.CODE, "sample")
        for step in result["steps"]:
            action = next(iter(step))
            assert action != "browser.wait_for_element"

    def test_wait_steps_are_valid_and_have_selector(self):
        result = PlaywrightTsConverter().convert(self.CODE, "sample")
        waits = [s for s in result["steps"] if "browser.wait_for" in s]
        assert len(waits) == 5
        for step in waits:
            _assert_valid_action("browser.wait_for")
            params = step["browser.wait_for"]
            assert params.get("selector"), f"wait step missing selector: {params}"
            # No stray locator fields the runner would silently ignore
            assert not set(params) - {"selector", "state", "timeout"}

    def test_wait_for_url_keeps_url_pattern(self):
        result = PlaywrightTsConverter().convert(self.CODE, "sample")
        url_waits = [s for s in result["steps"] if "browser.wait_for_url" in s]
        assert len(url_waits) == 1
        _assert_valid_action("browser.wait_for_url")
        assert url_waits[0]["browser.wait_for_url"]["url"] == "**/dashboard"

    def test_role_locator_becomes_role_selector(self):
        result = PlaywrightTsConverter().convert(self.CODE, "sample")
        selectors = [s["browser.wait_for"]["selector"]
                     for s in result["steps"] if "browser.wait_for" in s]
        assert 'role=link[name="Devices"]' in selectors


class TestRobotMigratorWaits:
    def test_wait_until_element_is_visible(self):
        step = _map_keyword("Wait Until Element Is Visible", ["#spinner"])
        assert step["action"] == "browser.wait_for"
        _assert_valid_action(step["action"])
        assert step["selector"] == "#spinner"


class TestBddMigratorWaits:
    def test_wait_with_selector(self):
        step = _map_browser({"command": "waitfor", "target": "#spinner", "timeout": 5000})
        assert step["action"] == "browser.wait_for"
        _assert_valid_action(step["action"])
        assert step["selector"] == "#spinner"

    def test_bare_wait_maps_to_timed_pause(self):
        step = _map_browser({"command": "wait", "timeout": 2000})
        assert step["action"] == "browser.wait"
        _assert_valid_action(step["action"])
        assert "selector" not in step


class TestRuleBasedAnalyzerWaits:
    def test_modal_cases_use_wait_for(self):
        el = ElementSnapshot(tag="button", text="Open Dialog", role="button",
                             selectors=["#open-dialog"])
        pattern = _PatternMatch(name="modal", elements=[el])
        cases = _build_modal_cases(pattern, "https://example.com")
        wait_steps = [s for c in cases for s in c.steps if "wait" in s.action]
        assert wait_steps, "expected at least one wait step in modal cases"
        for s in wait_steps:
            assert s.action == "browser.wait_for"
            _assert_valid_action(s.action)
