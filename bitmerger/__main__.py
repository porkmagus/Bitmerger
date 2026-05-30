"""Entry point for python -m bitmerger."""

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--gui", "-g"):
        from .gui import run
        run()
    else:
        from .cli import main
        main()


if __name__ == "__main__":
    main()
