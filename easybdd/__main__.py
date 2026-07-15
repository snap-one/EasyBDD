"""
Main entry point for the Easy BDD Framework
Usage: python -m easybdd [command] [options]
       python -m easybdd [command] ?         # contextual help
"""

import os
import re
import sys
import argparse
import textwrap
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
from .core.testrail_utils import build_testrail_preconditions


# ---------------------------------------------------------------------------
# Contextual help — triggered by appending '?' to any command or sub-command
# ---------------------------------------------------------------------------

_W = 78  # output width

_COMMANDS = {
    "testrail-run": {
        "summary": "Execute tests driven by an active TestRail EASYBDD: run",
        "usage":   "easybdd testrail-run <project_id> [options]",
        "required": [
            ("project_id", "int", "TestRail project ID to scan for an active EASYBDD: run"),
        ],
        "optional": [
            ("--run-id",       "int",  None,                  "Target a specific run ID (skips auto-discovery)"),
            ("--tests-dir",    "path", "tests/cases",          "Directory to search for local YAML tests"),
            ("--artifact-dir", "path", "reports/testrail",     "Directory for generated artifacts and reports"),
            ("--prefix",       "str",  "EASYBDD:",            "Run name prefix to match (or TESTRAIL_RUN_PREFIX env var)"),
            ("--quiet",        "flag", None,                   "Suppress per-test progress output"),
            ("--no-datalake",  "flag", None,                   "Skip posting results to the datalake"),
            ("--find-only",    "flag", None,                   "Check if an active run exists, write .properties file, no execution"),
        ],
        "examples": [
            ("Run active tests in project 79",
             "easybdd testrail-run 79"),
            ("Target a specific run instead of auto-discovering",
             "easybdd testrail-run 79 --run-id 194886"),
            ("Quiet mode (Jenkins-friendly)",
             "easybdd testrail-run 79 --quiet"),
            ("Check if a run exists without executing",
             "easybdd testrail-run 79 --find-only"),
        ],
        "notes": [
            "Requires TESTRAIL_URL, TESTRAIL_USERNAME, TESTRAIL_API_KEY in .env",
            "Results (pass/fail) are posted back to TestRail automatically",
            "An HTML report is saved to --artifact-dir and attached to the TestRail run",
        ],
    },

    "testrail-list": {
        "summary": "List TestRail projects or active EASYBDD: runs",
        "usage":   "easybdd testrail-list [project_id] [options]",
        "required": [],
        "optional": [
            ("project_id", "int", None,        "Show runs for this project (omit to list all projects)"),
            ("--prefix",   "str", "EASYBDD:", "Filter runs by name prefix"),
        ],
        "examples": [
            ("List all TestRail projects",
             "easybdd testrail-list"),
            ("List active runs in project 79",
             "easybdd testrail-list 79"),
        ],
        "notes": [],
    },

    "testrail-create-run": {
        "summary": "Create TestRail run(s) from a suite, optionally filtered to sections",
        "usage":   "easybdd testrail-create-run <project_id> <suite_id> [options]",
        "required": [
            ("project_id", "int", "TestRail project ID"),
            ("suite_id",   "int", "TestRail suite ID to create the run from"),
        ],
        "optional": [
            ("--name",              "str",  None,           "Run name (default: EASYBDD: <suite name>)"),
            ("--sections",          "str+", None,           "Section names to include (substring match, repeatable)"),
            ("--prefix",            "str",  "EASYBDD:",    "Run name prefix"),
            ("--description",       "str",  "",             "Run description (supports JSON run-config syntax)"),
            ("--milestone-id",      "int",  None,           "Associate run with this milestone"),
            ("--var-section",       "str",  None,           "Section with Var: cases — creates one run per Var: case (per-SKU mode)"),
            ("--run-name-template", "str",  "{prefix} {sku} Smoke Test", "Format string for per-SKU run names ({prefix}, {sku}, {product_category})"),
            ("--product-category",  "str",  "",             "Substituted as {product_category} in --run-name-template"),
            ("--dry-run",           "flag", None,           "Preview what would be created without creating it"),
        ],
        "examples": [
            ("Create a single run for all cases in suite 106670",
             "easybdd testrail-create-run 79 106670"),
            ("Create a run with only the Firmware and Functions sections",
             "easybdd testrail-create-run 79 106670 --sections Firmware Functions"),
            ("Per-SKU mode: one run per device in the 'Products' section",
             "easybdd testrail-create-run 79 106670 --var-section Products --sections Firmware Functions"),
            ("Dry-run to preview without creating",
             "easybdd testrail-create-run 79 106670 --var-section Products --sections Firmware --dry-run"),
        ],
        "notes": [
            "--sections uses case-insensitive substring match against section names",
            "--var-section mode requires Var: case titles in that section (e.g. 'Var: AN-220-SW-R-16-POE')",
        ],
    },

    "testrail-convert": {
        "summary": "Convert a mybdd-format TestRail suite to Easy BDD YAML files",
        "usage":   "easybdd testrail-convert <project_id> (--suite SUITE_ID | --run RUN_ID) [options]",
        "required": [
            ("project_id",       "int", "TestRail project ID"),
            ("--suite / --run",  "int", "Source suite ID or run ID (one required)"),
        ],
        "optional": [
            ("--output-dir",        "path", "tests/cases/<slug>", "Directory to write generated YAML files"),
            ("--shared-steps-file", "path", "<output-dir>/shared_steps.yaml", "Path for shared_steps.yaml"),
            ("--tag",               "str",  "<suite slug>",        "Tag added to every generated test"),
            ("--no-testrail",       "flag", None,                  "Write YAML files only — do NOT create a new TestRail suite"),
            ("--no-yaml",           "flag", None,                  "Create TestRail suite only — do NOT write YAML files"),
            ("--target-suite",      "int",  None,                  "Write into an existing TestRail suite instead of creating new"),
            ("--target-suite-name", "str",  "EASYBDD: <name>",    "Name for the new TestRail suite"),
            ("--dry-run",           "flag", None,                  "Preview without creating files or TestRail cases"),
            ("--quiet",             "flag", None,                  "Suppress per-case progress output"),
        ],
        "examples": [
            ("Convert mybdd suite 12345 in project 79 to YAML + new TestRail suite",
             "easybdd testrail-convert 79 --suite 12345"),
            ("Preview only (no files, no TestRail changes)",
             "easybdd testrail-convert 79 --suite 12345 --dry-run"),
            ("Convert to YAML only (no new TestRail suite)",
             "easybdd testrail-convert 79 --suite 12345 --no-testrail --output-dir tests/cases/moip"),
        ],
        "notes": [
            "Reads Given:/Shared:/Feature: prefixed cases from the source suite",
            "Produces Var:/Setup:/Shared:/Feature:/Teardown: cases in the new format",
        ],
    },

    "testrail-sync": {
        "summary": "Sync an Easy BDD TestRail suite to local YAML files (for 'easybdd run')",
        "usage":   "easybdd testrail-sync <project_id> (--suite SUITE_ID | --run RUN_ID) [options]",
        "required": [
            ("project_id",      "int", "TestRail project ID"),
            ("--suite / --run", "int", "Source suite or run ID (one required)"),
        ],
        "optional": [
            ("--output-dir", "path", "tests/cases/<slug>", "Directory to write YAML files"),
            ("--tag",        "str",  "<suite slug>",        "Tag added to every generated test"),
            ("--dry-run",    "flag", None,                  "Preview without writing files"),
            ("--quiet",      "flag", None,                  "Suppress per-case progress output"),
        ],
        "examples": [
            ("Sync suite 106670 from project 79 to local YAML",
             "easybdd testrail-sync 79 --suite 106670"),
            ("Preview what would be written",
             "easybdd testrail-sync 79 --suite 106670 --dry-run"),
        ],
        "notes": [
            "Produces runnable YAML files — use 'easybdd run <dir>' to execute them locally",
            "Feature:, Shared:, Var: cases are all synced",
        ],
    },

    "validate": {
        "summary": "Validate test YAML files or TestRail cases for syntax errors",
        "usage":   "easybdd validate [path] [options]",
        "required": [],
        "optional": [
            ("path",               "path", "tests/cases/", "File or directory to validate"),
            ("--strict",           "flag", None,           "Treat warnings as errors"),
            ("--snippet",          "str",  None,           "Validate a YAML step snippet string inline"),
            ("--snippet-file",     "path", None,           "Validate a file containing YAML steps (not a full test)"),
            ("--stdin",            "flag", None,           "Read YAML snippet from stdin"),
            ("--shared-steps-dir", "path", None,           "Directory with shared_steps.yaml for reference validation"),
            ("--testrail-case",    "int",  None,           "Validate a single TestRail case by ID"),
            ("--testrail-suite",   "int",  None,           "Validate all cases in a TestRail suite (requires --project)"),
            ("--testrail-run",     "int",  None,           "Validate all Feature:/Shared: cases in a TestRail run"),
            ("--project",          "int",  None,           "TestRail project ID (required with --testrail-suite)"),
        ],
        "examples": [
            ("Validate all local YAML files",
             "easybdd validate tests/cases/"),
            ("Validate a single TestRail case",
             "easybdd validate --testrail-case 18684737"),
            ("Validate all cases in a TestRail run",
             "easybdd validate --testrail-run 194886"),
            ("Validate all cases in a TestRail suite",
             "easybdd validate --testrail-suite 106670 --project 79"),
            ("Validate a step snippet inline",
             "easybdd validate --snippet '- test.assert:\\n    expression: last_response[\"status\"] == 200'"),
        ],
        "notes": [],
    },

    "run": {
        "summary": "Run local YAML test files",
        "usage":   "easybdd run [path] [options]",
        "required": [],
        "optional": [
            ("path",             "path",   "tests/cases/",            "Test file or directory to run"),
            ("--tags",           "str",    None,                      "Comma-separated tags to filter tests"),
            ("--headless",       "flag",   None,                      "Run browser in headless mode"),
            ("--headed",         "flag",   None,                      "Run browser with visible window"),
            ("--browser",        "choice", "chrome",                  "Browser: chrome | firefox | edge | safari"),
            ("--ignore-https",   "flag",   None,                      "Ignore HTTPS certificate errors"),
            ("--record-video",   "flag",   None,                      "Record video of browser steps"),
            ("--export-results", "path",   None,                      "Export results to .json / .csv / .xml"),
        ],
        "examples": [
            ("Run all tests",
             "easybdd run"),
            ("Run a specific test file",
             "easybdd run tests/cases/my_test.yaml"),
            ("Run tests tagged 'firmware'",
             "easybdd run --tags firmware"),
            ("Run headless with results exported",
             "easybdd run tests/cases/ --headless --export-results results.json"),
        ],
        "notes": [
            "For TestRail-driven runs use 'easybdd testrail-run' instead",
        ],
    },

    "generate": {
        "summary": "Generate Gherkin .feature files from local YAML tests",
        "usage":   "easybdd generate <path> [options]",
        "required": [
            ("path", "path", "YAML test file or directory to convert"),
        ],
        "optional": [
            ("--output", "path",   "tests/features/", "Output directory for .feature files"),
            ("--format", "choice", "gherkin",         "Output format: gherkin | yaml | json"),
        ],
        "examples": [
            ("Generate Gherkin from all YAML tests",
             "easybdd generate tests/cases/"),
        ],
        "notes": [],
    },

    "floci-upload": {
        "summary": "Upload local file(s) to a Floci-emulated S3 bucket",
        "usage":   "easybdd floci-upload <bucket_name> <file_path>... [options]",
        "required": [
            ("bucket_name", "str", "Floci bucket name (created automatically if missing)"),
            ("file_path",   "path", "One or more local files to upload"),
        ],
        "optional": [
            ("--key-prefix",   "str",  "",                        "Prefix prepended to each object key"),
            ("--flatten",      "flag", None,                      "Use just the basename as the object key (drop directory structure)"),
            ("--endpoint-url", "str",  "$FLOCI_ENDPOINT_URL or http://localhost:4566", "Floci endpoint URL"),
            ("--region",       "str",  "us-east-1",               "Region passed to boto3 (Floci does not validate it)"),
        ],
        "examples": [
            ("Mirror a single changed firmware file into Floci",
             "easybdd floci-upload wattbox wattbox/upgrade_moip_4.7.0.bin"),
            ("Mirror several files, flattening directory structure",
             "easybdd floci-upload wattbox wattbox/a.bin wattbox/b.bin --flatten"),
            ("Point at a non-default Floci host",
             "easybdd floci-upload wattbox wattbox/a.bin --endpoint-url http://floci-host:4566"),
        ],
        "notes": [
            "No AWS credentials required — Floci accepts any identity",
            "Independent of the real S3 bucket; does not read from or write to AWS",
            "Bucket is created automatically on first upload if it doesn't exist yet",
        ],
    },

    "floci-delete": {
        "summary": "Delete object(s) from a Floci-emulated S3 bucket by repo-relative path",
        "usage":   "easybdd floci-delete <bucket_name> <path>... [options]",
        "required": [
            ("bucket_name", "str", "Floci bucket name"),
            ("path",        "path", "One or more repo-relative paths to delete (need not exist on disk)"),
        ],
        "optional": [
            ("--key-prefix",   "str",  "",                        "Prefix prepended to each key (must match upload-time prefix)"),
            ("--flatten",      "flag", None,                      "Use just the basename as the key (must match upload-time --flatten)"),
            ("--endpoint-url", "str",  "$FLOCI_ENDPOINT_URL or http://localhost:4566", "Floci endpoint URL"),
            ("--region",       "str",  "us-east-1",               "Region passed to boto3 (Floci does not validate it)"),
        ],
        "examples": [
            ("Remove a firmware file deleted from the repo",
             "easybdd floci-delete wattbox wattbox/upgrade_moip_4.7.0.bin"),
        ],
        "notes": [
            "Deleting a key that isn't present in the bucket is not an error (matches S3 delete semantics)",
            "--key-prefix/--flatten must match whatever was passed to floci-upload for the same file, or the derived key won't line up",
        ],
    },

    "floci-reconcile": {
        "summary": "Delete Floci objects that no longer have a matching file in a repo checkout",
        "usage":   "easybdd floci-reconcile <bucket_name> <repo_root> [options]",
        "required": [
            ("bucket_name", "str",  "Floci bucket name"),
            ("repo_root",   "path", "Path to the checked-out firmware repo to compare Floci against"),
        ],
        "optional": [
            ("--extension",    "str",  ".bin",                    "File extension to reconcile on both sides"),
            ("--key-prefix",   "str",  "",                        "Prefix prepended to each expected key (must match upload-time prefix)"),
            ("--execute",      "flag", None,                      "Actually delete stale objects (default: dry-run report only)"),
            ("--endpoint-url", "str",  "$FLOCI_ENDPOINT_URL or http://localhost:4566", "Floci endpoint URL"),
            ("--region",       "str",  "us-east-1",               "Region passed to boto3 (Floci does not validate it)"),
        ],
        "examples": [
            ("Preview what would be cleaned up (no changes made)",
             "easybdd floci-reconcile wattbox /var/lib/jenkins/workspace/Wattbox-Firmware"),
            ("Actually delete the stale objects",
             "easybdd floci-reconcile wattbox /var/lib/jenkins/workspace/Wattbox-Firmware --execute"),
        ],
        "notes": [
            "Defaults to a dry run — pass --execute to actually delete anything",
            "One-time/periodic cleanup only — the CI mirror stage already keeps Floci in sync with new commits going forward",
        ],
    },

    "mcp-serve": {
        "summary": "Start the Easy BDD MCP server (for Claude / AI integrations)",
        "usage":   "easybdd mcp-serve [options]",
        "required": [],
        "optional": [
            ("--sse",  "flag", None,    "Use HTTP/SSE transport instead of STDIO"),
            ("--host", "str",  "0.0.0.0", "Bind address for SSE mode"),
            ("--port", "int",  "8080",  "Port for SSE mode"),
        ],
        "examples": [
            ("Start in STDIO mode (default, for Claude Desktop)",
             "easybdd mcp-serve"),
            ("Start in SSE/HTTP mode",
             "easybdd mcp-serve --sse --port 8080"),
        ],
        "notes": [],
    },
}

