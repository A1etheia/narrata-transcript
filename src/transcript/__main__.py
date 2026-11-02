"""Command-line entry point. No pipeline commands exist yet."""

import argparse
from collections.abc import Sequence

from transcript import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="transcript",
        description="Turn roleplay session recordings into structured transcripts.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
