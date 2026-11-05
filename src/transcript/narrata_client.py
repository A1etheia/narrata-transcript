"""Access to the Narrata transcription-context endpoint (IOA-1215).

The token is a secret: it comes from the environment or `.env`, never from the
configuration file, and no message, log record or exception names its value.
"""

import http.client
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path

TOKEN_VARIABLE = "NARRATA_TOKEN"
TIMEOUT_S = 30


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would resend the bearer token to wherever a redirect points."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def context_url(
    base_url: str,
    group_id: int,
    ordinal: int,
    *,
    recent_sessions: int,
    archive_limit: int,
) -> str:
    """The transcription-context endpoint of one play session (IOA-1215).

    Both query parameters are always sent, so the result never depends on a
    server default: `n` is the window of the `recent` tier, `archive_limit`
    caps the `archive` tier.
    """
    query = urllib.parse.urlencode(
        {"n": recent_sessions, "archive_limit": archive_limit}
    )
    return (
        f"{base_url.rstrip('/')}/api/groups/{group_id}"
        f"/play-sessions/{ordinal}/transcription-context?{query}"
    )


def fetch_context(
    base_url: str,
    group_id: int,
    ordinal: int,
    token: str,
    *,
    recent_sessions: int,
    archive_limit: int,
    timeout: float = TIMEOUT_S,
) -> bytes:
    """The raw transcription-context response; `store_context` checks it."""
    request = urllib.request.Request(
        context_url(
            base_url,
            group_id,
            ordinal,
            recent_sessions=recent_sessions,
            archive_limit=archive_limit,
        ),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        error.close()  # an HTTPError holds the open error response
        raise NarrataClientError(_http_message(error.code, group_id, ordinal)) from None
    except (OSError, http.client.HTTPException) as error:  # URLError is an OSError
        reason = getattr(error, "reason", None) or str(error) or type(error).__name__
        raise NarrataClientError(
            f"cannot reach Narrata at {base_url}: {reason}"
        ) from None


def _http_message(code: int, group_id: int, ordinal: int) -> str:
    if code == 401:
        return (
            f"Narrata rejected the token (HTTP 401); {TOKEN_VARIABLE} is missing "
            "or expired, login tokens last 24 h"
        )
    if code == 404:
        return (
            f"Narrata has no session {ordinal} in group {group_id} for this token "
            "(HTTP 404); check narrata.groups and that the token belongs to the "
            "group's active game master"
        )
    if code == 422:
        return "Narrata rejected the request parameters (HTTP 422)"
    if 300 <= code < 400:
        return f"Narrata redirected the request (HTTP {code}); check narrata.url"
    return f"Narrata answered HTTP {code}"
