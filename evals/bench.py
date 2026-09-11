"""Thin launcher for Harbor; execution, isolation and trajectories belong to Harbor."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path

HARBOR_VERSION = "0.22.0"
CODEX_VERSION = "0.149.1"


def _toml(data: dict, prefix: tuple[str, ...] = ()) -> str:
    """Render config scalars/tables without an extra host Python dependency."""
    lines = ["[" + ".".join(json.dumps(k) for k in prefix) + "]"] if prefix else []
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f"{json.dumps(key)} = {json.dumps(value, ensure_ascii=True)}")
    for key, value in data.items():
        if isinstance(value, dict):
            lines.extend(["", _toml(value, (*prefix, key))])
    return "\n".join(lines) + "\n"


def _codex_config(rules_root: Path, process_env: dict[str, str]) -> dict:
    home = Path(process_env.get("CODEX_HOME", str(Path.home() / ".codex")))
    global_path = home / "config.toml"
    global_config = tomllib.loads(global_path.read_text(encoding="utf-8")) if global_path.exists() else {}
    config = tomllib.loads((rules_root / ".codex/config.toml").read_text(encoding="utf-8"))
    # Carry only the selected connection, never host MCP commands or projects.
    provider = config.get("model_provider", global_config.get("model_provider"))
    if provider:
        config["model_provider"] = provider
        if provider not in config.get("model_providers", {}):
            definition = global_config.get("model_providers", {}).get(provider)
            if definition:
                config.setdefault("model_providers", {})[provider] = definition
    if "openai_base_url" in global_config and "openai_base_url" not in config:
        config["openai_base_url"] = global_config["openai_base_url"]
    config.setdefault("projects", {})["/app"] = {"trust_level": "trusted"}
    if not process_env.get("OPENAI_API_KEY") and not process_env.get("CODEX_AUTH_JSON_PATH"):
        auth = home / "auth.json"
        if auth.is_file():
            process_env["CODEX_AUTH_JSON_PATH"] = str(auth)
    return config


def _read_trials(job_dir: Path, expected_count: int, expected_reward: int) -> tuple[list[dict], list[str]]:
    trials, errors = [], []
    for path in sorted(job_dir.glob("*/result.json")):
        trial = json.loads(path.read_text(encoding="utf-8"))
        reward = ((trial.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        exception = trial.get("exception_info")
        passed = exception is None and reward == expected_reward
        trials.append({"case": trial["task_name"], "pass": passed, "reward": reward,
                       "result": str(path), "usage": trial.get("agent_result")})
        if not passed:
            detail = exception["exception_type"] if exception else f"reward={reward}, expected={expected_reward}"
            errors.append(f"{trial['task_name']}: {detail}")
    if len(trials) != expected_count:
        errors.append(f"Expected {expected_count} completed trials, found {len(trials)}")
    return trials, errors


def bench(case_name: str, output: Path | None, rules_root: Path, timeout: int,
          repository_root: Path, *, self_test: bool = False, attempts: int = 1,
          model: str | None = None) -> dict:
    from harbor_tasks import export_tasks
    from run import CASES

    if timeout < 1 or attempts < 1:
        raise ValueError("timeout and attempts must be positive")
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("Install uv first: https://docs.astral.sh/uv/getting-started/installation/")
    docker = shutil.which("docker")
    if not docker:
        raise ValueError("Install and start Docker Desktop with Linux containers first")
    probe = subprocess.run([docker, "info", "--format", "{{.OSType}}"], capture_output=True, text=True, timeout=30)
    if probe.returncode or probe.stdout.strip() != "linux":
        raise ValueError("Docker Linux engine is unavailable. Start Docker Desktop, then rerun the same command.")
    output = (output or repository_root / "work/evals" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")).resolve()
    output.mkdir(parents=True, exist_ok=False)
    dataset = export_tasks(case_name, output / "tasks", rules_root, timeout)
    count = len(CASES) if case_name == "all" else 1
    payload = {"pass": False, "framework": f"harbor=={HARBOR_VERSION}", "output": str(output),
               "self_test": self_test, "results": [], "errors": []}
    process_env = os.environ.copy()
    process_env["PYTHONIOENCODING"] = "utf-8"
    process_env["PYTHONUTF8"] = "1"
    process_env["PYTHONUNBUFFERED"] = "1"
    try:
        # Only the temporary path enters the persisted Harbor job config.
        # Native configuration may contain credentials; Harbor uploads it privately.
        with tempfile.TemporaryDirectory(prefix="orchestrator-harbor-") as temporary:
            native_config = Path(temporary) / "config.toml"
            if not self_test:
                config = _codex_config(rules_root, process_env)
                native_config.write_text(_toml(config), encoding="utf-8")
                model = model or config.get("model")
                if not model:
                    raise ValueError("Set model in .codex/config.toml or pass --model")
            for agent in (["oracle", "nop"] if self_test else ["codex"]):
                command = [uv, "tool", "run", "--from", f"harbor=={HARBOR_VERSION}", "harbor", "run",
                           "-p", str(dataset), "-a", agent, "--env", "docker", "-n", "1", "-k", str(attempts),
                           "--max-retries", "0", "--jobs-dir", str(output / "jobs"), "--job-name", agent]
                if agent == "codex":
                    command += ["-m", model, "--ak", f"version={CODEX_VERSION}", "--ak", f"config={native_config}"]
                print(f"Harbor: {agent}, {count} cases x {attempts} attempts", flush=True)
                completed = subprocess.run(command, env=process_env, check=False)
                trials, errors = _read_trials(output / "jobs" / agent, count * attempts, 0 if agent == "nop" else 1)
                payload["results"].append({"agent": agent, "trials": trials})
                payload["errors"].extend(errors)
                if completed.returncode:
                    payload["errors"].append(f"Harbor {agent} exited with code {completed.returncode}")
                if errors or completed.returncode:
                    break
        payload["pass"] = not payload["errors"]
    except KeyboardInterrupt:
        payload["interrupted"] = True
        payload["errors"].append("Interrupted; completed Harbor trial logs remain in jobs/")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        payload["errors"].append(str(error))
    finally:
        (output / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        from report import write_report

        write_report(output)
        print(f"summary: {output / 'summary.md'}", flush=True)
    return payload
