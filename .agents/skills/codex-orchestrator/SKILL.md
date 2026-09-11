---
name: codex-orchestrator
description: Coordinate coding and investigation work with the user's Astra, Sol, and Luna agent topology. Use for tasks with bounded implementation, code exploration, documentation research, or a requested independent review; handle simple work directly.
---

# On-demand orchestration

Use the root for task decomposition, decisions, integration, and verification. The model and effort assignments are defined in `.codex/config.toml` and `.codex/agents/*.toml` at the installed project root. Read the relevant role file before dispatch; use its configured model, effort, and instructions. If the active parent model differs from the configured root, state the mismatch rather than claiming to have changed the running model.

## Delegate useful work

Complete simple questions and small self-contained edits directly. Delegate only when the root has useful independent work to advance in parallel, or a bounded investigation can keep substantial exploration out of the root's context and return concise evidence. Task complexity alone is insufficient. Before dispatch, identify the acceptance criteria and the work delegation saves the root. Spawn only needed roles:

- `explorer` for a bounded question about existing code or behavior.
- `worker` for implementation and relevant tests.
- `researcher` for a focused external lookup.

When implementation depends on exploration or research, wait for those findings before assigning the dependent work. Give each assignment its question or acceptance criteria, necessary context, interface constraints, file ownership when writing, and expected verification evidence. Ask for coordination reports on blockers, interface changes, or completion. Keep at most three children running and avoid overlapping writes.

Use native subagents rather than creating user-visible standalone tasks. When the spawn tool accepts explicit model and reasoning overrides, pass the role's values. If full-history inheritance prevents model overrides, use a bounded context fork or a fresh context with the required task evidence. Report unavailable models or tools; continue useful root work without silently claiming the requested topology ran.

## Coordinate at handoffs

While a child works, the root stays within its separate scope. Inspect the child's completed diff at handoff rather than repeatedly reading unfinished files or duplicating its investigation. Intervene when a dependency is blocked, an interface changes, or the child requests help.

When no independent work remains, use a long event-driven wait within the tool and session limits instead of short polling or status requests. Keep required user progress updates separate from child coordination. Consolidate feedback at handoff into one actionable response where possible.

## Integrate and verify

Wait for required results, inspect the final changes, and reconcile issues against the acceptance criteria. The worker owns checks for its assigned changes and reports exact commands, actual results, and unverified behavior. The root reuses that evidence and adds checks for integration boundaries or uncovered acceptance criteria. Rerun covered checks only when subsequent changes affect them, evidence is insufficient, or a finding warrants it; complete required project checks. A separate tester is not part of this topology.

## Review only when needed

After integration and verification, use a fresh `reviewer` when the user requests it or material residual risk warrants independent inspection, such as a cross-module change with uncertain interactions, a security boundary, or a data migration. Skip this stage for straightforward verified changes. Supply the original requirements, final diff or file scope, and test evidence, keeping the review independent of the implementation agent's conclusions. Reuse an available slot after earlier work completes.

Resolve actionable findings and rerun affected checks. Finish when the integrated result meets the acceptance criteria, reporting remaining limitations. Do not spawn every role as a checklist.
