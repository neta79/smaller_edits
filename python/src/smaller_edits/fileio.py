from __future__ import annotations

from pathlib import Path


def read_file_lines(file_path: str) -> list[str]:
    text = Path(file_path).read_text(encoding="utf-8")
    return text.splitlines()


def write_file_lines(file_path: str, lines: list[str]) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not lines:
        path.write_text("", encoding="utf-8")
        return
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
