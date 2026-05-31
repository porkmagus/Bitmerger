#!/usr/bin/env python3
"""
Build script for Bitmerger standalone executables.

Usage:
    python build.py              # Build for current platform
    python build.py --all        # Build for all platforms (requires Docker)
    python build.py --onefile    # Build as single-file executable
"""

import sys
import subprocess
import os
from pathlib import Path


def run(cmd: list[str]) -> None:
    print(" ->", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    onefile = "--onefile" in sys.argv
    here = Path(__file__).parent
    icon = here / "assets" / "icon.png"
    icon_arg = [f"--icon={icon}"] if icon.exists() else []

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "Bitmerger",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--hidden-import", "bitmerger.core",
        "--hidden-import", "bitmerger.gui",
        "--hidden-import", "bitmerger.theme",
        "--hidden-import", "bitmerger.icons",
        "--hidden-import", "bitmerger.item_editor",
        "--hidden-import", "bitmerger.undo_manager",
        "--hidden-import", "jinja2",
        "--hidden-import", "thefuzz",
        "--hidden-import", "tldextract",
        "--add-data", f"{here / 'bitmerger' / 'templates'}{os.pathsep}bitmerger/templates",
    ] + icon_arg + (["--onefile"] if onefile else ["--onedir"]) + [
        str(here / "bw_dedup.py")
    ]

    run(cmd)
    print("\n[OK] Build complete. Output in dist/Bitmerger")


if __name__ == "__main__":
    main()
