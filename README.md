# Codex Orchestrator

**English** | [简体中文](README.zh-CN.md)

On-demand multi-agent configuration for Codex: **Astra orchestrates, Luna investigates, Sol implements.** Add an independent Astra review when the change needs one.

This repository provides agent profiles, an orchestration skill, and project instructions for coding tasks that benefit from focused delegation. Simple tasks stay with the root agent. Independent work can run in parallel, and the root integrates and verifies the result.

## How it works

```text
                    Astra · medium
                   root / orchestrator
                           |
                    delegate on demand
              +------------+------------+
              |            |            |
           explorer      worker      researcher
          Luna · max    Sol · high    Luna · max
           codebase    implementation  focused
        investigation    + tests       lookup
              |            |            |
              +------------+------------+
                           |
                    Astra · medium
                   integrate + verify
                           |
                     only if needed
                           |
                    Astra · xhigh
                   independent review
```

| Role | Model | Reasoning effort | Responsibility |
|---|---|---|---|
| Root | `gpt-6-astra` | `medium` | Scope, delegate, integrate, and verify |
| explorer | `gpt-5.6-luna` | `max` | Investigate a bounded codebase question |
| worker | `gpt-5.6-sol` | `high` | Implement changes and run relevant tests |
| researcher | `gpt-5.6-luna` | `max` | Answer focused documentation or source questions |
| reviewer | `gpt-6-astra` | `xhigh` | Independently inspect the integrated change when needed |

The configuration allows three concurrent subagents. Review runs after integration and verification, reusing an available slot. Work that depends on investigation waits for the findings. Delegation is intended to control overhead; it does not guarantee lower token usage for every task.

## Requirements

- A Codex environment with subagents, custom agent profiles, and skills support.
- Access to the configured models and reasoning levels, or compatible replacements you configure yourself.
- Lookup tools available to Codex when using the researcher.
- Python 3.11 or later only if you want to run the configuration validator.

See the [OpenAI subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents) for platform configuration details.

## Installation

Clone the repository:

```sh
git clone https://github.com/da34/codex-orchestrator.git
```

Merge these components into your target project:

| Component | Purpose |
|---|---|
| `.codex/config.toml` | Root model, default subagent settings, and concurrency |
| `.codex/agents/` | Four named agent profiles |
| `.agents/skills/codex-orchestrator/` | Orchestration skill |
| `AGENTS.md` | Project instruction to use the skill |

For an existing project, back up overlapping files and merge their contents. Preserve existing `AGENTS.md` rules and provider, authentication, MCP, and permission settings. Merge the keys into any existing `[agents]` table instead of adding a duplicate table.

Open a new Codex task in the trusted target project after installation. Cloning alone does not install the configuration. This repository uses project-scoped settings and provides no automatic installer.

## Usage

Invoke the skill with a concrete task:

```text
$codex-orchestrator
Add CSV export to the invoices page. Follow the existing export conventions
and verify column ordering, escaping, and empty results.
```

Or request an independent review as part of the task:

```text
$codex-orchestrator
Refactor the permission checks without changing behavior.
After integration and verification, use an independent reviewer
to check for access-control regressions.
```

Delegate when the root can advance separate work in parallel, or a bounded investigation can return concise evidence while keeping substantial exploration out of the root's context. Complexity alone does not justify delegation. During execution the root works within its own scope, uses long event-driven waits when idle, and inspects completed changes at handoff. Coordination focuses on blockers, interface changes, and completion.

The worker runs checks for its changes and reports commands and results. The root reuses this evidence and covers integration boundaries and remaining acceptance criteria, repeating checks when affected by later changes, insufficient evidence, or findings. Required project checks still apply. There is no separate tester stage. The reviewer is optional unless requested or warranted by material residual risk.

## Customization

- Change the root model and effort in `.codex/config.toml`.
- Change a named role's model, effort, permissions, or instructions in its `.codex/agents/*.toml` file. Named roles pin these values, so changing generic subagent defaults does not change them.
- Adjust delegation and review criteria in the `codex-orchestrator` skill.
- Adjust `agents.max_concurrent_threads_per_session` to change the child-agent limit.

The explorer, researcher, and reviewer use read-only permissions; the worker uses workspace-write. Execution remains subject to the parent session's permissions. Explicit UI or project overrides may change the active configuration, and existing sessions may need to be restarted to load changes.

## Validation and contributions

Run the configuration checks from this repository:

```sh
python scripts/validate.py
```

GitHub Actions runs the same checks on pushes and pull requests. They validate TOML, role models and effort, permissions, concurrency, and the presence of instruction files. They do not make model requests or verify runtime orchestration behavior.

To evaluate orchestration behavior, run `python evals/run.py bench` with Python 3.11+, uv, Docker Desktop (Linux engine), and Codex authentication. The [repeatable evaluation pack](evals/README.md) uses pinned Harbor to run six independent cases. `--self-test` checks oracle/nop baselines without model calls. Reported usage may not include all subagents; passing checks does not demonstrate token savings.

Issues and pull requests are welcome. For bugs, include the relevant Codex environment, configuration, task, and observed behavior with secrets removed. When proposing a topology change, update the configuration, expected values in `scripts/validate.py`, and both README translations together. Keep unrelated changes in separate pull requests.

## Acknowledgments

Architecture inspired by [donvito/codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator/).

## License

[MIT](LICENSE) © 2026 da34.
