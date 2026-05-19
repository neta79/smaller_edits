from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smaller_edits import FileLine, FileOffset, create_in_memory_context, create_toolset
from helpers import line_prefixes


class StateReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.file_path = Path(self.temp_dir.name) / "sample.txt"

    def test_expanding_one_line_shifts_downstream_atoms_and_records_offset(self) -> None:
        self.file_path.write_text(
            "package main\n\nimport (\n    \"fmt\"\n)\n\nfunc main() {\n",
            encoding="utf-8",
        )
        context = create_in_memory_context()
        tools = create_toolset(context)

        read_text = tools.read(str(self.file_path), offset=0, limit=7)
        import_anchor = line_prefixes(read_text)[2]
        tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "replace_range",
                    "start": import_anchor,
                    "end": import_anchor,
                    "content": '"fmt"\n"os"\n"strings"',
                }
            ],
        )

        atoms = context.snapshot(str(self.file_path)).atoms
        offsets = [atom for atom in atoms if isinstance(atom, FileOffset)]
        lines = [atom for atom in atoms if isinstance(atom, FileLine)]
        func_line = next(atom for atom in lines if atom.content == "func main() {")

        self.assertTrue(any(atom.fileno == 5 and atom.orig_fileno == 3 and atom.delta == 2 for atom in offsets))
        self.assertEqual(func_line.fileno, 8)

    def test_deleting_line_shifts_downstream_atoms_and_records_negative_offset(self) -> None:
        self.file_path.write_text("a\nb\nc\nd\n", encoding="utf-8")
        context = create_in_memory_context()
        tools = create_toolset(context)

        read_text = tools.read(str(self.file_path), offset=0, limit=4)
        delete_anchor = line_prefixes(read_text)[1]
        tools.edit(
            str(self.file_path),
            operations=[
                {
                    "kind": "delete_range",
                    "start": delete_anchor,
                    "end": delete_anchor,
                }
            ],
        )

        atoms = context.snapshot(str(self.file_path)).atoms
        offsets = [atom for atom in atoms if isinstance(atom, FileOffset)]
        lines = [atom for atom in atoms if isinstance(atom, FileLine)]
        d_line = next(atom for atom in lines if atom.content == "d")

        self.assertTrue(any(atom.fileno == 1 and atom.orig_fileno == 2 and atom.delta == -1 for atom in offsets))
        self.assertEqual(d_line.fileno, 2)


if __name__ == "__main__":
    unittest.main()
