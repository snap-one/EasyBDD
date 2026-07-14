"""
Easy BDD Crawler — AI-driven web UI explorer and test generator.

Starts a local FastAPI server that the Chrome extension POSTs page snapshots to.
The server uses an AI backend (Claude or Ollama) to analyze the UI, rank selectors,
generate Easy BDD YAML test files, and push cases to TestRail.

Usage:
    python -m easybdd crawler start            # default port 8765
    python -m easybdd crawler start --port 9000
"""

from .server import create_app, run_server

__all__ = ["create_app", "run_server"]
