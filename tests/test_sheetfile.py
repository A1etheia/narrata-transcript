import tempfile
import unittest
from pathlib import Path

from transcript.jsonfile import DataFileError
from transcript.sheetfile import read_sheet


class ReadSheetTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.sheet = Path(directory.name) / "sheet.csv"

    def test_a_german_sheet_gives_columns_and_numbered_rows(self) -> None:
        self.sheet.write_text(
            'id;note\r\na;"zwei\r\nZeilen"\r\nb; Grüße \r\n', encoding="utf-8-sig"
        )

        columns, rows = read_sheet(self.sheet, "sheet")

        self.assertEqual(columns, {"id", "note"})
        self.assertEqual(
            rows,
            [
                (2, {"id": "a", "note": "zwei\r\nZeilen"}),
                (3, {"id": "b", "note": "Grüße"}),
            ],
        )

    def test_a_comma_sheet_is_read_too(self) -> None:
        self.sheet.write_text("id,note\na,x\n", encoding="utf-8")

        self.assertEqual(
            read_sheet(self.sheet, "sheet")[1], [(2, {"id": "a", "note": "x"})]
        )

    def test_empty_rows_are_skipped_but_keep_their_number(self) -> None:
        self.sheet.write_text("id;note\r\n;\r\n\r\nc\r\n;;\r\n", encoding="utf-8")

        self.assertEqual(
            read_sheet(self.sheet, "sheet")[1], [(4, {"id": "c", "note": ""})]
        )

    def test_an_unreadable_sheet_names_the_file_only(self) -> None:
        self.sheet.write_bytes(b"id\n\xff\xfe\n")

        with self.assertRaisesRegex(DataFileError, "sheet.csv: sheet is unreadable"):
            read_sheet(self.sheet, "sheet")

    def test_an_empty_file_has_no_columns(self) -> None:
        self.sheet.write_text("", encoding="utf-8")

        self.assertEqual(read_sheet(self.sheet, "sheet"), (set(), []))


if __name__ == "__main__":
    unittest.main()
