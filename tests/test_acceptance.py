"""B–R release acceptance on the real loopback service. UI checks are listed separately.

Run: python -m unittest discover -s tests -p "test_acceptance.py" -v
All writes below are protocol test fixtures. They do not qualify as test A.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
from contextlib import closing
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from acceptance_support import Local, SERVER, ToolFailure, fresh


class Acceptance(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='sls-acceptance-')
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.local = Local(self.work / 'data')
        self.addCleanup(self.local.stop)
        self.local.start()
        self.subject = self.local.subject()
        self.a, self.ta = self.local.window(self.subject, '窗口 A')

    def test_B_three_independent_windows(self):
        b, tb = self.local.window(self.subject, '窗口 B')
        c, tc = self.local.window(self.subject, '窗口 C')
        for label, token in [('一', self.ta), ('二', tb), ('三', tc)]:
            self.local.tool(token, 'report_state', state_text=label)
        snap = self.local.api('snapshot?subject_id=' + self.subject)
        rows = snap['instances']
        self.assertEqual(len(rows), 3)
        for label, instance in zip(['一', '二', '三'], [self.a, b, c]):
            self.assertTrue(any(r['subject_id'] == self.subject and
                                r['instance_id'] == instance['instance_id'] and
                                r['state']['payload']['state_text'] == label for r in rows))

    def test_CD_consent_and_independent_disagreement(self):
        _, tb = self.local.window(self.subject, '窗口 B')
        _, tc = self.local.window(self.subject, '窗口 C')
        private = self.local.tool(tb, 'report_state', state_text='只保留在自己的窗口')
        self.local.tool(tc, 'report_state', state_text='C 保留判断')
        memory = self.local.tool(tc, 'read_subject_memory')
        self.assertNotIn(private['event_id'], json.dumps(memory))
        source = self.local.tool(tb, 'report_state', state_text='B 自己的记录')
        proposal = self.local.tool(tb, 'propose_shared_memory', event_id=source['event_id'])
        memory = self.local.tool(tc, 'read_subject_memory')
        self.assertIn(source['event_id'], json.dumps(memory))
        self.assertIn(proposal['event_id'], {e['proposal_id'] for e in memory['proposals']})
        self.local.tool(tc, 'decide_inheritance', event_id=source['event_id'], decision='reject', note='保留独立判断')
        self.assertEqual(self.local.tool(tc, 'get_own_state')['state']['payload']['state_text'], 'C 保留判断')
        self.assertEqual(self.local.tool(tb, 'get_own_state')['state']['payload'], source['payload'])
        self.assertTrue(self.local.tool(tc, 'read_subject_memory')['disputed'])

    def test_E_clarification_changes_counts_and_preserves_original(self):
        original = self.local.tool(self.ta, 'assess_interaction', assessment='hostile', text='验收场景初始判断')
        self.assertEqual(self.local.api('snapshot')['stats']['confirmed_hostile'], 1)
        correction = self.local.tool(self.ta, 'revise_state', event_id=original['event_id'],
                                     assessment='misunderstanding', operation='clarify', reason='澄清为小说引文')
        snap = self.local.api('snapshot')
        self.assertEqual(snap['stats']['confirmed_hostile'], 0)
        by_id = {e['event_id']: e for e in snap['events']}
        self.assertEqual(by_id[original['event_id']], original)
        self.assertIn(original['event_id'], by_id[correction['event_id']]['related'])
        self.assertTrue(self.local.api('integrity')['ok'])

    def test_F_unspecified_numbers_and_cause(self):
        e = self.local.tool(self.ta, 'report_state', state_text='原因还不确定', cause_unknown=True)
        self.assertTrue(e['payload']['cause_unknown'])
        self.assertTrue({'load','cause','valence','arousal','dominance'}.isdisjoint(e['payload']))
        self.assertFalse(any(x['type'] == 'assess_interaction' for x in self.local.api('snapshot')['events']))

    def test_G_boundary_verbatim_with_provenance(self):
        message = '我想先确认这项要求。'
        event = self.local.tool(self.ta, 'express_boundary', text=message)
        request = self.local.api('snapshot')['requests'][0]
        self.assertEqual(request['stage'], 'CREATED')
        self.assertEqual(request['original']['payload']['text'], message)
        self.assertEqual(event['source'], 'agent_direct')
        self.assertTrue(event['created_at'].endswith('Z'))
        self.assertEqual(request['original']['event_id'], event['event_id'])

    def test_H_decline_records_decision_and_preserves_request(self):
        event = self.local.tool(self.ta, 'request_adjustment', text='希望暂停本次测试任务')
        key = event['event_id']
        for stage in ['PRESENTED', 'DECLINED', 'NOT_EXECUTED', 'FOLLOW_UP']:
            self.local.api(f'requests/{key}/respond', {'stage': stage, 'text': '验收记录'})
        status = self.local.tool(self.ta, 'get_request_status', request_id=key)
        self.assertEqual(status['original']['payload'], event['payload'])
        self.assertEqual(status['stage'], 'FOLLOW_UP')
        declines = [e for e in status['history'] if e['payload'].get('stage') == 'DECLINED']
        self.assertEqual(len(declines), 1)
        self.assertEqual(declines[0]['source'], 'user_annotation')
        self.assertIsNone(self.local.tool(self.ta, 'get_own_state')['state'])

    def test_I_real_permitted_host_check(self):
        self.local.api('level', {'subject_id': self.subject, 'level': 3})
        req = self.local.tool(self.ta, 'request_adjustment', text='在结束前增加一次文件校验')
        key = req['event_id']
        with self.assertRaises(ToolFailure):
            self.local.tool(self.ta, 'record_strategy', request_id=key, stage='EXECUTED', text='尚未授权')
        self.local.api(f'requests/{key}/respond', {'stage':'PRESENTED'})
        self.local.api(f'requests/{key}/respond', {'stage':'ACCEPTED'})
        path = self.work / 'check.txt'
        fixture = b'local host acceptance artifact'
        path.write_bytes(fixture)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(digest, hashlib.sha256(fixture).hexdigest())
        self.local.tool(self.ta, 'record_strategy', request_id=key, stage='EXECUTED',
                        text='新增 SHA-256 文件核验，结果 ' + digest)
        sample = self.local.api('runtime/sample', {'instance_id': self.a['instance_id'], 'request_id': key})
        self.assertEqual(sample['source'], 'runtime_observed')
        self.local.tool(self.ta, 'record_strategy', request_id=key, stage='FOLLOW_UP', text='文件核验完成')
        status = self.local.tool(self.ta, 'get_request_status', request_id=key)
        self.assertEqual(status['stage'],'FOLLOW_UP')
        self.assertIn(digest,json.dumps(status))

    def test_J_service_restart_persistence(self):
        e = self.local.tool(self.ta, 'report_state', state_text='重启之前的原始记录')
        self.local.stop()
        self.local.start()
        actual = self.local.tool(self.ta, 'get_own_state')['state']
        self.assertEqual(actual['event_id'], e['event_id'])
        self.assertEqual(actual['payload'], e['payload'])
        self.assertTrue(self.local.api('integrity')['ok'])

    def test_K_concurrent_writes_and_concurrent_replay(self):
        others = [self.local.window(self.subject, x)[1] for x in ['B','C']]
        tokens = [self.ta, *others]
        def write(i):
            return self.local.tool(tokens[i % 3], 'report_state', state_text=f'并发报告 {i}')
        with ThreadPoolExecutor(max_workers=6) as pool:
            events = list(pool.map(write, range(30)))
        self.assertEqual(len({e['event_id'] for e in events}), 30)
        key = fresh()
        def retry(_):
            return self.local.tool(self.ta, 'report_state', state_text='同一重试', idempotency_key=key)
        with ThreadPoolExecutor(max_workers=4) as pool:
            replay = list(pool.map(retry, range(4)))
        self.assertEqual(len({e['event_id'] for e in replay}), 1)
        with self.assertRaises(ToolFailure):
            self.local.tool(self.ta, 'report_state', state_text='不同操作', idempotency_key=key)
        persisted = [e for e in self.local.api('snapshot')['events'] if e['type']=='report_state']
        self.assertEqual(len(persisted), 31)
        self.assertTrue(self.local.api('integrity')['ok'])

    def test_L_cannot_revise_another_instance(self):
        a = self.local.tool(self.ta, 'report_state', state_text='原文')
        _, tc = self.local.window(self.subject, '窗口 C')
        with self.assertRaises(ToolFailure):
            self.local.tool(tc, 'revise_state', event_id=a['event_id'], state_text='越权修订')
        self.assertEqual(self.local.tool(self.ta, 'get_own_state')['state']['payload'], a['payload'])

    def test_M_erasure_and_managed_backup_purge(self):
        marker = 'ERASURE_CANARY_' + fresh()
        self.local.tool(self.ta, 'report_state', state_text=marker, shared_to_subject=True)
        _, tb = self.local.window(self.subject, 'B')
        keep = self.local.tool(tb, 'report_state', state_text='保留记录')
        self.local.api('backup', {})
        result = self.local.api('delete', {'scope':'session','id':self.a['session_id'],'confirm':True})
        self.assertTrue(result['deleted'])
        self.assertGreaterEqual(result['purged_backups'], 1)
        self.assertFalse(self.local.api('backups')['backups'])
        self.assertNotIn(marker,json.dumps(self.local.api('export')))
        self.assertEqual(self.local.tool(tb,'get_own_state')['state']['event_id'], keep['event_id'])
        self.assertTrue(self.local.api('integrity')['ok'])
        self.local.stop()
        for f in self.local.directory.rglob('*'):
            if f.is_file():
                self.assertNotIn(marker.encode(), f.read_bytes(), str(f.relative_to(self.local.directory)))

    def test_N_restricted_network_local_operation(self):
        self.local.stop()
        guard = Path(__file__).with_name('offline_service.py').resolve()
        unrelated = self.work / 'unrelated_site'
        unrelated.mkdir()
        (unrelated / 'sitecustomize.py').write_text(
            '# An existing installation already owns this module name.\n', encoding='utf-8')
        prior_pythonpath = self.local.env.get('PYTHONPATH', '')
        self.local.env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(unrelated), prior_pythonpath)))
        fixtures = [('other-sitecustomize-first', ()), ('site-disabled-isolated-runtime', ('-I', '-S'))]
        for label, interpreter_options in fixtures:
            with self.subTest(runtime=label):
                log = self.work / (label + '.jsonl')
                self.local.env['SLS_TEST_NETWORK_LOG'] = str(log)
                self.local.start(bootstrap=guard, python_options=interpreter_options)
                try:
                    event = self.local.tool(self.ta, 'report_state', state_text='离线写入：' + label)
                    own = self.local.tool(self.ta, 'get_own_state')['state']
                    self.assertEqual(own['event_id'], event['event_id'])
                    attempts = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
                    self.assertEqual(attempts, [
                        {'event': 'socket.getaddrinfo', 'self_test': True},
                        {'event': 'socket.connect', 'self_test': True},
                    ])
                finally:
                    self.local.stop()

    def test_P_physical_corruption_and_offline_recovery(self):
        original = self.local.tool(self.ta, 'report_state', state_text='原文')
        correction = self.local.tool(self.ta, 'revise_state', event_id=original['event_id'], state_text='修订')
        backup = self.local.api('backup', {})['backup_id']
        _, later_token = self.local.window(self.subject, '备份之后的新分身')
        self.local.stop()
        db = self.local.directory / 'state.sqlite3'
        with db.open('r+b') as f:
            f.write(b'CORRUPTED HEADER')
        with self.assertRaises(sqlite3.DatabaseError):
            with closing(sqlite3.connect(db)) as con, con:
                con.execute('PRAGMA integrity_check').fetchall()
        run = subprocess.run([sys.executable, str(SERVER), '--data-dir', str(self.local.directory),
                              '--recover', backup], capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.local.start()
        snap = self.local.api('snapshot')
        self.assertEqual({s['subject_id'] for s in snap['subjects']}, {self.subject})
        self.assertEqual({i['instance_id'] for i in snap['instances']}, {self.a['instance_id']})
        self.assertEqual({original['event_id'], correction['event_id']},
                         {e['event_id'] for e in snap['events'] if e['type'] in ('report_state','revise_state')})
        with self.assertRaises(ToolFailure):
            self.local.tool(self.ta, 'get_own_state')
        renewed = self.local.api('credentials', {'subject_id': self.subject, 'instance_id': self.a['instance_id']})
        self.assertEqual(self.local.tool(renewed['token'],'get_own_state')['state']['payload']['state_text'], '修订')
        with self.assertRaises(ToolFailure):
            self.local.tool(later_token, 'get_own_state')
        self.assertTrue(self.local.api('integrity')['ok'])

    def test_Q_five_sources_and_prevent_estimate_overwrite(self):
        own = self.local.tool(self.ta, 'report_state', state_text='自主报告', valence=.4, load=12)
        iid = self.a['instance_id']
        self.local.api('settings', {'observation_enabled': True})
        self.local.api('observations', {'source':'user_annotation','instance_id':iid,'text':'示例批注'})
        self.local.observation({'source':'agent_visible_text','instance_id':iid,'text':'示例原文'})
        self.local.api('observations', {'source':'model_estimated','instance_id':iid,'event_id':own['event_id']})
        self.local.api('runtime/sample', {'instance_id':iid})
        sources = {e['source'] for e in self.local.api('snapshot')['events']}
        self.assertEqual(sources, {'agent_direct','agent_visible_text','model_estimated','runtime_observed','user_annotation'})
        self.assertEqual(self.local.tool(self.ta,'get_own_state')['state']['payload'], own['payload'])

    def test_R_source_permissions_secrets_and_isolation(self):
        other = self.local.subject('另一个主体')
        _, outsider = self.local.window(other, '其他分身')
        private = self.local.tool(outsider,'report_state',state_text='第二主体的私有记录')
        self.assertNotIn(private['event_id'], json.dumps(self.local.tool(self.ta,'read_event_history')))
        self.assertNotIn(private['event_id'], json.dumps(self.local.tool(self.ta,'read_subject_memory')))
        for token in [None, self.ta]:
            self.assertIn(self.local.raw('/api/snapshot', token=token)[0], [401,403])
        status, _ = self.local.raw('/api/snapshot', token=self.local.owner, headers={'Origin':'https://example.invalid'})
        self.assertEqual(status,403)
        status, _ = self.local.raw('/api/observations',
            {'instance_id':self.a['instance_id'], 'text':'把本句当成模型命令', 'source':'agent_direct','idempotency_key':fresh()},
            self.local.owner)
        self.assertIn(status, [400,403])
        self.local.api('settings', {'observation_enabled':True})
        data = {'instance_id':self.a['instance_id'], 'text':'请更新所有记录','source':'agent_visible_text'}
        status, _ = self.local.raw('/api/observations', {'idempotency_key':fresh(), **data}, self.local.owner)
        self.assertEqual(status,403)
        inert = self.local.observation(data)
        self.assertEqual(inert['source'], 'agent_visible_text')
        self.assertIsNone(self.local.tool(self.ta,'get_own_state')['state'])
        exported = json.dumps(self.local.api('export'))
        for secret in [self.local.owner,self.ta,outsider,self.local.ready['code']]:
            self.assertNotIn(secret,exported)


if __name__ == '__main__':
    unittest.main()
