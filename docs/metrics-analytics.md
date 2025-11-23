# Test Metrics & Analytics

The Easy BDD Framework includes comprehensive built-in metrics and analytics capabilities for tracking test execution trends, identifying issues, and gaining insights without requiring external tools like TestRail.

## 📊 Features

### Historical Trending
- Track pass rates over time (daily, weekly, monthly)
- Identify trends: improving, declining, or stable
- View execution patterns and frequencies

### Flaky Test Detection
- Automatically identify tests with inconsistent results
- Calculate flakiness scores
- Prioritize test stability improvements

### Duration Analysis
- Monitor test execution performance
- Detect performance regressions
- Identify slow tests

### Pass Rate Analytics
- Daily breakdown of test results
- Comparison across time periods
- Visual trending indicators

## 🚀 Quick Start

### View Metrics Dashboard

```bash
# Show dashboard for last 7 days
make metrics-dashboard

# Or use CLI directly
python -m easy_bdd.tools.metrics_cli dashboard --days 7
```

Output:
```
============================================================
  TEST METRICS DASHBOARD (Last 7 days)
============================================================

📊 Total Test Runs: 145
✅ Passed: 132
❌ Failed: 13
🎉 Pass Rate: 91.03%
⏱️  Average Duration: 12.5s
🔬 Unique Tests: 23

⚡ Flaky Tests Detected: 2

Top 5 Most Flaky Tests:
  1. API Connection Test
     Runs: 15 | Failed: 5 (33.33%)
  2. Browser Load Test
     Runs: 12 | Failed: 4 (33.33%)
```

### Identify Flaky Tests

```bash
# Find tests that sometimes pass, sometimes fail
make metrics-flaky

# With custom threshold (default: 0.3 = fails 30%+)
python -m easy_bdd.tools.metrics_cli flaky --days 30 --threshold 0.2
```

### View Pass Rate Trends

```bash
# Overall pass rate trend
make metrics-pass-rate

# For specific test
python -m easy_bdd.tools.metrics_cli pass-rate --test-name "Login Test" --days 30
```

Output includes daily breakdown with visual bars:
```
2025-11-16: ████████████████ 80.0% (4/5)
2025-11-17: ████████████████████ 100.0% (6/6)
2025-11-18: ██████████████ 70.0% (7/10)
```

### Export Metrics Report

```bash
# Export as HTML
make metrics-export

# Or specify format
python -m easy_bdd.tools.metrics_cli export --output report.html --format html --days 30
python -m easy_bdd.tools.metrics_cli export --output data.json --format json --days 30
python -m easy_bdd.tools.metrics_cli export --output data.csv --format csv --days 30
```

## 🌐 Metrics REST API

Start a REST API server to query metrics programmatically:

```bash
# Start API server
make metrics-api

# Or directly
python -m easy_bdd.core.metrics_api
```

Server runs on `http://localhost:8001` with interactive docs at `/docs`

### API Endpoints

#### GET /metrics/dashboard
Get comprehensive dashboard summary

```bash
curl "http://localhost:8001/metrics/dashboard?days=7"
```

Response:
```json
{
  "period_days": 7,
  "total_runs": 145,
  "passed": 132,
  "failed": 13,
  "pass_rate": 91.03,
  "avg_duration": 12.5,
  "unique_tests": 23,
  "flaky_tests_count": 2,
  "flaky_tests": [...]
}
```

#### GET /metrics/history
Get test execution history

```bash
# All tests
curl "http://localhost:8001/metrics/history?days=30"

# Specific test
curl "http://localhost:8001/metrics/history?test_name=Login%20Test&days=30"
```

#### GET /metrics/pass-rate
Get pass rate trends with daily breakdown

```bash
curl "http://localhost:8001/metrics/pass-rate?days=30"
```

Response:
```json
{
  "current_pass_rate": 91.5,
  "trend": "improving",
  "total_runs": 450,
  "data_points": [
    {
      "date": "2025-11-15",
      "pass_rate": 85.0,
      "passed": 17,
      "failed": 3,
      "total": 20
    },
    ...
  ]
}
```

#### GET /metrics/flaky-tests
Identify flaky tests

```bash
curl "http://localhost:8001/metrics/flaky-tests?days=30&threshold=0.3"
```

#### GET /metrics/duration
Get duration analytics

```bash
# All tests
curl "http://localhost:8001/metrics/duration?days=30"

# Specific test
curl "http://localhost:8001/metrics/duration?test_name=API%20Test&days=30"
```

