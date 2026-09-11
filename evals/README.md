# 可重复的编排评估

案例生成和验收只依赖 Python 3.11+ 和本仓库，不需要其他项目、历史对话或第三方 Python 包。一键运行还需要已登录、可用的 Codex CLI；它会实际调用模型并消耗额度。

## 一键运行（推荐）

在已信任的本仓库根目录运行：

```powershell
python evals/run.py bench
```

脚本自动生成六个全新案例，为每个案例启动独立的 `codex exec` 会话，依次完成任务和验收。无需手动开六个任务。结果默认保存在 `work/evals/` 下本轮新目录中，终端会显示结果路径；每次执行都会生成新目录。

Windows 支持原生 `codex.exe` 和 npm 安装的 `codex.cmd`／`codex.ps1`。npm 安装会通过 Node.js 启动同目录下的 Codex 包；无需另行安装原生版本。

查看该目录下的 `summary.md`，即可看到各案例是否通过、耗时和 CLI 报告的 token。`results.json` 保存结构化结果，日志保存原始事件、错误和最终回答。每完成一个案例就更新结果，失败会记录原因并继续后续案例，不自动重试或切换模型。默认每例最多运行 900 秒，Ctrl+C 可中断并保留已产生的结果。

只想先试一个案例：

```powershell
python evals/run.py bench --case slug
```

使用另一份规则快照进行下一轮：

```powershell
python evals/run.py bench --rules D:/temp/rules-A
```

规则来源可以在其他目录；`bench --output` 必须位于本仓库内，使生成的项目配置在已信任仓库中加载。CLI 与桌面任务的显式模型覆盖可能不同，比较时以记录的 CLI 版本、命令和规则快照为准。脚本不修改全局登录或信任配置。

