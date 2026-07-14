"""
AI client abstraction for the crawler.

Supports:
  - Claude API (Anthropic)  — set ANTHROPIC_API_KEY in .env
  - Ollama (local)          — set OLLAMA_BASE_URL (default http://localhost:11434)

The client receives a serialised page snapshot and returns a list of
suggested test steps in Easy BDD action format.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests


_SYSTEM_PROMPT = """\
You are an expert test automation engineer for the Easy BDD framework.
Analyse the page snapshot and generate test cases for EVERY interactive element found.

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array. No markdown, no explanation. Each item:
{
  "name": "Short descriptive name",
  "description": "What this test verifies",
  "tags": ["browser", "smoke"],
  "steps": [
    {"action": "browser.open",  "params": {"url": "${base_url}"}},
    {"action": "browser.fill",  "params": {"selector": "#field", "value": "test"}, "description": "Fill the field"},
    {"action": "browser.click", "params": {"selector": "role=button[name=Save]"}, "description": "Click Save"},
    {"action": "browser.screenshot", "params": {"name": "after-save"}}
  ]
}

=== SELECTOR PRIORITY (use best available) ===
1. data-testid / data-cy  →  [data-testid="submit"]
2. ARIA role + name       →  role=button[name="Save"]
3. Stable ID              →  #save-btn
4. Label                  →  label="Email address"
5. Visible text           →  text="Sign In"
6. CSS class              →  .btn-primary

=== RULES — FOLLOW EXACTLY ===

1. TEXT / NUMBER / PASSWORD INPUTS
   - Create one test per input field
   - Steps: open page → fill the field with a realistic value → screenshot
   - Name: "Fill [field label/placeholder]"

2. DROPDOWNS / SELECTS
   - Create one test per dropdown
   - Steps: open page → select an option → screenshot
   - Use browser.select action

3. CHECKBOXES / TOGGLES
   - Create one test per checkbox
   - Steps: open page → click to toggle → screenshot

4. SAVE / APPLY / SUBMIT BUTTONS
   - This is the most important pattern — always include it when a save button exists
   - Steps:
       a. browser.open
       b. Fill ALL input fields on the form with realistic test values
       c. browser.get_text on a key field (store_as: value_before)
       d. browser.click the Save/Apply button
       e. browser.wait_for — wait for confirmation message or page reload
       f. browser.screenshot (name: "after-save")
       g. browser.assert_text — verify success message like "Settings saved" / "Applied" / "Success"
   - If a confirmation dialog appears (OK/Confirm button), add a step to click it

5. CONFIRMATION DIALOGS (OK / Confirm / Yes buttons)
   - Create TWO tests: one that confirms, one that cancels
   - "Confirm [action] — accept": click trigger → click OK/Confirm → verify result
   - "Confirm [action] — cancel": click trigger → click Cancel → verify nothing changed

6. NAVIGATION LINKS / TABS
   - Create one test per nav link
   - Steps: open page → click link → browser.get_title (store_as: page_title) → screenshot

7. EVERY TEST must start with browser.open and end with browser.screenshot

Use variables: ${base_url}, ${username}, ${password}
Use realistic placeholder values for inputs (e.g. "TestNetwork", "192.168.1.100", "admin").
"""


class AIClient(ABC):
    @abstractmethod
    def analyze_page(
        self,
        snapshot_json: str,
        existing_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return a list of raw test case dicts from the AI."""
        ...

    @abstractmethod
    def suggest_selectors(self, element_description: str, page_html_fragment: str) -> List[str]:
        """Ask the AI to suggest stable selectors for a broken/missing element."""
        ...


