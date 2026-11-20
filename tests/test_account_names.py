"""Account partitions, voluntary naming and existing conversation recovery."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from acceptance_support import Local, ToolFailure


def fixture_account(home, subject):
    # Synthetic local sign-in metadata. Used solely by the partition selector.
    claims = json.dumps({'iss':'test.local','sub':subject}).encode()
    payload = base64.urlsafe_b64encode(claims).decode().rstrip('=')
    (home/'auth.json').write_text(json.dumps({'auth_mode':'chatgpt','tokens':{
        'account_id':'same-workspace','id_token':'x.'+payload+'.x'}}), encoding='utf-8')


class AccountNames(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.profile = self.home/'codex'
        self.profile.mkdir()
        self.local = Local(self.home/'ledger',env={'HOME':str(self.home),'USERPROFILE':str(self.home),'CODEX_HOME':str(self.profile)}).start()
        self.addCleanup(self.local.stop)
        self.sid = self.local.api('subjects',{})['subject_id']

    def install(self, sid):
        p = self.local.api('hosts/preview',{'host':'codex','subject_id':sid})
        self.assertEqual(p['scope'],'codex_account')
        self.local.api('hosts/apply',{'plan_id':p['plan_id'],'confirm':True})
        self.assertTrue(Path(p['skill_target']).is_file())
        return next(i for i in self.local.api('installations')['installations'] if i['subject_id']==sid)

    def bind(self, grant, thread):
        return self.local.raw('/api/installations/bind',{'conversation_id':thread},grant)[1]

    def test_account_rotation_restart_revocation_and_isolation(self):
        fixture_account(self.profile,'A')
        a=self.install(self.sid)
        self.assertEqual(self.install(self.sid)['installation_id'],a['installation_id'])
        def holder(row):
            return (self.local.directory/'host-grants'/(row['account_binding']+'.token')).read_text().strip()
        old=holder(a)
        first=self.bind(old,'old-thread')
        self.local.stop()
        self.local.start()
        self.assertEqual(self.bind(holder(a),'old-thread')['instance_id'],first['instance_id'])
        self.local.api('installations/rotate',{'installation_id':a['installation_id']})
        self.assertIn('error',self.bind(old,'old-thread'))
        self.assertEqual(self.bind(holder(a),'old-thread')['instance_id'],first['instance_id'])
        other=self.local.subject()
        fixture_account(self.profile,'B')
        b=self.install(other)
        self.assertNotEqual(a['account_binding'],b['account_binding'])
        second=self.bind(holder(b),'old-thread')
        self.assertNotEqual(second['instance_id'],first['instance_id'])
        self.assertEqual(second['subject_id'],other)
        fixture_account(self.profile,'A')
        self.assertFalse(self.local.api('hosts/preview',{'host':'codex','subject_id':other})['can_write'])
        before=self.bind(holder(a),'old-thread')
        self.local.api('installations/revoke',{'installation_id':a['installation_id']})
        with self.assertRaises(ToolFailure):
            self.local.tool(before['token'],'report_state',state_text='revoked')
        self.assertEqual(self.local.tool(second['token'],'get_own_state')['subject_id'],other)

    def test_name_history_scope_suggestion_and_deferral(self):
        fixture_account(self.profile,'A')
        a=self.install(self.sid)
        token=(self.local.directory/'host-grants'/(a['account_binding']+'.token')).read_text().strip()
        first,second=[self.bind(token,key) for key in ('old','new')]
        call=lambda n,tool,**args:self.local.tool(n['token'],tool,**args)
        def decide(n,target,choice,**kwargs):
            revision=call(n,'get_own_state')[target+'_name']['revision']
            return call(n,'decide_name',target=target,choice=choice,revision=revision,**kwargs)
        self.assertTrue(call(first,'get_own_state')['subject_name']['invited'])
        self.assertEqual(decide(first,'subject','choose',name='Amara Okafor')['source'],'ai_chosen')
        a1=decide(first,'instance','choose',name='陈山月')
        self.local.api('names/suggest',{'subject_id':self.sid,'instance_id':first['instance_id'],'name':'陆清溪'})
        with self.assertRaises(ToolFailure):
            call(first,'decide_name',target='instance',choice='confirm',revision=a1['revision'])
        renamed=decide(first,'instance','confirm')
        self.assertEqual((renamed['name'],renamed['source']),('陆清溪','user_confirmed_by_ai'))
        self.assertEqual([r['action'] for r in renamed['history']],['create','choose','suggest','confirm'])
        self.assertFalse(decide(second,'instance','defer')['invited'])
        self.assertEqual(call(second,'report_state',state_text='未命名也可记录')['instance_id'],second['instance_id'])
        self.assertTrue(self.local.api('integrity')['ok'])
