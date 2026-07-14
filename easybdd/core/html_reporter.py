"""
HTML Report Generator for Easy BDD Tests
"""

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class HTMLReporter:
    """Generate beautiful HTML reports for test execution"""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _parse_steps_from_log(self, execution_log: str) -> List[Dict[str, Any]]:
        """Parse test steps from execution log output"""
        steps = []
        if not execution_log:
            return steps

        lines = execution_log.split("\n")
        current_step = None

        # Patterns to match step information - each tuple is (pattern, step_num_group_index, action_group_index)
        step_patterns = [
            (
                r"Step\s+(\d+)/(\d+):\s+(.+)",
                1,
                3,
            ),  # "Step 1/5: action" - group 1 is step num, group 3 is action
            (
                r"Step\s+(\d+):\s+(.+)",
                1,
                2,
            ),  # "Step 1: action" - group 1 is step num, group 2 is action
            (r"→\s+(.+)", None, 1),  # "→ action" - group 1 is action, no step num
        ]

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Check for step start
            for pattern_info in step_patterns:
                pattern, step_num_group, action_group = pattern_info
                match = re.match(pattern, line)
                if match:
                    # Extract step number
                    if (
                        step_num_group is not None
                        and len(match.groups()) >= step_num_group
                    ):
                        try:
                            step_num = int(match.group(step_num_group))
                        except (ValueError, IndexError):
                            step_num = len(steps) + 1
                    else:
                        step_num = len(steps) + 1

                    # Extract action
                    if action_group is not None and len(match.groups()) >= action_group:
                        try:
                            action = match.group(action_group).strip()
                        except IndexError:
                            action = line
                    else:
                        action = line

                    # Close previous step if exists
                    if current_step:
                        steps.append(current_step)

                    # Start new step
                    current_step = {
                        "number": step_num,
                        "action": action,
                        "status": "pending",
                        "output": [],
                    }
                    break

            # Check for step completion indicators
            if current_step:
                if (
                    "✅" in line
                    or "completed successfully" in line.lower()
                    or "PASSED" in line
                ):
                    current_step["status"] = "completed"
                    steps.append(current_step)
                    current_step = None
                elif "❌" in line or "FAILED" in line or "failed" in line.lower():
                    current_step["status"] = "failed"
                    current_step["output"].append(line)
                    steps.append(current_step)
                    current_step = None
                else:
                    # Add to step output
                    current_step["output"].append(line)

        # Add final step if exists
        if current_step:
            steps.append(current_step)

        return steps

    def _parse_logs_into_sections(self, execution_log: str) -> tuple:
        """Parse execution log into simple and debug sections"""
        if not execution_log:
            return ("", "")

        lines = execution_log.split("\n")
        simple_lines = []
        debug_lines = []

        # Patterns that indicate verbose/debug content (should be excluded from simple log)
        verbose_patterns = [
            r"^\s+📋",  # Request/Response Headers
            r"^\s+📤",  # Request Body
            r"^\s+📡",  # Status
            r"^\s+📦",  # Response Body
            r"^\s+🔑",  # Token/auth info
            r"^\s+🔄",  # Retry/auth refresh
            r"^\s+💾",  # Storage info
            r"^\s+⚠️",  # Warnings
            r"^\s+🔍",  # Debug/search
            r"^\s+\{",  # JSON objects (indented)
            r"^\s+\[",  # JSON arrays (indented)
            r"Response Headers:",
            r"Request Headers:",
            r"Query Params:",
            r"Request Body \(JSON\):",
            r"Response Body \(JSON\):",
            r"Response Body:",
            r"Request Body:",
        ]

        # Patterns for simple log (step names, status, minimal info)
        simple_patterns = [
            r"^Step\s+\d+/\d+:",  # "Step 1/5:"
            r"^Step\s+\d+:",  # "Step 1:"
            r"^→\s+",  # "→"
            r"^Executing test",
            r"^Test Results:",
            r"^Execution time:",
            r"^Generated \d+",
            r"^Running \d+",
            r"^===",
            r"^✅|^❌|^PASSED|^FAILED",
            r"^.*completed successfully",
            r"^.*STEP.*FAILED",
        ]

        i = 0
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()

            # Skip empty lines in simple log, but keep them in debug log
            if not line_stripped:
                debug_lines.append(line)
                i += 1
                continue

            # Check if line is verbose/debug content
            is_verbose = any(
                re.search(pattern, line, re.IGNORECASE) for pattern in verbose_patterns
            )

            # Check if line is a simple/status line
            is_simple_line = any(
                re.search(pattern, line, re.IGNORECASE) for pattern in simple_patterns
            )

            # Always add to debug log
            debug_lines.append(line)

            # Add to simple log only if it's a simple line and not verbose
            if is_simple_line and not is_verbose:
                # For API lines, extract just the basic info
                if "API" in line and (
                    "GET" in line
                    or "POST" in line
                    or "PUT" in line
                    or "PATCH" in line
                    or "DELETE" in line
                ):
                    # Extract just "API GET: url" without device info
                    match = re.match(
                        r"(.+?API\s+(?:GET|POST|PUT|PATCH|DELETE):\s+[^\s(]+)", line
                    )
                    if match:
                        simple_lines.append(match.group(1).strip())
                    else:
                        # Fallback: just the API method and URL part
                        parts = line.split("(")
                        simple_lines.append(parts[0].strip())
                else:
                    simple_lines.append(line)
            elif is_simple_line and is_verbose:
                # It's a simple line but has verbose content - extract just the key part
                if "API" in line:
                    match = re.match(
                        r"(.+?API\s+(?:GET|POST|PUT|PATCH|DELETE):\s+[^\s(]+)", line
                    )
                    if match:
                        simple_lines.append(match.group(1).strip())

            i += 1

        return ("\n".join(simple_lines), "\n".join(debug_lines))

    def generate_report(
        self,
        test_details: List[Dict[str, Any]],
        total_tests: int,
        passed: int,
        failed: int,
        execution_time: float,
        test_file_name: str = "test",
        report_name: str = None,
    ) -> Path:
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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #0f172a;
            color: #f1f5f9;
            line-height: 1.6;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        .header {{
            background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
            color: #f1f5f9;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            margin-bottom: 30px;
            border: 1px solid #334155;
        }}

        .header h1 {{
            font-size: 32px;
            font-weight: 600;
            margin-bottom: 8px;
        }}

        .header .subtitle {{
            font-size: 14px;
            opacity: 0.9;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: #1e293b;
            padding: 24px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
            text-align: center;
            border-top: 3px solid #334155;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            border: 1px solid #334155;
        }}

        .stat-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.4);
            background: #334155;
        }}

        .stat-card.success {{
            border-top-color: #10b981;
        }}

        .stat-card.failure {{
            border-top-color: #ef4444;
        }}

        .stat-card.rate {{
            border-top-color: #3b82f6;
        }}

        .stat-card.duration {{
            border-top-color: #f59e0b;
        }}

        .stat-card .label {{
            color: #94a3b8;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
            font-weight: 600;
        }}

        .stat-card .value {{
            font-size: 32px;
            font-weight: 700;
            color: #f1f5f9;
        }}

        .stat-card.success .value {{
            color: #10b981;
        }}

        .stat-card.failure .value {{
            color: #ef4444;
        }}

        .stat-card.rate .value {{
            color: #3b82f6;
        }}

        .stat-card.duration .value {{
            color: #f59e0b;
        }}

        .progress-bar {{
            background: #1e293b;
            padding: 24px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
            margin-bottom: 30px;
            border: 1px solid #334155;
        }}

        .progress-bar h3 {{
            color: #f1f5f9;
            margin-bottom: 16px;
            font-size: 16px;
            font-weight: 600;
        }}

        .progress-track {{
            background: #334155;
            height: 32px;
            border-radius: 16px;
            overflow: hidden;
            position: relative;
        }}

        .progress-fill {{
            background: linear-gradient(90deg, #10b981 0%, #059669 100%);
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
            font-size: 13px;
            transition: width 1s ease;
        }}

        .tests-section {{
            background: #1e293b;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
            margin-bottom: 30px;
            border: 1px solid #334155;
        }}

        .tests-section h2 {{
            color: #f1f5f9;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 2px solid #334155;
            font-size: 20px;
            font-weight: 600;
        }}

        .test-item {{
            padding: 24px;
            border-left: 4px solid #334155;
            margin-bottom: 24px;
            background: #0f172a;
            border-radius: 8px;
            transition: all 0.2s ease;
            border: 1px solid #334155;
        }}

        .test-item:hover {{
            background: #1e293b;
        }}

        .test-item.passed {{
            border-left-color: #10b981;
        }}

        .test-item.failed {{
            border-left-color: #ef4444;
        }}

        .test-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}

        .test-name {{
            font-size: 18px;
            font-weight: 600;
            color: #f1f5f9;
        }}

        .test-status {{
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .test-status.passed {{
            background: #d1fae5;
            color: #065f46;
        }}

        .test-status.failed {{
            background: #fee2e2;
            color: #991b1b;
        }}

        .test-description {{
            color: #94a3b8;
            font-size: 14px;
            margin-bottom: 12px;
        }}

        .test-meta {{
            display: flex;
            gap: 20px;
            font-size: 13px;
            color: #64748b;
            margin-bottom: 16px;
        }}

        .test-meta span {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .tag {{
            display: inline-block;
            padding: 4px 10px;
            background: #334155;
            color: #94a3b8;
            border-radius: 6px;
            font-size: 11px;
            margin-right: 6px;
            font-weight: 500;
        }}

        .steps-section {{
            margin-top: 20px;
            margin-bottom: 20px;
        }}

        .steps-title {{
            font-size: 14px;
            font-weight: 600;
            color: #94a3b8;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .steps-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .step-item {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 12px;
            background: #1e293b;
            border-radius: 6px;
            border: 1px solid #334155;
            transition: all 0.2s ease;
        }}

        .step-item:hover {{
            border-color: #475569;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
            background: #334155;
        }}

        .step-icon {{
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            flex-shrink: 0;
            font-size: 12px;
        }}

        .step-item.pending .step-icon {{
            background: #334155;
            color: #64748b;
        }}

        .step-item.completed .step-icon {{
            background: #065f46;
            color: #10b981;
        }}

        .step-item.failed .step-icon {{
            background: #7f1d1d;
            color: #ef4444;
        }}

        .step-content {{
            flex: 1;
        }}

        .step-action {{
            font-size: 14px;
            font-weight: 500;
            color: #f1f5f9;
            margin-bottom: 4px;
        }}

        .step-description {{
            font-size: 12px;
            color: #94a3b8;
        }}

        .error-message {{
            margin-top: 16px;
            padding: 16px;
            background: #fef2f2;
            border-left: 3px solid #ef4444;
            border-radius: 6px;
            color: #991b1b;
            font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            line-height: 1.5;
        }}

        .log-section {{
            margin-top: 20px;
        }}

        .log-tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
            border-bottom: 2px solid #334155;
        }}

        .log-tab {{
            background: transparent;
            color: #94a3b8;
            border: none;
            padding: 10px 20px;
            border-radius: 6px 6px 0 0;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s ease;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
        }}

        .log-tab:hover {{
            color: #f1f5f9;
            background: #1e293b;
        }}

        .log-tab.active {{
            color: #3b82f6;
            border-bottom-color: #3b82f6;
            background: #1e293b;
        }}

        .log-content {{
            display: none;
            padding: 16px;
            background: #1e293b;
            color: #e2e8f0;
            border-radius: 6px;
            font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            max-height: 600px;
            overflow-y: auto;
            white-space: pre-wrap;
            line-height: 1.6;
        }}

        .log-content.active {{
            display: block;
        }}

        .log-toggle {{
            background: #3b82f6;
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: background 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 12px;
        }}

        .log-toggle:hover {{
            background: #2563eb;
        }}

        .footer {{
            text-align: center;
            color: #94a3b8;
            margin-top: 40px;
            padding: 24px;
            font-size: 13px;
        }}

        @media print {{
            body {{
                background: white;
                padding: 0;
            }}

            .test-item {{
                page-break-inside: avoid;
            }}

            .log-content {{
                max-height: none;
            }}
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
            <div class="stat-card duration">
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
        for test_idx, test in enumerate(test_details):
            status = test.get("status", "UNKNOWN").lower()
            name = test.get("name", "Unknown Test")
            description = test.get("description", "")
            tags = test.get("tags", [])
            exec_time = test.get("execution_time", 0)
            error = test.get("error", "")
            file_path = test.get("file_path", "")
            execution_log = test.get("execution_log", "")

            status_class = (
                "passed" if status == "passed" or status == "completed" else "failed"
            )
            status_emoji = "✅" if status == "passed" or status == "completed" else "❌"

            tags_html = "".join(
                [f'<span class="tag">{html.escape(str(tag))}</span>' for tag in tags]
            )

            html_content += f"""
            <div class="test-item {status_class}">
                <div class="test-header">
                    <div class="test-name">{status_emoji} {html.escape(name)}</div>
                    <div class="test-status {status_class}">{status.upper()}</div>
                </div>
                <div class="test-description">{html.escape(description)}</div>
                <div class="test-meta">
                    <span>⏱️ {exec_time:.2f}s</span>
                    <span>📁 {html.escape(Path(file_path).name if file_path else 'N/A')}</span>
                    <span>{tags_html}</span>
                </div>
"""

            # Get step logs from test_detail (more accurate than parsing logs)
            step_logs = test.get("step_logs", [])
            
            # Also parse steps from execution log as fallback
            steps = self._parse_steps_from_log(execution_log)
            
            # Use step_logs if available (more accurate), otherwise use parsed steps
            if step_logs:
                total_steps = len(step_logs)
                completed_steps = sum(1 for s in step_logs if s.get("status") == "passed")
                failed_steps = sum(1 for s in step_logs if s.get("status") == "failed")
                progress_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
                
                html_content += f"""
                <div class="steps-section" style="margin-top: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div class="steps-title" style="font-size: 16px; font-weight: bold; color: #1e293b;">📝 Test Execution Progress</div>
                        <div style="font-size: 14px; color: #64748b;">
                            <span style="color: #10b981;">✓ {completed_steps}</span> / 
                            <span style="color: #ef4444;">✗ {failed_steps}</span> / 
                            <span style="color: #64748b;">○ {total_steps}</span> steps
                        </div>
                    </div>
                    
                    <!-- Progress Bar -->
                    <div style="margin-bottom: 16px;">
                        <div style="background: #e5e7eb; border-radius: 8px; height: 24px; overflow: hidden; position: relative;">
                            <div style="background: linear-gradient(90deg, #10b981 0%, #059669 100%); height: 100%; width: {progress_percentage}%; transition: width 0.3s ease; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold;">
                                {int(progress_percentage)}%
                            </div>
                        </div>
                    </div>
                    
                    <div class="steps-list" style="display: flex; flex-direction: column; gap: 8px;">
"""
                for step_log in step_logs:
                    step_num = step_log.get("step", step_log.get("number", 0))
                    step_action = html.escape(str(step_log.get("action", "Unknown step")))
                    step_status = step_log.get("status", "pending")
                    
                    # Determine status and styling
                    if step_status == "passed":
                        icon = "✓"
                        status_color = "#10b981"
                        bg_color = "#f0fdf4"
                        border_color = "#10b981"
                    elif step_status == "failed":
                        icon = "✗"
                        status_color = "#ef4444"
                        bg_color = "#fef2f2"
                        border_color = "#ef4444"
                    else:
                        icon = "○"
                        status_color = "#94a3b8"
                        bg_color = "#f8fafc"
                        border_color = "#cbd5e1"
                    
                    html_content += f"""
                        <div class="step-item {step_status}" style="display: flex; align-items: start; padding: 12px; background: {bg_color}; border-left: 4px solid {border_color}; border-radius: 6px; gap: 12px;">
                            <div class="step-icon" style="font-size: 18px; color: {status_color}; font-weight: bold; min-width: 24px;">{icon}</div>
                            <div class="step-content" style="flex: 1;">
                                <div class="step-action" style="font-weight: 600; color: #1e293b; margin-bottom: 4px;">
                                    Step {step_num}: {step_action}
                                </div>
                                <div style="font-size: 12px; color: {status_color}; text-transform: uppercase; font-weight: 500;">
                                    {step_status}
                                </div>
                            </div>
                        </div>
"""
                html_content += """
                    </div>
                </div>
"""
            elif steps:
                # Fallback to parsed steps if step_logs not available
                total_steps = len(steps)
                completed_steps = sum(1 for s in steps if s.get("status") == "completed")
                failed_steps = sum(1 for s in steps if s.get("status") == "failed")
                progress_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
                
                html_content += f"""
                <div class="steps-section" style="margin-top: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div class="steps-title" style="font-size: 16px; font-weight: bold; color: #1e293b;">📝 Test Execution Progress</div>
                        <div style="font-size: 14px; color: #64748b;">
                            <span style="color: #10b981;">✓ {completed_steps}</span> / 
                            <span style="color: #ef4444;">✗ {failed_steps}</span> / 
                            <span style="color: #64748b;">○ {total_steps}</span> steps
                        </div>
                    </div>
                    
                    <!-- Progress Bar -->
                    <div style="margin-bottom: 16px;">
                        <div style="background: #e5e7eb; border-radius: 8px; height: 24px; overflow: hidden; position: relative;">
                            <div style="background: linear-gradient(90deg, #10b981 0%, #059669 100%); height: 100%; width: {progress_percentage}%; transition: width 0.3s ease; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold;">
                                {int(progress_percentage)}%
                            </div>
                        </div>
                    </div>
                    
                    <div class="steps-list" style="display: flex; flex-direction: column; gap: 8px;">
"""
                for step in steps:
                    step_status = step.get("status", "pending")
                    step_num = step.get("number", 0)
                    step_action = html.escape(step.get("action", "Unknown step"))

                    if step_status == "completed":
                        icon = "✓"
                        status_color = "#10b981"
                        bg_color = "#f0fdf4"
                        border_color = "#10b981"
                    elif step_status == "failed":
                        icon = "✗"
                        status_color = "#ef4444"
                        bg_color = "#fef2f2"
                        border_color = "#ef4444"
                    else:
                        icon = "○"
                        status_color = "#94a3b8"
                        bg_color = "#f8fafc"
                        border_color = "#cbd5e1"

                    html_content += f"""
                        <div class="step-item {step_status}" style="display: flex; align-items: start; padding: 12px; background: {bg_color}; border-left: 4px solid {border_color}; border-radius: 6px; gap: 12px;">
                            <div class="step-icon" style="font-size: 18px; color: {status_color}; font-weight: bold; min-width: 24px;">{icon}</div>
                            <div class="step-content" style="flex: 1;">
                                <div class="step-action" style="font-weight: 600; color: #1e293b; margin-bottom: 4px;">
                                    Step {step_num}: {step_action}
                                </div>
                                <div style="font-size: 12px; color: {status_color}; text-transform: uppercase; font-weight: 500;">
                                    {step_status}
                                </div>
                            </div>
                        </div>
"""
                html_content += """
                    </div>
                </div>
"""

            # Add failure video if available
            video_path = test.get("video_path")
            if video_path and Path(f"reports/{video_path}").exists():
                html_content += f"""
                <div style="margin-top: 16px;">
                    <strong style="color: #1e293b;">🎥 Failure Video:</strong>
                    <div style="margin-top: 10px; border: 2px solid #ef4444; border-radius: 8px; overflow: hidden; background: #000;">
                        <video controls style="max-width: 100%; display: block;">
                            <source src="{html.escape(video_path)}" type="video/webm">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                </div>
"""

            # Add failure screenshot if available
            failure_screenshot = test.get("failure_screenshot")
            if failure_screenshot and Path(f"reports/{failure_screenshot}").exists():
                html_content += f"""
                <div style="margin-top: 16px;">
                    <strong style="color: #1e293b;">📸 Failure Screenshot (Last Action Before Failure):</strong>
                    <div style="margin-top: 10px; border: 2px solid #ef4444; border-radius: 8px; overflow: hidden; background: #fef2f2;">
                        <img src="{html.escape(failure_screenshot)}" alt="Failure Screenshot" style="max-width: 100%; display: block; cursor: pointer;" onclick="window.open(this.src, '_blank')" title="Click to open full size">
                    </div>
                    <p style="margin-top: 8px; font-size: 12px; color: #666;">This screenshot shows the state after the last successful step, before the failure occurred.</p>
                </div>
"""
            
            # Add step screenshots if available (for debugging)
            step_screenshots = test.get("step_screenshots", [])
            if step_screenshots and len(step_screenshots) > 0:
                html_content += """
                <div style="margin-top: 16px;">
                    <strong style="color: #1e293b;">📸 Step Screenshots:</strong>
                    <div style="margin-top: 10px; display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;">
"""
                for step_screenshot in step_screenshots[-5:]:  # Show last 5 step screenshots
                    step_num = step_screenshot.get("step", "?")
                    screenshot_path = step_screenshot.get("screenshot", "")
                    if screenshot_path and Path(f"reports/{screenshot_path}").exists():
                        html_content += f"""
                        <div style="border: 1px solid #ddd; border-radius: 6px; overflow: hidden; background: white;">
                            <div style="padding: 6px; background: #f8f9fa; font-size: 11px; font-weight: bold; color: #495057;">Step {step_num}</div>
                            <img src="{html.escape(screenshot_path)}" alt="Step {step_num} Screenshot" style="width: 100%; display: block; cursor: pointer;" onclick="window.open(this.src, '_blank')" title="Click to open full size">
                        </div>
"""
                html_content += """
                    </div>
                </div>
"""

            # Add soft assertion failures
            soft_assertions = test.get("soft_assertions")
            if soft_assertions and soft_assertions.get("count", 0) > 0:
                failures = soft_assertions.get("failures", [])
                html_content += f"""
                <div class="error-message" style="background: #fffbeb; border-left: 4px solid #f59e0b; color: #92400e;">
                    <strong>⚠️ Soft Assertion Failures: {soft_assertions['count']}</strong>
                    <ul style="margin: 10px 0 0 20px; padding: 0;">
"""
                for failure in failures:
                    step_num = failure.get("step_number", "N/A")
                    action = failure.get("action", "Unknown")
                    message = failure.get("message", "")
                    expected = failure.get("expected")
                    actual = failure.get("actual")

                    html_content += f"""
                        <li style="margin: 5px 0;">
                            <strong>Step {step_num} ({html.escape(str(action))}):</strong> {html.escape(str(message))}
"""
                    if expected:
                        html_content += f"<br>&nbsp;&nbsp;&nbsp;&nbsp;<em>Expected:</em> {html.escape(str(expected))}"
                    if actual:
                        html_content += f"<br>&nbsp;&nbsp;&nbsp;&nbsp;<em>Actual:</em> {html.escape(str(actual))}"
                    html_content += "</li>"

                html_content += """
                    </ul>
                </div>
"""

            # Add failed step details
            failed_step = test.get("failed_step")
            if failed_step:
                step_num = failed_step.get("step_number", "N/A")
                step_action = failed_step.get("step_action", "Unknown")
                step_details = failed_step.get("step_details", "")
                step_error = failed_step.get("error", "")

                html_content += f"""
                <div class="error-message">
                    <strong>❌ Failed at Step {step_num}:</strong> {html.escape(str(step_action))}<br>
                    {f'<strong>Details:</strong> {html.escape(str(step_details))}<br>' if step_details else ''}
                    {f'<strong>Error:</strong> {html.escape(str(step_error))}' if step_error else ''}
                </div>
"""
            elif error:
                html_content += f"""
                <div class="error-message">
                    <strong>Error:</strong> {html.escape(str(error))}
                </div>
"""

            # Add execution log if available
            if execution_log:
                simple_log, debug_log = self._parse_logs_into_sections(execution_log)
                escaped_simple = html.escape(simple_log)
                escaped_debug = html.escape(debug_log)
                log_id = f"log-{test_idx}"

                html_content += f"""
                <div class="log-section">
                    <button class="log-toggle" onclick="toggleLogSection(this)">
                        <span>📋</span>
                        <span>Show Execution Logs</span>
                    </button>
                    <div class="log-tabs-container" style="display: none;">
                        <div class="log-tabs">
                            <button class="log-tab active" onclick="switchLogTab(this, '{log_id}', 'simple')">
                                📝 Simple Log
                            </button>
                            <button class="log-tab" onclick="switchLogTab(this, '{log_id}', 'debug')">
                                🔍 Debug Log
                            </button>
                        </div>
                        <div id="log-simple-{log_id}" class="log-content active">
{escaped_simple}
                        </div>
                        <div id="log-debug-{log_id}" class="log-content">
{escaped_debug}
                        </div>
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
            if (progressFill) {
            const width = progressFill.style.width;
            progressFill.style.width = '0%';
            setTimeout(() => {
                progressFill.style.width = width;
            }, 100);
            }
        });

        // Toggle log section visibility
        function toggleLogSection(button) {
            const tabsContainer = button.nextElementSibling;
            const span = button.querySelector('span:last-child');

            if (tabsContainer.style.display === 'none') {
                tabsContainer.style.display = 'block';
                span.textContent = 'Hide Execution Logs';
            } else {
                tabsContainer.style.display = 'none';
                span.textContent = 'Show Execution Logs';
            }
        }

        // Switch between Simple and Debug log tabs
        function switchLogTab(button, logId, logType) {
            // Get the log section container
            const logSection = button.closest('.log-section');
            const tabs = logSection.querySelectorAll('.log-tab');

            // Remove active class from all tabs
            tabs.forEach(tab => tab.classList.remove('active'));

            // Add active class to clicked tab
            button.classList.add('active');

            // Hide all log contents
            const simpleContent = document.getElementById(`log-simple-${logId}`);
            const debugContent = document.getElementById(`log-debug-${logId}`);

            if (simpleContent) simpleContent.classList.remove('active');
            if (debugContent) debugContent.classList.remove('active');

            // Show the selected content
            if (logType === 'simple' && simpleContent) {
                simpleContent.classList.add('active');
            } else if (logType === 'debug' && debugContent) {
                debugContent.classList.add('active');
            }
        }
    </script>
</body>
</html>
"""

        # Build filename slug: use report_name if provided, else test_file_name
        import re as _re
        raw_name = report_name or test_file_name or "test"
        slug = _re.sub(r"[^\w\-]", "_", raw_name)   # replace non-word chars with _
        slug = _re.sub(r"_+", "_", slug).strip("_")  # collapse runs of underscores
        slug = slug[:80]                              # cap length

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"{slug}_report_{timestamp_str}.html"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Also save JSON for metrics engine
        json_data = {
            "timestamp": timestamp,
            "test_file": test_file_name,
            "report_name": raw_name,
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "execution_time": execution_time,
            "tests": test_details,
        }
        json_path = self.output_dir / f"{slug}_results_{timestamp_str}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

        return report_path
