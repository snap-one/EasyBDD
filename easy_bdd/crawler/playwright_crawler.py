"""
playwright_crawler.py — headed Playwright browser auto-crawler.

An alternative to the Chrome extension that needs no browser plugin at all.

How it works:
  1. Opens a visible (headed) Playwright Chromium browser
  2. Navigates to the start URL
  3. Pauses for the user to log in (waits until URL changes or a timeout passes)
  4. From that point, every page navigation automatically:
       a. Takes an accessibility snapshot via accessibility_snapshotter.py
       b. Feeds it to the configured analyzer (rule-based or AI)
       c. Writes YAML to disk and optionally pushes to TestRail
  5. Runs until the user closes the browser or Ctrl+C is pressed

No Chrome extension, no API key (when using rule-based mode), no Node.js.
The Playwright browser session shares no cookies with Chrome — the user
logs in once inside the Playwright window at startup.

Usage (via CLI):
    python -m easy_bdd crawler playwright \
        --url https://app.example.com \
        --project 12 \
        --provider rules

Usage (programmatic):
    from easy_bdd.crawler.playwright_crawler import PlaywrightCrawler
    from easy_bdd.crawler.models import CrawlSessionConfig

    config = CrawlSessionConfig(
        testrail_project_id=12,
        ai_provider="rules",
        output_dir="tests/cases/crawled",
        base_url="https://app.example.com",
    )
    crawler = PlaywrightCrawler(config)
    crawler.run(start_url="https://app.example.com/login")
"""

from __future__ import annotations

import os
import time
import threading
from pathlib import Path
from typing import Callable, List, Optional, Set
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

from .accessibility_snapshotter import snapshot_page_a11y
from .ai_client import build_ai_client
from .crawl_session import CrawlSession
from .models import CrawlSessionConfig, PageSnapshot
from .page_analyzer import analyze_snapshot
from .testrail_publisher import TestRailPublisher
from .yaml_writer import write_all_cases


# ── Login detection ───────────────────────────────────────────────────────────

_LOGIN_PATH_PATTERNS = {
    "login", "signin", "sign-in", "auth", "authenticate",
    "logon", "log-in", "sso", "oauth",
}


