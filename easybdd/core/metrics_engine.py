"""
Metrics Engine for Easy BDD Framework

Provides test execution analytics, historical trending, and insights.
Works with S3 data lake and local JSON reports.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import statistics


class TestMetrics:
    """Comprehensive test execution metrics"""

    def __init__(self, results_dir: Path = None, s3_bucket: str = None):
        """
        Initialize metrics engine

        Args:
            results_dir: Local directory with JSON test results
            s3_bucket: S3 bucket name for remote data lake
        """
        self.results_dir = results_dir or Path("reports")
        self.s3_bucket = s3_bucket
        self._cache = {}

    def get_test_history(
        self, test_name: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get historical test execution data

        Args:
            test_name: Specific test name or None for all tests
            days: Number of days to look back

        Returns:
            List of test execution records
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        history = []

        # Load from local JSON files
        if self.results_dir.exists():
            for json_file in self.results_dir.glob("**/*.json"):
                try:
                    with open(json_file) as f:
                        data = json.load(f)

                    # Parse timestamp from data or filename
                    timestamp = self._extract_timestamp(data, json_file)

                    if timestamp and timestamp >= cutoff_date:
                        # Handle aggregate test results format (from HTML reporter)
                        if "tests" in data and isinstance(data["tests"], list):
                            for test in data["tests"]:
                                test_file_name = data.get("test_file", "unknown")
                                if test_name is None or test.get("name") == test_name or test_file_name == test_name:
                                    # Parse status - normalize to lowercase
                                    status = test.get("status", "unknown").lower()
                                    if status == "failed":
                                        status = "failed"
                                    elif status in ["passed", "pass"]:
                                        status = "passed"
                                    
                                    # Get duration - handle both duration and execution_time fields
                                    duration = test.get("execution_time", test.get("duration", 0))
                                    
                                    # Count steps
                                    step_logs = test.get("step_logs", [])
                                    steps_passed = sum(1 for s in step_logs if s.get("status") == "passed")
                                    steps_failed = len(step_logs) - steps_passed
                                    
                                    history.append(
                                        {
                                            "timestamp": timestamp.isoformat(),
                                            "test_name": test.get("name", test_file_name),
                                            "status": status,
                                            "duration": duration,
                                            "steps_passed": steps_passed,
                                            "steps_failed": steps_failed,
                                            "file": str(json_file),
                                        }
                                    )
                        # Handle individual test record format
                        elif test_name is None or data.get("test_name") == test_name:
                            history.append(
                                {
                                    "timestamp": timestamp.isoformat(),
                                    "test_name": data.get("test_name", "unknown"),
                                    "status": data.get("status", "unknown"),
                                    "duration": data.get("duration", 0),
                                    "steps_passed": data.get("steps_passed", 0),
                                    "steps_failed": data.get("steps_failed", 0),
                                    "file": str(json_file),
                                }
                            )
                except (json.JSONDecodeError, Exception):
                    # Skip invalid files
                    continue

        # Sort by timestamp descending
        history.sort(key=lambda x: x["timestamp"], reverse=True)
        return history

    def get_pass_rate_trend(
        self, test_name: Optional[str] = None, days: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate pass rate trend over time

        Args:
            test_name: Specific test or None for all
            days: Days to analyze

        Returns:
            Dictionary with trend data
        """
        history = self.get_test_history(test_name, days)

        if not history:
            return {
                "current_pass_rate": 0,
                "trend": "no_data",
                "data_points": [],
                "total_runs": 0,
            }

        # Group by day
        daily_stats = defaultdict(lambda: {"passed": 0, "failed": 0, "total": 0})

        for record in history:
            date = record["timestamp"][:10]  # YYYY-MM-DD
            status = record["status"]

            daily_stats[date]["total"] += 1
            if status == "passed":
                daily_stats[date]["passed"] += 1
            else:
                daily_stats[date]["failed"] += 1

        # Calculate pass rates
        data_points = []
        for date in sorted(daily_stats.keys()):
            stats = daily_stats[date]
            pass_rate = (
                (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )
            data_points.append(
                {
                    "date": date,
                    "pass_rate": round(pass_rate, 2),
                    "passed": stats["passed"],
                    "failed": stats["failed"],
                    "total": stats["total"],
                }
            )

        # Determine trend
        if len(data_points) >= 2:
            recent_avg = statistics.mean(
                [p["pass_rate"] for p in data_points[-7:]]  # Last 7 days
            )
            older_avg = statistics.mean(
                [p["pass_rate"] for p in data_points[:-7] or data_points]
            )
            if recent_avg > older_avg + 5:
                trend = "improving"
            elif recent_avg < older_avg - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        # Current pass rate (last 7 days)
        recent_runs = [p for p in data_points[-7:]]
        if recent_runs:
            current_pass_rate = statistics.mean([p["pass_rate"] for p in recent_runs])
        else:
            current_pass_rate = 0

        return {
            "current_pass_rate": round(current_pass_rate, 2),
            "trend": trend,
            "data_points": data_points,
            "total_runs": sum(p["total"] for p in data_points),
        }

    def identify_flaky_tests(self, days: int = 30, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Identify tests with inconsistent results (flaky tests)

        Args:
            days: Days to analyze
            threshold: Flakiness threshold (0.3 = fails 30%+ of the time but not always)

        Returns:
            List of flaky tests with details
        """
        history = self.get_test_history(days=days)

        # Group by test name
        test_stats = defaultdict(lambda: {"passed": 0, "failed": 0, "total": 0})

        for record in history:
            test_name = record["test_name"]
            status = record["status"]

            test_stats[test_name]["total"] += 1
            if status == "passed":
                test_stats[test_name]["passed"] += 1
            else:
                test_stats[test_name]["failed"] += 1

        # Identify flaky tests (sometimes pass, sometimes fail)
        flaky_tests = []
        for test_name, stats in test_stats.items():
            if stats["total"] < 3:
                continue  # Need multiple runs to determine flakiness

            failure_rate = stats["failed"] / stats["total"]

            # Flaky if it fails between threshold and (1-threshold)
            if threshold < failure_rate < (1 - threshold):
                flaky_tests.append(
                    {
                        "test_name": test_name,
                        "total_runs": stats["total"],
                        "passed": stats["passed"],
                        "failed": stats["failed"],
                        "failure_rate": round(failure_rate * 100, 2),
                        "flakiness_score": round(
                            abs(0.5 - failure_rate) * 2, 2
                        ),  # 0 = most flaky, 1 = deterministic
                    }
                )

        # Sort by flakiness (most flaky first)
        flaky_tests.sort(key=lambda x: x["flakiness_score"])

        return flaky_tests

    def get_duration_trend(
        self, test_name: Optional[str] = None, days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze test execution duration over time

        Args:
            test_name: Specific test or None for all
            days: Days to analyze

        Returns:
            Duration trend data
        """
        history = self.get_test_history(test_name, days)

        if not history:
            return {
                "average_duration": 0,
                "min_duration": 0,
                "max_duration": 0,
                "trend": "no_data",
                "data_points": [],
            }

        durations = [r["duration"] for r in history if r["duration"] > 0]

        if not durations:
            return {
                "average_duration": 0,
                "min_duration": 0,
                "max_duration": 0,
                "trend": "no_data",
                "data_points": [],
            }

        # Group by day
        daily_durations = defaultdict(list)
        for record in history:
            if record["duration"] > 0:
                date = record["timestamp"][:10]
                daily_durations[date].append(record["duration"])

        # Calculate daily averages
        data_points = []
        for date in sorted(daily_durations.keys()):
            avg_duration = statistics.mean(daily_durations[date])
            data_points.append({"date": date, "avg_duration": round(avg_duration, 2)})

        # Determine trend
        if len(data_points) >= 2:
            recent_avg = statistics.mean([p["avg_duration"] for p in data_points[-7:]])
            older_avg = statistics.mean(
                [p["avg_duration"] for p in data_points[:-7] or data_points]
            )
            if recent_avg > older_avg * 1.2:
                trend = "slower"
            elif recent_avg < older_avg * 0.8:
                trend = "faster"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "average_duration": round(statistics.mean(durations), 2),
            "min_duration": round(min(durations), 2),
            "max_duration": round(max(durations), 2),
            "median_duration": round(statistics.median(durations), 2),
            "trend": trend,
            "data_points": data_points,
        }

    def get_summary_dashboard(self, days: int = 7) -> Dict[str, Any]:
        """
        Get comprehensive dashboard summary

        Args:
            days: Days to include in summary

        Returns:
            Dashboard data
        """
        history = self.get_test_history(days=days)

        if not history:
            return {
                "period_days": days,
                "total_runs": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": 0,
                "avg_duration": 0,
                "unique_tests": 0,
                "flaky_tests_count": 0,
                "flaky_tests": [],
                "recent_failures": [],
                "most_run_tests": [],
            }

        # Overall stats
        total_runs = len(history)
        passed = sum(1 for r in history if r["status"] == "passed")
        pass_rate = (passed / total_runs * 100) if total_runs > 0 else 0

        durations = [r["duration"] for r in history if r["duration"] > 0]
        avg_duration = statistics.mean(durations) if durations else 0

        unique_tests = len(set(r["test_name"] for r in history))

        # Get flaky tests
        flaky_tests = self.identify_flaky_tests(days=days)

        # Recent failures (last 10)
        recent_failures = [r for r in history if r["status"] != "passed"][:10]

        # Test frequency
        test_counts = defaultdict(int)
        for record in history:
            test_counts[record["test_name"]] += 1

        most_run_tests = sorted(
            test_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "period_days": days,
            "total_runs": total_runs,
            "passed": passed,
            "failed": total_runs - passed,
            "pass_rate": round(pass_rate, 2),
            "avg_duration": round(avg_duration, 2),
            "unique_tests": unique_tests,
            "flaky_tests_count": len(flaky_tests),
            "flaky_tests": flaky_tests[:5],  # Top 5 most flaky
            "recent_failures": recent_failures,
            "most_run_tests": [
                {"test_name": name, "run_count": count}
                for name, count in most_run_tests
            ],
        }

    def export_metrics(
        self, output_file: Path, format: str = "json"
    ) -> None:
        """
        Export metrics to file

        Args:
            output_file: Output file path
            format: Export format (json, csv, html)
        """
        dashboard = self.get_summary_dashboard(days=30)

        if format == "json":
            with open(output_file, "w") as f:
                json.dump(dashboard, f, indent=2)
        elif format == "csv":
            import csv
            with open(output_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])
                for key, value in dashboard.items():
                    if not isinstance(value, (list, dict)):
                        writer.writerow([key, value])
        elif format == "html":
            self._export_html_dashboard(dashboard, output_file)

    def _export_html_dashboard(
        self, dashboard: Dict[str, Any], output_file: Path
    ) -> None:
        """Generate HTML dashboard report"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Test Metrics Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .card {{ background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .metric {{ display: inline-block; margin: 10px 20px; }}
        .metric-value {{ font-size: 32px; font-weight: bold; color: #2563eb; }}
        .metric-label {{ font-size: 14px; color: #666; }}
        .pass-rate {{ color: {'#10b981' if dashboard['pass_rate'] >= 90 else '#ef4444'}; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f9fafb; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Test Metrics Dashboard</h1>
        <p>Period: Last {dashboard['period_days']} days</p>
        
        <div class="card">
            <h2>Overview</h2>
            <div class="metric">
                <div class="metric-value">{dashboard['total_runs']}</div>
                <div class="metric-label">Total Runs</div>
            </div>
            <div class="metric">
                <div class="metric-value pass-rate">{dashboard['pass_rate']}%</div>
                <div class="metric-label">Pass Rate</div>
            </div>
            <div class="metric">
                <div class="metric-value">{dashboard['avg_duration']}s</div>
                <div class="metric-label">Avg Duration</div>
            </div>
            <div class="metric">
                <div class="metric-value">{dashboard['unique_tests']}</div>
                <div class="metric-label">Unique Tests</div>
            </div>
        </div>
        
        <div class="card">
            <h2>Flaky Tests ({dashboard['flaky_tests_count']} detected)</h2>
            <table>
                <tr>
                    <th>Test Name</th>
                    <th>Runs</th>
                    <th>Passed</th>
                    <th>Failed</th>
                    <th>Failure Rate</th>
                </tr>
                {''.join(f'<tr><td>{t["test_name"]}</td><td>{t["total_runs"]}</td><td>{t["passed"]}</td><td>{t["failed"]}</td><td>{t["failure_rate"]}%</td></tr>' for t in dashboard['flaky_tests'])}
            </table>
        </div>
        
        <div class="card">
            <h2>Most Run Tests</h2>
            <table>
                <tr>
                    <th>Test Name</th>
                    <th>Run Count</th>
                </tr>
                {''.join(f'<tr><td>{t["test_name"]}</td><td>{t["run_count"]}</td></tr>' for t in dashboard['most_run_tests'])}
            </table>
        </div>
    </div>
</body>
</html>
"""
        with open(output_file, "w") as f:
            f.write(html)

    def _extract_timestamp(
        self, data: Dict[str, Any], file_path: Path
    ) -> Optional[datetime]:
        """Extract timestamp from test data or filename"""
        # Try data fields
        for field in ["timestamp", "start_time", "execution_time", "date"]:
            if field in data:
                try:
                    return datetime.fromisoformat(data[field].replace("Z", "+00:00"))
                except:
                    pass

        # Try file modification time
        try:
            return datetime.fromtimestamp(file_path.stat().st_mtime)
        except:
            pass

        return None


def generate_metrics_report(
    results_dir: Path = None, output_dir: Path = None, days: int = 30
) -> Path:
    """
    Convenience function to generate metrics report

    Args:
        results_dir: Directory with test results
        output_dir: Output directory for report
        days: Days to include

    Returns:
        Path to generated report
    """
    metrics = TestMetrics(results_dir)
    output_dir = output_dir or Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"metrics_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    metrics.export_metrics(output_file, format="html")

    return output_file
