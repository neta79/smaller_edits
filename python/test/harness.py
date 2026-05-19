from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4
from typing import Any, Literal, Sequence

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from smaller_edits import create_in_memory_context, create_toolset
from smaller_edits.context import InMemoryToolContext
from smaller_edits.fileio import read_file_lines
from smaller_edits.models import FileLine


AGNO_IMPORT_ERROR_MESSAGE = (
    "Agno is required for the demo harness. Install it in the target environment with `pip install agno`."
)
OPENAI_IMPORT_ERROR_MESSAGE = (
    "The selected Agno model requires the `openai` package. Install it in the target environment with `pip install openai`."
)

DEFAULT_AGENT_INSTRUCTIONS = [
    "For small files, start with `read(path, offset=0, limit=200)`.",
    "If the user asks to change a file, do not stop after `read`. You must actually call `edit`.",
    "Once the needed anchor is visible, call `edit` immediately. Do not read the same file again unless `edit` fails.",
    "A read line looks like `1,ujzi|two`. The anchor is only `1,ujzi`.",
    "Replace one line with: `edit(path='replace-3.txt', kind='replace_range', start='1,ujzi', end='1,ujzi', content='TWO')`.",
    "If read returns `1,ZeFd|beta`, then the anchor is `1,ZeFd`, not `beta`.",
    "Insert after one line with: `edit(path='basic-4.txt', kind='insert_after', start='1,ZeFd', content='BETA2')`.",
    "Delete a range with: `edit(path='basic-4.txt', kind='delete_range', start='2,0yzS', end='3,fL6q')`.",
    "If the task is to delete `gamma` and `delta` from `basic-4.txt`, then after the read you should immediately call `edit(path='basic-4.txt', kind='delete_range', start='2,0yzS', end='3,fL6q')`.",
    "The anchors shown in examples are patterns only. Do not reuse them blindly. Always get fresh anchors by calling `read` on the current file first.",
    "Never use plain text like `beta`. Never type placeholder words like `lineno` or `chainHash`. Always include every required field.",
    "After `edit`, trust the returned `text` literally. It is the new file window.",
]


@dataclass(frozen=True)
class FunctionalHarnessConfig:
    model_name: str = "openai:gpt-4.1-mini"
    base_url: str | None = None
    api_key: str | None = None
    env_file: Path | None = None
    include_workspace_discovery: bool = False
    include_debug_state: bool = False
    vector_file: Path | None = None
    vector_names: tuple[str, ...] = ()


class ScopedLinehashToolAdapter:
    def __init__(
        self,
        root_dir: str | Path,
        context: InMemoryToolContext | None = None,
    ) -> None:
        self.root_dir = Path(root_dir).resolve(strict=False)
        if not self.root_dir.exists() or not self.root_dir.is_dir():
            raise ValueError(f"root_dir must be an existing directory: {root_dir}")
        self.context = context or create_in_memory_context()
        self._toolset = create_toolset(self.context)

    def read(self, path: str, offset: int = 0, limit: int = 200) -> str:
        """Read file lines. Example output line: `1,ujzi|two`."""
        try:
            resolved_path = self._resolve_user_path(path)
            return self._toolset.read(str(resolved_path), offset=offset, limit=limit)
        except Exception as error:
            return f"Error reading file: {error}"

    def edit(
        self,
        path: str,
        kind: Literal[
            "replace_range",
            "insert_after",
            "delete_range",
            "insert_at_start",
        ],
        start: str = "",
        end: str = "",
        content: str = "",
    ) -> dict[str, Any]:
        """Edit one contiguous block.

        Replace one line with `kind='replace_range', start='1,ujzi', end='1,ujzi', content='TWO'`.
        If read returns `1,ZeFd|beta`, use anchor `1,ZeFd`, not `beta`.
        Insert after one line with `kind='insert_after', start='1,ZeFd', content='BETA2'`.
        Delete a range with `kind='delete_range', start='2,0yzS', end='3,fL6q'`.
        Use anchors copied from `read`. Do not use plain text like `two` or `beta`.
        """
        try:
            resolved_path = self._resolve_user_path(path)
            before_lines = read_file_lines(str(resolved_path))
            operation = _build_single_operation(
                kind=kind,
                start=_normalize_anchor(start),
                end=_normalize_anchor(end),
                content=content,
            )
            result = self._toolset.edit(
                str(resolved_path),
                operations=[operation],
            )
            if "text" in result:
                after_lines = read_file_lines(str(resolved_path))
                if before_lines == after_lines:
                    return {
                        "type": "NO_OP",
                        "reason": "edit produced no file change; verify the replacement or inserted text",
                    }
            return result
        except Exception as error:
            return {
                "type": "UNEXPECTED_ERROR",
                "reason": str(error),
            }

    def show_state(self, path: str) -> dict[str, Any]:
        try:
            resolved_path = self._resolve_user_path(path)
            snapshot = self.context.snapshot(str(resolved_path))
            atoms = []
            for atom in snapshot.atoms:
                atom_type = "file_line" if isinstance(atom, FileLine) else "file_offset"
                atoms.append({"type": atom_type, **asdict(atom)})
            return {
                "root_dir": str(self.root_dir),
                "resolved_path": snapshot.file_path,
                "display_path": str(resolved_path.relative_to(self.root_dir)),
                "atoms": atoms,
            }
        except Exception as error:
            return {
                "type": "UNEXPECTED_ERROR",
                "reason": str(error),
            }

    def _resolve_user_path(self, path: str) -> Path:
        if not path.strip():
            raise ValueError("path cannot be empty")
        user_path = Path(path)
        candidate = user_path if user_path.is_absolute() else self.root_dir / user_path
        resolved_path = candidate.resolve(strict=False)
        try:
            resolved_path.relative_to(self.root_dir)
        except ValueError as error:
            raise ValueError(f"path escapes harness root: {path}") from error
        return resolved_path

