"""
TestRail API service for Easy BDD Framework.
Provides read/write access to TestRail runs, tests, cases, results, and attachments.
"""

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class TestRailError(Exception):
    """Raised when a TestRail API call fails."""


class RunVariables:
    """Run variables stored in the TestRail run description as JSON.

    Store as JSON in the run description field:
        {"retry": 1, "cron": "0 9 * * MON-FRI", "data": {"base_url": "https://staging.example.com"}}
    """

    def __init__(self, data: Dict[str, Any] = None):
        data = data or {}
        self.cron: Optional[str] = data.get("cron")
        self.retry: int = int(data.get("retry", 0))
        self.rerun: int = int(data.get("rerun", 0))
        self.test_order: str = data.get("test_order", "sequential")
        self.execute_options: Dict[str, Any] = data.get("execute_options", {})
        # Extra variables injected into every test run from this run
        self.extra: Dict[str, Any] = data.get("data", {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cron": self.cron,
            "retry": self.retry,
            "rerun": self.rerun,
            "test_order": self.test_order,
            "execute_options": self.execute_options,
            "data": self.extra,
        }


class TestRailService:
    """TestRail API client using requests + HTTP Basic auth.

    Credentials are read from environment variables by default:
        TESTRAIL_URL      — base URL, e.g. https://testrail.control4.com
        TESTRAIL_USERNAME — API user e-mail
        TESTRAIL_API_KEY  — API key (not account password)
    """

    # Standard TestRail status IDs (instance-specific custom statuses may differ)
    STATUS_PASSED = 1
    STATUS_BLOCKED = 2
    STATUS_UNTESTED = 3
    STATUS_RETEST = 4
    STATUS_FAILED = 5
    STATUS_RUNNING = 7  # Custom "Running" status (instance-specific; 6 = Not Applicable here)

    def __init__(
        self,
        url: str = None,
        username: str = None,
        api_key: str = None,
    ):
        self._base_url = (url or os.getenv("TESTRAIL_URL", "")).rstrip("/")
        username = username or os.getenv("TESTRAIL_USERNAME", "")
        api_key = api_key or os.getenv("TESTRAIL_API_KEY", "")

        if not self._base_url:
            raise TestRailError(
                "TESTRAIL_URL is not configured. Set it in .env or pass url= to TestRailService()."
            )
        if not username or not api_key:
            raise TestRailError(
                "TESTRAIL_USERNAME and TESTRAIL_API_KEY must be set in .env or passed explicitly."
            )

        credentials = base64.b64encode(f"{username}:{api_key}".encode()).decode()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------ #
    # Internal HTTP helpers                                                #
    # ------------------------------------------------------------------ #

    def _api_url(self, path: str) -> str:
        path = path.lstrip("/")
        if path.startswith("index.php"):
            return f"{self._base_url}/{path}"
        return f"{self._base_url}/index.php?/api/v2/{path}"

    def _get(self, path: str) -> Any:
        resp = self._session.get(self._api_url(path))
        self._raise_for_status(resp)
        return resp.json()

    def _post(self, path: str, payload: Dict[str, Any] = None) -> Any:
        resp = self._session.post(self._api_url(path), json=payload or {})
        self._raise_for_status(resp)
        try:
            return resp.json()
        except Exception:
            return {}

    def _raise_for_status(self, resp: requests.Response) -> None:
        if not resp.ok:
            try:
                body = resp.json()
                msg = body.get("error", resp.text[:300])
            except Exception:
                msg = resp.text[:300]
            raise TestRailError(f"TestRail API error {resp.status_code}: {msg}")

    def _paginated(self, path: str, key: str) -> List[Dict[str, Any]]:
        """Fetch all pages from a paginated TestRail endpoint."""
        items: List[Dict[str, Any]] = []
        next_path: Optional[str] = path
        while next_path:
            data = self._get(next_path)
            if isinstance(data, list):
                items.extend(data)
                break
            if isinstance(data, dict):
                batch = data.get(key)
                if isinstance(batch, list):
                    items.extend(batch)
                next_url = data.get("_links", {}).get("next")
                if next_url:
                    # next_url is like "index.php?/api/v2/get_tests/123&offset=250"
                    if "/api/v2/" in next_url:
                        next_path = next_url.split("/api/v2/", 1)[1]
                    else:
                        next_path = next_url
                else:
                    next_path = None
            else:
                break
        return items

    # ------------------------------------------------------------------ #
    # Runs                                                                 #
    # ------------------------------------------------------------------ #

    def get_runs(self, project_id: int, created_after: int = None) -> List[Dict]:
        path = f"get_runs/{project_id}"
        if created_after is not None:
            path += f"&created_after={created_after}"
        return self._paginated(path, "runs")

    def get_run(self, run_id: int) -> Dict:
        return self._get(f"get_run/{run_id}")

    def add_run(self, project_id: int, **kwargs) -> Dict:
        return self._post(f"add_run/{project_id}", kwargs)

    def update_run(self, run_id: int, **kwargs) -> Dict:
        return self._post(f"update_run/{run_id}", kwargs)

    def close_run(self, run_id: int) -> Dict:
        return self._post(f"close_run/{run_id}")

    def delete_run(self, run_id: int) -> None:
        self._post(f"delete_run/{run_id}")

    # ------------------------------------------------------------------ #
    # Tests (instances of cases within a run)                              #
    # ------------------------------------------------------------------ #

    def get_tests(self, run_id: int) -> List[Dict]:
        return self._paginated(f"get_tests/{run_id}", "tests")

    def get_test(self, test_id: int) -> Dict:
        return self._get(f"get_test/{test_id}")

    # ------------------------------------------------------------------ #
    # Results                                                              #
    # ------------------------------------------------------------------ #

    def add_result(
        self,
        test_id: int,
        status_id: int,
        comment: str = "",
        elapsed: str = None,
    ) -> Dict:
        payload: Dict[str, Any] = {"status_id": status_id, "comment": comment}
        if elapsed:
            payload["elapsed"] = elapsed
        return self._post(f"add_result/{test_id}", payload)

    def add_results(self, run_id: int, results: List[Dict]) -> List:
        return self._post(f"add_results/{run_id}", {"results": results})

    def get_results(self, test_id: int) -> List[Dict]:
        return self._paginated(f"get_results/{test_id}", "results")

    def get_results_for_run(self, run_id: int) -> List[Dict]:
        return self._paginated(f"get_results_for_run/{run_id}", "results")

    # ------------------------------------------------------------------ #
    # Cases                                                                #
    # ------------------------------------------------------------------ #

    def get_case(self, case_id: int) -> Dict:
        return self._get(f"get_case/{case_id}")

    def get_cases(self, project_id: int, suite_id: int = None) -> List[Dict]:
        path = f"get_cases/{project_id}"
        if suite_id is not None:
            path += f"&suite_id={suite_id}"
        return self._paginated(path, "cases")

    def add_case(self, section_id: int, **kwargs) -> Dict:
        return self._post(f"add_case/{section_id}", kwargs)

    def update_case(self, case_id: int, **kwargs) -> Dict:
        return self._post(f"update_case/{case_id}", kwargs)

    def delete_case(self, case_id: int) -> None:
        self._post(f"delete_case/{case_id}")

    # ------------------------------------------------------------------ #
    # Suites                                                               #
    # ------------------------------------------------------------------ #

    def get_suite(self, suite_id: int) -> Dict:
        return self._get(f"get_suite/{suite_id}")

    def get_suites(self, project_id: int) -> List[Dict]:
        data = self._get(f"get_suites/{project_id}")
        return data if isinstance(data, list) else data.get("suites", [])

    def add_suite(self, project_id: int, **kwargs) -> Dict:
        return self._post(f"add_suite/{project_id}", kwargs)

    def update_suite(self, suite_id: int, **kwargs) -> Dict:
        return self._post(f"update_suite/{suite_id}", kwargs)

    def delete_suite(self, suite_id: int) -> None:
        self._post(f"delete_suite/{suite_id}")

    # ------------------------------------------------------------------ #
    # Sections                                                             #
    # ------------------------------------------------------------------ #

    def get_sections(self, project_id: int, suite_id: int = None) -> List[Dict]:
        path = f"get_sections/{project_id}"
        if suite_id is not None:
            path += f"&suite_id={suite_id}"
        return self._paginated(path, "sections")

    def add_section(self, project_id: int, **kwargs) -> Dict:
        return self._post(f"add_section/{project_id}", kwargs)

    # ------------------------------------------------------------------ #
    # Projects                                                             #
    # ------------------------------------------------------------------ #

    def get_project(self, project_id: int) -> Dict:
        return self._get(f"get_project/{project_id}")

    def get_projects(self) -> List[Dict]:
        data = self._get("get_projects")
        return data if isinstance(data, list) else data.get("projects", [])

    # ------------------------------------------------------------------ #
    # Milestones                                                           #
    # ------------------------------------------------------------------ #

    def get_milestone(self, milestone_id: int) -> Dict:
        return self._get(f"get_milestone/{milestone_id}")

    def get_milestones(self, project_id: int) -> List[Dict]:
        return self._paginated(f"get_milestones/{project_id}", "milestones")

    # ------------------------------------------------------------------ #
    # Plans                                                                #
    # ------------------------------------------------------------------ #

    def get_plan(self, plan_id: int) -> Dict:
        return self._get(f"get_plan/{plan_id}")

    def get_plans(self, project_id: int) -> List[Dict]:
        return self._paginated(f"get_plans/{project_id}", "plans")

    def add_plan(self, project_id: int, **kwargs) -> Dict:
        return self._post(f"add_plan/{project_id}", kwargs)

    # ------------------------------------------------------------------ #
    # Users                                                                #
    # ------------------------------------------------------------------ #

    def get_user(self, user_id: int) -> Dict:
        return self._get(f"get_user/{user_id}")

    def get_user_by_email(self, email: str) -> Dict:
        return self._get(f"get_user_by_email&email={email}")

    def get_users(self, project_id: int = None) -> List[Dict]:
        path = "get_users"
        if project_id is not None:
            path += f"&project_id={project_id}"
        data = self._get(path)
        return data if isinstance(data, list) else data.get("users", [])

    # ------------------------------------------------------------------ #
    # Attachments                                                          #
    # ------------------------------------------------------------------ #

    def add_attachment_to_run(self, run_id: int, file_path: str) -> Dict:
        return self._upload(f"add_attachment_to_run/{run_id}", file_path)

    def add_attachment_to_result(self, result_id: int, file_path: str) -> Dict:
        return self._upload(f"add_attachment_to_result/{result_id}", file_path)

    def get_attachments_for_test(self, test_id: int) -> List[Dict]:
        data = self._get(f"get_attachments_for_test/{test_id}")
        return data if isinstance(data, list) else data.get("attachments", [])

    def get_attachments_for_run(self, run_id: int) -> List[Dict]:
        data = self._get(f"get_attachments_for_run/{run_id}")
        return data if isinstance(data, list) else data.get("attachments", [])

    def _upload(self, path: str, file_path: str) -> Dict:
        auth_header = self._session.headers["Authorization"]
        file_path_obj = Path(file_path)
        with open(file_path_obj, "rb") as f:
            resp = requests.post(
                self._api_url(path),
                headers={"Authorization": auth_header},
                files={"attachment": (file_path_obj.name, f)},
            )
        self._raise_for_status(resp)
        return resp.json()

    # ------------------------------------------------------------------ #
    # Reports                                                              #
    # ------------------------------------------------------------------ #

    def get_reports(self, project_id: int) -> List[Dict]:
        data = self._get(f"get_reports/{project_id}")
        return data if isinstance(data, list) else data.get("reports", [])

    def run_report(self, report_id: int) -> Dict:
        return self._get(f"run_report/{report_id}")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_run_vars(description: str = None) -> RunVariables:
        """Parse run variables from a TestRail run description string."""
        import html as _html
        try:
            raw = json.loads(_html.unescape(description or "{}"))
        except (json.JSONDecodeError, Exception):
            raw = {}
        return RunVariables(raw)
