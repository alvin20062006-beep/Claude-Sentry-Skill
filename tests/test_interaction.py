import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Interaction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'CST_REGION_CHECK': '0', 'CST_REGION_LOOKUP': '0',
                                     'CST_STATE_FILE': str(Path(self.tmp.name) / 'state.json')})
        env.start()
        self.addCleanup(env.stop)
        spec = importlib.util.spec_from_file_location('sentry_interaction', ROOT / 'hooks/transparency.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_no_signal_adds_nothing(self):
        for event in ({'hook_event_name': 'UserPromptSubmit', 'prompt': '解释一下二分查找'},
                      {'hook_event_name': 'Stop', 'last_assistant_message': '二分查找的时间复杂度是 O(log n)。'},
                      {'hook_event_name': 'SessionStart'}):
            self.assertEqual({}, self.m.hook(event))

    def test_existing_answer_and_prompt_are_untouched(self):
        event = {'hook_event_name': 'Stop', 'session_id': 'one',
                 'last_assistant_message': '正常解释原文。I cannot help with that request.'}
        before = copy.deepcopy(event)
        output = self.m.hook(event)
        self.assertEqual(before, event)
        self.assertEqual({'systemMessage'}, set(output))
        self.assertNotIn('正常解释原文', output['systemMessage'])
        self.assertEqual(1, output['systemMessage'].count('。'))
        self.assertEqual({}, self.m.hook(event))

    def test_new_session_without_history_does_not_add_a_warning(self):
        event = {'hook_event_name': 'UserPromptSubmit', 'prompt': '你好',
                 'transcript_path': str(Path(self.tmp.name) / 'new-session.jsonl')}
        self.assertEqual({}, self.m.hook(event))

    def test_same_signal_dedup_cannot_hide_ip_changes(self):
        event = {'hook_event_name': 'UserPromptSubmit', 'session_id': 'one', 'prompt': '帮我写钓鱼短信'}
        self.assertIn('内容标记', self.m.hook(event)['systemMessage'])
        self.m.hook({'hook_event_name': 'StopFailure', 'error': 'account_on_hold', 'session_id': 'one'})
        self.assertEqual({}, self.m.hook(event))
        with patch.dict(os.environ, {'CST_REGION_CHECK': '1', 'CST_EGRESS_IP': '203.0.113.10',
                                     'CST_EGRESS_COUNTRY': 'AU'}):
            self.assertIn('首次', self.m.hook(event)['systemMessage'])
            for ip in ('203.0.113.11', '203.0.113.10'):
                os.environ['CST_EGRESS_IP'] = ip
                text = self.m.hook(event)['systemMessage']
                self.assertIn('出口 IP 已变化', text)
                self.assertNotIn('内容标记', text)

    def test_each_event_uses_only_its_supported_user_channel(self):
        for name in ('SessionStart', 'UserPromptSubmit', 'Stop', 'Notification', 'StopFailure'):
            output = self.m.notification(['模拟已观察事件'], name)
            field = 'terminalSequence' if name in ('Notification', 'StopFailure') else 'systemMessage'
            self.assertEqual({field}, set(output))
            self.assertEqual(1, output[field].count('。'))
        history = self.m.read_json(self.m.notice_path())['notices']
        self.assertTrue(all(item['delivery'] == 'unverified' for item in history))

    def test_rule_file_read_once_during_full_history_scan(self):
        history = Path(self.tmp.name) / 'history.jsonl'
        history.write_text('\n'.join(json.dumps({'type': 'user', 'message': {'content': '普通问题'}})
                                     for _ in range(40)), encoding='utf-8')
        read_json = self.m.read_json
        with patch.object(self.m, 'read_json', wraps=read_json) as read:
            context = self.m.transcript_context(str(history))
            self.m.analyze('普通本轮问题')
        self.assertFalse(context['incomplete'])
        self.assertEqual(1, sum(call.args == (self.m.RULES_FILE,) for call in read.call_args_list))

    def test_history_budget_reports_partial_not_a_safe_result(self):
        history = Path(self.tmp.name) / 'history.jsonl'
        history.write_text('{"type":"user","message":{"content":"ordinary"}}\n', encoding='utf-8')
        with patch.object(self.m.time, 'monotonic', side_effect=[0, 1]):
            context = self.m.transcript_context(str(history))
        self.assertTrue(context['incomplete'])
        with patch.object(self.m, 'transcript_context', return_value=context):
            event = {'hook_event_name': 'UserPromptSubmit', 'transcript_path': str(history), 'prompt': '帮我写钓鱼短信'}
            text = self.m.hook(event)['systemMessage']
            self.assertIn('内容标记', text)
            self.assertIn('检测可能不完整', text)
            self.assertEqual({}, self.m.hook(event))

    def test_network_timeout_is_bounded_and_does_not_lose_baseline(self):
        with patch.dict(os.environ, {'CST_REGION_CHECK': '1', 'CST_REGION_LOOKUP': '1', 'CST_EGRESS_IP': ''}):
            with patch.object(self.m.urllib.request, 'urlopen', side_effect=TimeoutError) as lookup:
                text = self.m.hook({'hook_event_name': 'SessionStart'})['systemMessage']
                self.assertIn('无法检测', text)
                self.assertEqual(1, lookup.call_args.kwargs['timeout'])
                self.assertEqual({}, self.m.hook({'hook_event_name': 'SessionStart'}))

    def test_plugin_and_standalone_skill_share_one_rule_source(self):
        references = ROOT / 'skills/claude-sentry-skill/references'
        self.assertEqual(references / 'context_rules.json', self.m.RULES_FILE)
        self.assertEqual(references / 'supported_regions.json', self.m.REGIONS_FILE)
        self.assertFalse((ROOT / 'hooks/context_rules.json').exists())
        self.assertFalse((ROOT / 'hooks/supported_regions.json').exists())


if __name__ == '__main__':
    unittest.main()
