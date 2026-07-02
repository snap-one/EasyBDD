"""
Regression tests for RecorderConverter._parse_playwright_line quote handling.

The old patterns used ["\']([^"\']*)["\'] to capture string arguments, which
truncated any argument containing the *other* quote character — e.g.
page.wait_for_selector("button:has-text('Save')") captured "button:has-text("
instead of the full selector. The patterns now match the closing quote with a
backreference to the opening quote, so mixed quotes inside the string survive.
"""

import pytest

from easybdd.core.recorder_converter import RecorderConverter


@pytest.fixture
def converter():
    return RecorderConverter()


class TestMixedQuoteSelectors:
    """Arguments containing the other quote character must not be truncated."""

    def test_wait_for_selector_has_text_single_inside_double(self, converter):
        step = converter._parse_playwright_line(
            'page.wait_for_selector("button:has-text(\'Save\')")'
        )
        assert step["action"] == "Wait for element"
        assert step["selector"] == "button:has-text('Save')"

    def test_click_has_text_single_inside_double(self, converter):
        step = converter._parse_playwright_line(
            'page.click("button:has-text(\'Save\')")'
        )
        assert step["action"] == "Click element"
        assert step["selector"] == "button:has-text('Save')"

    def test_click_attribute_selector_single_inside_double(self, converter):
        step = converter._parse_playwright_line("page.click(\"a[href='/home']\")")
        assert step["action"] == "Click element"
        assert step["selector"] == "a[href='/home']"

    def test_fill_attribute_selector_single_inside_double(self, converter):
        step = converter._parse_playwright_line(
            "page.fill(\"[name='email']\", \"user@test.com\")"
        )
        assert step["action"] == "Fill form field"
        assert step["field"] == "[name='email']"
        assert step["value"] == "user@test.com"

    def test_fill_attribute_selector_double_inside_single(self, converter):
        step = converter._parse_playwright_line(
            "page.fill('input[type=\"password\"]', 'secret')"
        )
        assert step["action"] == "Fill form field"
        assert step["field"] == 'input[type="password"]'
        assert step["value"] == "secret"

    def test_hover_attribute_selector_mixed_quotes(self, converter):
        step = converter._parse_playwright_line("page.hover(\"div[title='Info']\")")
        assert step["action"] == "Hover"
        assert step["selector"] == "div[title='Info']"

    def test_dblclick_has_text_mixed_quotes(self, converter):
        step = converter._parse_playwright_line(
            'page.dblclick("li:has-text(\'Item 1\')")'
        )
        assert step["action"] == "Double click"
        assert step["selector"] == "li:has-text('Item 1')"

    def test_press_attribute_selector_mixed_quotes(self, converter):
        step = converter._parse_playwright_line(
            "page.press(\"[name='search']\", \"Enter\")"
        )
        assert step["action"] == "Press key"
        assert step["selector"] == "[name='search']"
        assert step["key"] == "Enter"

    def test_goto_url_with_single_quotes_in_query(self, converter):
        step = converter._parse_playwright_line(
            "page.goto(\"https://example.com/search?q='test'\")"
        )
        assert step["action"] == "Open browser"
        assert step["url"] == "https://example.com/search?q='test'"

    def test_get_by_role_name_with_apostrophe(self, converter):
        step = converter._parse_playwright_line(
            'page.get_by_role("button", name="Don\'t Save").click()'
        )
        assert step["action"] == "Click element"
        assert step["role"] == "button"
        assert step["name"] == "Don't Save"

    def test_get_by_role_fill_value_with_apostrophe(self, converter):
        step = converter._parse_playwright_line(
            'page.get_by_role("textbox", name="Owner\'s name").fill("O\'Brien")'
        )
        assert step["action"] == "Fill form field"
        assert step["role"] == "textbox"
        assert step["name"] == "Owner's name"
        assert step["value"] == "O'Brien"

    def test_get_by_text_with_apostrophe(self, converter):
        step = converter._parse_playwright_line(
            'page.get_by_text("It\'s working").click()'
        )
        assert step["action"] == "Click element"
        assert step["text"] == "It's working"

    def test_get_by_label_double_quotes_inside_single(self, converter):
        step = converter._parse_playwright_line(
            'page.get_by_label(\'Email "work"\').fill("user@test.com")'
        )
        assert step["action"] == "Fill form field"
        assert step["label"] == 'Email "work"'
        assert step["value"] == "user@test.com"

    def test_get_by_placeholder_with_apostrophe(self, converter):
        step = converter._parse_playwright_line(
            'page.get_by_placeholder("Enter owner\'s email").fill("a@b.com")'
        )
        assert step["action"] == "Fill form field"
        assert step["label"] == "Enter owner's email"
        assert step["value"] == "a@b.com"

    def test_expect_lines_are_skipped(self, converter):
        # Lines starting with "expect(" are on the parser's skip list, so the
        # to_contain_text branch is not reachable through them.
        step = converter._parse_playwright_line(
            'expect(page.locator("#msg")).to_contain_text("It\'s done")'
        )
        assert step is None


