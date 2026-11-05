"""Local pipeline that turns session recordings into structured transcripts."""

import logging
import os

__version__ = "0.0.1"

# V0.1 runs fully locally (CLAUDE.md, docs/datenschutz.md). Set for the whole
# process before any model library is imported, and set rather than defaulted,
# so an inherited environment cannot switch them back on:
# - huggingface_hub reads HF_HUB_OFFLINE once, at import;
# - pyannote.audio 4 sends run metadata to otel.pyannote.ai unless disabled.
OFFLINE_ENVIRONMENT = {"HF_HUB_OFFLINE": "1", "PYANNOTE_METRICS_ENABLED": "false"}
os.environ.update(OFFLINE_ENVIRONMENT)

# A library leaves log output to its caller; the CLI shows it on stderr.
logging.getLogger(__name__).addHandler(logging.NullHandler())
