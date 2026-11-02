"""Logger for transcript text, the only way such text may reach a log.

Privacy rule (docs/datenschutz.md): transcript text goes to a file under `work/` and
only in debug mode, never to the console.
"""

import logging

from transcript.config import Config
from transcript.session import SessionKey


def transcript_logger(config: Config, key: SessionKey) -> logging.Logger:
    """Return the session's text logger; it never propagates to other handlers."""
    logger = logging.getLogger(f"transcript.text.{key}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    if not config.debug:
        logger.addHandler(logging.NullHandler())
        return logger

    paths = config.session_paths(key)
    paths.work_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(paths.debug_log, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger
