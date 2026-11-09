import copy
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from test_rendering import FIXTURE, MIRA, document, passage

from transcript.docx_render import render_docx, write_docx
from transcript.rendering import paragraphs, render_txt
from transcript.session import SessionKey, SessionPaths

KEY = SessionKey("beispielgruppe", 7)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "docProps/core.xml",
    "word/_rels/document.xml.rels",
    "word/styles.xml",
    "word/document.xml",
)
HEAD_STYLES = ("Title", "Subtitle", "Meta")

Runs = list[tuple[str, str | None]]  # text, character style


def rendered(built: dict[str, Any], rule: str = "turn") -> bytes:
    return render_docx(KEY, built, paragraphs(built), rule)  # type: ignore[arg-type]


def part(data: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(name)


def body(data: bytes) -> list[tuple[str | None, Runs]]:
    """Each paragraph of the document as (style, runs)."""
    found = []
    for p in ElementTree.fromstring(part(data, "word/document.xml")).iter(f"{W}p"):
        style = p.find(f"{W}pPr/{W}pStyle")
        runs = []
        for r in p.iter(f"{W}r"):
            run_style = r.find(f"{W}rPr/{W}rStyle")
            runs.append(
                (
                    "".join(t.text or "" for t in r.iter(f"{W}t")),
                    None if run_style is None else run_style.get(f"{W}val"),
                )
            )
        found.append((None if style is None else style.get(f"{W}val"), runs))
    return found


def text(paragraph: tuple[str | None, Runs]) -> str:
    return "".join(run for run, _ in paragraph[1])


def transcript(data: bytes) -> list[tuple[str | None, Runs]]:
    """The paragraphs after the head."""
    return [p for p in body(data) if p[0] not in HEAD_STYLES]


class PackageTest(unittest.TestCase):
    DATA = rendered(FIXTURE)

    def test_every_part_is_there_and_well_formed(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self.DATA)) as archive:
            self.assertEqual(tuple(archive.namelist()), PARTS)
            self.assertIsNone(archive.testzip())
        for name in PARTS:
            with self.subTest(part=name):
                ElementTree.fromstring(part(self.DATA, name))

    def test_content_types_and_relationships_name_existing_parts(self) -> None:
        types = ElementTree.fromstring(part(self.DATA, "[Content_Types].xml"))
        for override in types:
            if override.get("PartName"):
                self.assertIn(override.get("PartName", "").lstrip("/"), PARTS)
        for rels, base in (
            ("_rels/.rels", ""),
            ("word/_rels/document.xml.rels", "word/"),
        ):
            for rel in ElementTree.fromstring(part(self.DATA, rels)):
                self.assertIn(base + rel.get("Target", ""), PARTS)

    def test_used_styles_are_defined(self) -> None:
        styles = ElementTree.fromstring(part(self.DATA, "word/styles.xml"))
        defined = {s.get(f"{W}styleId") for s in styles.iter(f"{W}style")}
        used = set()
        for style, runs in body(self.DATA):
            used |= {style, *(run_style for _, run_style in runs)}
        self.assertLessEqual(used - {None}, defined)

    def test_core_properties_hold_no_time_or_person(self) -> None:
        core = part(self.DATA, "docProps/core.xml").decode("utf-8")
        with zipfile.ZipFile(io.BytesIO(self.DATA)) as archive:
            times = {info.date_time for info in archive.infolist()}
        self.assertNotIn("dcterms", core)
        self.assertNotIn("lastModifiedBy", core)
        self.assertEqual(times, {(1980, 1, 1, 0, 0, 0)})

    def test_equal_exports_give_equal_bytes(self) -> None:
        self.assertEqual(rendered(copy.deepcopy(FIXTURE)), self.DATA)


class HeadTest(unittest.TestCase):
    def head(self, built: dict[str, Any]) -> list[str]:
        return [text(p) for p in body(rendered(built)) if p[0] in HEAD_STYLES]

    def test_the_head_names_session_date_and_pipeline(self) -> None:
        self.assertEqual(
            self.head(FIXTURE),
            [
                "Transkript beispielgruppe/007",
                "Sitzung 7 · 30.10.2026",
                "Backend: whisperx / large-v3",
                "Wissens-Snapshot: ctx-90017-1",
                "Contract: 1.0",
                "Narrata: Gruppe 9001, Spielsitzung 90017",
            ],
        )

    def test_a_missing_date_and_snapshot_are_left_out_or_named(self) -> None:
        built = copy.deepcopy(FIXTURE)
        built["session"]["session_date"] = None
        built["pipeline"]["knowledge_snapshot_id"] = None

        head = self.head(built)

        self.assertEqual(head[1], "Sitzung 7")
        self.assertIn("Wissens-Snapshot: keiner", head)


