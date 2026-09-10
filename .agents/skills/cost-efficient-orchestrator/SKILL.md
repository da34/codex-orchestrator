---
name: cost-efficient-orchestrator
description: Coordinate coding and investigation work with the user's Astra, Sol, and Luna agent topology. Use for tasks with bounded implementation, code exploration, documentation research, or a requested independent review; handle simple work directly.
---

# On-demand orchestration

Use the root for task decomposition, decisions, integration, and verification. The model and effort assignments are defined in `.codex/config.toml` and `.codex/agents/*.toml` at the installed project root. Read the relevant role file before dispatch; use its configured model, effort, and instructions. If the active parent model differs from the configured root, state the mismatch rather than claiming to have changed the running model.

## Delegate useful work

First identify the acceptance criteria and whether delegation would produce an independent, useful result. Complete simple questions and small self-contained edits directly. Spawn only needed roles:

- `explorer` for a bounded question about existing code or behavior.
- `worker` for implementation and relevant tests.
- `researcher` for a focused external lookup.

Parallelize independent work while the root advances a useful separate part. When implementation depends on exploration or research, wait for those findings before assigning the dependent work. Give each assignment its question or acceptance criteria, necessary context, file ownership when writing, and expected evidence. Keep at most three children running and avoid overlapping writes.

Use native subagents rather than creating user-visible standalone tasks. When the spawn tool accepts explicit model and reasoning overrides, pass the role's values. If full-history inheritance prevents model overrides, use a bounded context fork or a fresh context with the required task evidence. Report unavailable models or tools; continue useful root work without silently claiming the requested topology ran.

## Integrate and verify

Wait for required results, inspect the changes, reconcile issues, and verify the integrated behavior against the acceptance criteria. Distinguish checks actually run from suggestions. The worker owns implementation tests; a separate tester is not part of this topology.

## Review only when needed

After integration and verification, use a fresh `reviewer` when the user requests it or material residual risk warrants independent inspection, such as a cross-module change with uncertain interactions, a security boundary, or a data migration. Skip this stage for straightforward verified changes. Supply the original requirements, final diff or file scope, and test evidence, keeping the review independent of the implementation agent's conclusions. Reuse an available slot after earlier work completes.

Resolve actionable findings and rerun affected checks. Finish when the integrated result meets the acceptance criteria, reporting remaining limitations. Do not spawn every role as a checklist.
