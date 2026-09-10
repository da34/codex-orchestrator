"""Validate the configured topology without credentials or model requests."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "explorer": ("gpt-5.6-luna", "max", "read-only"),
    "worker": ("gpt-5.6-sol", "high", "workspace-write"),
    "researcher": ("gpt-5.6-luna", "max", "read-only"),
    "reviewer": ("gpt-6-astra", "xhigh", "read-only"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
    require(config["model"] == "gpt-6-astra", "Root must use Astra")
    require(config["model_reasoning_effort"] == "medium", "Root must use medium effort")
    agents = config["agents"]
    require(agents["enabled"] is True, "Subagents must be enabled")
    require(agents["max_concurrent_threads_per_session"] == 3, "Expected three child slots")
    require(agents["default_subagent_model"] == "gpt-5.6-luna", "Default child must use Luna")
    require(agents["default_subagent_reasoning_effort"] == "max", "Default child must use max effort")
    files = {path.stem: path for path in (ROOT / ".codex/agents").glob("*.toml")}
    require(files.keys() == EXPECTED.keys(), "Expected explorer, worker, researcher, reviewer only")
    for name, expected in EXPECTED.items():
        role = tomllib.loads(files[name].read_text(encoding="utf-8"))
        require(role["name"] == name, f"Role name mismatch: {name}")
        actual = tuple(role[key] for key in ("model", "model_reasoning_effort", "sandbox_mode"))
        require(actual == expected, f"Topology mismatch for {name}: {actual}")
        for key in ("description", "developer_instructions"):
            require(isinstance(role[key], str) and role[key].strip(), f"Missing {name}.{key}")
    skill = ROOT / ".agents/skills/cost-efficient-orchestrator/SKILL.md"
    require(skill.is_file(), "Missing orchestration skill")
    require((ROOT / "AGENTS.md").is_file(), "Missing project instruction entrypoint")
    print("PASS: TOML, role models, effort, permissions, concurrency, and instruction files")


if __name__ == "__main__":
    main()
