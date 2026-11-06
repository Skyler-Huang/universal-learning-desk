#!/usr/bin/env python3
"""Install universal-learning-desk into an agent skills directory.

The skill is just a folder. Different agents look in different places; this
script only copies the folder, it does not modify any agent configuration.

Examples:
  python scripts/install_skill.py --target dsh
  python scripts/install_skill.py --target workbuddy
  python scripts/install_skill.py --target claude
  python scripts/install_skill.py --target custom --dest ./.agents/skills
  python scripts/install_skill.py --list
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

TARGETS = {
    "dsh": ("DSH (DeepSeek Harness)", Path.home() / ".dsh" / "skills"),
    "workbuddy": ("WorkBuddy", Path.home() / ".workbuddy" / "skills"),
    "codebuddy": ("CodeBuddy", Path.home() / ".codebuddy" / "skills"),
    "claude": ("Claude Code", Path.home() / ".claude" / "skills"),
    "codex": ("Codex", Path.home() / ".codex" / "skills"),
}

IGNORE = shutil.ignore_patterns(
    ".git", ".git/**", "__pycache__", "*.pyc", "output", "output/**",
    "work", "work/**", ".venv", "venv", "node_modules", "*.log",
    "examples/fixtures", "examples/smoke_out", "smoke_out",
)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Install universal-learning-desk into an agent skills folder.")
    ap.add_argument("--target", choices=sorted(TARGETS) + ["custom"], help="Agent/platform preset.")
    ap.add_argument("--dest", help="Custom skills directory; required with --target custom.")
    ap.add_argument("--name", default="universal-learning-desk", help="Folder name under the skills directory.")
    ap.add_argument("--force", action="store_true", help="Replace an existing installation.")
    ap.add_argument("--dry-run", action="store_true", help="Print the target without copying.")
    ap.add_argument("--list", action="store_true", help="List presets and exit.")
    args = ap.parse_args()

    if args.list:
        print("Presets:")
        for key, (label, path) in TARGETS.items():
            print(f"  {key:10s} {label:24s} {path}")
        print(f"  {'custom':10s} {'任意目录':24s} --dest <dir>")
        return 0

    if not args.target:
        ap.error("--target is required (or use --list)")
    if args.target == "custom":
        if not args.dest:
            ap.error("--target custom requires --dest")
        skills_dir = Path(args.dest).expanduser().resolve()
    else:
        skills_dir = TARGETS[args.target][1]

    src = skill_root()
    dst = skills_dir / args.name
    print(f"source: {src}")
    print(f"target: {dst}")

    if args.dry_run:
        print("dry run: no files written")
        return 0
    if dst.exists() and not args.force:
        print("target already exists; use --force to replace")
        return 2
    try:
        if dst.exists():
            shutil.rmtree(dst)
        skills_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, ignore=IGNORE)
    except OSError as e:
        print(f"install failed: {e}")
        return 1

    print("installed")
    print("next: reload the agent / start a new session, then ask it to use universal-learning-desk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
