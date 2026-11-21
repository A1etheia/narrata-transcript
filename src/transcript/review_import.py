"""Review import: the decisions filled into the review sheet, read back (TOOL-48).

The sheet (TOOL-47) is edited in a spreadsheet; this module reads its columns
`id`, `status`, `target_text`, `note` and `version` and turns every row that
differs from the decision in force into a decision (TOOL-46). A row that fails
its checks is reported and left out, the other rows are still taken. The whole
sheet is refused only if a column is missing or an ID appears twice, since then
no row can be trusted to mean one candidate.

A row unchanged since the export is no decision, so a sheet imported as it
was exported changes nothing, and importing the same sheet twice neither.
Candidates and transcript are only read.

The sheet holds corrected text and notes; messages name file, row, candidate ID
and field only, never a cell's content, and this module logs nothing.
"""

import datetime
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from transcript.candidates import SessionCandidates
from transcript.decisions import (
    STATUSES,
    ReviewDecision,
    ReviewStatus,
    SessionDecisions,
    decide,
    review_items,
)
from transcript.jsonfile import DataFileError
from transcript.review_sheet import FORMULA_START
from transcript.sheetfile import Row, read_sheet

IMPORT_COLUMNS = ("id", "status", "target_text", "note", "version")
_ID = re.compile(r"s\d{2}-p\d{4}")


class ReviewImportError(DataFileError):
    """The review sheet cannot be imported at all."""


@dataclass(frozen=True)
class ImportResult:
    decisions: SessionDecisions  # all of them, the imported ones included
    imported: Counter[ReviewStatus]  # rows taken, per status
    unchanged: int  # rows that match the decision in force
    problems: tuple[str, ...]  # one per row left out: row, ID and field

    @property
    def changed(self) -> bool:
        return bool(self.imported)


def read_review_sheet(path: Path) -> list[Row]:
    """The non-empty rows of the sheet; `ReviewImportError` if none can be trusted."""
    columns, rows = read_sheet(path, "review sheet", ReviewImportError)
    missing = [column for column in IMPORT_COLUMNS if column not in columns]
    if missing:
        raise ReviewImportError(
            f"{path}: review sheet lacks column(s) {', '.join(missing)}"
        )
    first: dict[str, int] = {}
    for number, cells in rows:
        candidate = cells["id"]
        if candidate and candidate in first:
            raise ReviewImportError(
                f"{path}: rows {first[candidate]} and {number}: "
                f"{_shown(candidate)} appears twice"
            )
        first[candidate] = number
    return rows


def import_rows(
    found: SessionCandidates,
    decisions: SessionDecisions,
    rows: Sequence[Row],
    now: datetime.datetime | None = None,
) -> ImportResult:
    """`decisions` with every valid, changed row of the sheet decided."""
    items = {item.candidate.id: item for item in review_items(found, decisions).items}
    version = found.processed_at
    made_on = {(d.id, d.reference_processed_at): d for d in decisions.decisions}
    result = decisions
    imported: Counter[ReviewStatus] = Counter()
    unchanged = 0
    problems = []
    for number, cells in rows:
        candidate = cells["id"]
        try:
            if not candidate:
                raise ValueError("field 'id' missing")
            if not _ID.fullmatch(candidate):
                raise ValueError("no such candidate")
            # a row of an older export numbers the passages of its own version,
            # which a cut may have renumbered since: it is untouched if it shows
            # the decision made on that version, whatever the id means today
            older = cells["version"] != version.get(int(candidate[1:3]))
            item = None if older else items.get(candidate)
            if not older and item is None:
                raise ValueError("no such candidate")
            wanted = (
                _status(cells["status"]),
                _unmarked(cells["target_text"]),
                _unmarked(cells["note"]),
            )
            in_force = (
                made_on.get((candidate, cells["version"]))
                if item is None
                else item.decision
            )
            if wanted == _state(in_force):
                unchanged += 1
                continue
            if older:
                raise ValueError(
                    "field 'version' is not the current transcript; export again"
                )
            result = decide(result, found, candidate, *wanted, now=now)
            imported[wanted[0]] += 1
        except ValueError as error:
            problems.append(f"row {number} ({_shown(candidate)}): {error}")
    return ImportResult(result, imported, unchanged, tuple(problems))


def _status(cell: str) -> ReviewStatus:
    status = cell.casefold() or "open"
    if status not in STATUSES:
        raise ValueError("field 'status' invalid")
    return cast(ReviewStatus, status)


def _unmarked(cell: str) -> str | None:
    """A free-text cell without the formula mark of the export; `None` if empty."""
    if cell.startswith("'") and cell[1:].startswith(FORMULA_START):
        cell = cell[1:]
    return cell or None


def _state(
    decision: ReviewDecision | None,
) -> tuple[ReviewStatus, str | None, str | None]:
    """What a row shows for `decision`; an undecided candidate is open."""
    if decision is None:
        return "open", None, None
    return decision.status, decision.target_text, decision.note


def _shown(candidate: str) -> str:
    """The cell as ID if it looks like one; anything else may be someone's text."""
    if not candidate:
        return "no id"
    return candidate if _ID.fullmatch(candidate) else "invalid id"
