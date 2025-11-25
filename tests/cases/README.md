# Test Cases Organization

This directory contains all test cases organized by product category and workspace.

## Directory Structure

```
tests/cases/
├── api_modules/          # API module tests
├── audio/               # Audio system tests
├── dev/                 # Development and experimental tests
│   └── examples/        # Example tests and tutorials
├── media/               # Media streaming tests
├── networking/          # Network device tests
├── ovrc/                # OvrC API and WebSocket tests
├── power/               # Power management tests
└── surveillance/        # Camera and NVR tests
```

## Workspace Organization

Tests are organized into **workspaces** based on product categories:

- **ovrc/**: OvrC API tests (WebSocket, HTTP API, combined examples)
- **networking/**: Network device tests (Araknis, firmware upgrades, device monitoring)
- **dev/**: Development and experimental tests
  - **dev/examples/**: Example tests demonstrating framework features
- **api_modules/**: Reusable API test modules
- **media/**: Media streaming and control tests
- **audio/**: Audio system tests
- **power/**: Power management tests (WattBox, PDUs, UPS)
- **surveillance/**: Camera and NVR tests

## Usage

### Run Tests by Workspace

```bash
# Run all OvrC tests
python -m easy_bdd run tests/cases/ovrc/

# Run all networking tests
python -m easy_bdd run tests/cases/networking/

# Run example tests
python -m easy_bdd run tests/cases/dev/examples/
```

### Run Tests by Tag

```bash
# Run all firmware tests across categories
python -m easy_bdd run tests/cases/ --tags firmware

# Run all critical tests
python -m easy_bdd run tests/cases/ --tags critical
```

## Naming Conventions

- Use descriptive names: `{device}_{feature}_{action}.yaml`
- Examples:
  - `ovrc-login-flow.yaml`
  - `ovrc-select-device.yaml`
  - `conditional_firmware_upgrade.yaml`

## Recommended Tags

- **Category tags**: `ovrc`, `networking`, `media`, `surveillance`, `audio`, `power`
- **Priority tags**: `critical`, `high`, `medium`, `low`
- **Type tags**: `smoke`, `regression`, `integration`, `performance`
- **Feature tags**: `firmware`, `api`, `webui`, `configuration`

## Adding New Tests

1. Choose the appropriate workspace directory
2. Create your test file with a descriptive name
3. Add relevant tags to help with filtering
4. Update this README if creating a new workspace

## Verbose Logging

To see full request/response details for OvrC API calls, set one of these variables in your test:

```yaml
variables:
  verbose_logging: true
  # OR
  show_full_response: true
```

When enabled, you'll see:
- Full request headers (with auth masked)
- Complete request body
- Response headers
- Complete response body
- WebSocket message details

This is useful for debugging API interactions but can produce verbose output.
