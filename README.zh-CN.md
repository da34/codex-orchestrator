# Codex Orchestrator

[English](README.md) | **简体中文**

为 Codex 提供按需多代理编排，并提供两套预设：默认的 **Pro** 拓扑和 **Plus** 拓扑。两套预设使用相同的五个具名角色，仅在需要时由 Astra 进行独立审查。

本仓库提供代理配置、编排技能和项目指令，适合能够拆分为明确子任务的开发工作。简单任务由主代理直接完成，独立工作可以并行，最终由主代理整合并验证结果。

## 工作方式

```text
                         主代理
                  定范围、决策、整合、验证
                           |
                         按需分派
       +-----------+----------+------------+
       |           |          |            |
   explorer     worker      tester     researcher
    代码调查       实现        独立且        资料查询
                与相关测试    范围明确的测试
       |           |          |            |
       +-----------+----------+------------+
                           |
                          主代理
                       整合与验证
                           |
                 reviewer，仅在需要时
                       独立审查
```

主代理可以向四个执行角色分派任务：`explorer`、`worker`、`tester` 和 `researcher`。`tester` 用于有价值且范围明确的独立测试；它不是必经的流水线阶段，`worker` 仍负责自己改动的相关测试。第五个具名角色 `reviewer` 仅在整合和验证后按明确要求使用，或在存在值得关注的剩余风险时使用。

| 设置 | 默认 Pro 预设 | Plus 预设 |
|---|---|---|
| 来源 | `.codex/` | `presets/plus/.codex/` |
| 主代理 | `gpt-6-astra` · `medium` | `gpt-5.6-luna` · `max` |
| 通用子代理默认值 | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` |
| 并发子代理数 | 4，不含主代理 | 4，不含主代理 |

| 具名角色 | 默认 Pro 预设 | Plus 预设 | 职责 |
|---|---|---|---|
| explorer | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | 调查范围明确的代码问题 |
| worker | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | 实现修改并运行相关测试 |
| tester | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | 在有价值时运行范围明确的独立测试 |
| researcher | `gpt-5.6-luna` · `max` | `gpt-5.6-luna` · `medium` | 回答聚焦的文档或资料问题 |
| reviewer | `gpt-6-astra` · `low` | `gpt-6-astra` · `low` | 按需独立检查整合后的修改 |

两套预设都将子代理并发上限设为 4，不含主代理；实际并行数量仍受 Codex 运行时和会话限制。审查在整合与验证后复用空闲名额，依赖调查结论的工作会等待结果。按需分派旨在控制协调开销，不保证每个任务都能节省 Token。

## 环境要求

- 支持子代理、自定义代理配置和技能的 Codex 环境。
- 可使用配置中的模型及思考强度，或自行配置兼容的替代模型。
- 使用 researcher 时，Codex 需要有可用的资料查询工具。
- 仅在运行配置校验脚本时需要 Python 3.11 或更新版本。

平台配置细节见 [OpenAI 子代理文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)。

## 安装

克隆仓库：

```sh
git clone https://github.com/da34/codex-orchestrator.git
```

选择一套预设，将其内容合并到目标项目的 `.codex/` 目录：

| 预设 | 要合并的来源 | 目标位置 |
|---|---|---|
| 默认 Pro | `.codex/config.toml` 和 `.codex/agents/` | `<目标项目>/.codex/` |
| Plus | `presets/plus/.codex/config.toml` 和 `presets/plus/.codex/agents/` | `<目标项目>/.codex/` |

然后合并两套预设共用的组件：

| 组件 | 用途 |
|---|---|
| `.agents/skills/codex-orchestrator/` | 两套预设共用的编排技能 |
| `AGENTS.md` | 两套预设共用的项目指令 |

两套预设包含相同的五个具名角色、角色指令和分派方式，模型与思考强度的区别见上表。不要同时合并两套预设配置。Codex 不会自动检测订阅方案或选择预设。

已有项目应先备份重名文件，再合并内容。保留原有 `AGENTS.md` 规则、技能，以及模型服务商、认证、MCP 和权限设置。存在 `[agents]` 表时，将所选预设的配置键合并到该表中，避免重复定义。

安装后，在已信任的目标项目中开启新的 Codex 任务。仅克隆仓库不会完成安装。本仓库采用项目级配置，既不提供安装脚本，也不会自动检测订阅方案。

## 使用

通过技能名称提交具体任务：

```text
$codex-orchestrator
为发票页面添加 CSV 导出，遵循现有导出约定，
并验证列顺序、转义和空结果。
```

也可以在任务中明确要求独立审查：

```text
$codex-orchestrator
在保持行为不变的前提下重构权限检查。
整合和验证后，请独立审查访问控制是否出现回归。
```

仅在主代理能并行推进独立工作，或范围明确的调查能隔离大量探索并返回精简证据时委派。任务复杂本身不足以构成委派理由。执行期间，主代理推进自己的工作，无独立工作时采用较长的事件等待，在交付时集中检查最终改动。协调消息聚焦阻塞、接口变化和完成。

worker 负责所属改动的检查，回报命令与实际结果；主代理复用这些证据，补充集成边界和未覆盖验收项的检查。仅在后续改动影响结果、证据不足或发现问题时重跑，项目必需检查仍须完成。当单独工作确有价值时，可以由 tester 独立验证范围明确的风险或验收项，但测试不是必经的交接阶段。除非明确要求或存在值得独立检查的剩余风险，否则可以跳过 reviewer。

## 自定义

- 在目标项目的 `.codex/config.toml` 中调整所选预设的主模型和思考强度。
- 在目标项目对应的 `.codex/agents/*.toml` 中调整具名角色的模型、强度、权限或指令。具名角色固定了这些值，修改通用子代理默认值不会改变它们。
- 在 `codex-orchestrator` 技能中调整分派和审查条件。
- 通过 `agents.max_concurrent_threads_per_session` 调整配置中的子代理并发上限；实际仍受运行时限制。

如果同时定制两套预设，请保持角色指令一致。explorer、researcher 和 reviewer 使用只读权限，worker 和 tester 使用 workspace-write。实际执行仍受父会话权限约束。界面或项目中的显式覆盖可能改变生效配置，已有会话可能需要重新启动以加载修改。

## 校验与贡献

在本仓库中运行配置检查：

```sh
python scripts/validate.py
```

GitHub Actions 会在 push 和 pull request 时运行相同检查，验证 TOML、两套预设矩阵、五个具名角色、权限、并发数量、预设间一致的角色描述与指令，以及指令文件是否存在。检查不会调用模型，也不会验证运行时的编排行为。

评估实际编排行为，运行 `python evals/run.py bench`，由固定版本 Harbor 在 Docker 中执行六个独立任务案例。需要 Python 3.11+、uv、Docker Linux 引擎和 Codex 认证；加 `--self-test` 可不调用模型验证标准答案与空操作基线。详见 [可重复评估包](evals/README.md)。usage 不保证包含全部子代理消耗，通过验收也不代表 Token 已减少。

欢迎提交 Issue 和 pull request。报告问题时，请提供相关 Codex 环境、配置、任务和实际表现，并移除密钥等敏感信息。调整编排结构时，请同步修改配置、`scripts/validate.py` 中的预期值和中英文 README；互不相关的修改请分别提交。

## 致谢

架构灵感来自 [donvito/codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator/)。

## 开源协议

[MIT](LICENSE) © 2026 da34。