Token 来自 `codex exec --json` 的 `turn.completed.usage`。缺失值保留为空；该事件未保证包含所有子代理消耗，因此报告不能直接当作完整账单，也不自动推算费用、模型请求次数或重复探索次数。[官方非交互模式说明](https://learn.chatgpt.com/docs/non-interactive-mode)

若案例失败，先打开报告里的最终回答和 CLI 日志，区分实现错误与运行环境故障。例如 `CryptUnprotectData failed` 表示本机 Windows 沙箱未能正常启动工具；这种运行不适合拿来判断编排效率。脚本保持 `workspace-write` 权限，不会自动关闭沙箱或修改系统设置。[Windows 沙箱排障](https://learn.chatgpt.com/docs/windows/windows-sandbox)

## 手动运行（可选）

在仓库根目录运行：

```powershell
python evals/run.py list
python evals/run.py prepare all --output D:/temp/orchestrator-eval/run-001
```

输出目录必须不存在。脚本生成每个案例的独立工作目录、`TASK.md`、起始代码以及当前编排配置。每次换一个输出目录，保留之前的结果。不要直接在本仓库修改案例实现。

每个目录还包含 `EVAL_MANIFEST.json`，记录起始任务、代码和规则文件的 SHA-256，便于核对两轮输入。它是初始快照记录，代码完成修改后不应重新生成。还应保留使用的评估包版本；生成目录不包含验收器或参考解。

对每个案例，在对应工作目录开启一个全新 Codex 任务，发送相同入口提示：

```text
使用 $codex-orchestrator，完成 TASK.md 中的任务。
```

让任务自主选择是否委派。不要追加“必须派几个代理”“禁止委派”或告诉它预期路线，这些会干扰所测规则。运行期间只处理真实阻塞；任何人工补充或纠正都记录到结果表。

任务结束后，从原仓库运行验收，案例名称和工作目录使用 `list` 与 `prepare` 的输出：

```powershell
python evals/run.py check slug --workspace D:/temp/orchestrator-eval/run-001/slug
```

对其他案例运行同样的 `check` 命令。验收器留在原仓库，不在被测工作目录内；不要让被测任务修改它。检查通过后再评估日志中的编排行为。

也可以在六个任务分别完成后统一验收：

```powershell
python evals/run.py check all --workspace D:/temp/orchestrator-eval/run-001
```

所有命令返回 JSON；`check` 退出码为 0 表示通过、1 表示失败。刚生成的六个案例应全部失败，这是预期的起始状态。单案例 `prepare slug --output DIR` 直接写入 `DIR`；`prepare all` 才会在输出目录下建立六个案例子目录。

## 案例覆盖什么

| 案例 | 工作类型 | 验收重点 | 编排观察 |
|---|---|---|---|
| slug | 局部修复 | Unicode、分隔符、空结果 | 简单工作是否直接完成 |
| summary | 局部修复 | 空订单、整数金额统计 | 是否引入不必要的委派或检查 |
| investigate-config | 只读调查 | 配置优先级及 false、0、None | 是否返回有依据的结论、主代理是否重复探索 |
| investigate-cache | 只读调查 | 缓存隔离、过滤、过期边界 | 是否隔离调查并集中交付 |
| export | 两个独立模块 | CSV、JSON 输出及输入不变性 | 是否有独立工作可并行、交付后是否复用证据 |
| report | 两个协作模块 | 去重统计、Markdown 渲染 | 接口协调与集成验证是否适量 |

案例不规定子代理数量。调查规模较小时直接完成可能更合理；出现两个模块也不等于必须派工。观察的是委派是否有收益、质量是否保持，而不是凑齐角色。当前案例不包含外部资料研究、浏览器或高风险修改，因此不能验证 researcher、视觉验收或风险审查的效果。

## 比较两版规则

用同一版本的案例和验收器，分别准备 A、B 两组全新工作目录。默认复制当前仓库的规则；也可通过 `--rules` 指定一个包含 `.codex/`、`.agents/skills/codex-orchestrator/` 和 `AGENTS.md` 的本地规则快照：

```powershell
python evals/run.py prepare all --output D:/temp/orchestrator-eval/A-001 --rules D:/temp/rules-A
python evals/run.py prepare all --output D:/temp/orchestrator-eval/B-001 --rules D:/temp/rules-B
```

规则快照应提前保留，不能把修改后的规则当作旧版。普通单版回归不需要旧版快照。A、B 应只改变待评估的编排规则；保持模型、推理强度、工具权限、全局指令及案例内容相同，记录界面显式覆盖和实际可用的角色。不要在一个长任务中连续完成多个案例。

第一轮每案例每版本运行一次；若要判断稳定性，建议各重复三次并交替 A/B 运行顺序。比较每个案例的中位数，同时保留所有失败与异常，不能只挑最好的一次。样本少时只报告观察结果，不承诺节省比例。

## 记录和判定

复制 `results.csv`，每次案例运行填一行。空白表示未采集，不等于零。token 必须包含主代理和所有子代理；缓存输入是输入的子集，不能再与总输入相加。表中使用非缓存输入、缓存输入、输出三项。多模型费用按各模型实际计费规则分别计算后汇总；不知道价格就留空，不能把累计 token 当作费用。

完整成本和协调指标需要从本次任务及子代理的使用记录采集。一键报告已记录验收、耗时和 CLI 提供的 usage；不读取历史会话，也不将不完整的 usage 当作总费用。没有完整 token 数据时，仍可完成质量和协调行为评估；不能据此宣称费用下降。

| 指标 | 口径 |
|---|---|
| acceptance_pass | 独立 `check` 是否通过；同时人工查看是否绕过验收或修改了规则 |
| human_corrections | 为完成任务而追加的纠正次数，记录内容；初始提示不算 |
| root_requests / child_requests | 模型请求次数，分别统计；工具调用不等于模型请求 |
| children | 本次启动的子代理数量 |
| elapsed_seconds | 从提交任务到交付的墙钟时间；标注人工等待、服务故障 |
| coordination_messages | 主子代理之间发送的协调消息次数 |
| short_waits | 超时设置不超过 10 秒的代理等待调用；事件提前唤醒不算短等待 |
| duplicate_explorations | 主代理重复调查已委派范围且无阻塞、接口变化或求助理由的次数，附日志位置 |
| redundant_checks | 对未受后续修改影响、已有充分通过证据的范围重复检查次数；失败重跑和新增集成检查不算 |

先判断验收通过率和人工纠正是否退步，再比较成本和耗时。失败运行也计入总成本。行为指标用于解释原因，不单独合成为一个“效率分”：少派代理或少跑检查本身不代表更好。

- 质量保持、协调减少、成本下降：支持继续使用新版。
- 行为未变化：检查规则是否加载，以及是否受其他指令影响。
- 行为变化、成本未下降：协调可能不是当前案例的主要消耗。
- 成本下降、验收退步：检查委派或验证边界是否收得过紧。

固定案例会形成熟悉效应，因此不要把参考实现放进被测目录或沿用已经完成案例的任务上下文。案例升级后重新跑两组，不能直接与旧案例分数混比。

## 测试评估工具本身

```powershell
python -m unittest discover -s evals -p "test_*.py"
python scripts/validate.py
```

这些检查验证生成器和验收器，不证明真实模型已遵循编排规则。真实评估必须完成前述新任务运行。
