from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smaller_edits import FileLine, create_in_memory_context, create_toolset
from helpers import line_contents


class ReadToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.file_path = Path(self.temp_dir.name) / "sample.txt"

    def test_read_returns_prefixed_lines_and_updates_state(self) -> None:
        self.file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        context = create_in_memory_context()
        tools = create_toolset(context)

        text = tools.read(str(self.file_path), offset=1, limit=2)

        self.assertEqual(line_contents(text), ["beta", "gamma"])
        atoms = context.snapshot(str(self.file_path)).atoms
        line_atoms = [atom for atom in atoms if isinstance(atom, FileLine)]
        self.assertEqual([atom.fileno for atom in line_atoms], [1, 2])

    def test_overlapping_read_replaces_old_window_atoms(self) -> None:
        self.file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        context = create_in_memory_context()
        tools = create_toolset(context)

        tools.read(str(self.file_path), offset=0, limit=3)
        tools.read(str(self.file_path), offset=1, limit=1)

        atoms = context.snapshot(str(self.file_path)).atoms
        line_atoms = [atom for atom in atoms if isinstance(atom, FileLine)]
        self.assertEqual([atom.fileno for atom in line_atoms], [0, 1, 2])
        self.assertEqual(len(line_atoms), 3)

    def test_reading_empty_file_clears_stale_line_atoms(self) -> None:
        self.file_path.write_text("alpha\nbeta\n", encoding="utf-8")
        context = create_in_memory_context()
        tools = create_toolset(context)

        tools.read(str(self.file_path), offset=0, limit=2)
        self.file_path.write_text("", encoding="utf-8")

        text = tools.read(str(self.file_path), offset=0, limit=10)

        self.assertEqual(text, "")
        atoms = context.snapshot(str(self.file_path)).atoms
        line_atoms = [atom for atom in atoms if isinstance(atom, FileLine)]
        self.assertEqual(line_atoms, [])


if __name__ == "__main__":
    unittest.main()
