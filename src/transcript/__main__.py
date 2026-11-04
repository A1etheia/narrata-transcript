"""Command-line entry point: `config`, `doctor`, `extract`, `manifest`, `transcribe`,
`diarize`."""

import argparse
import contextlib
import logging
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from transcript import __version__, audio, audio_tools, diarization, manifest
from transcript.asr import BackendError
from transcript.asr.whisper import WhisperBackend
from transcript.config import Config, ConfigError, format_config, load_config
from transcript.diarization.pyannote import PyannoteDiarizer
from transcript.jsonfile import DataFileError
from transcript.session import SessionKey
from transcript.timecode import format_ms
from transcript.transcription import TranscriptionError, transcribe_segment

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
    transcribe_command = commands.add_parser(
        "transcribe", help="Transcribe one segment of a session with the ASR backend."
    )
    transcribe_command.add_argument("session", help="session key <group>/<ordinal>")
    transcribe_command.add_argument(
        "--segment",
        type=_positive_int,
        required=True,
        help="segment to transcribe, counted from 1 as in the manifest",
    )
    transcribe_command.add_argument(
        "--force",
        action="store_true",
        help="transcribe again even if a transcript exists; drops speaker labels",
    )
    diarize_command = commands.add_parser(
        "diarize", help="Label the words of a session's transcripts with speakers."
    )
    diarize_command.add_argument("session", help="session key <group>/<ordinal>")
    diarize_command.add_argument(
        "--num-speakers",
        type=_positive_int,
        help="number of people audible, if known (default: the model decides)",
    )
    diarize_command.add_argument(
        "--force",
        action="store_true",
        help="diarize again even if a stored result matches",
    )
    for command in (
        config_command,
        extract_command,
        manifest_command,
        transcribe_command,
        diarize_command,
    ):
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
    if args.command == "transcribe":
        return _transcribe(args.session, args.config, args.segment, args.force)
    if args.command == "diarize":
        return _diarize(args.session, args.config, args.num_speakers, args.force)
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


def _transcribe(raw_key: str, config_path: Path, index: int, force: bool) -> int:
    """Only counts, times and provenance reach the console, never text (TOOL-66)."""
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        result = transcribe_segment(
            paths,
            manifest.load_manifest(paths),
            index,
            WhisperBackend.from_config(config),
            config.language,
            keywords=(),  # hints from the knowledge interface come with TOOL-43
            force=force,
        )
    except (
        ValueError,
        ConfigError,
        DataFileError,
        BackendError,
        TranscriptionError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    revision = f" ({result.model_version})" if result.model_version else ""
    print(
        f"{key}: segment {result.index} transcribed in {result.elapsed_ms / 1000:.1f} s "
        f"with {result.backend_id} {result.model}{revision}: "
        f"{result.passages} passage(s), {result.words} word(s), "
        f"{result.words_with_confidence} with confidence, "
        f"language {result.language or 'unknown'}"
    )
    print(f"wrote {paths.reference(result.index)}")
    return 0


def _diarize(
    raw_key: str, config_path: Path, num_speakers: int | None, force: bool
) -> int:
    """Only counts and times reach the console, never labels or text (TOOL-66)."""
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        summaries = diarization.diarize_session(
            paths,
            manifest.load_manifest(paths),
            PyannoteDiarizer.from_config(config),
            num_speakers=num_speakers,
            force=force,
        )
    except (ValueError, ConfigError, DataFileError, BackendError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"{key}: {len(summaries)} segment(s)")
    for summary in summaries:
        if summary.outcome == "skipped":
            print(f"  {summary.index}. skipped: {summary.reason}")
            continue
        how = (
            "reused stored diarization"
            if summary.outcome == "reused"
            else f"diarized in {summary.elapsed_ms / 1000:.1f} s"
        )
        print(
            f"  {summary.index}. {how}: {summary.labels} label(s), "
            f"{summary.turns} turn(s), "
            f"{summary.labelled_words}/{summary.words} words labelled"
        )
    print(f"wrote {paths.asr_dir} and {paths.diarization_dir}")
    return 0


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive whole number")
    return value


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
