"""Reading CSV sheets that someone filled in with a spreadsheet.

A spreadsheet in a German locale saves with `;`, one in an English locale with
`,`; the header line tells which. Error messages name the file only, never a
cell: sheets may hold names of real people.
"""

import csv
from pathlib import Path

from transcript.jsonfile import DataFileError

Row = tuple[int, dict[str, str]]  # row number as the spreadsheet shows it; cells


def read_sheet(
    path: Path, what: str, error: type[DataFileError] = DataFileError
) -> tuple[set[str], list[Row]]:
    """The column names and the non-empty rows of a sheet; `what` names it.

    The header is row 1, so the first data row is row 2, also when a cell
    before it spans several lines. Missing cells read as `""`, cells without a
    column name are dropped, and every cell is stripped.
    """
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            header = handle.readline()
            handle.seek(0)
            delimiter = ";" if header.count(";") > header.count(",") else ","
            records = list(csv.reader(handle, delimiter=delimiter))
    except (OSError, UnicodeDecodeError, csv.Error):
        raise error(f"{path}: {what} is unreadable") from None
    if not records:
        return set(), []
    names = [name.strip() for name in records[0]]
    rows = []
    for number, record in enumerate(records[1:], start=2):
        cells = {
            name: (record[n].strip() if n < len(record) else "")
            for n, name in enumerate(names)
            if name
        }
        if any(cells.values()):
            rows.append((number, cells))
    return {name for name in names if name}, rows
