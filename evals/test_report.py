import json
import tempfile
import unittest
from pathlib import Path

from report import render_report


class ReportTests(unittest.TestCase):
    def test_metrics_include_failed_runs_and_do_not_double_count_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job = root / 'jobs/codex'
            for i, reward in enumerate([1, 0]):
                trial = job / f'case-{i}'
                (trial / 'agent').mkdir(parents=True)
                data = {'trial_name': f'case-{i}', 'agent_result': {'n_input_tokens':100, 'n_cache_tokens':40, 'n_output_tokens':10, 'cost_usd':0.25}, 'verifier_result': {'rewards': {'reward':reward}}, 'started_at':'2026-01-01T00:00:00Z', 'finished_at':'2026-01-01T00:00:10Z', 'agent_execution': {'started_at':'2026-01-01T00:00:02Z', 'finished_at':'2026-01-01T00:00:08Z'}}
                (trial / 'result.json').write_text(json.dumps(data))
                (trial / 'agent/trajectory.json').write_text(json.dumps({'steps':[{'tool_calls':[{'function_name':'exec_command'}, {'function_name':'functions.spawn_agent'}]}]}))
            (job / 'result.json').write_text(json.dumps({'n_total_trials':2,'started_at':'2026-01-01T00:00:00Z','finished_at':'2026-01-01T00:00:22Z'}))
            text = render_report(root)
            for expected in ['| 验收通过 / 计划运行 | 1 / 2 |', '| 输入 Token（含缓存） | 200 |', '| 非缓存输入 Token | 120 |', '| 缓存输入占比 | 40.00% |', '| 输出 Token | 20 |', '| 框架估算费用（USD，非实际账单） | 0.5000 |', '| 已记录工具调用 / spawn_agent 调用 | 4 / 2 |', '| 整轮墙钟时间（秒） | 22.00 |', '| 代理执行时间合计（秒） | 12.00 |']:
                self.assertIn(expected, text)

    def test_partial_measurements_remain_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i, usage in enumerate([{'n_input_tokens':100}, None]):
                trial = root / 'jobs/codex' / str(i)
                trial.mkdir(parents=True)
                (trial / 'result.json').write_text(json.dumps({'agent_result':usage, 'verifier_result':None, 'started_at':'2026-01-01T00:00:00Z'}))
            text = render_report(root)
            self.assertIn('| 输入 Token（含缓存） | — |', text)
            self.assertIn('| 已记录工具调用 / spawn_agent 调用 | — / — |', text)
            self.assertIn('| 整轮墙钟时间（秒） | — |', text)
            self.assertIn('未评分', text)

    def test_nop_exceptions_are_not_expected_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i, exception in enumerate([None, {'exception_type':'EnvironmentError'}]):
                trial = root / 'jobs/nop' / str(i)
                trial.mkdir(parents=True)
                (trial / 'result.json').write_text(json.dumps({'verifier_result':{'rewards':{'reward':0}}, 'exception_info':exception}))
            text = render_report(root)
            self.assertIn('符合预期：1/2', text)
            self.assertIn('| 已记录结果 / 异常结果 | 2 / 1 |', text)


if __name__ == '__main__':
    unittest.main()
