"""Reading and writing the pipeline's JSON working files.

Error messages name the file and the field, never a field's value: working files
may hold names of real people.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class DataFileError(Exception):
    """A working file is missing or invalid; the message is meant for the user."""


def read_object(
    path: Path, what: str, error: type[DataFileError] = DataFileError
) -> dict[str, Any]:
    """Read a JSON object; `what` names the file in messages, e.g. "manifest"."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise error(f"{path}: {what} not found") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as cause:
        raise error(f"{path}: {what} is unreadable ({cause})") from None
    if not isinstance(data, dict):
        raise error(f"{path}: {what} is not a JSON object")
    return data


def field(
    data: Any,
    name: str,
    kind: type,
    path: Path,
    error: type[DataFileError] = DataFileError,
) -> Any:
    """`data[name]` if it has type `kind`; `True` does not count as an int."""
    value = data.get(name) if isinstance(data, dict) else None
    if not _is_kind(value, kind):
        raise error(f"{path}: field {name!r} missing or invalid")
    return value


def optional_field(
    data: Any,
    name: str,
    kind: type,
    path: Path,
    error: type[DataFileError] = DataFileError,
) -> Any:
    """Like `field`, but an absent or null value yields `None`."""
    if isinstance(data, dict) and data.get(name) is None:
        return None
    return field(data, name, kind, path, error)


def optional_number(
    data: Any, name: str, path: Path, error: type[DataFileError] = DataFileError
) -> float | None:
    """An optional JSON number as float; `True` does not count as a number."""
    value = optional_field(data, name, (int, float), path, error)
    return None if value is None else float(value)


def list_of(
    data: Any,
    name: str,
    kind: type,
    path: Path,
    error: type[DataFileError] = DataFileError,
) -> list[Any]:
    """`data[name]` as a list whose items all have type `kind`."""
    values = field(data, name, list, path, error)
    if not all(_is_kind(value, kind) for value in values):
        raise error(f"{path}: field {name!r} holds invalid items")
    return values


def _is_kind(value: Any, kind: type) -> bool:
    """`isinstance`, except that booleans never count as numbers."""
    return isinstance(value, kind) and (kind is bool or not isinstance(value, bool))


def write_atomic(path: Path, data: dict[str, Any]) -> None:
    """Replace `path` atomically, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.stem}-", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.write("\n")
    try:
        os.replace(tmp.name, path)
    except OSError:
        Path(tmp.name).unlink(missing_ok=True)
        raise
