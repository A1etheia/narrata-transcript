import csv
import dataclasses
import io

from test_candidates import ONLY_FIRST, _SessionCase
from test_decisions import MOMENT, NONE
from test_uncertainty import hint, passage, transcript, words

from transcript.candidates import SessionCandidates, collect, session_candidates
from transcript.decisions import ReviewStatus, SessionDecisions, decide
from transcript.reference import Processing
from transcript.review_sheet import (
    SHEET_COLUMNS,
    ReviewSheet,
    SheetError,
    render,
    review_sheet,
    write_sheet,
)

SECRET = '- Grüße an „Öde“;\nzweite Zeile mit "Zitat"'


def parsed(sheet: ReviewSheet) -> list[dict[str, str]]:
    text = render(sheet).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=";"))


class _SheetCase(_SessionCase):
    def setUp(self) -> None:
        super().setUp()
        self.reference = transcript(
            passage(words(0.3, 0.9, 0.9), index=1),  # needs_review
            passage(words(0.3, 0.3, 0.9), index=2),  # uncertain
            passage(words(0.3, 0.9, 0.9), index=3),  # uncertain by its hint, first
        )
        self.rated(self.reference, dataclasses.replace(hint(ambiguous=True), passage=3))
        self.found = session_candidates(self.paths, ONLY_FIRST)

    def decide(
        self,
        candidate: str,
        status: ReviewStatus,
        on: SessionDecisions = NONE,
        **optional: str,
    ) -> SessionDecisions:
        return decide(on, self.found, candidate, status, now=MOMENT, **optional)


class ReviewSheetTest(_SheetCase):
    def test_rows_are_in_recording_order_with_their_review_order(self) -> None:
        rows = parsed(review_sheet(self.found, NONE))

        self.assertEqual(
            [r["id"] for r in rows], ["s01-p0001", "s01-p0002", "s01-p0003"]
        )
        self.assertEqual([r["order"] for r in rows], ["3", "2", "1"])
        self.assertEqual({r["status"] for r in rows}, {"open"})

    def test_by_default_only_open_and_deferred_candidates_appear(self) -> None:
        decisions = self.decide(
            "s01-p0002", "deferred", on=self.decide("s01-p0001", "confirmed")
        )

        sheet = review_sheet(self.found, decisions)

        self.assertEqual([r["id"] for r in parsed(sheet)], ["s01-p0002", "s01-p0003"])
        self.assertEqual(sheet.counts, {"deferred": 1, "open": 1})

    def test_all_rows_carry_their_decision(self) -> None:
        decisions = self.decide(
            "s01-p0003", "corrected", target_text="Grauwasser", note="klar zu hören"
        )

        row = parsed(review_sheet(self.found, decisions, include_all=True))[2]

        self.assertEqual(row["status"], "corrected")
        self.assertEqual(row["target_text"], "Grauwasser")
        self.assertEqual(row["note"], "klar zu hören")
        self.assertEqual(row["version"], self.reference.processing.processed_at)

    def test_a_stale_decision_is_shown_but_not_filled_in(self) -> None:
        decisions = self.decide("s01-p0003", "corrected", target_text="alt")
        newer = dataclasses.replace(
            self.reference,
            processing=Processing("0.0.1", "2026-11-09T20:00:00+01:00"),
        )
        self.rated(newer)

        sheet = review_sheet(collect(self.paths, ONLY_FIRST), decisions)

        row = parsed(sheet)[-1]
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["target_text"], "")
        self.assertEqual(
            row["earlier_decision"], f"corrected {MOMENT.isoformat()}, older transcript"
        )
        self.assertEqual(row["version"], "2026-11-09T20:00:00+01:00")
        self.assertEqual(sheet.stale, decisions.decisions)

    def test_an_orphaned_decision_is_reported_not_listed(self) -> None:
        decisions = self.decide("s01-p0003", "kept")
        others = tuple(c for c in self.found.candidates if c.id != "s01-p0003")
        fewer = SessionCandidates(self.found.rated, self.found.not_rated, others)

        sheet = review_sheet(fewer, decisions, include_all=True)

        self.assertEqual(sheet.orphaned, decisions.decisions)
        self.assertNotIn("s01-p0003", [r["id"] for r in parsed(sheet)])

    def test_reasons_hints_and_times_are_readable(self) -> None:
        first, _, row = parsed(review_sheet(self.found, NONE))

        self.assertEqual(first["reasons"], "low_confidence 0.333/0.2")
        self.assertEqual(first["hints"], "")
        self.assertIn("ambiguous", row["reasons"])
        self.assertEqual(
            row["hints"],
            "known_variant „Grau Wasser“ → place 1 Grauwasser (name, session) "
            "ambiguous",
        )
        self.assertRegex(row["start"], r"^\d{2}:\d{2}:\d{2}\.\d{3}$")
        self.assertRegex(row["segment_start"], r"^\d{2}:\d{2}:\d{2}\.\d{3}$")
        self.assertEqual(row["speaker"], "SPEAKER_00")


class RenderTest(_SheetCase):
    def test_the_file_suits_a_german_spreadsheet(self) -> None:
        data = render(review_sheet(self.found, NONE))

        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        header, _ = data.decode("utf-8-sig").split("\r\n", 1)
        self.assertEqual(header, ";".join(SHEET_COLUMNS))

    def test_text_survives_with_umlauts_breaks_and_separators(self) -> None:
        odd = tuple(
            dataclasses.replace(c, text=SECRET) if c.passage == 1 else c
            for c in self.found.candidates
        )
        found = dataclasses.replace(self.found, candidates=odd)

        first, second, _ = parsed(review_sheet(found, NONE))

        self.assertEqual(first["text"], "'" + SECRET)  # shown as text, not a formula
        self.assertEqual(second["text"], "wort0 wort1 wort2")

    def test_the_same_data_gives_the_same_bytes(self) -> None:
        decisions = self.decide("s01-p0002", "deferred", note="hören")

        first = render(review_sheet(self.found, decisions))
        again = render(review_sheet(self.found, decisions))

        self.assertEqual(first, again)

    def test_a_note_starting_like_a_formula_stays_text(self) -> None:
        decisions = self.decide("s01-p0002", "deferred", note="=nochmal")

        row = parsed(review_sheet(self.found, decisions))[1]

        self.assertEqual(row["note"], "'=nochmal")

    def test_no_candidates_give_the_header_only(self) -> None:
        empty = SessionCandidates(self.found.rated, (), ())

        self.assertEqual(parsed(review_sheet(empty, NONE)), [])


class WriteSheetTest(_SheetCase):
    def test_an_existing_sheet_is_replaced_only_with_force(self) -> None:
        sheet = review_sheet(self.found, NONE)
        self.paths.review_sheet.write_bytes(b"filled in by hand")

        with self.assertRaisesRegex(SheetError, "use --force") as caught:
            write_sheet(self.paths, sheet)
        self.assertEqual(self.paths.review_sheet.read_bytes(), b"filled in by hand")
        self.assertNotIn("filled", str(caught.exception))

        write_sheet(self.paths, sheet, force=True)
        self.assertEqual(self.paths.review_sheet.read_bytes(), render(sheet))

    def test_a_new_sheet_needs_no_force(self) -> None:
        write_sheet(self.paths, review_sheet(self.found, NONE))

        self.assertTrue(self.paths.review_sheet.is_file())
