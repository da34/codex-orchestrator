from __future__ import annotations

import ast
import base64
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

if __package__:
    from .harbor_tasks import CASES, export_tasks
else:
    from harbor_tasks import CASES, export_tasks


EVAL_DIR = Path(__file__).resolve().parent


class HarborTaskExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.rules = self.root / "rules"
        (self.rules / ".codex").mkdir(parents=True)
        (self.rules / ".agents" / "skills" / "sample").mkdir(parents=True)
        (self.rules / "AGENTS.md").write_text("# Test rules\n", encoding="utf-8")
        (self.rules / ".codex" / "config.toml").write_text(
            "profile = 'test'\n", encoding="utf-8"
        )
        (self.rules / ".agents" / "skills" / "sample" / "SKILL.md").write_text(
            "---\nname: sample\ndescription: test\n---\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_exports_standard_harbor_tasks_with_pinned_cached_agent_layer(self):
        dataset = export_tasks("all", self.root / "dataset", self.rules, timeout=123)

        self.assertEqual(
            {path.name for path in dataset.iterdir() if path.is_dir()}, set(CASES)
        )
        for case_name, case in CASES.items():
            task = dataset / case_name
            self.assertEqual(
                {path.name for path in task.iterdir()},
                {"environment", "instruction.md", "solution", "task.toml", "tests"},
            )
            self.assertEqual(
                (task / "instruction.md").read_text(encoding="utf-8"), "使用 $codex-orchestrator，完成 TASK.md 中的任务。\n\n" + case["task"]
            )
            config = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
            self.assertEqual(config["schema_version"], "1.4")
            self.assertEqual(config["task"]["name"], f"orchestrator/{case_name}")
            self.assertEqual(config["task"]["version"], "1.0.0")
            self.assertEqual(config["agent"]["timeout_sec"], 123)
            self.assertEqual(config["verifier"]["timeout_sec"], 123)
            self.assertEqual(config["environment"]["cpus"], 1)
            self.assertEqual(config["environment"]["memory_mb"], 2048)

            dockerfile = (task / "environment" / "Dockerfile").read_text(
                encoding="utf-8"
            )
            self.assertTrue(dockerfile.startswith("FROM python:3.12-slim@sha256:"))
            for dependency in (
                "ca-certificates",
                "curl",
                "git",
                "nodejs",
                "npm",
                "ripgrep",
            ):
                self.assertIn(dependency, dockerfile)
            install = "npm install --global @openai/codex@0.149.1"
            self.assertLess(dockerfile.index(install), dockerfile.index("COPY workspace /app"))
            self.assertIn("WORKDIR /app\nCOPY workspace /app", dockerfile)

    def test_checker_and_solution_are_outside_the_environment_build_context(self):
        dataset = export_tasks("all", self.root / "dataset", self.rules)

        runner = EVAL_DIR / "run.py"
        for case_name in CASES:
            task = dataset / case_name
            environment = task / "environment"
            self.assertEqual(
                {path.name for path in environment.iterdir()}, {"Dockerfile", "workspace"}
            )
            self.assertEqual((task / "tests" / "run.py").read_bytes(), runner.read_bytes())
            self.assertTrue((task / "tests" / "test.sh").is_file())
            self.assertTrue((task / "solution" / "solve.sh").is_file())
            self.assertFalse(any(path.name == "solve.sh" for path in environment.rglob("*")))
            self.assertFalse(any(path.name == "run.py" for path in environment.rglob("*")))

            verifier = (task / "tests" / "test.sh").read_text(encoding="utf-8")
            self.assertIn(
                f"python3 /tests/run.py check {case_name} --workspace /app", verifier
            )
            self.assertIn("/logs/verifier/reward.txt", verifier)
            self.assertIn("checker infrastructure failure", verifier)

    def test_prepare_snapshot_is_exact_and_fresh_for_each_export(self):
        first = export_tasks("slug", self.root / "first", self.rules)
        first_workspace = first / "slug" / "environment" / "workspace"
        self.assertEqual(
            (first_workspace / "AGENTS.md").read_bytes(),
            (self.rules / "AGENTS.md").read_bytes(),
        )
        first_manifest = (first_workspace / "EVAL_MANIFEST.json").read_bytes()
        (first_workspace / "src" / "slug.py").write_text("changed\n", encoding="utf-8")

        second = export_tasks("slug", self.root / "second", self.rules)
        second_workspace = second / "slug" / "environment" / "workspace"
        self.assertEqual(
            (second_workspace / "src" / "slug.py").read_text(encoding="utf-8"),
            CASES["slug"]["files"]["src/slug.py"],
        )
        self.assertEqual(
            (second_workspace / "EVAL_MANIFEST.json").read_bytes(), first_manifest
        )

        marker = second / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "output already exists"):
            export_tasks("slug", second, self.rules)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")

    def test_invalid_request_does_not_create_output(self):
        unknown = self.root / "unknown"
        with self.assertRaisesRegex(ValueError, "unknown case"):
            export_tasks("missing", unknown, self.rules)
        self.assertFalse(unknown.exists())

        invalid_timeout = self.root / "invalid-timeout"
        with self.assertRaisesRegex(ValueError, "positive integer"):
            export_tasks("slug", invalid_timeout, self.rules, timeout=0)
        self.assertFalse(invalid_timeout.exists())

    def test_all_starters_fail_and_generated_oracles_pass(self):
        dataset = export_tasks("all", self.root / "dataset", self.rules)

        for case_name in CASES:
            task = dataset / case_name
            workspace = task / "environment" / "workspace"
            failed = self._run_checker(task, workspace)
            self.assertEqual(failed.returncode, 1, failed.stderr + failed.stdout)
            self.assertFalse(json.loads(failed.stdout)["pass"])

            for relative, content in self._files_from_solve_script(
                task / "solution" / "solve.sh"
            ).items():
                destination = workspace / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8", newline="\n")

            passed = self._run_checker(task, workspace)
            self.assertEqual(passed.returncode, 0, passed.stderr + passed.stdout)
            self.assertTrue(json.loads(passed.stdout)["pass"])

    @staticmethod
    def _run_checker(task: Path, workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(task / "tests" / "run.py"),
                "check",
                task.name,
                "--workspace",
                str(workspace),
            ],
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    @staticmethod
    def _files_from_solve_script(path: Path) -> dict[str, str]:
        script = path.read_text(encoding="utf-8")
        assignment = next(
            line for line in script.splitlines() if line.startswith("files = json.loads(")
        )
        encoded_json = ast.literal_eval(assignment.removeprefix("files = json.loads(")[:-1])
        encoded = json.loads(encoded_json)
        return {
            relative: base64.b64decode(content).decode("utf-8")
            for relative, content in encoded.items()
        }

if __name__ == "__main__":
    unittest.main()
