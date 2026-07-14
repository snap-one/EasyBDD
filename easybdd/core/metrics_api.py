"""
Metrics API for Easy BDD Framework

REST API for querying test metrics, trends, and analytics.

Optional Dependencies:
    pip install fastapi uvicorn
"""

from pathlib import Path
from typing import Optional, List
from datetime import datetime

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import JSONResponse, HTMLResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("\n⚠️  FastAPI not installed. Metrics API requires optional dependencies.")
    print("   Install with: pip install fastapi uvicorn")
    print("   Or use the CLI tool instead: python -m easybdd.tools.metrics_cli\n")
    import sys
    sys.exit(1)

from easybdd.core.metrics_engine import TestMetrics


class MetricsAPI:
    """FastAPI-based metrics API"""

    def __init__(self, results_dir: Path = None, s3_bucket: str = None):
        """
        Initialize metrics API

        Args:
            results_dir: Directory with test results
            s3_bucket: S3 bucket for remote data
        """
        self.app = FastAPI(
            title="Easy BDD Metrics API",
            description="Query test execution metrics and analytics",
            version="1.0.0",
        )
        self.metrics = TestMetrics(results_dir, s3_bucket)
        self._setup_routes()

    def _setup_routes(self):
        """Setup API routes"""

        @self.app.get("/")
        async def root():
            """API documentation"""
            return {
                "name": "Easy BDD Metrics API",
                "version": "1.0.0",
                "endpoints": {
                    "/health": "Health check",
                    "/metrics/dashboard": "Summary dashboard",
                    "/metrics/history": "Test execution history",
                    "/metrics/pass-rate": "Pass rate trends",
                    "/metrics/flaky-tests": "Identify flaky tests",
                    "/metrics/duration": "Duration trends",
                    "/metrics/export": "Export metrics report",
                },
            }

        @self.app.get("/health")
        async def health():
            """Health check endpoint"""
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

        @self.app.get("/metrics/dashboard")
        async def get_dashboard(
            days: int = Query(7, ge=1, le=365, description="Number of days to analyze")
        ):
            """
            Get comprehensive dashboard summary

            Args:
                days: Number of days to include (default: 7)

            Returns:
                Dashboard metrics including pass rates, flaky tests, etc.
            """
            try:
                dashboard = self.metrics.get_summary_dashboard(days=days)
                return JSONResponse(content=dashboard)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics/history")
        async def get_history(
            test_name: Optional[str] = Query(
                None, description="Specific test name (optional)"
            ),
            days: int = Query(30, ge=1, le=365, description="Number of days"),
        ):
            """
            Get test execution history

            Args:
                test_name: Filter by specific test name (optional)
                days: Number of days to look back (default: 30)

            Returns:
                List of historical test executions
            """
            try:
                history = self.metrics.get_test_history(test_name, days)
                return JSONResponse(
                    content={
                        "test_name": test_name,
                        "days": days,
                        "total_runs": len(history),
                        "history": history,
                    }
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics/pass-rate")
        async def get_pass_rate(
            test_name: Optional[str] = Query(None, description="Specific test name"),
            days: int = Query(30, ge=1, le=365, description="Number of days"),
        ):
            """
            Get pass rate trend over time

            Args:
                test_name: Filter by specific test (optional)
                days: Number of days to analyze (default: 30)

            Returns:
                Pass rate trend data with daily breakdowns
            """
            try:
                trend = self.metrics.get_pass_rate_trend(test_name, days)
                return JSONResponse(content=trend)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics/flaky-tests")
        async def get_flaky_tests(
            days: int = Query(30, ge=1, le=365, description="Number of days"),
            threshold: float = Query(
                0.3,
                ge=0.1,
                le=0.5,
                description="Flakiness threshold (0.3 = fails 30%+ but not always)",
            ),
        ):
            """
            Identify flaky tests with inconsistent results

            Args:
                days: Number of days to analyze (default: 30)
                threshold: Flakiness threshold (default: 0.3)

            Returns:
                List of flaky tests sorted by flakiness score
            """
            try:
                flaky = self.metrics.identify_flaky_tests(days, threshold)
                return JSONResponse(
                    content={
                        "days": days,
                        "threshold": threshold,
                        "flaky_tests_count": len(flaky),
                        "flaky_tests": flaky,
                    }
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics/duration")
        async def get_duration(
            test_name: Optional[str] = Query(None, description="Specific test name"),
            days: int = Query(30, ge=1, le=365, description="Number of days"),
        ):
            """
            Get test duration trends

            Args:
                test_name: Filter by specific test (optional)
                days: Number of days to analyze (default: 30)

            Returns:
                Duration statistics and trends
            """
            try:
                duration = self.metrics.get_duration_trend(test_name, days)
                return JSONResponse(content=duration)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics/export", response_class=HTMLResponse)
        async def export_dashboard(
            days: int = Query(30, ge=1, le=365, description="Number of days")
        ):
            """
            Export metrics dashboard as HTML

            Args:
                days: Number of days to include (default: 30)

            Returns:
                HTML dashboard report
            """
            try:
                dashboard = self.metrics.get_summary_dashboard(days=days)
                
                # Generate HTML inline
                output_file = Path("reports") / "temp_dashboard.html"
                self.metrics._export_html_dashboard(dashboard, output_file)
                
                with open(output_file) as f:
                    html_content = f.read()
                
                # Clean up temp file
                output_file.unlink()
                
                return HTMLResponse(content=html_content)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics/test-names")
        async def get_test_names(
            days: int = Query(30, ge=1, le=365, description="Number of days")
        ):
            """
            Get list of all test names in history

            Args:
                days: Number of days to look back (default: 30)

            Returns:
                List of unique test names
            """
            try:
                history = self.metrics.get_test_history(days=days)
                test_names = sorted(set(r["test_name"] for r in history))
                return JSONResponse(
                    content={"days": days, "count": len(test_names), "test_names": test_names}
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))


def create_metrics_api(results_dir: Path = None, s3_bucket: str = None) -> FastAPI:
    """
    Create and configure metrics API

    Args:
        results_dir: Directory with test results
        s3_bucket: S3 bucket for remote data

    Returns:
        Configured FastAPI app

    Example:
        >>> from easybdd.core.metrics_api import create_metrics_api
        >>> app = create_metrics_api(Path("reports"))
        >>> # Run with: uvicorn metrics_api:app --reload
    """
    api = MetricsAPI(results_dir, s3_bucket)
    return api.app


# Default app instance
app = create_metrics_api()


if __name__ == "__main__":
    import uvicorn

    print("Starting Easy BDD Metrics API...")
    print("API docs available at: http://localhost:8001/docs")
    uvicorn.run(app, host="0.0.0.0", port=8001)
