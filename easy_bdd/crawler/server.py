"""
Easy BDD Crawler — FastAPI local server.

Endpoints:
  GET  /health                  — liveness check
  GET  /config                  — return TestRail projects + AI config for the extension popup
  POST /crawl/start             — start a new crawl session
  POST /crawl/snapshot          — receive a page snapshot, analyse, write YAML
  POST /crawl/stop              — finalise crawl: push to TestRail, create run
  GET  /crawl/status            — poll crawl progress
  POST /heal                    — single-shot selector self-heal call

Start with:
  python -m easy_bdd crawler start [--port 8765]
"""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .ai_client import build_ai_client
from .crawl_session import CrawlSession
from .models import (
    AnalyzeResponse,
    ConfigResponse,
    CrawlSessionConfig,
    CrawlStatus,
    PageSnapshot,
)
from .page_analyzer import analyze_snapshot
from .testrail_publisher import TestRailPublisher
from .yaml_writer import write_all_cases

# Intelligent mode: deferred 3-phase analysis (map → plan → generate)
_INTELLIGENT_PROVIDERS = {"intelligent", "auto", "automap"}


# ── App factory ────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="Easy BDD Crawler",
        description="Local server for the Easy BDD Chrome extension — AI-driven test generation.",
        version="1.0.0",
    )

    # Allow the Chrome extension (chrome-extension://*) to POST here
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Session store (single active session; multi-session trivially extensible) ──
    _sessions: Dict[str, CrawlSession] = {}

    def _active_session(session_id: str) -> CrawlSession:
        if session_id not in _sessions:
            raise HTTPException(404, f"Session '{session_id}' not found")
        return _sessions[session_id]

    # ── Endpoints ──────────────────────────────────────────────────────────────

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "service": "easy-bdd-crawler"}

    @app.get("/config", response_model=ConfigResponse)
    def get_config() -> ConfigResponse:
        """Return TestRail config + AI provider info for the extension popup."""
        try:
            from ..services.testrail_service import TestRailService, TestRailError

            tr = TestRailService()
            projects = tr.get_projects()
            testrail_url = os.getenv("TESTRAIL_URL", "")
        except Exception as e:
            return ConfigResponse(
                testrail_url="",
                testrail_projects=[],
                ai_provider=os.getenv("CRAWLER_AI_PROVIDER", "claude"),
                ai_model=os.getenv("CRAWLER_AI_MODEL", ""),
                status="error",
                error=str(e),
            )
        return ConfigResponse(
            testrail_url=testrail_url,
            testrail_projects=[
                {"id": p["id"], "name": p["name"]} for p in projects
            ],
            ai_provider=os.getenv("CRAWLER_AI_PROVIDER", "claude"),
            ai_model=os.getenv("CRAWLER_AI_MODEL", ""),
            status="ok",
        )

    @app.get("/config/suites")
    def get_suites(project_id: int) -> Any:
        """Return suites for a TestRail project (for the popup dropdown)."""
        try:
            from ..services.testrail_service import TestRailService
            tr = TestRailService()
            suites = tr.get_suites(project_id)
            return [{"id": s["id"], "name": s["name"]} for s in suites]
        except Exception as e:
            return []

    @app.post("/crawl/start")
    def start_crawl(config: CrawlSessionConfig) -> Dict[str, str]:
        """Initialise a new crawl session and return its ID."""
        session = CrawlSession(config)
        session.state = "crawling"
        _sessions[session.session_id] = session
        return {"session_id": session.session_id, "status": "crawling"}

    @app.post("/crawl/snapshot", response_model=AnalyzeResponse)
    def receive_snapshot(
        session_id: str,
        snapshot: PageSnapshot,
    ) -> AnalyzeResponse:
        """
        Receive a page snapshot from the content script, analyse it,
        generate YAML test cases, and return the results.
        """
        session = _active_session(session_id)

        if session.is_visited(snapshot.url):
            return AnalyzeResponse(
                session_id=session_id,
                page_url=snapshot.url,
                cases=[],
                status="skipped",
            )

        session.mark_visited(snapshot.url)
        snapshot.timestamp = time.time()

        # ── Intelligent (deferred) mode ─────────────────────────────────────────
        provider = (session.config.ai_provider or "").lower()
        if provider in _INTELLIGENT_PROVIDERS:
            session.store_snapshot(snapshot)
            session.state = "crawling"
            return AnalyzeResponse(
                session_id=session_id,
                page_url=snapshot.url,
                cases=[],
                status="deferred",
            )

        # ── Immediate per-page mode ────────────────────────────────────────────
        session.state = "generating"

        try:
            ai = build_ai_client(
                provider=session.config.ai_provider,
                model=session.config.ai_model,
            )
            cases = analyze_snapshot(
                snapshot,
                ai_client=ai,
                existing_context=session.ai_context,
            )
            session.add_cases(cases)
            session.state = "crawling"

            # Write YAML files immediately
            output_dir = Path(session.config.output_dir)
            write_all_cases(cases, output_dir, base_url=session.config.base_url)

            return AnalyzeResponse(
                session_id=session_id,
                page_url=snapshot.url,
                cases=cases,
                status="ok",
            )
        except Exception as e:
            session.state = "error"
            session.error = str(e)
            traceback.print_exc()
            return AnalyzeResponse(
                session_id=session_id,
                page_url=snapshot.url,
                cases=[],
                status="error",
                error=str(e),
            )

    @app.post("/crawl/stop", response_model=CrawlStatus)
    def stop_crawl(session_id: str) -> CrawlStatus:
        """
        Finalise the crawl: push all generated cases to TestRail
        and optionally create a test run.

        In intelligent mode, runs the 3-phase SitePlanner analysis first
        (rule-based per page + Ollama workflow planning + workflow generation).
        """
        session = _active_session(session_id)
        cases_pushed = 0
        run_url: Optional[str] = None

        # ── Intelligent mode: run deferred 3-phase analysis ────────────────────
        provider = (session.config.ai_provider or "").lower()
        if provider in _INTELLIGENT_PROVIDERS and session.raw_snapshots:
            session.state = "analyzing"
            try:
                from .site_planner import SitePlanner

                ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                ollama_model = os.getenv("CRAWLER_AI_MODEL", "qwen3-coder:30b-a3b-q4_K_M")
                planner = SitePlanner(
                    ollama_base_url=ollama_url,
                    model=ollama_model,
                )
                output_dir = Path(session.config.output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                all_cases = planner.run(session.raw_snapshots, str(output_dir))
                session.add_cases(all_cases)
            except Exception as e:
                session.state = "error"
                session.error = f"Intelligent analysis failed: {e}"
                traceback.print_exc()
                return session.to_status(cases_pushed=0)

        session.state = "pushing"

        try:
            from ..services.testrail_service import TestRailService

            tr = TestRailService()
            publisher = TestRailPublisher(
                testrail=tr,
                project_id=session.config.testrail_project_id,
                suite_id=session.config.testrail_suite_id,
                section_name=session.config.testrail_section_name,
            )
            case_ids = publisher.publish_all(session.all_cases)
            cases_pushed = len(case_ids)

            if session.config.create_test_run and case_ids:
                from datetime import datetime

                run_name = f"Crawler Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                _, run_url = publisher.create_run(case_ids, run_name=run_name)
                session.test_run_url = run_url

        except Exception as e:
            session.state = "error"
            session.error = f"TestRail push failed: {e}"
            traceback.print_exc()
            return session.to_status(cases_pushed=cases_pushed)

        session.state = "done"
        return session.to_status(cases_pushed=cases_pushed)

    @app.get("/crawl/status/{session_id}", response_model=CrawlStatus)
    def crawl_status(session_id: str) -> CrawlStatus:
        session = _active_session(session_id)
        return session.to_status()

    @app.post("/heal")
    def self_heal(body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Single-shot selector self-heal request from a running test.

        Body:
          {
            "broken_selector": "#old-id",
            "element_description": "Submit button on login form",
            "page_html": "<html>...",
            "ranked_selectors": [...],   // RankedSelector objects
            "ai_provider": os.getenv("CRAWLER_AI_PROVIDER", "rules")
          }
        """
        from .models import RankedSelector
        from .self_healer import SelfHealer

        broken = body.get("broken_selector", "")
        description = body.get("element_description", "")
        html = body.get("page_html", "")
        raw_ranked = body.get("ranked_selectors", [])
        ranked = [RankedSelector(**r) for r in raw_ranked if isinstance(r, dict)]
        provider = body.get("ai_provider", os.getenv("CRAWLER_AI_PROVIDER", "claude"))

        ai = build_ai_client(provider=provider)
        healer = SelfHealer(ai_client=ai)
        new_sel = healer.heal(
            broken_selector=broken,
            element_description=description,
            page_html=html,
            ranked_selectors=ranked,
        )
        return {"healed_selector": new_sel, "success": new_sel is not None}

    return app


# ── Runner ────────────────────────────────────────────────────────────────────


def run_server(host: str = "127.0.0.1", port: int = 8765, reload: bool = False) -> None:
    """Start the Uvicorn server."""
    import uvicorn

    app = create_app()
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
