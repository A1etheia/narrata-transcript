"""Command-line entry point: `config`, `doctor`, `extract` and `manifest`."""

import argparse
import contextlib
import logging
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from transcript import __version__, audio, audio_tools, manifest
from transcript.config import Config, ConfigError, format_config, load_config
from transcript.jsonfile import DataFileError
from transcript.session import SessionKey
from transcript.timecode import format_ms

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
    commands.add_parser(
        "doctor", help="Check that ffmpeg and ffprobe are installed and run."
    )
    extract_command = commands.add_parser(
        "extract", help="Extract the audio track of a session's recordings."
    )
    extract_command.add_argument("session", help="session key <group>/<ordinal>")
    extract_command.add_argument(
        "--stream",
        type=int,
        default=0,
        help="audio stream to use, counted from 0 (default: 0, the first)",
    )
    manifest_command = commands.add_parser(
        "manifest", help="Write the session manifest from audio and Narrata context."
    )
    manifest_command.add_argument("session", help="session key <group>/<ordinal>")
    manifest_command.add_argument(
        "--consent",
        action="store_true",
        help="note that everyone audible agreed to the recording orally",
    )
    for command in (config_command, extract_command, manifest_command):
        command.add_argument(
            "--config",
            type=Path,
            default=_DEFAULT_CONFIG,
            help=f"configuration file (default: {_DEFAULT_CONFIG})",
        )
    args = parser.parse_args(argv)

    if args.command == "config":
        return _show_config(args.config)
    if args.command == "doctor":
        return _doctor()
    if args.command == "extract":
        return _extract(args.session, args.config, args.stream)
    if args.command == "manifest":
        return _manifest(args.session, args.config, args.consent)
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


def _extract(raw_key: str, config_path: Path, stream: int) -> int:
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        recordings = audio.find_recordings(paths)
        with _log_to_stderr():
            tools = audio_tools.check_audio_tools()
            infos = [audio.probe(recording, tools) for recording in recordings]
            segments = audio.extract(infos, paths, config, tools, stream=stream)
    except (
        ValueError,
        ConfigError,
        audio_tools.AudioToolError,
        audio.AudioError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"{key}: {len(segments)} recording(s) in this order")
    for segment in segments:
        info = segment.source
        video = ", video ignored" if info.has_video else ""
        print(
            f"  {segment.index}. {info.path.name}: {info.container}, "
            f"audio stream {stream} of {len(info.audio_streams)} "
            f"({segment.stream.codec}){video}, "
            f"{format_ms(segment.duration_ms)} -> {paths.segment_wav(segment.index).name}"
        )
    print(f"wrote {paths.audio_dir} and {paths.audio_metadata.name}")
    return 0


def _manifest(raw_key: str, config_path: Path, consent: bool) -> int:
    try:
        key = SessionKey.parse(raw_key)
        paths = _load_config(config_path).session_paths(key)
        result = manifest.build_manifest(paths, consent=consent)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(
        f"{key}: play session {result.play_session_id}, "
        f"{result.session_date.isoformat()}, {len(result.segments)} segment(s)"
    )
    for segment in result.segments:
        print(
            f"  {segment.index}. {format_ms(segment.start_ms)} - "
            f"{format_ms(segment.end_ms)}  {segment.file} ({segment.source.file})"
        )
    if result.consent is None:
        print(
            "warning: no consent note; run again with --consent once everyone "
            "audible agreed",
            file=sys.stderr,
        )
    else:
        print(f"consent noted at {result.consent.noted_at}")
    print(f"wrote {paths.manifest}")
    return 0


@contextlib.contextmanager
def _log_to_stderr() -> Iterator[None]:
    """Show the pipeline's INFO logs; transcript text has its own non-propagating logger."""
    logger = logging.getLogger("transcript")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _show_config(path: Path) -> int:
    try:
        config = _load_config(path)
    except ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(format_config(config), end="")
    return 0


def _load_config(path: Path) -> Config:
    if path == _DEFAULT_CONFIG and not path.exists():
        raise ConfigError(f"{path} not found; copy {_EXAMPLE_CONFIG} to create it")
    return load_config(path)


if __name__ == "__main__":
    raise SystemExit(main())