def _looks_like_login_page(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(p in path for p in _LOGIN_PATH_PATTERNS)


# ── Crawler ───────────────────────────────────────────────────────────────────


class PlaywrightCrawler:
    """
    Headed Playwright browser crawler — no Chrome extension required.

    Args:
        config: CrawlSessionConfig controlling AI provider, TestRail target, output dir
        on_case_generated: Optional callback called with each GeneratedTestCase
        login_timeout_s: How long to wait for user to complete login (default 120s)
        page_settle_ms: How long to wait after navigation before snapshotting (default 1200ms)
    """

    def __init__(
        self,
        config: CrawlSessionConfig,
        on_case_generated: Optional[Callable] = None,
        login_timeout_s: int = 120,
        page_settle_ms: int = 1200,
    ):
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
        self.config = config
        self.on_case_generated = on_case_generated
        self.login_timeout_s = login_timeout_s
        self.page_settle_ms = page_settle_ms

        self._session = CrawlSession(config)
        self._ai = build_ai_client(provider=config.ai_provider, model=config.ai_model)
        self._stop_event = threading.Event()
        self._cases_pushed: int = 0

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self, start_url: str) -> CrawlSession:
        """
        Open a headed browser, crawl all same-origin pages, write YAML and push to TestRail.
        Blocks until the browser is closed or stop() is called.

        Returns the completed CrawlSession.
        """
        self._session.state = "crawling"
        origin = urlparse(start_url).netloc

        with sync_playwright() as pw:
            browser: Browser = pw.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = browser.new_context(no_viewport=True)
            page: Page = context.new_page()

            print(f"\n[Crawler] Opening browser → {start_url}")
            page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)

            # ── Wait for login if we landed on a login page ───────────────────
            if _looks_like_login_page(page.url):
                print(
                    f"[Crawler] Login page detected. Please log in within "
                    f"{self.login_timeout_s}s…"
                )
                self._wait_for_login(page, origin)

            # ── Snapshot current page ─────────────────────────────────────────
            self._process_page(page, origin)

            # ── Register navigation handler ───────────────────────────────────
            last_url: dict = {"url": page.url}

            def _on_frame_navigated(frame):
                if frame != page.main_frame:
                    return
                new_url = frame.url
                if (
                    new_url == last_url["url"]
                    or new_url.startswith("about:")
                    or not self._same_origin(new_url, origin)
                ):
                    return
                last_url["url"] = new_url
                # Small settle delay then snapshot
                page.wait_for_timeout(self.page_settle_ms)
                self._process_page(page, origin)

            page.on("framenavigated", _on_frame_navigated)

            # ── Keep running until browser closed or stop() ───────────────────
            print("[Crawler] Browser ready. Navigate the app — each page will be crawled automatically.")
            print("[Crawler] Close the browser or press Ctrl+C to stop and push to TestRail.\n")

            try:
                while not self._stop_event.is_set():
                    try:
                        # Check if browser is still open
                        _ = page.url
                    except Exception:
                        # Browser was closed by user
                        break
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

            print("\n[Crawler] Stopping…")
            try:
                browser.close()
            except Exception:
                pass

        self._finalise()
        return self._session

    def stop(self) -> None:
        """Signal the crawler to stop after the current page."""
        self._stop_event.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _wait_for_login(self, page: Page, origin: str) -> None:
        """
        Poll until the URL leaves the login page or timeout expires.
        Gives the user time to fill in credentials manually.
        """
        deadline = time.time() + self.login_timeout_s
        while time.time() < deadline:
            try:
                current = page.url
            except Exception:
                return
            if not _looks_like_login_page(current) and self._same_origin(current, origin):
                print(f"[Crawler] Login detected — now at {current}")
                page.wait_for_timeout(self.page_settle_ms)
                return
            time.sleep(1)
        print("[Crawler] Login timeout reached — proceeding from current page.")

    def _process_page(self, page: Page, origin: str) -> None:
        url = page.url
        if self._session.is_visited(url):
            return
        if not self._same_origin(url, origin):
            return

        self._session.mark_visited(url)
        print(f"[Crawler] Snapshotting: {url}")

        try:
            snapshot: PageSnapshot = snapshot_page_a11y(
                page,
                include_html=(self.config.ai_provider not in ("rules", "none", "rule-based")),
            )

            cases = analyze_snapshot(
                snapshot,
                ai_client=self._ai,
                existing_context=self._session.ai_context,
            )

            if cases:
                self._session.add_cases(cases)
                output_dir = Path(self.config.output_dir)
                write_all_cases(cases, output_dir, base_url=self.config.base_url)

                print(f"[Crawler]   → {len(cases)} case(s) generated for {url}")
                if self.on_case_generated:
                    for c in cases:
                        self.on_case_generated(c)
            else:
                print(f"[Crawler]   → No cases generated for {url}")

        except Exception as e:
            print(f"[Crawler]   ✗ Error processing {url}: {e}")
            self._session.error = str(e)

    def _finalise(self) -> None:
        """Push all cases to TestRail and create a test run."""
        cases = self._session.all_cases
        if not cases:
            print("[Crawler] No cases to push.")
            self._session.state = "done"
            return

        print(f"\n[Crawler] Generated {len(cases)} total case(s).")

        try:
            from ..services.testrail_service import TestRailService
            tr = TestRailService()
            publisher = TestRailPublisher(
                testrail=tr,
                project_id=self.config.testrail_project_id,
                suite_id=self.config.testrail_suite_id,
                section_name=self.config.testrail_section_name,
            )
            case_ids = publisher.publish_all(cases)
            self._cases_pushed = len(case_ids)
            print(f"[Crawler] Pushed {self._cases_pushed} case(s) to TestRail.")

            if self.config.create_test_run and case_ids:
                from datetime import datetime
                run_name = f"Playwright Crawler — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                _, run_url = publisher.create_run(case_ids, run_name=run_name)
                self._session.test_run_url = run_url
                print(f"[Crawler] TestRail run: {run_url}")

        except Exception as e:
            print(f"[Crawler] TestRail push failed: {e}")
            self._session.error = str(e)

        self._session.state = "done"

    @staticmethod
    def _same_origin(url: str, origin: str) -> bool:
        try:
            return urlparse(url).netloc == origin
        except Exception:
            return False

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def status(self) -> dict:
        return {
            "state": self._session.state,
            "pages_visited": self._session.pages_visited,
            "cases_generated": self._session.cases_count,
            "cases_pushed": self._cases_pushed,
            "test_run_url": self._session.test_run_url,
            "error": self._session.error,
        }
