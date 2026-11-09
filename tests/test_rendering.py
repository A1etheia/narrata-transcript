import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any

from transcript.contract import validate
from transcript.rendering import (
    ExportUnreadable,
    Line,
    Paragraph,
    load_export,
    paragraphs,
    render_txt,
    write_txt,
)
from transcript.session import SessionKey, SessionPaths

# Narrata's reference fixture (IOA-1214): 320 made-up passages
FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "contract" / "session-v1.json").read_text(
        "utf-8"
    )
)
MIRA = {"participant_id": 102, "display_name": "Mira"}  # made up, as in FIXTURE


def passage(
    start: float,
    label: str,
    text: str,
    status: str = "confirmed",
    markers: tuple[tuple[str, float], ...] = (),
) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return {
        "id": f"p-{round(start * 1000):08d}-{slug}",
        "start": start,
        "end": start + 0.5,
        "speaker_label": label,
        "participant_id": None,
        "text": text,
        "asr_text": None,
        "confidence_tier": "confident",
        "review_status": status,
        "review_note": None,
        "markers": [{"type": kind, "at": at} for kind, at in markers],
        "segment_ref": None,
        "knowledge_hints": [],
        "layers": {},
    }


def document(speakers: dict[str, Any], *passages: dict[str, Any]) -> dict[str, Any]:
    """A valid export with FIXTURE's head and these speakers and passages."""
    built = copy.deepcopy(FIXTURE) | {"speakers": speakers, "passages": list(passages)}
    assert validate(built) == (), validate(built)
    return built


def rendered(built: dict[str, Any], rule: str = "turn") -> str:
    return render_txt(paragraphs(built), rule)  # type: ignore[arg-type]


class ParagraphTest(unittest.TestCase):
    def test_a_change_of_speaker_starts_a_paragraph(self) -> None:
        built = document(
            {"A": MIRA, "B": None},
            passage(1, "A", "Eins."),
            passage(2, "A", "Zwei."),
            passage(3, "B", "Drei."),
            passage(4, "A", "Vier."),
        )

        self.assertEqual(
            paragraphs(built),
            (
                Paragraph("Mira", (Line(1000, "Eins."), Line(2000, "Zwei.")), True),
                Paragraph("B (nicht zugeordnet)", (Line(3000, "Drei."),), False),
                Paragraph("Mira", (Line(4000, "Vier."),), True),
            ),
        )

    def test_two_labels_of_one_person_stay_one_paragraph(self) -> None:
        built = document(
            {"s01-A": MIRA, "s02-B": MIRA},
            passage(1, "s01-A", "Eins."),
            passage(2, "s02-B", "Zwei."),
        )

        self.assertEqual([p.speaker for p in paragraphs(built)], ["Mira"])

    def test_person_label_and_nameless_person_are_told_apart(self) -> None:
        nameless = {"participant_id": 103, "display_name": None}
        built = document(
            {"A": MIRA, "B": None, "C": nameless},
            passage(1, "A", "Eins."),
            passage(2, "B", "Zwei."),
            passage(3, "C", "Drei."),
        )

        self.assertEqual(
            [(p.speaker, p.named) for p in paragraphs(built)],
            [
                ("Mira", True),
                ("B (nicht zugeordnet)", False),
                ("C (zugeordnet, ohne Namen)", False),
            ],
        )


class MarkerTest(unittest.TestCase):
    def text(self, *passages: dict[str, Any]) -> list[str]:
        built = document({"A": MIRA}, *passages)
        return [line.shown for line in paragraphs(built)[0].lines]

    def test_text_and_markers_stay_apart_for_other_renderers(self) -> None:
        built = document({"A": MIRA}, passage(1, "A", "Ja.", "open", (("gap", 1),)))

        self.assertEqual(
            paragraphs(built)[0].lines,
            (Line(1000, "Ja.", ("[unklar 00:00:01]", "[Lücke 00:00:01]")),),
        )

    def test_an_open_passage_keeps_its_text_and_is_marked_at_its_start(self) -> None:
        self.assertEqual(
            self.text(passage(3725.5, "A", "Grauwasser", "open")),
            ["Grauwasser [unklar 01:02:05]"],
        )

    def test_an_unintelligible_passage_shows_its_marker_only(self) -> None:
        self.assertEqual(
            self.text(passage(2, "A", "", "corrected", (("unintelligible", 2.9),))),
            ["[unverständlich 00:00:02]"],
        )

    def test_each_contract_marker_is_labelled_in_file_order(self) -> None:
        markers = (("speaker_unclear", 5), ("crosstalk", 6), ("gap", 7))
        expected = (
            "Ja. [unklar 00:00:05] [Sprecher unklar 00:00:05] "
            "[durcheinander 00:00:06] [Lücke 00:00:07]"
        )
        self.assertEqual(self.text(passage(5, "A", "Ja.", "open", markers)), [expected])

    def test_settled_passages_are_not_marked(self) -> None:
        for status in ("unreviewed", "confirmed", "corrected"):
            with self.subTest(status=status):
                self.assertEqual(self.text(passage(1, "A", "Ja.", status)), ["Ja."])

    def test_line_breaks_in_the_text_become_one_space(self) -> None:
        self.assertEqual(
            self.text(passage(1, "A", " Ja,\n  genau.\r\n")), ["Ja, genau."]
        )


