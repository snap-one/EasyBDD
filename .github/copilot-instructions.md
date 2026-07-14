# Easy BDD Testing Framework - Copilot Instructions

This workspace contains a user-friendly BDD testing framework that doesn't rely on TestRail. The framework supports:

- Simple YAML-based test definitions (no programming required)
- Multi-protocol testing (browser, REST APIs, WebSocket, Android, AWS, serial)
- File-based test case management
- Automatic Gherkin feature generation from YAML
- Global variables with ${variable} syntax
- Modern Python architecture with type hints

## Key Components

- `easybdd/core/` - Framework core modules (config, parser, generator, runner)
- `easybdd/services/` - Protocol service implementations
- `tests/cases/` - YAML test definitions
- `tests/features/` - Generated Gherkin files
- `config/` - Framework configuration
- `reports/` - Test results and artifacts

## Architecture

The framework follows a clean architecture:
- **Parser**: Converts YAML test definitions to internal format
- **Generator**: Creates Gherkin features from parsed tests
- **Runner**: Executes tests and manages results
- **Config**: Manages framework and environment settings
- **Services**: Handle different protocols (browser, API, etc.)

## Development Guidelines

- Keep YAML syntax simple and intuitive for non-programmers
- Use descriptive action names that read like plain English
- Follow Python best practices with type hints
- Maintain modular service architecture
- Ensure comprehensive error handling and validation
- Document all available actions and parameters

## Test Definition Format

Tests are defined in YAML with this structure:
```yaml
name: "Test Name"
description: "What this test does"
tags: ["tag1", "tag2"]
variables:
  var_name: "value"
steps:
  - action: "Action name"
    parameter: "value"
```

## Available Commands

- `python -m easybdd run [path]` - Run tests
- `python -m easybdd generate [path]` - Generate Gherkin only
- Use `--tags` to filter tests by tags