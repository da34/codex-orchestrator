# Codex project instructions

Use the `codex-orchestrator` skill for complex coding tasks when its description matches the work.

The root makes architectural decisions, breaks down the task, integrates results, and verifies completion.
Delegate bounded code exploration to explorer, implementation and tests to worker, and focused research to researcher.
Use tester for bounded independent acceptance or regression testing when needed.
Request an independent reviewer after integration and verification only when needed.
Handle trivial work directly. Parallelize independent tasks with clear file ownership for each writing agent.
Follow the skill and configured agent profiles for model selection and reasoning effort.
Explicit user instructions take precedence over these defaults.
