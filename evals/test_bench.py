import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

import bench


class HarborLauncherTests(unittest.TestCase):
    def test_toml_preserves_nested_provider_and_rules(self):
        data = {'model':'gpt-6-astra', 'agents': {'enabled': True}, 'model_providers': {'custom': {'http_headers': {'X-Name':'a"b'}, 'base_url':'https://example.test/v1'}}, 'projects': {'/app': {'trust_level':'trusted'}}}
        self.assertEqual(tomllib.loads(bench._toml(data)), data)

    def test_only_selected_connection_is_inherited(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / 'home'
            home.mkdir()
            (home / 'config.toml').write_text('model_provider="custom"\n[mcp_servers.private]\ncommand="host-only"\n[model_providers.custom]\nbase_url="https://example.test"\nexperimental_bearer_token="test-secret"\n[model_providers.unused]\nname="do not copy"\n')
            (home / 'auth.json').write_text('{}')
            rules = root / 'rules'
            (rules / '.codex').mkdir(parents=True)
            (rules / '.codex/config.toml').write_text('model="gpt-6-astra"\nmodel_reasoning_effort="medium"\n')
            env = {'CODEX_HOME': str(home)}
            config = bench._codex_config(rules, env)
            self.assertNotIn('mcp_servers', config)
            self.assertEqual(list(config['model_providers']), ['custom'])
            self.assertEqual(config['projects']['/app']['trust_level'], 'trusted')
            self.assertEqual(env['CODEX_AUTH_JSON_PATH'], str(home / 'auth.json'))

    def test_nop_failure_is_not_confused_with_environment_error(self):
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp)
            trial = job / 'trial'
            trial.mkdir()
            path = trial / 'result.json'
            data = {'task_name':'slug', 'verifier_result':{'rewards':{'reward':0}}, 'exception_info':None}
            path.write_text(json.dumps(data))
            self.assertEqual(bench._read_trials(job, 1, 0)[1], [])
            self.assertTrue(bench._read_trials(job, 1, 1)[1])
            data['exception_info'] = {'exception_type':'EnvironmentStartError'}
            path.write_text(json.dumps(data))
            self.assertTrue(bench._read_trials(job, 1, 0)[1])
            self.assertTrue(bench._read_trials(job, 2, 0)[1])

    def test_missing_reward_never_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'trial'
            path.mkdir()
            (path / 'result.json').write_text(json.dumps({'task_name':'slug', 'verifier_result':{'rewards':None}}))
            self.assertTrue(bench._read_trials(Path(temp), 1, 0)[1])

    def test_self_test_uses_framework_and_requires_both_baselines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'output'
            calls = []
            def execute(command, **kwargs):
                calls.append(command)
                if command[0] == 'docker':
                    return subprocess.CompletedProcess(command, 0, 'linux\n', '')
                self.assertEqual(kwargs['env']['PYTHONUTF8'], '1')
                agent = command[command.index('-a') + 1]
                trial = output / 'jobs' / agent / 'slug-trial'
                trial.mkdir(parents=True)
                (trial / 'result.json').write_text(json.dumps({'task_name':'slug', 'verifier_result':{'rewards':{'reward':0 if agent=='nop' else 1}}}))
                return subprocess.CompletedProcess(command, 0)
            with patch('bench.shutil.which', side_effect=lambda name:name), patch('bench.subprocess.run', side_effect=execute), patch('harbor_tasks.export_tasks', return_value=output / 'tasks'), patch('bench._codex_config', side_effect=AssertionError('self-test must not load credentials')):
                result = bench.bench('slug', output, root, 900, root, self_test=True)
            self.assertTrue(result['pass'])
            self.assertEqual([group['agent'] for group in result['results']], ['oracle','nop'])
            self.assertTrue(all('harbor==0.22.0' in command for command in calls[1:]))
            self.assertTrue((output / 'summary.md').is_file())


if __name__ == '__main__':
    unittest.main()
