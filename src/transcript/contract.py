"""The Narrata transcript contract v1 (IOA-1214, 1.1: IOA-1287): schema and checks.

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
- with `recordings`, every passage starts inside one of them.

As in Narrata, a recording rule stays silent where the schema already reports
the value, so one defect is one violation.

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

CONTRACT_VERSION = "1.1"  # the latest minor this copy knows
SINGLE_RECORDING_VERSION = "1.0"  # a session of one recording needs nothing newer
RECORDINGS_SINCE = "1.1"  # the first version whose `source` may hold `recordings`
SUPPORTED_MAJOR = 1
SCHEMA_FILE = "transcript-v1.schema.json"
SCHEMA_SOURCE = (
    "ios-archiv e8bfb9702, ios-archiv-backend/resources/contracts/" + SCHEMA_FILE
)
SCHEMA_SHA256 = "019ae2df0cbe2a27a35a6e39d6416284d01251be48c3593207236acadd48e41d"

_VERSION = re.compile(r"([1-9][0-9]*)\.(0|[1-9][0-9]*)")


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
    """The violations of contract v1 in `document`; empty if it is valid."""
    data = document if isinstance(document, dict) else {}
    major = _major(data.get("contract_version"))
    if major is not None and major != SUPPORTED_MAJOR:
        return (f"/contract_version: unsupported major {major}",)
    passages = data.get("passages")
    passages = passages if isinstance(passages, list) else []
    found = sorted(
        (_pointer(error.absolute_path), tuple(error.absolute_path), error.validator)
        for error in _validator().iter_errors(document)
    )
    return (
        *(
            f"{_located(pointer, path, passages)}: {rule}"
            for pointer, path, rule in found
        ),
        *_rules(data, passages),
        *_recording_rules(data, passages),
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


def _recording_rules(data: dict[str, Any], passages: Sequence[Any]) -> Iterable[str]:
    source = data.get("source")
    if not isinstance(source, dict):
        return
    recordings = source.get("recordings")
    if not isinstance(recordings, list):
        return
    version = _version(data.get("contract_version"))
    since = _version(RECORDINGS_SINCE)
    if version is not None and since is not None and version < since:
        yield f"/source/recordings: needs contract version {RECORDINGS_SINCE} or later"
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