_ALL_COMMANDS_SUMMARY = [
    ("testrail-run",        "Execute tests driven by an active TestRail EASYBDD: run"),
    ("testrail-list",       "List TestRail projects or active runs"),
    ("testrail-create-run", "Create TestRail run(s) from a suite"),
    ("testrail-convert",    "Convert mybdd-format suite → Easy BDD YAML + TestRail suite"),
    ("testrail-sync",       "Sync Easy BDD TestRail suite → local YAML files"),
    ("validate",            "Validate local YAML files or TestRail cases for syntax errors"),
    ("run",                 "Run local YAML test files"),
    ("generate",            "Generate Gherkin .feature files from YAML tests"),
    ("mcp-serve",           "Start the MCP server for AI integrations"),
    ("floci-upload",        "Upload local file(s) to a Floci-emulated S3 bucket"),
    ("floci-delete",        "Delete object(s) from a Floci-emulated S3 bucket by repo-relative path"),
    ("floci-reconcile",     "Delete Floci objects that no longer have a matching file in a repo checkout"),
    ("docker-run",          "Build and run a test inside a Docker container"),
    ("record",              "Launch Playwright codegen and convert recording to YAML"),
    ("selector-audit",      "Scan YAML files for fragile CSS/XPath selectors"),
    ("edit-test",           "Open a test file in the default editor"),
    ("convert",             "Convert a UI recorder file to Easy BDD YAML"),
]


