"""The session's transcript as Narrata contract v1 (TOOL-69, IOA-1214).

The export reads the stored working version and its closing report and adds no
rule about the transcript itself: text and status come from the working version,
markers from `markers.block_markers`, times from `session_time.passage_span`,
`stats` is the report unchanged.

What the contract needs and the working version holds differently:

- Speaker labels hold per segment; the contract's are session wide, so a label
  becomes `s<NN>-<label>`, e.g. `s01-SPEAKER_00`. A passage without a label is
  `unlabelled`. In `speakers`, only a label assigned to a person names one; an
  open, unknown, several-people or missing label is `null`.
- A passage id is minted as `p-<session start in ms, 8 digits>-<label slug>`,
  with `-2`, `-3`, … for a second or third passage with the same start and
  label. Start and label come from the reference transcript, which no review
  changes, so a re-export after more review keeps every id; only transcribing
  or diarizing again makes new passages, with new ids.
- An unintelligible passage has the text `""` and an `unintelligible` marker;
  the recognised text stays in `asr_text`. An open passage is
  `review_status: open`, not a marker.

The contract needs a start and an end for every passage, one recording per
session (more: IOA-1287) and integer Narrata ids; a working version that cannot
give them is an `ExportError`, never filled in.

`write_export` stores the document as `output/<s>/transcript.json` after
`contract.validate` found nothing; with sorted keys and no time stamp, equal
inputs give an equal file. The file holds text, names and user ids; it goes to
Narrata only by an import someone starts (IOA-1218). Nothing here logs; error
messages name segment, passage, field and contract rule, never text, a name or
an id.
"""

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from transcript.contract import SINGLE_RECORDING_VERSION, summarize, validate
from transcript.decisions import ReviewStatus
from transcript.jsonfile import DataFileError, write_bytes_atomic
from transcript.knowledge import load_snapshot
from transcript.manifest import Manifest, Segment
from transcript.markers import Marker, MarkerKind, block_markers
from transcript.narrata import Participant
from transcript.report import Pipeline, SessionReport, Used, report_json
from transcript.report import compose as compose_report
from transcript.session import SessionPaths, segment_name
from transcript.session_time import passage_span
from transcript.speakers import SpeakerRef, UserId
from transcript.working import Block, WorkingTranscript, load_working

UNLABELLED = "unlabelled"

_REVIEW_STATUS: dict[ReviewStatus, str] = {
    "confirmed": "confirmed",
    "kept": "confirmed",  # reviewed, text left as recognised
    "corrected": "corrected",
    "unintelligible": "corrected",  # reviewed, text replaced by nothing
}
# `unresolved` is a review status in the contract, not a marker
_CONTRACT_MARKERS: frozenset[MarkerKind] = frozenset(
    {"unintelligible", "speaker_unclear", "crosstalk"}
)


class ExportError(DataFileError):
    """The working version cannot be exported as contract v1."""


@dataclass(frozen=True)
class _Timed:
    """A block with its session time, which the contract requires."""

    start_ms: int
    end_ms: int
    block: Block


def build(
    stored: WorkingTranscript,
    manifest: Manifest,
    report: SessionReport,
    participants: Sequence[Participant],
    group_id: int,
) -> dict[str, Any]:
    """The contract v1 document of `stored`, the working version `report` describes.

    `participants` are those of the knowledge snapshot, for the display names;
    `group_id` is the Narrata id of the session's group.
    """
    if not stored.blocks:
        raise ExportError("the working version has no passages; nothing to export")
    segments = {segment.index: segment for segment in manifest.segments}
    timed = sorted(
        (_timed(block, segments) for block in stored.blocks),
        key=lambda t: (t.start_ms, t.block.segment, t.block.passage),
    )
    names = {p.user_id: p.display_name for p in participants}
    split = len(manifest.segments) > 1
    speakers: dict[str, dict[str, Any] | None] = {}
    used: set[str] = set()
    passages = []
    for found in timed:
        label = session_label(found.block)
        speaker = speakers[label] = _speaker(found.block.speaker, names)
        participant_id = None if speaker is None else speaker["participant_id"]
        passage_id = _mint(found.start_ms, label, used)
        passages.append(
            _passage(found, passage_id, label, participant_id, manifest, split)
        )
    return {
        "contract_version": SINGLE_RECORDING_VERSION,
        "tool_version": report.pipeline.tool_version,
        "session": {
            "group": group_id,
            "ordinal": manifest.key.ordinal,
            "play_session_id": _integer(manifest.play_session_id, "play_session_id"),
            "session_date": manifest.session_date.isoformat(),
        },
        "source": _source(manifest),
        "pipeline": _pipeline(report.pipeline, stored.inputs.knowledge_snapshot_id),
        "speakers": speakers,
        "stats": report_json(report),
        "passages": passages,
    }


def compose(
    paths: SessionPaths,
    manifest: Manifest,
    groups: Mapping[str, int],
    closing: SessionReport | None = None,
) -> dict[str, Any]:
    """The export of the session's stored working version.

    `groups` maps group slugs to Narrata group ids (`narrata.groups`); `closing`
    is the report of the current files if the caller has composed it already.
    A missing, outdated or invalid input is a `DataFileError`.
    """
    group_id = groups.get(paths.key.group)
    if group_id is None:
        raise ExportError(
            f"narrata.groups has no group id for {paths.key.group}; "
            "add it to the configuration"
        )
    if closing is None:
        closing = compose_report(paths, manifest)  # refuses an outdated working version
    return build(
        load_working(paths),
        manifest,
        closing,
        load_snapshot(paths).participants,
        group_id,
    )


