from __future__ import annotations

from .context import InMemoryToolContext
from .fileio import read_file_lines
from .hashing import compute_chained_hashes


def build_read_tool(context: InMemoryToolContext):
    def read(file_path: str, offset: int = 0, limit: int = 200) -> str:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 0:
            raise ValueError("limit must be non-negative")

        with context.file_guard(file_path):
            all_lines = read_file_lines(file_path)
            hashes = compute_chained_hashes(all_lines, context.config)

            if not all_lines:
                context.clear_file_lines(file_path)
                return ""

            if limit == 0 or offset >= len(all_lines):
                return ""

            window_lines = all_lines[offset : offset + limit]
            window_hashes = hashes[offset : offset + limit]
            context.remember_read_window(
                file_path,
                start_line=offset,
                lines=window_lines,
                hashes=window_hashes,
            )
            return _format_window(offset, window_lines, window_hashes)

    return read


def _format_window(start_line: int, lines: list[str], hashes: list[str]) -> str:
    formatted = [
        f"{start_line + index},{chain_hash}|{content}"
        for index, (content, chain_hash) in enumerate(zip(lines, hashes, strict=True))
    ]
    return "\n".join(formatted)
