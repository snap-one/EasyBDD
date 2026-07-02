"""
Builder "paste recording" import: POST /api/import/recording converts
clipboard-pasted recorder output (Playwright codegen JS/TS or Python,
Chrome DevTools Recorder, Selenium IDE, Katalon, ... JSON exports) into
builder step nodes whose actions are registered in the validator.
"""

import json

import pytest
from fastapi.testclient import TestClient

from easybdd.core.validator import ACTION_SCHEMA, _resolve_schema
from frontend.testrail_builder import app, convert_recording_text

client = TestClient(app)


def _post(text, fmt="auto", include_logs=False):
    return client.post(
        "/api/import/recording",
        json={"text": text, "format": fmt, "include_logs": include_logs},
    )


def _assert_nodes_valid(payload):
    assert payload["steps"], "no steps returned"
    for node in payload["steps"]:
        assert node["kind"] in ("action", "raw")
        if node["kind"] == "action":
            assert _resolve_schema(node["action"]) is not None, (
                f"unregistered action from import: {node['action']}"
            )


# ── Playwright codegen JS/TS ──────────────────────────────────────────────────

PLAYWRIGHT_JS = """
import { test, expect } from '@playwright/test';

test('login works', async ({ page }) => {
  await page.goto('https://example.com/login');
  await page.getByLabel('Email').fill('user@test.com');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('**/dashboard');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});
"""


