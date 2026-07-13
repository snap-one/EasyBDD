"""TestRail run result reporter — datalake delivery.

Extracted from testrail_runner.py so reporting concerns are separate from
test execution logic. TestRailRunner holds a TestRailReporter instance and
delegates outbound notifications to it.
"""

import os
from datetime import datetime


class TestRailReporter:
    """Posts TestRail run outcomes to the datalake."""

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