def _hr(char="─"):
    return char * _W


def _print_contextual_help(tokens: list) -> None:
    """Print rich contextual help based on tokens typed before the '?'."""
    # Separate flags/options (start with -) from positional args
    positional = [t for t in tokens if not t.startswith("-")]
    command = positional[0] if positional else None

    # ── No command yet: list everything ──────────────────────────────────────
    if command is None:
        print()
        print("  Easy BDD — available commands")
        print(_hr())
        for cmd, desc in _ALL_COMMANDS_SUMMARY:
            print(f"  {cmd:<26}  {desc}")
        print(_hr())
        print()
        print("  Usage:  easybdd <command> ?         show help for a command")
        print("  Usage:  easybdd <command> <args> ?  show what comes next")
        print()
        print("  Most common:")
        print("    easybdd testrail-run ?")
        print("    easybdd testrail-create-run ?")
        print("    easybdd testrail-list ?")
        print("    easybdd validate ?")
        print()
        return

    info = _COMMANDS.get(command)

    # ── Unknown command ───────────────────────────────────────────────────────
    if info is None:
        print(f"\n  Unknown command: '{command}'")
        print("  Available commands:")
        for cmd, _ in _ALL_COMMANDS_SUMMARY:
            print(f"    {cmd}")
        print()
        return

    # ── Work out which required args are already satisfied ───────────────────
    already_provided_positional = positional[1:]  # tokens after the command name
    required = info.get("required", [])
    remaining_required = required[len(already_provided_positional):]
    satisfied = required[:len(already_provided_positional)]

    print()
    print(f"  {command}  —  {info['summary']}")
    print(_hr())
    print(f"  Usage: {info['usage']}")
    print()

    # Already-provided positional values
    if satisfied and already_provided_positional:
        print("  Already provided:")
        for (name, typ, desc), val in zip(satisfied, already_provided_positional):
            print(f"    {name} = {val}")
        print()

    # What's required next
    if remaining_required:
        print("  REQUIRED — next argument(s):")
        for name, typ, desc in remaining_required:
            print(f"    {name:<22} <{typ}>   {desc}")
        print()
    else:
        print("  All required arguments provided.")
        print()

    # Optional flags
    optional = info.get("optional", [])
    if optional:
        print("  OPTIONAL flags:")
        for name, typ, default, desc in optional:
            default_str = f"  (default: {default})" if default else ""
            flag_type   = "" if typ == "flag" else f" <{typ}>"
            col = f"    {name}{flag_type}"
            print(f"{col:<42}  {desc}{default_str}")
        print()

    # Examples
    examples = info.get("examples", [])
    if examples:
        print("  Examples:")
        for label, cmd in examples:
            print(f"    # {label}")
            print(f"    {cmd}")
            print()

    # Notes
    notes = info.get("notes", [])
    if notes:
        print("  Notes:")
        for note in notes:
            print(f"    • {note}")
        print()

    print(_hr())
    print()