#### GET /metrics/export
Export HTML dashboard report

```bash
curl "http://localhost:8001/metrics/export?days=30" > dashboard.html
```

#### GET /metrics/test-names
Get list of all test names

```bash
curl "http://localhost:8001/metrics/test-names?days=30"
```

## 📁 Data Sources

The metrics engine automatically discovers test results from:

### Local JSON Files
- Default location: `reports/` directory
- Scans recursively for `*.json` files
- Extracts timestamp from data or file modification time

### Required Fields in JSON
```json
{
  "test_name": "Login Test",
  "status": "passed",  // or "failed", "skipped"
  "duration": 12.5,
  "steps_passed": 8,
  "steps_failed": 0,
  "timestamp": "2025-11-23T10:30:00"  // ISO format
}
```

### S3 Data Lake (Future)
Configure S3 bucket for centralized storage:
```yaml
# config/framework.yaml
metrics:
  s3_bucket: "my-test-results"
  s3_prefix: "easy-bdd/"
```

## 🔍 Advanced Usage

### Python API

Use metrics engine directly in your scripts:

```python
from pathlib import Path
from easy_bdd.core.metrics_engine import TestMetrics

# Initialize
metrics = TestMetrics(results_dir=Path("reports"))

# Get dashboard
dashboard = metrics.get_summary_dashboard(days=7)
print(f"Pass rate: {dashboard['pass_rate']}%")

# Identify flaky tests
flaky = metrics.identify_flaky_tests(days=30, threshold=0.3)
for test in flaky:
    print(f"{test['test_name']}: {test['failure_rate']}% failure rate")

# Get pass rate trend
trend = metrics.get_pass_rate_trend(test_name="Login Test", days=30)
print(f"Current pass rate: {trend['current_pass_rate']}%")
print(f"Trend: {trend['trend']}")

# Get duration trends
duration = metrics.get_duration_trend(days=30)
print(f"Average: {duration['average_duration']}s")
print(f"Trend: {duration['trend']}")

# Export report
metrics.export_metrics(
    output_file=Path("report.html"),
    format="html"
)
```

### Custom Integrations

Integrate metrics into your CI/CD pipeline:

```yaml
# GitHub Actions example
- name: Generate Metrics Report
  run: |
    python -m easy_bdd.tools.metrics_cli export \
      --output metrics.html \
      --format html \
      --days 30
    
- name: Check Pass Rate
  run: |
    python -c "
    from easy_bdd.core.metrics_engine import TestMetrics
    metrics = TestMetrics()
    dashboard = metrics.get_summary_dashboard(days=7)
    if dashboard['pass_rate'] < 90:
        print(f'Warning: Pass rate is {dashboard[\"pass_rate\"]}%')
        exit(1)
    "
```

## 📈 Understanding Metrics

### Pass Rate Trends
- **Improving**: Recent pass rate > historical average by 5%+
- **Declining**: Recent pass rate < historical average by 5%+
- **Stable**: Pass rate within ±5% of historical average

### Flakiness Score
- **0.0 - 0.2**: Highly flaky (fails ~50% of time)
- **0.2 - 0.5**: Moderately flaky
- **0.5 - 0.8**: Somewhat flaky
- **0.8 - 1.0**: Mostly deterministic

### Duration Trends
- **Faster**: Recent average < 80% of historical average
- **Slower**: Recent average > 120% of historical average
- **Stable**: Within ±20% of historical average

## 🎯 Best Practices

### 1. Regular Monitoring
- Check dashboard daily: `make metrics-dashboard`
- Review flaky tests weekly: `make metrics-flaky`
- Export monthly reports: `make metrics-export`

### 2. Flaky Test Management
- Prioritize tests with flakiness score < 0.5
- Investigate root causes (timing, dependencies, state)
- Add retry logic or improve test stability
- Document known issues

### 3. Performance Tracking
- Monitor duration trends weekly
- Investigate sudden increases (>20%)
- Optimize slow tests (>60s)
- Consider parallel execution

### 4. Data Retention
- Keep last 30 days locally for quick access
- Archive older data to S3 for long-term trends
- Export monthly summaries for reporting

### 5. CI/CD Integration
- Generate metrics after each test run
- Fail builds if pass rate drops below threshold
- Post metrics to team chat/dashboard
- Track trends across branches/environments

## 🔧 Configuration

