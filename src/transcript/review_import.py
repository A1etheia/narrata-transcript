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
    ReviewItem,
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
    result = decisions
    imported: Counter[ReviewStatus] = Counter()
    unchanged = 0
    problems = []
    for number, cells in rows:
        candidate = cells["id"]
        try:
            if not candidate:
                raise ValueError("field 'id' missing")
            item = items.get(candidate)
            if item is None:
                raise ValueError("no such candidate")
            wanted = (
                _status(cells["status"]),
                _unmarked(cells["target_text"]),
                _unmarked(cells["note"]),
            )
            if wanted == _in_force(item):
                unchanged += 1
                continue
            # only a change needs the version: an untouched row of an older
            # export is no error after the segment was transcribed again
            if cells["version"] != version[item.candidate.segment]:
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


def _in_force(item: ReviewItem) -> tuple[ReviewStatus, str | None, str | None]:
    decision = item.decision
    if decision is None:
        return "open", None, None
    return decision.status, decision.target_text, decision.note


def _shown(candidate: str) -> str:
    """The cell as ID if it looks like one; anything else may be someone's text."""
    if not candidate:
        return "no id"
    return candidate if _ID.fullmatch(candidate) else "invalid id"
