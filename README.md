# Codex Orchestrator

**English** | [简体中文](README.zh-CN.md)

On-demand multi-agent configuration for Codex with two presets: a default **Pro** topology and a **Plus** topology. Both use the same five named roles and add an independent Astra review only when the change needs one.

This repository provides agent profiles, an orchestration skill, and project instructions for coding tasks that benefit from focused delegation. Simple tasks stay with the root agent. Independent work can run in parallel, and the root integrates and verifies the result.

## How it works

```text
                         root
             scope, decide, integrate, verify
                           |
                    delegate on demand
       +-----------+----------+------------+
       |           |          |            |
   explorer     worker      tester     researcher
 investigate  implement   independent    research
                + tests    bounded tests
       |           |          |            |
       +-----------+----------+------------+
                           |
                          root
                  integrate + verify
                           |
                reviewer, only if needed
                  independent review
```

The root may delegate to four execution roles: `explorer`, `worker`, `tester`, and `researcher`. The `tester` is available for useful, bounded independent testing; it is not a required pipeline stage, and the `worker` still owns the relevant tests for its changes. The fifth named role, `reviewer`, is used after integration and verification only when requested or justified by material residual risk.

| Setting | Default Pro preset | Plus preset |
|---|---|---|
| Source | `.codex/` | `presets/plus/.codex/` |
| Root | `gpt-6-astra` · `medium` | `gpt-5.6-luna` · `max` |
| Generic subagent default | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` |
| Concurrent subagents | 4, excluding root | 4, excluding root |

| Named role | Default Pro preset | Plus preset | Responsibility |
|---|---|---|---|
| explorer | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | Investigate a bounded codebase question |
| worker | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | Implement changes and run relevant tests |
| tester | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | Run bounded independent testing when useful |
| researcher | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | Answer focused documentation or source questions |
| reviewer | `gpt-6-astra` · `low` | `gpt-6-astra` · `low` | Independently inspect the integrated change when needed |

Each preset sets the subagent concurrency limit to four, excluding the root. Actual parallelism remains subject to Codex runtime and session limits. Review reuses an available slot after integration and verification, and work that depends on investigation waits for the findings. Delegation is intended to control coordination overhead; it does not guarantee lower token usage for every task.

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

Choose one preset and merge its contents into the target project's `.codex/` directory:

| Preset | Source to merge | Intended target |
|---|---|---|
| Default Pro | `.codex/config.toml` and `.codex/agents/` | `<target>/.codex/` |
| Plus | `presets/plus/.codex/config.toml` and `presets/plus/.codex/agents/` | `<target>/.codex/` |

Then merge the shared components:

| Component | Purpose |
|---|---|
| `.agents/skills/codex-orchestrator/` | Orchestration skill shared by both presets |
| `AGENTS.md` | Project instruction shared by both presets |

The two presets contain the same five named roles, role instructions, and delegation behavior; their model and reasoning settings differ as shown above. Do not merge both preset configurations. Codex does not automatically detect a subscription plan or select a preset.

For an existing project, back up overlapping files and merge their contents. Preserve existing `AGENTS.md` rules, skills, and provider, authentication, MCP, and permission settings. Merge the selected keys into any existing `[agents]` table instead of adding a duplicate table.

Open a new Codex task in the trusted target project after installation. Cloning alone does not install the configuration. This repository uses project-scoped settings and provides neither an installer nor automatic plan detection.

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

The worker runs checks for its changes and reports commands and results. The root reuses this evidence and covers integration boundaries and remaining acceptance criteria, repeating checks when affected by later changes, insufficient evidence, or findings. Required project checks still apply. A tester may independently exercise a bounded risk or acceptance criterion when that separate work is useful, but testing is not a mandatory handoff stage. The reviewer is optional unless requested or warranted by material residual risk.

## Customization

- Change the selected preset's root model and effort in the target project's `.codex/config.toml`.
- Change a named role's model, effort, permissions, or instructions in the target project's `.codex/agents/*.toml` file. Named roles pin these values, so changing generic subagent defaults does not change them.
- Adjust delegation and review criteria in the `codex-orchestrator` skill.
- Adjust `agents.max_concurrent_threads_per_session` to change the configured subagent limit, subject to runtime limits.

Keep the role instructions aligned across presets if you customize both. The explorer, researcher, and reviewer use read-only permissions; worker and tester use workspace-write. Execution remains subject to the parent session's permissions. Explicit UI or project overrides may change the active configuration, and existing sessions may need to be restarted to load changes.

## Validation and contributions

Run the configuration checks from this repository:

```sh
python scripts/validate.py
```

GitHub Actions runs the same checks on pushes and pull requests. They validate TOML, the two preset matrices, five named roles, permissions, concurrency, matching role descriptions and instructions across presets, and the presence of instruction files. They do not make model requests or verify runtime orchestration behavior.

To evaluate orchestration behavior, run `python evals/run.py bench` with Python 3.11+, uv, Docker Desktop (Linux engine), and Codex authentication. The [repeatable evaluation pack](evals/README.md) uses pinned Harbor to run six independent task cases. `--self-test` checks oracle/nop baselines without model calls. Reported usage may not include all subagents; passing checks does not demonstrate token savings.

Issues and pull requests are welcome. For bugs, include the relevant Codex environment, configuration, task, and observed behavior with secrets removed. When proposing a topology change, update the configuration, expected values in `scripts/validate.py`, and both README translations together. Keep unrelated changes in separate pull requests.

## Acknowledgments

Architecture inspired by [donvito/codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator/).

## License

[MIT](LICENSE) © 2026 da34.
