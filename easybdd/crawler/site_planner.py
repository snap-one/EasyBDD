"""
Site Planner — builds a full site map from all crawled snapshots and uses
Ollama to plan comprehensive cross-page test scenarios.

This is the "intelligent" layer that makes Easy BDD behave like QAWolf:
instead of analyzing each page in isolation, it sees the entire site at once
and plans tests around real user workflows (login → configure → save → verify).

Flow:
  1. build_site_map()   — distils all snapshots into a compact site map
  2. plan_workflows()   — asks Ollama to identify key user workflows
  3. generate_tests()   — generates multi-page GeneratedTestCase objects
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests

from .models import GeneratedStep, GeneratedTestCase, PageSnapshot
from .page_analyzer import _slim_snapshot
from .rule_based_analyzer import analyze_snapshot_rules


_PLAN_SYSTEM_PROMPT = """\
You are a senior QA architect analysing a web application site map.
Your job is to identify the most important USER WORKFLOWS to test — not individual elements.

A workflow is a sequence of steps a real user would perform across one or more pages.
Examples:
  - "Configure Wi-Fi: navigate to Wi-Fi settings → change SSID and password → click Apply → verify confirmation"
  - "Login and navigate: enter credentials → click Login → verify dashboard loads"
  - "Change system settings: open Settings → update hostname → click Save → verify success toast"

OUTPUT FORMAT — return ONLY a valid JSON array:
[
  {
    "workflow_name": "Short descriptive name",
    "description": "What user goal this tests",
    "pages": ["https://device/settings", "https://device/settings/wifi"],
    "steps": [
      {"page": "https://device/settings", "action": "click", "element": "Wi-Fi Setup link", "selector": "role=link[name='Wi-Fi Setup']"},
      {"page": "https://device/settings/wifi", "action": "fill", "element": "SSID input", "selector": "#ssid", "value": "TestNetwork"},
      {"page": "https://device/settings/wifi", "action": "fill", "element": "Password input", "selector": "#wifi-password", "value": "TestPass123"},
      {"page": "https://device/settings/wifi", "action": "click", "element": "Apply button", "selector": "role=button[name='Apply Changes']"},
      {"page": "https://device/settings/wifi", "action": "assert", "element": "Success message", "selector": "text='Settings saved'"}
    ]
  }
]

Rules:
- Only use selectors from the elements lists provided in the site map
- Focus on CONFIGURATION workflows (the most valuable tests for network device UIs)
- Include save/apply flows with result verification for every form
- Include navigation flows that verify page loads correctly
- Maximum 10 workflows
- If a page has no interactive elements worth testing, skip it
"""

_WORKFLOW_TO_EASYBDD_PROMPT = """\
Convert the following workflow plan into Easy BDD test cases.

Easy BDD format (dot-notation YAML steps as JSON):
- browser.open:              {"url": "${base_url}"}
- browser.fill:              {"selector": "#field", "value": "text"}
- browser.click:             {"selector": "role=button[name='Save']"}
- browser.select:            {"selector": "#dropdown", "value": "option"}
- browser.wait_for:          {"selector": "text='Success'", "timeout": 5000}
- browser.get_text:          {"selector": ".status", "store_as": "status_text"}
- test.assert_text_contains: {"selector": ".alert", "text": "Settings saved"}
- test.assert_text_equals:   {"selector": ".label", "text": "ON"}
- browser.screenshot:        {"name": "descriptive-name"}

Return ONLY a valid JSON array of test case objects:
[{
  "name": "Workflow name",
  "description": "What this verifies",
  "tags": ["browser", "workflow", "e2e"],
  "steps": [
    {"action": "browser.open",  "params": {"url": "${base_url}"}},
    {"action": "browser.fill",  "params": {"selector": "#field", "value": "test"}},
    {"action": "browser.click", "params": {"selector": "role=button[name='Save']"}},
    {"action": "browser.screenshot", "params": {"name": "after-save"}}
  ]
}]

