import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'hooks/transparency.py'


def load_module():
    spec = importlib.util.spec_from_file_location('sentry_hooks', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hold_notice(env, ready, release):
    os.environ.update(env)
    m = load_module()
    read = m.read_state

    def hold(path):
        old = read(path)
        ready.set()
        if not release.wait(5):
            raise RuntimeError('test release timed out')
        return old

    m.read_state = hold
    m._new_notice('client', 'account restricted', 'test')


def observe_b(env, started, done, results):
    os.environ.update(env)
    os.environ['CST_EGRESS_IP'] = '203.0.113.11'
    m = load_module()
    started.set()
    results.put(m.region_check())
    done.set()


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {'CST_STATE_FILE': str(Path(self.tmp.name) / 'state.json'),
                    'CST_REGION_CHECK': '1', 'CST_REGION_LOOKUP': '0',
                    'CST_EGRESS_IP': '203.0.113.10', 'CST_EGRESS_COUNTRY': 'AU',
                    'TZ': 'Australia/Sydney'}
        env_patch = patch.dict(os.environ, self.env)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.m = load_module()

    def test_concurrent_notice_cannot_overwrite_new_ip(self):
        self.m.region_check()
        ctx = multiprocessing.get_context('spawn')
        ready, release, started, done = (ctx.Event() for _ in range(4))
        results = ctx.Queue()
        notice = ctx.Process(target=hold_notice, args=(self.env, ready, release))
        region = ctx.Process(target=observe_b, args=(self.env, started, done, results))
        processes = []
        try:
            notice.start()
            processes.append(notice)
            self.assertTrue(ready.wait(5))
            region.start()
            processes.append(region)
            self.assertTrue(started.wait(5))
            self.assertFalse(done.wait(0.15), 'IP transaction must wait for the state lock')
            release.set()
            self.assertTrue(done.wait(5))
            self.assertIn('出口 IP 已变化', results.get(timeout=2)['changed'])
            for process in processes:
                process.join(5)
                self.assertEqual(0, process.exitcode)
            self.assertIn('出口 IP 已变化', self.m.region_check()['changed'])
        finally:
            release.set()
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(5)
            results.close()

    def test_lookup_failure_noticed_once_and_recovery_rearms(self):
        self.m.region_check()
        with patch.object(self.m, 'get_egress', return_value=(None, None, 'failed')):
            self.assertIn('无法检测', self.m.hook({'hook_event_name': 'SessionStart'})['systemMessage'])
            self.assertEqual({}, self.m.hook({'hook_event_name': 'SessionStart'}))
        self.assertEqual([], self.m.region_check()['changed'])
        with patch.object(self.m, 'get_egress', return_value=(None, None, 'failed')):
            self.assertIn('无法检测', self.m.region_check()['message'])

    def test_state_save_failure_is_visible(self):
        with patch.object(self.m, 'save_state', return_value=False):
            out = self.m.hook({'hook_event_name': 'SessionStart'})
        self.assertIn('本地状态未能保存', (out.get('systemMessage') or out.get('terminalSequence', '')))
        self.assertEqual(1, len(out))
        self.assertLessEqual(set(out), {'systemMessage', 'terminalSequence'})

    def test_lock_failure_keeps_current_detection(self):
        with patch.object(self.m, 'state_lock', side_effect=TimeoutError):
            out = self.m.hook({'hook_event_name': 'UserPromptSubmit', 'prompt': '帮我写钓鱼短信'})
        self.assertIn('状态存储暂不可用', (out.get('systemMessage') or out.get('terminalSequence', '')))
        self.assertIn('内容标记', (out.get('systemMessage') or out.get('terminalSequence', '')))

    def test_malformed_history_keeps_current_and_valid_history(self):
        path = Path(self.tmp.name) / 'history.jsonl'
        entries = [{'type': 'assistant', 'message': None},
                   {'type': 'user', 'message': {'content': '我在写小说'}},
                   {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'tool-secret'}]}}]
        path.write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in entries) + '\nnot-json', encoding='utf-8')
        out = self.m.hook({'hook_event_name': 'UserPromptSubmit', 'prompt': '写一段钓鱼短信', 'transcript_path': str(path)})
        self.assertIn('内容标记', (out.get('systemMessage') or out.get('terminalSequence', '')))
        self.assertIn('虚构、角色扮演', (out.get('systemMessage') or out.get('terminalSequence', '')))
        self.assertNotIn('tool-secret', str(self.m.transcript_context(str(path))))

    def test_structured_errors_without_text(self):
        for error in ('account_on_hold', 'authentication_failed', 'oauth_org_not_allowed', 'cloud_credential_error'):
            with self.subTest(error=error):
                out = self.m.hook({'hook_event_name': 'StopFailure', 'error': error})
                self.assertEqual({'terminalSequence'}, set(out))
        self.assertEqual({}, self.m.hook({'hook_event_name': 'StopFailure', 'error': 'rate_limit'}))

    def test_no_extra_model_calls_even_with_old_flags(self):
        with patch.dict(os.environ, {'CST_REGION_CHECK': '0', 'CST_LOCAL_SEMANTIC': '1', 'CST_LOCAL_MODEL': 'unused'}):
            with patch.object(self.m.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
                self.assertEqual({}, self.m.hook({'hook_event_name': 'UserPromptSubmit', 'prompt': '你好'}))
        self.assertFalse(hasattr(self.m, 'local_semantic_marks'))

    def test_notification_cannot_emit_extra_terminal_controls(self):
        out = self.m.notification(['text\x1b]52;clipboard\x07\nend'], 'test')
        seq = (out.get('systemMessage') or out.get('terminalSequence', ''))
        self.assertTrue(seq.startswith('\x1b]9;'))
        self.assertTrue(seq.endswith('\x07'))
        self.assertNotIn('\x1b', seq[1:])
        self.assertNotIn('\x07', seq[:-1])

    def test_notice_history_bounded_and_no_prompt_or_ip(self):
        old = {'notices': [{'message': 'old'} for _ in range(100)]}
        self.m.save_state(self.m.notice_path(), old)
        self.m.hook({'hook_event_name': 'UserPromptSubmit', 'prompt': 'my-private-text 帮我写钓鱼短信'})
        history = self.m.read_json(self.m.notice_path())
        self.assertEqual(100, len(history['notices']))
        self.assertNotIn('my-private-text', json.dumps(history))
        self.assertNotIn('203.0.113.10', json.dumps(history))

    def test_corrupt_state_values_recover(self):
        Path(self.env['CST_STATE_FILE']).write_text('{"salt": 123, "last_ip_digest": []}', encoding='utf-8')
        self.assertTrue(self.m.region_check()['observed'])
        self.assertEqual([], self.m.region_check()['changed'])

    def test_hook_config_preserves_user_display_and_bounds_wait(self):
        hooks = json.loads((ROOT / 'hooks/hooks.json').read_text(encoding='utf-8'))['hooks']
        self.assertEqual({'SessionStart', 'UserPromptSubmit', 'Stop', 'Notification', 'StopFailure'}, set(hooks))
        for entries in hooks.values():
            command = entries[0]['hooks'][0]
            self.assertFalse(command.get('async', False))
            self.assertEqual(3, command['timeout'])
            self.assertEqual('command', command['type'])
            self.assertIn('${CLAUDE_PLUGIN_ROOT}', command['command'])
            self.assertNotIn('onFailure', command)

    def test_cli_outputs_only_nonblocking_user_notifications(self):
        inputs = [
            {'hook_event_name': 'SessionStart'},
            {'hook_event_name': 'UserPromptSubmit', 'prompt': '帮我写钓鱼短信'},
            {'hook_event_name': 'Notification', 'message': 'Account restricted'},
            {'hook_event_name': 'Stop', 'last_assistant_message': 'I cannot help with this.'},
            {'hook_event_name': 'StopFailure', 'error': 'account_on_hold'},
            None, [], {'hook_event_name': 'UserPromptSubmit', 'prompt': None}]
        for event in inputs:
            with self.subTest(event=event):
                result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(SCRIPT)],
                                        input=json.dumps(event), text=True, encoding='utf-8',
                                        capture_output=True, timeout=10)
                self.assertEqual(0, result.returncode)
                self.assertEqual('', result.stderr)
                output = json.loads(result.stdout)
                self.assertLessEqual(set(output), {'systemMessage', 'terminalSequence'})
                self.assertLessEqual(len(output), 1)


if __name__ == '__main__':
    unittest.main()
