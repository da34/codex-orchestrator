"""Validate the configured topology without credentials or model requests."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
ROLE_PERMISSIONS = {
    "explorer": "read-only",
    "worker": "workspace-write",
    "tester": "workspace-write",
    "researcher": "read-only",
    "reviewer": "read-only",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_preset(directory, root_model, root_effort, child_effort):
    config = tomllib.loads((directory / "config.toml").read_text(encoding="utf-8"))
    require(config["model"] == root_model, f"Root must use {root_model}: {directory}")
    require(config["model_reasoning_effort"] == root_effort, f"Root must use {root_effort} effort")
    agents = config["agents"]
    require(agents["enabled"] is True, "Subagents must be enabled")
    require(agents["max_concurrent_threads_per_session"] == 4, "Expected four child slots")
    require(agents["default_subagent_model"] == "gpt-5.6-luna", "Default child must use Luna")
    require(agents["default_subagent_reasoning_effort"] == child_effort, f"Default child must use {child_effort} effort")
    files = {path.stem: path for path in (directory / "agents").glob("*.toml")}
    require(files.keys() == ROLE_PERMISSIONS.keys(), "Expected explorer, worker, tester, researcher, reviewer only")
    roles = {}
    for name, permission in ROLE_PERMISSIONS.items():
        role = tomllib.loads(files[name].read_text(encoding="utf-8"))
        require(role["name"] == name, f"Role name mismatch: {name}")
        model, effort = ("gpt-6-astra", "low") if name == "reviewer" else ("gpt-5.6-luna", child_effort)
        expected = (model, effort, permission)
        actual = tuple(role[key] for key in ("model", "model_reasoning_effort", "sandbox_mode"))
        require(actual == expected, f"Topology mismatch for {name}: {actual}")
        for key in ("description", "developer_instructions"):
            require(isinstance(role[key], str) and role[key].strip(), f"Missing {name}.{key}")
        roles[name] = role
    return roles


def main():
    pro = validate_preset(ROOT / ".codex", "gpt-6-astra", "medium", "max")
    plus = validate_preset(ROOT / "presets/plus/.codex", "gpt-5.6-luna", "max", "medium")
    for name in ROLE_PERMISSIONS:
        for key in ("description", "developer_instructions"):
            require(pro[name][key] == plus[name][key], f"Preset instructions differ: {name}.{key}")
    skill = ROOT / ".agents/skills/codex-orchestrator/SKILL.md"
    require(skill.is_file(), "Missing orchestration skill")
    require((ROOT / "AGENTS.md").is_file(), "Missing project instruction entrypoint")
    print("PASS: Plus and Pro TOML, role models, effort, permissions, concurrency, and shared instructions")


if __name__ == "__main__":
    main()
