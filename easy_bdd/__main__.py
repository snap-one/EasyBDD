"""
Main entry point for the Easy BDD Framework
Usage: python -m easy_bdd [command] [options]
"""

import sys
import argparse
from pathlib import Path

from .core.runner import TestRunner
from .core.generator import GherkinGenerator
from .core.config import ConfigManager


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
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run tests")
    run_parser.add_argument(
        "path", 
        nargs="?", 
        default="tests/cases/",
        help="Path to test files or directory (default: tests/cases/)"
    )
    run_parser.add_argument(
        "--tags", 
        help="Comma-separated list of tags to filter tests"
    )
    run_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )
    run_parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser with visible window (default)"
    )
    run_parser.add_argument(
        "--ignore-https",
        action="store_true",
        help="Ignore HTTPS certificate errors"
    )
    run_parser.add_argument(
        "--browser",
        choices=["chrome", "firefox", "edge", "safari"],
        help="Browser to use for tests"
    )
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate Gherkin features from YAML/JSON")
    gen_parser.add_argument(
        "path", 
        help="Path to YAML/JSON test files or directory"
    )
    gen_parser.add_argument(
        "--output", 
        default="tests/features/",
        help="Output directory for Gherkin files (default: tests/features/)"
    )
    gen_parser.add_argument(
        "--format",
        choices=["gherkin", "yaml", "json"],
        default="gherkin",
        help="Output format (default: gherkin)"
    )
    
    # Convert command for UI recordings
    convert_parser = subparsers.add_parser("convert", help="Convert UI recorder files to Easy BDD format")
    convert_parser.add_argument(
        "input_file",
        help="Input recorder file (JSON format)"
    )
    convert_parser.add_argument(
        "--output",
        help="Output file path (default: auto-generated)"
    )
    convert_parser.add_argument(
        "--format-type",
        choices=["playwright", "selenium", "cypress", "puppeteer", "katalon", "auto"],
        default="auto",
        help="Input format type (default: auto-detect)"
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
            args.input_file,
            format_type=args.format_type
        )
        
        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            input_path = Path(args.input_file)
            output_path = (input_path.parent /
                           f"{input_path.stem}_converted.yaml")
        
        # Write converted file
        with open(output_path, 'w') as f:
            f.write(yaml_content)
        
        print(f"Successfully converted {args.input_file} to {output_path}")
        return 0
        
    except Exception as e:
        print(f"Error converting file: {e}", file=sys.stderr)
        return 1


def run_tests(args) -> int:
    """Run tests with the given arguments"""
    config = ConfigManager()
    
    # Override browser configuration from CLI arguments
    if hasattr(args, 'headless') and args.headless:
        config.browser.headless = True
        
    if hasattr(args, 'headed') and args.headed:
        config.browser.headless = False
        
    if hasattr(args, 'ignore_https') and args.ignore_https:
        # Add dynamic attributes for HTTPS handling
        config.browser.ignore_https_errors = True
        config.browser.ignore_certificate_errors = True
        
    if hasattr(args, 'browser') and args.browser:
        config.browser.default = args.browser
    
    runner = TestRunner(config)
    
    # Parse tags
    tags = []
    if args.tags:
        tags = [tag.strip() for tag in args.tags.split(",")]
    
    # Run tests
    result = runner.run(
        test_path=Path(args.path),
        tags=tags
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
        yaml_files = (list(input_path.glob("**/*.yaml")) +
                      list(input_path.glob("**/*.yml")))
    
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


if __name__ == "__main__":
    sys.exit(main())