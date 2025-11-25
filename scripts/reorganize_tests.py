#!/usr/bin/env python3
"""
Test File Reorganization Script
Helps organize test files into proper workspace directories
"""

import shutil
from pathlib import Path
import yaml

# Base directory
BASE_DIR = Path(__file__).parent.parent
TESTS_DIR = BASE_DIR / "tests" / "cases"

# Organization rules
ORGANIZATION_RULES = {
    # OvrC-related files -> ovrc/
    "ovrc": [
        "ovrc_example.yaml",
        "ovrc_api_websocket_test.yaml",
        "ovrc_combined_example.yaml",
        "ovrc_http_api_example.yaml",
    ],
    # Examples -> dev/examples/
    "dev/examples": [
        "inline_shared_steps_example.yaml",
        "jsonrpc_get_about_example.yaml",
        "recorded_test.yaml",
    ],
    # Networking-related
    "networking": [
        "firmware_upload_webui.yaml",
        "device_monitoring_loop.yaml",
    ],
}

def analyze_current_structure():
    """Analyze current test file structure"""
    print("=" * 60)
    print("Current Test File Structure Analysis")
    print("=" * 60)
    
    # Files in root of tests/cases
    root_files = list(TESTS_DIR.glob("*.yaml"))
    print(f"\n📁 Files in root of tests/cases/: {len(root_files)}")
    for f in sorted(root_files):
        print(f"   - {f.name}")
    
    # Files by workspace
    print(f"\n📁 Files by workspace:")
    workspaces = {}
    for workspace_dir in TESTS_DIR.iterdir():
        if workspace_dir.is_dir() and workspace_dir.name not in [".git", "__pycache__"]:
            yaml_files = list(workspace_dir.glob("*.yaml"))
            if yaml_files:
                workspaces[workspace_dir.name] = len(yaml_files)
                print(f"   - {workspace_dir.name}/: {len(yaml_files)} files")
    
    # Duplicates
    print(f"\n🔍 Checking for duplicates:")
    all_files = {}
    for f in TESTS_DIR.rglob("*.yaml"):
        if f.name in all_files:
            print(f"   ⚠️  Duplicate: {f.name}")
            print(f"      - {all_files[f.name]}")
            print(f"      - {f}")
        else:
            all_files[f.name] = f
    
    return root_files, workspaces

def propose_organization():
    """Propose organization plan"""
    print("\n" + "=" * 60)
    print("Proposed Organization Plan")
    print("=" * 60)
    
    root_files, workspaces = analyze_current_structure()
    
    print("\n📋 Proposed moves:")
    for target_dir, files in ORGANIZATION_RULES.items():
        target_path = TESTS_DIR / target_dir
        print(f"\n   → {target_dir}/")
        for filename in files:
            source = TESTS_DIR / filename
            if source.exists():
                print(f"      ✓ {filename}")
            else:
                print(f"      ✗ {filename} (not found)")
    
    # Files not in organization rules
    unorganized = []
    for f in root_files:
        if f.name not in [item for sublist in ORGANIZATION_RULES.values() for item in sublist]:
            unorganized.append(f.name)
    
    if unorganized:
        print(f"\n   ⚠️  Files not in organization plan:")
        for filename in unorganized:
            print(f"      - {filename}")

def reorganize(dry_run=True):
    """Reorganize test files"""
    print("\n" + "=" * 60)
    print(f"{'DRY RUN: ' if dry_run else ''}Reorganizing Test Files")
    print("=" * 60)
    
    moved = 0
    errors = []
    
    for target_dir, files in ORGANIZATION_RULES.items():
        target_path = TESTS_DIR / target_dir
        target_path.mkdir(parents=True, exist_ok=True)
        
        for filename in files:
            source = TESTS_DIR / filename
            if not source.exists():
                print(f"   ⚠️  Skipping {filename} (not found)")
                continue
            
            dest = target_path / filename
            
            if dest.exists():
                print(f"   ⚠️  Skipping {filename} (already exists at {dest})")
                # Check if they're different
                try:
                    with open(source, 'r') as f1, open(dest, 'r') as f2:
                        if f1.read() != f2.read():
                            print(f"      ⚠️  Files differ - consider merging manually")
                except:
                    pass
                continue
            
            try:
                if not dry_run:
                    shutil.move(str(source), str(dest))
                print(f"   {'[DRY RUN] ' if dry_run else ''}✓ Moved {filename} → {target_dir}/")
                moved += 1
            except Exception as e:
                error_msg = f"Error moving {filename}: {e}"
                print(f"   ❌ {error_msg}")
                errors.append(error_msg)
    
    print(f"\n{'Would move' if dry_run else 'Moved'} {moved} file(s)")
    if errors:
        print(f"   {len(errors)} error(s) occurred")
    
    return moved, errors

if __name__ == "__main__":
    import sys
    
    # Analyze current structure
    analyze_current_structure()
    
    # Propose organization
    propose_organization()
    
    # Ask for confirmation
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        print("\n" + "=" * 60)
        response = input("Execute reorganization? (yes/no): ")
        if response.lower() == "yes":
            reorganize(dry_run=False)
        else:
            print("Reorganization cancelled.")
    else:
        print("\n" + "=" * 60)
        print("This is a dry run. Use --execute to actually move files.")
        print("=" * 60)
        reorganize(dry_run=True)

