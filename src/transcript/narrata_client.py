"""Access to the Narrata transcription-context endpoint (IOA-1215).

The token is a group's pipeline token (IOA-1251): the active game master mints
it in Narrata for one group, it lasts 90 days and opens only this endpoint. Each
group has its own variable, `NARRATA_TOKEN_<SLUG>`.

The token is a secret: it comes from the environment or `.env`, never from the
configuration file, and no message, log record or exception names its value.
"""

import http.client
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

TOKEN_PREFIX = "NARRATA_TOKEN_"
LEGACY_VARIABLE = "NARRATA_TOKEN"  # the single login token before TOOL-84
TIMEOUT_S = 30
_MINT_HINT = (
    "create a pipeline token for the group in Narrata (Profil → Aktive Sitzungen)"
)


class NarrataClientError(Exception):
    """Narrata could not be asked; the message is meant for the user."""


@dataclass(frozen=True)
class Token:
    """A pipeline token with the variable it came from; `repr` hides the value."""

    variable: str
    value: str = field(repr=False)


def token_variable(group: str) -> str:
    """`NARRATA_TOKEN_<SLUG>`; slugs hold no `_`, so `-` → `_` stays unambiguous."""
    return TOKEN_PREFIX + group.upper().replace("-", "_")


def read_token(environ: Mapping[str, str], dotenv: Path, group: str) -> Token:
    """The group's token from the environment, else from the `dotenv` file."""
    variable = token_variable(group)
    if value := environ.get(variable, "").strip():
        return Token(variable, value)  # a set variable needs no readable .env
    values = _read_dotenv(dotenv) if dotenv.is_file() else {}
    if value := values.get(variable):
        return Token(variable, value)
    if environ.get(LEGACY_VARIABLE, "").strip() or values.get(LEGACY_VARIABLE):
        where = f"{LEGACY_VARIABLE} is no longer read, store it as {variable}"
    else:
        where = f"put it into {dotenv} (see .env.example) or into the environment"
    raise NarrataClientError(f"{variable} is not set; {_MINT_HINT} and {where}")


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
    token: Token,
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
        headers={
            "Authorization": f"Bearer {token.value}",
            "Accept": "application/json",
        },
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        error.close()  # an HTTPError holds the open error response
        raise NarrataClientError(
            _http_message(error.code, group_id, ordinal, token.variable)
        ) from None
    except (OSError, http.client.HTTPException) as error:  # URLError is an OSError
        reason = getattr(error, "reason", None) or str(error) or type(error).__name__
        raise NarrataClientError(
            f"cannot reach Narrata at {base_url}: {reason}"
        ) from None


def _http_message(code: int, group_id: int, ordinal: int, variable: str) -> str:
    if code == 401:
        return (
            f"Narrata rejected the token (HTTP 401); {variable} is expired or "
            f"revoked, {_MINT_HINT} and replace it"
        )
    if code == 404:
        return (
            f"Narrata has no session {ordinal} in group {group_id} for this token "
            f"(HTTP 404); check narrata.groups, that {variable} was created for "
            "this group and that its game master is still active"
        )
    if code == 422:
        return "Narrata rejected the request parameters (HTTP 422)"
    if 300 <= code < 400:
        return f"Narrata redirected the request (HTTP {code}); check narrata.url"
    return f"Narrata answered HTTP {code}"