def main():
    # Handle '?' contextual help before argparse touches argv
    _argv = sys.argv[1:]
    if _argv and _argv[-1] == "?":
        _print_contextual_help(_argv[:-1])
        return 0

    parser = argparse.ArgumentParser(
        description="Easy BDD Testing Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m easybdd run                              # Run all tests
  python -m easybdd run tests/cases/login.yaml      # Run specific test
  python -m easybdd run --tags browser,api          # Run tests with tags
  python -m easybdd docker-run tests/cases/login.yaml  # Run test in Docker
  python -m easybdd generate tests/cases/           # Generate Gherkin only
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
            "  python -m easybdd validate tests/cases/my_test.yaml\n"
            "  python -m easybdd validate tests/cases/\n"
            "  python -m easybdd validate --snippet \"- test.assert:\\n    expression: x == 1\"\n"
            "  python -m easybdd validate --snippet-file my_steps.yaml\n"
            "  cat steps.yaml | python -m easybdd validate --stdin"
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
        help="Execute tests driven by a TestRail run (EASYBDD: prefix)",
    )
    tr_parser.add_argument(
        "project_id",
        type=int,
        help="TestRail project ID to scan for an active EASYBDD: run",
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
        help="TestRail run name prefix to match (default: EASYBDD:, or TESTRAIL_RUN_PREFIX env var)",
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
        help="Name for the new TestRail suite (default: 'EASYBDD: <source name>')",
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

    # TestRail sync command — Easy BDD TestRail suite → local YAML files
    trs_parser = subparsers.add_parser(
        "testrail-sync",
        help="Sync an Easy BDD TestRail suite to local YAML files runnable via 'easybdd run'",
    )
    trs_parser.add_argument(
        "project_id",
        type=int,
        help="TestRail project ID",
    )
    _trs_src = trs_parser.add_mutually_exclusive_group(required=True)
    _trs_src.add_argument(
        "--suite",
        type=int,
        dest="source_suite_id",
        metavar="SUITE_ID",
        help="Easy BDD suite ID to sync (Feature:/Shared:/Var: cases)",
    )
    _trs_src.add_argument(
        "--run",
        type=int,
        dest="source_run_id",
        metavar="RUN_ID",
        help="Run ID to read cases from instead of a suite",
    )
    trs_parser.add_argument(
        "--output-dir",
        default=None,
        metavar="PATH",
        help="Directory to write generated YAML files (default: tests/cases/<suite_slug>)",
    )
    trs_parser.add_argument(
        "--tag",
        default=None,
        metavar="TAG",
        help="Tag added to every generated test (default: slugified suite name)",
    )
    trs_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without creating any files",
    )
    trs_parser.add_argument(
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
        "--streamable-http",
        action="store_true",
        dest="streamable_http",
        help="Use Streamable HTTP transport (required for Claude Desktop 1.14+)",
    )
    mcp_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address for SSE/streamable-http transport (default: 0.0.0.0)",
    )
    mcp_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE/streamable-http transport (default: 8080)",
    )

    # Floci upload command — mirror local file(s) into a Floci-emulated S3 bucket
    floci_parser = subparsers.add_parser(
        "floci-upload",
        help="Upload local file(s) to a Floci-emulated S3 bucket",
    )
    floci_parser.add_argument(
        "bucket_name", help="Floci bucket name (created automatically if missing)"
    )
    floci_parser.add_argument(
        "file_paths", nargs="+", metavar="FILE", help="Local file path(s) to upload"
    )
    floci_parser.add_argument(
        "--key-prefix",
        default="",
        metavar="PREFIX",
        help="Prefix prepended to each object key",
    )
    floci_parser.add_argument(
        "--flatten",
        action="store_true",
        help="Use just the file's basename as the object key (drop directory structure)",
    )
    floci_parser.add_argument(
        "--endpoint-url",
        default=None,
        dest="endpoint_url",
        metavar="URL",
        help="Floci endpoint URL (default: $FLOCI_ENDPOINT_URL or http://localhost:4566)",
    )
    floci_parser.add_argument(
        "--region",
        default="us-east-1",
        help="Region passed to boto3 (default: us-east-1; Floci does not validate it)",
    )

    # Floci delete command — remove object(s) from a Floci-emulated S3 bucket
    # by the same repo-relative path convention floci-upload keys them under,
    # so a file removed from a firmware repo can be removed from Floci too
    # without needing it to still exist on disk.
    floci_delete_parser = subparsers.add_parser(
        "floci-delete",
        help="Delete object(s) from a Floci-emulated S3 bucket by repo-relative path",
    )
    floci_delete_parser.add_argument(
        "bucket_name", help="Floci bucket name"
    )
    floci_delete_parser.add_argument(
        "paths", nargs="+", metavar="PATH",
        help="Repo-relative path(s) to delete (matching how floci-upload derived their key — the file need not exist on disk)",
    )
    floci_delete_parser.add_argument(
        "--key-prefix",
        default="",
        metavar="PREFIX",
        help="Prefix prepended to each object key (must match the prefix used at upload time)",
    )
    floci_delete_parser.add_argument(
        "--flatten",
        action="store_true",
        help="Use just the basename as the object key (must match --flatten used at upload time)",
    )
    floci_delete_parser.add_argument(
        "--endpoint-url",
        default=None,
        dest="endpoint_url",
        metavar="URL",
        help="Floci endpoint URL (default: $FLOCI_ENDPOINT_URL or http://localhost:4566)",
    )
    floci_delete_parser.add_argument(
        "--region",
        default="us-east-1",
        help="Region passed to boto3 (default: us-east-1; Floci does not validate it)",
    )

    # Floci reconcile command — one-time/periodic cleanup for drift the
    # incremental CI mirror stage can't see on its own (it only reacts to
    # commit-to-commit deltas, so anything removed from the repo before that
    # mirror stage existed, or during any gap in CI coverage, never gets
    # cleaned up by it). Compares a repo checkout's actual current files
    # against Floci's actual current contents and removes what's stale.
    floci_reconcile_parser = subparsers.add_parser(
        "floci-reconcile",
        help="Delete Floci objects that no longer have a matching file in a repo checkout",
    )
    floci_reconcile_parser.add_argument(
        "bucket_name", help="Floci bucket name"
    )
    floci_reconcile_parser.add_argument(
        "repo_root", help="Path to the checked-out firmware repo to compare Floci against"
    )
    floci_reconcile_parser.add_argument(
        "--extension",
        default=".bin",
        help="File extension to reconcile on both sides (default: .bin)",
    )
    floci_reconcile_parser.add_argument(
        "--key-prefix",
        default="",
        metavar="PREFIX",
        help="Prefix prepended to each expected key (must match the prefix used at upload time)",
    )
    floci_reconcile_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete the stale objects. Without this flag, only reports what would be deleted.",
    )
    floci_reconcile_parser.add_argument(
        "--endpoint-url",
        default=None,
        dest="endpoint_url",
        metavar="URL",
        help="Floci endpoint URL (default: $FLOCI_ENDPOINT_URL or http://localhost:4566)",
    )
    floci_reconcile_parser.add_argument(
        "--region",
        default="us-east-1",
        help="Region passed to boto3 (default: us-east-1; Floci does not validate it)",
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
        help='Run name (default: "EASYBDD: <suite name>")',
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
        help='Run name prefix (default: "EASYBDD: " or TESTRAIL_RUN_PREFIX env var)',
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
        "--var-section",
        metavar="SECTION",
        default=None,
        help=(
            "Name of the section containing 'Var:' cases (one per SKU/variant). "
            "When set, creates one run per Var: case found in that section. "
            "The Var: case is always included; --sections controls the rest of the cases. "
            'Example: --var-section "VPS" --sections "Functions" "Firmware Resiliency" "VPS Web UI" "VPS API"'
        ),
    )
    trcr_parser.add_argument(
        "--run-name-template",
        default=None,
        metavar="TEMPLATE",
        help=(
            'Python format string for per-Var run names. '
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
        help="List TestRail projects and active EASYBDD: runs",
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
        help="Run name prefix to filter by (default: EASYBDD:, or TESTRAIL_RUN_PREFIX env var)",
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
    # Crawler command
    crawler_parser = subparsers.add_parser(
        "crawler",
        help="Start the Easy BDD Crawler local server (used by the Chrome extension)",
    )
    crawler_sub = crawler_parser.add_subparsers(dest="crawler_command")
    crawler_start = crawler_sub.add_parser("start", help="Start the crawler server (Chrome extension mode)")
    crawler_start.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    crawler_start.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")

    crawler_pw = crawler_sub.add_parser(
        "playwright",
        help="Crawl using a headed Playwright browser — no Chrome extension needed",
    )
    crawler_pw.add_argument("--url", required=True, help="Starting URL (e.g. https://app.example.com/login)")
    crawler_pw.add_argument("--project", type=int, required=True, metavar="PROJECT_ID",
                            help="TestRail project ID")
    crawler_pw.add_argument("--suite", type=int, default=None, metavar="SUITE_ID",
                            help="TestRail suite ID (default: create new suite)")
    crawler_pw.add_argument("--section", default="Auto-generated", metavar="NAME",
                            help="TestRail section name (default: Auto-generated)")
    crawler_pw.add_argument("--provider", default="rules",
                            choices=["rules", "claude", "ollama"],
                            help="AI provider for test generation (default: rules — no API key needed)")
    crawler_pw.add_argument("--model", default=None, metavar="MODEL",
                            help="AI model override (optional)")
    crawler_pw.add_argument("--output", default="tests/cases/crawled", metavar="DIR",
                            help="Output directory for generated YAML files (default: tests/cases/crawled)")
    crawler_pw.add_argument("--no-run", action="store_true",
                            help="Skip creating a TestRail test run after crawl")
    crawler_pw.add_argument("--login-timeout", type=int, default=120, metavar="SECONDS",
                            help="Seconds to wait for manual login (default: 120)")

    crawler_crx = crawler_sub.add_parser(
        "convert-crx",
        help="Convert a Playwright CRX / Chrome DevTools Recorder file to Easy BDD YAML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Convert Playwright TypeScript/JavaScript recordings or Chrome DevTools
            Recorder JSON exports to Easy BDD dot-notation YAML test files.

            Supported input formats:
              .ts / .js  — Playwright TypeScript or JavaScript codegen output
                           (Chrome DevTools Recorder → "Export as Playwright test")
              .json      — Chrome DevTools Recorder JSON export
              .py        — Playwright Python codegen output

            Examples:
              python -m easybdd crawler convert-crx recording.ts
              python -m easybdd crawler convert-crx recording.json --output tests/cases/
              python -m easybdd crawler convert-crx *.ts --output tests/cases/
        """),
    )
    crawler_crx.add_argument(
        "input_files",
        nargs="+",
        metavar="FILE",
        help="Playwright / Chrome DevTools Recorder file(s) to convert (.ts, .js, .json, .py)",
    )
    crawler_crx.add_argument(
        "--output", "-o",
        default=None,
        metavar="DIR",
        help="Output directory for generated YAML files (default: same directory as input file)",
    )

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
        elif args.command == "testrail-sync":
            return testrail_sync(args)
        elif args.command == "mcp-serve":
            return mcp_serve(args)
        elif args.command == "floci-upload":
            return floci_upload(args)
        elif args.command == "floci-delete":
            return floci_delete(args)
        elif args.command == "floci-reconcile":
            return floci_reconcile(args)
        elif args.command == "selector-audit":
            return selector_audit(args)
        elif args.command == "record":
            return record_and_upload(args)
        elif args.command == "crawler":
            return crawler_serve(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def floci_upload(args) -> int:
    """Upload local file(s) to a Floci-emulated S3 bucket.

    Independent of the real S3 upload path — intended for CI stages that want
    firmware mirrored into a local/free Floci bucket in addition to (not
    instead of) whatever already lands in the real bucket.
    """
    from .services.floci_service import FlociService

    service = FlociService(logger=print, endpoint_url=args.endpoint_url)

    failures = 0
    for file_path in args.file_paths:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            failures += 1
            continue

        key = path.name if args.flatten else str(path).replace(os.sep, "/").lstrip("./")
        if args.key_prefix:
            key = f"{args.key_prefix.rstrip('/')}/{key}"

        try:
            url = service.upload_file(
                bucket_name=args.bucket_name,
                local_file_path=str(path),
                s3_key=key,
                region=args.region,
            )
            print(f"[Floci] Uploaded {file_path} -> {url}")
        except Exception as e:
            print(f"Error uploading {file_path} to Floci: {e}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\n{failures} of {len(args.file_paths)} file(s) failed to upload.", file=sys.stderr)
        return 1

    print(f"\nUploaded {len(args.file_paths)} file(s) to Floci bucket '{args.bucket_name}'.")
    return 0


def floci_delete(args) -> int:
    """Delete object(s) from a Floci-emulated S3 bucket by repo-relative path.

    Mirrors floci_upload's key derivation exactly (--key-prefix/--flatten) so
    a path already removed from disk (deleted or renamed away in git) still
    maps to the same object key it was mirrored under, letting a CI stage
    keep Floci's contents in sync with the firmware repo on deletes too.
    """
    from .services.floci_service import FlociService

    service = FlociService(logger=print, endpoint_url=args.endpoint_url)

    failures = 0
    for file_path in args.paths:
        key = (
            os.path.basename(file_path)
            if args.flatten
            else file_path.replace(os.sep, "/").lstrip("./")
        )
        if args.key_prefix:
            key = f"{args.key_prefix.rstrip('/')}/{key}"

        try:
            service.delete_object(
                bucket_name=args.bucket_name,
                s3_key=key,
                region=args.region,
            )
            print(f"[Floci] Deleted {args.bucket_name}/{key}")
        except Exception as e:
            print(f"Error deleting {key} from Floci: {e}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\n{failures} of {len(args.paths)} key(s) failed to delete.", file=sys.stderr)
        return 1

    print(f"\nDeleted {len(args.paths)} key(s) from Floci bucket '{args.bucket_name}'.")
    return 0


def floci_reconcile(args) -> int:
    """Delete Floci objects that no longer have a matching file in a repo checkout.

    The CI mirror stage only reacts to commit-to-commit git diffs, so it
    can't clean up drift from before it existed or from any gap in CI
    coverage. This walks the repo checkout's actual current files and Floci's
    actual current contents and removes whatever's only on the Floci side.
    """
    from .services.floci_service import FlociService

    service = FlociService(logger=print, endpoint_url=args.endpoint_url)

    repo_root = Path(args.repo_root)
    if not repo_root.is_dir():
        print(f"Error: repo root not found: {args.repo_root}", file=sys.stderr)
        return 1

    ext_lower = args.extension.lower()
    expected_keys = set()
    for path in repo_root.rglob("*"):
        if not path.is_file() or not path.name.lower().endswith(ext_lower):
            continue
        key = str(path.relative_to(repo_root)).replace(os.sep, "/")
        if args.key_prefix:
            key = f"{args.key_prefix.rstrip('/')}/{key}"
        expected_keys.add(key)

    actual_keys = set(
        service.list_keys(
            bucket_name=args.bucket_name,
            file_extension=args.extension,
            region=args.region,
        )
    )

    stale = sorted(actual_keys - expected_keys)

    print(f"Repo checkout ({repo_root}): {len(expected_keys)} '{args.extension}' file(s)")
    print(f"Floci bucket '{args.bucket_name}': {len(actual_keys)} '{args.extension}' object(s)")
    print(f"Stale in Floci (not in repo checkout): {len(stale)}")

    if not stale:
        print("Nothing to clean up — Floci matches the repo checkout.")
        return 0

    for key in stale:
        print(f"  stale: {key}")

    if not args.execute:
        print(f"\nDry run — no objects deleted. Re-run with --execute to delete these {len(stale)} key(s).")
        return 0

    failures = 0
    for key in stale:
        try:
            service.delete_object(bucket_name=args.bucket_name, s3_key=key, region=args.region)
            print(f"[Floci] Deleted {args.bucket_name}/{key}")
        except Exception as e:
            print(f"Error deleting {key} from Floci: {e}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\n{failures} of {len(stale)} stale key(s) failed to delete.", file=sys.stderr)
        return 1

    print(f"\nDeleted {len(stale)} stale key(s) from Floci bucket '{args.bucket_name}'.")
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

    cmd = ["playwright", "codegen", "--output", output_file, "--target", "python"]
    if args.url:
        cmd.append(args.url)

    # On headless servers (no $DISPLAY), wrap with xvfb-run to provide a virtual display
    no_display = not os.environ.get("DISPLAY") and sys.platform != "darwin" and sys.platform != "win32"
    if no_display:
        cmd = ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1280x1024x24"] + cmd
        print("\n[Record] No $DISPLAY detected — using xvfb-run for virtual display.")

    print("\n[Record] Launching Playwright codegen...")
    print("  Record your browser steps, then close the browser window to continue.\n")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Recording exited with error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        if "xvfb-run" in str(e) or (no_display and "playwright" not in str(e)):
            print(
                "xvfb-run not found. Install it with:\n"
                "  sudo apt-get install -y xvfb",
                file=sys.stderr,
            )
        else:
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
        if isinstance(step, dict) and len(step) == 1:
            # Nested browser.xxx format: {browser.click: {role: button, name: Save}}
            action, params = next(iter(step.items()))
            if isinstance(params, dict):
                parts = [f"{k}={v!r}" for k, v in params.items()]
            else:
                parts = []
        else:
            action = step.get("action", "?")
            parts = [f"{k}={step[k]!r}" for k in ("url", "role", "name", "label", "text", "selector", "value") if step.get(k)]
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

    preconditions = build_testrail_preconditions(steps)

    try:
        case = tr.add_case(
            section_id,
            title=test_data["name"],
            custom_preconds=preconditions,
            type_id=1,
            custom_automation_status=5,
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

    # Get project root (parent of easybdd package)
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
        container_test_cmd = ["python", "-m", "easybdd", "run", str(test_path_in_container)]
        
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
    from easybdd.core.parser import YAMLParser
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


def testrail_sync(args) -> int:
    """Sync an Easy BDD TestRail suite to local runnable YAML files."""
    from .services.testrail_service import TestRailService, TestRailError
    from .core.testrail_syncer import TestrailSyncer

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        print("Set TESTRAIL_URL, TESTRAIL_USERNAME, and TESTRAIL_API_KEY in your .env file.",
              file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else None

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    src_desc = f"suite {args.source_suite_id}" if args.source_suite_id else f"run {args.source_run_id}"
    print(f"\n[Sync] {mode} — {src_desc} → {output_dir or 'tests/cases/<suite_slug>'}")
    print()

    syncer = TestrailSyncer(tr)
    result = syncer.sync(
        project_id=args.project_id,
        source_suite_id=args.source_suite_id,
        source_run_id=args.source_run_id,
        output_dir=output_dir,
        suite_tag=args.tag,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    result.print_summary()
    return 1 if result.error_count > 0 else 0


def testrail_list(args) -> int:
    """List TestRail projects or active EASYBDD: runs for a project."""
    from .services.testrail_service import TestRailService, TestRailError

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        return 1

    prefix = args.prefix or os.getenv("TESTRAIL_RUN_PREFIX", "EASYBDD:")

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
        print(f"\nUse 'easybdd testrail-list <project_id>' to see active runs.")
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
      - --var-section MODE: find Var: cases in a section, create one
        run per Var: case (one per SKU/variant).
    """
    from .services.testrail_service import TestRailService, TestRailError

    try:
        tr = TestRailService()
    except TestRailError as e:
        print(f"TestRail configuration error: {e}", file=sys.stderr)
        return 1

    prefix = args.prefix or os.getenv("TESTRAIL_RUN_PREFIX", "EASYBDD:").rstrip()

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

    # ── MODE: --var-section ─────────────────────────────────────────────────
    if args.var_section:
        var_section_label = args.var_section.lower()
        var_section_ids = {
            s["id"] for s in all_sections
            if var_section_label == s["name"].lower() or var_section_label in s["name"].lower()
        }
        if not var_section_ids:
            print(f"Var section '{args.var_section}' not found.", file=sys.stderr)
            print(f"Available: {', '.join(s['name'] for s in all_sections)}", file=sys.stderr)
            return 1

        var_cases = [
            c for c in all_cases
            if c.get("section_id") in var_section_ids
            and c.get("title", "").startswith("Var:")
        ]
        if not var_cases:
            print(f"No 'Var:' cases found in section '{args.var_section}'.")
            return 0

        print(f"\nFound {len(var_cases)} Var: case(s) in '{args.var_section}':")
        for gc in var_cases:
            sku = gc["title"].replace("Var:", "").strip()
            print(f"  → {sku}")

        # Resolve the shared sections (Functions, Firmware Resiliency, etc.)
        shared_section_ids = _resolve_section_ids(args.sections) if args.sections else set()
        shared_case_ids = [
            c["id"] for c in all_cases
            if c.get("section_id") in shared_section_ids
            and not c.get("title", "").startswith("Var:")
        ]

        name_template = (
            args.run_name_template or "{prefix} {sku} Smoke Test"
        )
        product_category = getattr(args, "product_category", "") or ""

        if args.dry_run:
            print("\n[dry-run] Would create:")
            for gc in var_cases:
                sku = gc["title"].replace("Var:", "").strip()
                run_name = name_template.format(
                    prefix=prefix, sku=sku, product_category=product_category
                )
                total = 1 + len(shared_case_ids)
                print(f"  Run: '{run_name}'  ({total} cases: 1 Var + {len(shared_case_ids)} shared)")
            return 0

        print()
        created = 0
        for gc in var_cases:
            sku = gc["title"].replace("Var:", "").strip()
            run_name = name_template.format(
                prefix=prefix, sku=sku, product_category=product_category
            )
            case_ids = [gc["id"]] + shared_case_ids
            try:
                _create_one_run(run_name, case_ids, description=args.description)
                created += 1
            except Exception as e:
                print(f"  ❌ Failed to create run for '{sku}': {e}", file=sys.stderr)

        print(f"\nCreated {created}/{len(var_cases)} run(s).")
        return 0 if created == len(var_cases) else 1

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
    """Discover and execute tests driven by a TestRail EASYBDD: run."""
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

    if getattr(args, "streamable_http", False):
        transport = "streamable-http"
    elif getattr(args, "sse", False):
        transport = "sse"
    else:
        transport = "stdio"
    host = getattr(args, "host", "0.0.0.0")
    port = getattr(args, "port", 8080)

    if transport == "streamable-http":
        print(f"Starting Easy BDD MCP server (Streamable HTTP) on {host}:{port}/mcp")
    elif transport == "sse":
        print(f"Starting Easy BDD MCP server (SSE) on {host}:{port}/sse")
    else:
        print("Starting Easy BDD MCP server (STDIO) — ready for Claude Desktop")

    serve(transport=transport, host=host, port=port)
    return 0


def crawler_serve(args) -> int:
    """Dispatch crawler subcommands: start (HTTP server), playwright, or convert-crx."""
    crawler_cmd = getattr(args, "crawler_command", None)

    if crawler_cmd == "playwright":
        return crawler_playwright(args)

    if crawler_cmd == "convert-crx":
        from .crawler.crx_converter import cli_convert_crx
        return cli_convert_crx(args)

    # Default: start the HTTP server for the Chrome extension
    try:
        from .crawler.server import run_server
    except ImportError as e:
        print(
            f"Crawler dependencies missing: {e}\n"
            "Run: pip install fastapi uvicorn --break-system-packages",
            file=sys.stderr,
        )
        return 1

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    print(f"Starting Easy BDD Crawler server on http://{host}:{port}")
    print("Load the Chrome extension and click 'Start Crawl' to begin.")
    print("Press Ctrl+C to stop.\n")
    run_server(host=host, port=port)
    return 0


def crawler_playwright(args) -> int:
    """
    Crawl a web app using a headed Playwright browser.
    No Chrome extension, no API key (when using --provider rules).
    """
    try:
        from .crawler.playwright_crawler import PlaywrightCrawler
        from .crawler.models import CrawlSessionConfig
    except ImportError as e:
        print(
            f"Crawler dependencies missing: {e}\n"
            "Run: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    config = CrawlSessionConfig(
        testrail_project_id=args.project,
        testrail_suite_id=getattr(args, "suite", None),
        testrail_section_name=getattr(args, "section", "Auto-generated"),
        create_test_run=not getattr(args, "no_run", False),
        ai_provider=getattr(args, "provider", "rules"),
        ai_model=getattr(args, "model", None),
        output_dir=getattr(args, "output", "tests/cases/crawled"),
        base_url=args.url,
    )

    login_timeout = getattr(args, "login_timeout", 120)
    crawler = PlaywrightCrawler(config, login_timeout_s=login_timeout)
    crawler.run(start_url=args.url)

    status = crawler.status
    print(f"\nDone — {status['cases_generated']} case(s) generated, "
          f"{status['cases_pushed']} pushed to TestRail.")
    if status.get("test_run_url"):
        print(f"TestRail run: {status['test_run_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
