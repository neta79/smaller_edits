from __future__ import annotations

from dataclasses import dataclass

from .context import InMemoryToolContext
from .errors import EditError
from .fileio import read_file_lines, write_file_lines
from .hashing import compute_chained_hashes
from .read_tool import _format_window
from .models import ReconciliationEvent


@dataclass(frozen=True)
class _ResolvedOperation:
    kind: str
    start_anchor: str | None
    end_anchor: str | None
    edit_start: int
    old_count: int
    new_lines: list[str]

    @property
    def delta(self) -> int:
        return len(self.new_lines) - self.old_count


def build_edit_tool(context: InMemoryToolContext):
    def edit(
        file_path: str,
        operations: list[dict],
        context_before: int | None = None,
        context_after: int | None = None,
    ) -> dict[str, object]:
        if not operations:
            return EditError("INVALID_OPERATION", "at least one operation is required").to_dict()

        before = context.config.context_before if context_before is None else context_before
        after = context.config.context_after if context_after is None else context_after
        if before < 0 or after < 0:
            return EditError("INVALID_OPERATION", "context values must be non-negative").to_dict()

        with context.file_guard(file_path):
            try:
                live_lines = read_file_lines(file_path)
                resolved = _resolve_operations(context, file_path, live_lines, operations)
                _validate_non_overlapping(resolved)

                updated_lines = list(live_lines)
                for operation in sorted(resolved, key=lambda item: item.edit_start, reverse=True):
                    updated_lines[
                        operation.edit_start : operation.edit_start + operation.old_count
                    ] = operation.new_lines

                write_file_lines(file_path, updated_lines)

                final_hashes = compute_chained_hashes(updated_lines, context.config)
                window_start, window_end = _compute_return_window(
                    resolved,
                    updated_line_count=len(updated_lines),
                    context_before=before,
                    context_after=after,
                )
                return_lines = updated_lines[window_start : window_end + 1]
                return_hashes = final_hashes[window_start : window_end + 1]

                context.reconcile_edit(
                    file_path,
                    events=[
                        ReconciliationEvent(
                            edit_start=item.edit_start,
                            old_count=item.old_count,
                            new_count=len(item.new_lines),
                        )
                        for item in sorted(resolved, key=lambda item: item.edit_start, reverse=True)
                    ],
                    return_start=window_start,
                    return_lines=return_lines,
                    return_hashes=return_hashes,
                )

                return {
                    "text": _format_window(window_start, return_lines, return_hashes),
                    "startLine": window_start,
                    "endLine": window_end,
                }
            except EditError as error:
                return error.to_dict()

    return edit


