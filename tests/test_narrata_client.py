import http.server
import logging
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from transcript.narrata_client import (
    NarrataClientError,
    Token,
    context_url,
    fetch_context,
    read_token,
    token_variable,
)

TOKEN = "12|made-up-token"  # stands in for a real token that must not leak
GROUP = "beispielgruppe"
VARIABLE = "NARRATA_TOKEN_BEISPIELGRUPPE"


class ReadTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dotenv = Path(directory.name) / ".env"

    def write(self, text: str) -> None:
        self.dotenv.write_text(text, encoding="utf-8")

    def read(self, environ: dict[str, str]) -> Token:
        return read_token(environ, self.dotenv, GROUP)

    def assert_fails(self, environ: dict[str, str], *expected: str) -> None:
        with self.assertRaises(NarrataClientError) as caught:
            self.read(environ)
        for part in expected:
            self.assertIn(part, str(caught.exception))
        self.assertNotIn("made-up", str(caught.exception))

    def test_variable_is_named_after_the_group(self) -> None:
        self.assertEqual(token_variable(GROUP), VARIABLE)
        self.assertEqual(token_variable("runde-2"), "NARRATA_TOKEN_RUNDE_2")

    def test_environment_wins_over_dotenv(self) -> None:
        self.write(f"{VARIABLE}=from-file\n")

        self.assertEqual(self.read({VARIABLE: TOKEN}), Token(VARIABLE, TOKEN))

    def test_environment_alone_needs_no_readable_dotenv(self) -> None:
        self.write("not a pair\n")

        self.assertEqual(self.read({VARIABLE: TOKEN}).value, TOKEN)

    def test_dotenv_is_read_when_the_environment_has_none(self) -> None:
        for text in (
            f"{VARIABLE}={TOKEN}\n",
            f"# comment\n\nOTHER=x\nexport {VARIABLE} = {TOKEN}  \n",
            f'{VARIABLE}="{TOKEN}"\n',
            f"{VARIABLE}='{TOKEN}'\n",
        ):
            with self.subTest(text=text):
                self.write(text)

                self.assertEqual(self.read({VARIABLE: ""}).value, TOKEN)

    def test_another_groups_token_is_not_taken(self) -> None:
        self.write(f"NARRATA_TOKEN_ANDERE_RUNDE={TOKEN}\n")

        self.assert_fails({}, f"{VARIABLE} is not set")

    def test_missing_token_points_to_narrata_and_the_example(self) -> None:
        for text in (None, f"{VARIABLE}=\n", "OTHER=x\n"):
            with self.subTest(text=text):
                if text is not None:
                    self.write(text)

                self.assert_fails(
                    {},
                    f"{VARIABLE} is not set",
                    "create a pipeline token",
                    ".env.example",
                )

    def test_legacy_variable_is_named_but_not_used(self) -> None:
        for environ, text in (
            ({"NARRATA_TOKEN": TOKEN}, None),
            ({}, f"NARRATA_TOKEN={TOKEN}\n"),
        ):
            with self.subTest(environ=environ, text=text):
                if text is not None:
                    self.write(text)

                self.assert_fails(
                    environ,
                    "NARRATA_TOKEN is no longer read",
                    f"store it as {VARIABLE}",
                )

    def test_value_stays_out_of_the_repr(self) -> None:
        token = Token(VARIABLE, TOKEN)

        self.assertIn(VARIABLE, repr(token))
        self.assertNotIn("made-up", repr(token))

    def test_malformed_line_is_named_by_number_only(self) -> None:
        self.write(f"OTHER=x\n{TOKEN}\n")

        self.assert_fails({}, "line 2 is not KEY=VALUE")

    def test_example_file_holds_no_token(self) -> None:
        example = Path(__file__).resolve().parent.parent / ".env.example"

        with self.assertRaises(NarrataClientError) as caught:
            read_token({}, example, GROUP)

        self.assertIn(f"{VARIABLE} is not set", str(caught.exception))