def create_agno_demo_tools(
    root_dir: str | Path,
    context: InMemoryToolContext | None = None,
    *,
    include_workspace_discovery: bool = False,
    include_debug_state: bool = False,
) -> list[Any]:
    _require_agno()
    adapter = ScopedLinehashToolAdapter(root_dir=root_dir, context=context)
    tools: list[Any] = [adapter.read, adapter.edit]
    if include_debug_state:
        tools.append(adapter.show_state)
    if include_workspace_discovery:
        from agno.tools.workspace import Workspace

        tools.append(Workspace(str(adapter.root_dir), allowed=["list", "search"]))
    return tools


def create_agno_demo_agent(
    *,
    model: Any = "openai:gpt-4.1-mini",
    root_dir: str | Path = ".",
    context: InMemoryToolContext | None = None,
    include_workspace_discovery: bool = False,
    include_debug_state: bool = False,
    name: str = "Smaller Edits Demo Agent",
    extra_instructions: Sequence[str] | None = None,
    load_env: bool = True,
    env_file: str | Path | None = None,
    env_override: bool = False,
    **agent_kwargs: Any,
) -> Any:
    _require_agno()
    if load_env:
        load_demo_env(root_dir=root_dir, env_file=env_file, override=env_override)

    from agno.agent import Agent

    if "tools" in agent_kwargs:
        raise ValueError("create_agno_demo_agent manages tools itself; pass extra_instructions instead")

    instructions = list(DEFAULT_AGENT_INSTRUCTIONS)
    if extra_instructions:
        instructions.extend(extra_instructions)

    markdown = agent_kwargs.pop("markdown", False)
    cache_session = agent_kwargs.pop("cache_session", False)
    add_history_to_context = agent_kwargs.pop("add_history_to_context", False)
    num_history_runs = agent_kwargs.pop("num_history_runs", 8)
    session_id = agent_kwargs.pop("session_id", f"linehash-console-{uuid4()}")
    description = agent_kwargs.pop(
        "description",
        "Use read and edit on linehash-anchored files.",
    )

    try:
        return Agent(
            model=model,
            name=name,
            session_id=session_id,
            cache_session=cache_session,
            add_history_to_context=add_history_to_context,
            num_history_runs=num_history_runs,
            description=description,
            instructions=instructions,
            markdown=markdown,
            tools=create_agno_demo_tools(
                root_dir=root_dir,
                context=context,
                include_workspace_discovery=include_workspace_discovery,
                include_debug_state=include_debug_state,
            ),
            **agent_kwargs,
        )
    except ImportError as error:
        if _looks_like_missing_openai_dependency(error, model):
            raise RuntimeError(OPENAI_IMPORT_ERROR_MESSAGE) from error
        raise


def load_demo_env(
    *,
    root_dir: str | Path = ".",
    env_file: str | Path | None = None,
    override: bool = False,
) -> Path | None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    for candidate in _env_candidates(root_dir=root_dir, env_file=env_file):
        if candidate.is_file():
            load_dotenv(candidate, override=override)
            return candidate
    return None


def build_model_from_config(config: FunctionalHarnessConfig) -> Any:
    load_demo_env(root_dir=".", env_file=config.env_file, override=False)
    if config.base_url:
        _require_agno()
        from agno.models.openai.like import OpenAILike

        return OpenAILike(
            id=config.model_name,
            base_url=config.base_url,
            api_key=config.api_key or os.getenv("OPENAI_API_KEY") or "ollama",
        )
    return config.model_name


def load_functional_config() -> FunctionalHarnessConfig:
    env_file = os.getenv("LINEHASH_TEST_ENV_FILE")
    vector_file = os.getenv("LINEHASH_TEST_VECTOR_FILE")
    vector_names_text = os.getenv("LINEHASH_TEST_VECTOR_NAMES") or os.getenv("LINEHASH_TEST_VECTOR_NAME", "")
    vector_names = tuple(name.strip() for name in vector_names_text.split(",") if name.strip())
    return FunctionalHarnessConfig(
        model_name=os.getenv("LINEHASH_TEST_MODEL", "openai:gpt-4.1-mini"),
        base_url=os.getenv("LINEHASH_TEST_BASE_URL"),
        api_key=os.getenv("LINEHASH_TEST_API_KEY"),
        env_file=Path(env_file).resolve(strict=False) if env_file else None,
        include_workspace_discovery=_env_flag("LINEHASH_TEST_INCLUDE_WORKSPACE_DISCOVERY", default=False),
        include_debug_state=_env_flag("LINEHASH_TEST_INCLUDE_DEBUG_STATE", default=False),
        vector_file=Path(vector_file).resolve(strict=False) if vector_file else None,
        vector_names=vector_names,
    )