def _resolve_operations(
    context: InMemoryToolContext,
    file_path: str,
    live_lines: list[str],
    operations: list[dict],
) -> list[_ResolvedOperation]:
    resolved: list[_ResolvedOperation] = []

    for operation in operations:
        if not isinstance(operation, dict):
            raise EditError("INVALID_OPERATION", "operations must be objects")
        kind = operation.get("kind")
        if kind == "replace_range":
            start_anchor = _require_string(operation, "start", kind)
            end_anchor = _require_string(operation, "end", kind)
            content = _optional_string(operation.get("content"), field_name="content", kind=kind)
            start_line, start_hash = _parse_anchor(start_anchor)
            end_line, end_hash = _parse_anchor(end_anchor)
            start_atom = context.resolve_anchor(file_path, lineno=start_line, chain_hash=start_hash)
            end_atom = context.resolve_anchor(file_path, lineno=end_line, chain_hash=end_hash)
            if start_atom is None or end_atom is None:
                raise EditError(
                    "ANCHOR_NOT_FOUND",
                    "no matching FileLine atom in shared state",
                    start=start_anchor,
                    end=end_anchor,
                )
            if start_atom.fileno > end_atom.fileno:
                raise EditError(
                    "INVALID_OPERATION",
                    "start anchor must not come after end anchor",
                    start=start_anchor,
                    end=end_anchor,
                )
            cached_span = context.get_cached_span(
                file_path,
                start_line=start_atom.fileno,
                end_line=end_atom.fileno,
            )
            if cached_span is None:
                raise EditError(
                    "SPAN_NOT_CACHED",
                    "target span crosses a gap in shared state",
                    start=start_anchor,
                    end=end_anchor,
                )
            _verify_live_span(
                live_lines,
                cached_span,
                start=start_anchor,
                end=end_anchor,
            )
            resolved.append(
                _ResolvedOperation(
                    kind=kind,
                    start_anchor=start_anchor,
                    end_anchor=end_anchor,
                    edit_start=start_atom.fileno,
                    old_count=end_atom.fileno - start_atom.fileno + 1,
                    new_lines=_split_content(content),
                )
            )
        elif kind == "delete_range":
            start_anchor = _require_string(operation, "start", kind)
            end_anchor = _require_string(operation, "end", kind)
            start_line, start_hash = _parse_anchor(start_anchor)
            end_line, end_hash = _parse_anchor(end_anchor)
            start_atom = context.resolve_anchor(file_path, lineno=start_line, chain_hash=start_hash)
            end_atom = context.resolve_anchor(file_path, lineno=end_line, chain_hash=end_hash)
            if start_atom is None or end_atom is None:
                raise EditError(
                    "ANCHOR_NOT_FOUND",
                    "no matching FileLine atom in shared state",
                    start=start_anchor,
                    end=end_anchor,
                )
            if start_atom.fileno > end_atom.fileno:
                raise EditError(
                    "INVALID_OPERATION",
                    "start anchor must not come after end anchor",
                    start=start_anchor,
                    end=end_anchor,
                )
            cached_span = context.get_cached_span(
                file_path,
                start_line=start_atom.fileno,
                end_line=end_atom.fileno,
            )
            if cached_span is None:
                raise EditError(
                    "SPAN_NOT_CACHED",
                    "target span crosses a gap in shared state",
                    start=start_anchor,
                    end=end_anchor,
                )
            _verify_live_span(
                live_lines,
                cached_span,
                start=start_anchor,
                end=end_anchor,
            )
            resolved.append(
                _ResolvedOperation(
                    kind=kind,
                    start_anchor=start_anchor,
                    end_anchor=end_anchor,
                    edit_start=start_atom.fileno,
                    old_count=end_atom.fileno - start_atom.fileno + 1,
                    new_lines=[],
                )
            )
        elif kind == "insert_after":
            start_anchor = _require_string(operation, "start", kind)
            content = _optional_string(operation.get("content"), field_name="content", kind=kind)
            start_line, start_hash = _parse_anchor(start_anchor)
            start_atom = context.resolve_anchor(file_path, lineno=start_line, chain_hash=start_hash)
            if start_atom is None:
                raise EditError(
                    "ANCHOR_NOT_FOUND",
                    "no matching FileLine atom in shared state",
                    start=start_anchor,
                )
            if start_atom.fileno >= len(live_lines):
                raise EditError(
                    "LINE_OUT_OF_BOUNDS",
                    "anchor line is out of bounds",
                    start=start_anchor,
                )
            if live_lines[start_atom.fileno] != start_atom.content:
                raise EditError(
                    "CONTENT_DRIFT",
                    "live file content does not match remembered anchor",
                    start=start_anchor,
                )
            resolved.append(
                _ResolvedOperation(
                    kind=kind,
                    start_anchor=start_anchor,
                    end_anchor=None,
                    edit_start=start_atom.fileno + 1,
                    old_count=0,
                    new_lines=_split_content(content),
                )
            )
        elif kind == "insert_at_start":
            content = _optional_string(operation.get("content"), field_name="content", kind=kind)
            resolved.append(
                _ResolvedOperation(
                    kind=kind,
                    start_anchor=None,
                    end_anchor=None,
                    edit_start=0,
                    old_count=0,
                    new_lines=_split_content(content),
                )
            )
        else:
            raise EditError("INVALID_OPERATION", f"unsupported operation kind: {kind!r}")

    return resolved


