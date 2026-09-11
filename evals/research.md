# Agent 编排测评研究笔记

研究日期：2026-09-11。资料以 Harbor/Terminal-Bench 的 `main` 和 Codex 官方当前文档为准；这些链接没有固定提交号，实际测评必须另外记录 Harbor commit、数据集版本、Codex CLI 版本和模型的完整 ID。`latest` 适合试跑，不适合 A/B 对照。

## 网上成熟测评的共同结构

Harbor 把一次评估拆成四个可独立核对的部分：任务说明、运行环境、验证脚本和可选的参考解。一次 trial 是一个 agent 在一个 task 上的一次执行；重复 trial 组成 job。任务应在全新的环境中运行，验证脚本只根据最终状态给 reward。Harbor 的适配指南还要求先验证 oracle，再做 parity；否则失败可能来自适配或环境，而不是 agent 能力。

Terminal-Bench 的公开运行示例先用 oracle 重复 5 次确认沙箱和任务可靠，再运行指定 agent/model。Harbor 的适配流程则建议先在双方各跑 5–10 个任务的 sanity check，再各跑一次完整集，最后对双方各跑 3 次；配置、安装脚本、启动命令、工具、提示词、超时和模型 ID 都要保持一致。

Harbor 的排障顺序很关键：先处理崩溃、超时、镜像构建和 verifier 错误；这些运行不能当作低分。环境日志干净后，才通过 agent trajectory 区分真实能力失败和路径、测试输出等 harness 错误。小数任务出现高方差时，单独重复该任务 5–10 次，避免为调查一个噪声任务而重跑整个集。

## 套到当前本地 bench 的最小流程

建议把每个案例的一次运行分成下面三道门，任何前置门失败都停止这一批：

1. **环境预检**：先检查 Docker Linux 引擎，再运行 Harbor oracle/nop 基线，验证容器构建、文件注入和验收链路；通过后用真实案例检查模型链路。无模型自检不能证明认证、模型或子代理工具健康。
2. **验证器预检**：用未修改的 fixture 跑验证器，确认预期会失败；再用参考解（oracle）确认预期会通过。若任务是确定性的，一次可发现路径错误；若有波动，按 5 次重复做稳定性检查。
3. **agent trial**：只有前两道门通过后，才把 agent 的最终验证结果记作实现质量。每次使用新的工作目录和相同的初始快照，不能复用前一次已经被修改的目录。

Harbor 源码提供 `oracle` 和 `nop` 两个实用 agent。`nop` 不修改环境，可作为 floor：未修改的 fixture 被 no-op 判通过，说明 verifier 没有真正检查任务结果；oracle 失败则先修 task/environment/verifier。no-op 是适合本项目的校验基线，并非编排策略本身的质量分。

迁移前运行 `work/evals/20260911-103913-162174/summary.md` 显示 CLI 退出码为 0，但六个案例的独立行为检查失败。这类结果只有在启动器和 verifier 预检通过后，才能归入 agent/任务验收失败。主代理同时定位到 WindowsApps 商店版 PowerShell 在相同 CLI、sandbox、cwd 下出现 `CreateProcessAsUserW`，便携版 PowerShell 可以启动；带有这类错误的运行应标成 `environment_error`，从实现分母中排除并单独报告环境可用率。`CryptUnprotectData`、CLI 不存在、认证失败也属于同一层。

| 发生阶段 | 例子 | 统计处理 |
| --- | --- | --- |
| launcher/auth/sandbox | `CreateProcessAsUserW`、`CryptUnprotectData`、CLI 或认证不可用 | `environment_error`；停止批次，不算 agent 低分 |
| environment/build | 依赖、路径、权限、镜像构建或 healthcheck 失败 | `environment_error`；先修环境 |
| verifier/fixture | 验证器自身缺依赖或路径错误、oracle 不通过 | `harness_error`；先修任务或验证器 |
| agent execution | 环境健康但 agent 超时、返回失败或未生成要求的答案文件 | agent failure；可计入质量失败 |
| acceptance | agent 正常结束，独立验证器返回失败 | implementation failure |
| telemetry | JSONL 截断、子 agent usage 未采集 | `measurement_incomplete`；不能作成本结论 |

## CLI 和 agent adapter 的隔离

每次 A/B 运行应记录并固定：规则快照 hash、任务 fixture hash、目录布局、Codex CLI 版本、模型完整 ID、推理强度、sandbox、相关环境变量、工具/MCP、系统提示、超时和实际启动命令。A/B 只替换待测编排规则；不要让一版读取另一版的会话或已改工作目录。服务端缓存不一定能隔离，应交替运行并记录命中量；不要保存环境变量中的秘密值。

官方 Codex 非交互文档提供配置控制、显式 sandbox 和 JSONL 输出。本项目继续保留现有认证、provider 和执行安全规则；若将来采用独立配置目录，需要明确提供这些配置，不能简单清空后就声称实现了隔离。`--json` 会输出 `thread.started`、`turn.completed`、`turn.failed`、`error` 和命令/文件变更等事件；应保存原始流，而不是只保存最终回答。

