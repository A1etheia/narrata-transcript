"""The Narrata transcript contract v1 (IOA-1214; 1.1: IOA-1287, 1.2: IOA-1224,
1.3: IOA-1300): schema and checks.

Narrata owns the contract. `contracts/transcript-v1.schema.json` is a copy of
the schema in the Narrata repository, never a version of our own; `SCHEMA_SOURCE`
names the commit it was copied from and `SCHEMA_SHA256` the copied bytes.
`validate` checks a document against it and against the rules a schema cannot
express (`docs/transcript-contract.md` in the Narrata repository, "Regeln
jenseits des Schemas"):

- `contract_version` has a supported major, else that is the only violation;
- passage ids are unique;
- passages are chronological: `start` never falls;
- `end` is not before `start`;
- `speaker_label` is a key of `speakers`;
- `source.recordings` only from `RECORDINGS_SINCE` on;
- `recordings[0]` repeats `source.file_name`, `duration_seconds` and
  `audio_sha256` and starts at 0;
- `recordings[].starts_at` never falls (recordings may overlap);
- with `recordings`, every passage starts inside one of them;
- `layers.it_ot` and `stats.it_ot` only from `IT_OT_SINCE` on;
- `source.kind` and `source.format` only from `UPLOAD_SINCE` on;
- outside an upload (`source.kind = upload`): no `source.format`, no `null`
  in times, `confidence_tier`, `markers[].at`, audio fields or `pipeline`
  (one violation per file), and no position ids (`u-…`).

The schema allows those `null`s and position ids by type, so the last rule is
what keeps a pipeline file as strict as before 1.3. The pipeline writes neither
the IT/OT layer nor uploads, so their own rules (blocks, spans and modes; an
upload's timing, ids and forbidden fields) are not repeated here: Narrata checks
them on import. As in Narrata, an upload skips the recording and IT/OT rules.

As in Narrata, a rule stays silent where the schema already reports the value,
so one defect is one violation.

The transcription context has a contract of its own with its own version
(`narrata.SUPPORTED_MAJOR`); the two rise independently.

A document holds transcript text and names, so a violation names the JSON path,
the rule and the passage id, never a value: `jsonschema`'s own messages quote
the value and are not used, a speaker label in a path shows as `*`, and an id
that does not match the schema's id pattern is not quoted. Nothing here logs or
writes.
"""

import functools
import json
import re
from collections.abc import Iterable, Sequence
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

CONTRACT_VERSION = "1.3"  # the latest minor this copy knows
SINGLE_RECORDING_VERSION = "1.0"  # a session of one recording needs nothing newer
RECORDINGS_SINCE = "1.1"  # the first version whose `source` may hold `recordings`
IT_OT_SINCE = "1.2"  # the first version with `layers.it_ot` and `stats.it_ot`
UPLOAD_SINCE = "1.3"  # the first version whose `source` may hold `kind`, `format`
SUPPORTED_MAJOR = 1
SCHEMA_FILE = "transcript-v1.schema.json"
SCHEMA_SOURCE = (
    "ios-archiv b1fa375ef, ios-archiv-backend/resources/contracts/" + SCHEMA_FILE
)
SCHEMA_SHA256 = "58f9fe56e0386763d12f6d0ba9098e18f109c4a26ef79613b4fa117792af5115"

_VERSION = re.compile(r"([1-9][0-9]*)\.(0|[1-9][0-9]*)")
# The schema's id form of an untimed upload (`u-<position>-…`); as Narrata's
# UploadSourceRules, kept here rather than taken apart from the id pattern.
_POSITION_ID = re.compile(r"u-[0-9]{6}-")
# The fields the schema types as nullable "only for source.kind = upload";
# re-check this list whenever the copy changes.
_NULLABLE_IN_SOURCE = ("duration_seconds", "audio_sha256")
_NULLABLE_IN_PASSAGE = ("start", "end", "confidence_tier")


def schema_bytes() -> bytes:
    """The copied schema file, unchanged."""
    return (resources.files("transcript") / "contracts" / SCHEMA_FILE).read_bytes()


@functools.cache
def load_schema() -> dict[str, Any]:
    """The contract's JSON schema, as copied from Narrata."""
    return json.loads(schema_bytes().decode("utf-8"))


@functools.cache
def _validator() -> Draft202012Validator:
    return Draft202012Validator(load_schema())


@functools.cache
def _passage_id() -> re.Pattern[str]:
    """The schema's own pattern of a passage id."""
    pattern = load_schema()["$defs"]["passage"]["properties"]["id"]["pattern"]
    return re.compile(pattern)