class LayoutTest(unittest.TestCase):
    BUILT = document(
        {"A": MIRA, "B": None},
        passage(30, "A", "Ihr erreicht Rabenfurt."),
        passage(32.9, "A", "Der Fluss steht hoch."),
        passage(62, "B", "", "corrected", (("unintelligible", 62),)),
    )

    def test_turn_gives_each_paragraph_one_time(self) -> None:
        self.assertEqual(
            rendered(self.BUILT, "turn"),
            "[00:00:30] Mira\n"
            "Ihr erreicht Rabenfurt. Der Fluss steht hoch.\n"
            "\n"
            "[00:01:02] B (nicht zugeordnet)\n"
            "[unverständlich 00:01:02]\n",
        )

    def test_passage_gives_each_passage_a_line_and_a_time(self) -> None:
        self.assertEqual(
            rendered(self.BUILT, "passage"),
            "Mira\n"
            "[00:00:30] Ihr erreicht Rabenfurt.\n"
            "[00:00:32] Der Fluss steht hoch.\n"
            "\n"
            "B (nicht zugeordnet)\n"
            "[00:01:02] [unverständlich 00:01:02]\n",
        )

    def test_nothing_of_the_head_or_stats_goes_into_the_text(self) -> None:
        text = rendered(self.BUILT)

        for value in ("spielabend-07.flac", "whisperx", "ctx-90017-1", "2026-10-30"):
            self.assertNotIn(value, text)


class FixtureTest(unittest.TestCase):
    TEXT = rendered(FIXTURE)

    def test_order_and_wording_follow_the_export(self) -> None:
        position = 0
        for found in FIXTURE["passages"]:
            if not found["text"]:
                continue
            position = self.TEXT.index(found["text"], position) + len(found["text"])

    def test_every_open_passage_and_every_marker_shows(self) -> None:
        passages = FIXTURE["passages"]
        expected = {
            "[unklar ": sum(p["review_status"] == "open" for p in passages),
            "[unverständlich ": 29,
            "[Sprecher unklar ": 11,
            "[durcheinander ": 12,
        }
        for label, count in expected.items():
            with self.subTest(label=label):
                self.assertEqual(self.TEXT.count(label), count)

    def test_equal_exports_give_equal_text(self) -> None:
        self.assertEqual(rendered(copy.deepcopy(FIXTURE)), self.TEXT)


class FileTest(unittest.TestCase):
    def setUp(self) -> None:
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.paths = SessionPaths(SessionKey("beispielgruppe", 7), Path(root.name))

    def stored(self, built: dict[str, Any]) -> None:
        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        self.paths.transcript_export.write_text(
            json.dumps(built, ensure_ascii=False), "utf-8"
        )

    def test_unicode_stays_as_it_is_in_utf_8_without_bom(self) -> None:
        words = "Grüße aus Öhringen, Œuvre 🐉, é, Æthelwyn"
        self.stored(document({"A": MIRA}, passage(1, "A", words)))

        write_txt(self.paths, rendered(load_export(self.paths)))

        raw = self.paths.transcript_text.read_bytes()
        self.assertIn(words.encode("utf-8"), raw)
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.paths.transcript_text.parent, self.paths.output_dir)

    def test_rendering_twice_gives_equal_bytes(self) -> None:
        self.stored(FIXTURE)
        written = []
        for _ in range(2):
            write_txt(self.paths, rendered(load_export(self.paths)))
            written.append(self.paths.transcript_text.read_bytes())

        self.assertEqual(written[0], written[1])

    def test_a_missing_export_points_to_the_export_command(self) -> None:
        with self.assertRaisesRegex(ExportUnreadable, "run transcript export"):
            load_export(self.paths)

    def test_an_invalid_export_is_refused_without_quoting_a_value(self) -> None:
        built = copy.deepcopy(FIXTURE)
        built["passages"][0]["review_status"] = "Grauwasser"
        self.stored(built)

        with self.assertRaises(ExportUnreadable) as raised:
            load_export(self.paths)

        message = str(raised.exception)
        self.assertIn("not rendered, 1 contract violation(s)", message)
        self.assertIn("/passages/0/review_status", message)
        self.assertNotIn("Grauwasser", message)

    def test_an_unknown_major_is_refused(self) -> None:
        self.stored(copy.deepcopy(FIXTURE) | {"contract_version": "2.0"})

        with self.assertRaisesRegex(ExportUnreadable, "unsupported major 2"):
            load_export(self.paths)

    def test_the_export_is_left_unchanged(self) -> None:
        self.stored(FIXTURE)
        before = self.paths.transcript_export.read_bytes()

        write_txt(self.paths, rendered(load_export(self.paths)))

        self.assertEqual(self.paths.transcript_export.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
