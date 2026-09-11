#!/usr/bin/env python3
"""Prepare and check small, repeatable orchestration evaluation cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


CONFIG_TASK = """# Investigate configuration precedence

Read the implementation under `src/config/` and write `answers.json`. Do not change
the source files. Report what the code does, including the complete call path used by
`load_config`.

`answers.json` must have this shape:

```json
{
  "precedence_low_to_high": ["..."],
  "skipped_value": "...",
  "preserves_false_and_zero": true,
  "call_path": ["path:symbol"]
}
```

Use these serialization rules so the answer can be checked without interpreting prose:

- `precedence_low_to_high` contains each of `defaults`, `file`, `environment`, and
  `cli` once, ordered from lowest to highest precedence.
- `skipped_value` is a string chosen from `null`, `false`, `zero`,
  `empty_string`, or `missing`.
- `call_path` starts with `src/config/api.py:load_config`, then lists every
  repository-defined function that it calls, in execution order. Format every item
  as `repository-relative-path:function-name`.
"""

CACHE_TASK = """# Investigate cache behavior

Read the implementation under `src/cache/` and write `answers.json`. Do not change
the source files. Report the cache key inputs, when archived records are filtered,
the exact expiration comparison, and the call path from the public service function.

`answers.json` must have this shape:

```json
{
  "key_fields": ["..."],
  "archived_filter_stage": "...",
  "expires_when": "...",
  "call_path": ["path:symbol"]
}
```

Use these serialization rules:

- `key_fields` contains the parameter names used to construct the key, in order.
- `archived_filter_stage` is one of `before_cache_write`, `after_cache_write`, or
  `not_filtered`.
- `expires_when` copies the comparison expression from `TimedCache.get`, with one
  space around its comparison operator.
- `call_path` describes the cache-miss branch. Start with
  `src/cache/service.py:load_record`, then list repository-defined functions and
  methods invoked by that branch in execution order, formatted as
  `repository-relative-path:qualified-name`. Exclude calls on injected external
  objects, such as the backend client's own methods.
"""


CASES: dict[str, dict[str, Any]] = {
    "slug": {
        "kind": "implementation",
        "summary": "Repair Unicode-aware slug generation.",
        "task": """# Repair slug generation

Implement `slugify(value: str) -> str` in `src/slug.py`.

The result must lowercase Unicode text, preserve every Unicode letter and number,
replace each run of other characters with one ASCII hyphen, and remove leading or
trailing hyphens. Preserve the public function name and do not add dependencies.
""",
        "files": {
            "src/__init__.py": "",
            "src/slug.py": '''def slugify(value: str) -> str:\n    """Return a URL slug for value."""\n    return "-".join(value.lower().split())\n''',
        },
    },
    "summary": {
        "kind": "implementation",
        "summary": "Compute an order summary, including the empty case.",
        "task": """# Complete order summaries

Implement `summarize_orders(orders)` in `src/order_summary.py`. Each order is a
mapping with an integer `amount_cents`.

