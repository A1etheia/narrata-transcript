"""Access to the Narrata transcription-context endpoint (IOA-1215).

The token is a secret: it comes from the environment or `.env`, never from the
configuration file, and no message, log record or exception names its value.
"""

from collections.abc import Mapping
from pathlib import Path

TOKEN_VARIABLE = "NARRATA_TOKEN"


class NarrataClientError(Exception):
    """Narrata could not be asked; the message is meant for the user."""


def read_token(environ: Mapping[str, str], dotenv: Path) -> str:
    """`NARRATA_TOKEN` from the environment, else from the `dotenv` file."""
    token = environ.get(TOKEN_VARIABLE, "").strip()
    if not token and dotenv.is_file():
        token = _read_dotenv(dotenv).get(TOKEN_VARIABLE, "")
    if not token:
        raise NarrataClientError(
            f"{TOKEN_VARIABLE} is not set; put a Narrata login token into "
            f"{dotenv} (see .env.example) or into the environment"
        )
    return token


def _read_dotenv(path: Path) -> dict[str, str]:
    """`KEY=VALUE` lines with `#` comments, an optional `export ` and quotes.

    Messages name the line number only, since any line may hold a secret.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise NarrataClientError(f"{path}: cannot read file") from None
    values = {}
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.removeprefix("export ").partition("=")
        key = key.strip()
        if not separator or not key:
            raise NarrataClientError(f"{path}: line {number} is not KEY=VALUE")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values
