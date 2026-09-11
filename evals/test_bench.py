from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from pathlib import Path

import bench
from test_run import CACHE_ANSWER, CONFIG_ANSWER, SOLUTIONS


EVAL_DIR = Path(__file__).resolve().parent
REPOSITORY = EVAL_DIR.parent
RUNNER = EVAL_DIR / "run.py"
CASES = ["slug", "summary", "investigate-config", "investigate-cache", "export", "report"]


class BenchTests(unittest.TestCase):
    def setUp(self):
        (REPOSITORY / "work").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=REPOSITORY / "work")
        self.root = Path(self.temporary.name)
        self.rules = self.root / "rules"
        (self.rules / ".codex").mkdir(parents=True)
        (self.rules / ".agents" / "skills" / "codex-orchestrator").mkdir(parents=True)
        (self.rules / "AGENTS.md").write_text("# Test rules\n", encoding="utf-8")
        (self.rules / ".codex" / "config.toml").write_text(
            'model = "fake"\n', encoding="utf-8"
        )
        (self.rules / ".agents" / "skills" / "codex-orchestrator" / "SKILL.md").write_text(
            "---\nname: codex-orchestrator\ndescription: fake\n---\n",
            encoding="utf-8",
        )
        self.fake_cli = self.root / "fake_codex.py"
        self.fake_cli.write_text(self._fake_cli_source(), encoding="utf-8", newline="\n")

    def tearDown(self):
        self.temporary.cleanup()

    def test_npm_cmd_on_path_resolves_without_native_codex(self):
        npm = self.root / "npm installation with spaces"
        entry = npm / "node_modules/@openai/codex/bin/codex.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("// package entry", encoding="utf-8")
        shim = npm / "codex.cmd"
        shim.write_text("@echo off", encoding="utf-8")
        node = npm / "node.exe"
        node.write_bytes(b"")
        with patch.dict(os.environ, {"PATH": str(npm)}), patch(
            "bench.shutil.which", return_value=str(shim)
        ):
            self.assertEqual(bench._resolve_cli(None), [str(node), str(entry)])

    def test_explicit_npm_shim_uses_node_from_path(self):
        npm = self.root / "npm"
        entry = npm / "node_modules/@openai/codex/bin/codex.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("// package entry", encoding="utf-8")
        for suffix in (".cmd", ".ps1"):
            shim = npm / ("codex" + suffix)
            shim.write_text("shim", encoding="utf-8")
            with patch("bench.shutil.which", return_value=sys.executable):
                self.assertEqual(bench._resolve_cli(str(shim)), [sys.executable, str(entry)])

    def test_unrecognized_shim_is_rejected(self):
        shim = self.root / "unknown.cmd"
        shim.write_text("unrecognized command", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Codex npm entry"):
            bench._resolve_cli(str(shim))

    def run_bench(
        self,
        output_name: str,
        *arguments: str,
        environment: dict[str, str] | None = None,
        expected_code: int | None = None,
        timeout: int = 30,
    ):
        output = self.root / output_name
        command = [
            sys.executable,
            str(RUNNER),
            "bench",
            "--output",
            str(output),
            "--rules",
            str(self.rules),
            "--codex",
            str(self.fake_cli),
            *arguments,
        ]
        process_environment = os.environ.copy()
        if environment:
            process_environment.update(environment)
        completed = subprocess.run(
            command,
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=process_environment,
            check=False,
        )
        if expected_code is not None:
            self.assertEqual(completed.returncode, expected_code, completed.stderr + completed.stdout)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            self.fail(f"bench did not return JSON: {completed.stdout!r}; stderr={completed.stderr!r}")
        return output, completed, payload

    def test_success_writes_artifacts_and_usage(self):
        output, completed, payload = self.run_bench(
            "success", "--case", "slug", expected_code=0
        )
        self.assertTrue(payload["pass"])
        self.assertIn("[1/1] slug: passed", completed.stderr)
        self.assertIn(str(output / "summary.md"), completed.stderr)
        result = payload["results"][0]
        self.assertEqual(
            result["usage"],
            {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20},
        )
        self.assertTrue(result["completed_event"])
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertEqual(result["config_overrides"], [])
        self.assertIn("fake-codex 1.0", result["cli"]["version"])
        self.assertEqual(json.loads((output / "results.json").read_text(encoding="utf-8")), payload)
        self.assertTrue((output / "summary.md").is_file())
        self.assertTrue((output / "logs" / "slug" / "events.jsonl").is_file())
        self.assertTrue((output / "logs" / "slug" / "stderr.log").is_file())
        self.assertTrue((output / "logs" / "slug" / "final.txt").is_file())
        self.assertFalse((output / "workspaces" / "slug" / "logs").exists())
        argv = result["argv"]
        self.assertEqual(argv[2:5], ["-a", "never", "exec"])
        self.assertIn("--json", argv)
        self.assertIn("--skip-git-repo-check", argv)

    def test_nonzero_case_fails_and_later_cases_continue(self):
        output, _, payload = self.run_bench(
            "continue",
            environment={"FAKE_CODEX_FAIL_CASE": "summary"},
            expected_code=1,
        )
        self.assertFalse(payload["pass"])
        self.assertEqual([result["case"] for result in payload["results"]], CASES)
        failed = payload["results"][1]
        self.assertEqual(failed["returncode"], 7)
        self.assertFalse(failed["pass"])
        self.assertTrue(failed["validation"]["pass"])
        self.assertTrue(payload["results"][-1]["pass"])
        checkpoint = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(len(checkpoint["results"]), 6)

    def test_missing_cli_reports_failure_without_running_cases(self):
        output = self.root / "missing"
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "bench",
                "--case",
                "slug",
                "--output",
                str(output),
                "--rules",
                str(self.rules),
                "--codex",
                str(self.root / "does-not-exist.exe"),
            ],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["pass"])
        self.assertIn("was not found", payload["errors"][0])
        checkpoint = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["results"], [])
        self.assertIn("was not found", (output / "summary.md").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["errors"], payload["errors"])
        self.assertEqual(checkpoint["output"], str(output.resolve()))
        self.assertIn(str(output / "summary.md"), completed.stderr)

    def test_version_failure_is_checkpointed(self):
        output, _, payload = self.run_bench(
            "version-failure",
            "--case",
            "slug",
            environment={"FAKE_CODEX_VERSION_FAIL": "1"},
            expected_code=1,
        )
        self.assertTrue(any("version check failed" in error for error in payload["errors"]))
        checkpoint = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["errors"], payload["errors"])

    def test_timeout_fails_and_preserves_checkpoint(self):
        output, _, payload = self.run_bench(
            "timeout",
            "--timeout",
            "1",
            environment={"FAKE_CODEX_SLEEP_CASE": "slug"},
            expected_code=1,
        )
        self.assertEqual(payload["results"][0]["status"], "timeout")
        self.assertEqual(len(payload["results"]), len(CASES))
        self.assertTrue(payload["results"][-1]["pass"])
        self.assertTrue(any("timeout" in error for error in payload["errors"]))
        checkpoint = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["results"][0]["status"], "timeout")

    def test_invalid_json_and_missing_completion_event_fail(self):
        _, _, invalid = self.run_bench(
            "invalid-json",
            "--case",
            "slug",
            environment={"FAKE_CODEX_INVALID_CASE": "slug"},
            expected_code=1,
        )
        self.assertTrue(any("invalid JSON event" in error for error in invalid["errors"]))
        _, _, incomplete = self.run_bench(
            "no-completion",
            "--case",
            "slug",
            environment={"FAKE_CODEX_NO_COMPLETE_CASE": "slug"},
            expected_code=1,
        )
        self.assertTrue(any("turn.completed" in error for error in incomplete["errors"]))

    def test_failure_event_and_invalid_utf8_fail_without_crashing(self):
        _, _, failed_event = self.run_bench(
            "failed-event",
            "--case",
            "slug",
            environment={"FAKE_CODEX_ERROR_EVENT_CASE": "slug"},
            expected_code=1,
        )
        self.assertTrue(any("turn.failed" in error for error in failed_event["errors"]))
        _, _, bad_utf8 = self.run_bench(
            "bad-utf8",
            "--case",
            "slug",
            environment={"FAKE_CODEX_BAD_UTF8_CASE": "slug"},
            expected_code=1,
        )
        self.assertTrue(any("not valid UTF-8" in error for error in bad_utf8["errors"]))

    def test_output_outside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "bench",
                    "--case",
                    "slug",
                    "--output",
                    str(Path(outside) / "result"),
                    "--rules",
                    str(self.rules),
                    "--codex",
                    str(self.fake_cli),
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertIn("trusted repository", payload["errors"][0])

    @staticmethod
    def _fake_cli_source() -> str:
        source = f'''\
import json
import os
import sys
import time
from pathlib import Path

SOLUTIONS = {SOLUTIONS!r}
CONFIG_ANSWER = {CONFIG_ANSWER!r}
CACHE_ANSWER = {CACHE_ANSWER!r}

if "--version" in sys.argv:
    if os.environ.get("FAKE_CODEX_VERSION_FAIL"):
        print("simulated version failure", file=sys.stderr)
        raise SystemExit(4)
    print("fake-codex 1.0")
    raise SystemExit(0)

arguments = sys.argv[1:]
workspace = Path(arguments[arguments.index("-C") + 1])
final_path = Path(arguments[arguments.index("-o") + 1])
case = workspace.name
prompt = sys.stdin.buffer.read().decode("utf-8")
if "当前案例目录中的 $codex-orchestrator" not in prompt:
    print("unexpected prompt", file=sys.stderr)
    raise SystemExit(9)

if os.environ.get("FAKE_CODEX_SLEEP_CASE") == case:
    time.sleep(5)

destinations = {{
    "slug": ["src/slug.py"],
    "summary": ["src/order_summary.py"],
    "export": ["src/export/csv_export.py", "src/export/json_export.py"],
    "report": ["src/report/stats.py", "src/report/markdown.py"],
}}
for relative in destinations.get(case, []):
    (workspace / relative).write_text(SOLUTIONS[relative], encoding="utf-8", newline="\\n")
if case == "investigate-config":
    (workspace / "answers.json").write_text(json.dumps(CONFIG_ANSWER), encoding="utf-8")
if case == "investigate-cache":
    (workspace / "answers.json").write_text(json.dumps(CACHE_ANSWER), encoding="utf-8")

final_path.write_text("done\\n", encoding="utf-8")
print(json.dumps({{"type": "thread.started"}}), flush=True)
if os.environ.get("FAKE_CODEX_INVALID_CASE") == case:
    print("{{not-json", flush=True)
if os.environ.get("FAKE_CODEX_ERROR_EVENT_CASE") == case:
    print(json.dumps({{"type": "turn.failed", "error": "simulated failure"}}), flush=True)
if os.environ.get("FAKE_CODEX_BAD_UTF8_CASE") == case:
    sys.stdout.flush()
    sys.stdout.buffer.write(b"\\xff\\n")
    sys.stdout.buffer.flush()
if os.environ.get("FAKE_CODEX_NO_COMPLETE_CASE") != case:
    print(json.dumps({{
        "type": "turn.completed",
        "usage": {{"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20}},
    }}), flush=True)
if os.environ.get("FAKE_CODEX_FAIL_CASE") == case:
    raise SystemExit(7)
'''
        return textwrap.dedent(source)


if __name__ == "__main__":
    unittest.main()
