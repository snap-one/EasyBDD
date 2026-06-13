"""
Main entry point for the Easy BDD Framework
Usage: python -m easy_bdd [command] [options]
"""

import os
import re
import sys
import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()  # Load environment variables from .env file
except ImportError:
    pass  # python-dotenv not installed, continue without it

from .core.runner import TestRunner
from .core.generator import GherkinGenerator
from .core.config import ConfigManager
from .core.variable_manager import GlobalConfigManager


def main():
    parser = argparse.ArgumentParser(
        description="Easy BDD Testing Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m easy_bdd run                              # Run all tests
  python -m easy_bdd run tests/cases/login.yaml      # Run specific test
  python -m easy_bdd run --tags browser,api          # Run tests with tags
  python -m easy_bdd docker-run tests/cases/login.yaml  # Run test in Docker
  python -m easy_bdd generate tests/cases/           # Generate Gherkin only
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run tests")
    run_parser.add_argument(
        "path",
        nargs="?",
        default="tests/cases/",
        help="Path to test files or directory (default: tests/cases/)",
    )
    run_parser.add_argument(
        "--tags", help="Comma-separated list of tags to filter tests"
    )
    run_parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    run_parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser with visible window (default)",
    )
    run_parser.add_argument(
        "--ignore-https", action="store_true", help="Ignore HTTPS certificate errors"
    )
    run_parser.add_argument(
        "--browser",
        choices=["chrome", "firefox", "edge", "safari"],
        help="Browser to use for tests",
    )
    run_parser.add_argument(
        "--export-results",
        help="Export test results to file (JSON, CSV, XML format auto-detected by extension)",
    )
    run_parser.add_argument(
        "--record-video",
        action="store_true",
        help="Enable video recording for all browser actions in this test run",
    )

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate", help="Generate Gherkin features from YAML/JSON"
    )
    gen_parser.add_argument("path", help="Path to YAML/JSON test files or directory")
    gen_parser.add_argument(
        "--output",
        default="tests/features/",
        help="Output directory for Gherkin files (default: tests/features/)",
    )
    gen_parser.add_argument(
        "--format",
        choices=["gherkin", "yaml", "json"],
        default="gherkin",
        help="Output format (default: gherkin)",
    )

    # Convert command for UI recordings
    convert_parser = subparsers.add_parser(
        "convert", help="Convert UI recorder files to Easy BDD format"
    )
    convert_parser.add_argument(
        "input_file", help="Path to the recorder file to convert"
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate test files or a YAML step snippet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Validate Easy BDD test YAML for syntax, action names, parameters,\n"
            "shared step references, and variable usage.\n\n"
            "Examples:\n"
            "  python -m easy_bdd validate tests/cases/my_test.yaml\n"
            "  python -m easy_bdd validate tests/cases/\n"
            "  python -m easy_bdd validate --snippet \"- test.assert:\\n    expression: x == 1\"\n"
            "  python -m easy_bdd validate --snippet-file my_steps.yaml\n"
            "  cat steps.yaml | python -m easy_bdd validate --stdin"
        ),
    )
    validate_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to test file or directory (default: tests/cases/)",
    )
    validate_parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )
    validate_parser.add_argument(
        "--snippet", "-s",
        metavar="YAML",
        help="Validate a YAML step snippet string instead of a file",
    )
    validate_parser.add_argument(
        "--snippet-file",
        metavar="FILE",
        help="Validate a file containing YAML steps (not a full test file)",
    )
    validate_parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read YAML snippet from stdin",
    )
    validate_parser.add_argument(
        "--shared-steps-dir",
        metavar="DIR",
        help="Directory containing shared_steps.yaml for shared step validation",
    )
    # TestRail targets
    _tr_group = validate_parser.add_argument_group("TestRail targets")
    _tr_group.add_argument(
        "--testrail-case",
        metavar="CASE_ID",
        type=int,
        help="Validate a single TestRail case by ID",
    )
    _tr_group.add_argument(
        "--testrail-suite",
        metavar="SUITE_ID",
        type=int,
        help="Validate all cases in a TestRail suite",
    )
    _tr_group.add_argument(
        "--testrail-run",
        metavar="RUN_ID",
        type=int,
        help="Validate all Feature:/Shared: cases in a TestRail run",
    )
    _tr_group.add_argument(
        "--project",
        metavar="PROJECT_ID",
        type=int,
        help="TestRail project ID (required with --testrail-suite)",
    )
    
    # Docker-run command
    docker_parser = subparsers.add_parser(
        "docker-run", help="Build Docker image, run test in container, then cleanup"
    )
    docker_parser.add_argument(
        "test_path",
        help="Path to test file (e.g., tests/cases/login.yaml)",
    )
    docker_parser.add_argument(
        "--image-name",
        default="easy-bdd:latest",
        help="Docker image name (default: easy-bdd:latest)",
    )
    docker_parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip building the image (use existing image)",
    )
    docker_parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Keep container after execution (don't auto-remove)",
    )
    docker_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    docker_parser.add_argument(
        "--tags",
        help="Comma-separated list of tags to filter tests",
    )
    docker_parser.add_argument(
        "--export-results",
        help="Export test results to file (mounted from host)",
    )

    # Edit-test command
    edit_parser = subparsers.add_parser(
        "edit-test", help="Open a test file in the default editor"
    )
    edit_parser.add_argument(
        "test_path", type=str, help="Path to test file to edit"
    )

    # TestRail run command
    tr_parser = subparsers.add_parser(
        "testrail-run",
        help="Execute tests driven by a TestRail run (EASY_BDD: prefix)",
    )
    tr_parser.add_argument(
        "project_id",
        type=int,
        help="TestRail project ID to scan for an active EASY_BDD: run",
    )
    tr_parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        help="Target a specific TestRail run ID instead of auto-discovering",
    )
    tr_parser.add_argument(
        "--tests-dir",
        default="tests/cases",
        help="Directory to search for local YAML tests (default: tests/cases)",
    )
    tr_parser.add_argument(
        "--artifact-dir",
        default="reports/testrail",
        help="Directory for generated artifacts and reports (default: reports/testrail)",
    )
    tr_parser.add_argument(
        "--prefix",
        default=None,
        help="TestRail run name prefix to match (default: EASY_BDD:, or TESTRAIL_RUN_PREFIX env var)",
    )
    tr_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-test progress output",
    )
    tr_parser.add_argument(
        "--no-datalake",
        action="store_true",
        dest="no_datalake",
        help="Skip posting results to the datalake for this run",
    )
    tr_parser.add_argument(
        "--find-only",
        action="store_true",
        dest="find_only",
        help="Check if an active run exists and write properties file, without executing tests",
    )

    # TestRail convert command
    trc_parser = subparsers.add_parser(
        "testrail-convert",
        help="Convert a mybdd-format TestRail suite to Easy BDD YAML test files",
    )
    trc_parser.add_argument(
        "project_id",
        type=int,
        help="TestRail project ID",
    )
    _src = trc_parser.add_mutually_exclusive_group(required=True)
    _src.add_argument(
        "--suite",
        type=int,
        dest="source_suite_id",
        metavar="SUITE_ID",
        help="Suite ID to convert (mybdd format: Given:/Shared:/Feature: cases)",
    )
    _src.add_argument(
        "--run",
        type=int,
        dest="source_run_id",
        metavar="RUN_ID",
        help="Run ID to read cases from instead of a suite",
    )
    trc_parser.add_argument(
        "--output-dir",
        default=None,
        metavar="PATH",
        help="Directory to write generated YAML files (default: tests/cases/<suite_slug>)",
    )
    trc_parser.add_argument(
        "--shared-steps-file",
        default=None,
        metavar="PATH",
        help="Path for shared_steps.yaml (default: <output-dir>/shared_steps.yaml)",
    )
    trc_parser.add_argument(
        "--tag",
        default=None,
        metavar="TAG",
        help="Tag to add to every generated test (default: slugified suite name)",
    )
    trc_parser.add_argument(
        "--no-testrail",
        action="store_true",
        help="Only write YAML files locally; do NOT create a new TestRail suite",
    )
    trc_parser.add_argument(
        "--no-yaml",
        action="store_true",
        help="Only create the TestRail suite; do NOT write local YAML files",
    )
    trc_parser.add_argument(
        "--target-suite",
        type=int,
        default=None,
        metavar="SUITE_ID",
        help="Write Easy BDD cases into an existing suite instead of creating a new one",
    )
    trc_parser.add_argument(
        "--target-suite-name",
        default=None,
        metavar="NAME",
        help="Name for the new TestRail suite (default: 'EASY_BDD: <source name>')",
    )
    trc_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without creating any files or TestRail cases",
    )
    trc_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case progress output",
    )

    # MCP serve command
    mcp_parser = subparsers.add_parser(
        "mcp-serve",
        help="Start the Easy BDD MCP (Model Context Protocol) server",
    )
    mcp_parser.add_argument(
        "--sse",
        action="store_true",
        help="Use SSE (HTTP) transport instead of STDIO (default)",
    )
    mcp_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address for SSE transport (default: 0.0.0.0)",
    )
    mcp_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080)",
    )

    # TestRail list command
    trcr_parser = subparsers.add_parser(
        "testrail-create-run",
        help="Create a TestRail run from a suite, optionally filtered to specific sections",
    )
    trcr_parser.add_argument("project_id", type=int, help="TestRail project ID")
    trcr_parser.add_argument("suite_id", type=int, help="TestRail suite ID")
    trcr_parser.add_argument(
        "--name",
        default=None,
        help='Run name (default: "EASY_BDD: <suite name>")',
    )
    trcr_parser.add_argument(
        "--sections",
        nargs="+",
        metavar="SECTION",
        default=None,
        help=(
            "Section/subsection names to include (case-insensitive substring match). "
            "Omit to include all cases in the suite. "
            'Example: --sections "Functions" "Firmware Resiliency" "VPS Web UI" "VPS API"'
        ),
    )
    trcr_parser.add_argument(
        "--prefix",
        default=None,
        help='Run name prefix (default: "EASY_BDD: " or TESTRAIL_RUN_PREFIX env var)',
    )
    trcr_parser.add_argument(
        "--description",
        default="",
        help="Optional run description (supports JSON run-config syntax)",
    )
    trcr_parser.add_argument(
        "--milestone-id",
        type=int,
        default=None,
        help="Milestone ID to associate the run with",
    )
    trcr_parser.add_argument(
        "--given-section",
        metavar="SECTION",
        default=None,
        help=(
            "Name of the section containing 'Given:' cases (one per SKU/variant). "
            "When set, creates one run per Given: case found in that section. "
            "The Given: case is always included; --sections controls the rest of the cases. "
            'Example: --given-section "VPS" --sections "Functions" "Firmware Resiliency" "VPS Web UI" "VPS API"'
        ),
    )
    trcr_parser.add_argument(
        "--run-name-template",
        default=None,
        metavar="TEMPLATE",
        help=(
            'Python format string for per-Given run names. '
            'Available variables: {prefix}, {sku}, {product_category}. '
            'Default: "{prefix} {sku} Smoke Test"'
        ),
    )
    trcr_parser.add_argument(
        "--product-category",
        default="",
        help="Product category label substituted into --run-name-template as {product_category}",
    )
    trcr_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without actually creating it",
    )

    trl_parser = subparsers.add_parser(
        "testrail-list",
        help="List TestRail projects and active EASY_BDD: runs",
    )
    trl_parser.add_argument(
        "project_id",
        type=int,
        nargs="?",
        default=None,
        help="Show runs for a specific project (omit to list all projects)",
    )
    trl_parser.add_argument(
        "--prefix",
        default=None,
        help="Run name prefix to filter by (default: EASY_BDD:, or TESTRAIL_RUN_PREFIX env var)",
    )

    convert_parser.add_argument(
        "--output", help="Output file path (default: auto-generated)"
    )
    convert_parser.add_argument(
        "--format-type",
        choices=["playwright", "selenium", "cypress", "puppeteer", "katalon", "chrome-devtools", "auto"],
        default="auto",
        help="Input format type (default: auto-detect)",
    )

    # Selector audit command
    audit_parser = subparsers.add_parser(
        "selector-audit",
        help="Scan test YAML files for CSS/XPath selectors that could be role-based",
    )
    audit_parser.add_argument(
        "path",
        nargs="?",
        default="tests/cases",
        help="Directory to scan (default: tests/cases)",
    )
    audit_parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-upgrade selectors in-place (writes files)",
    )

    # Record and upload command
    record_parser = subparsers.add_parser(
        "record",
        help="Launch Playwright codegen, convert recording, and optionally upload to TestRail",
    )
    record_parser.add_argument(
        "url",
        nargs="?",
        default="",
        help="Starting URL for the browser recording",
    )
    record_parser.add_argument(
        "--name",
        help="Test name (default: derived from recorded actions)",
    )
    record_parser.add_argument(
        "--output",
        help="Output YAML path (default: tests/cases/<name>.yaml)",
    )
    record_parser.add_argument(
        "--testrail-section",
        metavar="SECTION_ID",
        type=int,
        help="TestRail section ID to upload the case to",
    )
    record_parser.add_argument(
        "--testrail-suite",
        metavar="SUITE_ID",
        type=int,
        help="TestRail suite ID — uploads to the first section in the suite (or creates one)",
    )
    record_parser.add_argument(
        "--testrail-project",
        metavar="PROJECT_ID",
        type=int,
        help="TestRail project ID (required with --testrail-suite)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "run":
            return run_tests(args)
        elif args.command == "generate":
            return generate_features(args)
        elif args.command == "convert":
            return convert_recording(args)
        elif args.command == "validate":
            return validate_tests(args)
        elif args.command == "docker-run":
            return docker_run(args)
        elif args.command == "edit-test":
            return edit_test(args)
        elif args.command == "testrail-run":
            return testrail_run(args)
        elif args.command == "testrail-list":
            return testrail_list(args)
        elif args.command == "testrail-create-run":
            return testrail_create_run(args)
        elif args.command == "testrail-convert":
            return testrail_convert(args)
        elif args.command == "mcp-serve":
            return mcp_serve(args)
        elif args.command == "selector-audit":
            return selector_audit(args)
        elif args.command == "record":
            return record_and_upload(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def convert_recording(args):
    """Convert UI recorder file to Easy BDD format."""
    from .core.recorder_converter import RecorderConverter

    try:
        converter = RecorderConverter()

        # Convert the recorder file
        yaml_content = converter.convert_file(
            args.input_file, format_type=args.format_type
        )

        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            input_path = Path(args.input_file)
            output_path = input_path.parent / f"{input_path.stem}_converted.yaml"

        # Write converted file
        with open(output_path, "w") as f:
            f.write(yaml_content)

        print(f"Successfully converted {args.input_file} to {output_path}")
        return 0

    except Exception as e:
        print(f"Error converting file: {e}", file=sys.stderr)
        return 1


def selector_audit(args) -> int:
    """Scan test YAML files for CSS/XPath selectors that could be role-based."""
    import yaml
    from .core.recorder_converter import RecorderConverter

    search_dir = Path(args.path)
    if not search_dir.exists():
        print(f"Directory not found: {search_dir}", file=sys.stderr)
        return 1

    yaml_files = sorted(search_dir.rglob("*.yaml")) + sorted(search_dir.rglob("*.yml"))

    SELECTOR_FIELDS = {"selector", "field"}
    XPATH_PATTERNS = [r"^//", r"^xpath=", r"\[contains\(", r"following::", r"preceding::"]
    CSS_PATTERNS = [r"^#\w", r"^\.\w", r"^\w[\w-]*\[", r"^\w[\w-]*#\w", r"^input\b", r"^button\b", r"^a\b", r"^select\b", r"^textarea\b"]

    findings = []

    for yaml_file in yaml_files:
        try:
            with open(yaml_file) as f:
                content = yaml.safe_load(f)
        except Exception:
            continue

        if not isinstance(content, dict):
            continue

        all_steps = (
            content.get("steps", [])
            + content.get("setup", [])
            + content.get("cleanup", [])
        )

        for i, step in enumerate(all_steps):
            if not isinstance(step, dict):
                continue
            for field in SELECTOR_FIELDS:
                val = step.get(field)
                if not val or not isinstance(val, str):
                    continue
                if step.get("role") or step.get("label") or step.get("text"):
                    continue
                is_xpath = any(re.search(p, val) for p in XPATH_PATTERNS)
                is_css = any(re.search(p, val) for p in CSS_PATTERNS)
                if is_xpath or is_css:
                    findings.append({
                        "file": yaml_file,
                        "step_index": i,
                        "field": field,
                        "selector": val,
                        "kind": "xpath" if is_xpath else "css",
                        "step": step,
                    })

    if not findings:
        print("No fragile CSS/XPath selectors found.")
        return 0

    converter = RecorderConverter()

    if args.fix:
        # Group by file and rewrite
        from collections import defaultdict
        import yaml as yaml_mod

        by_file = defaultdict(list)
        for f in findings:
            by_file[f["file"]].append(f)

        fixed_total = 0
        for yaml_file, file_findings in by_file.items():
            with open(yaml_file) as f:
                content = yaml_mod.safe_load(f)

            sections = ["steps", "setup", "cleanup"]
            fixed_in_file = 0
            for section in sections:
                steps = content.get(section, [])
                for i, step in enumerate(steps):
                    upgraded = converter.upgrade_step_to_role_selector(step)
                    if upgraded is not step and upgraded != step:
                        steps[i] = upgraded
                        fixed_in_file += 1

            if fixed_in_file:
                with open(yaml_file, "w") as f:
                    yaml_mod.dump(content, f, default_flow_style=False, sort_keys=False)
                print(f"  Fixed {fixed_in_file} selector(s) in {yaml_file}")
                fixed_total += fixed_in_file

        print(f"\nUpgraded {fixed_total} selector(s) across {len(by_file)} file(s).")
        return 0

    # Report only
    print(f"\nFound {len(findings)} CSS/XPath selector(s) that could be role-based:\n")
    current_file = None
    for f in findings:
        if f["file"] != current_file:
            print(f"  {f['file']}")
            current_file = f["file"]
        upgraded = converter.upgrade_step_to_role_selector(f["step"])
        suggestion = ""
        if upgraded.get("role"):
            suggestion = f"  → role: {upgraded['role']} name: {upgraded.get('name', '?')}"
        elif upgraded.get("label"):
            suggestion = f"  → label: {upgraded['label']}"
        print(f"    Step {f['step_index'] + 1} [{f['kind']}] {f['field']}: {f['selector']}{suggestion}")

    print(f"\nRun with --fix to auto-upgrade selectors in-place.")
    return 0


def record_and_upload(args) -> int:
    """Launch Playwright codegen, convert recording to YAML, and optionally upload to TestRail."""
    import subprocess
    import tempfile
    import yaml

    from .core.recorder_converter import RecorderConverter

    # 1. Launch playwright codegen into a temp file
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as tmp:
        output_file = tmp.name

    cmd = ["playwright", "codegen", "--output", output_file, "--target", "python-pytest"]
    if args.url:
        cmd.append(args.url)

    print("\n[Record] Launching Playwright codegen...")
    print("  Record your browser steps, then close the browser window to continue.\n")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Recording exited with error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(
            "playwright command not found.\n"
            "Install with: pip install playwright && playwright install",
            file=sys.stderr,
        )
        return 1

    # 2. Read and convert
    try:
        with open(output_file) as f:
            code = f.read()
    except Exception as e:
        print(f"Could not read recording: {e}", file=sys.stderr)
        return 1

    if not code.strip():
        print("No steps were recorded.")
        return 1

    converter = RecorderConverter()
    test_data = converter.convert_playwright_native_code(code)
    if args.name:
        test_data["name"] = args.name

    # 3. Preview
    steps = test_data.get("steps", [])
    print(f"\n[Preview] '{test_data['name']}' — {len(steps)} step(s):\n")
    for i, step in enumerate(steps, 1):
        action = step.get("action", "?")
        parts = []
        for k in ("url", "role", "name", "label", "text", "selector", "field", "value", "key"):
            if step.get(k):
                parts.append(f"{k}={step[k]!r}")
        print(f"  {i:2}. {action}  {', '.join(parts)}")

    if not steps:
        print("No recognizable steps found in the recording.")
        return 1

    # 4. Save locally (always)
    output_path = Path(
        args.output
        or f"tests/cases/{re.sub(r'[^a-z0-9]+', '_', test_data['name'].lower()).strip('_')}.yaml"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(test_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"\n[Saved] {output_path}")

    section_id = getattr(args, "testrail_section", None)
    suite_id = getattr(args, "testrail_suite", None)
    project_id = args.testrail_project

    if not section_id and not suite_id and not project_id:
        print("\nTip: use --testrail-project <id>, --testrail-suite <id>, or --testrail-section <id> to upload as a TestRail case.")
        return 0

    # 5. Upload to TestRail
    from .services.testrail_service import TestRailService, TestRailError

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        print("Set TESTRAIL_URL, TESTRAIL_USERNAME, and TESTRAIL_API_KEY in .env", file=sys.stderr)
        return 1

    WEB_UI_SECTION = "Web UI Tests"

    def _get_or_create_section(proj_id, s_id):
        """Find the 'Web UI Tests' section in a suite, or create it."""
        try:
            sections = tr.get_sections(proj_id, suite_id=s_id)
        except Exception as e:
            print(f"Could not fetch sections for suite S{s_id}: {e}", file=sys.stderr)
            return None
        match = next((s for s in sections if s["name"] == WEB_UI_SECTION), None)
        if match:
            print(f"[TestRail] Using existing section '{WEB_UI_SECTION}' (ID {match['id']}) in suite S{s_id}")
            return match["id"]
        try:
            section = tr.add_section(proj_id, suite_id=s_id, name=WEB_UI_SECTION)
            print(f"[TestRail] Created section '{WEB_UI_SECTION}' (ID {section['id']}) in suite S{s_id}")
            return section["id"]
        except Exception as e:
            print(f"Could not create section in suite S{s_id}: {e}", file=sys.stderr)
            return None

    if section_id:
        # Explicit section — use it directly
        pass
    elif suite_id:
        # Suite given — find or create "Web UI Tests" subsection
        if not project_id:
            print("--testrail-project PROJECT_ID is required when using --testrail-suite", file=sys.stderr)
            return 1
        section_id = _get_or_create_section(project_id, suite_id)
        if section_id is None:
            return 1
    else:
        # Project only — create a new suite named after the test, then "Web UI Tests" inside it
        if not project_id:
            print("--testrail-project PROJECT_ID is required", file=sys.stderr)
            return 1
        suite_name = test_data["name"]
        try:
            new_suite = tr.add_suite(project_id, name=suite_name)
            suite_id = new_suite["id"]
            print(f"[TestRail] Created suite '{suite_name}' (S{suite_id}) in project {project_id}")
        except Exception as e:
            print(f"Could not create suite in project {project_id}: {e}", file=sys.stderr)
            return 1
        section_id = _get_or_create_section(project_id, suite_id)
        if section_id is None:
            return 1

    steps_yaml = yaml.dump(steps, default_flow_style=False, allow_unicode=True)
    preconditions = f"# Auto-recorded via easy_bdd record\n\n```yaml\n{steps_yaml}```"

    try:
        case = tr.add_case(
            section_id,
            title=test_data["name"],
            custom_preconds=preconditions,
            custom_steps=f"tag: browser\nfile: {output_path}",
            type_id=1,
        )
        print(f"[TestRail] Case created: C{case['id']} — {case['title']}")
    except Exception as e:
        print(f"TestRail upload failed: {e}", file=sys.stderr)
        return 1

    return 0


def export_test_results(result, output_path):
    """Export test results to various formats based on file extension"""
    import json
    import csv
    import xml.etree.ElementTree as ET
    from datetime import datetime

    output_path = Path(output_path)
    extension = output_path.suffix.lower()

    # Prepare result data
    result_data = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tests": result.total_tests,
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "success_rate": (
                round((result.passed / result.total_tests) * 100, 2)
                if result.total_tests > 0
                else 0
            ),
            "execution_time_seconds": round(result.execution_time, 2),
        },
        "status": "PASSED" if result.success else "FAILED",
        "tests": result.test_details if result.test_details else [],
    }

    try:
        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if extension == ".json":
            return export_to_json(result_data, output_path)
        elif extension == ".csv":
            return export_to_csv(result_data, output_path)
        elif extension == ".xml":
            return export_to_xml(result_data, output_path)
        else:
            # Default to JSON if no recognized extension
            output_path = output_path.with_suffix(".json")
            return export_to_json(result_data, output_path)

    except Exception as e:
        print(f"Export error: {e}", file=sys.stderr)
        return False


def export_to_json(result_data, output_path):
    """Export results to JSON format"""
    import json

    with open(output_path, "w") as f:
        json.dump(result_data, f, indent=2)
    return True


def export_to_csv(result_data, output_path):
    """Export results to CSV format"""
    import csv

    summary = result_data["summary"]

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Write summary header
        writer.writerow(["SUMMARY"])
        writer.writerow(["Metric", "Value"])

        # Write summary data
        writer.writerow(["Timestamp", result_data["timestamp"]])
        writer.writerow(["Status", result_data["status"]])
        writer.writerow(["Total Tests", summary["total_tests"]])
        writer.writerow(["Passed", summary["passed"]])
        writer.writerow(["Failed", summary["failed"]])
        writer.writerow(["Skipped", summary["skipped"]])
        writer.writerow(["Success Rate %", summary["success_rate"]])
        writer.writerow(["Execution Time (s)", summary["execution_time_seconds"]])

        # Write test details if available
        if result_data.get("tests"):
            writer.writerow([])  # Empty row
            writer.writerow(["INDIVIDUAL TEST RESULTS"])
            writer.writerow(
                [
                    "Test Name",
                    "Status",
                    "Description",
                    "Execution Time (s)",
                    "Tags",
                    "Error",
                ]
            )

            for test in result_data["tests"]:
                writer.writerow(
                    [
                        test.get("name", ""),
                        test.get("status", ""),
                        test.get("description", ""),
                        test.get("execution_time", ""),
                        ", ".join(test.get("tags", [])),
                        test.get("error", ""),
                    ]
                )

    return True


def export_to_xml(result_data, output_path):
    """Export results to XML format"""
    import xml.etree.ElementTree as ET

    # Create root element
    root = ET.Element("test_results")
    root.set("timestamp", result_data["timestamp"])
    root.set("status", result_data["status"])

    # Add summary element
    summary_elem = ET.SubElement(root, "summary")

    summary = result_data["summary"]
    for key, value in summary.items():
        elem = ET.SubElement(summary_elem, key.replace("_", "-"))
        elem.text = str(value)

    # Add individual tests if available
    if result_data.get("tests"):
        tests_elem = ET.SubElement(root, "tests")

        for test in result_data["tests"]:
            test_elem = ET.SubElement(tests_elem, "test")
            test_elem.set("name", test.get("name", ""))
            test_elem.set("status", test.get("status", ""))

            # Add test details
            desc_elem = ET.SubElement(test_elem, "description")
            desc_elem.text = test.get("description", "")

            time_elem = ET.SubElement(test_elem, "execution-time")
            time_elem.text = str(test.get("execution_time", ""))

            if test.get("tags"):
                tags_elem = ET.SubElement(test_elem, "tags")
                tags_elem.text = ", ".join(test.get("tags", []))

            if test.get("error"):
                error_elem = ET.SubElement(test_elem, "error")
                error_elem.text = test.get("error", "")

    # Write to file
    tree = ET.ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    return True


def run_tests(args) -> int:
    """Run tests with the given arguments"""
    config = GlobalConfigManager()

    # TODO: Implement browser configuration overrides for GlobalConfigManager
    # Override browser configuration from CLI arguments
    # if hasattr(args, 'headless') and args.headless:
    #     config.browser.headless = True

    # if hasattr(args, 'headed') and args.headed:
    #     config.browser.headless = False

    # if hasattr(args, 'ignore_https') and args.ignore_https:
    #     # Add dynamic attributes for HTTPS handling
    #     config.browser.ignore_https_errors = True
    #     config.browser.ignore_certificate_errors = True

    # if hasattr(args, 'browser') and args.browser:
    #     config.browser.default = args.browser

    runner = TestRunner(config)

    # Parse tags
    tags = []
    if args.tags:
        tags = [tag.strip() for tag in args.tags.split(",")]

    # Run tests
    record_video = getattr(args, "record_video", False)
    result = runner.run(test_path=Path(args.path), tags=tags, record_video=record_video)

    # Export results if requested
    if args.export_results:
        export_success = export_test_results(result, args.export_results)
        if export_success:
            print(f"Test results exported to: {args.export_results}")
        else:
            print(
                f"Warning: Failed to export results to {args.export_results}",
                file=sys.stderr,
            )

    return 0 if result.success else 1


def docker_run(args) -> int:
    """Build Docker image, run test in container, then cleanup"""
    import subprocess
    import shutil
    import os
    from pathlib import Path

    # Check if Docker is available
    if not shutil.which("docker"):
        print("Error: Docker is not installed or not in PATH", file=sys.stderr)
        print("\nTo install Docker:", file=sys.stderr)
        print("  macOS: Download Docker Desktop from https://www.docker.com/products/docker-desktop", file=sys.stderr)
        print("  Linux: sudo apt-get install docker.io  (or use your package manager)", file=sys.stderr)
        print("  Windows: Download Docker Desktop from https://www.docker.com/products/docker-desktop", file=sys.stderr)
        print("\nAfter installation, make sure Docker Desktop is running and try again.", file=sys.stderr)
        return 1
    
    # Verify Docker daemon is running
    try:
        check_daemon = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        if check_daemon.returncode != 0:
            print("Error: Docker daemon is not running", file=sys.stderr)
            print("Please start Docker Desktop and try again.", file=sys.stderr)
            return 1
    except subprocess.TimeoutExpired:
        print("Error: Docker daemon is not responding", file=sys.stderr)
        print("Please start Docker Desktop and try again.", file=sys.stderr)
        return 1
    except Exception:
        # If docker info fails, continue anyway - docker run will fail with a better error
        pass

    # Get project root (parent of easy_bdd package)
    project_root = Path(__file__).parent.parent.parent
    test_path = Path(args.test_path)
    
    # Resolve test path relative to project root
    if not test_path.is_absolute():
        test_path = project_root / test_path
    
    if not test_path.exists():
        print(f"Error: Test file '{test_path}' does not exist", file=sys.stderr)
        return 1

    image_name = args.image_name
    container_name = f"easy-bdd-{os.urandom(4).hex()}"
    
    try:
        # Step 1: Build Docker image (unless --no-build is specified)
        if not args.no_build:
            print(f"Building Docker image '{image_name}'...")
            build_cmd = [
                "docker", "build",
                "-t", image_name,
                "-f", str(project_root / "Dockerfile"),
                str(project_root)
            ]
            
            result = subprocess.run(build_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error building Docker image: {result.stderr}", file=sys.stderr)
                return 1
            print("✓ Docker image built successfully")
        else:
            print(f"Using existing Docker image '{image_name}'...")
            # Verify image exists
            check_cmd = ["docker", "image", "inspect", image_name]
            result = subprocess.run(check_cmd, capture_output=True)
            if result.returncode != 0:
                print(f"Error: Docker image '{image_name}' not found", file=sys.stderr)
                return 1

        # Step 2: Prepare volume mounts
        # Mount tests directory
        tests_dir = project_root / "tests"
        reports_dir = project_root / "reports"
        reports_dir.mkdir(exist_ok=True)
        
        # Get relative test path for container
        test_path_in_container = test_path.relative_to(project_root)
        
        # Build docker run command
        run_cmd = [
            "docker", "run",
            "--name", container_name,
            "--rm" if not args.keep_container else "",
            "-v", f"{tests_dir}:/app/tests:ro",  # Mount tests as read-only
            "-v", f"{reports_dir}:/app/reports",  # Mount reports for output
        ]
        
        # Remove empty strings from list
        run_cmd = [arg for arg in run_cmd if arg]
        
        # Add environment variables
        if args.headless:
            run_cmd.extend(["-e", "HEADLESS=true"])
        
        # Build the test execution command inside container
        container_test_cmd = ["python", "-m", "easy_bdd", "run", str(test_path_in_container)]
        
        if args.headless:
            container_test_cmd.append("--headless")
        
        if args.tags:
            container_test_cmd.extend(["--tags", args.tags])
        
        if args.export_results:
            container_test_cmd.extend(["--export-results", args.export_results])
        
        # Add the image and command
        run_cmd.append(image_name)
        run_cmd.extend(container_test_cmd)
        
        # Step 3: Run the container
        print(f"\nRunning test '{test_path_in_container}' in Docker container...")
        print(f"Container name: {container_name}")
        print(f"Command: {' '.join(container_test_cmd)}\n")
        
        result = subprocess.run(run_cmd, cwd=project_root)
        exit_code = result.returncode
        
        # Step 4: Cleanup (if not keeping container)
        if not args.keep_container:
            # Container is auto-removed with --rm flag, but clean up if it still exists
            cleanup_cmd = ["docker", "rm", "-f", container_name]
            subprocess.run(cleanup_cmd, capture_output=True)  # Ignore errors
        else:
            print(f"\nContainer '{container_name}' kept running. Remove manually with:")
            print(f"  docker rm -f {container_name}")
        
        if exit_code == 0:
            print("\n✓ Test execution completed successfully")
        else:
            print(f"\n✗ Test execution failed with exit code {exit_code}")
        
        return exit_code
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Cleaning up...")
        # Force remove container
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        # Try to cleanup on error
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        return 1


def generate_features(args) -> int:
    """Generate Gherkin features from YAML files"""
    generator = GherkinGenerator()

    input_path = Path(args.path)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Path '{input_path}' does not exist", file=sys.stderr)
        return 1

    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate features
    if input_path.is_file():
        yaml_files = [input_path]
    else:
        yaml_files = list(input_path.glob("**/*.yaml")) + list(
            input_path.glob("**/*.yml")
        )

    if not yaml_files:
        print(f"No YAML files found in '{input_path}'", file=sys.stderr)
        return 1

    generated_count = 0
    for yaml_file in yaml_files:
        try:
            feature_content = generator.yaml_to_gherkin(yaml_file)

            # Create output file path
            relative_path = yaml_file.relative_to(
                input_path.parent if input_path.is_file() else input_path
            )
            output_file = output_path / relative_path.with_suffix(".feature")

            # Create subdirectories if needed
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Write feature file
            output_file.write_text(feature_content, encoding="utf-8")
            print(f"Generated: {output_file}")
            generated_count += 1

        except Exception as e:
            print(f"Error processing '{yaml_file}': {e}", file=sys.stderr)

    print(f"\\nGenerated {generated_count} feature files in '{output_path}'")
    return 0


def edit_test(args) -> int:
    """Open a test file in the default editor"""
    from pathlib import Path
    from easy_bdd.core.parser import YAMLParser
    import platform
    import subprocess
    
    test_path = Path(args.test_path)
    parser = YAMLParser()
    
    if not test_path.exists():
        print(f"❌ Test file not found: {test_path}")
        print(f"   Absolute path: {test_path.absolute()}")
        return 1
    
    if not test_path.is_file():
        print(f"❌ Path is not a file: {test_path}")
        return 1
    
    file_path_str = str(test_path.absolute())
    system = platform.system().lower()
    
    print(f"📁 Opening test file: {file_path_str}")
    
    try:
        if system == "darwin":  # macOS
            subprocess.run(["open", file_path_str], check=True)
        elif system == "linux":
            # Try VS Code first, then default editor
            try:
                subprocess.run(["code", file_path_str], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                subprocess.run(["xdg-open", file_path_str], check=True)
        elif system == "windows":
            subprocess.run(["start", file_path_str], check=True, shell=True)
        else:
            print(f"⚠️  Unknown platform: {system}")
            print(f"   Please open manually: {file_path_str}")
            return 1
        
        print(f"✅ Opened {test_path.name} in editor")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to open file: {e}")
        print(f"   Please open manually: {file_path_str}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def edit_test(args) -> int:
    """Open a test file in the default editor"""
    from pathlib import Path
    import platform
    import subprocess
    
    test_path = Path(args.test_path)
    
    if not test_path.exists():
        print(f"❌ Test file not found: {test_path}")
        print(f"   Absolute path: {test_path.absolute()}")
        return 1
    
    if not test_path.is_file():
        print(f"❌ Path is not a file: {test_path}")
        return 1
    
    file_path_str = str(test_path.absolute())
    system = platform.system().lower()
    
    print(f"📁 Opening test file: {file_path_str}")
    
    try:
        if system == "darwin":  # macOS
            subprocess.run(["open", file_path_str], check=True)
        elif system == "linux":
            # Try VS Code first, then default editor
            try:
                subprocess.run(["code", file_path_str], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                subprocess.run(["xdg-open", file_path_str], check=True)
        elif system == "windows":
            subprocess.run(["start", file_path_str], check=True, shell=True)
        else:
            print(f"⚠️  Unknown platform: {system}")
            print(f"   Please open manually: {file_path_str}")
            return 1
        
        print(f"✅ Opened {test_path.name} in editor")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to open file: {e}")
        print(f"   Please open manually: {file_path_str}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def _validate_testrail(args) -> int:
    """Validate TestRail cases fetched via the API."""
    from .core.validator import EasyBDDValidator
    from .services.testrail_service import TestRailService, TestRailError

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        print("Set TESTRAIL_URL, TESTRAIL_USERNAME, and TESTRAIL_API_KEY in .env.", file=sys.stderr)
        return 1

    cases = []
    source_desc = ""

    try:
        if getattr(args, "testrail_case", None):
            case = tr.get_case(args.testrail_case)
            cases = [case]
            source_desc = f"case C{args.testrail_case}"

        elif getattr(args, "testrail_suite", None):
            if not getattr(args, "project", None):
                print("Error: --project PROJECT_ID is required with --testrail-suite", file=sys.stderr)
                return 1
            cases = tr.get_cases(args.project, suite_id=args.testrail_suite)
            source_desc = f"suite S{args.testrail_suite} (project {args.project})"

        elif getattr(args, "testrail_run", None):
            # get_tests returns run instances; fetch their full case data
            tests = tr.get_tests(args.testrail_run)
            case_ids = list({t.get("case_id") for t in tests if t.get("case_id")})
            print(f"Fetching {len(case_ids)} case(s) from run R{args.testrail_run}...")
            for cid in case_ids:
                try:
                    cases.append(tr.get_case(cid))
                except Exception as e:
                    print(f"  Warning: could not fetch case C{cid}: {e}", file=sys.stderr)
            source_desc = f"run R{args.testrail_run}"

    except TestRailError as e:
        print(f"TestRail API error: {e}", file=sys.stderr)
        return 1

    if not cases:
        print(f"No cases found for {source_desc}.")
        return 0

    # Collect Shared: case names from the fetched set to validate references
    from .core.testrail_runner import _classify, _strip_prefix
    shared_step_names: set = set()
    for c in cases:
        title = c.get("title", "")
        if _classify(title) == "keyword":
            name = re.sub(r"[^A-Za-z0-9_]+", "_", _strip_prefix(title)).strip("_")
            shared_step_names.add(name)

    validator = EasyBDDValidator()
    print(f"Validating {len(cases)} case(s) from {source_desc}...\n")

    results = validator.validate_testrail_cases(cases, shared_steps_from_tr=shared_step_names)
    report, total_errors, total_warnings = EasyBDDValidator.format_testrail_report(results)
    print(report)

    print("\n" + "=" * 60)
    print("TESTRAIL VALIDATION SUMMARY")
    print("=" * 60)
    print(f"  Cases checked : {len(results)}")
    print(f"  Total errors  : {total_errors}")
    print(f"  Total warnings: {total_warnings}")

    if total_errors > 0:
        print("\n❌ Validation FAILED")
        return 1
    if total_warnings > 0 and getattr(args, "strict", False):
        print("\n⚠️  Validation FAILED (strict mode)")
        return 1
    print("\n✅ Validation PASSED")
    return 0


def validate_tests(args) -> int:
    """Validate test files or a YAML step snippet."""
    from .core.validator import EasyBDDValidator

    # Route TestRail requests to the dedicated handler
    if (
        getattr(args, "testrail_case", None)
        or getattr(args, "testrail_suite", None)
        or getattr(args, "testrail_run", None)
    ):
        return _validate_testrail(args)

    validator = EasyBDDValidator()
    shared_steps_dir = (
        Path(args.shared_steps_dir) if getattr(args, "shared_steps_dir", None) else None
    )

    # --- Snippet mode ---
    snippet_text = None
    snippet_source = None
    if getattr(args, "stdin", False):
        snippet_text = sys.stdin.read()
        snippet_source = "<stdin>"
    elif getattr(args, "snippet", None):
        snippet_text = args.snippet
        snippet_source = "<--snippet>"
    elif getattr(args, "snippet_file", None):
        sf = Path(args.snippet_file)
        if not sf.exists():
            print(f"Error: snippet file '{sf}' does not exist", file=sys.stderr)
            return 1
        snippet_text = sf.read_text(encoding="utf-8")
        snippet_source = str(sf)
        if shared_steps_dir is None:
            shared_steps_dir = sf.parent

    if snippet_text is not None:
        print(f"Validating snippet from {snippet_source}...\n")
        issues = validator.validate_snippet(snippet_text, shared_steps_dir)
        print(EasyBDDValidator.format_report(issues))
        errors = [i for i in issues if i.severity == "ERROR"]
        warnings = [i for i in issues if i.severity == "WARNING"]
        if errors:
            return 1
        if warnings and getattr(args, "strict", False):
            return 1
        return 0

    # --- File / directory mode ---
    raw_path = getattr(args, "path", None) or "tests/cases/"
    input_path = Path(raw_path)

    if not input_path.exists():
        print(f"Error: Path '{input_path}' does not exist", file=sys.stderr)
        return 1

    if input_path.is_file():
        test_files = [input_path]
    else:
        test_files = sorted(
            list(input_path.glob("**/*.yaml")) + list(input_path.glob("**/*.yml"))
        )

    if not test_files:
        print(f"No YAML files found in '{input_path}'", file=sys.stderr)
        return 1

    print(f"Validating {len(test_files)} file(s)...\n")

    total_errors = 0
    total_warnings = 0
    files_with_issues = 0

    for test_file in test_files:
        try:
            issues = validator.validate_file(test_file, shared_steps_dir)
            errors = [i for i in issues if i.severity == "ERROR"]
            warnings = [i for i in issues if i.severity == "WARNING"]
            file_ok = len(errors) == 0 and (
                not getattr(args, "strict", False) or len(warnings) == 0
            )

            if not file_ok or issues:
                status = "❌" if errors else "⚠️ "
                print(f"{status} {test_file}")
                print(EasyBDDValidator.format_report(issues))
                print()
                if not file_ok:
                    files_with_issues += 1
            else:
                print(f"✅ {test_file}")

            total_errors += len(errors)
            total_warnings += len(warnings)

        except Exception as e:
            files_with_issues += 1
            total_errors += 1
            print(f"❌ {test_file}")
            print(f"  [ERROR] Unexpected validation failure: {e}\n")

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"  Files checked : {len(test_files)}")
    print(f"  Files OK      : {len(test_files) - files_with_issues}")
    print(f"  Files with issues: {files_with_issues}")
    print(f"  Total errors  : {total_errors}")
    print(f"  Total warnings: {total_warnings}")

    if total_errors > 0:
        print("\n❌ Validation FAILED")
        return 1
    if total_warnings > 0 and getattr(args, "strict", False):
        print("\n⚠️  Validation FAILED (strict mode — warnings treated as errors)")
        return 1
    print("\n✅ Validation PASSED")
    return 0


def testrail_convert(args) -> int:
    """Convert a mybdd-format TestRail suite to Easy BDD YAML test files."""
    from .services.testrail_service import TestRailService, TestRailError
    from .core.suite_converter import BddSuiteConverter

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        print("Set TESTRAIL_URL, TESTRAIL_USERNAME, and TESTRAIL_API_KEY in your .env file.",
              file=sys.stderr)
        return 1

    # Resolve output directory
    output_dir: Path = None
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        # Auto: tests/cases/<suite_slug>/
        if args.source_suite_id:
            try:
                suite_info = tr.get_suite(args.source_suite_id)
                slug = re.sub(r"[^A-Za-z0-9_\-]", "_", suite_info.get("name", "")).lower().strip("_")
            except Exception:
                slug = f"suite_{args.source_suite_id}"
        else:
            slug = f"run_{args.source_run_id}"
        output_dir = Path("tests") / "cases" / slug

    shared_path = Path(args.shared_steps_file) if args.shared_steps_file else None

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    src_desc = f"suite {args.source_suite_id}" if args.source_suite_id else f"run {args.source_run_id}"
    print(f"\n[Convert] {mode} — {src_desc} → {output_dir}")
    print()

    create_tr = not args.no_testrail
    converter = BddSuiteConverter(tr)
    result = converter.convert(
        project_id=args.project_id,
        source_suite_id=args.source_suite_id,
        source_run_id=args.source_run_id,
        output_dir=output_dir,
        shared_steps_path=shared_path,
        suite_tag=args.tag,
        write_yaml=not args.no_yaml,
        create_testrail_suite=create_tr,
        target_suite_id=args.target_suite,
        target_suite_name=args.target_suite_name,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    result.print_summary()
    return 1 if result.errors > 0 else 0


def testrail_list(args) -> int:
    """List TestRail projects or active EASY_BDD: runs for a project."""
    from .services.testrail_service import TestRailService, TestRailError

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        return 1

    prefix = args.prefix or os.getenv("TESTRAIL_RUN_PREFIX", "EASY_BDD:")

    if args.project_id is None:
        # List all projects
        try:
            projects = tr.get_projects()
        except Exception as e:
            print(f"Error fetching projects: {e}", file=sys.stderr)
            return 1
        if not projects:
            print("No TestRail projects found.")
            return 0
        print(f"\n{'ID':<8} {'Name'}")
        print("-" * 50)
        for p in projects:
            print(f"{p['id']:<8} {p['name']}")
        print(f"\nUse 'easy_bdd testrail-list <project_id>' to see active runs.")
    else:
        # List runs for a specific project
        import time
        created_after = int(time.time()) - 30 * 86400
        try:
            runs = tr.get_runs(args.project_id, created_after=created_after)
        except Exception as e:
            print(f"Error fetching runs: {e}", file=sys.stderr)
            return 1

        matching = [r for r in runs if r.get("name", "").startswith(prefix)]
        all_runs = runs

        print(f"\nProject {args.project_id} — runs matching '{prefix}' (last 30 days):\n")
        if not matching:
            print(f"  No runs with prefix '{prefix}' found.")
            print(f"\nAll runs in project ({len(all_runs)} total):")
            for r in all_runs[:10]:
                untested = r.get("untested_count", 0)
                retest = r.get("retest_count", 0)
                print(f"  [{r['id']}] {r['name']}  (untested={untested} retest={retest})")
        else:
            print(f"{'ID':<8} {'Untested':<10} {'Retest':<8} {'Name'}")
            print("-" * 60)
            for r in matching:
                untested = r.get("untested_count", 0)
                retest = r.get("retest_count", 0)
                print(f"{r['id']:<8} {untested:<10} {retest:<8} {r['name']}")
        print()

    return 0


def testrail_create_run(args) -> int:
    """Create TestRail run(s) from a suite filtered to named sections.

    Two modes:
      - Default: one run for the whole suite (or --sections subset).
      - --given-section MODE: find Given: cases in a section, create one
        run per Given: case (one per SKU/variant).
    """
    from .services.testrail_service import TestRailService, TestRailError

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        return 1

    prefix = args.prefix or os.getenv("TESTRAIL_RUN_PREFIX", "EASY_BDD:").rstrip()

    try:
        suite = tr.get_suite(args.suite_id)
    except Exception as e:
        print(f"Error fetching suite {args.suite_id}: {e}", file=sys.stderr)
        return 1
    suite_name = suite.get("name", f"Suite {args.suite_id}")

    try:
        all_sections = tr.get_sections(args.project_id, suite_id=args.suite_id)
    except Exception as e:
        print(f"Error fetching sections: {e}", file=sys.stderr)
        return 1

    try:
        all_cases = tr.get_cases(args.project_id, suite_id=args.suite_id)
    except Exception as e:
        print(f"Error fetching cases: {e}", file=sys.stderr)
        return 1

    section_by_id = {s["id"]: s for s in all_sections}
    testrail_base = os.getenv("TESTRAIL_URL", "").rstrip("/")

    def _resolve_section_ids(labels):
        """Return set of section IDs (and all their descendants) matching labels."""
        matched = set()
        for label in labels:
            ll = label.lower()
            for s in all_sections:
                if ll == s["name"].lower() or ll in s["name"].lower():
                    matched.add(s["id"])
        # Expand to descendants
        grew = True
        while grew:
            grew = False
            for s in all_sections:
                if s.get("parent_id") in matched and s["id"] not in matched:
                    matched.add(s["id"])
                    grew = True
        return matched

    def _create_one_run(run_name, case_ids, description=""):
        payload = {
            "name": run_name,
            "suite_id": args.suite_id,
            "case_ids": list(dict.fromkeys(case_ids)),  # dedupe, preserve order
            "include_all": False,
        }
        if description:
            payload["description"] = description
        if args.milestone_id:
            payload["milestone_id"] = args.milestone_id
        run = tr.add_run(args.project_id, **payload)
        run_url = f"{testrail_base}/index.php?/runs/view/{run['id']}"
        print(f"  ✅ [{run['id']}] {run['name']}  ({len(payload['case_ids'])} cases)")
        print(f"     {run_url}")
        return run

    # ── MODE: --given-section ───────────────────────────────────────────────
    if args.given_section:
        given_section_label = args.given_section.lower()
        given_section_ids = {
            s["id"] for s in all_sections
            if given_section_label == s["name"].lower() or given_section_label in s["name"].lower()
        }
        if not given_section_ids:
            print(f"Given section '{args.given_section}' not found.", file=sys.stderr)
            print(f"Available: {', '.join(s['name'] for s in all_sections)}", file=sys.stderr)
            return 1

        given_cases = [
            c for c in all_cases
            if c.get("section_id") in given_section_ids
            and c.get("title", "").startswith("Given:")
        ]
        if not given_cases:
            print(f"No 'Given:' cases found in section '{args.given_section}'.")
            return 0

        print(f"\nFound {len(given_cases)} Given: case(s) in '{args.given_section}':")
        for gc in given_cases:
            sku = gc["title"].replace("Given:", "").strip()
            print(f"  → {sku}")

        # Resolve the shared sections (Functions, Firmware Resiliency, etc.)
        shared_section_ids = _resolve_section_ids(args.sections) if args.sections else set()
        shared_case_ids = [
            c["id"] for c in all_cases
            if c.get("section_id") in shared_section_ids
            and not c.get("title", "").startswith("Given:")
        ]

        name_template = (
            args.run_name_template or "{prefix} {sku} Smoke Test"
        )
        product_category = getattr(args, "product_category", "") or ""

        if args.dry_run:
            print("\n[dry-run] Would create:")
            for gc in given_cases:
                sku = gc["title"].replace("Given:", "").strip()
                run_name = name_template.format(
                    prefix=prefix, sku=sku, product_category=product_category
                )
                total = 1 + len(shared_case_ids)
                print(f"  Run: '{run_name}'  ({total} cases: 1 Given + {len(shared_case_ids)} shared)")
            return 0

        print()
        created = 0
        for gc in given_cases:
            sku = gc["title"].replace("Given:", "").strip()
            run_name = name_template.format(
                prefix=prefix, sku=sku, product_category=product_category
            )
            case_ids = [gc["id"]] + shared_case_ids
            try:
                _create_one_run(run_name, case_ids, description=args.description)
                created += 1
            except Exception as e:
                print(f"  ❌ Failed to create run for '{sku}': {e}", file=sys.stderr)

        print(f"\nCreated {created}/{len(given_cases)} run(s).")
        return 0 if created == len(given_cases) else 1

    # ── MODE: single run ────────────────────────────────────────────────────
    run_name = args.name or f"{prefix} {suite_name}"

    if args.sections:
        matched_ids = _resolve_section_ids(args.sections)
        if not matched_ids:
            print("No matching sections found — aborting.", file=sys.stderr)
            return 1
        matched_names = [s["name"] for s in all_sections if s["id"] in matched_ids]
        print(f"Matched sections: {', '.join(matched_names)}")
        case_ids = [c["id"] for c in all_cases if c.get("section_id") in matched_ids]
    else:
        print("No --sections filter: including all cases in suite")
        case_ids = [c["id"] for c in all_cases]

    if not case_ids:
        print("No cases found — aborting.", file=sys.stderr)
        return 1

    print(f"\nRun name : {run_name}")
    print(f"Suite    : [{args.suite_id}] {suite_name}")
    print(f"Cases    : {len(case_ids)} case(s)")

    if args.dry_run:
        print("\n[dry-run] Would create run with the above settings — no changes made.")
        return 0

    try:
        _create_one_run(run_name, case_ids, description=args.description)
    except Exception as e:
        print(f"Error creating run: {e}", file=sys.stderr)
        return 1

    return 0


def testrail_run(args) -> int:
    """Discover and execute tests driven by a TestRail EASY_BDD: run."""
    from .core.config import ConfigManager
    from .core.variable_manager import GlobalConfigManager
    from .core.testrail_runner import TestRailRunner
    from .services.testrail_service import TestRailService, TestRailError

    try:
        config_manager = GlobalConfigManager()
    except Exception:
        config_manager = GlobalConfigManager()

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        print(
            "Set TESTRAIL_URL, TESTRAIL_USERNAME, and TESTRAIL_API_KEY in your .env file.",
            file=sys.stderr,
        )
        return 1

    runner = TestRailRunner(
        config_manager=config_manager,
        testrail=tr,
        tests_dir=Path(args.tests_dir),
        artifact_dir=Path(args.artifact_dir),
        run_prefix=args.prefix,
    )

    print(f"\nScanning TestRail project {args.project_id} for an active run...")

    if getattr(args, "find_only", False):
        found = runner.find_run(args.project_id)
        if found is None:
            print(f"No active run found for project {args.project_id}")
            return 0
        print(f"Found run: {found['run_name']}")
        props_path = Path(f"reports/run_{args.project_id}.properties")
        props_path.parent.mkdir(parents=True, exist_ok=True)
        props_path.write_text(
            f"RUN_NAME={found['run_name']}\nRUN_URL={found['run_url']}\n", encoding="utf-8"
        )
        return 0

    result = runner.run(
        project_id=args.project_id,
        run_id=args.run_id,
        verbose=not args.quiet,
        no_datalake=getattr(args, "no_datalake", False),
    )

    if result.get("skipped"):
        print(f"\nSkipped: {result.get('reason', 'no run found')}")
        return 0

    run_name = result.get("run_name", "")
    run_url  = result.get("run_url", "")
    if run_name:
        props_path = Path(f"reports/run_{args.project_id}.properties")
        props_path.parent.mkdir(parents=True, exist_ok=True)
        props_path.write_text(
            f"RUN_NAME={run_name}\nRUN_URL={run_url}\n", encoding="utf-8"
        )

    failed = result.get("failed", 0)
    return 1 if failed > 0 else 0


def mcp_serve(args) -> int:
    """Start the Easy BDD MCP server."""
    from .mcp_server import serve

    transport = "sse" if getattr(args, "sse", False) else "stdio"
    host = getattr(args, "host", "0.0.0.0")
    port = getattr(args, "port", 8080)

    if transport == "sse":
        print(f"Starting Easy BDD MCP server (SSE) on {host}:{port}")
    else:
        print("Starting Easy BDD MCP server (STDIO) — ready for Claude Desktop")

    serve(transport=transport, host=host, port=port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
