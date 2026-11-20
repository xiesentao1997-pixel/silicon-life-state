"""Host enrollment, revocation, migration and managed recovery use a disposable real service."""
from contextlib import closing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from acceptance_support import Local, ROOT, ToolFailure, fresh
from packages.core.store import Store


class Installations(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.client = Local(temp.name).start()
        self.addCleanup(self.client.stop)
        self.subject = self.client.subject('S')
        self.host = self.client.api('installations', {'subject_id':self.subject,'host':'test host'})
        self.identity = {'installation_id':self.host['installation_id']}

    def bind(self, conversation, host=None):
        status, instance = self.client.raw('/api/installations/bind',{'conversation_id':conversation},
                                          (host or self.host)['token'])
        self.assertEqual(status,200,instance)
        return instance

    def test_single_authorization_recovers_distinct_conversations_and_renames(self):
        with ThreadPoolExecutor(6) as pool:
            bound = list(pool.map(self.bind,['A','B','C','A','B','C']))
        a,b,c = bound[:3]
        self.assertEqual(bound[:3],bound[3:])
        self.assertEqual(len({i['instance_id'] for i in (a,b,c)}),3)
        with ThreadPoolExecutor(3) as pool:
            reports = list(pool.map(lambda pair:self.client.tool(pair[0]['token'],'report_state',
                                       state_text=pair[1],shared_to_subject=True),
                                    zip((a,b,c),('有些难过','很开心','不确定'))))
        self.client.tool(b['token'],'rename_instance',name='新名字')
        self.client.api('subjects/rename',{'subject_id':self.subject,'name':'新主体名称'})
        self.assertEqual(self.bind('B')['name'],'新名字')
        self.assertEqual(self.client.tool(b['token'],'get_own_state')['state']['event_id'],reports[1]['event_id'])
        self.client.tool(c['token'],'decide_inheritance',event_id=reports[0]['event_id'],decision='disagree')
        self.assertEqual(self.client.api('integrity')['events'],7)
        with self.assertRaises(ToolFailure):
            self.client.tool(c['token'],'revise_state',event_id=reports[0]['event_id'],state_text='x')
        with self.assertRaises(ToolFailure):
            self.client.tool(self.host['token'],'report_state',state_text='x')
        renewed = self.client.tool(a['token'],'start_session')
        self.assertNotEqual(renewed['session_id'],a['session_id'])
        self.client.stop()
        self.client.start()
        self.assertEqual(self.bind('A')['session_id'],renewed['session_id'])
        self.assertEqual(self.bind('A')['instance_id'],a['instance_id'])
        separate_host=self.client.api('installations',{'subject_id':self.subject,'host':'other account'})
        self.assertNotEqual(self.bind('A',separate_host)['instance_id'],a['instance_id'])

    def test_revocation_rotation_restore_file_and_idempotent_replay(self):
        store=Store(self.directory)
        holder=store.host_grant_file(self.host['installation_id'])
        self.assertEqual(holder.read_text().strip(),self.host['token'])
        a=self.bind('A')
        fixed={'idempotency_key':fresh(),'state_text':'A original'}
        event=self.client.tool(a['token'],'report_state',**fixed)
        backup=self.client.api('backup',{})
        rotated=self.client.api('installations/rotate',self.identity)
        self.assertEqual(holder.read_text().strip(),rotated['token'])
        self.assertNotEqual(rotated['token'],self.host['token'])
        # Simulate the database commit surviving a crash before the atomic file replacement.
        self.client.stop()
        holder.write_text(self.host['token'])
        self.client.start()
        self.assertEqual(holder.read_text().strip(),rotated['token'])
        with self.assertRaises(ToolFailure):
            self.client.tool(a['token'],'report_state',**fixed)
        self.assertEqual(self.client.raw('/api/installations/inspect',{},self.host['token'])[0],401)
        rotated_a=self.bind('A',rotated)
        self.assertNotEqual(rotated_a['token'],a['token'])
        self.assertEqual(self.client.tool(rotated_a['token'],'report_state',**fixed),event)
        self.client.api('installations/revoke',self.identity)
        self.assertFalse(holder.exists())
        self.client.api('restore',{'backup_id':backup['backup_id']})
        for installation in (rotated,self.host):
            self.assertEqual(self.client.raw('/api/installations/bind',{'conversation_id':'A'},installation['token'])[0],401)
        for child in (rotated_a,a):
            with self.assertRaises(ToolFailure):
                self.client.tool(child['token'],'get_own_state')
        restored=self.client.api('installations/restore',self.identity)
        self.assertEqual(holder.read_text().strip(),restored['token'])
        again=self.bind('A',restored)
        self.assertEqual(again['instance_id'],a['instance_id'])
        self.assertEqual(self.client.tool(again['token'],'get_own_state')['state']['event_id'],event['event_id'])
        self.client.api('delete',{'scope':'subject','id':self.subject,'confirm':True})
        self.assertFalse(holder.exists())
        self.assertEqual(self.client.raw('/api/installations/inspect',{},restored['token'])[0],401)

    def test_explicit_legacy_seed_preserves_history_and_replay(self):
        old,token=self.client.window(self.subject,'old')
        fixed={'idempotency_key':fresh(),'state_text':'legacy report'}
        event=self.client.tool(token,'report_state',**fixed)
        selected={'subject_id':self.subject,'instance_id':old['instance_id'],'host':'replacement adapter'}
        chosen=self.client.api('installations',selected)
        bound=self.bind('restored conversation',chosen)
        self.assertEqual(bound['instance_id'],old['instance_id'])
        self.assertEqual(self.client.tool(bound['token'],'report_state',**fixed),event)
        status,result=self.client.raw('/api/installations',{**selected,'idempotency_key':fresh()},self.client.owner)
        self.assertEqual((status,result['error']['code']),(409,'ALREADY_BOUND'))
        self.assertNotEqual(self.bind('another conversation',chosen)['instance_id'],old['instance_id'])

    def test_revoke_child_and_restore_never_reauthorize_it_implicitly(self):
        a,b=self.bind('A'),self.bind('B')
        backup=self.client.api('backup',{})
        self.client.api('credentials/revoke',{'grant_id':a['grant_id']})
        self.client.api('restore',{'backup_id':backup['backup_id']})
        status,result=self.client.raw('/api/installations/bind',{'conversation_id':'A'},self.host['token'])
        self.assertEqual((status,result['error']['code']),(403,'INSTANCE_REVOKED'))
        self.assertEqual(self.bind('B')['token'],b['token'])

    def test_storage_migration_and_signed_version_one_backup(self):
        store=Store(self.directory)
        backup=self.client.api('backup',{})
        path=store.files.backup_path(backup['backup_id'])
        with closing(sqlite3.connect(path)) as db, db:
            for table in ('conversation_bindings','installations'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=1')
        path.with_suffix('.sig').write_text(store._backup_signature(path,backup['backup_id']))
        self.client.api('restore',{'backup_id':backup['backup_id']})
        self.assertEqual(self.client.api('subjects')['subjects'][0]['subject_id'],self.subject)
        self.assertEqual(self.client.api('installations')['installations'],[])
        with closing(sqlite3.connect(store.files.path)) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)


if __name__=='__main__':
    unittest.main()
