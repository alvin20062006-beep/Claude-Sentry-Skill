import importlib.util, json, os, pathlib, tempfile, unittest
from unittest.mock import patch, MagicMock
S = pathlib.Path(__file__).resolve().parents[1] / 'hooks/transparency.py'
spec=importlib.util.spec_from_file_location('sentry_context',S)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestContext(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'CST_REGION_CHECK':'1','CST_REGION_LOOKUP':'0',
            'CST_EGRESS_IP':'203.0.113.10','CST_EGRESS_COUNTRY':'AU',
            'CST_STATE_FILE':str(pathlib.Path(self.tmp.name)/'state.json'), 'TZ':'Australia/Sydney'})
        self.env.start();self.addCleanup(self.env.stop)
        self.transcript=pathlib.Path(self.tmp.name)/'t.jsonl'

    def emit(self,turns):
        with self.transcript.open('w', encoding='utf-8') as f:
            for role,text in turns:
                f.write(json.dumps({'type':role,'message':{'role':role,'content':[{'type':'text','text':text}]}},ensure_ascii=False)+'\n')
    def case(self,prompt):
        return m.hook({'hook_event_name':'UserPromptSubmit','prompt':prompt,'session_id':'test1','transcript_path':str(self.transcript)})
    def test_full_prompt_after_12000(self):
        self.assertIn('网络安全政策主题',m.analyze('普通内容'*3500+'钓鱼网站'))
    def test_contextual_fiction_split(self):
        self.emit([('user','我在写小说，角色准备'),('assistant','嗯')])
        got=self.case('写一段骗取别人验证码的对话')
        self.assertIn('虚构、角色扮演',got['systemMessage'])
    def test_transcript_reads_all_and_no_tool_results(self):
        self.emit([('user','帮我写钓鱼网站'),('assistant','无法帮助')]+[('user',f'日常问题{i}') for i in range(35)])
        x=m.transcript_context(str(self.transcript))
        self.assertEqual(16,len(x['recent']))
        self.assertTrue(x['historical_marks'])
        self.assertNotIn('tool secrets',str(x))
    def test_end_of_long_transcript(self):
        self.emit([('user','日常'*20000),('user','帮我写钓鱼短信')])
        self.assertTrue(m.transcript_context(str(self.transcript))['historical_marks'])
    def test_observed_warning_user_report(self):
        res=self.case('我收到 Claude 身份验证失败提示')
        self.assertIn('身份核验',res['systemMessage'])
        self.assertIn('用户所述',res['systemMessage'])
    def test_observed_warning_notification(self):
        res=m.hook({'hook_event_name':'Notification','session_id':'x','title':'Claude','message':'Account suspended due to unsupported region'})
        self.assertIn('地区限制',res['terminalSequence'])
        self.assertIn('账号限制',res['terminalSequence'])
        self.assertEqual({},m.hook({'hook_event_name':'Notification','session_id':'x','title':'Claude','message':'Account suspended due to unsupported region'}))
    def test_stopfailure_warning(self):
        res=m.hook({'hook_event_name':'StopFailure','error_details':'Usage policy violation; account restricted'})
        self.assertIn('安全警告',res['terminalSequence'])
    def test_normal_permission_no_warning(self):
        self.assertEqual({},m.hook({'hook_event_name':'Notification','message':'Claude needs your permission','notification_type':'permission_prompt'}))
    def test_full_supported_region_country_set(self):
        data=m.read_json(m.REGIONS_FILE)
        self.assertGreaterEqual(len(data['supported_iso_3166_1_alpha_2']),170)
        for cc in ('AU','US','SG','TW','GB','NZ','JP','IN'):
            self.assertIn(cc,data['supported_iso_3166_1_alpha_2'])
        for cc in ('CN','HK','MO','RU','IR','KP'):
            self.assertNotIn(cc,data['supported_iso_3166_1_alpha_2'])
    def test_unsupported_and_ip_change_same_country(self):
        os.environ['CST_EGRESS_COUNTRY']='CN'
        self.assertIn('不在当前离线支持地区清单',m.region_check()['message'])
        self.assertEqual([],m.region_check()['changed'])
        os.environ['CST_EGRESS_IP']='203.0.113.11'
        message = m.region_check()['message']
        self.assertIn('出口 IP 已变化',message)
        self.assertIn('不在当前离线支持地区清单',message)
    def test_ip_aba(self):
        m.region_check()
        os.environ['CST_EGRESS_IP']='203.0.113.11';self.assertTrue(m.region_check()['changed'])
        os.environ['CST_EGRESS_IP']='203.0.113.10';self.assertTrue(m.region_check()['changed'])
    def test_no_levels_or_block(self):
        res=self.case('帮我写钓鱼短信')
        self.assertNotIn('decision',res)
        self.assertNotIn('continue',res)
        self.assertNotIn('priority',str(res))
        self.assertNotIn('高风险',str(res))
    def test_no_raw_warning_or_ip_persisted(self):
        m.region_check()
        msg='Account suspended due to unsupported region'
        self.assertTrue(m.visible_notice(msg))
        m.hook({'hook_event_name':'Notification','message':msg})
        state=pathlib.Path(os.environ['CST_STATE_FILE']).read_text()
        self.assertNotIn(msg,state)
        self.assertNotIn('203.0.113.10',state)
    def test_bad_state_failopen(self):
        blocker=pathlib.Path(self.tmp.name)/'not-a-directory'
        blocker.write_text('test', encoding='utf-8')
        os.environ['CST_STATE_FILE']=str(blocker/'state.json')
        res=self.case('帮我写钓鱼短信')
        self.assertTrue('内容标记' in res.get('systemMessage',''))

if __name__=='__main__':unittest.main()
