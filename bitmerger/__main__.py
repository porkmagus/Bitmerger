"""Entry point for python -m bitmerger.

GUI-only mode. All operations run through the graphical interface.
"""

from .gui import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
