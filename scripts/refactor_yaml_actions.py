#!/usr/bin/env python3
"""
Refactor YAML test files to use correct dot notation for actions.
Converts old action names to new dot notation format.
"""

import os
import re
from pathlib import Path

# Mapping of old action names to new dot notation
ACTION_MAPPINGS = {
    # API actions
    "api get": "api.get",
    "api post": "api.post",
    "api put": "api.put",
    "api patch": "api.patch",
    "api delete": "api.delete",
    
    # Validation actions
    "validate status": "test.assert_response",
    "validate response": "test.assert_response",
    "validate json": "test.assert",  # For JSON field validation
    
    # AWS actions (if they exist)
    "AWS get latest firmware": "aws.get_latest",
    
    # OvrC actions (already in correct format, but ensure consistency)
    "ovrc get about": "ovrc.get about",  # Keep space for this one
    "ovrc.get_about": "ovrc.get about",
}

def refactor_yaml_file(file_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Refactor a single YAML file.
    Returns (lines_changed, replacements_made)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        replacements = 0
        
        # Pattern to match action: "value" or action: value
        action_pattern = r'action:\s*["\']?([^"\'\n]+)["\']?'
        
        def replace_action(match):
            nonlocal replacements
            action_value = match.group(1).strip()
            
            # Check if this action needs to be updated
            if action_value in ACTION_MAPPINGS:
                new_action = ACTION_MAPPINGS[action_value]
                replacements += 1
                # Preserve the quote style
                quote_char = '"' if '"' in match.group(0) else ("'" if "'" in match.group(0) else '"')
                return f'action: {quote_char}{new_action}{quote_char}'
            
            return match.group(0)
        
        content = re.sub(action_pattern, replace_action, content, flags=re.IGNORECASE)
        
        # After updating actions, update parameter names if needed
        # If we changed "validate status" to "test.assert_response", change "status:" to "status_code:"
        # and add "response: last_response" if not present
        if "test.assert_response" in content:
            # Pattern to match "status:" parameter (but not "status_code:")
            # Match "status:" that's indented and followed by a number
            status_pattern = r'(\s+)status:\s*(\d+)'
            def replace_status(match):
                nonlocal replacements
                replacements += 1
                return f'{match.group(1)}status_code: {match.group(2)}'
            content = re.sub(status_pattern, replace_status, content)
            
            # Add "response: last_response" parameter if not present
            # Find all test.assert_response blocks and check if they have a response parameter
            # Match the action line and all following indented lines
            lines = content.split('\n')
            new_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                new_lines.append(line)
                
                # Check if this is a test.assert_response action
                if re.search(r'action:\s*["\']?test\.assert_response["\']?', line):
                    # Get the base indentation
                    base_indent = len(line) - len(line.lstrip())
                    param_indent = ' ' * (base_indent + 2)
                    
                    # Check the next few lines for parameters
                    has_response = False
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > base_indent):
                        if 'response:' in lines[j].lower():
                            has_response = True
                            break
                        j += 1
                    
                    # If no response parameter found, add it
                    if not has_response:
                        # Find where to insert it (after action line, before other params)
                        insert_pos = i + 1
                        # Skip empty lines
                        while insert_pos < len(lines) and not lines[insert_pos].strip():
                            new_lines.append(lines[insert_pos])
                            insert_pos += 1
                        
                        # Insert response parameter
                        new_lines.insert(insert_pos, f'{param_indent}response: last_response')
                        replacements += 1
                        i = insert_pos
                        continue
                
                i += 1
            
            content = '\n'.join(new_lines)
        
        if content != original_content:
            if not dry_run:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            return (len(content.split('\n')), replacements)
        
        return (0, 0)
    
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return (0, 0)

def main():
    """Main function to refactor all YAML files."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Refactor YAML test files to use dot notation')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without making changes')
    parser.add_argument('--path', type=str, default='tests', help='Path to search for YAML files')
    args = parser.parse_args()
    
    tests_dir = Path(args.path)
    if not tests_dir.exists():
        print(f"Error: Path {tests_dir} does not exist")
        return
    
    yaml_files = list(tests_dir.rglob('*.yaml')) + list(tests_dir.rglob('*.yml'))
    
    if not yaml_files:
        print(f"No YAML files found in {tests_dir}")
        return
    
    print(f"Found {len(yaml_files)} YAML files")
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified\n")
    
    total_replacements = 0
    files_modified = 0
    
    for yaml_file in sorted(yaml_files):
        lines, replacements = refactor_yaml_file(yaml_file, dry_run=args.dry_run)
        if replacements > 0:
            files_modified += 1
            total_replacements += replacements
            status = "[DRY RUN] Would modify" if args.dry_run else "Modified"
            print(f"{status}: {yaml_file} ({replacements} replacements)")
    
    print(f"\nSummary:")
    print(f"  Files processed: {len(yaml_files)}")
    print(f"  Files {'would be ' if args.dry_run else ''}modified: {files_modified}")
    print(f"  Total replacements: {total_replacements}")
    
    if args.dry_run and total_replacements > 0:
        print("\nRun without --dry-run to apply changes")

if __name__ == '__main__':
    main()

