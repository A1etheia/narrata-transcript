import csv
import tempfile
import unittest
from pathlib import Path

from test_reference import minimal

from transcript.calibration import (
    SHEET_COLUMNS,
    SHEET_SIZE,
    CalibrationError,
    align,
    evaluate,
    judged_precision,
    parse_hand_reference,
    read_hand_reference,
    similar_sheet,
    write_sheet,
)
from transcript.config import UncertaintyThresholds
from transcript.hints import Candidate, Hint, SegmentHints, write_hints
from transcript.reference import AsrInfo, Passage, ReferenceTranscript, Word
from transcript.session import SessionPaths
from transcript.uncertainty import assess

# Everything below is made up; "Ærwyn" stands for a real speaker's name.
HAND = "Ærwyn: wir reiten nach Norden\nBrakk: das [lacht] ist ??? gut\n"
SIGNALS = {"no_speech_prob": 0.01, "avg_logprob": -0.2, "compression_ratio": 1.3}


def recognised(
    *passages: list[tuple[str, float]], step: int = 300
) -> ReferenceTranscript:
    """Passages of (word, confidence), each word `step` ms after the previous."""
    built = []
    clock = 0
    for number, spoken in enumerate(passages, start=1):
        words = []
        for text, confidence in spoken:
            words.append(Word(text, clock, clock + 250, confidence))
            clock += step
        built.append(
            Passage(
                number,
                " ".join(w.text for w in words),
                words[0].start_ms,
                words[-1].end_ms,
                tuple(words),
                signals=dict(SIGNALS),
            )
        )
    return minimal(
        passages=tuple(built),
        asr=AsrInfo("fake", "fake", capabilities={"word_timestamps": True}),
    )


def report_lines(reference: ReferenceTranscript, start: int = 0, end: int = 10_000):
    ratings = assess(reference, None, UncertaintyThresholds())
    return evaluate(reference, ratings, parse_hand_reference(HAND), start, end)


class HandReferenceTest(unittest.TestCase):
    def test_labels_notes_and_inaudible_stretches_are_not_words(self) -> None:
        hand = parse_hand_reference(HAND)

        self.assertEqual(
            hand.tokens, ("wir", "reiten", "nach", "norden", "das", "ist", "gut")
        )
        self.assertEqual(hand.speakers, ("S1",) * 4 + ("S2",) * 3)
        self.assertEqual(hand.gaps, frozenset({6}))

    def test_an_empty_or_unreadable_reference_is_rejected_without_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.txt"
            path.write_text("Ærwyn: [lacht]\n", encoding="utf-8")
            with self.assertRaisesRegex(CalibrationError, "has no words") as caught:
                read_hand_reference(path)
            self.assertNotIn("Ærwyn", str(caught.exception))
            with self.assertRaisesRegex(CalibrationError, "unreadable"):
                read_hand_reference(Path(directory) / "missing.txt")


class AlignTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hand = parse_hand_reference(HAND)

    def test_a_substitution_points_at_the_recognised_word(self) -> None:
        found = align(
            self.hand, ["wir", "reiten", "noch", "norden", "das", "ist", "gut"]
        )

        self.assertEqual(found.counts["substitutions"], 1)
        self.assertEqual([n for n, bad in enumerate(found.wrong) if bad], [2])
        self.assertEqual(found.substituted, (2,))

    def test_a_deletion_sits_next_to_a_recognised_word(self) -> None:
        found = align(self.hand, ["wir", "reiten", "norden", "das", "ist", "gut"])

        self.assertEqual(found.counts["deletions"], 1)
        self.assertEqual(found.deletions, ((2, 2),))
        self.assertFalse(any(found.wrong))

    def test_an_insertion_is_wrong_but_not_inside_an_inaudible_stretch(self) -> None:
        inserted = align(
            self.hand, ["wir", "wir", "reiten", "nach", "norden", "das", "ist", "gut"]
        )
        self.assertEqual(inserted.counts["insertions"], 1)
        self.assertEqual(sum(inserted.wrong), 1)

        absorbed = align(
            self.hand, ["wir", "reiten", "nach", "norden", "das", "ist", "sehr", "gut"]
        )
        self.assertEqual(absorbed.counts["insertions"], 0)
        self.assertEqual(absorbed.counts["absorbed"], 1)
        self.assertEqual(absorbed.absorbed[6], True)
        self.assertFalse(any(absorbed.wrong))

    def test_nothing_recognised_leaves_deletions_unplaced(self) -> None:
        found = align(self.hand, [])

        self.assertEqual(found.counts["deletions"], 7)
        self.assertTrue(all(near is None for _, near in found.deletions))


