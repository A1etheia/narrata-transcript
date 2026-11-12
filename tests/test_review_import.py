import dataclasses
import unittest

from test_candidates import ONLY_FIRST
from test_decisions import MOMENT, NONE
from test_review_sheet import SECRET, _SheetCase, parsed, save_rows

from transcript.candidates import collect
from transcript.decisions import SessionDecisions
from transcript.reference import Processing
from transcript.review_import import (
    ImportResult,
    ReviewImportError,
    import_rows,
    read_review_sheet,
)
from transcript.review_sheet import SHEET_COLUMNS, render, review_sheet


class ReviewImportTest(_SheetCase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet = self.paths.review_dir / "review.csv"
        self.before = self.paths.review_candidates.read_bytes()

    def export(self, decisions: SessionDecisions = NONE) -> list[dict[str, str]]:
        """The rows of a fresh export of all candidates, for editing."""
        return parsed(review_sheet(self.found, decisions, include_all=True))

    def save(self, rows: list[dict[str, str]], columns=SHEET_COLUMNS) -> None:
        save_rows(self.sheet, rows, columns)

    def reimport(self, decisions: SessionDecisions = NONE) -> ImportResult:
        return import_rows(
            self.found, decisions, read_review_sheet(self.sheet), now=MOMENT
        )

    def test_an_unchanged_export_imports_without_changes(self) -> None:
        decisions = self.decide(
            "s01-p0002", "corrected", target_text="- Ja", note=SECRET
        )
        self.sheet.write_bytes(render(review_sheet(self.found, decisions, True)))

        result = self.reimport(decisions)

        self.assertEqual(result.decisions, decisions)
        self.assertFalse(result.changed)
        self.assertEqual((result.unchanged, result.problems), (3, ()))

    def test_a_filled_in_row_decides_its_candidate(self) -> None:
        rows = self.export()
        rows[2].update(status=" Corrected ", target_text="Grauwasser", note="klar")
        self.save(rows)

        result = self.reimport()

        (decision,) = result.decisions.decisions
        self.assertEqual(decision.id, "s01-p0003")
        self.assertEqual(
            (decision.status, decision.target_text, decision.note),
            ("corrected", "Grauwasser", "klar"),
        )
        self.assertEqual(
            decision.reference_processed_at, self.reference.processing.processed_at
        )
        self.assertEqual(decision.decided_at, MOMENT.isoformat())
        self.assertEqual(result.imported, {"corrected": 1})
        self.assertEqual(result.unchanged, 2)

    def test_importing_the_same_sheet_again_changes_nothing(self) -> None:
        rows = self.export()
        rows[0]["status"] = "confirmed"
        self.save(rows)
        first = self.reimport()

        second = self.reimport(first.decisions)

        self.assertEqual(second.decisions, first.decisions)
        self.assertFalse(second.changed)

    def test_a_decision_set_back_to_open_is_imported(self) -> None:
        decisions = self.decide("s01-p0001", "deferred")
        rows = self.export(decisions)
        rows[0]["status"] = ""
        self.save(rows)

        result = self.reimport(decisions)

        self.assertEqual(result.decisions.decisions[0].status, "open")

    def test_bad_rows_are_reported_and_left_out_the_rest_is_taken(self) -> None:
        first, second, third = self.export()
        self.save(
            [
                dict(first, status="corrected"),  # without target text
                dict(second, status="erledigt", note=SECRET),
                dict(third, id="", status="kept"),
                dict(third, id="s01-p0099", status="kept"),
                dict(third, id=SECRET, status="kept"),
                dict(third, status="kept"),
            ]
        )

        result = self.reimport()

        self.assertEqual(
            result.problems,
            (
                "row 2 (s01-p0001): field 'target_text' required for corrected",
                "row 3 (s01-p0002): field 'status' invalid",
                "row 4 (no id): field 'id' missing",
                "row 5 (s01-p0099): no such candidate",
                "row 6 (invalid id): no such candidate",
            ),
        )
        self.assertNotIn("Grüße", "\n".join(result.problems))
        self.assertEqual([d.id for d in result.decisions.decisions], ["s01-p0003"])
        self.assertEqual(result.imported, {"kept": 1})

    def test_a_target_text_beside_another_status_is_refused(self) -> None:
        rows = self.export()
        rows[0].update(status="confirmed", target_text="anders")
        self.save(rows[:1])

        result = self.reimport()

        self.assertEqual(
            result.problems,
            ("row 2 (s01-p0001): field 'target_text' only allowed for corrected",),
        )

    def test_a_changed_row_of_an_older_transcript_is_refused(self) -> None:
        rows = self.export()
        rows[2]["status"] = "confirmed"
        self.save(rows)
        newer = dataclasses.replace(
            self.reference,
            processing=Processing("0.0.1", "2026-11-09T20:00:00+01:00"),
        )
        self.rated(newer)
        self.found = collect(self.paths, ONLY_FIRST)

        result = self.reimport()

        (problem,) = result.problems
        self.assertEqual(
            problem,
            "row 4 (s01-p0003): field 'version' is not the current transcript; "
            "export again",
        )
        self.assertEqual(result.unchanged, 2)  # untouched rows are no error
        self.assertFalse(result.changed)

    def test_the_formula_mark_of_the_export_is_removed(self) -> None:
        rows = self.export()
        rows[2].update(status="corrected", target_text="'=Grau", note="'s war so")
        self.save(rows)

        (decision,) = self.reimport().decisions.decisions

        self.assertEqual((decision.target_text, decision.note), ("=Grau", "'s war so"))

    def test_extra_columns_and_their_order_do_not_matter(self) -> None:
        rows = self.export()
        rows[0].update(status="kept", spare="x")
        self.save(
            rows, columns=("version", "spare", "note", "status", "id", "target_text")
        )

        self.assertEqual(self.reimport().imported, {"kept": 1})

    def test_a_missing_column_refuses_the_sheet(self) -> None:
        self.save(self.export(), columns=("id", "status", "note", "version"))

        with self.assertRaisesRegex(
            ReviewImportError, "lacks column\\(s\\) target_text"
        ):
            read_review_sheet(self.sheet)

    def test_an_id_twice_refuses_the_sheet(self) -> None:
        rows = self.export()
        self.save([rows[0], rows[1], rows[0]])

        with self.assertRaisesRegex(
            ReviewImportError, "rows 2 and 4: s01-p0001 appears twice"
        ):
            read_review_sheet(self.sheet)

    def test_the_candidates_stay_as_they_are(self) -> None:
        rows = self.export()
        rows[0].update(status="corrected", target_text="neu")
        rows[1].update(status="falsch")
        self.save(rows)

        self.reimport()

        self.assertEqual(self.paths.review_candidates.read_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
