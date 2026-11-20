"""Subject projections and competing real stdio clients backed by one local service."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest

from acceptance_support import Local, ROOT, ToolFailure, fresh


def stdio_exchange(base_url, token, name, requests, barrier):
    # One independent OS bridge per client. Bound waits allow a protocol failure
    # to terminate the test instead of leaving a blocked reader or child.
    with subprocess.Popen(
        [sys.executable, '-I', str(ROOT / 'packages/mcp-server/stdio.py')],
        env={**os.environ, 'SILICON_AGENT_TOKEN': token, 'SILICON_MCP_URL': base_url + '/mcp'},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8'
    ) as process:
        try:
            barrier.wait(timeout=10)
            initialize = {'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize',
                          'params': {'protocolVersion': '2025-11-25', 'capabilities': {},
                                     'clientInfo': {'name': name, 'version': 'test'}}}
            initialized = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
            discover = {'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}
            batch = [initialize, initialized, discover, *requests]
            out, err = process.communicate(''.join(json.dumps(m) + '\n' for m in batch), timeout=20)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    if process.returncode:
        raise AssertionError(err)
    return {reply['id']: reply['result'] for reply in map(json.loads, out.splitlines())}


class SubjectSummaryTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.local = Local(Path(work.name) / 'data')
        self.addCleanup(self.local.stop)
        self.local.start()
        self.sid = self.local.subject()
        self.windows = [self.local.window(self.sid, name) for name in 'ABC']

    def call(self, index, name, **args):
        return self.local.tool(self.windows[index][1], name, **args)

    def summary(self):
        return self.local.api('snapshot?subject_id=' + self.sid)['subject_summaries'][0]

    def test_explicit_sharing_partial_adoption_disagreement_and_withdrawal(self):
        root = self.call(0, 'report_state', state_text='first, private for now')['event_id']
        self.call(0, 'revise_state', event_id=root, state_text='first, revised')
        self.assertFalse(self.summary()['trend'])
        second = self.call(0, 'report_state', state_text='second', shared_to_subject=True)['event_id']
        self.call(0, 'propose_shared_memory', event_id=root)
        self.call(0, 'revise_state', event_id=root, state_text='corrected early report')
        # A late share or a revision of an older root cannot displace a newer one.
        self.assertEqual(self.summary()['distribution'][0]['report_ids'], [second])
        self.call(1, 'decide_inheritance', event_id=second, decision='partial', note='only the date')
        self.call(2, 'decide_inheritance', event_id=second, decision='disagree')
        self.call(2, 'report_state', state_text='private')
        before = self.summary()
        self.assertEqual(before['common'][0]['event_id'], second)
        self.assertEqual(before['disputed'][0]['event_id'], second)
        withdraw = self.call(0, 'revise_state', event_id=second, operation='withdraw')
        after = self.summary()
        self.assertEqual(after, self.call(2, 'read_subject_memory')['summary'])
        self.assertEqual(after['distribution'][0]['state_text'], 'corrected early report')
        self.assertEqual(after['current_reports'][0]['event_id'], root)
        self.assertEqual(after['trend'][-1]['event_id'], withdraw['event_id'])
        self.assertEqual(after['trend'][-1]['current_report_id'], root)
        self.assertEqual(after['changes'][-1]['event_id'], withdraw['event_id'])
        self.assertEqual((after['common'], after['disputed']), ([], []))
        self.assertEqual(self.call(2, 'get_own_state')['state']['payload']['state_text'], 'private')

    def test_private_revisions_and_withdrawn_roots_do_not_publish(self):
        private = self.call(0, 'report_state', state_text='private-original')
        revision = self.call(0, 'revise_state', event_id=private['event_id'], state_text='private-correction')
        self.call(0, 'revise_state', event_id=private['event_id'], operation='withdraw')
        with self.assertRaisesRegex(ToolFailure, 'WITHDRAWN'):
            self.call(0, 'propose_shared_memory', event_id=private['event_id'])
        public = json.dumps(self.call(1, 'read_subject_memory'))
        for hidden in ('private-original', 'private-correction', private['event_id'], revision['event_id']):
            self.assertNotIn(hidden, public)

        shared = self.call(0, 'report_state', state_text='published', shared_to_subject=True)
        root = shared['event_id']
        def propose(note):
            return self.call(0, 'propose_shared_memory', event_id=root, note=note)
        with ThreadPoolExecutor(max_workers=2) as executor:
            extra = list(executor.map(propose, ('first note', 'second note')))
        memory = self.call(2, 'read_subject_memory')
        self.assertEqual(memory['proposals'][0]['proposal_id'], max(extra, key=lambda e:e['seq'])['event_id'])
        self.assertTrue({e['event_id'] for e in extra} <= {e['event_id'] for e in memory['events']})
        self.assertEqual(len(memory['summary']['trend']), 1)
        self.assertEqual(memory['summary']['distribution'][0]['count'], 1)
        self.call(0, 'revise_state', event_id=root, operation='withdraw')
        with self.assertRaisesRegex(ToolFailure, 'WITHDRAWN'):
            propose('too late')
        self.assertEqual(self.summary()['distribution'], [])

    def test_subject_scope_equal_labels_and_reports_without_text(self):
        self.call(0, 'report_state', state_text='exact', shared_to_subject=True)
        self.call(1, 'report_state', state_text='exact', shared_to_subject=True)
        dim = self.call(2, 'report_state', valence=0, shared_to_subject=True)
        other = self.local.subject('outside')
        _, token = self.local.window(other, 'A')
        self.local.tool(token, 'report_state', state_text='outside', shared_to_subject=True)
        results = {s['subject_id']: s for s in self.local.api('snapshot')['subject_summaries']}
        self.assertEqual({r['state_text']: r['count'] for r in results[self.sid]['distribution']},
                         {'exact': 2, None: 1})
        self.assertEqual(results[other]['distribution'][0]['state_text'], 'outside')
        self.assertEqual(len(results[other]['current_reports']), 1)
        self.assertNotIn('outside', json.dumps(self.call(0, 'read_subject_memory')))
        self.assertEqual(results[self.sid]['current_reports'][0]['event_id'], dim['event_id'])

    def test_three_stdio_processes_share_branch_replay_and_reconnect(self):
        labels = ['有些难过', '很开心', '不确定']

        def parallel(write):
            barrier = Barrier(3)
            def client(index):
                name = 'fixture-' + 'ABC'[index]
                if write:
                    args = {'state_text': labels[index], 'shared_to_subject': True,
                            'idempotency_key': fresh()}
                    calls = [('report', 'report_state', args), ('replay', 'report_state', args)]
                    if index == 0:
                        calls.append(('other', 'report_state', {'state_text': 'private extra',
                                                                 'idempotency_key': fresh()}))
                else:
                    calls = [('memory', 'read_subject_memory', {})]
                messages = [{'jsonrpc': '2.0', 'id': rid, 'method': 'tools/call',
                             'params': {'name': action, 'arguments': args}}
                            for rid, action, args in calls]
                return stdio_exchange(self.local.base, self.windows[index][1], name, messages, barrier)
            with ThreadPoolExecutor(max_workers=3) as executor:
                return list(executor.map(client, range(3)))

        writes = parallel(True)
        for i, reply in enumerate(writes):
            self.assertEqual(reply['init']['protocolVersion'], '2025-11-25')
            self.assertIn('report_state', [tool['name'] for tool in reply['list']['tools']])
            result = reply['report']['structuredContent']
            self.assertEqual(result, reply['replay']['structuredContent'])
            self.assertEqual(result['instance_id'], self.windows[i][0]['instance_id'])
        before = self.summary()
        self.assertEqual({r['state_text']: r['count'] for r in before['distribution']},
                         dict.fromkeys(labels, 1))
        self.assertEqual(len(before['current_reports']), 3)
        self.assertEqual(len(before['trend']), 3)
        snapshot = self.local.api('snapshot')
        self.assertEqual(len(snapshot['events']), 7)  # 4 reports and 3 share events.
        self.assertEqual(self.local.api('integrity'), {'ok': True, 'events': 7, 'errors': []})
        backup = self.local.api('backup', {})
        self.local.stop()
        self.local.start()
        for reply in parallel(False):
            self.assertEqual(reply['memory']['structuredContent']['summary'], before)
        # Recompute from a managed backup after an additional committed write.
        self.call(1, 'report_state', state_text='later', shared_to_subject=True)
        self.local.api('restore', {'backup_id': backup['backup_id']})
        self.assertEqual(self.summary(), before)
        self.assertEqual(self.local.api('snapshot')['events'], snapshot['events'])
        self.assertTrue(self.local.api('integrity')['ok'])
