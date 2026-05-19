from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smaller_edits.hashing import canonicalize_line, compute_chained_hashes
from smaller_edits.models import ToolConfig


class HashingTests(unittest.TestCase):
    def test_identical_consecutive_lines_get_distinct_hashes(self) -> None:
        hashes = compute_chained_hashes(["", "", ""], ToolConfig(hash_width=4))
        self.assertEqual(len(hashes), 3)
        self.assertEqual(len(set(hashes)), 3)

    def test_canonicalization_removes_eol_characters(self) -> None:
        self.assertEqual(canonicalize_line("hello\r\n"), "hello")

    def test_optional_space_trimming_is_supported(self) -> None:
        self.assertEqual(
            canonicalize_line("  hello  ", trim_surrounding_spaces=True),
            "hello",
        )


if __name__ == "__main__":
    unittest.main()
