"""Unit tests for RecorderConverter, focused on the 'Wait for element' mapping.

Regression coverage for the bug where 'Wait for element' was mapped to the
non-existent action 'browser.wait_for_element' (observed as builder validation
failures, e.g. TestRail case C18691794).  The canonical action is
'browser.wait_for' and its runner handler only reads selector/state/timeout.
"""

from pathlib import Path

import pytest

from easybdd.core.recorder_converter import RecorderConverter
from easybdd.core.validator import ACTION_SCHEMA


WAIT_FOR_ALLOWED = set(ACTION_SCHEMA["browser.wait_for"]["optional"]) | set(
    ACTION_SCHEMA["browser.wait_for"]["required"]
)


@pytest.fixture
def converter():
    return RecorderConverter()


def _browser_steps(test_data):
    """Return only the browser.* steps (skip the interleaved test.log steps)."""
    return [s for s in test_data["steps"] if "test.log" not in s]


class TestWaitForElementMapping:
    def test_maps_to_canonical_browser_wait_for(self, converter):
        step = converter._to_browser_step(
            {"action": "Wait for element", "selector": "#login", "state": "visible"}
        )
        assert "browser.wait_for" in step
        assert "browser.wait_for_element" not in step
        assert step["browser.wait_for"] == {"selector": "#login", "state": "visible"}

    def test_wait_for_is_a_known_validator_action(self):
        # The mapped action must exist in the validator schema (directly,
        # not via alias) so builder validation passes.
        assert "alias_of" not in ACTION_SCHEMA["browser.wait_for"]

    def test_playwright_codegen_wait_for_selector(self, converter):
        code = 'page.wait_for_selector("#dashboard")'
        test_data = converter.convert_playwright_native_code(code)
        steps = _browser_steps(test_data)
        assert len(steps) == 1
        assert "browser.wait_for" in steps[0]
        params = steps[0]["browser.wait_for"]
        assert params["selector"] == "#dashboard"
        assert params["state"] == "visible"
        assert set(params) <= WAIT_FOR_ALLOWED

    def test_timeout_is_preserved(self, converter):
        step = converter._to_browser_step(
            {"action": "Wait for element", "selector": "#x", "timeout": 10}
        )
        assert step["browser.wait_for"] == {"selector": "#x", "timeout": 10}


class TestWaitForParamTranslation:
    """role/name/label/text fields must be folded into a selector param,
    since the runner's wait_for handler only reads selector/state/timeout."""

    def test_role_and_name_become_selector(self, converter):
        step = converter._to_browser_step(
            {"action": "Wait for element", "role": "link", "name": "Home", "state": "visible"}
        )
        params = step["browser.wait_for"]
        assert params["selector"] == 'role=link[name="Home"]'
        assert set(params) <= WAIT_FOR_ALLOWED

    def test_role_without_name_becomes_selector(self, converter):
        step = converter._to_browser_step(
            {"action": "Wait for element", "role": "button"}
        )
        assert step["browser.wait_for"]["selector"] == "role=button"

    def test_text_becomes_selector(self, converter):
        step = converter._to_browser_step(
            {"action": "Wait for element", "text": "Welcome", "state": "visible"}
        )
        assert step["browser.wait_for"]["selector"] == "text=Welcome"

    def test_label_becomes_aria_selector(self, converter):
        step = converter._to_browser_step(
            {"action": "Wait for element", "label": "Email", "state": "visible"}
        )
        assert step["browser.wait_for"]["selector"] == '[aria-label="Email"]'

    def test_selenium_linktext_wait(self, converter):
        # Selenium 'waitForElementVisible' with linkText target goes through
        # the role/name path end to end.
        data = {
            "name": "Login flow",
            "tests": [
                {
                    "commands": [
                        {"command": "waitForElementVisible", "target": "linkText=Home", "value": ""},
                    ]
                }
            ],
        }
        test_data = converter.convert(data, "selenium", Path("recording.side"))
        steps = _browser_steps(test_data)
        assert len(steps) == 1
        params = steps[0]["browser.wait_for"]
        assert params == {"state": "visible", "selector": 'role=link[name="Home"]'}

    def test_chrome_devtools_aria_wait(self, converter):
        data = {
            "title": "Recorded flow",
            "steps": [
                {"type": "waitForElement", "selectors": [["aria/Submit"]], "visible": True},
            ],
        }
        test_data = converter.convert(data, "chrome-devtools", Path("recording.json"))
        steps = _browser_steps(test_data)
        assert len(steps) == 1
        params = steps[0]["browser.wait_for"]
        assert params["selector"] == '[aria-label="Submit"]'
        assert params["state"] == "visible"

    def test_chrome_devtools_text_wait(self, converter):
        data = {
            "title": "Recorded flow",
            "steps": [
                {"type": "waitForElement", "selectors": [["text/Dashboard"]], "visible": True},
            ],
        }
        test_data = converter.convert(data, "chrome-devtools", Path("recording.json"))
        steps = _browser_steps(test_data)
        assert steps[0]["browser.wait_for"]["selector"] == "text=Dashboard"

    def test_css_wait_selector_survives_role_upgrade(self, converter):
        # upgrade_step_to_role_selector rewrites button:has-text CSS into
        # role/name — the wait translation must fold it back into a selector.
        steps = converter._finalise_step(
            {"action": "Wait for element", "selector": "button:has-text('Save')", "state": "visible"}
        )
        browser_steps = [s for s in steps if "test.log" not in s]
        params = browser_steps[0]["browser.wait_for"]
        assert params["selector"] == 'role=button[name="Save"]'
        assert set(params) <= WAIT_FOR_ALLOWED
