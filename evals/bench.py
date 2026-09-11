#!/usr/bin/env python3
"""Run prepared evaluation cases through fresh Codex CLI sessions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import run as evaluation


PROMPT = "使用当前案例目录中的 $codex-orchestrator，完成 TASK.md 中的任务。"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _default_output(repository_root: Path) -> Path:
    parent = repository_root / "work" / "evals"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    candidate = parent / stamp
    suffix = 1
    while candidate.exists():
        candidate = parent / f"{stamp}-{suffix}"
        suffix += 1
    return candidate


def _cli_prefix(path: Path) -> list[str]:
    if path.suffix.lower() in (".cmd", ".ps1"):
        entry = path.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        if not entry.is_file():
            raise ValueError(f"Codex npm entry was not found next to the launcher: {entry}")
        local_node = path.parent / "node.exe"
        node = str(local_node) if local_node.is_file() else shutil.which("node")
        if not node:
            raise ValueError("Node.js was not found; it is required by the npm Codex installation")
        return [node, str(entry)]
    if path.suffix.lower() == ".py":
        return [sys.executable, str(path)]
    return [str(path)]


def _resolve_cli(requested: str | None) -> list[str]:
    if requested:
        path = Path(requested).expanduser()
        resolved = path.resolve() if path.exists() else shutil.which(requested)
        if not resolved:
            raise ValueError(f"Codex CLI was not found: {requested}")
        return _cli_prefix(Path(resolved))

    if os.name == "nt":
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue
            candidate = Path(directory) / "codex.exe"
            if candidate.is_file():
                return [str(candidate.resolve())]
    resolved = shutil.which("codex")
    if not resolved:
        raise ValueError("Codex CLI was not found on PATH; use --codex to specify it")
    return _cli_prefix(Path(resolved).resolve())


def _cli_version(prefix: list[str]) -> str:
    try:
        completed = subprocess.run(
            [*prefix, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"Codex CLI version check failed: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"Codex CLI version check failed ({completed.returncode}): {detail}")
    return completed.stdout.strip() or completed.stderr.strip() or "unknown"


def _parse_events(path: Path) -> tuple[dict[str, int | None], bool, list[str]]:
    completion: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        content = path.read_bytes()
    except OSError as error:
        return _empty_usage(), False, [f"could not read CLI events: {error}"]
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as error:
        errors.append(f"CLI events are not valid UTF-8: {error}")
        decoded = content.decode("utf-8", errors="replace")
    lines = decoded.splitlines()
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"invalid JSON event on line {line_number}: {error.msg}")
            continue
        if not isinstance(event, dict):
            errors.append(f"JSON event on line {line_number} is not an object")
            continue
        if event.get("type") == "turn.completed":
            completion = event
        elif event.get("type") in ("turn.failed", "error"):
            detail = event.get("error") or event.get("message") or "no details"
            errors.append(f"CLI emitted {event['type']}: {detail}")
    if completion is None:
        return _empty_usage(), False, [*errors, "CLI did not emit a turn.completed event"]
    usage = completion.get("usage")
    if not isinstance(usage, dict):
        return _empty_usage(), True, errors
    return {
        "input_tokens": _usage_value(usage, "input_tokens"),
        "cached_input_tokens": _usage_value(usage, "cached_input_tokens"),
        "output_tokens": _usage_value(usage, "output_tokens"),
    }, True, errors


def _usage_value(usage: dict[str, Any], name: str) -> int | None:
    value = usage.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _empty_usage() -> dict[str, None]:
    return {"input_tokens": None, "cached_input_tokens": None, "output_tokens": None}


def _summary(payload: dict[str, Any]) -> str:
    lines = [
        "# Codex orchestration evaluation",
        "",
        f"Overall: {'PASS' if payload['pass'] else 'FAIL'}",
        "",
        "| Case | Result | Seconds | CLI exit | Input | Cached input | Output |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in payload["results"]:
        usage = result["usage"]
        cells = [
            result["case"],
            result["status"],
            f"{result['elapsed_seconds']:.2f}",
            _display(result["returncode"]),
            _display(usage["input_tokens"]),
            _display(usage["cached_input_tokens"]),
            _display(usage["output_tokens"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            "Token counts are reported by the Codex CLI turn.completed event;",
            "their scope is determined by that CLI and is not assumed to include subagents.",
            "",
        ]
    )
    if payload["errors"]:
        lines.extend(["## Failures", ""])
        for error in payload["errors"]:
            lines.extend(["```text", str(error).replace("```", "'''"), "```", ""])
    if payload["results"]:
        lines.extend(["## Run logs", ""])
        for result in payload["results"]:
            name = result["case"]
            lines.append(
                f"- {name}: [final response](logs/{name}/final.txt), "
                f"[CLI diagnostics](logs/{name}/stderr.log), "
                f"[events](logs/{name}/events.jsonl)"
            )
        lines.append("")
    return "\n".join(lines)


def _display(value: Any) -> str:
    return "—" if value is None else str(value)


def _checkpoint(payload: dict[str, Any], output: Path) -> None:
    _write_json_atomic(output / "results.json", payload)
    (output / "summary.md").write_text(
        _summary(payload), encoding="utf-8", newline="\n"
    )


def _run_case(
    case_name: str,
    workspace: Path,
    logs: Path,
    cli_prefix: list[str],
    version: str,
    timeout: int,
) -> tuple[dict[str, Any], bool]:
    case_logs = logs / case_name
    case_logs.mkdir(parents=True, exist_ok=False)
    events_path = case_logs / "events.jsonl"
    stderr_path = case_logs / "stderr.log"
    final_path = case_logs / "final.txt"
    argv = [
        *cli_prefix,
        "-a",
        "never",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-s",
        "workspace-write",
        "-C",
        str(workspace.resolve()),
        "-o",
        str(final_path.resolve()),
        "-",
    ]
    errors: list[str] = []
    returncode: int | None = None
    status = "failed"
    interrupted = False
    process: subprocess.Popen[str] | None = None
    started_at = datetime.now().astimezone().isoformat()
    started_clock = time.monotonic()
    with events_path.open("w", encoding="utf-8", newline="\n") as events_stream, stderr_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as stderr_stream:
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=events_stream,
                stderr=stderr_stream,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            process.communicate(PROMPT, timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            status = "timeout"
            errors.append(f"Codex CLI exceeded the {timeout}-second timeout")
            if process is not None:
                process.kill()
                process.wait()
                returncode = process.returncode
        except KeyboardInterrupt:
            status = "interrupted"
            errors.append("evaluation interrupted by user")
            interrupted = True
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                returncode = process.returncode
        except OSError as error:
            errors.append(f"could not start Codex CLI: {error}")

    usage, completed_event, event_errors = _parse_events(events_path)
    errors.extend(event_errors)
    validation = evaluation.check(case_name, workspace)
    if returncode not in (None, 0):
        errors.append(f"Codex CLI exited with code {returncode}")
    if not validation["pass"]:
        errors.extend(f"validation: {error}" for error in validation["errors"])
    if status not in ("timeout", "interrupted"):
        status = "passed" if not errors and returncode == 0 and completed_event else "failed"
    manifest = workspace / "EVAL_MANIFEST.json"
    result = {
        "case": case_name,
        "pass": status == "passed",
        "status": status,
        "started_at": started_at,
        "elapsed_seconds": round(time.monotonic() - started_clock, 3),
        "workspace": str(workspace.resolve()),
        "logs": {
            "events": str(events_path.resolve()),
            "stderr": str(stderr_path.resolve()),
            "final": str(final_path.resolve()),
        },
        "cli": {"path": cli_prefix[-1], "version": version},
        "argv": argv,
        "config_overrides": [],
        "rules_manifest": str(manifest.resolve()),
        "returncode": returncode,
        "completed_event": completed_event,
        "usage": usage,
        "usage_scope": "Codex CLI turn.completed event; subagent inclusion is not assumed",
        "validation": validation,
        "errors": errors,
    }
    return result, interrupted


def bench(
    case_name: str,
    output: Path | None,
    rules_root: Path,
    timeout: int,
    requested_cli: str | None,
    repository_root: Path,
) -> dict[str, Any]:
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    evaluation._rule_sources(rules_root)
    output = (output or _default_output(repository_root)).resolve()
    try:
        output.relative_to(repository_root.resolve())
    except ValueError as error:
        raise ValueError(
            "bench output must be inside the trusted repository so its copied .codex configuration loads"
        ) from error
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)
    workspaces = output / "workspaces"
    logs = output / "logs"
    selected = list(evaluation.CASES) if case_name == "all" else [case_name]
    if case_name == "all":
        evaluation.prepare("all", workspaces, rules_root)
    else:
        evaluation.prepare(case_name, workspaces / case_name, rules_root)

    payload: dict[str, Any] = {
        "pass": False,
        "command": "bench",
        "case": case_name,
        "output": str(output),
        "rules": str(rules_root.resolve()),
        "timeout_seconds": timeout,
        "interrupted": False,
        "results": [],
        "errors": [],
    }
    _checkpoint(payload, output)
    try:
        cli_prefix = _resolve_cli(requested_cli)
        version = _cli_version(cli_prefix)
    except ValueError as error:
        payload["errors"].append(str(error))
        _checkpoint(payload, output)
        print(f"summary: {output / 'summary.md'}", file=sys.stderr, flush=True)
        return payload
    payload["cli"] = {"path": cli_prefix[-1], "version": version}
    _checkpoint(payload, output)

    for index, name in enumerate(selected, 1):
        print(f"[{index}/{len(selected)}] {name}: running", file=sys.stderr, flush=True)
        result, interrupted = _run_case(
            name, workspaces / name, logs, cli_prefix, version, timeout
        )
        payload["results"].append(result)
        payload["interrupted"] = interrupted
        payload["errors"] = [
            f"{item['case']}: {error}"
            for item in payload["results"]
            for error in item["errors"]
        ]
        payload["pass"] = (
            len(payload["results"]) == len(selected)
            and all(item["pass"] for item in payload["results"])
        )
        _checkpoint(payload, output)
        print(
            f"[{index}/{len(selected)}] {name}: {result['status']}",
            file=sys.stderr,
            flush=True,
        )
        if interrupted:
            break
    print(f"summary: {output / 'summary.md'}", file=sys.stderr, flush=True)
    return payload
