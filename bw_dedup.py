#!/usr/bin/env python3
"""Backward-compatible entry point.\n\nThis script delegates to the bitmerger package.\n"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--gui", "-g"):
        sys.argv.pop(1)  # remove --gui so Qt doesn't see it
        from bitmerger.gui import run
        run()
    else:
        from bitmerger.cli import main
        main()
