"""
Main entry point for the Easy BDD Framework
Usage: python -m easy_bdd [command] [options]
"""

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
        "validate", help="Validate test files without running them"
    )
    validate_parser.add_argument(
        "path",
        nargs="?",
        default="tests/cases/",
        help="Path to test file or directory (default: tests/cases/)",
    )
    validate_parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )
    
    # Edit-test command
    edit_parser = subparsers.add_parser(
        "edit-test", help="Open a test file in the default editor"
    )
    edit_parser.add_argument(
        "test_path", type=str, help="Path to test file to edit"
    )
    convert_parser.add_argument(
        "--output", help="Output file path (default: auto-generated)"
    )
    convert_parser.add_argument(
        "--format-type",
        choices=["playwright", "selenium", "cypress", "puppeteer", "katalon", "auto"],
        default="auto",
        help="Input format type (default: auto-detect)",
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
        elif args.command == "edit-test":
            return edit_test(args)
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
    result = runner.run(test_path=Path(args.path), tags=tags)

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


def validate_tests(args) -> int:
    """Validate test files without running them"""
    from .core.validator import ConfigValidator

    input_path = Path(args.path)

    if not input_path.exists():
        print(f"Error: Path '{input_path}' does not exist", file=sys.stderr)
        return 1

    validator = ConfigValidator()

    # Collect test files
    if input_path.is_file():
        test_files = [input_path]
    else:
        test_files = list(input_path.glob("**/*.yaml")) + list(
            input_path.glob("**/*.yml")
        )

    if not test_files:
        print(f"No YAML files found in '{input_path}'", file=sys.stderr)
        return 1

    print(f"Validating {len(test_files)} test file(s)...\\n")

    total_errors = 0
    total_warnings = 0
    files_with_issues = 0

    for test_file in test_files:
        try:
            is_valid, messages = validator.validate_test_file(
                test_file, strict=args.strict
            )

            if not is_valid:
                files_with_issues += 1
                print(f"❌ {test_file}")
                for msg in messages:
                    if msg.startswith("ERROR:"):
                        print(f"  {msg}")
                        total_errors += 1
                    elif msg.startswith("WARNING:"):
                        print(f"  {msg}")
                        total_warnings += 1
                print()
            else:
                print(f"✅ {test_file}")

        except Exception as e:
            files_with_issues += 1
            total_errors += 1
            print(f"❌ {test_file}")
            print(f"  ERROR: Failed to validate: {e}\\n")

    # Print summary
    print("\\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total files: {len(test_files)}")
    print(f"Valid files: {len(test_files) - files_with_issues}")
    print(f"Files with issues: {files_with_issues}")
    print(f"Total errors: {total_errors}")
    print(f"Total warnings: {total_warnings}")

    if total_errors > 0:
        print("\\n❌ Validation FAILED")
        return 1
    elif total_warnings > 0 and args.strict:
        print("\\n⚠️  Validation FAILED (strict mode, warnings treated as errors)")
        return 1
    else:
        print("\\n✅ Validation PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
