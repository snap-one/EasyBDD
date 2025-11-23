"""
HTML and PDF Report Generation Module for Easy BDD Framework
"""
import json
from datetime import datetime
from jinja2 import Template
from fastapi import HTTPException, Response
from fastapi.responses import RedirectResponse

# HTML Template for Professional Test Reports
REPORT_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Easy BDD Test Report - {{ timestamp }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6; color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; padding: 20px;
        }
        
        .report-container {
            max-width: 1200px; margin: 0 auto; background: white;
            border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .report-header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white; padding: 40px; text-align: center; position: relative;
        }
        
        .report-header h1 {
            font-size: 2.5em; margin-bottom: 10px; position: relative; z-index: 1;
        }
        
        .report-header .subtitle {
            font-size: 1.2em; opacity: 0.9; position: relative; z-index: 1;
        }
        
        .report-meta {
            background: #f8f9fa; padding: 30px; border-bottom: 3px solid #e9ecef;
        }
        
        .meta-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px; margin-bottom: 20px;
        }
        
        .meta-item {
            background: white; padding: 20px; border-radius: 10px;
            border-left: 4px solid #007bff; box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        .meta-item h3 {
            color: #007bff; font-size: 0.9em; text-transform: uppercase;
            letter-spacing: 1px; margin-bottom: 8px;
        }
        
        .meta-item p { font-size: 1.2em; font-weight: 600; color: #2c3e50; }
        
        .summary-stats {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;
        }
        
        .stat-card {
            text-align: center; padding: 20px; background: white;
            border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        .stat-card.success { border-left: 4px solid #28a745; }
        .stat-card.failed { border-left: 4px solid #dc3545; }
        .stat-card.total { border-left: 4px solid #6f42c1; }
        .stat-card.duration { border-left: 4px solid #fd7e14; }
        
        .stat-number { font-size: 2.5em; font-weight: bold; margin-bottom: 5px; }
        .stat-card.success .stat-number { color: #28a745; }
        .stat-card.failed .stat-number { color: #dc3545; }
        .stat-card.total .stat-number { color: #6f42c1; }
        .stat-card.duration .stat-number { color: #fd7e14; }
        
        .stat-label {
            color: #6c757d; text-transform: uppercase; font-size: 0.8em; letter-spacing: 1px;
        }
        
        .results-section { padding: 40px; }
        
        .section-title {
            font-size: 1.8em; color: #2c3e50; margin-bottom: 20px;
            padding-bottom: 10px; border-bottom: 2px solid #e9ecef;
            display: flex; align-items: center;
        }
        
        .section-title::before { content: '📊'; margin-right: 10px; font-size: 1.2em; }
        
        .test-result {
            background: white; border: 1px solid #e9ecef; border-radius: 10px;
            margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); overflow: hidden;
        }
        
        .test-header {
            padding: 20px; background: #f8f9fa; border-bottom: 1px solid #e9ecef;
            display: flex; justify-content: space-between; align-items: center;
        }
        
        .test-title { font-size: 1.3em; font-weight: 600; color: #2c3e50; margin-bottom: 5px; }
        
        .test-status {
            display: inline-block; padding: 5px 15px; border-radius: 20px;
            font-size: 0.8em; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;
        }
        
        .test-status.passed {
            background: #d4edda; color: #155724; border: 1px solid #c3e6cb;
        }
        
        .test-status.failed {
            background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;
        }
        
        .test-details { padding: 20px; }
        
        .test-info {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px; margin-bottom: 20px;
        }
        
        .info-item {
            background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 3px solid #007bff;
        }
        
        .info-label {
            font-size: 0.8em; color: #6c757d; text-transform: uppercase;
            letter-spacing: 1px; margin-bottom: 5px;
        }
        
        .info-value { font-weight: 600; color: #2c3e50; }
        
        .console-section { margin-top: 40px; background: #f8f9fa; padding: 40px; }
        .console-section .section-title::before { content: '🖥️'; }
        
        .console-log {
            background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 10px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 0.9em; line-height: 1.4; max-height: 500px; overflow-y: auto;
            white-space: pre-wrap; border: 1px solid #333;
        }
        
        .log-entry { margin-bottom: 8px; display: flex; align-items: flex-start; }
        .log-timestamp { color: #808080; margin-right: 15px; min-width: 90px; font-size: 0.8em; }
        .log-level { margin-right: 10px; min-width: 60px; font-weight: bold; }
        .log-level.INFO { color: #3794ff; }
        .log-level.SUCCESS { color: #00d26a; }
        .log-level.ERROR { color: #ff4757; }
        .log-level.WARNING { color: #ffa502; }
        .log-message { flex: 1; }
        
        .api-response {
            background: #2d3748; border: 1px solid #4a5568; border-radius: 8px;
            padding: 15px; margin: 10px 0 10px 105px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        }
        
        .api-response-header {
            color: #81c784; font-weight: bold; margin-bottom: 10px;
            padding-bottom: 5px; border-bottom: 1px solid #4a5568;
        }
        
        .api-response-body { color: #e8f5e8; white-space: pre-wrap; font-size: 0.85em; }
        
        .footer {
            background: #2c3e50; color: white; text-align: center; padding: 20px; font-size: 0.9em;
        }
        
        @media print {
            body { background: white; padding: 0; }
            .report-container { box-shadow: none; border-radius: 0; }
            .console-log { max-height: none; overflow: visible; }
        }
    </style>
</head>
<body>
    <div class="report-container">
        <div class="report-header">
            <h1>Easy BDD Test Report</h1>
            <div class="subtitle">Comprehensive Test Execution Summary</div>
        </div>
        
        <div class="report-meta">
            <div class="meta-grid">
                <div class="meta-item">
                    <h3>Generated</h3>
                    <p>{{ timestamp }}</p>
                </div>
                <div class="meta-item">
                    <h3>Framework</h3>
                    <p>Easy BDD v1.0</p>
                </div>
                <div class="meta-item">
                    <h3>Environment</h3>
                    <p>{{ environment | default('Development') }}</p>
                </div>
                <div class="meta-item">
                    <h3>Total Duration</h3>
                    <p>{{ total_duration }}s</p>
                </div>
            </div>
            
            <div class="summary-stats">
                <div class="stat-card total">
                    <div class="stat-number">{{ total_tests }}</div>
                    <div class="stat-label">Total Tests</div>
                </div>
                <div class="stat-card success">
                    <div class="stat-number">{{ passed_tests }}</div>
                    <div class="stat-label">Passed</div>
                </div>
                <div class="stat-card failed">
                    <div class="stat-number">{{ failed_tests }}</div>
                    <div class="stat-label">Failed</div>
                </div>
                <div class="stat-card duration">
                    <div class="stat-number">{{ success_rate }}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
            </div>
        </div>
        
        <div class="results-section">
            <h2 class="section-title">Test Results</h2>
            
            {% for test in tests %}
            <div class="test-result">
                <div class="test-header">
                    <div>
                        <div class="test-title">{{ test.test_name }}</div>
                        <div class="test-status {{ 'passed' if test.success else 'failed' }}">
                            {{ 'PASSED' if test.success else 'FAILED' }}
                        </div>
                    </div>
                </div>
                
                <div class="test-details">
                    <div class="test-info">
                        <div class="info-item">
                            <div class="info-label">Test Type</div>
                            <div class="info-value">{{ test.test_type | upper }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Duration</div>
                            <div class="info-value">{{ test.duration }}s</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Steps</div>
                            <div class="info-value">{{ test.steps_passed }}/{{ test.steps_total }}</div>
                        </div>
                        {% if test.api_summary %}
                        <div class="info-item">
                            <div class="info-label">API Requests</div>
                            <div class="info-value">{{ test.api_summary.successful_requests }}/{{ test.api_summary.total_requests }}</div>
                        </div>
                        {% endif %}
                    </div>
                    
                    <div class="info-item" style="grid-column: 1 / -1;">
                        <div class="info-label">Output</div>
                        <div class="info-value">{{ test.output }}</div>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="console-section">
            <h2 class="section-title">Console Logs</h2>
            
            {% for test in tests %}
            <div class="test-result">
                <div class="test-header">
                    <div class="test-title">{{ test.test_name }} - Console Output</div>
                </div>
                
                <div class="console-log">
                    {% for log in test.logs %}
                    <div class="log-entry">
                        <span class="log-timestamp">{{ log.timestamp.split('T')[1].split('.')[0] if log.timestamp else '' }}</span>
                        <span class="log-level {{ log.level }}">{{ log.level }}</span>
                        <span class="log-message">{{ log.message }}</span>
                    </div>
                    
                    {% if log.details and log.details.response_body %}
                    <div class="api-response">
                        <div class="api-response-header">
                            📡 API Response ({{ log.details.method }} {{ log.details.url }})
                        </div>
                        <div class="api-response-body">{{ log.details.response_body | tojson(indent=2) }}</div>
                    </div>
                    {% endif %}
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="footer">
            Generated by Easy BDD Framework | {{ timestamp }}
        </div>
    </div>
</body>
</html>
"""


def generate_html_report(test_results_dict):
    """Generate HTML report from test results"""
    results = list(test_results_dict.values())
    
    if not results:
        raise HTTPException(status_code=404, detail="No test results found")
    
    # Calculate summary statistics
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.get('success', False))
    failed_tests = total_tests - passed_tests
    success_rate = round((passed_tests / total_tests) * 100, 1) if total_tests > 0 else 0
    total_duration = round(sum(r.get('duration', 0) for r in results), 2)
    
    # Prepare template context
    context = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': failed_tests,
        'success_rate': success_rate,
        'total_duration': total_duration,
        'environment': 'Development',
        'tests': results
    }
    
    # Render HTML template
    template = Template(REPORT_HTML_TEMPLATE)
    html_content = template.render(**context)
    
    # Return as HTML response with download headers
    filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    
    return Response(
        content=html_content,
        media_type='text/html',
        headers=headers
    )


def generate_pdf_report(test_results_dict):
    """Generate PDF report (redirects to HTML for now)"""
    return RedirectResponse(url="/api/tests/results/report/html")