def _verify_live_span(
    live_lines: list[str],
    cached_span,
    *,
    start: str,
    end: str,
) -> None:
    if not cached_span:
        raise EditError("SPAN_NOT_CACHED", "target span crosses a gap in shared state", start=start, end=end)
    first_line = cached_span[0].fileno
    last_line = cached_span[-1].fileno
    if first_line < 0 or last_line >= len(live_lines):
        raise EditError("LINE_OUT_OF_BOUNDS", "line number out of bounds", start=start, end=end)
    expected = [atom.content for atom in cached_span]
    actual = live_lines[first_line : last_line + 1]
    if actual != expected:
        raise EditError(
            "CONTENT_DRIFT",
            "live file content does not match remembered span",
            start=start,
            end=end,
        )


def _validate_non_overlapping(operations: list[_ResolvedOperation]) -> None:
    for index, left in enumerate(operations):
        for right in operations[index + 1 :]:
            if _operations_conflict(left, right):
                raise EditError(
                    "CONFLICT",
                    "overlapping batch",
                    start=left.start_anchor,
                    end=right.end_anchor or right.start_anchor,
                )


def _operations_conflict(left: _ResolvedOperation, right: _ResolvedOperation) -> bool:
    if left.old_count == 0 and right.old_count == 0:
        return left.edit_start == right.edit_start

    if left.old_count == 0:
        return _boundary_conflicts(right, left.edit_start)
    if right.old_count == 0:
        return _boundary_conflicts(left, right.edit_start)

    left_start = left.edit_start
    left_end = left.edit_start + left.old_count - 1
    right_start = right.edit_start
    right_end = right.edit_start + right.old_count - 1
    return not (left_end < right_start or right_end < left_start)


def _boundary_conflicts(operation: _ResolvedOperation, boundary: int) -> bool:
    start = operation.edit_start
    end = operation.edit_start + operation.old_count
    return start <= boundary <= end


def _compute_return_window(
    operations: list[_ResolvedOperation],
    *,
    updated_line_count: int,
    context_before: int,
    context_after: int,
) -> tuple[int, int]:
    if updated_line_count == 0:
        return 0, -1

    changed_starts: list[int] = []
    changed_ends: list[int] = []
    for operation in operations:
        shift = sum(
            other.delta for other in operations if other.edit_start < operation.edit_start
        )
        final_start = operation.edit_start + shift
        if operation.new_lines:
            final_end = final_start + len(operation.new_lines) - 1
        else:
            final_end = min(final_start, updated_line_count - 1)
        changed_starts.append(min(final_start, updated_line_count - 1))
        changed_ends.append(max(final_end, 0))

    start_line = max(0, min(changed_starts) - context_before)
    end_line = min(updated_line_count - 1, max(changed_ends) + context_after)
    return start_line, end_line


def _parse_anchor(anchor: str) -> tuple[int, str]:
    if not isinstance(anchor, str) or "," not in anchor:
        raise EditError("INVALID_OPERATION", f"invalid anchor: {anchor!r}")
    lineno_text, chain_hash = anchor.split(",", 1)
    try:
        lineno = int(lineno_text)
    except ValueError as error:
        raise EditError("INVALID_OPERATION", f"invalid anchor: {anchor!r}") from error
    if lineno < 0 or not chain_hash:
        raise EditError("INVALID_OPERATION", f"invalid anchor: {anchor!r}")
    return lineno, chain_hash


def _require_string(operation: dict, field_name: str, kind: str) -> str:
    value = operation.get(field_name)
    if not isinstance(value, str):
        raise EditError(
            "INVALID_OPERATION",
            f"{kind} requires string field {field_name!r}",
        )
    return value


def _optional_string(value: object, *, field_name: str, kind: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EditError(
            "INVALID_OPERATION",
            f"{kind} requires string field {field_name!r}",
        )
    return value


def _split_content(content: str) -> list[str]:
    return content.splitlines()