class LayoutTest(unittest.TestCase):
    BUILT = document(
        {"A": MIRA, "B": None},
        passage(30, "A", "Ihr erreicht Rabenfurt."),
        passage(32.9, "A", "Der Fluss steht hoch.", "open"),
        passage(62, "B", "", "corrected", (("unintelligible", 62),)),
    )

    def test_turn_gives_a_speaker_head_with_time_and_one_text_paragraph(self) -> None:
        space = (" ", None)
        self.assertEqual(
            transcript(rendered(self.BUILT, "turn")),
            [
                ("Speaker", [("[00:00:30]", "Time"), space, ("Mira", None)]),
                (
                    None,
                    [
                        ("Ihr erreicht Rabenfurt.", None),
                        space,
                        ("Der Fluss steht hoch.", None),
                        space,
                        ("[unklar 00:00:32]", "Marker"),
                    ],
                ),
                (
                    "Speaker",
                    [
                        ("[00:01:02]", "Time"),
                        space,
                        ("B (nicht zugeordnet)", "SpeakerLabel"),
                    ],
                ),
                (None, [("[unverständlich 00:01:02]", "Marker")]),
            ],
        )

    def test_both_rules_read_as_the_txt_lines(self) -> None:
        for rule in ("turn", "passage"):
            with self.subTest(rule=rule):
                lines = render_txt(paragraphs(FIXTURE), rule).split("\n")  # type: ignore[arg-type]
                self.assertEqual(
                    [text(p) for p in transcript(rendered(FIXTURE, rule))],
                    [line for line in lines if line],
                )

    def test_a_nameless_person_shows_as_a_label(self) -> None:
        nameless = {"participant_id": 103, "display_name": None}
        built = document({"C": nameless}, passage(1, "C", "Ja."))

        head = transcript(rendered(built))[0]

        self.assertEqual(head[1][-1], ("C (zugeordnet, ohne Namen)", "SpeakerLabel"))


class TextTest(unittest.TestCase):
    def words(self, words: str) -> str:
        built = document({"A": MIRA}, passage(1, "A", words))
        return text(transcript(rendered(built))[1])

    def test_unicode_stays_as_it_is(self) -> None:
        words = "Grüße aus Öhringen, Œuvre 🐉, é, Æthelwyn, Straße"
        self.assertEqual(self.words(words), words)

    def test_xml_characters_are_escaped(self) -> None:
        self.assertEqual(self.words('a < b & "c" > d'), 'a < b & "c" > d')

    def test_characters_xml_forbids_are_dropped(self) -> None:
        self.assertEqual(self.words("Ja\x00\x07￾."), "Ja.")


class FixtureTest(unittest.TestCase):
    PARAGRAPHS = transcript(rendered(FIXTURE))

    def test_order_and_wording_follow_the_export(self) -> None:
        spoken = [
            run
            for style, runs in self.PARAGRAPHS
            if style != "Speaker"
            for run, run_style in runs
            if run_style is None and run != " "
        ]
        expected = [
            " ".join(p["text"].split()) for p in FIXTURE["passages"] if p["text"]
        ]
        self.assertEqual(spoken, expected)

    def test_every_open_passage_and_every_marker_shows_as_a_marker(self) -> None:
        markers = [
            run
            for _, runs in self.PARAGRAPHS
            for run, style in runs
            if style == "Marker"
        ]
        passages = FIXTURE["passages"]
        self.assertEqual(
            len(markers),
            sum(p["review_status"] == "open" for p in passages)
            + sum(len(p["markers"]) for p in passages),
        )


class FileTest(unittest.TestCase):
    def test_write_docx_stores_the_bytes_under_output(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = SessionPaths(KEY, Path(root))
            data = PackageTest.DATA

            write_docx(paths, data)

            self.assertEqual(paths.transcript_document.read_bytes(), data)
            self.assertEqual(
                paths.transcript_document.relative_to(root).as_posix(),
                "output/beispielgruppe/007/transcript.docx",
            )
