from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Union


@dataclass(frozen=True)
class ToolConfig:
    hash_width: int = 4
    context_before: int = 2
    context_after: int = 2
    trim_surrounding_spaces: bool = False

    def __post_init__(self) -> None:
        if self.hash_width < 4:
            raise ValueError("hash_width must be at least 4")
        if self.context_before < 0 or self.context_after < 0:
            raise ValueError("context sizes must be non-negative")


@dataclass(frozen=True)
class FileLine:
    fileno: int
    orig_fileno: int
    chain_hash: str
    content: str


@dataclass(frozen=True)
class FileOffset:
    fileno: int
    orig_fileno: int
    delta: int


FileAtom = Union[FileLine, FileOffset]


@dataclass(frozen=True)
class FileStateView:
    file_path: str
    atoms: tuple[FileAtom, ...]


@dataclass(frozen=True)
class Toolset:
    read: Callable[..., str]
    edit: Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ReconciliationEvent:
    edit_start: int
    old_count: int
    new_count: int
