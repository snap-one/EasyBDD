#!/usr/bin/env python3
"""
build_mcpb.py — Package Easy BDD as an MCPB (MCP Bundle) file.

Usage:
    python build_mcpb.py                  # creates easy-bdd-1.0.0.mcpb
    python build_mcpb.py --output my.mcpb # custom output path

The .mcpb format is a ZIP archive containing manifest.json plus the server
source.  See: https://github.com/modelcontextprotocol/mcpb
"""

import argparse
import fnmatch
import json
import sys
import zipfile
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
MANIFEST_PATH = ROOT / "manifest.json"
IGNORE_FILE   = ROOT / ".mcpbignore"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_ignore_patterns(ignore_path: Path) -> list[str]:
    """Read .mcpbignore and return non-comment, non-blank patterns."""
    if not ignore_path.exists():
        return []
    patterns = []
    for line in ignore_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_ignored(rel_path: Path, patterns: list[str]) -> bool:
    """Return True if *rel_path* matches any .mcpbignore pattern."""
    parts = rel_path.parts
    rel_str = rel_path.as_posix()

    for pattern in patterns:
        # Directory patterns (trailing /) — match any path component
        if pattern.endswith("/"):
            dir_pattern = pattern.rstrip("/")
            if any(fnmatch.fnmatch(part, dir_pattern) for part in parts):
                return True
        else:
            # Match against the full relative path OR just the filename
            if fnmatch.fnmatch(rel_str, pattern):
                return True
            if fnmatch.fnmatch(rel_path.name, pattern):
                return True
            # Also match directory names in path (e.g. ".git" pattern blocks ".git/...")
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
    return False


def collect_files(root: Path, patterns: list[str]) -> list[Path]:
    """Walk *root* and return absolute paths of files not ignored."""
    result = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if not is_ignored(rel, patterns):
            result.append(path)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build easy-bdd.mcpb bundle")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output .mcpb path (default: easy-bdd-<version>.mcpb in project root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be included without creating the archive",
    )
    args = parser.parse_args()

    # ── Read manifest ────────────────────────────────────────────────────────
    if not MANIFEST_PATH.exists():
        print(f"ERROR: manifest.json not found at {MANIFEST_PATH}", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text())
    version  = manifest.get("version", "0.0.0")
    name     = manifest.get("name", "easy-bdd")

    output_path = Path(args.output) if args.output else ROOT / f"{name}-{version}.mcpb"

    # ── Collect files ────────────────────────────────────────────────────────
    patterns = load_ignore_patterns(IGNORE_FILE)
    files    = collect_files(ROOT, patterns)

    print(f"Bundle: {output_path.name}")
    print(f"Files : {len(files)}")
    print()

    if args.dry_run:
        for f in files:
            print(f"  {f.relative_to(ROOT).as_posix()}")
        print("\n(dry-run — no archive written)")
        return 0

    # ── Write ZIP ────────────────────────────────────────────────────────────
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arc_name = f.relative_to(ROOT).as_posix()
            zf.write(f, arc_name)
            print(f"  + {arc_name}")

    size_kb = output_path.stat().st_size // 1024
    print(f"\nCreated {output_path}  ({size_kb} KB)")
    print("\nInstall in Claude Desktop:")
    print(f"  Open {output_path.name} with Claude Desktop (or drag it onto the app)")
    print("\nOr register manually in claude_desktop_config.json with:")
    print(f"  mcpb install {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