class EvaluateTest(unittest.TestCase):
    def test_errors_land_in_the_passage_and_level_that_holds_them(self) -> None:
        reference = recognised(
            [("Wir", 0.9), ("reiten", 0.9), ("noch", 0.3), ("Norden.", 0.9)],
            [("Das", 0.9), ("ist", 0.9), ("gut.", 0.9)],
        )

        report = report_lines(reference)

        self.assertEqual(report.counts["substitutions"], 1)
        self.assertEqual(report.by_level["needs_review"].errors, 1)
        self.assertEqual(report.by_level["needs_review"].with_errors, 1)
        self.assertEqual(report.by_level["confident"].errors, 0)
        self.assertEqual(report.by_rule["low_confidence"].errors, 1)
        self.assertEqual(report.speaker_words, {"S1": 4, "S2": 3})
        self.assertEqual(report.speaker_errors, {"S1": 1})
        self.assertEqual(report.auc, 1.0)
        self.assertEqual(report.lowest[0.2], 1.0)

    def test_a_deletion_in_a_confident_passage_is_missed(self) -> None:
        reference = recognised(
            [("Wir", 0.9), ("reiten", 0.9), ("Norden.", 0.9)],
            [("Das", 0.9), ("ist", 0.9), ("gut.", 0.9)],
        )

        report = report_lines(reference)

        self.assertEqual(report.by_level["confident"].deletions, 1)
        lines = "\n".join(report.lines())
        self.assertIn("missed: 1 error(s) in confident passages, 1 of them", lines)

    def test_only_words_starting_in_the_range_count(self) -> None:
        reference = recognised(
            [("Vorher", 0.9)],
            [("Wir", 0.9), ("reiten", 0.9), ("nach", 0.9), ("Norden.", 0.9)],
            [("Das", 0.9), ("ist", 0.9), ("gut.", 0.9)],
        )

        report = report_lines(reference, start=300)

        self.assertEqual(report.recognised, 7)
        self.assertEqual(report.counts["hits"], 7)
        self.assertEqual(sum(t.passages for t in report.by_level.values()), 2)

    def test_the_report_holds_no_words_or_names(self) -> None:
        reference = recognised(
            [("Wir", 0.9), ("reiten", 0.9), ("noch", 0.3), ("Norden.", 0.9)],
            [("Das", 0.9), ("ist", 0.9), ("gut.", 0.9)],
        )

        lines = "\n".join(report_lines(reference).lines())

        for secret in ("Ærwyn", "Brakk", "reiten", "Norden", "noch"):
            self.assertNotIn(secret, lines)
        self.assertIn("speaker S1: 4 word(s), 25.0% wrong", lines)
        self.assertIn("confidence AUC 1.00", lines)


def similar(number: int, score: float = 0.9) -> Hint:
    candidate = Candidate(
        "place", number, "Grauwasser", "name", "name", "session", False
    )
    return Hint(
        passage=1,
        first_word=0,
        last_word=0,
        start_ms=number * 1000,
        end_ms=number * 1000 + 300,
        heard="Grauwassr",
        signal="similar",
        method="spelling",
        score=score,
        candidates=(candidate,),
        ambiguous=False,
    )


class SimilarSheetTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.paths = SessionPaths(minimal().key, self.root)

    def store(self, *found: Hint) -> None:
        write_hints(
            self.paths,
            SegmentHints(1, "ab" * 32, "2026-11-04T20:00:00+01:00", 0, found),
        )

    def test_the_sheet_lists_similar_hints_for_judging(self) -> None:
        known = Hint(
            **{**similar(9).__dict__, "signal": "known_variant", "method": None}
        )
        self.store(similar(1), known, similar(2))

        rows = similar_sheet(self.paths, [1, 2])

        self.assertEqual([row.hint for row in rows], ["1-1", "1-3"])
        self.assertEqual(rows[0].time, "00:00:01.000")
        self.assertEqual(rows[0].candidates, "Grauwasser")
        sheet = self.root / "sheet.csv"
        write_sheet(sheet, rows)
        with sheet.open(encoding="utf-8", newline="") as handle:
            stored = list(csv.reader(handle))
        self.assertEqual(tuple(stored[0]), SHEET_COLUMNS)
        self.assertEqual(stored[1][-1], "")

    def test_a_long_list_is_spread_evenly_and_the_same_every_time(self) -> None:
        self.store(*(similar(n) for n in range(1, 121)))

        rows = similar_sheet(self.paths, [1])

        self.assertEqual(len(rows), SHEET_SIZE)
        self.assertEqual((rows[0].hint, rows[-1].hint), ("1-1", "1-120"))
        self.assertEqual(rows, similar_sheet(self.paths, [1]))

    def test_judged_answers_give_precision_per_band(self) -> None:
        sheet = self.root / "judged.csv"
        rows = [
            ("1-1", "spelling", "0.870", "ja"),
            ("1-2", "spelling", "0.870", "n"),
            ("1-3", "spelling", "0.970", "J"),
            ("1-4", "sound", "", "nein"),
            ("1-5", "sound", "", ""),
        ]
        with sheet.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(SHEET_COLUMNS)
            for hint, method, score, correct in rows:
                writer.writerow(
                    (
                        hint,
                        1,
                        "?",
                        "Grauwassr",
                        "Grauwasser",
                        method,
                        score,
                        "nein",
                        correct,
                    )
                )

        lines = judged_precision(sheet)

        self.assertIn("similar spelling <0.9: 1 of 2 right (50.0%)", lines)
        self.assertIn("similar spelling >=0.95: 1 of 1 right (100.0%)", lines)
        self.assertIn("similar sound: 0 of 1 right (0.0%)", lines)
        self.assertIn("similar all: 2 of 4 right (50.0%)", lines)
        self.assertIn("not judged: 1", lines)
        self.assertNotIn("Grau", "\n".join(lines))

    def test_a_sheet_saved_by_a_german_spreadsheet_is_read(self) -> None:
        sheet = self.root / "judged.csv"
        sheet.write_text(
            ";".join((*SHEET_COLUMNS, "note"))
            + "\r\n1-1;1;?;Grauwassr;Grauwasser;spelling;0,970;nein;ja;x\r\n",
            encoding="utf-8-sig",
        )

        lines = judged_precision(sheet)

        self.assertIn("similar spelling >=0.95: 1 of 1 right (100.0%)", lines)

    def test_an_invalid_answer_names_the_line_but_not_the_value(self) -> None:
        sheet = self.root / "judged.csv"
        sheet.write_text(
            ",".join(SHEET_COLUMNS)
            + "\n1-1,1,?,Grauwassr,Grauwasser,sound,,nein,Ærwyn\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            CalibrationError, "line 2: field 'correct'"
        ) as caught:
            judged_precision(sheet)
        self.assertNotIn("Ærwyn", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
