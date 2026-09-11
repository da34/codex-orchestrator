"""Render detailed summaries from saved Harbor results without invoking a model."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import median


def _seconds(data: dict | None) -> float | None:
    if not data or not data.get('started_at') or not data.get('finished_at'):
        return None
    return (datetime.fromisoformat(data['finished_at'].replace('Z', '+00:00')) -
            datetime.fromisoformat(data['started_at'].replace('Z', '+00:00'))).total_seconds()


def _sum(values: list) -> float | None:
    # Missing measurements must not be silently treated as zero.
    return sum(values) if values and all(v is not None for v in values) else None


def _fmt(value: float | None, digits: int = 0) -> str:
    return '—' if value is None else f'{value:,.{digits}f}'


def _tools(path: Path) -> tuple[int | None, int | None]:
    if not path.is_file():
        return None, None
    data = json.loads(path.read_text(encoding='utf-8'))
    calls = [call for step in data.get('steps', []) for call in (step.get('tool_calls') or [])]
    return len(calls), sum(call.get('function_name', '').split('.')[-1] == 'spawn_agent' for call in calls)


def render_report(output: Path) -> str:
    lines = ['# Harbor 详细测评报告', '',
             '每个案例的 reward 是二元验收结果：1 为通过，0 为未通过；不是综合能力分数。', '']
    for job_dir in sorted((output / 'jobs').iterdir()) if (output / 'jobs').is_dir() else []:
        if not job_dir.is_dir():
            continue
        job_path = job_dir / 'result.json'
        job = json.loads(job_path.read_text(encoding='utf-8')) if job_path.is_file() else {}
        rows = []
        for path in sorted(job_dir.glob('*/result.json')):
            trial = json.loads(path.read_text(encoding='utf-8'))
            usage = trial.get('agent_result') or {}
            reward = ((trial.get('verifier_result') or {}).get('rewards') or {}).get('reward')
            exception = trial.get('exception_info')
            tool_calls, delegations = _tools(path.parent / 'agent/trajectory.json')
            rows.append({'trial': trial, 'path': path, 'usage': usage, 'reward': reward,
                         'exception': exception, 'seconds': _seconds(trial),
                         'agent_seconds': _seconds(trial.get('agent_execution')),
                         'tools': tool_calls, 'delegations': delegations})
        expected = job.get('n_total_trials', len(rows))
        passed = sum(r['reward'] == 1 and not r['exception'] for r in rows)
        errors = sum(bool(r['exception']) for r in rows)
        measured = [r['agent_seconds'] for r in rows if r['agent_seconds'] is not None]
        totals = {key: _sum([r['usage'].get(key) for r in rows]) for key in
                  ('n_input_tokens', 'n_cache_tokens', 'n_output_tokens', 'cost_usd')}
        inputs, cached = totals['n_input_tokens'], totals['n_cache_tokens']
        noncached = inputs - cached if inputs is not None and cached is not None else None
        hit_rate = cached / inputs * 100 if inputs and cached is not None else None
        models = sorted({(r['trial'].get('agent_info', {}).get('model_info') or {}).get('name', '未记录') for r in rows})
        lines += [f'## {job_dir.name}', '', f"模型：{', '.join(models) or '未记录'}。", '',
                  '| 汇总指标 | 数值 |', '| --- | --- |',
                  f'| 验收通过 / 计划运行 | {passed} / {expected} |',
                  f'| 已记录结果 / 异常结果 | {len(rows)} / {errors} |',
                  f'| 通过率（计划运行作分母） | {_fmt(passed / expected * 100 if expected else None, 1)}% |',
                  f'| 整轮墙钟时间（秒） | {_fmt(_seconds(job), 2)} |',
                  f'| 代理执行时间合计（秒） | {_fmt(_sum([r["agent_seconds"] for r in rows]), 2)} |',
                  f'| 单次代理执行中位数（秒；有效样本 {len(measured)}） | {_fmt(median(measured) if measured else None, 2)} |',
                  f'| 输入 Token（含缓存） | {_fmt(inputs)} |',
                  f'| 缓存输入 Token | {_fmt(cached)} |',
                  f'| 非缓存输入 Token | {_fmt(noncached)} |',
                  f'| 缓存输入占比 | {_fmt(hit_rate, 2)}% |',
                  f'| 输出 Token | {_fmt(totals["n_output_tokens"])} |',
                  f'| 已记录工具调用 / spawn_agent 调用 | {_fmt(_sum([r["tools"] for r in rows]))} / {_fmt(_sum([r["delegations"] for r in rows]))} |',
                  f'| 框架估算费用（USD，非实际账单） | {_fmt(totals["cost_usd"], 4)} |', '']
        if job_dir.name == 'nop':
            matched = sum(r['reward'] == 0 and not r['exception'] for r in rows)
            lines += [f'空操作基线要求 reward=0；符合预期：{matched}/{expected}。此处 0% 验收通过率是预期结果。', '']
        lines += ['### 每次运行', '',
                  '| 案例 / 运行 | 结果 | 总耗时 s | 代理执行 s | 输入（含缓存） | 缓存输入 | 输出 | 工具 / 委派调用 | 估算 USD |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        for row in rows:
            trial, usage = row['trial'], row['usage']
            status = ('异常' if row['exception'] else '通过' if row['reward'] == 1 else '未通过' if row['reward'] == 0 else '未评分')
            link = row['path'].relative_to(output).as_posix()
            name = trial.get('trial_name', row['path'].parent.name)
            lines.append(f'| [{name}]({link}) | {status} | {_fmt(row["seconds"], 2)} | {_fmt(row["agent_seconds"], 2)} | {_fmt(usage.get("n_input_tokens"))} | {_fmt(usage.get("n_cache_tokens"))} | {_fmt(usage.get("n_output_tokens"))} | {_fmt(row["tools"])} / {_fmt(row["delegations"])} | {_fmt(usage.get("cost_usd"), 4)} |')
        lines += ['', '### 耗时拆分（秒）', '', '| 运行 | 环境准备 | 代理安装 | 代理执行 | 验收 |', '| --- | --- | --- | --- | --- |']
        for row in rows:
            trial = row['trial']
            timings = ' | '.join(_fmt(_seconds(trial.get(key)), 2) for key in ('environment_setup', 'agent_setup', 'agent_execution', 'verifier'))
            lines.append(f'| {trial.get("trial_name", row["path"].parent.name)} | {timings} |')
        lines.append('')
    payload_path = output / 'results.json'
    if payload_path.is_file():
        payload = json.loads(payload_path.read_text(encoding='utf-8'))
        if payload.get('errors'):
            lines += ['## 运行错误', '', *[f'- {error}' for error in payload['errors']], '']
    lines += ['## 指标口径与限制', '',
              '- “—”表示未记录；缺失测量不会按零计入合计。进行中的运行不计算完整耗时。',
              '- 输入 Token 已包含缓存输入，两者不能相加。费用为 Harbor 的估算，不能替代供应商账单。',
              '- 工具和委派次数来自各 trial 的 ATIF 轨迹，委派只统计已记录的 spawn_agent 调用；不等于成功创建的子代理数，也不保证包含子代理内部调用。',
              '- Token 统计也不保证覆盖全部子代理。未采集人工纠正、重复探索、冗余验证及完整模型请求次数，不能据此推断这些指标为零。',
              '- 整轮墙钟时间与各阶段合计可能不同：并行执行、清理及框架开销不在相同口径内。',
              '- 六个固定小任务的一次通过只能证明本轮功能验收；评估是否更高效，应对旧/新规则使用相同模型与案例重复运行，比较质量、耗时和成本。', '']
    return '\n'.join(lines)


def write_report(output: Path) -> Path:
    target = output / 'summary.md'
    target.write_text(render_report(output), encoding='utf-8')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='existing evaluation run directory')
    args = parser.parse_args()
    if not (args.output / 'jobs').is_dir():
        parser.error('directory must contain saved Harbor jobs')
    print(write_report(args.output.resolve()))