class TestPlainQuoteRegressions:
    """Existing single-quote-style and double-quote-style lines still parse."""

    def test_goto_double_quotes(self, converter):
        step = converter._parse_playwright_line('page.goto("https://example.com")')
        assert step == {
            "action": "Open browser",
            "url": "https://example.com",
            "description": "Navigate to https://example.com",
        }

    def test_goto_single_quotes(self, converter):
        step = converter._parse_playwright_line("page.goto('https://example.com')")
        assert step["url"] == "https://example.com"

    def test_click_simple_selector(self, converter):
        step = converter._parse_playwright_line('page.click("#submit")')
        assert step["action"] == "Click element"
        assert step["selector"] == "#submit"

    def test_fill_simple(self, converter):
        step = converter._parse_playwright_line('page.fill("#email", "a@b.com")')
        assert step["field"] == "#email"
        assert step["value"] == "a@b.com"

    def test_get_by_role_click_single_quotes(self, converter):
        step = converter._parse_playwright_line(
            "page.get_by_role('button', name='Save').click()"
        )
        assert step["role"] == "button"
        assert step["name"] == "Save"

    def test_get_by_role_click_no_name(self, converter):
        step = converter._parse_playwright_line('page.get_by_role("banner").click()')
        assert step == {"action": "Click element", "role": "banner"}

    def test_get_by_label_fill(self, converter):
        step = converter._parse_playwright_line(
            'page.get_by_label("Email").fill("user@test.com")'
        )
        assert step["label"] == "Email"
        assert step["value"] == "user@test.com"

    def test_wait_for_selector_simple(self, converter):
        step = converter._parse_playwright_line('page.wait_for_selector("#spinner")')
        assert step["selector"] == "#spinner"
        assert step["state"] == "visible"

    def test_press_simple(self, converter):
        step = converter._parse_playwright_line('page.press("#input", "Enter")')
        assert step["selector"] == "#input"
        assert step["key"] == "Enter"

    def test_await_prefix_is_stripped(self, converter):
        step = converter._parse_playwright_line(
            '    await page.click("button:has-text(\'OK\')")'
        )
        assert step["selector"] == "button:has-text('OK')"

    def test_unrecognized_line_returns_none(self, converter):
        assert converter._parse_playwright_line("some_random_call()") is None


class TestEndToEndConversion:
    def test_mixed_quote_selector_upgrades_to_role(self, converter):
        """The untruncated has-text selector must reach the role-upgrade logic."""
        code = "await page.click(\"button:has-text('Save')\")"
        result = converter.convert_playwright_native_code(code)
        browser_steps = [s for s in result["steps"] if "browser.click" in s]
        assert len(browser_steps) == 1
        params = browser_steps[0]["browser.click"]
        assert params["role"] == "button"
        assert params["name"] == "Save"

    def test_full_script_step_count(self, converter):
        code = "\n".join(
            [
                "from playwright.sync_api import sync_playwright",
                'page.goto("https://example.com")',
                "page.fill(\"[name='email']\", \"user@test.com\")",
                'page.click("button:has-text(\'Log in\')")',
                "page.wait_for_selector(\"div[class='dashboard']\")",
            ]
        )
        result = converter.convert_playwright_native_code(code)
        # Each recognized line produces a test.log step plus a browser step
        actions = [next(iter(s)) for s in result["steps"]]
        assert actions.count("test.log") == 4
        assert "browser.open" in actions
        assert "browser.fill" in actions
        assert "browser.click" in actions
