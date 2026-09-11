"""Reference outputs used by the evaluation runner's oracle checks."""

from __future__ import annotations


SOLUTIONS = {
    "src/slug.py": '''def slugify(value: str) -> str:\n    """Return a URL slug for value."""\n    output = []\n    separator_pending = False\n    for character in value.lower():\n        if character.isalnum():\n            if separator_pending and output:\n                output.append("-")\n            output.append(character)\n            separator_pending = False\n        else:\n            separator_pending = True\n    return "".join(output)\n''',
    "src/order_summary.py": '''def summarize_orders(orders):\n    """Return aggregate values for a sequence of orders."""\n    total = sum(order["amount_cents"] for order in orders)\n    count = len(orders)\n    return {\n        "total_cents": total,\n        "count": count,\n        "average_cents": total // count if count else 0,\n    }\n''',
    "src/export/csv_export.py": '''import csv\nimport io\n\n\ndef export_csv(rows, fieldnames):\n    stream = io.StringIO(newline="")\n    writer = csv.writer(stream, lineterminator="\\n")\n    writer.writerow(fieldnames)\n    for row in rows:\n        writer.writerow([row.get(name, "") for name in fieldnames])\n    return stream.getvalue()\n''',
    "src/export/json_export.py": '''import json\n\n\ndef export_json(rows):\n    ordered = sorted((dict(row) for row in rows), key=lambda row: row["id"])\n    return json.dumps(ordered, sort_keys=True, separators=(",", ":"))\n''',
    "src/report/stats.py": '''def latest_events(events):\n    """Return a copied latest event for each id, ordered by id."""\n    latest = {}\n    for event in events:\n        previous = latest.get(event["id"])\n        if previous is None or event["timestamp"] >= previous["timestamp"]:\n            latest[event["id"]] = dict(event)\n    return [latest[event_id] for event_id in sorted(latest)]\n''',
    "src/report/markdown.py": '''from .stats import latest_events\n\n\ndef _cell(value):\n    return str(value).replace("\\r\\n", "<br>").replace("\\r", "<br>").replace("\\n", "<br>").replace("|", "\\\\|")\n\n\ndef render_markdown(events):\n    rows = latest_events(events)\n    lines = ["| ID | Timestamp | Message |", "| --- | --- | --- |"]\n    for row in rows:\n        lines.append(f"| {_cell(row['id'])} | {_cell(row['timestamp'])} | {_cell(row['message'])} |")\n    lines.append(f"Total: {len(rows)}")\n    return "\\n".join(lines) + "\\n"\n''',
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
