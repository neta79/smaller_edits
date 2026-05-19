from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smaller_edits import create_in_memory_context, create_toolset
from helpers import line_prefixes


class FailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.file_path = Path(self.temp_dir.name) / "sample.txt"

    def test_edit_fails_when_span_was_not_fully_read(self) -> None:
        self.file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        tools = create_toolset(create_in_memory_context())

        read_text = tools.read(str(self.file_path), offset=0, limit=1)
        alpha_anchor = line_prefixes(read_text)[0]
        result = tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "replace_range",
                    "start": alpha_anchor,
                    "end": "1,missing",
                    "content": "x",
                }
            ],
        )

        self.assertEqual(result["type"], "ANCHOR_NOT_FOUND")

    def test_edit_fails_when_live_content_has_drifted(self) -> None:
        self.file_path.write_text("alpha\nbeta\n", encoding="utf-8")
        tools = create_toolset(create_in_memory_context())

        read_text = tools.read(str(self.file_path), offset=0, limit=2)
        beta_anchor = line_prefixes(read_text)[1]
        self.file_path.write_text("alpha\nchanged\n", encoding="utf-8")

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

        self.assertEqual(result["type"], "CONTENT_DRIFT")

    def test_overlapping_batch_is_rejected(self) -> None:
        self.file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        tools = create_toolset(create_in_memory_context())

        read_text = tools.read(str(self.file_path), offset=0, limit=3)
        prefixes = line_prefixes(read_text)
        result = tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "replace_range",
                    "start": prefixes[1],
                    "end": prefixes[1],
                    "content": "BETA",
                },
                {
                    "kind": "insert_after",
                    "start": prefixes[1],
                    "content": "after-beta",
                },
            ],
        )

        self.assertEqual(result["type"], "CONFLICT")


if __name__ == "__main__":
    unittest.main()
