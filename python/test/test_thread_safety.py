from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smaller_edits import FileLine, create_in_memory_context, create_toolset
from helpers import line_prefixes


class ThreadSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.file_path = Path(self.temp_dir.name) / "sample.txt"

    def test_concurrent_access_does_not_corrupt_state(self) -> None:
        self.file_path.write_text("root\n", encoding="utf-8")
        context = create_in_memory_context()
        tools = create_toolset(context)
        errors: list[Exception] = []

        def reader() -> None:
            try:
                for _ in range(20):
                    tools.read(str(self.file_path), offset=0, limit=50)
            except Exception as error:  # pragma: no cover - test guard
                errors.append(error)

        def editor(label: str) -> None:
            try:
                for _ in range(5):
                    text = tools.read(str(self.file_path), offset=0, limit=50)
                    last_anchor = line_prefixes(text)[-1]
                    tools.edit(
                        str(self.file_path),
                        operations=[
                            {
                                "kind": "insert_after",
                                "start": last_anchor,
                                "content": label,
                            }
                        ],
                    )
            except Exception as error:  # pragma: no cover - test guard
                errors.append(error)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=editor, args=("A",)),
            threading.Thread(target=editor, args=("B",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        tools.read(str(self.file_path), offset=0, limit=100)
        line_atoms = [
            atom
            for atom in context.snapshot(str(self.file_path)).atoms
            if isinstance(atom, FileLine)
        ]
        self.assertEqual([atom.fileno for atom in line_atoms], list(range(len(line_atoms))))

    def test_path_aliases_share_context_state(self) -> None:
        self.file_path.write_text("root\nchild\n", encoding="utf-8")
        alias_path = Path(self.temp_dir.name) / "alias.txt"
        alias_path.symlink_to(self.file_path)
        context = create_in_memory_context()
        tools = create_toolset(context)

        tools.read(str(alias_path), offset=0, limit=2)

        direct_atoms = context.snapshot(str(self.file_path)).atoms
        alias_atoms = context.snapshot(str(alias_path)).atoms

        self.assertEqual(direct_atoms, alias_atoms)


if __name__ == "__main__":
    unittest.main()
