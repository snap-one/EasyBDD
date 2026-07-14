"""
Builder "Runs" view: browse TestRail runs for a project, drill into a run's
tests, and push a result (default Retest) onto selected cases.

Exercises /api/testrail/runs, /api/testrail/run/{id}/tests, and
/api/testrail/run/{id}/results against a fake TestRailService so no live
TestRail instance is required.
"""

import pytest
from fastapi.testclient import TestClient

import frontend.testrail_builder as tb

client = TestClient(tb.app)


class FakeTestRail:
    """Minimal stand-in for TestRailService covering the runs/tests/results surface."""

    def __init__(self):
        self.runs = {
            101: {
                "id": 101, "name": "EASY_BDD: Smoke — 2026-07-02", "is_completed": False,
                "created_on": 1750000000, "completed_on": None,
                "passed_count": 3, "blocked_count": 0, "untested_count": 2,
                "retest_count": 1, "failed_count": 1,
            },
            102: {
                "id": 102, "name": "EASY_BDD: Regression — closed", "is_completed": True,
                "created_on": 1749000000, "completed_on": 1749100000,
                "passed_count": 5, "blocked_count": 0, "untested_count": 0,
                "retest_count": 0, "failed_count": 0,
            },
        }
        self.tests = {
            101: [
                {"id": 1, "case_id": 501, "title": "Login works", "status_id": 1},
                {"id": 2, "case_id": 502, "title": "Logout works", "status_id": 5},
                {"id": 3, "case_id": 503, "title": "Password reset", "status_id": 3},
                {"id": 4, "case_id": 504, "title": "2FA challenge", "status_id": 3},
                {"id": 5, "case_id": 505, "title": "Session timeout", "status_id": 4},
                {"id": 6, "case_id": 506, "title": "Remember me", "status_id": 1},
                {"id": 7, "case_id": 507, "title": "Account lockout", "status_id": 1},
            ],
            102: [{"id": 8, "case_id": 601, "title": "Closed case", "status_id": 1}],
        }
        self.added_results = []

    def get_runs(self, project_id, created_after=None):
        return list(self.runs.values())

    def get_run(self, run_id):
        return self.runs[run_id]

    def get_tests(self, run_id):
        return self.tests[run_id]

    def get_statuses(self):
        return [
            {"id": 1, "label": "Passed"}, {"id": 2, "label": "Blocked"},
            {"id": 3, "label": "Untested"}, {"id": 4, "label": "Retest"},
            {"id": 5, "label": "Failed"},
        ]

    def add_results_for_cases(self, run_id, results):
        self.added_results.append((run_id, results))
        for r in results:
            for t in self.tests[run_id]:
                if t["case_id"] == r["case_id"]:
                    t["status_id"] = r["status_id"]
        return results


@pytest.fixture(autouse=True)
def fake_tr(monkeypatch):
    fake = FakeTestRail()
    monkeypatch.setattr(tb, "_tr_service", fake)
    monkeypatch.setattr(tb, "_status_cache", None)
    yield fake


class TestListRuns:
    def test_returns_runs_sorted_newest_first(self):
        r = client.get("/api/testrail/runs", params={"project_id": 59})
        assert r.status_code == 200
        body = r.json()
        assert [run["id"] for run in body] == [101, 102]

    def test_counts_and_progress_fields(self):
        body = client.get("/api/testrail/runs", params={"project_id": 59}).json()
        run = next(r for r in body if r["id"] == 101)
        assert run["counts"] == {"passed": 3, "blocked": 0, "untested": 2, "retest": 1, "failed": 1}
        assert run["total"] == 7
        assert run["is_completed"] is False

    def test_limit_param_caps_results(self):
        body = client.get("/api/testrail/runs", params={"project_id": 59, "limit": 1}).json()
        assert len(body) == 1
        assert body[0]["id"] == 101  # newest


class TestRunTests:
    def test_returns_run_and_tests_with_status_labels(self):
        r = client.get("/api/testrail/run/101/tests")
        assert r.status_code == 200
        body = r.json()
        assert body["run"]["id"] == 101
        assert len(body["tests"]) == 7
        by_case = {t["case_id"]: t for t in body["tests"]}
        assert by_case[501]["status"] == "Passed"
        assert by_case[502]["status"] == "Failed"
        assert by_case[505]["status"] == "Retest"

    def test_statuses_list_includes_all_five(self):
        body = client.get("/api/testrail/run/101/tests").json()
        labels = {s["label"] for s in body["statuses"]}
        assert {"Passed", "Blocked", "Untested", "Retest", "Failed"} <= labels


class TestMarkForRetest:
    def test_marks_selected_cases_retest_by_default(self, fake_tr):
        r = client.post("/api/testrail/run/101/results", json={"case_ids": [501, 502]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated"] == 2
        assert body["status_id"] == 4
        assert body["status"] == "Retest"
        run_id, results = fake_tr.added_results[0]
        assert run_id == 101
        assert {r["case_id"] for r in results} == {501, 502}
        assert all(r["status_id"] == 4 for r in results)

    def test_explicit_status_and_comment(self, fake_tr):
        r = client.post("/api/testrail/run/101/results", json={
            "case_ids": [503], "status_id": 1, "comment": "verified manually",
        })
        assert r.status_code == 200
        _, results = fake_tr.added_results[0]
        assert results[0] == {"case_id": 503, "status_id": 1, "comment": "verified manually"}

    def test_empty_selection_rejected(self):
        r = client.post("/api/testrail/run/101/results", json={"case_ids": []})
        assert r.status_code == 422

    def test_untested_status_rejected(self):
        r = client.post("/api/testrail/run/101/results", json={"case_ids": [501], "status_id": 3})
        assert r.status_code == 422
        assert "initial state" in r.json()["detail"]

    def test_unknown_status_rejected(self):
        r = client.post("/api/testrail/run/101/results", json={"case_ids": [501], "status_id": 999})
        assert r.status_code == 422

    def test_reflected_in_subsequent_tests_fetch(self, fake_tr):
        client.post("/api/testrail/run/101/results", json={"case_ids": [503, 504]})
        body = client.get("/api/testrail/run/101/tests").json()
        by_case = {t["case_id"]: t for t in body["tests"]}
        assert by_case[503]["status"] == "Retest"
        assert by_case[504]["status"] == "Retest"
