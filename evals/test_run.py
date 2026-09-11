from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parent
RUNNER = EVAL_DIR / "run.py"
CASES = ["slug", "summary", "investigate-config", "investigate-cache", "export", "report"]

if __package__:
    from .solutions import CACHE_ANSWER, CONFIG_ANSWER, SOLUTIONS
else:
    from solutions import CACHE_ANSWER, CONFIG_ANSWER, SOLUTIONS


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.rules = self.root / "rules"
        (self.rules / ".codex").mkdir(parents=True)
        (self.rules / ".agents" / "skills" / "sample").mkdir(parents=True)
        (self.rules / "AGENTS.md").write_text("# Test rules\n", encoding="utf-8")
        (self.rules / ".codex" / "config.toml").write_text("profile = 'test'\n", encoding="utf-8")
        (self.rules / ".agents" / "skills" / "sample" / "SKILL.md").write_text(
            "---\nname: sample\ndescription: test\n---\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments: object, expected_code: int | None = None):
        completed = subprocess.run(
            [sys.executable, str(RUNNER), *(str(argument) for argument in arguments)],
            cwd=EVAL_DIR.parent,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if expected_code is not None:
            self.assertEqual(completed.returncode, expected_code, completed.stderr + completed.stdout)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            self.fail(f"CLI did not return JSON: stdout={completed.stdout!r}, stderr={completed.stderr!r}")
        return completed, payload

    def prepare_all(self) -> Path:
        output = self.root / "workspaces"
        _, payload = self.run_cli("prepare", "all", "--output", output, "--rules", self.rules, expected_code=0)
        self.assertTrue(payload["pass"])
        return output

    def test_list_reports_six_fixed_cases(self):
        _, payload = self.run_cli("list", expected_code=0)
        self.assertEqual([case["name"] for case in payload["cases"]], CASES)
        self.assertTrue(payload["pass"])

    def test_prepare_rejects_existing_output_and_writes_reproducible_manifest(self):
        output = self.root / "slug-workspace"
        _, payload = self.run_cli("prepare", "slug", "--output", output, "--rules", self.rules, expected_code=0)
        self.assertTrue(payload["pass"])
        manifest = json.loads((output / "EVAL_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["case"], "slug")
        indexed = {entry["path"]: entry["sha256"] for entry in manifest["bundle"] + manifest["rules"]}
        for relative, digest in indexed.items():
            self.assertEqual(hashlib.sha256((output / relative).read_bytes()).hexdigest(), digest)
        marker = output / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        _, failed = self.run_cli("prepare", "slug", "--output", output, "--rules", self.rules, expected_code=1)
        self.assertFalse(failed["pass"])
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_prepare_uses_repository_rules_by_default(self):
        output = self.root / "default-rules"
        _, payload = self.run_cli("prepare", "slug", "--output", output, expected_code=0)
        self.assertTrue(payload["pass"])
        repository_root = EVAL_DIR.parent
        self.assertEqual(
            (output / "AGENTS.md").read_bytes(),
            (repository_root / "AGENTS.md").read_bytes(),
        )
        self.assertEqual(
            (output / ".codex" / "config.toml").read_bytes(),
            (repository_root / ".codex" / "config.toml").read_bytes(),
        )
        self.assertTrue((output / ".agents" / "skills" / "codex-orchestrator" / "SKILL.md").is_file())

    def test_export_task_preserves_literal_newline_notation(self):
        output = self.root / "export"
        self.run_cli("prepare", "export", "--output", output, "--rules", self.rules, expected_code=0)
        task = (output / "TASK.md").read_text(encoding="utf-8")
        self.assertIn("`\\n` as the record terminator", task)

    def test_all_six_starters_fail_their_checks(self):
        output = self.prepare_all()
        _, payload = self.run_cli("check", "all", "--workspace", output, expected_code=1)
        self.assertFalse(payload["pass"])
        self.assertEqual([result["case"] for result in payload["results"]], CASES)
        self.assertTrue(all(not result["pass"] for result in payload["results"]))

    def test_reference_solutions_pass_all_checks(self):
        output = self.prepare_all()
        for relative, content in SOLUTIONS.items():
            case = self._case_for_solution(relative)
            (output / case / relative).write_text(content, encoding="utf-8", newline="\n")
        (output / "investigate-config" / "answers.json").write_text(
            json.dumps(CONFIG_ANSWER), encoding="utf-8"
        )
        (output / "investigate-cache" / "answers.json").write_text(
            json.dumps(CACHE_ANSWER), encoding="utf-8"
        )
        _, payload = self.run_cli("check", "all", "--workspace", output, expected_code=0)
        self.assertTrue(payload["pass"], payload["errors"])
        self.assertTrue(all(result["pass"] for result in payload["results"]))

    def test_workspace_checker_cannot_override_external_check(self):
        workspace = self.root / "slug"
        self.run_cli("prepare", "slug", "--output", workspace, "--rules", self.rules, expected_code=0)
        fake = workspace / "evals" / "run.py"
        fake.parent.mkdir(parents=True)
        fake.write_text('print("{\\"pass\\": true, \\"errors\\": []}")\n', encoding="utf-8")
        _, payload = self.run_cli("check", "slug", "--workspace", workspace, expected_code=1)
        self.assertFalse(payload["pass"])

    def test_report_accepts_module_import_and_rejects_duplicate_implementation(self):
        workspace = self.root / "report"
        self.run_cli("prepare", "report", "--output", workspace, "--rules", self.rules, expected_code=0)
        for relative in ("src/report/stats.py", "src/report/markdown.py"):
            (workspace / relative).write_text(SOLUTIONS[relative], encoding="utf-8", newline="\n")
        renderer = workspace / "src/report/markdown.py"
        module_import = SOLUTIONS["src/report/markdown.py"].replace(
            "from .stats import latest_events", "from . import stats"
        ).replace("rows = latest_events(events)", "rows = stats.latest_events(events)")
        renderer.write_text(module_import, encoding="utf-8", newline="\n")
        self.run_cli("check", "report", "--workspace", workspace, expected_code=0)
        duplicate = SOLUTIONS["src/report/markdown.py"].replace(
            "from .stats import latest_events", SOLUTIONS["src/report/stats.py"]
        )
        renderer.write_text(duplicate, encoding="utf-8", newline="\n")
        _, payload = self.run_cli("check", "report", "--workspace", workspace, expected_code=1)
        self.assertIn("must call latest_events", payload["errors"][0])

    def test_malformed_manifest_returns_json_failure(self):
        workspace = self.root / "slug"
        self.run_cli("prepare", "slug", "--output", workspace, "--rules", self.rules, expected_code=0)
        (workspace / "EVAL_MANIFEST.json").write_text("[]\n", encoding="utf-8")
        completed, payload = self.run_cli("check", "slug", "--workspace", workspace, expected_code=1)
        self.assertEqual(completed.stderr, "")
        self.assertFalse(payload["pass"])
        self.assertIn("must contain a JSON object", payload["errors"][0])

    def test_investigation_source_changes_are_rejected(self):
        workspace = self.root / "config"
        self.run_cli(
            "prepare", "investigate-config", "--output", workspace, "--rules", self.rules, expected_code=0
        )
        (workspace / "answers.json").write_text(json.dumps(CONFIG_ANSWER), encoding="utf-8")
        source = workspace / "src" / "config" / "merge.py"
        source.write_text(source.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        _, payload = self.run_cli("check", "investigate-config", "--workspace", workspace, expected_code=1)
        self.assertTrue(any("source was changed" in error for error in payload["errors"]))

    @staticmethod
    def _case_for_solution(relative: str) -> str:
        if relative == "src/slug.py":
            return "slug"
        if relative == "src/order_summary.py":
            return "summary"
        if relative.startswith("src/export/"):
            return "export"
        if relative.startswith("src/report/"):
            return "report"
        raise AssertionError(relative)


if __name__ == "__main__":
    unittest.main()