def validate(document: Any) -> tuple[str, ...]:
    """The violations of contract v1 in `document`; empty if it is valid.

    For an upload (`source.kind = upload`) empty means less: its own rules are
    Narrata's to check, so a caller that needs a pipeline file must say so.
    """
    data = document if isinstance(document, dict) else {}
    major = _major(data.get("contract_version"))
    if major is not None and major != SUPPORTED_MAJOR:
        return (f"/contract_version: unsupported major {major}",)
    passages = data.get("passages")
    passages = passages if isinstance(passages, list) else []
    source = data.get("source")
    source = source if isinstance(source, dict) else {}
    found = sorted(
        (_pointer(error.absolute_path), tuple(error.absolute_path), error.validator)
        for error in _validator().iter_errors(document)
    )
    upload = source.get("kind") == "upload"
    return (
        *(
            f"{_located(pointer, path, passages)}: {rule}"
            for pointer, path, rule in found
        ),
        *_rules(data, passages),
        *(() if upload else _recording_rules(data, source, passages)),
        *(() if upload else _it_ot_rules(data, passages)),
        *_source_rules(data, source, passages),
    )


def summarize(violations: Sequence[str], shown: int = 10) -> str:
    """`violations` for a message: the count, the first `shown`, the rest counted."""
    listed = "; ".join(violations[:shown])
    more = len(violations) - shown
    rest = f"; and {more} more" if more > 0 else ""
    return f"{len(violations)} contract violation(s): {listed}{rest}"


def _major(version: Any) -> int | None:
    """The major of a well-formed `contract_version`; the schema reports others."""
    parsed = _version(version)
    return None if parsed is None else parsed[0]


def _version(version: Any) -> tuple[int, int] | None:
    """Major and minor of a well-formed `contract_version`."""
    match = _VERSION.fullmatch(version) if isinstance(version, str) else None
    return None if match is None else (int(match.group(1)), int(match.group(2)))


def _needs(
    data: dict[str, Any], pointer: str, since: str, what: str = "needs"
) -> Iterable[str]:
    """A violation at `pointer` if a well-formed version predates `since`."""
    version, first = _version(data.get("contract_version")), _version(since)
    if version is not None and first is not None and version < first:
        yield f"{pointer}: {what} contract version {since} or later"


def _null(container: dict[str, Any], key: str) -> bool:
    """Whether `key` is present and null (absent is the schema's to report)."""
    return key in container and container[key] is None


def _rules(data: dict[str, Any], passages: Sequence[Any]) -> Iterable[str]:
    speakers = data.get("speakers")
    labels = speakers if isinstance(speakers, dict) else {}
    seen: dict[str, int] = {}
    previous_start: float | None = None
    for n, passage in enumerate(passages):
        if not isinstance(passage, dict):
            continue  # the schema reports it
        where = f"/passages/{n}{_passage_note(passage)}"
        passage_id = passage.get("id")
        if isinstance(passage_id, str):
            if passage_id in seen:
                yield f"{where}: duplicate id, also at /passages/{seen[passage_id]}"
            else:
                seen[passage_id] = n
        start, end = _number(passage.get("start")), _number(passage.get("end"))
        if start is not None:
            if previous_start is not None and start < previous_start:
                yield f"{where}: start before the previous passage"
            previous_start = start
            if end is not None and end < start:
                yield f"{where}: end before start"
        label = passage.get("speaker_label")
        if isinstance(label, str) and label not in labels:
            yield f"{where}: speaker_label not in speakers"


def _recording_rules(
    data: dict[str, Any], source: dict[str, Any], passages: Sequence[Any]
) -> Iterable[str]:
    recordings = source.get("recordings")
    if not isinstance(recordings, list):
        return
    yield from _needs(data, "/source/recordings", RECORDINGS_SINCE)
    spans = {
        n: span
        for n, recording in enumerate(recordings)
        if (span := _span(recording)) is not None
    }
    if 0 in spans and _repeats_source(recordings[0], source) is False:
        yield (
            "/source/recordings/0: does not repeat source file_name, "
            "duration_seconds and audio_sha256 or does not start at 0"
        )
    previous: float | None = None
    for n, (starts_at, _) in spans.items():
        if previous is not None and starts_at < previous:
            yield f"/source/recordings/{n}/starts_at: before the previous recording"
        previous = starts_at
    if len(spans) != len(recordings):
        return  # the timeline is unknown; the schema reports the recording
    for n, passage in enumerate(passages):
        start = _number(passage.get("start")) if isinstance(passage, dict) else None
        if start is None or any(a <= start <= b for a, b in spans.values()):
            continue
        yield f"/passages/{n}/start{_passage_note(passage)}: in no recording"