def encode(document: dict[str, Any]) -> bytes:
    """The bytes `write_export` writes for `document`."""
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def write_export(paths: SessionPaths, document: dict[str, Any]) -> None:
    """Validate `document` as it would be read back, then replace the export.

    A document with a contract violation is an `ExportError`; nothing is written.
    """
    raw = encode(document)
    violations = validate(json.loads(raw))
    if violations:
        raise ExportError(
            f"{paths.transcript_export}: not written, {summarize(violations)}"
        )
    write_bytes_atomic(paths.transcript_export, raw)


def session_label(block: Block) -> str:
    """The block's label as the contract names it, unique within the session."""
    label = block.speaker.label
    return UNLABELLED if label is None else f"s{block.segment:02d}-{label}"


def _timed(block: Block, segments: Mapping[int, Segment]) -> _Timed:
    where = f"segment {block.segment}, passage {block.passage}"
    segment = segments.get(block.segment)
    if segment is None:
        raise ExportError(f"{where}: segment is not in the manifest")
    try:
        span = passage_span(segment, block)
    except ValueError:
        raise ExportError(f"{where}: time lies outside the segment") from None
    if span is None or span.start_ms is None or span.end_ms is None:
        raise ExportError(f"{where}: no start or end time; contract v1 needs both")
    return _Timed(span.start_ms, span.end_ms, block)


def _speaker(ref: SpeakerRef, names: Mapping[UserId, str]) -> dict[str, Any] | None:
    if ref.assigned != "person":
        return None
    return {
        "participant_id": _integer(ref.user_id, "user_id"),
        "display_name": names.get(ref.user_id),
    }


def _mint(start_ms: int, label: str, used: set[str]) -> str:
    """A new passage id, unique among `used`, which it joins."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    base = f"p-{start_ms:08d}-{slug}"
    minted, n = base, 1
    while minted in used:
        n += 1
        minted = f"{base}-{n}"
    used.add(minted)
    return minted


def _passage(
    found: _Timed,
    passage_id: str,
    label: str,
    participant_id: int | None,
    manifest: Manifest,
    split: bool,
) -> dict[str, Any]:
    block = found.block
    text = block.text or ""
    return {
        "id": passage_id,
        "start": _seconds(found.start_ms),
        "end": _seconds(found.end_ms),
        "speaker_label": label,
        "participant_id": participant_id,
        "text": text,
        "asr_text": None if block.asr_text == text else block.asr_text,
        "confidence_tier": block.level,
        "review_status": _review_status(block),
        "review_note": None,
        "markers": [
            {"type": marker.kind, "at": _seconds(_marker_ms(marker, block))}
            for marker in block_markers(block, manifest)
            if marker.kind in _CONTRACT_MARKERS
        ],
        "segment_ref": segment_name(block.segment) if split else None,
        "knowledge_hints": [],
        "layers": {},
    }


def _marker_ms(marker: Marker, block: Block) -> int:
    """The marker's session time, which every timed block's marker has."""
    if marker.at_ms is None:
        raise ExportError(
            f"segment {block.segment}, passage {block.passage}: marker without time"
        )
    return marker.at_ms


def _review_status(block: Block) -> str:
    if block.origin == "automatic":
        return "unreviewed"
    if block.origin == "open" or block.status is None:
        return "open"
    return _REVIEW_STATUS[block.status]


def _source(manifest: Manifest) -> dict[str, Any]:
    recordings = {
        segment.source.sha256: segment.source for segment in manifest.segments
    }
    if len(recordings) > 1:
        raise ExportError(
            f"the session has {len(recordings)} recordings; contract v1 holds one "
            "(see IOA-1287)"
        )
    (source,) = recordings.values()
    return {
        "file_name": source.file,
        "duration_seconds": _seconds(manifest.duration_ms),
        "audio_sha256": source.sha256,
    }


def _pipeline(pipeline: Pipeline, knowledge_snapshot_id: str) -> dict[str, Any]:
    ran = {
        "asr": [dataclasses.asdict(u) for u in pipeline.asr],
        "diarization": [dataclasses.asdict(u) for u in pipeline.diarization],
        "thresholds": [dataclasses.asdict(u) for u in pipeline.thresholds],
    }
    canonical = json.dumps(ran, sort_keys=True, separators=(",", ":"))
    return {
        "backend": _joined(pipeline.asr, "backend_id"),
        "model": _joined(pipeline.asr, "model"),
        "config_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "thresholds": {"uncertainty": ran["thresholds"]},
    }


def _joined(used: Sequence[Used], key: str) -> str:
    """The distinct values of `key`, in segment order, joined by `+`."""
    return "+".join(dict.fromkeys(str(u.values[key]) for u in used))


def _integer(value: Any, name: str) -> int:
    """A Narrata id as the contract needs it: a positive integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExportError(f"field {name!r} is no integer id; contract v1 needs one")
    return value


def _seconds(ms: int) -> float:
    return ms / 1000