class TestPlaywrightJsImport:
    def test_detects_and_converts(self):
        r = _post(PLAYWRIGHT_JS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "playwright-js"
        assert body["name"] == "login works"
        assert body["warnings"] == []
        _assert_nodes_valid(body)
        actions = [n["action"] for n in body["steps"]]
        assert "browser.open" in actions
        assert "browser.wait_for_url" in actions

    def test_variables_extracted(self):
        body = _post(PLAYWRIGHT_JS).json()
        keys = {v["key"] for v in body["variables"]}
        assert "base_url" in keys

    def test_explicit_format_hint(self):
        r = _post(PLAYWRIGHT_JS, fmt="playwright-js")
        assert r.status_code == 200
        assert r.json()["format"] == "playwright-js"


# ── Playwright codegen Python ─────────────────────────────────────────────────

PLAYWRIGHT_PY = """
page.goto("https://example.com/login")
page.get_by_label("Email").fill("user@test.com")
page.get_by_role("button", name="Sign in").click()
page.get_by_placeholder("Search").fill("router")
"""


class TestPlaywrightPythonImport:
    def test_detects_and_converts(self):
        r = _post(PLAYWRIGHT_PY)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "playwright-python"
        _assert_nodes_valid(body)

    def test_log_narration_filtered_by_default(self):
        default = _post(PLAYWRIGHT_PY).json()
        with_logs = _post(PLAYWRIGHT_PY, include_logs=True).json()
        assert all(n["action"] != "test.log" for n in default["steps"])
        assert any(n["action"] == "test.log" for n in with_logs["steps"])
        assert len(with_logs["steps"]) > len(default["steps"])


# ── Chrome DevTools Recorder JSON ─────────────────────────────────────────────

CHROME_DEVTOOLS = {
    "title": "Login flow",
    "steps": [
        {"type": "setViewport", "width": 1280, "height": 800},
        {"type": "navigate", "url": "https://example.com/login"},
        {"type": "change", "value": "admin", "selectors": [["#username"]]},
        {"type": "click", "selectors": [["aria/Sign in"], ["#signin"]]},
        {"type": "keyDown", "key": "Enter"},
        {"type": "scroll", "x": 0, "y": 400},
    ],
}


class TestChromeDevtoolsImport:
    def test_detects_and_converts(self):
        r = _post(json.dumps(CHROME_DEVTOOLS))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "chrome-devtools"
        assert body["warnings"] == []
        _assert_nodes_valid(body)
        actions = [n["action"] for n in body["steps"]]
        assert "browser.open" in actions
        assert "browser.scroll" in actions


# ── Selenium IDE (.side) JSON ─────────────────────────────────────────────────

SELENIUM_SIDE = {
    "name": "Login",
    "tests": [{
        "name": "login test",
        "commands": [
            {"command": "open", "target": "https://example.com/login", "value": ""},
            {"command": "type", "target": "id=username", "value": "admin"},
            {"command": "clear", "target": "id=notes", "value": ""},
            {"command": "click", "target": "css=#submit", "value": ""},
            {"command": "select", "target": "id=mode", "value": "auto"},
            {"command": "pause", "target": "1000", "value": ""},
            {"command": "verifytitle", "target": "Dashboard", "value": ""},
            {"command": "doubleclick", "target": "css=#row", "value": ""},
        ],
    }],
}


class TestSeleniumImport:
    def test_detects_and_converts(self):
        r = _post(json.dumps(SELENIUM_SIDE))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "selenium"
        assert body["warnings"] == []
        _assert_nodes_valid(body)
        actions = [n["action"] for n in body["steps"]]
        assert "browser.wait" in actions              # pause
        assert "test.assert_text_contains" in actions  # verifytitle
        # clear → empty fill
        fills = [n for n in body["steps"] if n["action"] == "browser.fill"]
        assert any(n["params"].get("value") == "" for n in fills)


# ── Katalon JSON ──────────────────────────────────────────────────────────────

KATALON = [
    {"command": "openBrowser", "target": "https://example.com", "value": ""},
    {"command": "setText", "target": "id=email", "value": "user@test.com"},
    {"command": "click", "target": "css=#login", "value": ""},
    {"command": "selectOption", "target": "id=country", "value": "US"},
    {"command": "scrollToElement", "target": "css=#footer", "value": ""},
    {"command": "verifyText", "target": "css=#banner", "value": "Welcome"},
]


class TestKatalonImport:
    def test_detects_and_converts(self):
        r = _post(json.dumps(KATALON))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == "katalon"
        assert body["warnings"] == []
        _assert_nodes_valid(body)
        actions = [n["action"] for n in body["steps"]]
        assert "browser.select" in actions
        assert "browser.scroll" in actions


# ── Error handling ────────────────────────────────────────────────────────────

class TestImportErrors:
    def test_empty_text_rejected(self):
        r = _post("   ")
        assert r.status_code == 400
        assert "paste" in r.json()["detail"].lower()

    def test_unrecognizable_text_rejected(self):
        r = _post("SELECT * FROM users;")
        assert r.status_code == 400

    def test_unrecognizable_json_rejected(self):
        r = _post(json.dumps({"foo": "bar"}))
        assert r.status_code == 400
        assert "recognize" in r.json()["detail"].lower()

    def test_json_format_hint_with_bad_json(self):
        r = _post("await page.goto('x');", fmt="selenium")
        assert r.status_code == 400
        assert "JSON" in r.json()["detail"]

    def test_unknown_format_rejected(self):
        r = _post("whatever", fmt="cucumber")
        assert r.status_code == 400

    def test_helper_raises_value_error_directly(self):
        with pytest.raises(ValueError):
            convert_recording_text("")


# ── Everything emitted is lint-clean ──────────────────────────────────────────

class TestImportedStepsPassValidator:
    """Every action produced by every import path must be registered and
    carry its required params — the whole point of the paste feature is
    that imported cases publish without lint errors."""

    FIXTURES = [
        ("js", PLAYWRIGHT_JS, "auto"),
        ("python", PLAYWRIGHT_PY, "auto"),
        ("chrome-devtools", json.dumps(CHROME_DEVTOOLS), "auto"),
        ("selenium", json.dumps(SELENIUM_SIDE), "auto"),
        ("katalon", json.dumps(KATALON), "auto"),
    ]

    @pytest.mark.parametrize("label,text,fmt", FIXTURES, ids=[f[0] for f in FIXTURES])
    def test_actions_registered_with_required_params(self, label, text, fmt):
        body = _post(text, fmt=fmt).json()
        for i, node in enumerate(body["steps"], 1):
            if node["kind"] != "action":
                continue
            schema = _resolve_schema(node["action"])
            assert schema is not None, f"[{label}] step {i}: {node['action']} unregistered"
            missing = [
                p for p in schema.get("required", [])
                if not node["params"].get(p) and node["params"].get(p) != 0
            ]
            assert not missing, (
                f"[{label}] step {i}: {node['action']} missing {missing}: {node['params']}"
            )