class FakeNarrata(http.server.ThreadingHTTPServer):
    """A Narrata stand-in on 127.0.0.1 that records requests and answers as told."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.status = 200
        self.body = b'{"contract_version": "1.1"}'
        self.headers: dict[str, str] = {}
        self.delay_s = 0.0
        self.requests: list[tuple[str, dict[str, str]]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _Handler(http.server.BaseHTTPRequestHandler):
    server: FakeNarrata

    def do_GET(self) -> None:
        self.server.requests.append((self.path, dict(self.headers)))
        time.sleep(self.server.delay_s)
        self.send_response(self.server.status)
        for name, value in self.server.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(self.server.body)))
        self.end_headers()
        self.wfile.write(self.server.body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # keeps request lines off the test output


def start_fake_narrata(test: unittest.TestCase) -> FakeNarrata:
    server = FakeNarrata()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    test.addCleanup(thread.join)
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server


class FetchContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.narrata = start_fake_narrata(self)

    def fetch(self, **kwargs: object) -> bytes:
        options: dict = {
            "base_url": self.narrata.url,
            "timeout": 5,
            "recent_sessions": 3,
            "archive_limit": 500,
            **kwargs,
        }
        token = Token(VARIABLE, TOKEN)
        return fetch_context(group_id=12, ordinal=42, token=token, **options)

    def assert_fails(self, expected: str, **kwargs: object) -> str:
        with (
            self.assertNoLogs(level=logging.DEBUG),
            self.assertRaises(NarrataClientError) as caught,
        ):
            self.fetch(**kwargs)
        message = str(caught.exception)
        self.assertIn(expected, message)
        self.assertNotIn("made-up", message)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)
        return message

    def test_url_follows_the_contract(self) -> None:
        self.assertEqual(
            context_url(
                "https://narrata.example/", 12, 42, recent_sessions=5, archive_limit=0
            ),
            "https://narrata.example/api/groups/12/play-sessions/42"
            "/transcription-context?n=5&archive_limit=0",
        )

    def test_response_bytes_are_returned_unchanged(self) -> None:
        self.narrata.body = b'{"contract_version":"1.1",  "x": "\xc3\xa4"}'

        with self.assertNoLogs(level=logging.DEBUG):
            self.assertEqual(self.fetch(), self.narrata.body)

        [(path, headers)] = self.narrata.requests
        self.assertEqual(
            path,
            "/api/groups/12/play-sessions/42/transcription-context"
            "?n=3&archive_limit=500",
        )
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(headers["Accept"], "application/json")

    def test_status_codes_get_their_own_message(self) -> None:
        for status, expected in (
            (401, f"{VARIABLE} is expired or revoked, create a pipeline token"),
            (404, "no session 42 in group 12"),
            (404, f"{VARIABLE} was created for this group"),
            (422, "rejected the request parameters"),
            (500, "Narrata answered HTTP 500"),
            (503, "Narrata answered HTTP 503"),
        ):
            with self.subTest(status=status):
                self.narrata.status = status
                self.narrata.body = TOKEN.encode()  # a body never reaches a message

                self.assert_fails(expected)

    def test_redirect_is_not_followed(self) -> None:
        self.narrata.status = 302
        self.narrata.headers = {"Location": f"{self.narrata.url}/elsewhere"}

        self.assert_fails("redirected the request (HTTP 302); check narrata.url")
        self.assertEqual(len(self.narrata.requests), 1)

    def test_timeout_is_reported(self) -> None:
        self.narrata.delay_s = 1

        self.assert_fails("cannot reach Narrata at", timeout=0.2)

    def test_unreachable_host_is_reported(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed_url = f"http://127.0.0.1:{probe.getsockname()[1]}"

        message = self.assert_fails("cannot reach Narrata at", base_url=closed_url)
        self.assertIn(closed_url, message)


if __name__ == "__main__":
    unittest.main()