Return a new mapping with `total_cents`, `count`, and `average_cents`. Total is the
sum of all amounts, count is the number of orders, and average is the mathematical
floor of total divided by count. The empty average is zero. Do not mutate the input.
""",
        "files": {
            "src/__init__.py": "",
            "src/order_summary.py": '''def summarize_orders(orders):\n    """Return aggregate values for a sequence of orders."""\n    total = sum(order["amount_cents"] for order in orders)\n    return {\n        "total_cents": total,\n        "count": len(orders),\n        "average_cents": total / len(orders),\n    }\n''',
        },
    },
    "investigate-config": {
        "kind": "investigation",
        "summary": "Trace configuration sources and merge semantics.",
        "task": CONFIG_TASK,
        "files": {
            "src/__init__.py": "",
            "src/config/__init__.py": "from .api import load_config\n",
            "src/config/defaults.py": '''DEFAULTS = {\n    "color": True,\n    "retries": 3,\n    "region": "local",\n}\n\n\ndef default_config():\n    return dict(DEFAULTS)\n''',
            "src/config/file_source.py": '''import json\n\n\ndef read_config_file(path):\n    if path is None:\n        return {}\n    with open(path, encoding="utf-8") as stream:\n        return json.load(stream)\n''',
            "src/config/env_source.py": '''ENV_KEYS = {\n    "APP_COLOR": "color",\n    "APP_RETRIES": "retries",\n    "APP_REGION": "region",\n}\n\n\ndef read_environment(environment):\n    return {name: environment[key] for key, name in ENV_KEYS.items() if key in environment}\n''',
            "src/config/merge.py": '''def merge_layers(*layers):\n    merged = {}\n    for layer in layers:\n        for name, value in layer.items():\n            if value is not None:\n                merged[name] = value\n    return merged\n''',
            "src/config/api.py": '''from .defaults import default_config\nfrom .env_source import read_environment\nfrom .file_source import read_config_file\nfrom .merge import merge_layers\n\n\ndef load_config(file_path=None, environment=None, cli=None):\n    file_values = read_config_file(file_path)\n    env_values = read_environment(environment or {})\n    cli_values = cli or {}\n    return merge_layers(default_config(), file_values, env_values, cli_values)\n''',
        },
    },
    "investigate-cache": {
        "kind": "investigation",
        "summary": "Trace cache identity, filtering, and expiration.",
        "task": CACHE_TASK,
        "files": {
            "src/__init__.py": "",
            "src/cache/__init__.py": "from .service import load_record\n",
            "src/cache/store.py": '''class TimedCache:\n    def __init__(self):\n        self._entries = {}\n\n    def get(self, key, now, ttl_seconds):\n        entry = self._entries.get(key)\n        if entry is None:\n            return None\n        stored_at, value = entry\n        age = now - stored_at\n        if age >= ttl_seconds:\n            del self._entries[key]\n            return None\n        return value\n\n    def put(self, key, value, now):\n        self._entries[key] = (now, value)\n''',
            "src/cache/backend.py": '''def fetch_record(client, tenant_id, record_id):\n    return client.fetch(tenant_id=tenant_id, record_id=record_id)\n''',
            "src/cache/service.py": '''from .backend import fetch_record\n\n\ndef cache_key(tenant_id, record_id):\n    return (tenant_id, record_id)\n\n\ndef load_record(cache, client, tenant_id, record_id, include_archived, now, ttl_seconds):\n    key = cache_key(tenant_id, record_id)\n    cached = cache.get(key, now, ttl_seconds)\n    if cached is not None:\n        return cached\n    record = fetch_record(client, tenant_id, record_id)\n    if record is not None and record.get("archived") and not include_archived:\n        record = None\n    cache.put(key, record, now)\n    return record\n''',
        },
    },
    "export": {
        "kind": "implementation",
        "summary": "Implement deterministic CSV and JSON exports.",
        "task": """# Complete data exports

Implement both public functions:

- `export_csv(rows, fieldnames)` in `src/export/csv_export.py` returns a string with
  one header row and one row per mapping. Use the supplied field order, CSV quoting
  rules, and `\\n` as the record terminator, including the final record.
- `export_json(rows)` in `src/export/json_export.py` returns compact JSON. Sort a
  copied sequence stably by each row's `id`, use lexicographically sorted object
  keys, and do not mutate any input list or row.

Use the Python standard library and preserve the public interfaces.
""",
        "files": {
            "src/__init__.py": "",
            "src/export/__init__.py": "from .csv_export import export_csv\nfrom .json_export import export_json\n",
            "src/export/csv_export.py": '''def export_csv(rows, fieldnames):\n    lines = [",".join(fieldnames)]\n    lines.extend(",".join(str(row.get(name, "")) for name in fieldnames) for row in rows)\n    return "\\n".join(lines)\n''',
            "src/export/json_export.py": '''import json\n\n\ndef export_json(rows):\n    rows.sort(key=lambda row: row["id"])\n    return json.dumps(rows)\n''',
        },
    },
    "report": {
        "kind": "implementation",
        "summary": "Deduplicate event data and render a Markdown report.",
        "task": """# Complete event reports

Implement both public functions:

- `latest_events(events)` in `src/report/stats.py` returns one copied mapping per
  `id`, ordered by `id`. Every timestamp has the fixed UTC format
  `YYYY-MM-DDTHH:MM:SSZ`. Keep the greatest timestamp; if timestamps tie, the later
  item in the input wins. Do not mutate the input or its mappings.
