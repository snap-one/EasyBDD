"""
Jenkins API service for Easy BDD Framework.
Triggers parameterized builds and resolves queued items to their assigned build.
"""

import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests


class JenkinsError(Exception):
    """Raised when a Jenkins API call fails."""


class JenkinsService:
    """Jenkins API client using requests + HTTP Basic auth.

    Credentials are read from environment variables by default:
        JENKINS_URL        — base URL, e.g. http://192.168.100.100:8080
        JENKINS_USERNAME   — Jenkins user
        JENKINS_API_TOKEN  — API token (user icon > Configure > API Token > Add new Token)
    """

    def __init__(self, url: str = None, username: str = None, api_token: str = None):
        self._base_url = (url or os.getenv("JENKINS_URL", "")).rstrip("/")
        username = username or os.getenv("JENKINS_USERNAME", "")
        api_token = api_token or os.getenv("JENKINS_API_TOKEN", "")

        if not self._base_url:
            raise JenkinsError(
                "JENKINS_URL is not configured. Set it in .env or pass url= to JenkinsService()."
            )
        if not username or not api_token:
            raise JenkinsError(
                "JENKINS_USERNAME and JENKINS_API_TOKEN must be set in .env or passed explicitly."
            )

        self._session = requests.Session()
        self._session.auth = (username, api_token)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _job_url(self, job_name: str) -> str:
        # Job names may live under folders ("Team/Sub Job"); each path segment
        # is percent-encoded on its own so literal spaces/slashes survive.
        segments = "/job/".join(quote(part, safe="") for part in job_name.split("/"))
        return f"{self._base_url}/job/{segments}"

    def _crumb_headers(self) -> Dict[str, str]:
        resp = self._session.get(f"{self._base_url}/crumbIssuer/api/json")
        if resp.status_code == 404:
            return {}  # CSRF crumb issuer disabled on this instance
        self._raise_for_status(resp)
        data = resp.json()
        return {data["crumbRequestField"]: data["crumb"]}

    def _raise_for_status(self, resp: requests.Response) -> None:
        if not resp.ok:
            raise JenkinsError(f"Jenkins API error {resp.status_code}: {resp.text[:300]}")

    # ------------------------------------------------------------------ #
    # Builds                                                               #
    # ------------------------------------------------------------------ #

    def trigger_build(self, job_name: str, params: Dict[str, Any]) -> str:
        """Trigger a parameterized build. Returns the queue item URL."""
        headers = self._crumb_headers()
        resp = self._session.post(
            f"{self._job_url(job_name)}/buildWithParameters",
            params=params,
            headers=headers,
        )
        self._raise_for_status(resp)
        queue_url = resp.headers.get("Location")
        if not queue_url:
            raise JenkinsError(
                "Jenkins accepted the trigger but returned no queue item location."
            )
        return queue_url.rstrip("/") + "/"

    def resolve_queue_item(
        self, queue_url: str, timeout: float = 15.0, interval: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """Poll a queue item until Jenkins assigns it a real build, or give up.

        Returns {"number": int, "url": str} once scheduled, or None if it's
        still waiting in the queue when the timeout elapses (not an error —
        the caller can still link to the queue item itself).
        """
        deadline = time.monotonic() + timeout
        while True:
            resp = self._session.get(f"{queue_url}api/json")
            self._raise_for_status(resp)
            data = resp.json()
            executable = data.get("executable")
            if executable:
                return {"number": executable.get("number"), "url": executable.get("url")}
            if data.get("cancelled"):
                raise JenkinsError("Jenkins build was cancelled while queued.")
            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)