def run_console_harness(
    *,
    model: Any = "openai:gpt-4.1-mini",
    root_dir: str | Path = ".",
    prompt: str | None = None,
    include_workspace_discovery: bool = False,
    include_debug_state: bool = False,
    load_env: bool = True,
    env_file: str | Path | None = None,
    env_override: bool = False,
    stream: bool = True,
    **agent_kwargs: Any,
) -> int:
    agent = create_agno_demo_agent(
        model=model,
        root_dir=root_dir,
        include_workspace_discovery=include_workspace_discovery,
        include_debug_state=include_debug_state,
        load_env=load_env,
        env_file=env_file,
        env_override=env_override,
        **agent_kwargs,
    )

    if prompt is not None:
        agent.print_response(prompt, stream=stream)
        return 0

    root_path = Path(root_dir).resolve(strict=False)
    print(f"Linehash Agno console harness. Root: {root_path}")
    print("Commands: /exit, /quit")
    while True:
        try:
            user_input = input("\n> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            return 0

        try:
            agent.print_response(user_input, stream=stream)
        except KeyboardInterrupt:
            print("\nInterrupted.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Console-style Agno demo harness for the linehash-aware edit toolset."
    )
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--model", default="openai:gpt-4.1-mini")
    parser.add_argument("--prompt")
    parser.add_argument("--env-file")
    parser.add_argument("--no-env", action="store_true")
    parser.add_argument("--env-override", action="store_true")
    parser.add_argument("--no-workspace-discovery", action="store_true")
    parser.add_argument("--debug-state-tool", action="store_true")
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        model: Any = args.model
        if args.base_url:
            model = build_model_from_config(
                FunctionalHarnessConfig(
                    model_name=args.model,
                    base_url=args.base_url,
                    api_key=args.api_key,
                    env_file=Path(args.env_file).resolve(strict=False) if args.env_file else None,
                )
            )
        return run_console_harness(
            model=model,
            root_dir=args.root_dir,
            prompt=args.prompt,
            include_workspace_discovery=not args.no_workspace_discovery,
            include_debug_state=args.debug_state_tool,
            load_env=not args.no_env,
            env_file=args.env_file,
            env_override=args.env_override,
            stream=not args.no_stream,
        )
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _env_candidates(*, root_dir: str | Path, env_file: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        resolved = candidate.resolve(strict=False)
        if resolved not in seen:
            candidates.append(resolved)
            seen.add(resolved)

    if env_file is not None:
        add(Path(env_file))
        return candidates

    cwd = Path.cwd()
    root_path = Path(root_dir).resolve(strict=False)
    package_project_root = Path(__file__).resolve().parents[2]
    add(cwd / ".env")
    add(root_path / ".env")
    add(root_path / "python" / ".env")
    add(package_project_root / ".env")
    return candidates


def _looks_like_missing_openai_dependency(error: ImportError, model: Any) -> bool:
    if not isinstance(model, str):
        return False
    if not model.startswith("openai:"):
        return False
    message = str(error)
    return "openai" in message and "install" in message.lower()


def _build_single_operation(*, kind: str, start: str, end: str, content: str) -> dict[str, str]:
    operation: dict[str, str] = {"kind": kind}
    if kind == "replace_range":
        _require_non_empty(start=start, end=end, content=content)
        operation["start"] = start
        operation["end"] = end
        operation["content"] = content
        return operation
    if kind == "insert_after":
        _require_non_empty(start=start, content=content)
        operation["start"] = start
        operation["content"] = content
        return operation
    if kind == "delete_range":
        _require_non_empty(start=start, end=end)
        operation["start"] = start
        operation["end"] = end
        return operation
    if kind == "insert_at_start":
        _require_non_empty(content=content)
        operation["content"] = content
        return operation
    raise ValueError(f"unsupported edit kind: {kind}")


def _normalize_anchor(value: str) -> str:
    if not value:
        return value
    prefix, _, _ = value.partition("|")
    return _strip_anchor_wrappers(prefix.strip())


def _strip_anchor_wrappers(value: str) -> str:
    if len(value) >= 2 and value.startswith("{") and value.endswith("}"):
        return value[1:-1].strip()
    return value


def _require_non_empty(**values: str) -> None:
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"missing required edit argument(s): {', '.join(sorted(missing))}")


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _require_agno() -> None:
    try:
        import agno  # noqa: F401
    except ImportError as error:
        raise RuntimeError(AGNO_IMPORT_ERROR_MESSAGE) from error


if __name__ == "__main__":
    raise SystemExit(main())