def _it_ot_rules(data: dict[str, Any], passages: Sequence[Any]) -> Iterable[str]:
    """The version of the IT/OT layer; its shape is Narrata's to check."""
    first = next(
        (
            n
            for n, passage in enumerate(passages)
            if isinstance(passage, dict)
            and isinstance(passage.get("layers"), dict)
            and "it_ot" in passage["layers"]
        ),
        None,
    )
    stats = data.get("stats")
    if first is not None:
        yield from _needs(data, f"/passages/{first}/layers/it_ot", IT_OT_SINCE)
    elif isinstance(stats, dict) and "it_ot" in stats:
        yield from _needs(data, "/stats/it_ot", IT_OT_SINCE)


def _source_rules(
    data: dict[str, Any], source: dict[str, Any], passages: Sequence[Any]
) -> Iterable[str]:
    """`source.kind` and what only an upload may do; an upload's own rules are Narrata's."""
    kind = source.get("kind", "pipeline")
    if kind not in ("pipeline", "upload"):
        return  # the schema reports it
    if "kind" in source or "format" in source:
        yield from _needs(data, "/source", UPLOAD_SINCE, "kind and format need")
    if kind == "upload":
        return
    if "format" in source:
        if "kind" not in source:
            # an upload that forgot to say so: one violation, not one per null
            yield "/source: format without kind upload"
            return
        yield "/source/format: only an upload carries a format"
    yield from _pipeline_rules(data, source, passages)


def _pipeline_rules(
    data: dict[str, Any], source: dict[str, Any], passages: Sequence[Any]
) -> Iterable[str]:
    """No `null` and no position id outside an upload, each once per file."""
    readable = [(n, p) for n, p in enumerate(passages) if isinstance(p, dict)]
    nulls = {n: found for n, p in readable if (found := _passage_nulls(p))}
    fields = [
        *(f"source.{field}" for field in _NULLABLE_IN_SOURCE if _null(source, field)),
        *(["pipeline"] if _null(data, "pipeline") else []),
        *dict.fromkeys(field for found in nulls.values() for field in found),
    ]
    if fields:
        first = next(iter(nulls), None)
        where = (
            "/"
            if first is None
            else f"/passages/{first}{_passage_note(passages[first])}"
        )
        yield f"{where}: only an upload may leave {', '.join(fields)} null"
    position = next(
        (
            n
            for n, passage in readable
            if isinstance(passage.get("id"), str) and _POSITION_ID.match(passage["id"])
        ),
        None,
    )
    if position is not None:
        note = _passage_note(passages[position])
        yield f"/passages/{position}/id{note}: position id outside an untimed upload"


def _passage_nulls(passage: dict[str, Any]) -> list[str]:
    """The fields of `passage` that are null and only an upload may leave null."""
    fields = [
        f"passages[].{field}" for field in _NULLABLE_IN_PASSAGE if _null(passage, field)
    ]
    markers = passage.get("markers")
    if isinstance(markers, list) and any(
        isinstance(marker, dict) and _null(marker, "at") for marker in markers
    ):
        fields.append("passages[].markers[].at")
    return fields


def _span(recording: Any) -> tuple[float, float] | None:
    """Start and end of a recording on the session timeline, if both are usable."""
    if not isinstance(recording, dict):
        return None
    starts_at = _number(recording.get("starts_at"))
    duration = _number(recording.get("duration_seconds"))
    if starts_at is None or duration is None or starts_at < 0 or duration < 0:
        return None
    return starts_at, starts_at + duration


def _repeats_source(first: Any, source: dict[str, Any]) -> bool | None:
    """Whether `first` is the top-level source; None when the schema has spoken."""
    if not isinstance(first, dict):
        return None
    fields = ("file_name", "audio_sha256")
    duration = _number(source.get("duration_seconds"))
    if duration is None or not all(
        isinstance(part.get(field), str) for part in (first, source) for field in fields
    ):
        return None
    return (
        all(first[field] == source[field] for field in fields)
        and _number(first.get("duration_seconds")) == duration
        and _number(first.get("starts_at")) == 0.0
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _pointer(path: Iterable[Any]) -> str:
    """A JSON pointer; the key under `speakers` is a label and shows as `*`."""
    parts = [str(part).replace("~", "~0").replace("/", "~1") for part in path]
    if len(parts) > 1 and parts[0] == "speakers":
        parts[1] = "*"
    return "/" + "/".join(parts)


def _located(pointer: str, path: tuple[Any, ...], passages: Sequence[Any]) -> str:
    """`pointer`, with the passage id after it when it lies in a passage."""
    if len(path) < 2 or path[0] != "passages" or not isinstance(path[1], int):
        return pointer
    index = path[1]
    passage = passages[index] if index < len(passages) else None
    return pointer + _passage_note(passage)


def _passage_note(passage: Any) -> str:
    """` (<id>)` for a passage with a well-formed id, else nothing."""
    passage_id = passage.get("id") if isinstance(passage, dict) else None
    if isinstance(passage_id, str) and _passage_id().fullmatch(passage_id):
        return f" ({passage_id})"
    return ""
