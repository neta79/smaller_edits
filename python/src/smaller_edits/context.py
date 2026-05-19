from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import RLock

from .models import FileAtom, FileLine, FileOffset, FileStateView, ReconciliationEvent, ToolConfig


class _MutableFileState:
    def __init__(self) -> None:
        self.atoms: list[FileAtom] = []


class InMemoryToolContext:
    def __init__(self, config: ToolConfig | None = None) -> None:
        self.config = config or ToolConfig()
        self._meta_lock = RLock()
        self._file_locks: dict[str, RLock] = {}
        self._file_states: dict[str, _MutableFileState] = {}

    @contextmanager
    def file_guard(self, file_path: str):
        normalized_path = self._normalize_file_path(file_path)
        file_lock = self._get_or_create_lock(normalized_path)
        with file_lock:
            yield

    def snapshot(self, file_path: str) -> FileStateView:
        normalized_path = self._normalize_file_path(file_path)
        with self.file_guard(normalized_path):
            state = self._state_for(normalized_path)
            atoms = tuple(state.atoms)
            return FileStateView(file_path=normalized_path, atoms=atoms)

    def remember_read_window(
        self,
        file_path: str,
        *,
        start_line: int,
        lines: list[str],
        hashes: list[str],
    ) -> None:
        normalized_path = self._normalize_file_path(file_path)
        state = self._state_for(normalized_path)
        atoms = list(state.atoms)
        window_end = start_line + len(lines) - 1

        if lines:
            atoms = [
                atom
                for atom in atoms
                if not (
                    isinstance(atom, FileLine)
                    and start_line <= atom.fileno <= window_end
                )
            ]
            for index, (content, chain_hash) in enumerate(zip(lines, hashes, strict=True)):
                fileno = start_line + index
                atoms.append(
                    FileLine(
                        fileno=fileno,
                        orig_fileno=fileno,
                        chain_hash=chain_hash,
                        content=content,
                    )
                )

        atoms.sort(key=self._sort_key)
        state.atoms = atoms

    def clear_file_lines(self, file_path: str) -> None:
        normalized_path = self._normalize_file_path(file_path)
        state = self._state_for(normalized_path)
        state.atoms = [atom for atom in state.atoms if not isinstance(atom, FileLine)]

    def resolve_anchor(self, file_path: str, *, lineno: int, chain_hash: str) -> FileLine | None:
        normalized_path = self._normalize_file_path(file_path)
        state = self._state_for(normalized_path)
        for atom in state.atoms:
            if (
                isinstance(atom, FileLine)
                and atom.fileno == lineno
                and atom.chain_hash == chain_hash
            ):
                return atom
        return None

    def get_cached_span(
        self, file_path: str, *, start_line: int, end_line: int
    ) -> list[FileLine] | None:
        normalized_path = self._normalize_file_path(file_path)
        state = self._state_for(normalized_path)
        line_index = {
            atom.fileno: atom for atom in state.atoms if isinstance(atom, FileLine)
        }
        span: list[FileLine] = []
        for lineno in range(start_line, end_line + 1):
            atom = line_index.get(lineno)
            if atom is None:
                return None
            span.append(atom)
        return span

    def reconcile_edit(
        self,
        file_path: str,
        *,
        events: list[ReconciliationEvent],
        return_start: int,
        return_lines: list[str],
        return_hashes: list[str],
    ) -> None:
        normalized_path = self._normalize_file_path(file_path)
        state = self._state_for(normalized_path)
        atoms = list(state.atoms)

        for event in events:
            delta = event.new_count - event.old_count
            orig_boundary = event.edit_start + event.old_count
            live_boundary = event.edit_start + event.new_count

            shifted: list[FileAtom] = []
            for atom in atoms:
                if atom.fileno >= orig_boundary:
                    shifted.append(replace(atom, fileno=atom.fileno + delta))
                else:
                    shifted.append(atom)
            atoms = shifted

            if delta != 0:
                atoms = [
                    atom
                    for atom in atoms
                    if not (
                        isinstance(atom, FileOffset)
                        and atom.orig_fileno == orig_boundary
                    )
                ]
                atoms.append(
                    FileOffset(
                        fileno=live_boundary,
                        orig_fileno=orig_boundary,
                        delta=delta,
                    )
                )

        if return_lines:
            return_end = return_start + len(return_lines) - 1
            atoms = [
                atom
                for atom in atoms
                if not (
                    isinstance(atom, FileLine)
                    and return_start <= atom.fileno <= return_end
                )
            ]
            for index, (content, chain_hash) in enumerate(
                zip(return_lines, return_hashes, strict=True)
            ):
                fileno = return_start + index
                atoms.append(
                    FileLine(
                        fileno=fileno,
                        orig_fileno=fileno,
                        chain_hash=chain_hash,
                        content=content,
                    )
                )

        atoms.sort(key=self._sort_key)
        state.atoms = atoms

    def _get_or_create_lock(self, file_path: str) -> RLock:
        with self._meta_lock:
            lock = self._file_locks.get(file_path)
            if lock is None:
                lock = RLock()
                self._file_locks[file_path] = lock
            return lock

    def _state_for(self, file_path: str) -> _MutableFileState:
        with self._meta_lock:
            state = self._file_states.get(file_path)
            if state is None:
                state = _MutableFileState()
                self._file_states[file_path] = state
            return state

    @staticmethod
    def _sort_key(atom: FileAtom) -> tuple[int, int]:
        return (atom.fileno, 0 if isinstance(atom, FileOffset) else 1)

    @staticmethod
    def _normalize_file_path(file_path: str) -> str:
        return str(Path(file_path).resolve(strict=False))


def create_in_memory_context(config: ToolConfig | None = None) -> InMemoryToolContext:
    return InMemoryToolContext(config=config)
