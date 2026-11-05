"""Command-line entry point: `config`, `doctor`, `extract`, `context`, `manifest`,
`transcribe`, `diarize`."""

import argparse
import collections
import contextlib
import logging
import os
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from transcript import __version__, audio, audio_tools, diarization, manifest, narrata
from transcript.asr import BackendError
from transcript.asr.whisper import WhisperBackend
from transcript.config import Config, ConfigError, format_config, load_config
from transcript.diarization.pyannote import PyannoteDiarizer
from transcript.jsonfile import DataFileError
from transcript.narrata_client import NarrataClientError, fetch_context, read_token
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_ms
from transcript.transcription import (
    OUTCOME_STATUSES,
    SegmentOutcome,
    TranscriptionError,
    transcribe_session,
)

_DEFAULT_CONFIG = Path("config/config.yaml")
_EXAMPLE_CONFIG = Path("config/example.yaml")
_DOTENV = Path(".env")


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
    context_command = commands.add_parser(
        "context",
        help="Fetch a session's transcription context from Narrata and store it.",
    )
    context_command.add_argument("session", help="session key <group>/<ordinal>")
    context_command.add_argument(
        "--from-file",
        type=Path,
        metavar="PATH",
        help="take a saved transcription-context response instead of asking Narrata",
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
        "transcribe",
        help="Transcribe a session's segments with the ASR backend, then diarize.",
    )
    transcribe_command.add_argument("session", help="session key <group>/<ordinal>")
    transcribe_command.add_argument(
        "--segment",
        type=_positive_int,
        help="only this segment, counted from 1 as in the manifest (default: all)",
    )
    transcribe_command.add_argument(
        "--force",
        action="store_true",
        help="transcribe again even if a matching transcript exists",
    )
    transcribe_command.add_argument(
        "--no-diarize",
        action="store_true",
        help="skip the speaker diarization after the transcription",
    )
    transcribe_command.add_argument(
        "--num-speakers",
        type=_positive_int,
        help="number of people audible, for the diarization (default: model decides)",
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
        context_command,
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
    with _log_to_stderr():  # pipeline steps log progress and failed attempts
        if args.command == "extract":
            return _extract(args.session, args.config, args.stream)
        if args.command == "context":
            return _context(args.session, args.config, args.from_file)
        if args.command == "manifest":
            return _manifest(args.session, args.config, args.consent)
        if args.command == "transcribe":
            return _transcribe(
                args.session,
                args.config,
                args.segment,
                args.force,
                diarize=not args.no_diarize,
                num_speakers=args.num_speakers,
            )
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


def _context(raw_key: str, config_path: Path, from_file: Path | None) -> int:
    """Only counts reach the console: participants and glossary hold real names."""
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        if from_file is None:
            raw = _fetch(key, config, config_path)
        else:
            raw = _read_bytes(from_file)
        session = narrata.store_context(paths, raw)
        participants = narrata.read_participants(paths).participants
        glossary = narrata.read_glossary(paths)
    except (ValueError, ConfigError, DataFileError, NarrataClientError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    tiers = collections.Counter(entry.relevance for entry in glossary.entries)
    print(
        f"{key}: play session {session.play_session_id}, "
        f"{session.session_date.isoformat()}, "
        f"contract {glossary.contract_version}"
    )
    print(
        f"  {len(participants)} participant(s) "
        f"({sum(p.role == 'gm' for p in participants)} gm, "
        f"{sum(p.is_former for p in participants)} former), "
        f"{sum(len(p.characters) for p in participants)} character(s)"
    )
    print(
        f"  {len(glossary.entries)} glossary entries ("
        + ", ".join(f"{tiers[tier]} {tier}" for tier in narrata.RELEVANCE_TIERS)
        + f"), archive tier {glossary.archive_returned} of {glossary.archive_total}, "
        f"{len(glossary.ambiguities)} asr ambiguities"
    )
    print(f"wrote {paths.narrata_context}")
    return 0


def _fetch(key: SessionKey, config: Config, config_path: Path) -> bytes:
    if config.narrata_url is None:
        raise ConfigError(f"{config_path}: narrata.url is not set")
    group_id = config.narrata_groups.get(key.group)
    if group_id is None:
        raise ConfigError(
            f"{config_path}: narrata.groups has no group id for {key.group}"
        )
    token = read_token(os.environ, _DOTENV)
    return fetch_context(config.narrata_url, group_id, key.ordinal, token)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise DataFileError(f"{path}: cannot read file ({error.strerror})") from None


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


def _transcribe(
    raw_key: str,
    config_path: Path,
    index: int | None,
    force: bool,
    diarize: bool,
    num_speakers: int | None,
) -> int:
    """Only counts, times and provenance reach the console, never text (TOOL-66).

    Exit 0 when every selected segment is transcribed and diarized, 1 when
    one failed or stayed open, 2 when the run could not start. Every failed
    attempt is logged to stderr with session, segment and backend.
    """
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        session_manifest = manifest.load_manifest(paths)
        diarizer = PyannoteDiarizer.from_config(config) if diarize else None
        if diarizer is not None:
            diarizer.identity()  # a missing pyannote fails now, not after the ASR
        print(f"{key}: {len(session_manifest.segments)} segment(s)")
        run = transcribe_session(
            paths,
            session_manifest,
            WhisperBackend.from_config(config),
            config.language,
            keywords=(),  # hints from the knowledge interface come with TOOL-43
            force=force,
            indices=None if index is None else {index},
            progress=_print_outcome,
            retries=config.asr_retries,
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

    info = run.identity.info
    revision = f" ({info.model_version})" if info.model_version else ""
    counts = collections.Counter(outcome.status for outcome in run.outcomes)
    print(
        f"{key}: "
        + ", ".join(f"{counts[status]} {status}" for status in OUTCOME_STATUSES)
        + f" with {info.backend_id} {info.model}{revision}"
    )
    if run.load_error is not None:
        print(f"error: {run.load_error}", file=sys.stderr)

    if diarizer is None:
        print(f"wrote {paths.asr_dir}")
        return 0 if run.complete else 1
    print(f"{key}: diarization")
    try:
        summaries = diarization.diarize_session(
            paths,
            session_manifest,
            diarizer,
            num_speakers=num_speakers,
            retries=config.diarization_retries,
        )
    except (ValueError, DataFileError, BackendError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    _print_diarization(summaries, paths)
    return 0 if run.complete and not _any_failed(summaries) else 1


def _print_outcome(outcome: SegmentOutcome) -> None:
    if outcome.status == "open":
        line = "open"
    elif outcome.status == "failed":
        line = str(outcome.failure)
    else:
        how = (
            "reused"
            if outcome.status == "reused"
            else f"transcribed in {(outcome.elapsed_ms or 0) / 1000:.1f} s"
        )
        line = (
            f"{how}: {outcome.passages} passage(s), {outcome.words} word(s), "
            f"{outcome.words_with_confidence} with confidence, "
            f"language {outcome.language or 'unknown'}"
        )
    print(f"  {outcome.index}. {line}", flush=True)


def _diarize(
    raw_key: str, config_path: Path, num_speakers: int | None, force: bool
) -> int:
    """Only counts and times reach the console, never labels or text (TOOL-66).

    Exit 0 when every transcribed segment is diarized, 1 when one failed, 2
    when the run could not start or the model could not load.
    """
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
            retries=config.diarization_retries,
        )
    except (ValueError, ConfigError, DataFileError, BackendError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"{key}: {len(summaries)} segment(s)")
    _print_diarization(summaries, paths)
    return 1 if _any_failed(summaries) else 0


def _any_failed(summaries: Sequence[diarization.SegmentSummary]) -> bool:
    return any(summary.outcome == "failed" for summary in summaries)


def _print_diarization(
    summaries: Sequence[diarization.SegmentSummary], paths: SessionPaths
) -> None:
    for summary in summaries:
        if summary.outcome == "skipped":
            print(f"  {summary.index}. skipped: {summary.reason}")
            continue
        if summary.outcome == "failed":
            print(f"  {summary.index}. {summary.failure}")
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
