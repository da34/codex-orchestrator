# 按图片编排的 Codex 配置包

[English](README.md) | **简体中文**

用于长期维护用户指定的 Codex 多代理编排。克隆本仓库不会自动安装配置，也不会修改当前 Codex 全局设置。

| 阶段 / 角色 | 模型 | 思考强度 | 工作 |
|---|---|---|---|
| 主代理 | GPT-6 Astra | medium | 拆解、调度、整合、验证 |
| explorer | GPT-5.6 Luna | max | 有明确范围的代码调查 |
| worker | GPT-5.6 Sol | high | 实现与测试 |
| researcher | GPT-5.6 Luna | max | 聚焦的资料查询 |
| reviewer（按需） | GPT-6 Astra | xhigh | 整合验证后的独立审查 |

最多同时运行三个子代理，加上主代理共四个。独立审查复用已完成工作的名额。简单任务由主代理直接处理；只有独立工作值得拆分时才启动对应角色。依赖调查结果的实现会等待结果，不强行并行。

## 文件结构

- `.codex/config.toml`：主代理与通用子代理默认值、并发上限。
- `.codex/agents/*.toml`：四个具名角色的模型、强度、职责和权限。
- `.agents/skills/cost-efficient-orchestrator/SKILL.md`：调度与验收规则。
- `AGENTS.md`：项目入口，指向上述技能。

## 日后安装到项目

1. 将包中的 `.codex` 和 `.agents` 合并到目标项目根目录。目标项目已有同名文件时，先备份并合并内容。
2. 将本包 `AGENTS.md` 的编排段落合并到项目原有 `AGENTS.md`，保留原有项目规则。
3. 对于已有 `.codex/config.toml`，合并模型、思考强度及 `[agents]` 中的键，不要重复创建同名 TOML 表。保留原来的模型服务商、认证、MCP 和其他配置。
4. 在已信任的目标项目中开启新的 Codex 任务。已有会话的模型和工具配置不保证热更新；项目或界面中的显式覆盖也可能改变实际模型。
5. 可以明确调用：`$cost-efficient-orchestrator 帮我实现……，按需使用子代理。`

此包按项目布局提供，不附带自动安装脚本。角色显式固定模型和强度，调整通用子代理默认值不会改变具名角色。研究角色还需要环境提供可用的资料查询工具。模型名称按当前会话支持的标识配置，目标环境仍须提供这些模型。

只读角色：explorer、researcher、reviewer。worker 使用 workspace-write，实际执行仍受父会话权限约束。根配置没有指定或覆盖现有审批、认证和服务商设置。

## 验证范围

配置包已做 TOML 解析、角色映射、技能 frontmatter 和打包完整性检查。没有安装到当前 Codex，也没有启动模型请求做端到端运行测试。按需分工旨在控制开销，实际 Token 用量取决于任务与上下文。

## 持续迭代

修改配置后，使用 Python 3.11 或更新版本执行：

```sh
python scripts/validate.py
```

每次 push 和 pull request 都会通过 GitHub Actions 自动校验 TOML、模型与强度、角色权限、并发数量和指令文件是否存在。此校验不调用模型，不需要 API 密钥，也不证明模型实际遵循全部调度规则。

角色职责在 `.codex/agents/` 中维护，调度行为在技能文件中维护。如果有意调整图片中的拓扑，同时更新配置、`scripts/validate.py` 的预期值和中英文 README；验证脚本保留预期值是为了检测意外的模型替换。使用功能分支和 pull request 记录修改，Issue 可用于收集实际运行中的问题与用量数据。

## 参考

架构参考：[donvito/codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator/)。配置与说明为按用户图片重新编写；主要差异是 Sol/high 负责实现和测试，Luna/max 负责探索与查询，Astra/medium 统筹，Astra/xhigh 仅按需审查，没有固定 tester 阶段。

配置依据：[OpenAI 子代理文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)。
