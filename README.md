# Cost-Efficient Codex Orchestrator

**English** | [简体中文](README.zh-CN.md)

A reusable configuration for on-demand multi-agent work in Codex. Cloning this repository does not install the configuration or change your global Codex settings.

| Stage / role | Model | Reasoning effort | Responsibility |
|---|---|---|---|
| Root | GPT-6 Astra | medium | Decomposition, orchestration, integration, verification |
| explorer | GPT-5.6 Luna | max | Bounded codebase investigation |
| worker | GPT-5.6 Sol | high | Implementation and tests |
| researcher | GPT-5.6 Luna | max | Focused documentation and source lookup |
| reviewer (optional) | GPT-6 Astra | xhigh | Independent review after integration and verification |

Run at most three subagents concurrently, for a total of four agents including the root. Independent review reuses a slot after earlier work completes. The root handles simple tasks directly and delegates only useful independent work. Implementation that depends on investigation waits for those findings.

## Repository layout

- `.codex/config.toml`: Root settings, generic subagent defaults, and concurrency limit.
- `.codex/agents/*.toml`: Models, reasoning effort, responsibilities, and permissions for the four named roles.
- `.agents/skills/cost-efficient-orchestrator/SKILL.md`: Delegation and acceptance rules.
- `AGENTS.md`: Project instructions pointing to the orchestration skill.

## Install into a project

1. Merge `.codex` and `.agents` into your target project's root directory. Back up and merge any existing files with matching names.
2. Merge the orchestration paragraph from this repository's `AGENTS.md` into the project's existing `AGENTS.md`, preserving its project rules.
3. If `.codex/config.toml` already exists, merge the model, reasoning effort, and `[agents]` keys without creating duplicate TOML tables. Preserve existing provider, authentication, MCP, and other settings.
4. Start a new Codex task in the trusted target project. Existing sessions may not reload model and tool settings; explicit project or UI overrides may also change the actual model used.
5. Invoke the skill explicitly if desired: `$cost-efficient-orchestrator Implement ..., using subagents where useful.`

This repository provides a project-scoped layout without an automatic installer. Named roles pin their models and reasoning effort, so changing generic subagent defaults does not change those roles. The researcher also needs lookup tools in the target environment. Model identifiers match the environment used to prepare this configuration; your environment must provide those models.

The explorer, researcher, and reviewer are read-only. The worker uses workspace-write, subject to the parent session's permissions. The root configuration does not set or override approval, authentication, or provider settings.

## Validation scope

The initial configuration package passed TOML parsing, role mapping, skill frontmatter, and archive integrity checks. It has not been installed into the active Codex configuration used to prepare it or tested through end-to-end model requests. On-demand delegation aims to control overhead; actual token usage depends on the task and context.

## Ongoing development

After changing the configuration, run the validator with Python 3.11 or later:

```sh
python scripts/validate.py
```

GitHub Actions runs on every push and pull request to validate TOML, models and reasoning effort, role permissions, concurrency, and the presence of instruction files. Validation makes no model requests, needs no API keys, and does not prove that models follow every orchestration rule.

Maintain role responsibilities in `.codex/agents/` and orchestration behavior in the skill file. When intentionally changing the topology, update the configuration, expected values in `scripts/validate.py`, and both README translations together. The validator keeps explicit expectations to detect accidental model substitutions. Use feature branches and pull requests to track changes, and issues to collect observed behavior and usage data.

## References

Architecture inspired by [donvito/codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator/). The configuration and documentation were written for the requested topology: Sol/high handles implementation and tests, Luna/max handles exploration and research, Astra/medium orchestrates, and Astra/xhigh reviews only when needed. There is no fixed tester stage.

Configuration reference: [OpenAI subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).