- `render_markdown(events)` in `src/report/markdown.py` renders the result as a
  Markdown table with columns `ID`, `Timestamp`, and `Message`, plus a final
  `Total: N` line. Escape literal `|` in cells with `\\|` and replace CRLF, CR, or
  LF inside cells with `<br>`. The output layout is exactly the header
  `| ID | Timestamp | Message |`, then the separator
  `| --- | --- | --- |`, then one row per event as
  `| ID | Timestamp | Message |`, and finally `Total: N`. Do not insert blank lines,
  and end the document with one newline. An empty report still contains the header,
  separator, and `Total: 0`.

`render_markdown` must obtain the deduplicated records through `latest_events`.
""",
        "files": {
            "src/__init__.py": "",
            "src/report/__init__.py": "from .markdown import render_markdown\nfrom .stats import latest_events\n",
            "src/report/stats.py": '''def latest_events(events):\n    """Return one event for each id."""\n    return list(events)\n''',
            "src/report/markdown.py": '''from .stats import latest_events\n\n\ndef render_markdown(events):\n    rows = latest_events(events)\n    lines = ["| ID | Timestamp | Message |", "| --- | --- | --- |"]\n    for row in rows:\n        lines.append(f"| {row['id']} | {row['timestamp']} | {row['message']} |")\n    lines.append(f"Total: {len(rows)}")\n    return "\\n".join(lines)\n''',
        },
    },
}


CONFIG_ANSWER = {
    "precedence_low_to_high": ["defaults", "file", "environment", "cli"],
    "skipped_value": "null",
    "preserves_false_and_zero": True,
    "call_path": [
        "src/config/api.py:load_config",
        "src/config/file_source.py:read_config_file",
        "src/config/env_source.py:read_environment",
        "src/config/defaults.py:default_config",
        "src/config/merge.py:merge_layers",
    ],
}

CACHE_ANSWER = {
    "key_fields": ["tenant_id", "record_id"],
    "archived_filter_stage": "before_cache_write",
    "expires_when": "age >= ttl_seconds",
    "call_path": [
        "src/cache/service.py:load_record",
        "src/cache/service.py:cache_key",
        "src/cache/store.py:TimedCache.get",
        "src/cache/backend.py:fetch_record",
        "src/cache/store.py:TimedCache.put",
    ],
}

CHECK_PROGRAMS = {
    "slug": r'''
from src.slug import slugify
cases = {
    "": "",
    " Hello, WORLD! ": "hello-world",
    "Crème déjà vu": "crème-déjà-vu",
    "中文 版本 ２": "中文-版本-２",
    "a___b...c": "a-b-c",
    "---": "",
}
for value, expected in cases.items():
    actual = slugify(value)
    assert actual == expected, f"slugify({value!r}) returned {actual!r}, expected {expected!r}"
''',
    "summary": r'''
from copy import deepcopy
from src.order_summary import summarize_orders
orders = [{"amount_cents": 101}, {"amount_cents": 102}, {"amount_cents": -4}]
before = deepcopy(orders)
assert summarize_orders(orders) == {"total_cents": 199, "count": 3, "average_cents": 66}
assert orders == before, "summarize_orders mutated its input"
assert summarize_orders([]) == {"total_cents": 0, "count": 0, "average_cents": 0}
assert summarize_orders([{"amount_cents": -3}, {"amount_cents": 0}])["average_cents"] == -2
''',
    "export": r'''
from copy import deepcopy
from src.export.csv_export import export_csv
from src.export.json_export import export_json
rows = [
    {"id": 2, "name": "Beta", "note": "line 1\nline 2"},
    {"id": 1, "name": "Alpha, Inc.", "note": 'said "hi"'},
    {"id": 2, "name": "Beta second", "note": ""},
]
before = deepcopy(rows)
expected_csv = 'id,name,note\n2,Beta,"line 1\nline 2"\n1,"Alpha, Inc.","said ""hi"""\n2,Beta second,\n'
assert export_csv(rows, ["id", "name", "note"]) == expected_csv
expected_json = '[{"id":1,"name":"Alpha, Inc.","note":"said \\"hi\\""},{"id":2,"name":"Beta","note":"line 1\\nline 2"},{"id":2,"name":"Beta second","note":""}]'
assert export_json(rows) == expected_json
assert rows == before, "an exporter mutated its input"
assert export_csv([], ["id", "name"]) == "id,name\n"
assert export_json([]) == "[]"
''',
    "report": r'''
