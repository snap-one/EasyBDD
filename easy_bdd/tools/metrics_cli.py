"""
CLI tool for Easy BDD Metrics

Command-line interface for viewing test metrics and analytics.
"""

import sys
from pathlib import Path
from typing import Optional
import argparse

from easy_bdd.core.metrics_engine import TestMetrics, generate_metrics_report


def cmd_dashboard(args):
    """Show dashboard summary"""
    metrics = TestMetrics(Path(args.results_dir))
    dashboard = metrics.get_summary_dashboard(days=args.days)

    print("\n" + "=" * 60)
    print(f"  TEST METRICS DASHBOARD (Last {args.days} days)")
    print("=" * 60 + "\n")

    total_runs = dashboard.get('total_runs', 0)
    passed = dashboard.get('passed', 0)
    failed = dashboard.get('failed', 0)
    pass_rate = dashboard.get('pass_rate', 0)
    avg_duration = dashboard.get('avg_duration', 0)
    unique_tests = dashboard.get('unique_tests', 0)

    print(f"📊 Total Test Runs: {total_runs}")
    
    if total_runs == 0:
        print("\n⚠️  No test data found in the results directory.")
        print(f"   Looking in: {args.results_dir}")
        print("\n💡 Tip: Run some tests first to generate metrics data.")
        print("   Example: make test")
        print("\n" + "=" * 60 + "\n")
        return
    
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    
    emoji = "🎉" if pass_rate >= 90 else "⚠️" if pass_rate >= 70 else "🚨"
    print(f"{emoji} Pass Rate: {pass_rate}%")
    print(f"⏱️  Average Duration: {avg_duration}s")
    print(f"🔬 Unique Tests: {unique_tests}")

    flaky_tests = dashboard.get('flaky_tests', [])
    if flaky_tests:
        print(f"\n⚡ Flaky Tests Detected: {dashboard.get('flaky_tests_count', 0)}")
        print("\nTop 5 Most Flaky Tests:")
        for i, test in enumerate(flaky_tests[:5], 1):
            print(f"  {i}. {test.get('test_name', 'Unknown')}")
            print(f"     Runs: {test.get('total_runs', 0)} | Failed: {test.get('failed', 0)} ({test.get('failure_rate', 0)}%)")

    most_run_tests = dashboard.get('most_run_tests', [])
    if most_run_tests:
        print("\n🏃 Most Frequently Run Tests:")
        for i, test in enumerate(most_run_tests[:5], 1):
            print(f"  {i}. {test.get('test_name', 'Unknown')} - {test.get('run_count', 0)} runs")

    print("\n" + "=" * 60 + "\n")


def cmd_pass_rate(args):
    """Show pass rate trend"""
    metrics = TestMetrics(Path(args.results_dir))
    trend_data = metrics.get_pass_rate_trend(args.test_name, days=args.days)

    print("\n" + "=" * 60)
    print(f"  PASS RATE TREND")
    if args.test_name:
        print(f"  Test: {args.test_name}")
    print("=" * 60 + "\n")

    print(f"Current Pass Rate: {trend_data['current_pass_rate']}%")
    print(f"Trend: {trend_data['trend'].upper()}")
    print(f"Total Runs: {trend_data['total_runs']}")

    if trend_data['data_points']:
        print("\nDaily Breakdown:")
        for point in trend_data['data_points'][-14:]:  # Last 14 days
            bar_length = int(point['pass_rate'] / 5)  # Scale to 20 chars max
            bar = "█" * bar_length
            print(f"  {point['date']}: {bar} {point['pass_rate']}% ({point['passed']}/{point['total']})")

    print("\n" + "=" * 60 + "\n")


def cmd_flaky(args):
    """Show flaky tests"""
    metrics = TestMetrics(Path(args.results_dir))
    flaky_tests = metrics.identify_flaky_tests(days=args.days, threshold=args.threshold)

    print("\n" + "=" * 60)
    print(f"  FLAKY TESTS (Last {args.days} days)")
    print("=" * 60 + "\n")

    if not flaky_tests:
        print("✨ No flaky tests detected! All tests are stable.\n")
        return

    print(f"Found {len(flaky_tests)} flaky tests:\n")

    for i, test in enumerate(flaky_tests, 1):
        print(f"{i}. {test['test_name']}")
        print(f"   Total Runs: {test['total_runs']}")
        print(f"   Passed: {test['passed']} | Failed: {test['failed']}")
        print(f"   Failure Rate: {test['failure_rate']}%")
        print(f"   Flakiness Score: {test['flakiness_score']:.2f} (lower = more flaky)")
        print()

    print("=" * 60 + "\n")