Harbor 的 Codex adapter 采用相同的隔离思路：以原生配置或内联配置为基础，叠加本次运行的明确输入，再把生效配置写入 trial 内的 `$CODEX_HOME/config.toml`，同时保存原生 rollout/trajectory。本项目现直接使用该 adapter；只提供规则快照和选中的连接配置，不复制宿主机会话历史或 MCP 配置。认证文件仍应按官方文档作为秘密处理。

## 重复 trial、质量和成本

先看质量，再看成本。每个 trial 至少记录：

- `acceptance_pass`、`human_corrections` 和错误分类；
- root/child 的模型请求数、子 agent 数、协调消息和等待；
- 每个 session 的非缓存输入、缓存输入、输出 token、实际费用（若账单可得）；
- 总耗时及启动器、agent、verifier 各阶段耗时；
- 规则、任务、模型、CLI、sandbox 和配置的版本/hash。

Codex 官方示例在 `turn.completed.usage` 中给出 input、cached input、output 三项。缓存输入是输入的一部分，不能再加到总输入；如果子 agent 是独立 session，必须把它们的 JSONL/usage 一并采集，否则主 agent 的 usage 只是部分成本。实际账单或 provider usage 是费用的最终依据。

当前六个案例适合作为 smoke/regression gate：它们能发现规则是否加载、启动是否健康、简单任务质量是否退步。它们还不足以证明编排成本下降，尤其不能从单次六案例运行推出固定节省比例。要测“是否值得委派”，应加入至少两个真正独立的模块/文件工作，并让每个模块有独立验收，再加一个需要集成的任务；不要用“必须派几个子 agent”来制造分数。对 A、B 交替运行相同的新快照，每版每案例先跑一次，稳定性结论至少重复 3 次；高方差案例单独跑 5–10 次。失败的环境运行要保留，但不和实现失败混入同一个质量分母。

Harbor parity 文档用每次运行的原始分数作为依据，报告均值 ± sample SEM（至少 2 次，3 次以上更合适），并要求双方的运行分数范围重叠。对当前小型本地 A/B，更稳妥的是同时报告逐案例原始结果、配对差值/中位数、环境错误率和完整成本；不要把“少派代理”或“少跑检查”单独合成为效率分。

## 是否迁移 Harbor

Harbor 的价值在于每个 trial 的环境、验证器、轨迹和结果有固定边界，并可通过 Docker 或云沙箱并行扩展；这正适合以后需要更多任务、多个 agent/model 或跨机器复现时使用。迁移需要准备任务目录、Dockerfile/镜像、测试与 reward 脚本、Harbor/uv 依赖、agent adapter、认证和环境提供商。Terminal-Bench 的公开示例还使用 Modal，并以高并发运行；这会带来镜像构建、网络、账户和费用成本。

本项目现按用户确定的方向迁移到 Harbor 0.22.0：保留六个任务及独立判分，替换自制执行器，用 Docker 作为隔离边界。迁移后的有效性仍需由 oracle 全通过、nop 全不通过和真实 Codex 执行分别验证。Harbor 内置 Codex adapter 在隔离容器中不嵌套 Codex 沙箱；这不修改宿主机沙箱配置。

## 资料与适用版本

- [Harbor Adapters（官方适配与 parity 指南，`main`）](https://github.com/harbor-framework/harbor/blob/main/docs/content/docs/datasets/adapters.mdx)：任务四要素、oracle、配置对齐、错误排查、重复运行和 SEM。
- [Terminal-Bench（维护仓库 README，`main`）](https://github.com/harbor-framework/terminal-bench/blob/main/README.md)：oracle 5 次预检、Harbor/Modal 的公开运行方式；命令中的 `@latest` 是浮动版本。
- [Harbor Codex adapter 与 no-op agent（`main` 源码）](https://github.com/harbor-framework/harbor/blob/main/src/harbor/agents/installed/codex.py)、[nop.py](https://github.com/harbor-framework/harbor/blob/main/src/harbor/agents/nop.py)：配置写入 trial 内 `$CODEX_HOME`、轨迹采集和 no-op 行为。
- [Codex 官方非交互模式文档](https://learn.chatgpt.com/docs/non-interactive-mode)：`codex exec`、显式 sandbox、`--ignore-user-config`/`--ignore-rules`、JSONL 事件和 usage；页面没有锁定 CLI 版本，需在运行时记录 `codex --version`。

仍有三点未由这些资料确定：Codex root turn 的 usage 是否涵盖本次编排启动的全部 child session、WindowsApps PowerShell 的具体系统修复路径、以及当前六个自制案例在 oracle 预检后的真实通过率。前两项应以本机日志/账单为准，后一项应先做 oracle/no-op 预检再评估。