Every test MUST:
1. Start with browser.open
2. End with browser.screenshot
3. Include browser.wait_for after any save/apply click
4. Include test.assert_text_contains or test.assert_text_equals to verify the result
"""


class SitePlanner:
    """
    Orchestrates the 3-phase intelligent crawl analysis.
    """

    def __init__(self, ollama_base_url: str, model: str, timeout: int = 1200):
        self.base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

    def _chat(self, system: str, user: str, max_tokens: int = 2048) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens, "num_ctx": self.num_ctx},
        }
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _parse_json(self, raw: str) -> Any:
        text = raw.strip()
        for fence in ("```json", "```"):
            if fence in text:
                text = text.split(fence, 1)[1].split("```")[0].strip()
                break
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        try:
            return json.loads(text)
        except Exception:
            return []

    # ── Phase 1: Build site map ────────────────────────────────────────────────

    def build_site_map(self, snapshots: List[PageSnapshot]) -> Dict[str, Any]:
        """
        Distil all snapshots into a compact site map for Ollama.
        Includes: URL, title, interactive elements (selectors + labels only).
        """
        pages = []
        for snap in snapshots:
            slim = _slim_snapshot(snap)
            # Further compress: just selector + label/name/placeholder per element
            compact_elements = []
            for el in slim.get("elements", []):
                entry: Dict[str, str] = {"tag": el.get("tag", "")}
                for field in ("type", "role", "name", "label", "placeholder",
                              "text", "id", "aria_label", "data_testid"):
                    if el.get(field):
                        entry[field] = el[field]
                # Best selector only
                sels = el.get("selectors", [])
                if sels:
                    entry["selector"] = sels[0]
                compact_elements.append(entry)

            pages.append({
                "url":      snap.url,
                "title":    snap.title,
                "elements": compact_elements,
            })

        return {
            "base_url":   self._common_base(snapshots),
            "page_count": len(pages),
            "pages":      pages,
        }

    @staticmethod
    def _common_base(snapshots: List[PageSnapshot]) -> str:
        if not snapshots:
            return ""
        from urllib.parse import urlparse
        p = urlparse(snapshots[0].url)
        return f"{p.scheme}://{p.netloc}"

    # ── Phase 2: Plan workflows ────────────────────────────────────────────────

    def plan_workflows(self, site_map: Dict[str, Any]) -> List[Dict]:
        """Ask Ollama to identify key user workflows from the site map."""
        site_map_json = json.dumps(site_map, indent=2)
        # Keep under token budget
        if len(site_map_json) > 10000:
            # Truncate element lists to save tokens
            for page in site_map.get("pages", []):
                page["elements"] = page["elements"][:15]
            site_map_json = json.dumps(site_map, indent=2)

        user_msg = (
            f"Here is the complete site map for the web application:\n\n"
            f"```json\n{site_map_json[:10000]}\n```\n\n"
            f"Identify up to 10 important user workflows to test. "
            f"Focus on configuration flows, save operations, and navigation paths. "
            f"Only use selectors that appear in the elements lists above."
        )

        try:
            raw = self._chat(_PLAN_SYSTEM_PROMPT, user_msg, max_tokens=2000)
            workflows = self._parse_json(raw)
            if isinstance(workflows, list):
                return workflows
        except Exception as e:
            print(f"[SitePlanner] workflow planning failed: {e}")
        return []

    # ── Phase 3: Generate workflow tests ──────────────────────────────────────

    def generate_workflow_tests(
        self,
        workflows: List[Dict],
        base_url: str,
    ) -> List[GeneratedTestCase]:
        """Convert planned workflows into Easy BDD test cases."""
        if not workflows:
            return []

        workflows_json = json.dumps(workflows, indent=2)
        user_msg = (
            f"base_url: {base_url}\n\n"
            f"Convert these planned workflows to Easy BDD test cases:\n\n"
            f"```json\n{workflows_json[:6000]}\n```\n\n"
            f"Return a JSON array of test cases."
        )

        try:
            raw = self._chat(_WORKFLOW_TO_EASYBDD_PROMPT, user_msg, max_tokens=3000)
            raw_cases = self._parse_json(raw)
        except Exception as e:
            print(f"[SitePlanner] workflow test generation failed: {e}")
            return []

        # Convert raw dicts to GeneratedTestCase (no element index enrichment
        # since these are cross-page tests; selectors come from the planning step)
        cases = []
        bad_names = {"unnamed test", "untitled", ""}
        for raw in raw_cases:
            if not isinstance(raw, dict):
                continue
            name = (raw.get("name") or "").strip()
            if name.lower() in bad_names or len(name) < 4:
                continue
            steps = []
            for s in raw.get("steps", []):
                if not isinstance(s, dict):
                    continue
                steps.append(GeneratedStep(
                    action=s.get("action", ""),
                    params=s.get("params", {}),
                    description=s.get("description", ""),
                ))
            if len(steps) < 2:
                continue
            cases.append(GeneratedTestCase(
                name=name,
                description=raw.get("description", ""),
                tags=raw.get("tags", ["browser", "workflow", "e2e"]),
                url=base_url,
                steps=steps,
            ))
        return cases

    # ── Full pipeline ──────────────────────────────────────────────────────────

    def run(self, snapshots: List[PageSnapshot], output_dir: str) -> List[GeneratedTestCase]:
        """
        Full 3-phase intelligent analysis:
          1. Rule-based tests for every element on every page
          2. Ollama workflow planning from full site map
          3. Multi-page workflow test generation
        Returns all cases combined.
        """
        from pathlib import Path
        from .yaml_writer import write_test_case

        all_cases: List[GeneratedTestCase] = []
        output_path = Path(output_dir)

        print(f"[SitePlanner] Phase 1: rule-based analysis ({len(snapshots)} pages)")
        for snap in snapshots:
            page_cases = analyze_snapshot_rules(snap)
            for case in page_cases:
                write_test_case(case, output_path, base_url=self._common_base(snapshots))
            all_cases.extend(page_cases)

        print(f"[SitePlanner] Phase 2: building site map and planning workflows")
        site_map = self.build_site_map(snapshots)
        workflows = self.plan_workflows(site_map)
        print(f"[SitePlanner] Ollama identified {len(workflows)} workflows")

        print(f"[SitePlanner] Phase 3: generating workflow tests")
        base_url = self._common_base(snapshots)
        workflow_cases = self.generate_workflow_tests(workflows, base_url)
        print(f"[SitePlanner] Generated {len(workflow_cases)} workflow tests")

        for case in workflow_cases:
            write_test_case(case, output_path, base_url=base_url)
        all_cases.extend(workflow_cases)

        return all_cases
