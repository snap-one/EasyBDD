"""
HTML Report Generator for Easy BDD Tests
"""

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import json


class HTMLReporter:
    """Generate beautiful HTML reports for test execution"""
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_report(self, test_details: List[Dict[str, Any]], 
                       total_tests: int, passed: int, failed: int, 
                       execution_time: float,
                       test_file_name: str = "test") -> Path:
        """Generate HTML report from test results"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Easy BDD Test Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            color: #2d3748;
            margin-bottom: 10px;
            font-size: 32px;
        }}
        
        .header .subtitle {{
            color: #718096;
            font-size: 14px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            text-align: center;
            transition: transform 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-card .label {{
            color: #718096;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }}
        
        .stat-card .value {{
            font-size: 36px;
            font-weight: bold;
            color: #2d3748;
        }}
        
        .stat-card.success .value {{
            color: #48bb78;
        }}
        
        .stat-card.failure .value {{
            color: #f56565;
        }}
        
        .stat-card.rate .value {{
            color: #667eea;
        }}
        
        .progress-bar {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            margin-bottom: 30px;
        }}
        
        .progress-bar h3 {{
            color: #2d3748;
            margin-bottom: 15px;
        }}
        
        .progress-track {{
            background: #e2e8f0;
            height: 30px;
            border-radius: 15px;
            overflow: hidden;
            position: relative;
        }}
        
        .progress-fill {{
            background: linear-gradient(90deg, #48bb78 0%, #38a169 100%);
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 14px;
            transition: width 1s ease;
        }}
        
        .tests-section {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }}
        
        .tests-section h2 {{
            color: #2d3748;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #e2e8f0;
        }}
        
        .test-item {{
            padding: 20px;
            border-left: 4px solid #e2e8f0;
            margin-bottom: 15px;
            background: #f7fafc;
            border-radius: 8px;
            transition: all 0.3s ease;
        }}
        
        .test-item:hover {{
            background: #edf2f7;
            transform: translateX(5px);
        }}
        
        .test-item.passed {{
            border-left-color: #48bb78;
        }}
        
        .test-item.failed {{
            border-left-color: #f56565;
        }}
        
        .test-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        
        .test-name {{
            font-size: 18px;
            font-weight: 600;
            color: #2d3748;
        }}
        
        .test-status {{
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        
        .test-status.passed {{
            background: #c6f6d5;
            color: #22543d;
        }}
        
        .test-status.failed {{
            background: #fed7d7;
            color: #742a2a;
        }}
        
        .test-description {{
            color: #718096;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        
        .test-meta {{
            display: flex;
            gap: 20px;
            font-size: 13px;
            color: #a0aec0;
        }}
        
        .test-meta span {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        
        .tag {{
            display: inline-block;
            padding: 4px 10px;
            background: #edf2f7;
            color: #4a5568;
            border-radius: 12px;
            font-size: 12px;
            margin-right: 5px;
        }}
        
        .error-message {{
            margin-top: 15px;
            padding: 15px;
            background: #fff5f5;
            border-left: 3px solid #f56565;
            border-radius: 5px;
            color: #742a2a;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            white-space: pre-wrap;
        }}
        
        .icon {{
            display: inline-block;
            width: 16px;
            height: 16px;
        }}
        
        @keyframes fadeIn {{
            from {{
                opacity: 0;
                transform: translateY(20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .test-item {{
            animation: fadeIn 0.5s ease;
        }}
        
        .footer {{
            text-align: center;
            color: white;
            margin-top: 30px;
            padding: 20px;
            font-size: 14px;
        }}
        
        .log-section {{
            margin-top: 15px;
        }}
        
        .log-toggle {{
            background: #4299e1;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: background 0.3s ease;
        }}
        
        .log-toggle:hover {{
            background: #3182ce;
        }}
        
        .log-content {{
            display: none;
            margin-top: 10px;
            padding: 15px;
            background: #1a202c;
            color: #e2e8f0;
            border-radius: 8px;
            font-family: 'Courier New', Monaco, monospace;
            font-size: 12px;
            max-height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
            line-height: 1.6;
        }}
        
        .log-content.show {{
            display: block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 Easy BDD Test Report</h1>
            <div class="subtitle">Generated on {timestamp}</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Tests</div>
                <div class="value">{total_tests}</div>
            </div>
            <div class="stat-card success">
                <div class="label">Passed</div>
                <div class="value">{passed}</div>
            </div>
            <div class="stat-card failure">
                <div class="label">Failed</div>
                <div class="value">{failed}</div>
            </div>
            <div class="stat-card rate">
                <div class="label">Pass Rate</div>
                <div class="value">{pass_rate:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="label">Duration</div>
                <div class="value">{execution_time:.1f}s</div>
            </div>
        </div>
        
        <div class="progress-bar">
            <h3>Test Execution Progress</h3>
            <div class="progress-track">
                <div class="progress-fill" style="width: {pass_rate}%">
                    {passed}/{total_tests} Passed
                </div>
            </div>
        </div>
        
        <div class="tests-section">
            <h2>📋 Test Results Details</h2>
"""
        
        # Add test details
        for test in test_details:
            status = test.get('status', 'UNKNOWN').lower()
            name = test.get('name', 'Unknown Test')
            description = test.get('description', '')
            tags = test.get('tags', [])
            exec_time = test.get('execution_time', 0)
            error = test.get('error', '')
            file_path = test.get('file_path', '')
            
            status_class = 'passed' if status == 'passed' else 'failed'
            status_emoji = '✅' if status == 'passed' else '❌'
            
            tags_html = ''.join([f'<span class="tag">{tag}</span>' for tag in tags])
            
            html_content += f"""
            <div class="test-item {status_class}">
                <div class="test-header">
                    <div class="test-name">{status_emoji} {name}</div>
                    <div class="test-status {status_class}">{status}</div>
                </div>
                <div class="test-description">{description}</div>
                <div class="test-meta">
                    <span>⏱️ {exec_time}s</span>
                    <span>📁 {Path(file_path).name if file_path else 'N/A'}</span>
                    <span>{tags_html}</span>
                </div>
"""
            
            # Add failure video if available
            video_path = test.get('video_path')
            if video_path and Path(f"reports/{video_path}").exists():
                html_content += f"""
                <div style="margin-top: 15px;">
                    <strong>🎥 Failure Video:</strong>
                    <div style="margin-top: 10px; border: 2px solid #f56565; border-radius: 8px; overflow: hidden; background: #000;">
                        <video controls style="max-width: 100%; display: block;">
                            <source src="{video_path}" type="video/webm">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                    <div style="margin-top: 5px;">
                        <a href="{video_path}" download style="color: #4299e1; text-decoration: none;">
                            📥 Download Video
                        </a>
                    </div>
                </div>
"""
            
            # Add failure screenshot if available
            failure_screenshot = test.get('failure_screenshot')
            if failure_screenshot and Path(f"reports/{failure_screenshot}").exists():
                html_content += f"""
                <div style="margin-top: 15px;">
                    <strong>📸 Failure Screenshot:</strong>
                    <div style="margin-top: 10px; border: 2px solid #f56565; border-radius: 8px; overflow: hidden;">
                        <img src="{failure_screenshot}" alt="Failure Screenshot" style="max-width: 100%; display: block;">
                    </div>
                </div>
"""
            
            # Add soft assertion failures
            soft_assertions = test.get('soft_assertions')
            if soft_assertions and soft_assertions.get('count', 0) > 0:
                failures = soft_assertions.get('failures', [])
                html_content += f"""
                <div class="error-message" style="background: #fff5e6; border-left: 4px solid #f59e0b;">
                    <strong>⚠️ Soft Assertion Failures: {soft_assertions['count']}</strong>
                    <ul style="margin: 10px 0 0 20px; padding: 0;">
"""
                for failure in failures:
                    step_num = failure.get('step_number', 'N/A')
                    action = failure.get('action', 'Unknown')
                    message = failure.get('message', '')
                    expected = failure.get('expected')
                    actual = failure.get('actual')
                    
                    html_content += f"""
                        <li style="margin: 5px 0;">
                            <strong>Step {step_num} ({action}):</strong> {message}
"""
                    if expected:
                        html_content += f"<br>&nbsp;&nbsp;&nbsp;&nbsp;<em>Expected:</em> {expected}"
                    if actual:
                        html_content += f"<br>&nbsp;&nbsp;&nbsp;&nbsp;<em>Actual:</em> {actual}"
                    html_content += "</li>"
                
                html_content += """
                    </ul>
                </div>
"""
            
            # Add failed step details
            failed_step = test.get('failed_step')
            if failed_step:
                step_num = failed_step.get('step_number', 'N/A')
                step_action = failed_step.get('step_action', 'Unknown')
                step_details = failed_step.get('step_details', '')
                step_error = failed_step.get('error', '')
                
                html_content += f"""
                <div class="error-message">
                    <strong>❌ Failed at Step {step_num}:</strong> {step_action}<br>
                    {f'<strong>Details:</strong> {step_details}<br>' if step_details else ''}
                    {f'<strong>Error:</strong> {step_error}' if step_error else ''}
                </div>
"""
            elif error:
                html_content += f"""
                <div class="error-message">
                    <strong>Error:</strong> {error}
                </div>
"""
            
            # Add execution log if available
            execution_log = test.get('execution_log', '')
            if execution_log:
                # Escape HTML in log
                import html
                escaped_log = html.escape(execution_log)
                
                html_content += f"""
                <div class="log-section">
                    <button class="log-toggle" onclick="toggleLog(this)">
                        📋 Show Execution Log
                    </button>
                    <div class="log-content">
{escaped_log}
                    </div>
                </div>
"""
            
            html_content += """
            </div>
"""
        
        html_content += """
        </div>
        
        <div class="footer">
            <p>Easy BDD Framework - Making BDD Testing Simple</p>
        </div>
    </div>
    
    <script>
        // Animate progress bar on load
        window.addEventListener('load', () => {
            const progressFill = document.querySelector('.progress-fill');
            const width = progressFill.style.width;
            progressFill.style.width = '0%';
            setTimeout(() => {
                progressFill.style.width = width;
            }, 100);
        });
        
        // Toggle log visibility
        function toggleLog(button) {
            const logContent = button.nextElementSibling;
            logContent.classList.toggle('show');
            
            if (logContent.classList.contains('show')) {
                button.textContent = '📋 Hide Execution Log';
            } else {
                button.textContent = '📋 Show Execution Log';
            }
        }
    </script>
</body>
</html>
"""
        
        # Write HTML file with test file name prefix
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"{test_file_name}_report_{timestamp}.html"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return report_path
