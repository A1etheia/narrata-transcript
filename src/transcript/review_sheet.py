"""Review sheet: the open review candidates as a CSV for a spreadsheet (TOOL-47).

One row per candidate (TOOL-36), in recording order, with its decision (TOOL-46)
if one applies. By default only candidates still to be decided appear:
`open`, which includes those whose decision is stale, and `deferred`. Confident
passages never appear, since they are no candidates.

The file is made for a spreadsheet in a German locale: `;` between cells, UTF-8
with a byte order mark, CRLF between rows. A free-text cell starting like a
formula gets a leading `'`, so that "- Ja, genau" stays text; the reimport
(TOOL-48) reads `id`, `status`, `target_text`, `note` and `version` and removes
that mark again. The recognised text itself is never read back.

The sheet holds recognised text, archive names and notes, so it stays under
`work/`; this module logs nothing, and its errors name the file only.
"""

import csv
import io
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from transcript.candidates import SessionCandidates
from transcript.decisions import (
    ReviewDecision,
    ReviewItem,
    ReviewStatus,
    SessionDecisions,
    review_items,
)
from transcript.hints import Hint
from transcript.jsonfile import DataFileError, write_bytes_atomic
from transcript.session import SessionPaths
from transcript.timecode import format_ms
from transcript.uncertainty import PassageRating, Reason

SHEET_COLUMNS = (
    "id",
    "start",  # session time
    "end",
    "segment",
    "segment_start",  # time in the segment's WAV, to find the passage by ear
    "speaker",
    "level",
    "order",  # position in the review order of the candidates
    "reasons",
    "missing",
    "hints",
    "text",  # as recognised; shown only, never read back
    "status",
    "target_text",
    "note",
    "earlier_decision",  # a stale decision, made on another transcript version
    "version",  # the transcript version the row shows
)
PENDING: frozenset[ReviewStatus] = frozenset({"open", "deferred"})
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class SheetError(DataFileError):
    """The review sheet cannot be written."""


@dataclass(frozen=True)
class ReviewSheet:
    rows: tuple[tuple[str, ...], ...]  # cells in the order of `SHEET_COLUMNS`
    counts: Counter[ReviewStatus]  # rows per status
    stale: tuple[ReviewDecision, ...]  # all of them, shown or not
    orphaned: tuple[ReviewDecision, ...]  # their candidate is gone; not in rows


def review_sheet(
    found: SessionCandidates, decisions: SessionDecisions, include_all: bool = False
) -> ReviewSheet:
    """The rows of the candidates still to decide, or of all with `include_all`."""
    state = review_items(found, decisions)
    order = {candidate.id: n for n, candidate in enumerate(found.candidates, 1)}
    version = found.processed_at
    shown = sorted(
        (item for item in state.items if include_all or item.status in PENDING),
        key=lambda item: (item.candidate.segment, item.candidate.passage),
    )
    return ReviewSheet(
        rows=tuple(
            _row(item, order[item.candidate.id], version[item.candidate.segment])
            for item in shown
        ),
        counts=Counter(item.status for item in shown),
        stale=state.stale,
        orphaned=state.orphaned,
    )


def _row(item: ReviewItem, order: int, version: str) -> tuple[str, ...]:
    candidate, decision, span = item.candidate, item.decision, item.candidate.time
    start, end, local = (
        ("", "", "")
        if span is None
        else (_time(span.start_ms), _time(span.end_ms), _time(span.local_start_ms))
    )
    target, note = (
        (None, None) if decision is None else (decision.target_text, decision.note)
    )
    return (
        candidate.id,
        start,
        end,
        str(candidate.segment),
        local,
        candidate.speaker or "",
        candidate.level,
        str(order),
        _reasons(candidate.rating),
        ", ".join(candidate.rating.missing),
        _text(_hints(candidate.hints)),
        _text(candidate.text),
        item.status,
        _text(target),
        _text(note),
        "" if item.earlier is None else _earlier(item.earlier),
        version,
    )


def _time(ms: int | None) -> str:
    return "" if ms is None else format_ms(ms)


def _reasons(rating: PassageRating) -> str:
    return "; ".join(_reason(reason) for reason in rating.reasons)


def _reason(reason: Reason) -> str:
    if reason.value is None:
        return reason.rule
    threshold = "" if reason.threshold is None else f"/{_number(reason.threshold)}"
    return f"{reason.rule} {_number(reason.value)}{threshold}"


def _number(value: float) -> str:
    return f"{round(value, 3):g}"


def _hints(hints: Iterable[Hint]) -> str:
    return "\n".join(_hint(hint) for hint in hints)


def _hint(hint: Hint) -> str:
    entries = " | ".join(
        f"{c.type} {c.id} {c.term} ({c.kind}, {c.relevance})" for c in hint.candidates
    )
    ambiguous = " ambiguous" if hint.ambiguous else ""
    return f"{hint.signal} „{hint.heard}“ → {entries}{ambiguous}"


def _earlier(decision: ReviewDecision) -> str:
    return f"{decision.status} {decision.decided_at}, older transcript"


def _text(value: str | None) -> str:
    """A free-text cell; one that starts like a formula gets a leading `'`."""
    if not value:
        return ""
    return f"'{value}" if value.startswith(FORMULA_START) else value


def render(sheet: ReviewSheet) -> bytes:
    """The sheet as CSV for a German spreadsheet: `;`, UTF-8 with BOM, CRLF."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(SHEET_COLUMNS)
    writer.writerows(sheet.rows)
    return buffer.getvalue().encode("utf-8-sig")


def write_sheet(paths: SessionPaths, sheet: ReviewSheet, force: bool = False) -> None:
    """Write the session's review sheet atomically; never replace one unasked.

    An existing sheet may hold decisions not imported yet, so it is replaced
    only with `force`.
    """
    path = paths.review_sheet
    if path.exists() and not force:
        raise SheetError(
            f"{path}: exists and may hold decisions not imported yet; "
            "use --force to replace it"
        )
    write_bytes_atomic(path, render(sheet))