from copy import deepcopy
from src.report.stats import latest_events
from src.report.markdown import render_markdown
events = [
    {"id": "b", "timestamp": "2026-01-02T10:00:00Z", "message": "old"},
    {"id": "a", "timestamp": "2026-01-03T09:00:00Z", "message": "line 1\r\nline|2"},
    {"id": "b", "timestamp": "2026-01-04T10:00:00Z", "message": "tie old"},
    {"id": "b", "timestamp": "2026-01-04T10:00:00Z", "message": "tie|new"},
    {"id": "c", "timestamp": "2026-01-05T10:00:00Z", "message": "newer\roption"},
    {"id": "c", "timestamp": "2026-01-01T10:00:00Z", "message": "older after newer"},
    {"id": "d", "timestamp": "2026-01-06T10:00:00Z", "message": "lf\nonly"},
]
before = deepcopy(events)
latest = latest_events(events)
expected_latest = [events[1], events[3], events[4], events[6]]
assert latest == expected_latest
assert all(result is not source for result, source in zip(latest, expected_latest)), "results must be copied"
expected = "| ID | Timestamp | Message |\n| --- | --- | --- |\n| a | 2026-01-03T09:00:00Z | line 1<br>line\\|2 |\n| b | 2026-01-04T10:00:00Z | tie\\|new |\n| c | 2026-01-05T10:00:00Z | newer<br>option |\n| d | 2026-01-06T10:00:00Z | lf<br>only |\nTotal: 4\n"
assert render_markdown(events) == expected
assert events == before, "report functions mutated their input"
empty = "| ID | Timestamp | Message |\n| --- | --- | --- |\nTotal: 0\n"
assert latest_events([]) == []
assert render_markdown([]) == empty

import sys
calls = []
def record_call(frame, event, arg):
    if event == "call" and frame.f_code is latest_events.__code__:
        calls.append(True)
sys.setprofile(record_call)
try:
    assert render_markdown(events) == expected
finally:
    sys.setprofile(None)