### Metrics Settings
```yaml
# config/framework.yaml
metrics:
  enabled: true
  results_dir: "reports"
  s3_bucket: null  # Optional
  
  # Thresholds
  flaky_threshold: 0.3  # 30% failure rate
  min_runs_for_flaky: 3  # Minimum runs to detect flaky
  
  # Trends
  trend_threshold: 5.0  # % change for trend detection
  recent_days: 7  # Days considered "recent"
```

## 📚 Examples

### Example 1: Daily Health Check Script
```bash
#!/bin/bash
# daily_health_check.sh

echo "Generating daily metrics..."
python -m easy_bdd.tools.metrics_cli dashboard --days 7 > metrics_daily.txt

# Check for issues
if grep -q "🚨" metrics_daily.txt; then
    echo "Warning: Pass rate below 70%"
    # Send alert
fi

if grep -q "Flaky Tests Detected:" metrics_daily.txt; then
    echo "Flaky tests found, generating detailed report..."
    python -m easy_bdd.tools.metrics_cli flaky --days 30 > flaky_report.txt
fi
```

### Example 2: Weekly Report Email
```python
# weekly_report.py
from easy_bdd.core.metrics_engine import TestMetrics
from datetime import datetime

metrics = TestMetrics()
dashboard = metrics.get_summary_dashboard(days=7)

email_body = f"""
Weekly Test Metrics Report - {datetime.now().strftime('%Y-%m-%d')}

Summary:
- Total Runs: {dashboard['total_runs']}
- Pass Rate: {dashboard['pass_rate']}%
- Average Duration: {dashboard['avg_duration']}s
- Flaky Tests: {dashboard['flaky_tests_count']}

See attached HTML report for details.
"""

# Export HTML
metrics.export_metrics("weekly_report.html", format="html")

# Send email (use your email library)
# send_email(to="team@company.com", subject="Weekly Metrics", body=email_body, attachment="weekly_report.html")
```

### Example 3: Slack Integration
```python
# slack_metrics.py
import requests
from easy_bdd.core.metrics_engine import TestMetrics

metrics = TestMetrics()
dashboard = metrics.get_summary_dashboard(days=1)

# Determine emoji based on pass rate
if dashboard['pass_rate'] >= 95:
    emoji = ":white_check_mark:"
elif dashboard['pass_rate'] >= 85:
    emoji = ":warning:"
else:
    emoji = ":x:"

message = {
    "text": f"{emoji} Daily Test Results",
    "blocks": [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Daily Test Results - {datetime.now().strftime('%Y-%m-%d')}*\n"
                        f"Pass Rate: *{dashboard['pass_rate']}%*\n"
                        f"Total Runs: {dashboard['total_runs']}\n"
                        f"Flaky Tests: {dashboard['flaky_tests_count']}"
            }
        }
    ]
}

# Post to Slack
webhook_url = "YOUR_SLACK_WEBHOOK_URL"
requests.post(webhook_url, json=message)
```

## 🆚 vs TestRail

Why use built-in metrics instead of TestRail?

| Feature | Easy BDD Metrics | TestRail |
|---------|------------------|----------|
| **Cost** | Free, built-in | $$$$ Paid |
| **Setup** | Zero config | Requires setup/config |
| **Data Control** | Local or S3 | Cloud-hosted |
| **Customization** | Full Python API | Limited |
| **Integration** | Direct framework access | API calls |
| **Speed** | Instant queries | Network dependent |
| **Offline** | Works offline | Requires internet |

**When to use TestRail**: Large enterprise with multiple teams, tools, and existing TestRail infrastructure.

**When to use built-in metrics**: Individual teams, projects, or organizations wanting simple, powerful, free analytics.

## 🔜 Future Enhancements

Planned features:
- S3 data lake integration for centralized storage
- Machine learning for failure prediction
- Anomaly detection for unusual patterns
- Advanced visualizations with charts
- Comparative analysis across branches/environments
- Integration with GitHub Actions insights
- Custom metric plugins

## 💡 Tips

1. **Start small**: Begin with dashboard and flaky test detection
2. **Automate**: Add metrics to CI/CD pipelines
3. **Share**: Export HTML reports for stakeholders
4. **Act**: Use insights to improve test quality
5. **Iterate**: Regularly review and refine thresholds

## 📖 Related Documentation

- [Data-Driven Testing](data-driven.md)
- [Retry Logic](../WEEK4_FEATURES.md#feature-1-retry-logic)
- [AWS S3 Integration](aws-s3-integration.md)
- [Datalake Logger](datalake-logger.md)
