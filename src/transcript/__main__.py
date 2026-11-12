"""Command-line entry point: `config`, `doctor`, `extract`, `context`, `snapshot`,
`manifest`, `transcribe`, `diarize`, `assess`, `calibrate`, `review-export`,
`review-import`, `speakers`, `working`, `report`, `export`, `txt`, `docx`, and
`process`, which runs them in order."""

import argparse
import collections
import contextlib
import functools
import logging
import os
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from transcript import (
    __version__,
    audio,
    audio_tools,
    calibration,
    candidates,
    decisions,
    diagnosis,
    diarization,
    docx_render,
    export,
    hints,
    knowledge,
    lock,
    manifest,
    narrata,
    pipeline,
    preflight,
    rendering,
    report,
    review_import,
    review_sheet,
    speaker_samples,
    speakers,
    status,
    uncertainty,
    variant_suggestions,
    working,
)
from transcript.asr import BackendError
from transcript.asr.whisper import WhisperBackend
from transcript.config import LEVELS, Config, ConfigError, format_config, load_config
from transcript.diarization.pyannote import PyannoteDiarizer
from transcript.domain import DomainContext
from transcript.jsonfile import DataFileError
from transcript.narrata_client import NarrataClientError, fetch_context, read_token
from transcript.session import SessionKey, SessionPaths, input_root, input_sessions
from transcript.timecode import format_ms, parse_timecode
from transcript.transcription import (
    OUTCOME_STATUSES,
    SegmentOutcome,
    TranscriptionError,
    transcribe_session,
)

