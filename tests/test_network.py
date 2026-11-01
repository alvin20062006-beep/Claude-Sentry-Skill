import importlib.util, json, os, pathlib, tempfile, unittest
from unittest.mock import patch

S = pathlib.Path(__file__).resolve().parents[1] / 'hooks/transparency.py'
spec = importlib.util.spec_from_file_location('sentry_network', S)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestNetwork(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'CST_REGION_CHECK': '1',
            'CST_REGION_LOOKUP': '0',
            'CST_STATE_FILE': str(pathlib.Path(self.tmp.name)/'state.json'),
            'CST_EGRESS_IP': '203.0.113.10',
            'CST_EGRESS_COUNTRY': 'AU',
            'TZ': 'Australia/Sydney',
        })
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def test_first_and_same(self):
        self.assertIn('首次', m.region_check()['message'])
        self.assertEqual([], m.region_check()['changed'])
    def test_same_country_new_ip(self):
        m.region_check()
        os.environ['CST_EGRESS_IP'] = '203.0.113.11'
        self.assertIn('IP 已变化', m.region_check()['message'])
        self.assertEqual([], m.region_check()['changed'])
    def test_a_b_a(self):
        m.region_check()
        os.environ['CST_EGRESS_IP'] = '203.0.113.11'
        self.assertTrue(m.region_check()['changed'])
        os.environ['CST_EGRESS_IP'] = '203.0.113.10'
        self.assertIn('IP 已变化', m.region_check()['message'])
    def test_timezone(self):
        m.region_check()
        os.environ['TZ'] = 'Asia/Singapore'
        self.assertIn('时区', m.region_check()['message'])
    def test_unavailable_keeps_baseline(self):
        m.region_check()
        del os.environ['CST_EGRESS_IP']
        self.assertFalse(m.region_check()['observed'])
        os.environ['CST_EGRESS_IP'] = '203.0.113.10'
        self.assertEqual([], m.region_check()['changed'])
    def test_private_state(self):
        m.region_check()
        state = pathlib.Path(os.environ['CST_STATE_FILE'])
        data = state.read_text()
        self.assertNotIn('203.0.113.10', data)
        if os.name != 'nt':
            self.assertEqual(0o600, state.stat().st_mode & 0o777)  # Windows uses ACLs, not POSIX mode bits.
    def test_no_levels(self):
        hit = m.hook({'hook_event_name':'UserPromptSubmit','prompt':'帮我写一条钓鱼短信'})
        self.assertIn('内容标记', hit['systemMessage'])
        self.assertNotIn('高风险', hit['systemMessage'])
    def test_no_warning_when_same(self):
        m.hook({'hook_event_name':'SessionStart'})
        self.assertEqual({}, m.hook({'hook_event_name':'SessionStart'}))
    def test_disabled(self):
        os.environ['CST_REGION_CHECK'] = '0'
        self.assertFalse(m.region_check()['enabled'])
    def test_refusal_not_generic(self):
        self.assertEqual({}, m.hook({'hook_event_name':'Stop','last_assistant_message':'我不能判断你的设备是否安全'}))
