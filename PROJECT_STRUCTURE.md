# Project Structure

```
Automation-Framework/
├── README.md                    # Main project documentation
├── pyproject.toml              # Python project configuration
├── easy_bdd/                   # Framework source code
│   ├── __main__.py            # CLI entry point
│   ├── core/                  # Core framework modules
│   │   ├── config.py         # Configuration management
│   │   ├── parser.py         # YAML test parser
│   │   ├── generator.py      # Gherkin generator
│   │   └── runner.py         # Test runner
│   ├── services/              # Protocol service implementations
│   │   ├── browser_service.py    # Playwright browser automation
│   │   ├── api_service.py        # REST API testing
│   │   ├── websocket_service.py  # WebSocket testing
│   │   ├── serial_service.py     # Serial communication
│   │   ├── android_service.py    # Android automation
│   │   └── aws_service.py        # AWS S3 operations
│   └── tools/                 # Utility tools
│       └── live_recorder.py  # Interactive test recorder
├── config/                    # Configuration files
│   ├── framework.yaml        # Framework settings
│   ├── devices/              # Device configurations
│   ├── device_types/         # Device type definitions
│   └── device_groups/        # Device group definitions
├── tests/                     # Test files
│   ├── cases/                # Test case YAML files
│   └── features/             # Generated Gherkin features
├── docs/                      # Documentation
│   ├── README.md             # Documentation index
│   ├── setup.md              # Installation guide
│   ├── syntax.md             # YAML syntax reference
│   ├── actions.md            # Available actions
│   ├── examples.md           # Example tests
│   ├── conditional-steps.md  # Conditional logic guide
│   ├── aws-s3-integration.md # AWS S3 integration
│   └── ... (other guides)
├── reports/                   # Test results and artifacts
│   ├── *.html                # HTML test reports
│   └── screenshots/          # Test screenshots
├── scripts/                   # Utility scripts
├── frontend/                  # Web UI for test results
├── Firmware/                  # Downloaded firmware files
└── archive/                   # Archived demo files
    ├── demos/                # Old demo scripts
    └── old-results/          # Historical results

## Key Directories

### `/easy_bdd` - Framework Source
The core framework code organized by function.

### `/tests/cases` - Test Definitions
Your YAML test files go here. Examples:
- fw_upgrade.yaml
- conditional_fw_upgrade_example.yaml

### `/config` - Configuration
Framework and device configuration files.

### `/docs` - Documentation
All guides and documentation for using the framework.

### `/reports` - Test Results
Generated after each test run. Contains HTML reports and screenshots.

### `/archive` - Old Files
Legacy code and old results kept for reference.
