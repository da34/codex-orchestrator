# 可重复的编排评估

六个独立案例由 **Harbor 0.22.0 + Docker Linux 容器**运行，使用内置 Codex adapter（CLI 固定为 0.149.1）。每次生成新任务快照和容器，不依赖其他项目或上一次运行。六个小案例用于回归检查，不能单独证明复杂编排的成本收益。

## 一键运行

首次需要 Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和已启动 Linux 引擎的 Docker Desktop。Harbor 由 uv 自动安装固定版本；首次构建镜像需要网络和时间。模型认证沿用本机 Codex 的 auth.json 或 OPENAI_API_KEY，以及当前选中的 provider 配置。

```powershell
python evals/run.py bench
```

自动跑完六项，终端给出 `work/evals/<本轮>/summary.md`。底层使用 [Harbor 本地数据集入口](https://www.harborframework.com/docs/getting-started)，不再维护自制 Codex 进程执行器。旧 `--codex`、`--windows-sandbox`、`--powershell` 参数已移除。

- `summary.md`：通过率、逐项结果、整轮和各阶段耗时、输入/缓存/输出 Token、缓存占比、工具与委派调用次数、框架估算费用。缺失指标显示为“—”。
- `jobs/codex/result.json`：Harbor 汇总。
- `jobs/codex/<trial>/result.json`：环境异常、执行时间、模型 usage。
- `jobs/codex/<trial>/agent/`：执行日志和轨迹。
- `tasks/`：本轮任务、规则快照、外置验收器和参考解。

默认每例执行上限 900 秒、顺序运行、不重试；失败运行也保留。Docker 未启动时在调用模型前退出。Harbor 中 reward=1 表示通过，reward=0 表示未通过；环境异常不能当成正常评分。

框架在独立容器内运行代理，隔离边界是 Docker；内置 Codex adapter 使用容器内不再嵌套沙箱的执行方式。不会关闭宿主机 Windows 沙箱或修改全局 Codex 配置，也不把宿主机项目整体或 Docker socket 挂载给被测代理；Harbor 仅挂载本轮日志目录。

仅把选中的模型连接和项目规则传给容器，不复制宿主机 MCP 配置。含凭据的原生配置使用临时文件，结束后删除，结果中只记录临时路径；重新运行会重新读取本机认证。结果仍可能包含任务内容，应按本地工作日志保管。

## 更新已有运行的报告

无需重新运行模型，直接从保存的 Harbor 日志重新生成详细摘要：

```powershell
python evals/report.py work/evals/20260911-114651-917167
```

只更新指定运行目录的 `summary.md`，保留原始 JSON 和轨迹。工具次数取各 trial 的 ATIF 轨迹，不等于模型请求次数；`spawn_agent` 调用次数也不保证是成功创建的子代理数。若委派次数为 0，本轮结果不能用于证明多代理协作收益。

## 不调用模型的自检

```powershell
python evals/run.py bench --self-test
```

Harbor 分别运行 `oracle` 和 `nop`：要求六个标准答案全部 reward=1，六个空操作全部 reward=0，且没有环境异常。这个命令通过说明任务和验收器接通，不代表 Codex 有效。验收器及答案不进入代理镜像构建目录，分别在验证和 oracle 阶段才注入。

## 单项与重复测评

```powershell
python evals/run.py bench --case slug
python evals/run.py bench --attempts 3
python evals/run.py bench --rules D:/temp/rules-A --attempts 3
```

`--model` 可显式覆盖根模型；默认取规则快照的 `.codex/config.toml`。子代理配置保持快照中的设置。A/B 应使用相同案例、模型、CLI 和认证环境，只改变规则；同时比较通过率、耗时和完整成本。Harbor 的 token 汇总不保证覆盖全部 Codex 子代理，缺失值不是零；`cost_usd` 是框架估算，不等于自定义供应商的实际账单，不能直接据此宣称省钱。内置 adapter 的结果可能将 provider 标为 `openai`，该标签不能用于判断实际连接地址；实际连接仍来自本轮继承的 Codex provider 配置。

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