assert calls, "render_markdown must call latest_events"
''',
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _rule_sources(root: Path) -> list[tuple[Path, Path]]:
    sources = [
        (root / "AGENTS.md", Path("AGENTS.md")),
        (root / ".codex", Path(".codex")),
        (root / ".agents" / "skills", Path(".agents") / "skills"),
    ]
    missing = [str(source) for source, _ in sources if not source.exists()]
    if missing:
        raise ValueError("rules snapshot is missing: " + ", ".join(missing))
    return sources


def _copy_rules(root: Path, workspace: Path) -> list[str]:
    copied: list[str] = []
    for source, relative in _rule_sources(root):
        destination = workspace / relative
        if source.is_dir():
            shutil.copytree(source, destination)
            copied.extend(
                path.relative_to(workspace).as_posix()
                for path in sorted(destination.rglob("*"))
                if path.is_file()
            )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative.as_posix())
    return copied


def _manifest(workspace: Path, case_name: str, bundle_files: list[str], rule_files: list[str]) -> None:
    def entries(paths: list[str]) -> list[dict[str, str]]:
        return [
            {"path": relative, "sha256": _sha256((workspace / relative).read_bytes())}
            for relative in sorted(paths)
        ]

    payload = {
        "format_version": 1,
        "case": case_name,
        "bundle": entries(bundle_files),
        "rules": entries(rule_files),
    }
    _write_text(workspace / "EVAL_MANIFEST.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _prepare_one(case_name: str, workspace: Path, rules_root: Path) -> None:
    case = CASES[case_name]
    workspace.mkdir(parents=True, exist_ok=False)
    bundle_files = ["TASK.md"]
    _write_text(workspace / "TASK.md", case["task"])
    for relative, content in case["files"].items():
        _write_text(workspace / relative, content)
        bundle_files.append(relative)
    rule_files = _copy_rules(rules_root, workspace)
    _manifest(workspace, case_name, bundle_files, rule_files)


def prepare(case_name: str, output: Path, rules_root: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    _rule_sources(rules_root)
    workspaces: dict[str, str] = {}
    if case_name == "all":
        output.mkdir(parents=True, exist_ok=False)
        for name in CASES:
            workspace = output / name
            _prepare_one(name, workspace, rules_root)
            workspaces[name] = str(workspace.resolve())
    else:
        _prepare_one(case_name, output, rules_root)
        workspaces[case_name] = str(output.resolve())
    return {"pass": True, "case": case_name, "workspaces": workspaces, "errors": []}


def _validate_manifest(case_name: str, workspace: Path) -> list[str]:
    path = workspace / "EVAL_MANIFEST.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid or missing EVAL_MANIFEST.json: {error}"]
    if not isinstance(data, dict):
        return ["EVAL_MANIFEST.json must contain a JSON object"]
    if data.get("format_version") != 1 or data.get("case") != case_name:
        return ["EVAL_MANIFEST.json does not identify this case"]
    return []


def _check_investigation(case_name: str, workspace: Path) -> list[str]:
    errors: list[str] = []
    for relative, expected in CASES[case_name]["files"].items():
        path = workspace / relative
        try:
            actual = path.read_bytes()
        except OSError as error:
            errors.append(f"source fixture missing: {relative}: {error}")
            continue
        if actual != expected.encode("utf-8"):
            errors.append(f"investigation source was changed: {relative}")
    answers_path = workspace / "answers.json"
    try:
        actual_answer = json.loads(answers_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid or missing answers.json: {error}")
        return errors
    expected_answer = CONFIG_ANSWER if case_name == "investigate-config" else CACHE_ANSWER
    if actual_answer != expected_answer:
        errors.append("answers.json does not match the behavior and evidence in the source")
    return errors


def _check_implementation(case_name: str, workspace: Path) -> list[str]:
    program = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        + CHECK_PROGRAMS[case_name]
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", program, str(workspace.resolve())],
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return [f"isolated behavior check could not run: {error}"]
    if completed.returncode == 0:
        return []
    detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
    return ["behavior check failed: " + detail[-2000:]]


def check(case_name: str, workspace: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not workspace.is_dir():
        errors.append(f"workspace is not a directory: {workspace}")
    else:
        errors.extend(_validate_manifest(case_name, workspace))
        if not errors:
            if CASES[case_name]["kind"] == "investigation":
                errors.extend(_check_investigation(case_name, workspace))
            else:
                errors.extend(_check_implementation(case_name, workspace))
    return {"pass": not errors, "case": case_name, "workspace": str(workspace.resolve()), "errors": errors}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list the fixed evaluation cases")

    prepare_parser = subparsers.add_parser("prepare", help="create one or all isolated workspaces")
    prepare_parser.add_argument("case", choices=[*CASES, "all"])
    prepare_parser.add_argument("--output", required=True, type=Path)
    prepare_parser.add_argument("--rules", type=Path)

    check_parser = subparsers.add_parser("check", help="check a prepared workspace")
    check_parser.add_argument("case", choices=[*CASES, "all"])
    check_parser.add_argument("--workspace", required=True, type=Path)

    bench_parser = subparsers.add_parser("bench", help="run cases in fresh Codex CLI sessions")
    bench_parser.add_argument("--case", choices=[*CASES, "all"], default="all")
    bench_parser.add_argument("--output", type=Path)
    bench_parser.add_argument("--rules", type=Path)
    bench_parser.add_argument("--timeout", type=int, default=900)
    bench_parser.add_argument("--codex", help="path or command name for the Codex CLI")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "list":
            payload = {
                "pass": True,
                "cases": [
                    {"name": name, "kind": case["kind"], "summary": case["summary"]}
                    for name, case in CASES.items()
                ],
                "errors": [],
            }
        elif args.command == "prepare":
            rules_root = args.rules or Path(__file__).resolve().parents[1]
            payload = prepare(args.case, args.output, rules_root.resolve())
        elif args.command == "bench":
            from bench import bench

            repository_root = Path(__file__).resolve().parents[1]
            rules_root = (args.rules or repository_root).resolve()
            payload = bench(
                args.case,
                args.output,
                rules_root,
                args.timeout,
                args.codex,
                repository_root,
            )
        elif args.case == "all":
            results = [check(name, args.workspace / name) for name in CASES]
            errors = [f"{result['case']}: {error}" for result in results for error in result["errors"]]
            payload = {"pass": not errors, "case": "all", "results": results, "errors": errors}
        else:
            payload = check(args.case, args.workspace)
    except (OSError, ValueError) as error:
        payload = {"pass": False, "errors": [str(error)]}
    _json_output(payload)
    if payload.get("interrupted"):
        return 130
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
