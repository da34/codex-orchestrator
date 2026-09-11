"""Export the fixed orchestration evaluations as Harbor task directories."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path

if __package__:
    from .run import CASES, prepare
    from .solutions import CACHE_ANSWER, CONFIG_ANSWER, SOLUTIONS
else:
    from run import CASES, prepare
    from solutions import CACHE_ANSWER, CONFIG_ANSWER, SOLUTIONS


_IMPLEMENTATION_SOLUTIONS = {
    "slug": ("src/slug.py",),
    "summary": ("src/order_summary.py",),
    "export": ("src/export/csv_export.py", "src/export/json_export.py"),
    "report": ("src/report/stats.py", "src/report/markdown.py"),
}

_DOCKERFILE = """FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \\
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \\
        ca-certificates \\
        curl \\
        git \\
        nodejs \\
        npm \\
        ripgrep \\
    && npm install --global @openai/codex@0.149.1 \\
    && npm cache clean --force \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY workspace /app
"""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _case_names(case_name: str) -> tuple[str, ...]:
    if case_name == "all":
        return tuple(CASES)
    if case_name not in CASES:
        choices = ", ".join([*CASES, "all"])
        raise ValueError(f"unknown case {case_name!r}; expected one of: {choices}")
    return (case_name,)


def _task_toml(case_name: str, timeout: int) -> str:
    description = json.dumps(CASES[case_name]["summary"], ensure_ascii=False)
    return f'''schema_version = "1.4"

[task]
name = "orchestrator/{case_name}"
version = "1.0.0"
description = {description}

[agent]
timeout_sec = {timeout}

[verifier]
timeout_sec = {timeout}

[environment]
cpus = 1
memory_mb = 2048
'''


def _reference_files(case_name: str) -> dict[str, str]:
    if case_name in _IMPLEMENTATION_SOLUTIONS:
        return {
            relative: SOLUTIONS[relative]
            for relative in _IMPLEMENTATION_SOLUTIONS[case_name]
        }
    answer = CONFIG_ANSWER if case_name == "investigate-config" else CACHE_ANSWER
    return {"answers.json": json.dumps(answer, indent=2, ensure_ascii=False) + "\n"}


def _solve_script(case_name: str) -> str:
    encoded = {
        relative: base64.b64encode(content.encode("utf-8")).decode("ascii")
        for relative, content in _reference_files(case_name).items()
    }
    payload = json.dumps(encoded, sort_keys=True)
    return f'''#!/bin/bash
set -euo pipefail

python3 - <<'PY'
import base64
import json
from pathlib import Path

workspace = Path("/app")
files = json.loads({payload!r})
for relative, encoded in files.items():
    destination = workspace / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(base64.b64decode(encoded))
PY
'''


def _test_script(case_name: str) -> str:
    return f'''#!/bin/bash
set -euo pipefail

result_file="$(mktemp)"
trap 'rm -f "$result_file"' EXIT
checker_status=0
python3 /tests/run.py check {case_name} --workspace /app > "$result_file" || checker_status=$?
cat "$result_file"

reward="$(python3 - "$result_file" "$checker_status" <<'PY'
import json
import sys
from pathlib import Path

result_path = Path(sys.argv[1])
checker_status = int(sys.argv[2])
try:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"checker infrastructure failure: invalid result: {{error}}")

passed = payload.get("pass")
errors = payload.get("errors")
if not isinstance(passed, bool) or not isinstance(errors, list):
    raise SystemExit("checker infrastructure failure: malformed result")
if checker_status != (0 if passed else 1):
    raise SystemExit(
        f"checker infrastructure failure: status {{checker_status}} disagrees with result"
    )
if any(
    isinstance(error, str) and error.startswith("isolated behavior check could not run:")
    for error in errors
):
    raise SystemExit("checker infrastructure failure: " + "; ".join(errors))
print(1 if passed else 0)
PY
)"
printf '%s\n' "$reward" > /logs/verifier/reward.txt
'''


def _write_task(dataset: Path, case_name: str, rules_root: Path, timeout: int) -> None:
    task = dataset / case_name
    environment = task / "environment"
    environment.mkdir(parents=True)
    prepare(case_name, environment / "workspace", rules_root)

    _write_text(task / "instruction.md", "使用 $codex-orchestrator，完成 TASK.md 中的任务。\n\n" + CASES[case_name]["task"])
    _write_text(task / "task.toml", _task_toml(case_name, timeout))
    _write_text(environment / "Dockerfile", _DOCKERFILE)

    solve = task / "solution" / "solve.sh"
    _write_text(solve, _solve_script(case_name))
    solve.chmod(0o755)

    tests = task / "tests"
    tests.mkdir()
    shutil.copy2(Path(__file__).with_name("run.py"), tests / "run.py")
    test_script = tests / "test.sh"
    _write_text(test_script, _test_script(case_name))
    test_script.chmod(0o755)


def export_tasks(
    case_name: str,
    output: Path,
    rules_root: Path,
    timeout: int = 900,
) -> Path:
    """Create a fresh Harbor dataset containing one case or all fixed cases."""

    names = _case_names(case_name)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("timeout must be a positive integer")

    destination = Path(output).resolve()
    if os.path.lexists(destination):
        raise ValueError(f"output already exists: {destination}")
    rules = Path(rules_root).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        for name in names:
            _write_task(staging, name, rules, timeout)
        try:
            destination.mkdir()
        except FileExistsError as error:
            raise ValueError(f"output already exists: {destination}") from error
        for name in names:
            (staging / name).replace(destination / name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return destination
