"""TestRail run result reporter — datalake and Teams webhook delivery.

Extracted from testrail_runner.py so reporting concerns are separate from
test execution logic. TestRailRunner holds a TestRailReporter instance and
delegates outbound notifications to it.
"""

import os
from datetime import datetime


class TestRailReporter:
    """Posts TestRail run outcomes to the datalake and a Teams webhook."""

    def post_datalake(
        self,
        *,
        run_title: str,
        run_id: int,
        product: str,
        product_category: str,
        mac_address: str,
        time_savings: float,
        success: bool,
        start_time: datetime,
        verbose: bool = True,
    ) -> None:
        """Post one datalake entry for the entire TestRail run."""
        try:
            from .datalake_logger import DatalakeLogger
            dl = DatalakeLogger(artifact_path="reports", post_results=True)
            run_url = (
                f"{os.getenv('TESTRAIL_URL', '').rstrip('/')}"
                f"/index.php?/runs/view/{run_id}"
            )
            dl.datalake_post(
                test_name=run_title,
                product=product,
                product_category=product_category,
                mac_address=mac_address,
                time_savings=time_savings,
                start_time=start_time,
                console="",
                run_url=run_url,
                success=success,
                type="testrail",
                run_title=run_title,
            )
            if verbose:
                print(f"\n[TestRail] Datalake posted for run: {run_title!r}")
        except Exception as exc:
            if verbose:
                print(f"\n[TestRail] Datalake post failed: {exc}")

    def post_teams(
        self,
        *,
        run_title: str,
        run_id: int,
        total_passed: int,
        total_failed: int,
        total_skipped: int,
        success: bool,
        start_time: datetime,
        verbose: bool = True,
    ) -> None:
        """Send a Teams Adaptive Card with TestRail run results + Jenkins build link."""
        webhook_url = os.getenv("TEAMS_WEBHOOK_URL", "")
        if not webhook_url:
            return

        try:
            import requests as _requests
        except ImportError:
            return

        testrail_base = os.getenv("TESTRAIL_URL", "").rstrip("/")
        testrail_url = f"{testrail_base}/index.php?/runs/view/{run_id}"
        jenkins_url = os.getenv("BUILD_URL", "")

        status_emoji = "✅" if success else "❌"
        status_text = "PASSED" if success else "FAILED"

        duration_secs = int((datetime.now() - start_time).total_seconds())
        duration_str = f"{duration_secs // 60}m {duration_secs % 60}s"

        facts = [
            {"title": "Status",   "value": f"{status_emoji} {status_text}"},
            {"title": "Passed",   "value": str(total_passed)},
            {"title": "Failed",   "value": str(total_failed)},
            {"title": "Skipped",  "value": str(total_skipped)},
            {"title": "Duration", "value": duration_str},
        ]

        body = [
            {
                "type": "TextBlock",
                "text": f"{status_emoji} **{run_title}**",
                "size": "Medium",
                "weight": "Bolder",
                "wrap": True,
            },
            {"type": "FactSet", "facts": facts},
        ]

        actions = [
            {
                "type": "Action.OpenUrl",
                "title": "View TestRail Run",
                "url": testrail_url,
            },
        ]
        if jenkins_url:
            actions.append(
                {
                    "type": "Action.OpenUrl",
                    "title": "View Jenkins Log",
                    "url": jenkins_url,
                }
            )

        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "msteams": {"width": "Full"},
                        "body": body,
                        "actions": actions,
                    },
                }
            ],
        }

        try:
            resp = _requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if verbose:
                if resp.status_code in (200, 202):
                    print(f"\n[TestRail] Teams notification sent for run: {run_title!r}")
                else:
                    print(
                        f"\n[TestRail] Teams notification failed "
                        f"({resp.status_code}): {resp.text[:200]}"
                    )
        except Exception as exc:
            if verbose:
                print(f"\n[TestRail] Teams notification error: {exc}")
