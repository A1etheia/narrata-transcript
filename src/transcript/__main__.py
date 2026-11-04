"""Command-line entry point: `config` and `doctor` so far; no pipeline commands yet."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from transcript import __version__, audio_tools
from transcript.config import ConfigError, format_config, load_config

_DEFAULT_CONFIG = Path("config/config.yaml")
_EXAMPLE_CONFIG = Path("config/example.yaml")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="transcript",
        description="Turn roleplay session recordings into structured transcripts.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    commands = parser.add_subparsers(dest="command")
    config_command = commands.add_parser(
        "config", help="Show the effective configuration."
    )
    config_command.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help=f"configuration file (default: {_DEFAULT_CONFIG})",
    )
    commands.add_parser(
        "doctor", help="Check that ffmpeg and ffprobe are installed and run."
    )
    args = parser.parse_args(argv)

    if args.command == "config":
        return _show_config(args.config)
    if args.command == "doctor":
        return _doctor()
    parser.print_help()
    return 0


def _doctor() -> int:
    try:
        tools = audio_tools.check_audio_tools()
    except audio_tools.AudioToolError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for info in (tools.ffmpeg, tools.ffprobe):
        print(f"{info.name} {info.version} ({info.path})")
    return 0


def _show_config(path: Path) -> int:
    try:
        if path == _DEFAULT_CONFIG and not path.exists():
            raise ConfigError(f"{path} not found; copy {_EXAMPLE_CONFIG} to create it")
        config = load_config(path)
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(format_config(config), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
