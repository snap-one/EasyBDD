"""
Pydantic models for the crawler API — shared between server and client.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Inbound (extension → server) ──────────────────────────────────────────────


class ElementSnapshot(BaseModel):
    """A single interactive element detected on the page."""

    tag: str
    type: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    label: Optional[str] = None
    placeholder: Optional[str] = None
    text: Optional[str] = None
    value: Optional[str] = None
    href: Optional[str] = None
    id: Optional[str] = None
    css_class: Optional[str] = None
    data_testid: Optional[str] = None
    aria_label: Optional[str] = None
    # Select element options [{value, text}]
    options: Optional[List[Dict[str, str]]] = None
    # Whether the field is required
    required: bool = False
    # Generated selector candidates (ordered best-first by content script)
    selectors: List[str] = Field(default_factory=list)
    # Bounding box for visual similarity self-healing
    bbox: Optional[Dict[str, float]] = None
    # True when element lives inside an iframe
    in_iframe: bool = False
    iframe_selector: Optional[str] = None
    # Screenshot of the element region (base64 PNG), optional
    screenshot_b64: Optional[str] = None


class PageSnapshot(BaseModel):
    """Full snapshot of a crawled page, sent from the content script."""

    url: str
    title: str
    origin: str
    path: str
    # Serialised HTML (truncated to 200 kB by the content script)
    html: Optional[str] = None
    elements: List[ElementSnapshot] = Field(default_factory=list)
    # Full-page screenshot (base64 PNG), optional
    screenshot_b64: Optional[str] = None
    # Iframe origins detected on the page
    iframes: List[str] = Field(default_factory=list)
    timestamp: float = 0.0


class CrawlSessionConfig(BaseModel):
    """Configuration sent by the extension when the user starts a crawl."""

    testrail_project_id: int
    testrail_suite_id: Optional[int] = None
    testrail_section_name: str = "Auto-generated"
    create_test_run: bool = True
    ai_provider: str = "claude"          # "claude" | "ollama"
    ai_model: Optional[str] = None       # e.g. "claude-opus-4-8" or "llama3"
    output_dir: str = "tests/cases/crawled"
    base_url: str = ""


# ── Outbound (server → extension) ─────────────────────────────────────────────


class RankedSelector(BaseModel):
    selector: str
    strategy: str       # "css" | "aria" | "xpath" | "text" | "testid"
    score: float        # 0-1, higher = more stable
    iframe_prefix: Optional[str] = None


class GeneratedStep(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    selectors: List[RankedSelector] = Field(default_factory=list)


class GeneratedTestCase(BaseModel):
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    url: str
    steps: List[GeneratedStep] = Field(default_factory=list)
    yaml_path: Optional[str] = None          # path written to disk
    testrail_case_id: Optional[int] = None   # ID after pushing to TestRail


class CrawlStatus(BaseModel):
    session_id: str
    state: str          # "idle" | "crawling" | "generating" | "pushing" | "done" | "error"
    pages_visited: int = 0
    cases_generated: int = 0
    cases_pushed: int = 0
    current_url: Optional[str] = None
    error: Optional[str] = None
    test_run_url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    session_id: str
    page_url: str
    cases: List[GeneratedTestCase] = Field(default_factory=list)
    status: str = "ok"
    error: Optional[str] = None


class ConfigResponse(BaseModel):
    testrail_url: str
    testrail_projects: List[Dict[str, Any]] = Field(default_factory=list)
    ai_provider: str = "claude"
    ai_model: str = ""
    status: str = "ok"
    error: Optional[str] = None
