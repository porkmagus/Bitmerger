"""Entry point for python -m bitmerger."""

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--gui", "-g"):
        sys.argv.pop(1)  # remove --gui so Qt doesn't see it
        from .gui import run
        run()
    else:
        from .cli import main
        main()


if __name__ == "__main__":
    main()
