from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from helpers import line_prefixes
from harness import (
    DEFAULT_AGENT_INSTRUCTIONS,
    ScopedLinehashToolAdapter,
    create_agno_demo_agent,
    create_agno_demo_tools,
)


class FakeWorkspace:
    def __init__(self, root: str, allowed=None, confirm=None, **kwargs) -> None:
        self.root = root
        self.allowed = allowed
        self.confirm = confirm
        self.kwargs = kwargs


class FakeAgent:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class AgnoHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root_dir = Path(self.temp_dir.name)
        self.file_path = self.root_dir / "sample.txt"
        self.file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    def test_scoped_adapter_reads_edits_and_exposes_state(self) -> None:
        adapter = ScopedLinehashToolAdapter(self.root_dir)

        read_text = adapter.read("sample.txt", offset=0, limit=3)
        beta_anchor = line_prefixes(read_text)[1]

        edit_result = adapter.edit(
            path="sample.txt",
            kind="replace_range",
            start=beta_anchor,
            end=beta_anchor,
            content="BETA",
        )
        state_result = adapter.show_state("sample.txt")

        self.assertIn("text", edit_result)
        self.assertEqual(
            self.file_path.read_text(encoding="utf-8").splitlines(),
            ["alpha", "BETA", "gamma"],
        )
        self.assertEqual(state_result["display_path"], "sample.txt")
        self.assertTrue(any(atom["type"] == "file_line" for atom in state_result["atoms"]))

    def test_scoped_adapter_rejects_paths_outside_root(self) -> None:
        adapter = ScopedLinehashToolAdapter(self.root_dir)

        read_result = adapter.read("../outside.txt")
        edit_result = adapter.edit(path="../outside.txt", kind="insert_at_start", content="x")
        state_result = adapter.show_state("../outside.txt")

        self.assertIn("path escapes harness root", read_result)
        self.assertEqual(edit_result["type"], "UNEXPECTED_ERROR")
        self.assertIn("path escapes harness root", edit_result["reason"])
        self.assertEqual(state_result["type"], "UNEXPECTED_ERROR")
        self.assertIn("path escapes harness root", state_result["reason"])

    def test_create_agno_demo_tools_uses_discovery_only_workspace(self) -> None:
        restore_modules = self._install_fake_agno()
        self.addCleanup(restore_modules)

        tools = create_agno_demo_tools(self.root_dir, include_workspace_discovery=True)

        self.assertEqual([tool.__name__ for tool in tools[:-1]], [
            "read",
            "edit",
        ])
        workspace = tools[-1]
        self.assertIsInstance(workspace, FakeWorkspace)
        self.assertEqual(workspace.allowed, ["list", "search"])
        self.assertIsNone(workspace.confirm)

    def test_create_agno_demo_agent_builds_agent_with_default_instructions(self) -> None:
        restore_modules = self._install_fake_agno()
        self.addCleanup(restore_modules)

        agent = create_agno_demo_agent(
            model="openai:gpt-5.4",
            root_dir=self.root_dir,
            extra_instructions=["Do not summarize tool schemas."],
        )

        self.assertIsInstance(agent, FakeAgent)
        self.assertEqual(agent.kwargs["model"], "openai:gpt-5.4")
        self.assertEqual(agent.kwargs["name"], "Smaller Edits Demo Agent")
        self.assertTrue(agent.kwargs["markdown"])
        self.assertEqual(agent.kwargs["instructions"][: len(DEFAULT_AGENT_INSTRUCTIONS)], DEFAULT_AGENT_INSTRUCTIONS)
        self.assertIn("Do not summarize tool schemas.", agent.kwargs["instructions"])
        self.assertEqual(len(agent.kwargs["tools"]), 2)

    def test_create_agno_demo_agent_rejects_explicit_tools_override(self) -> None:
        restore_modules = self._install_fake_agno()
        self.addCleanup(restore_modules)

        with self.assertRaisesRegex(ValueError, "manages tools itself"):
            create_agno_demo_agent(
                model="openai:gpt-5.4",
                root_dir=self.root_dir,
                tools=[],
            )

    def _install_fake_agno(self):
        previous = {name: sys.modules.get(name) for name in ["agno", "agno.agent", "agno.tools", "agno.tools.workspace"]}

        agno_module = types.ModuleType("agno")
        agent_module = types.ModuleType("agno.agent")
        tools_module = types.ModuleType("agno.tools")
        workspace_module = types.ModuleType("agno.tools.workspace")

        agent_module.Agent = FakeAgent
        workspace_module.Workspace = FakeWorkspace
        agno_module.agent = agent_module
        agno_module.tools = tools_module
        tools_module.workspace = workspace_module

        sys.modules["agno"] = agno_module
        sys.modules["agno.agent"] = agent_module
        sys.modules["agno.tools"] = tools_module
        sys.modules["agno.tools.workspace"] = workspace_module

        def restore() -> None:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

        return restore


if __name__ == "__main__":
    unittest.main()
