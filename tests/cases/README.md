# Test Cases Organization

This directory contains all test cases organized by product category.

## Directory Structure

```
tests/cases/
├── power/          # Power management tests (WattBox, PDUs, UPS)
├── networking/     # Network device tests (switches, routers, access points)
├── media/          # Media streaming and control tests
├── surveillance/   # Camera and NVR tests
├── audio/          # Audio system tests (amplifiers, speakers, DSPs)
├── api_modules/    # Reusable API test modules
└── dev/            # Development and experimental tests
```

## Usage

### Run Tests by Category

```bash
# Run all power tests
python -m easy_bdd run tests/cases/power/

# Run all networking tests
python -m easy_bdd run tests/cases/networking/

# Run specific test
python -m easy_bdd run tests/cases/power/wattbox_power_cycle.yaml
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
  - `wattbox_outlet_control.yaml`
  - `switch_vlan_configuration.yaml`
  - `camera_motion_detection.yaml`
  - `amplifier_volume_control.yaml`

## Recommended Tags

- **Category tags**: `power`, `networking`, `media`, `surveillance`, `audio`
- **Priority tags**: `critical`, `high`, `medium`, `low`
- **Type tags**: `smoke`, `regression`, `integration`, `performance`
- **Device tags**: `wattbox`, `switch`, `router`, `camera`, `amplifier`
- **Feature tags**: `firmware`, `api`, `webui`, `configuration`
