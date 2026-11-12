"""The lock of a running `transcript process` (TOOL-57).

`process` takes `work/<s>/process.lock` after the preflight and removes it when
the run ends. The lock holds the process id: a lock whose process is alive
keeps a second run out; one whose process is gone was left by an interrupted
run, which `transcript status` reports and the next run replaces. An
unreadable lock counts as gone. No version field: the file is short-lived.
"""

import contextlib
import datetime
import os
from collections.abc import Iterator
from typing import Literal

from transcript import jsonfile
from transcript.jsonfile import DataFileError
from transcript.session import SessionPaths

LockState = Literal["running", "interrupted"]


class LockedError(Exception):
    """Another `process` of the session is running."""


def state(paths: SessionPaths) -> LockState | None:
    """`running` or `interrupted` if a lock is there, else None."""
    if not paths.process_lock.exists():
        return None
    pid = _pid(paths)
    return "running" if pid is not None and _alive(pid) else "interrupted"


@contextlib.contextmanager
def held(paths: SessionPaths) -> Iterator[bool]:
    """Hold the lock; yields True if it replaced one of an interrupted run.

    `LockedError` if a running process holds it. Only a run that ends without
    an exception removes it; after Ctrl-C or a crash it stays for `status`.
    """
    pid = _pid(paths)
    if pid is not None and _alive(pid):
        raise LockedError(
            f"{paths.process_lock}: transcript process {paths.key} is running "
            f"(pid {pid}); remove the file if it is not"
        )
    replaced = paths.process_lock.exists()
    moment = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    jsonfile.write_atomic(
        paths.process_lock, {"pid": os.getpid(), "started_at": moment}
    )
    yield replaced
    if _pid(paths) == os.getpid():
        paths.process_lock.unlink(missing_ok=True)


def _pid(paths: SessionPaths) -> int | None:
    """The process id in the lock; None if there is none or it is unreadable."""
    path = paths.process_lock
    try:
        pid = jsonfile.field(
            jsonfile.read_object(path, "process lock"), "pid", int, path
        )
    except DataFileError:
        return None
    return pid if pid > 0 else None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # signal 0 checks, sends nothing
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # it exists, run by someone else
    return True
