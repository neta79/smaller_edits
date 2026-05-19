from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smaller_edits import create_in_memory_context, create_toolset
from helpers import line_contents, line_prefixes


class EditToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.file_path = Path(self.temp_dir.name) / "sample.txt"

    def test_replace_range_updates_file_and_returns_fresh_context(self) -> None:
        self.file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        context = create_in_memory_context()
        tools = create_toolset(context)

        read_text = tools.read(str(self.file_path), offset=0, limit=3)
        beta_anchor = line_prefixes(read_text)[1]
        result = tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "replace_range",
                    "start": beta_anchor,
                    "end": beta_anchor,
                    "content": "BETA",
                }
            ],
        )

        self.assertIn("text", result)
        self.assertEqual(
            self.file_path.read_text(encoding="utf-8").splitlines(),
            ["alpha", "BETA", "gamma"],
        )
        self.assertEqual(line_contents(result["text"]), ["alpha", "BETA", "gamma"])

    def test_insert_after_appends_lines_after_anchor(self) -> None:
        self.file_path.write_text("alpha\nbeta\n", encoding="utf-8")
        tools = create_toolset(create_in_memory_context())

        read_text = tools.read(str(self.file_path), offset=0, limit=2)
        alpha_anchor = line_prefixes(read_text)[0]
        result = tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "insert_after",
                    "start": alpha_anchor,
                    "content": "inserted",
                }
            ],
        )

        self.assertIn("text", result)
        self.assertEqual(
            self.file_path.read_text(encoding="utf-8").splitlines(),
            ["alpha", "inserted", "beta"],
        )

    def test_delete_range_removes_targeted_lines(self) -> None:
        self.file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        tools = create_toolset(create_in_memory_context())

        read_text = tools.read(str(self.file_path), offset=0, limit=3)
        prefixes = line_prefixes(read_text)
        result = tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "delete_range",
                    "start": prefixes[1],
                    "end": prefixes[2],
                }
            ],
        )

        self.assertIn("text", result)
        self.assertEqual(
            self.file_path.read_text(encoding="utf-8").splitlines(),
            ["alpha"],
        )

    def test_insert_at_start_populates_empty_file(self) -> None:
        self.file_path.write_text("", encoding="utf-8")
        tools = create_toolset(create_in_memory_context())

        result = tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "insert_at_start",
                    "content": "first\nsecond",
                }
            ],
        )

        self.assertIn("text", result)
        self.assertEqual(
            self.file_path.read_text(encoding="utf-8").splitlines(),
            ["first", "second"],
        )


if __name__ == "__main__":
    unittest.main()
