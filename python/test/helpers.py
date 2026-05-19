from __future__ import annotations


def line_prefixes(text: str) -> list[str]:
    if not text:
        return []
    return [line.split("|", 1)[0] for line in text.splitlines()]


def line_contents(text: str) -> list[str]:
    if not text:
        return []
    return [line.split("|", 1)[1] for line in text.splitlines()]