_DEFAULT_CONFIG = Path("config/config.yaml")
_EXAMPLE_CONFIG = Path("config/example.yaml")
_DOTENV = Path(".env")
_SHORT_ID = knowledge.SHORT_ID
_SHOWN_FINDINGS = 10  # the rest is in the diagnosis report
_SNAPSHOT_BEHIND = f"warning: {knowledge.BEHIND_CONTEXT}"
# the steps of a `process` run, for `pipeline.log` only: the console has its own lines
_PROCESS_LOG = logging.getLogger("transcript.process")
_PROCESS_LOG.propagate = False
_PROCESS_LOG.setLevel(logging.INFO)
_PROCESS_LOG.addHandler(logging.NullHandler())


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
    doctor_command = commands.add_parser(
        "doctor",
        help="Check tools, configuration and models before a run, and with a "
        "session also its input, knowledge and earlier artifacts; changes nothing.",
    )
    doctor_command.add_argument(
        "session", nargs="?", help="session key <group>/<ordinal> (default: none)"
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
    snapshot_command = commands.add_parser(
        "snapshot",
        help="Freeze a session's Narrata context as its knowledge snapshot.",
    )
    snapshot_command.add_argument("session", help="session key <group>/<ordinal>")
    snapshot_command.add_argument(
        "--refresh",
        action="store_true",
        help="build the snapshot again from the stored context and budget",
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
    assess_command = commands.add_parser(
        "assess",
        help="Rate the passages of a session's transcripts as confident, "
        "needs_review or uncertain.",
    )
    assess_command.add_argument("session", help="session key <group>/<ordinal>")
    assess_command.add_argument(
        "--segment",
        type=_positive_int,
        help="only this segment, counted from 1 as in the manifest (default: all)",
    )
    assess_command.add_argument(
        "--hints",
        action="store_true",
        help="first match the stored transcripts against the current knowledge "
        "snapshot again; the ASR result stays as it is",
    )
    calibrate_command = commands.add_parser(
        "calibrate",
        help="Measure the passage ratings against a hand-checked reference, or "
        "make and read a sheet of similar hints; prints counts only.",
    )
    calibrate_command.add_argument("session", help="session key <group>/<ordinal>")
    calibrate_command.add_argument(
        "--segment", type=_positive_int, help="segment the hand reference belongs to"
    )
    calibrate_command.add_argument(
        "--reference", type=Path, help="hand reference as a text file"
    )
    calibrate_command.add_argument(
        "--start", help="where the hand reference starts in the segment, HH:MM:SS.mmm"
    )
    calibrate_command.add_argument(
        "--end", help="where the hand reference ends in the segment, HH:MM:SS.mmm"
    )
    calibrate_command.add_argument(
        "--similar-sheet",
        action="store_true",
        help="write a sheet of similar hints to judge under review/calibration/",
    )
    calibrate_command.add_argument(
        "--similar-judged", type=Path, help="read a judged sheet of similar hints"
    )
    review_export_command = commands.add_parser(
        "review-export",
        help="Write the review candidates still to decide as a CSV for a spreadsheet.",
    )
    review_export_command.add_argument("session", help="session key <group>/<ordinal>")
    review_export_command.add_argument(
        "--all",
        action="store_true",
        help="list every candidate, decided ones with their decision",
    )
    review_export_command.add_argument(
        "--force",
        action="store_true",
        help="replace an existing sheet, with any decisions not imported yet",
    )
    review_import_command = commands.add_parser(
        "review-import",
        help="Read the decisions filled into the review sheet into decisions.json "
        "and suggest new ASR misrecognitions from the corrections.",
    )
    review_import_command.add_argument("session", help="session key <group>/<ordinal>")
    speakers_command = commands.add_parser(
        "speakers",
        help="List passages to listen to per speaker label, write the assignment "
        "template if there is none, and check the assignment.",
    )
    speakers_command.add_argument("session", help="session key <group>/<ordinal>")
    working_command = commands.add_parser(
        "working",
        help="Apply the review decisions and the speaker assignment to the "
        "reference transcripts and write the working version.",
    )
    working_command.add_argument("session", help="session key <group>/<ordinal>")
    report_command = commands.add_parser(
        "report",
        help="Write the closing report of the session's working version: counts, "
        "gaps and the configuration used, no transcript text.",
    )
    report_command.add_argument("session", help="session key <group>/<ordinal>")
    export_command = commands.add_parser(
        "export",
        help="Write the session's working version as Narrata transcript contract v1 "
        "to output/<session>/transcript.json, checked against the contract first.",
    )
    export_command.add_argument("session", help="session key <group>/<ordinal>")
    txt_command = commands.add_parser(
        "txt",
        help="Render the session's JSON export as plain text to "
        "output/<session>/transcript.txt; reads nothing else.",
    )
    txt_command.add_argument("session", help="session key <group>/<ordinal>")
    docx_command = commands.add_parser(
        "docx",
        help="Render the session's JSON export as a Word document to "
        "output/<session>/transcript.docx; reads nothing else.",
    )
    docx_command.add_argument("session", help="session key <group>/<ordinal>")
    status_command = commands.add_parser(
        "status",
        help="Show what is done and what is left of a session, or of every "
        "session under input/, from its files alone; changes nothing.",
    )
    status_command.add_argument(
        "session",
        nargs="?",
        help="session key <group>/<ordinal> (default: every session)",
    )
    process_command = commands.add_parser(
        "process",
        help="Run every step of a session from the preflight to the report, "
        "reusing what is in place; halts for the review sheet and the speaker "
        "assignment, and goes on when run again.",
    )
    process_command.add_argument("session", help="session key <group>/<ordinal>")
    process_command.add_argument(
        "--redo",
        choices=pipeline.REDOABLE,
        help="run this step again although its result is in place, and every "
        "later step with it",
    )
    process_command.add_argument(
        "--consent",
        action="store_true",
        help="note in the manifest that everyone audible agreed to the recording",
    )
    process_command.add_argument(
        "--num-speakers",
        type=_positive_int,
        help="number of people audible, for the diarization (default: model decides)",
    )
    for command in (
        config_command,
        doctor_command,
        extract_command,
        context_command,
        snapshot_command,
        manifest_command,
        transcribe_command,
        diarize_command,
        assess_command,
        calibrate_command,
        review_export_command,
        review_import_command,
        speakers_command,
        working_command,
        report_command,
        export_command,
        txt_command,
        docx_command,
        status_command,
        process_command,
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
        return _doctor(args.session, args.config)
    if args.command == "status":
        return _status(args.session, args.config)
    # pipeline steps log progress and failed attempts, to the console and the file
    with _log_to_stderr(), _session_log(args):
        if args.command == "extract":
            return _extract(args.session, args.config, args.stream)
        if args.command == "context":
            return _context(args.session, args.config, args.from_file)
        if args.command == "snapshot":
            return _snapshot(args.session, args.config, args.refresh)
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
        if args.command == "calibrate":
            return _calibrate(args)
        if args.command == "assess":
            return _assess(args.session, args.config, args.segment, args.hints)
        if args.command == "review-export":
            return _review_export(args.session, args.config, args.all, args.force)
        if args.command == "review-import":
            return _review_import(args.session, args.config)
        if args.command == "speakers":
            return _speakers(args.session, args.config)
        if args.command == "working":
            return _working(args.session, args.config)
        if args.command == "report":
            return _report(args.session, args.config)
        if args.command == "export":
            return _export(args.session, args.config)
        if args.command in ("txt", "docx"):
            return _render(args.session, args.config, args.command)
        if args.command == "process":
            return _process(args)
    parser.print_help()
    return 0


def _doctor(raw_key: str | None, config_path: Path, strict_resume: bool = False) -> int:
    """The preflight; only paths, counts and models reach the console (TOOL-66).

    Exit 0 when nothing stops a run, warnings included; 2 on any error.
    """
    try:
        key = None if raw_key is None else SessionKey.parse(raw_key)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    findings = preflight.run(config_path, key, strict_resume=strict_resume)
    for finding in findings:
        line = f"{finding.level}: {finding.check}: {finding.message}"
        print(line, file=sys.stdout if finding.level == "ok" else sys.stderr)
    warnings = preflight.warnings(findings)
    if preflight.blocked(findings):
        print(
            f"preflight failed: {preflight.errors(findings)} error(s), "
            f"{warnings} warning(s)",
            file=sys.stderr,
        )
        return 2
    checks = len({finding.check for finding in findings})
    print(f"preflight ok: {checks} checks, {warnings} warning(s)")
    return 0


def _status(raw_key: str | None, config_path: Path) -> int:
    """Step and session states; step names, counts and paths only (TOOL-66).

    With a session one line per step and a closing line, without one a line per
    session under `input/`. Exit 0, or 2 on an error.
    """
    try:
        key = None if raw_key is None else SessionKey.parse(raw_key)
        config = _load_config(config_path)
    except (ValueError, ConfigError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if key is not None:
        found = status.inspect(config.session_paths(key), config)
        print("\n".join((*status.step_lines(key, found), status.summary(key, found))))
        return 0
    keys = input_sessions(config.root)
    if not keys:
        print(f"no session under {input_root(config.root)}")
    for each in keys:
        print(status.summary(each, status.inspect(config.session_paths(each), config)))
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
        f"  {_tier_summary(glossary)}, "
        f"archive tier {glossary.archive_returned} of {glossary.archive_total}, "
        f"{len(glossary.ambiguities)} asr ambiguities"
    )
    print(f"wrote {paths.narrata_context}")
    _warn_if_snapshot_differs(paths, config)
    return 0


def _warn_if_snapshot_differs(paths: SessionPaths, config: Config) -> None:
    """A stored snapshot stays as it is; say so when the new context differs."""
    if not paths.knowledge_snapshot.is_file():
        return
    try:
        snapshot = knowledge.load_snapshot(paths)
        changed = knowledge.drift(snapshot, paths, config.keyword_budget)
    except DataFileError as error:
        print(f"warning: {error}", file=sys.stderr)
        return
    if changed.context_changed:
        print(_SNAPSHOT_BEHIND, file=sys.stderr)


def _tier_summary(glossary: narrata.NarrataGlossary) -> str:
    tiers = collections.Counter(entry.relevance for entry in glossary.entries)
    return (
        f"{len(glossary.entries)} glossary entries ("
        + ", ".join(f"{tiers[tier]} {tier}" for tier in narrata.RELEVANCE_TIERS)
        + ")"
    )


def _snapshot(raw_key: str, config_path: Path, refresh: bool) -> int:
    """Only counts, ids and positions reach the console, never names (TOOL-66)."""
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    paths = config.session_paths(key)
    exists = paths.knowledge_snapshot.is_file()
    try:
        if exists and not refresh:
            snapshot = knowledge.load_snapshot(paths)
            how = "reused"
        else:
            previous = _previous_id(paths) if exists else None
            snapshot = knowledge.build_snapshot(paths, config.keyword_budget)
            how = _built(previous, snapshot.snapshot_id, exists)
        changed = knowledge.drift(snapshot, paths, config.keyword_budget)
    except DataFileError as error:
        print(f"error: {error}", file=sys.stderr)
        if isinstance(error, knowledge.SnapshotError) and exists and not refresh:
            print("hint: transcript snapshot --refresh builds it anew", file=sys.stderr)
        _report_unusable(paths, error)
        return 2

    glossary = snapshot.glossary
    pc = sum(entry.relevance == "pc" for entry in snapshot.keyword_entries)
    budgeted = collections.Counter(
        entry.type for entry in snapshot.keyword_entries if entry.relevance != "pc"
    )
    print(
        f"{key}: snapshot {snapshot.snapshot_id[:_SHORT_ID]} {how}, "
        f"created {snapshot.created_at}, contract {snapshot.source.contract_version}"
    )
    print(
        f"  {len(snapshot.participants)} participant(s), {_tier_summary(glossary)}, "
        f"{len(glossary.ambiguities)} asr ambiguities"
    )
    print(
        f"  {len(snapshot.keyword_entries)} keyword entries: {pc} pc, "
        + ", ".join(
            f"{budgeted[t]}/{snapshot.keyword_budget.get(t, 0)} {t}"
            for t in narrata.ENTRY_TYPES
        )
    )
    if how != "reused":
        print(f"wrote {paths.knowledge_snapshot}")
    if changed.context_changed:
        print(_SNAPSHOT_BEHIND, file=sys.stderr)
    if changed.budget_changed:
        print(f"warning: {knowledge.BUDGET_CHANGED}", file=sys.stderr)
    findings = diagnosis.diagnose(snapshot.participants, glossary)
    diagnosis.write_report(paths.knowledge_diagnosis, findings, snapshot)
    _print_diagnosis(findings, paths.knowledge_diagnosis)
    return 0


def _report_unusable(paths: SessionPaths, error: DataFileError) -> None:
    """Replace the report, so no earlier one claims the knowledge is fine."""
    finding = diagnosis.unusable(error)
    try:
        diagnosis.write_report(paths.knowledge_diagnosis, [finding])
    except OSError as cause:
        print(f"warning: diagnosis report not written ({cause})", file=sys.stderr)


def _print_diagnosis(findings: Sequence[diagnosis.Finding], report: Path) -> None:
    errors, warnings = diagnosis.counts(findings)
    by_code = collections.Counter(f.code for f in findings)
    print(
        f"  diagnosis: {errors} error(s), {warnings} warning(s)"
        + "".join(f", {count} {code}" for code, count in by_code.items())
    )
    for finding in findings[:_SHOWN_FINDINGS]:
        print(f"    {diagnosis.describe(finding)}")
    if len(findings) > _SHOWN_FINDINGS:
        print(f"    … {len(findings) - _SHOWN_FINDINGS} more")
    print(f"wrote {report}")


def _previous_id(paths: SessionPaths) -> str | None:
    """The id of the snapshot about to be replaced; an unreadable one has none."""
    try:
        return knowledge.load_snapshot(paths).snapshot_id
    except DataFileError:
        return None


def _built(previous: str | None, current: str, existed: bool) -> str:
    """How a build relates to the snapshot it replaced, for the console."""
    if not existed:
        return "built"
    if previous == current:
        return "refreshed, knowledge unchanged"
    if previous is None:
        return "refreshed"
    return f"refreshed, was {previous[:_SHORT_ID]}"


def _fetch(key: SessionKey, config: Config, config_path: Path) -> bytes:
    if config.narrata_url is None:
        raise ConfigError(f"{config_path}: narrata.url is not set")
    group_id = config.narrata_groups.get(key.group)
    if group_id is None:
        raise ConfigError(
            f"{config_path}: narrata.groups has no group id for {key.group}"
        )
    token = read_token(os.environ, _DOTENV)
    return fetch_context(
        config.narrata_url,
        group_id,
        key.ordinal,
        token,
        recent_sessions=config.narrata_recent_sessions,
        archive_limit=config.narrata_archive_limit,
    )


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
        domain = _domain(paths)
        keywords = domain.transcription_keywords() if domain else ()
        snapshot_id = domain.origin.snapshot_id if domain else None
        if snapshot_id is not None:
            print(
                f"{key}: {len(keywords)} keyword(s) "
                f"from snapshot {snapshot_id[:_SHORT_ID]}"
            )
        backend = WhisperBackend.from_config(config)
        biasing = backend.capabilities.keyword_biasing
        if keywords and not biasing:
            print(
                f"{key}: keywords not passed: model {config.asr_model} takes no hotwords"
            )
        run = transcribe_session(
            paths,
            session_manifest,
            backend,
            config.language,
            keywords=keywords,
            force=force,
            indices=None if index is None else {index},
            progress=_print_outcome,
            retries=config.asr_retries,
            knowledge_snapshot_id=snapshot_id,
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
    counts = collections.Counter(outcome.status for outcome in run.outcomes)
    print(
        f"{key}: "
        + ", ".join(f"{counts[status]} {status}" for status in OUTCOME_STATUSES)
        + f" with {info.backend_id} {info.model_label}"
    )
    if keywords and biasing and run.keywords_used is not None:
        print(f"{key}: {run.keywords_used} of {len(keywords)} keyword(s) passed")
    if run.load_error is not None:
        print(f"error: {run.load_error}", file=sys.stderr)
    if not _write_hints(key, paths, config, domain, [o.index for o in run.outcomes]):
        return 2

    diarized = True  # False: the diarization could not run at all
    summaries: Sequence[diarization.SegmentSummary] = ()
    if diarizer is not None:
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
            diarized = False
        else:
            _print_diarization(summaries, paths)
    # Also after a failed diarization: the new transcripts get ratings.
    rated = _rate_passages(key, paths, config, [o.index for o in run.outcomes])
    if not (diarized and rated):
        return 2
    if diarizer is None:
        print(f"wrote {paths.asr_dir}")
    return 0 if run.complete and not _any_failed(summaries) else 1


def _assess(
    raw_key: str, config_path: Path, index: int | None, rebuild_hints: bool
) -> int:
    """Only counts reach the console (TOOL-66). Exit 0, or 2 on a problem.

    `rebuild_hints` matches the stored transcripts against the current snapshot
    first, so new knowledge reaches the review without a new ASR run.
    """
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        indices = [segment.index for segment in manifest.load_manifest(paths).segments]
        domain = _domain(paths) if rebuild_hints else None
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if index is not None:
        if index not in indices:
            print(f"error: segment {index} not in the manifest", file=sys.stderr)
            return 2
        indices = [index]
    if rebuild_hints and not _write_hints(key, paths, config, domain, indices):
        return 2
    return 0 if _rate_passages(key, paths, config, indices) else 2


def _write_hints(
    key: SessionKey,
    paths: SessionPaths,
    config: Config,
    domain: DomainContext | None,
    indices: Sequence[int],
) -> bool:
    """Write the review hints of `indices` and print their counts; False on a problem."""
    try:
        found = hints.review_session(paths, indices, domain, config.review_similar)
    except DataFileError as error:
        print(f"error: {error}", file=sys.stderr)
        return False
    if found is not None:
        print(
            f"{key}: review hints: {found['known_variant']} known variant(s), "
            f"{found['similar']} similar, {found['ambiguous']} ambiguous"
        )
    return True


def _calibrate(args: argparse.Namespace) -> int:
    """Only counts and shares reach the console, never text or names (TOOL-66)."""
    try:
        key = SessionKey.parse(args.session)
        config = _load_config(args.config)
        paths = config.session_paths(key)
        indices = [segment.index for segment in manifest.load_manifest(paths).segments]
        if args.similar_sheet:
            rows = calibration.similar_sheet(paths, indices)
            sheet = paths.review_dir / "calibration" / "similar-sheet.csv"
            calibration.write_sheet(sheet, rows)
            print(f"{key}: {len(rows)} similar hint(s) to judge")
            print(f"wrote {sheet}")
            return 0
        if args.similar_judged is not None:
            lines = calibration.judged_precision(args.similar_judged)
        else:
            lines = _measure(paths, config, indices, args)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for line in lines:
        print(f"{key}: {line}")
    return 0


def _measure(
    paths: SessionPaths,
    config: Config,
    indices: Sequence[int],
    args: argparse.Namespace,
) -> list[str]:
    """The report of the hand reference against the stored transcript."""
    if None in (args.segment, args.reference, args.start, args.end):
        raise ValueError(
            "calibrate needs --segment, --reference, --start and --end, "
            "or --similar-sheet, or --similar-judged"
        )
    if args.segment not in indices:
        raise ValueError(f"segment {args.segment} not in the manifest")
    report = calibration.measure(
        paths,
        args.segment,
        calibration.read_hand_reference(args.reference),
        parse_timecode(args.start),
        parse_timecode(args.end),
        config.review_uncertainty,
    )
    return report.lines()


def _review_export(
    raw_key: str,
    config_path: Path,
    include_all: bool,
    force: bool,
    skip_empty: bool = False,
) -> int:
    """Only counts and candidate IDs reach the console (TOOL-66). Exit 0 or 2.

    `skip_empty` writes no sheet when there is no row, for `process`.
    """
    try:
        key = SessionKey.parse(raw_key)
        paths = _load_config(config_path).session_paths(key)
        _require(paths.review_candidates, "review candidates", "assess")
        sheet = review_sheet.review_sheet(
            candidates.load_candidates(paths),
            decisions.load_decisions(paths),
            include_all,
        )
        if skip_empty and not sheet.rows:
            print(f"{key}: review: no candidate to decide")
            return 0
        review_sheet.write_sheet(paths, sheet, force)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"{key}: review sheet: {len(sheet.rows)} row(s){_by_status(sheet.counts)}")
    if sheet.stale:
        print(f"{key}: {len(sheet.stale)} stale decision(s), shown as earlier_decision")
    if sheet.orphaned:
        ids = ", ".join(decision.id for decision in sheet.orphaned)
        print(f"{key}: {len(sheet.orphaned)} orphaned decision(s), not listed: {ids}")
    print(f"wrote {paths.review_sheet}")
    return 0


def _review_import(raw_key: str, config_path: Path) -> int:
    """Only counts, rows, IDs and fields reach the console (TOOL-66).

    Exit 0, or 2 if the sheet is refused, a row was left out or the suggestions
    of new misrecognitions could not be made; the valid rows are stored either way.
    """
    try:
        key = SessionKey.parse(raw_key)
        paths = _load_config(config_path).session_paths(key)
        _require(paths.review_candidates, "review candidates", "assess")
        _require(paths.review_sheet, "review sheet", "review-export")
        found = candidates.load_candidates(paths)
        result = review_import.import_rows(
            found,
            decisions.load_decisions(paths),
            review_import.read_review_sheet(paths.review_sheet),
        )
        if result.changed:
            decisions.write_decisions(paths, result.decisions)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for problem in result.problems:
        print(f"error: {paths.review_sheet}: {problem}", file=sys.stderr)
    print(
        f"{key}: review import: {result.imported.total()} decision(s)"
        f"{_by_status(result.imported)}, {result.unchanged} unchanged, "
        f"{len(result.problems)} left out"
    )
    if result.changed:
        print(f"wrote {paths.review_decisions}")
    suggested = _suggest_variants(key, paths, found, result.decisions)
    return 2 if result.problems or not suggested else 0


def _speakers(raw_key: str, config_path: Path) -> int:
    """Only counts, segment and entry numbers reach the console (TOOL-66).

    Exit 0, 1 if an entry of the assignment is not applied, 2 on an error.
    """
    try:
        key = SessionKey.parse(raw_key)
        paths = _load_config(config_path).session_paths(key)
        found_manifest = manifest.load_manifest(paths)
        participants = knowledge.load_snapshot(paths).participants
        references = speakers.diarized_references(paths, found_manifest)
        if not references:
            raise ValueError(f"{key}: no diarized segment; run transcript diarize")
        created = speakers.write_template(paths, references)
        assignment = speakers.load_assignment(paths) or speakers.SpeakerAssignment()
        applied = speakers.check(assignment, references, participants)
        labels = speaker_samples.label_samples(found_manifest, references)
        speaker_samples.write_samples(
            paths, speaker_samples.render(key, labels, participants, applied)
        )
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"{key}: speakers: {len(references)} segment(s), {len(applied.labels)} "
        f"label(s){_by_status(applied.counts())}"
    )
    merge = sum(found.merge_candidate for found in labels)
    if merge:
        print(
            f"{key}: {merge} label(s) under {speaker_samples.MERGE_SHARE:.0%} "
            "of their segment's speech time, candidates for merging"
        )
    for split in applied.splits:
        print(
            f"warning: segment {split.segment}: {split.labels} labels assigned to "
            "one person, merged"
        )
    for finding in applied.findings:
        print(
            f"{key}: {_speaker_finding(finding.entry, finding.segment, finding.kind)}",
            file=sys.stderr,
        )
    if created:
        print(f"wrote template {paths.speaker_assignment}")
    print(f"wrote {paths.speaker_samples}")
    return 1 if applied.findings else 0


def _suggest_variants(
    key: SessionKey,
    paths: SessionPaths,
    found: candidates.SessionCandidates,
    made: decisions.SessionDecisions,
) -> bool:
    """Write the suggested misrecognitions; counts only (TOOL-66). False on a problem.

    Without a snapshot there is nothing to suggest for, and an older file goes.
    """
    try:
        suggested = variant_suggestions.review_session(
            paths, found, made, _domain(paths)
        )
    except DataFileError as error:
        print(f"error: {error}", file=sys.stderr)
        return False
    if suggested is None:
        print(
            f"{key}: no knowledge snapshot, no asr variant suggestions; "
            "run transcript snapshot"
        )
        return True
    print(
        f"{key}: asr variant suggestions: {len(suggested.suggestions)} new, "
        f"{suggested.known} known, {suggested.no_term} without glossary term"
    )
    print(f"wrote {paths.review_variant_suggestions}")
    return True


def _working(raw_key: str, config_path: Path) -> int:
    """Only counts, segment, passage and entry numbers reach the console (TOOL-66).

    Exit 0, 1 if something was not applied or a segment is missing, 2 on an error.
    """
    try:
        key = SessionKey.parse(raw_key)
        paths = _load_config(config_path).session_paths(key)
        result = working.compose(paths, manifest.load_manifest(paths))
        working.write_working(paths, result)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"{key}: working version: {len(result.blocks)} block(s)"
        f"{_by_status(result.counts())}"
    )
    if result.inputs.assignment_sha256 is None:
        print(
            f"{key}: no speaker assignment, every label stays open; "
            "run transcript speakers"
        )
    for finding in result.findings:
        print(f"{key}: {_working_finding(finding)}", file=sys.stderr)
    print(f"wrote {paths.working_transcript}")
    return 1 if result.findings else 0


def _report(raw_key: str, config_path: Path) -> int:
    """Only counts, codes and segment numbers reach the console (TOOL-66).

    Exit 0, 1 if the report names a gap, 2 on an error.
    """
    try:
        key = SessionKey.parse(raw_key)
        paths = _load_config(config_path).session_paths(key)
        result = report.compose(paths, manifest.load_manifest(paths))
        report.write_report(paths, result)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    review = result.review
    print(
        f"{key}: report: {result.passages.total} passage(s), "
        f"{review.candidates} candidate(s), {sum(review.decided.values())} decided, "
        f"{sum(review.unresolved.values())} open"
    )
    for note in result.notes:
        print(f"{key}: note: {note.code}{_segments_suffix(note.segments)}")
    for gap in result.gaps:
        print(
            f"{key}: gap: {gap.code}{_segments_suffix(gap.segments)}", file=sys.stderr
        )
    print(f"wrote {paths.report_json}")
    print(f"wrote {paths.report_markdown}")
    return 1 if result.gaps else 0


def _export(raw_key: str, config_path: Path) -> int:
    """Only counts, codes and the path reach the console (TOOL-66).

    Exit 0 once written, open passages included, since the contract carries
    them; 2 on an error or a refusal.
    """
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        document = export.compose(
            paths, manifest.load_manifest(paths), config.narrata_groups
        )
        export.write_export(paths, document)
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    passages = document["passages"]
    still_open = sum(p["review_status"] == "open" for p in passages)
    print(
        f"{key}: export: {len(passages)} passage(s), {still_open} open, "
        f"{len(document['speakers'])} speaker label(s)"
    )
    for gap in document["stats"]["gaps"]:
        print(
            f"{key}: gap: {gap['code']}{_segments_suffix(gap['segments'])}",
            file=sys.stderr,
        )
    print(f"wrote {paths.transcript_export}")
    return 0


def _render(raw_key: str, config_path: Path, kind: str) -> int:
    """Render the JSON export as `txt` or `docx` (TOOL-51, TOOL-52).

    Only counts and the path reach the console (TOOL-66). Exit 0 once written,
    open passages included; 2 on an error or a refusal.
    """
    try:
        key = SessionKey.parse(raw_key)
        config = _load_config(config_path)
        paths = config.session_paths(key)
        document = rendering.load_export(paths)
        found = rendering.paragraphs(document)
        rule = config.render_timestamps
        if kind == "txt":
            rendering.write_txt(paths, rendering.render_txt(found, rule))
            target = paths.transcript_text
        else:
            data = docx_render.render_docx(key, document, found, rule)
            docx_render.write_docx(paths, data)
            target = paths.transcript_document
    except (ValueError, ConfigError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    passages = document["passages"]
    still_open = sum(p["review_status"] == "open" for p in passages)
    print(
        f"{key}: {kind}: {len(passages)} passage(s), {len(found)} paragraph(s), "
        f"{still_open} open"
    )
    print(f"wrote {target}")
    return 0


def _process(args: argparse.Namespace) -> int:
    """Run the session's steps in order (TOOL-55); see `transcript.pipeline`.

    Each step is its command's handler, so it prints what that command prints
    (TOOL-66); this adds step names, statuses and paths only. Exit 0, 1 if the
    report names a gap or a step left something out, 2 on an error, 3 when the
    run halts for the review sheet or the speaker assignment.
    """
    try:
        key = SessionKey.parse(args.session)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    session, config = str(key), args.config

    @functools.cache
    def paths() -> SessionPaths:
        """Read after the preflight, which has checked the configuration."""
        return _load_config(config).session_paths(key)

    def step(
        name: pipeline.StepName,
        run: Callable[[bool], int],
        reusable: Callable[[], bool] | None = None,
        manual: bool = False,
        stop_on_incomplete: bool = False,
    ) -> pipeline.Step:
        def announced(forced: bool) -> int:
            say(f"{name}{' (redo)' if forced else ''}")
            code = run(forced)
            _PROCESS_LOG.info("%s: %s exit %d", session, name, code)
            return code

        return pipeline.Step(name, announced, reusable, manual, stop_on_incomplete)

    def say(message: str, stream: TextIO = sys.stdout) -> None:
        """A `process:` line on the console and the same line in `pipeline.log`."""
        print(f"process: {message}", file=stream, flush=True)
        _PROCESS_LOG.info("%s: process: %s", session, message)

    after_preflight = contextlib.ExitStack()  # the lock and the log, to the end

    def preflight(_: bool) -> int:
        """The strict preflight, then the lock and the log: nothing runs twice."""
        code = _doctor(session, config, strict_resume=args.redo is None)
        if code != pipeline.OK:
            return code
        try:
            paths().work_dir.mkdir(parents=True, exist_ok=True)
            replaced = after_preflight.enter_context(lock.held(paths()))
        except (OSError, lock.LockedError) as error:
            print(f"error: {error}", file=sys.stderr)
            return pipeline.FAILED
        after_preflight.enter_context(_pipeline_log(paths()))
        if replaced:
            say("replaced the lock of an interrupted run")
        return pipeline.OK

    steps = [
        step("preflight", preflight),
        step(
            "extract",
            lambda _: _extract(session, config, stream=0),
            reusable=lambda: _extracted(paths()),
        ),
        step(
            "context",
            lambda _: _context(session, config, None),
            reusable=lambda: paths().narrata_context.is_file(),
        ),
        step("snapshot", lambda forced: _snapshot(session, config, forced)),
        step(
            "manifest",
            lambda _: _manifest(session, config, args.consent),
            reusable=lambda: _manifest_in_place(paths(), args.consent),
        ),
        step(
            "transcribe",
            lambda forced: _transcribe(
                session,
                config,
                None,
                forced,
                diarize=True,
                num_speakers=args.num_speakers,
            ),
            stop_on_incomplete=True,
        ),
        step("review", lambda _: _review_step(session, config, paths()), manual=True),
        step(
            "speakers",
            lambda _: _speakers_step(session, config, paths()),
            manual=True,
            stop_on_incomplete=True,
        ),
        step("working", lambda _: _working(session, config)),
        step("export", lambda _: _export(session, config)),
        step("txt", lambda _: _render(session, config, "txt")),
        step("docx", lambda _: _render(session, config, "docx")),
        step("report", lambda _: _report(session, config)),
    ]
    with after_preflight:  # an exception, Ctrl-C too, leaves the lock for `status`
        try:
            outcome = pipeline.run(steps, args.redo)
        except BaseException:
            _PROCESS_LOG.info("%s: process: interrupted", session)
            raise
        say(", ".join(f"{r.step} {r.status}" for r in outcome.results))
        if outcome.stopped_at is not None:
            say(
                f"stopped at {outcome.stopped_at} (exit {outcome.exit_code})",
                sys.stderr,
            )
        if outcome.exit_code == pipeline.HALTED:
            _print_halt(key, paths(), outcome.halted)
            _PROCESS_LOG.info(
                "%s: process: halted for %s", session, ", ".join(outcome.halted)
            )
    return outcome.exit_code


def _extracted(paths: SessionPaths) -> bool:
    """Audio in place for every recording; without recordings, extract says why."""
    try:
        return audio.extracted(paths, len(audio.find_recordings(paths)))
    except audio.AudioError:
        return False


def _manifest_in_place(paths: SessionPaths, consent: bool) -> bool:
    """A manifest that needs no new run: present, and with consent if asked."""
    if not paths.manifest.is_file():
        return False
    if not consent:
        return True
    try:
        return manifest.load_manifest(paths).consent is not None
    except DataFileError:
        return False  # the manifest command says what is wrong


def _review_step(session: str, config: Path, paths: SessionPaths) -> int:
    """Import a filled sheet; without one, write it and halt if it has rows."""
    if paths.review_sheet.is_file():
        return _review_import(session, config)
    code = _review_export(session, config, False, False, skip_empty=True)
    return _halted_if_written(code, paths.review_sheet)


def _speakers_step(session: str, config: Path, paths: SessionPaths) -> int:
    """Check the assignment; without one, write the template and halt."""
    existed = paths.speaker_assignment.exists()
    code = _speakers(session, config)
    return code if existed else _halted_if_written(code, paths.speaker_assignment)


def _halted_if_written(code: int, path: Path) -> int:
    """HALTED when a step succeeded and left `path` for a person to fill in."""
    return pipeline.HALTED if code == 0 and path.exists() else code


def _print_halt(
    key: SessionKey, paths: SessionPaths, halted: Sequence[pipeline.StepName]
) -> None:
    """What to fill in before the next run; paths only (TOOL-66)."""
    print("process: halted for manual steps")
    if "review" in halted:
        print(f"  review: fill in the decisions in {paths.review_sheet}")
    if "speakers" in halted:
        print(
            f"  speakers: assign the labels in {paths.speaker_assignment}, "
            f"passages to listen to are in {paths.speaker_samples}"
        )
    print(
        f"then run transcript process {key} again; what is left open stays "
        "open and is named in the report"
    )


def _segments_suffix(segments: Sequence[int]) -> str:
    """`" (segment 1, 3)"`, or nothing for the whole session."""
    return f" (segment {', '.join(map(str, segments))})" if segments else ""


def _working_finding(finding: working.WorkingFinding) -> str:
    where = f"segment {finding.segment}"
    if finding.kind == "missing_segment":
        return f"{where}: no transcript, left out"
    if finding.kind == "speaker_entry":
        assert finding.entry is not None and finding.speaker_kind is not None
        found = _speaker_finding(finding.entry, finding.segment, finding.speaker_kind)
        return f"speaker {found}"
    reason = "stale" if finding.kind == "stale_decision" else "orphaned"
    return f"{where}, passage {finding.passage}: decision not applied: {reason}"


def _speaker_finding(entry: int, segment: int, kind: speakers.FindingKind) -> str:
    """`"entry 2 (segment 1) not applied: unknown person"`; no label, no id."""
    return f"entry {entry} (segment {segment}) not applied: {kind.replace('_', ' ')}"


def _require(path: Path, what: str, command: str) -> None:
    """`ValueError` pointing at the command that writes `path`, if it is missing."""
    if not path.is_file():
        raise ValueError(f"{path}: {what} not found; run transcript {command}")


def _by_status(counts: Mapping[str, int]) -> str:
    """`": 1 corrected, 2 kept"`, or nothing without counts."""
    listed = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
    return f": {listed}" if listed else ""


def _rate_passages(
    key: SessionKey, paths: SessionPaths, config: Config, indices: Sequence[int]
) -> bool:
    """Write the ratings of `indices` and the session's review candidates.

    Prints their counts only (TOOL-66); False on a problem.
    """
    try:
        counts = uncertainty.assess_session(paths, indices, config.review_uncertainty)
        found = candidates.session_candidates(paths, manifest.load_manifest(paths))
    except DataFileError as error:
        print(f"error: {error}", file=sys.stderr)
        return False
    print(
        f"{key}: passages: " + ", ".join(f"{counts[level]} {level}" for level in LEVELS)
    )
    rate = "" if found.per_hour is None else f" ({found.per_hour} per hour of audio)"
    print(f"{key}: review candidates: {len(found.candidates)}{rate}")
    print(f"wrote {paths.review_dir}")
    return True


def _domain(paths: SessionPaths) -> DomainContext | None:
    """The stored snapshot's knowledge; `transcribe` never builds one itself."""
    if not paths.knowledge_snapshot.is_file():
        return None
    return DomainContext.load(paths)


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
    if not _rate_passages(key, paths, config, [s.index for s in summaries]):
        return 2
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
def _pipeline_log(paths: SessionPaths) -> Iterator[None]:
    """Append the `transcript` logs and the run's steps to `pipeline.log` (TOOL-77).

    Only once `work/<s>/` exists; the file is opened on the first line. The text
    logger `transcript.text.*` does not propagate, and failed attempts are logged
    without `exc_info`, so neither text nor a runtime's own message gets here.
    """
    if not paths.work_dir.is_dir():
        yield
        return
    loggers = (logging.getLogger("transcript"), _PROCESS_LOG)
    handler = logging.FileHandler(paths.pipeline_log, encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.setLevel(logging.INFO)
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
        handler.close()


def _session_log(args: argparse.Namespace) -> contextlib.AbstractContextManager[None]:
    """`_pipeline_log` for a command's session, if it names a valid one.

    A command with an invalid key or configuration says so itself; `process`
    opens the log after its preflight, once it has made `work/<s>/`.
    """
    raw = getattr(args, "session", None)
    if raw is None or args.command == "process":
        return contextlib.nullcontext()
    try:
        paths = _load_config(args.config).session_paths(SessionKey.parse(raw))
    except (ValueError, ConfigError):
        return contextlib.nullcontext()
    return _pipeline_log(paths)


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