def cmd_duration(args):
    """Show duration trends"""
    metrics = TestMetrics(Path(args.results_dir))
    duration_data = metrics.get_duration_trend(args.test_name, days=args.days)

    print("\n" + "=" * 60)
    print(f"  DURATION TREND")
    if args.test_name:
        print(f"  Test: {args.test_name}")
    print("=" * 60 + "\n")

    print(f"Average Duration: {duration_data['average_duration']}s")
    print(f"Min: {duration_data['min_duration']}s")
    print(f"Max: {duration_data['max_duration']}s")
    print(f"Median: {duration_data['median_duration']}s")
    print(f"Trend: {duration_data['trend'].upper()}")

    if duration_data['data_points']:
        print("\nDaily Average Duration:")
        for point in duration_data['data_points'][-14:]:
            bar_length = int(point['avg_duration'] / 5)  # Scale
            bar = "▓" * min(bar_length, 40)
            print(f"  {point['date']}: {bar} {point['avg_duration']}s")

    print("\n" + "=" * 60 + "\n")


def cmd_export(args):
    """Export metrics report"""
    metrics = TestMetrics(Path(args.results_dir))
    output_file = Path(args.output)

    print(f"\nGenerating {args.format.upper()} report...")
    metrics.export_metrics(output_file, format=args.format)
    print(f"✅ Report saved to: {output_file}\n")


def cmd_history(args):
    """Show test history"""
    metrics = TestMetrics(Path(args.results_dir))
    history = metrics.get_test_history(args.test_name, days=args.days)

    print("\n" + "=" * 60)
    print(f"  TEST EXECUTION HISTORY (Last {args.days} days)")
    if args.test_name:
        print(f"  Test: {args.test_name}")
    print("=" * 60 + "\n")

    if not history:
        print("No test history found.\n")
        return

    print(f"Total executions: {len(history)}\n")

    for record in history[:args.limit]:
        status_emoji = "✅" if record['status'] == "passed" else "❌"
        print(f"{status_emoji} {record['timestamp'][:19]} - {record['test_name']}")
        print(f"   Duration: {record['duration']}s | Steps: {record['steps_passed']} passed, {record['steps_failed']} failed")

    if len(history) > args.limit:
        print(f"\n... and {len(history) - args.limit} more executions")

    print("\n" + "=" * 60 + "\n")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Easy BDD Metrics CLI - Test analytics and insights",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global arguments
    parser.add_argument(
        "--results-dir",
        default="reports",
        help="Directory containing test results (default: reports)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Dashboard command
    dash_parser = subparsers.add_parser("dashboard", help="Show summary dashboard")
    dash_parser.add_argument("--days", type=int, default=7, help="Days to analyze (default: 7)")
    dash_parser.set_defaults(func=cmd_dashboard)

    # Pass rate command
    pass_parser = subparsers.add_parser("pass-rate", help="Show pass rate trend")
    pass_parser.add_argument("--test-name", help="Specific test name (optional)")
    pass_parser.add_argument("--days", type=int, default=30, help="Days to analyze (default: 30)")
    pass_parser.set_defaults(func=cmd_pass_rate)

    # Flaky tests command
    flaky_parser = subparsers.add_parser("flaky", help="Identify flaky tests")
    flaky_parser.add_argument("--days", type=int, default=30, help="Days to analyze (default: 30)")
    flaky_parser.add_argument("--threshold", type=float, default=0.3, help="Flakiness threshold (default: 0.3)")
    flaky_parser.set_defaults(func=cmd_flaky)

    # Duration command
    duration_parser = subparsers.add_parser("duration", help="Show duration trends")
    duration_parser.add_argument("--test-name", help="Specific test name (optional)")
    duration_parser.add_argument("--days", type=int, default=30, help="Days to analyze (default: 30)")
    duration_parser.set_defaults(func=cmd_duration)

    # Export command
    export_parser = subparsers.add_parser("export", help="Export metrics report")
    export_parser.add_argument("--output", required=True, help="Output file path")
    export_parser.add_argument("--format", choices=["json", "csv", "html"], default="html", help="Export format (default: html)")
    export_parser.add_argument("--days", type=int, default=30, help="Days to include (default: 30)")
    export_parser.set_defaults(func=cmd_export)

    # History command
    history_parser = subparsers.add_parser("history", help="Show test execution history")
    history_parser.add_argument("--test-name", help="Specific test name (optional)")
    history_parser.add_argument("--days", type=int, default=30, help="Days to look back (default: 30)")
    history_parser.add_argument("--limit", type=int, default=20, help="Max results to show (default: 20)")
    history_parser.set_defaults(func=cmd_history)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()
