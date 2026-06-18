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
You are an expert test automation engineer specialising in the Easy BDD framework.
Your job is to analyse a web page snapshot and produce automated test cases.

Easy BDD YAML format uses dot-notation actions:
  browser.open, browser.click, browser.fill, browser.assert_text,
  browser.wait_for_element, browser.select, browser.hover, browser.screenshot

For selectors, prefer in this order:
  1. data-testid / data-cy attributes
  2. ARIA role + name  (role=button[name="Submit"])
  3. Stable IDs        (#login-button)
  4. Label text        (label="Email address")
  5. Visible text      (text="Sign In")
  6. CSS selector      (.btn-primary)

For iframes use the prefix: "iframe#frame-id >> <selector>"

Output ONLY a JSON array of test case objects. Each object has:
  {
    "name": "Human-readable test name",
    "description": "What this test verifies",
    "tags": ["browser", "smoke"],
    "steps": [
      {
        "action": "browser.fill",
        "params": {"selector": "#email", "value": "${username}"},
        "description": "Enter the username"
      }
    ]
  }

Guidelines:
- Group related UI interactions into meaningful test cases (login, navigation, form submission, etc.)
- Add browser.screenshot steps after key state changes
- After config changes, add a before/after assertion pattern:
    1. browser.get_text to capture initial value (store_as: before_value)
    2. perform the change
    3. browser.assert_text to verify the new value
- For forms, include both happy-path and required-field validation tests
- Use variables like ${username}, ${password}, ${base_url} for credentials/URLs
- Keep each test case focused on a single user workflow
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

    def _chat(self, messages: List[Dict], max_tokens: int = 4096) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": _SYSTEM_PROMPT}] + messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

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


def build_ai_client(provider: str = "claude", model: Optional[str] = None) -> AIClient:
    """Factory — returns the correct AI client based on provider string."""
    provider = (provider or "claude").lower()
    if provider in ("rules", "none", "rule-based", "rule_based"):
        return RuleBasedClient()
    if provider == "ollama":
        return OllamaClient(model=model)
    return ClaudeClient(model=model)