class ClaudeClient(AIClient):
    """Uses the Anthropic Messages API."""

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # fast + cheap for test generation

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or os.getenv("CRAWLER_AI_MODEL", self.DEFAULT_MODEL)
        self._base_url = "https://api.anthropic.com/v1"

    def _post(self, messages: List[Dict], max_tokens: int = 4096) -> str:
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": _SYSTEM_PROMPT,
            "messages": messages,
        }
        resp = requests.post(
            f"{self._base_url}/messages",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    def analyze_page(
        self,
        snapshot_json: str,
        existing_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        user_content = (
            f"Here is the page snapshot to analyse:\n```json\n{snapshot_json}\n```"
        )
        if existing_context:
            user_content = (
                f"Previously generated tests for this site:\n{existing_context}\n\n"
                + user_content
            )
        raw = self._post([{"role": "user", "content": user_content}])
        return _parse_json_response(raw)

    def suggest_selectors(self, element_description: str, page_html_fragment: str) -> List[str]:
        prompt = (
            f"An automated test has a broken selector. The element was described as:\n"
            f"{element_description}\n\n"
            f"Here is the current HTML around where the element should be:\n"
            f"```html\n{page_html_fragment[:4000]}\n```\n\n"
            f"Return a JSON array of up to 5 stable CSS/ARIA selectors that would "
            f"match this element, ordered best-first. Return only the JSON array."
        )
        raw = self._post([{"role": "user", "content": prompt}], max_tokens=512)
        try:
            result = json.loads(raw.strip())
            if isinstance(result, list):
                return [str(s) for s in result]
        except json.JSONDecodeError:
            pass
        return []


class OllamaClient(AIClient):
    """Uses a locally-running Ollama instance."""

    DEFAULT_MODEL = "llama3"

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("CRAWLER_AI_MODEL", self.DEFAULT_MODEL)

    # CPU-only inference is slow — allow up to 20 minutes per page
    _TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "1200"))
    # Max snapshot chars sent to Ollama — keeps prompt small and fast on CPU
    _MAX_SNAPSHOT_CHARS = int(os.getenv("OLLAMA_MAX_SNAPSHOT_CHARS", "12000"))

    def _chat(self, messages: List[Dict], max_tokens: int = 1024) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": _SYSTEM_PROMPT}] + messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096")),
            },
        }
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self._TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def analyze_page(
        self,
        snapshot_json: str,
        existing_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Truncate snapshot to keep prompt within CPU-friendly token budget
        if len(snapshot_json) > self._MAX_SNAPSHOT_CHARS:
            snapshot_json = snapshot_json[: self._MAX_SNAPSHOT_CHARS] + "\n... (truncated)"
        user_content = (
            f"Here is the page snapshot to analyse:\n```json\n{snapshot_json}\n```"
        )
        if existing_context:
            user_content = (
                f"Previously generated tests:\n{existing_context}\n\n" + user_content
            )
        raw = self._chat([{"role": "user", "content": user_content}])
        return _parse_json_response(raw)

    def suggest_selectors(self, element_description: str, page_html_fragment: str) -> List[str]:
        prompt = (
            f"Broken selector element: {element_description}\n"
            f"HTML fragment:\n```html\n{page_html_fragment[:3000]}\n```\n"
            f"Return a JSON array of up to 5 stable selectors, best-first."
        )
        raw = self._chat([{"role": "user", "content": prompt}], max_tokens=256)
        try:
            result = json.loads(raw.strip())
            if isinstance(result, list):
                return [str(s) for s in result]
        except json.JSONDecodeError:
            pass
        return []


def _parse_json_response(raw: str) -> List[Dict[str, Any]]:
    """Extract a JSON array from an AI response that may contain markdown fences."""
    text = raw.strip()
    # Strip markdown fences
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```")[0].strip()
    # Find first [ … ] block
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return []


class RuleBasedClient(AIClient):
    """
    Zero-cost, zero-dependency analyzer that generates test cases purely from
    DOM structure using pattern matching — no API key required.

    The analyze_page() method ignores the snapshot_json string and instead
    expects the caller (server.py) to pass the raw PageSnapshot object via
    the 'snapshot' keyword on the session.  For the standard AIClient
    interface it returns an empty list and delegates to the rule-based
    analyzer directly in page_analyzer.py.

    Usage: set CRAWLER_AI_PROVIDER=rules (or select in the extension popup).
    """

    def analyze_page(
        self,
        snapshot_json: str,
        existing_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # The real work happens in page_analyzer.analyze_snapshot() which
        # detects provider="rules" and calls analyze_snapshot_rules() directly.
        # This method is a no-op fallback.
        return []

    def suggest_selectors(self, element_description: str, page_html_fragment: str) -> List[str]:
        # Rule-based self-healing: return empty list so the fallback chain
        # in self_healer.py handles it without AI.
        return []


_WORKFLOW_PROMPT = """\
You are a test automation engineer. Given a list of EXISTING test cases (already generated by a rule engine) and the interactive elements on a page, your ONLY job is to generate ADDITIONAL workflow tests that the rule engine cannot produce:

1. SAVE FLOWS: fill all inputs → click Save/Apply → wait for confirmation → assert success message
2. CONFIRMATION DIALOGS: trigger an action → confirm dialog appears → click OK vs Cancel
3. MULTI-STEP WORKFLOWS: e.g. change a value → save → reload page → verify value persisted

DO NOT reproduce any test that already exists in the existing tests list.
DO NOT invent element names or selectors — use ONLY selectors from the "elements" list provided.
DO NOT generate tests if the page has no save/apply button or no confirmation dialogs.

Output ONLY a valid JSON array in the EXACT same format as the existing tests shown.
If there are no additional workflow tests to add, output an empty array: []

EXISTING TEST FORMAT EXAMPLE (follow this exactly):
{
  "name": "Save Wi-Fi settings",
  "description": "Fills SSID and password then saves and verifies confirmation",
  "tags": ["browser", "smoke"],
  "steps": [
    {"action": "browser.open",       "params": {"url": "${base_url}"}},
    {"action": "browser.fill",       "params": {"selector": "#ssid", "value": "TestNetwork"}},
    {"action": "browser.fill",       "params": {"selector": "#password", "value": "TestPass123"}},
    {"action": "browser.click",      "params": {"selector": "role=button[name=\\"Apply Changes\\"]"}},
    {"action": "browser.wait_for",   "params": {"selector": "text=\\"Settings saved\\"", "timeout": 5000}},
    {"action": "browser.screenshot", "params": {"name": "after-save"}}
  ]
}
"""


def _filter_ollama_cases(raw_cases: List[Dict], known_selectors: set) -> List[Dict]:
    """
    Remove hallucinated or malformed cases from Ollama output.
    Keeps a case only if:
      - it has a real name (not 'Unnamed test' or empty)
      - it has at least 2 steps
      - at least one step references a selector that exists on the page
    """
    good = []
    bad_names = {"unnamed test", "untitled", "test case", "feature", ""}
    for case in raw_cases:
        if not isinstance(case, dict):
            continue
        name = (case.get("name") or "").strip()
        if name.lower() in bad_names or len(name) < 4:
            continue
        steps = case.get("steps", [])
        if len(steps) < 2:
            continue
        # At least one step must reference a known selector (or be a browser.open/screenshot)
        anchored = False
        for step in steps:
            params = step.get("params", {})
            sel = params.get("selector", "")
            action = step.get("action", "")
            if action in ("browser.open", "browser.screenshot", "browser.wait_for"):
                anchored = True
                break
            if sel and any(k in sel for k in known_selectors):
                anchored = True
                break
            # Accept if selector looks like a real CSS/ARIA selector (not a placeholder)
            if sel and not sel.startswith("${") and len(sel) > 3:
                anchored = True
                break
        if anchored:
            good.append(case)
    return good


class HybridClient(AIClient):
    """
    Hybrid provider: rule-based generates all element-level tests with correct
    Easy BDD syntax, then Ollama adds workflow tests (save flows, confirmations)
    using the rule output as few-shot examples so it knows the exact format.

    Usage: set CRAWLER_AI_PROVIDER=hybrid
    """

    def __init__(self, model: Optional[str] = None):
        self._ollama = OllamaClient(model=model)

    def analyze_page(
        self,
        snapshot_json: str,
        existing_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Hybrid path is handled directly in page_analyzer.analyze_snapshot()
        return []

    def suggest_selectors(self, element_description: str, page_html_fragment: str) -> List[str]:
        return self._ollama.suggest_selectors(element_description, page_html_fragment)

    def analyze_workflows(
        self,
        snapshot_json: str,
        rule_cases_json: str,
        known_selectors: set,
    ) -> List[Dict[str, Any]]:
        """
        Ask Ollama to generate workflow tests on top of the rule-based cases.
        Uses the rule cases as few-shot examples so Ollama knows the exact format.
        """
        if len(snapshot_json) > self._ollama._MAX_SNAPSHOT_CHARS:
            snapshot_json = snapshot_json[: self._ollama._MAX_SNAPSHOT_CHARS] + "\n...(truncated)"

        user_content = (
            f"EXISTING TESTS (already generated — do not duplicate):\n"
            f"```json\n{rule_cases_json[:3000]}\n```\n\n"
            f"PAGE ELEMENTS:\n```json\n{snapshot_json}\n```\n\n"
            f"Generate ONLY additional workflow tests (save flows, confirmation dialogs, multi-step). "
            f"Output a JSON array or [] if none needed."
        )

        payload = {
            "model": self._ollama.model,
            "messages": [
                {"role": "system", "content": _WORKFLOW_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            "stream": False,
            "options": {
                "num_predict": 1500,
                "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096")),
            },
        }
        try:
            resp = requests.post(
                f"{self._ollama.base_url}/api/chat",
                json=payload,
                timeout=self._ollama._TIMEOUT,
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
            candidates = _parse_json_response(raw)
            return _filter_ollama_cases(candidates, known_selectors)
        except Exception:
            return []  # Ollama failure never blocks rule-based results


def build_ai_client(provider: str = "claude", model: Optional[str] = None) -> AIClient:
    """Factory — returns the correct AI client based on provider string."""
    provider = (provider or "claude").lower()
    if provider in ("rules", "none", "rule-based", "rule_based"):
        return RuleBasedClient()
    if provider == "hybrid":
        return HybridClient(model=model)
    if provider == "ollama":
        return OllamaClient(model=model)
    return ClaudeClient(model=model)
