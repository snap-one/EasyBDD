"""
Crawl session — tracks state across multiple page snapshots within one crawl.

Maintains:
  - visited URLs (avoid re-processing)
  - accumulated generated test cases
  - AI context string (summaries of previously generated cases)
  - per-session configuration
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional, Set

from .models import CrawlSessionConfig, CrawlStatus, GeneratedTestCase, PageSnapshot


class CrawlSession:
    """Stateful session for a single crawl run."""

    def __init__(self, config: CrawlSessionConfig):
        self.session_id: str = str(uuid.uuid4())[:8]
        self.config = config
        self.state: str = "idle"
        self.created_at: float = time.time()
        self.pages_visited: int = 0
        self.current_url: Optional[str] = None
        self.error: Optional[str] = None
        self.test_run_url: Optional[str] = None

        self._visited_urls: Set[str] = set()
        self._cases: List[GeneratedTestCase] = []
        self._context_summaries: List[str] = []
        self._raw_snapshots: List[PageSnapshot] = []   # for deferred intelligent analysis

    # ── URL tracking ──────────────────────────────────────────────────────────

    def is_visited(self, url: str) -> bool:
        return self._normalise_url(url) in self._visited_urls

    def mark_visited(self, url: str) -> None:
        self._visited_urls.add(self._normalise_url(url))
        self.pages_visited += 1
        self.current_url = url

    @staticmethod
    def _normalise_url(url: str) -> str:
        """Strip fragment and trailing slash for dedup."""
        url = url.split("#")[0].rstrip("/")
        return url

    # ── Cases ─────────────────────────────────────────────────────────────────

    def store_snapshot(self, snapshot: PageSnapshot) -> None:
        """Accumulate raw snapshots for deferred intelligent analysis."""
        self._raw_snapshots.append(snapshot)

    @property
    def raw_snapshots(self) -> List[PageSnapshot]:
        return list(self._raw_snapshots)

    def add_cases(self, cases: List[GeneratedTestCase]) -> None:
        self._cases.extend(cases)
        # Keep a rolling AI context of names/descriptions for deduplication hints
        for c in cases:
            self._context_summaries.append(f"- {c.name}: {c.description}")

    @property
    def all_cases(self) -> List[GeneratedTestCase]:
        return list(self._cases)

    @property
    def cases_count(self) -> int:
        return len(self._cases)

    @property
    def ai_context(self) -> Optional[str]:
        """Return a brief context string of existing cases for the AI."""
        if not self._context_summaries:
            return None
        return "Already generated:\n" + "\n".join(self._context_summaries[-20:])

    # ── Status ────────────────────────────────────────────────────────────────

    def to_status(self, cases_pushed: int = 0) -> CrawlStatus:
        return CrawlStatus(
            session_id=self.session_id,
            state=self.state,
            pages_visited=self.pages_visited,
            cases_generated=self.cases_count,
            cases_pushed=cases_pushed,
            current_url=self.current_url,
            error=self.error,
            test_run_url=self.test_run_url,
        )
