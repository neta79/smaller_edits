from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from harness import build_model_from_config, create_agno_demo_agent, load_functional_config


class HarnessFunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.vector_root = cls.repo_root / "test" / "vectors"
        cls.fixture_root = cls.repo_root / "test" / "fixtures"
        cls.enabled = os.getenv("LINEHASH_RUN_FUNCTIONAL") == "1"
        cls.verbose = os.getenv("LINEHASH_TEST_VERBOSE", "0") == "1"
        cls.show_full_reasoning = os.getenv("LINEHASH_TEST_SHOW_FULL_REASONING", "0") == "1"
        cls.config = load_functional_config()

    def test_selected_vectors(self) -> None:
        if not self.enabled:
            self.skipTest("Set LINEHASH_RUN_FUNCTIONAL=1 to run live harness functional tests")

        vector_file = self.config.vector_file or (self.vector_root / "harness-vectors.json")
        cases = json.loads(vector_file.read_text(encoding="utf-8"))
        selected_names = self.config.vector_names or tuple(cases.keys())
        model = build_model_from_config(self.config)

        for name in selected_names:
            case = cases[name]
            with self.subTest(vector=name):
                if self.verbose:
                    print(f"\n=== VECTOR {name} ===", flush=True)
                    print(f"fixture: {case['fixture']}", flush=True)
                    print(f"prompt: {case['prompt']}", flush=True)
                final_text, response = self._run_case(case=case, model=model)
                self.assertEqual(final_text, case["final_file"])
                self.assertIsNotNone(response.content)

    def _run_case(self, *, case: dict, model):
        fixture_name = case["fixture"]
        temp_dir = Path(tempfile.mkdtemp(prefix="linehash-functional-"))
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        shutil.copy2(self.fixture_root / fixture_name, temp_dir / fixture_name)

        agent = create_agno_demo_agent(
            model=model,
            root_dir=temp_dir,
            include_workspace_discovery=self.config.include_workspace_discovery,
            include_debug_state=self.config.include_debug_state,
            load_env=True,
            env_file=self.config.env_file,
        )
        response = agent.run(case["prompt"], stream=False, debug_mode=self.verbose)
        if self.verbose:
            print(f"workspace: {temp_dir}", flush=True)
            self._print_plain_run_output(response)
        final_text = (temp_dir / fixture_name).read_text(encoding="utf-8")
        return final_text, response

    def _print_plain_run_output(self, response) -> None:
        print(f"run_id: {response.run_id}", flush=True)
        print(f"session_id: {response.session_id}", flush=True)
        if response.reasoning_content and self.show_full_reasoning:
            print("--- reasoning ---", flush=True)
            print(response.reasoning_content, flush=True)
        if response.tools:
            print("--- tool calls ---", flush=True)
            for tool in response.tools:
                name = getattr(tool, "tool_name", None) or getattr(tool, "name", "<unknown>")
                args = getattr(tool, "tool_args", None) or getattr(tool, "arguments", None)
                result = getattr(tool, "result", None)
                print(f"tool: {name}", flush=True)
                if args is not None:
                    print(f"args: {args}", flush=True)
                if result is not None:
                    print(f"result: {result}", flush=True)
        print("--- final response ---", flush=True)
        print(response.content, flush=True)


if __name__ == "__main__":
    unittest.main()
