"""Focused domain regressions beyond the HTTP acceptance suite.

Run: python -m unittest packages.core.test_invariants -v
"""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from uuid import uuid4

from .store import DomainError, READS, Store


class DomainInvariants(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.s = Store(self.home)
        self.subject = self.owner('create_subject',name='Scope')
        self.tokens = []
        self.windows = []
        for label in ('A','B','C'):
            token = self.owner('issue_agent',subject_id=self.subject['subject_id'])['token']
            self.tokens.append(token)
            self.windows.append(self.call(token,'register_instance',name=label))

    def call(self,token,action,**args):
        if action not in READS:
            args.setdefault('idempotency_key',uuid4().hex)
        return self.s.tool(token,action,args)

    def owner(self,action,**args):
        if action not in READS:
            args.setdefault('idempotency_key',uuid4().hex)
        return self.s.admin(action,args)

    def assert_error(self,code,fn,*args,**kw):
        with self.assertRaises(DomainError) as context:
            fn(*args,**kw)
        self.assertEqual(context.exception.code,code)

    def test_partial_agreement_names_adopted_part_and_revisions_require_new_consent(self):
        a,b,c=self.tokens
        report=self.call(a,'report_state',state_text='Cloud cover and rain.',shared_to_subject=True)
        root=report['event_id']
        first=self.call(b,'decide_inheritance',event_id=root,decision='partial',note='Cloud cover only.')
        self.call(c,'decide_inheritance',event_id=root,decision='disagree')
        before=self.call(b,'read_subject_memory')
        self.assertEqual(before['common'][0]['adoption_scope'],'partial')
        self.assertEqual(before['common'][0]['adoptions'][0]['payload']['note'],'Cloud cover only.')
        self.assertEqual(before['common'][0]['adoptions'][0]['event_id'],first['event_id'])
        self.assertEqual(before['disputed'][0]['event_id'],root)
        revision=self.call(a,'revise_state',event_id=root,state_text='The sky cleared.')
        after=self.call(b,'read_subject_memory')
        self.assertEqual(after['common'],[])
        self.assertEqual(after['disputed'],[])
        self.assertEqual(len(after['proposals'][0]['prior_version_decisions']),2)
        self.assertTrue(all(not x['is_current_version'] for x in after['decisions']))
        self.assert_error('STALE_VERSION',self.call,b,'decide_inheritance',event_id=root,decision='adopt')
        self.call(b,'decide_inheritance',event_id=root,expected_version_id=revision['event_id'],decision='adopt')
        self.assertEqual(self.call(a,'read_subject_memory')['common'][0]['adoption_scope'],'full')
        self.assertEqual(self.call(b,'get_own_state')['state'],None)
        snap=self.owner('snapshot',subject_id=self.subject['subject_id'])
        self.assertEqual(snap['report_states'][0]['revision_id'],revision['event_id'])
        self.call(a,'revise_state',event_id=root,operation='withdraw')
        snap=self.owner('snapshot',subject_id=self.subject['subject_id'])
        self.assertEqual(snap['report_states'],[])
        self.assertIn(root,{e['event_id'] for e in snap['events']})

    def test_rotated_session_deletion_purges_cross_session_dependents_only(self):
        a,b,c=self.tokens
        marker='sensitive-'+uuid4().hex
        root=self.call(a,'report_state',state_text=marker,shared_to_subject=True)
        b_first=self.call(b,'report_state',state_text='first valid')
        self.call(b,'decide_inheritance',event_id=root['event_id'],decision='partial',note=marker)
        b_key=uuid4().hex
        b_last=self.call(b,'report_state',state_text='second valid',idempotency_key=b_key)
        new_session=self.call(a,'start_session')
        self.assertEqual(new_session['instance_id'],self.windows[0]['instance_id'])
        keep=self.call(a,'report_state',state_text='same window other session')
        self.owner('backup')
        erase=self.owner('delete_session',session_id=self.windows[0]['session_id'])
        self.assertEqual(erase['purged_backups'],1)
        export=self.owner('export')
        self.assertEqual({r['event_id'] for r in export['events']},{keep['event_id'],b_last['event_id'],b_first['event_id']})
        self.assert_error('UNAUTHENTICATED',self.call,a,'get_own_state')
        self.assertTrue(self.owner('verify')['ok'])
        replay=self.call(b,'report_state',state_text='second valid',idempotency_key=b_key)
        active=next(e for e in export['events'] if e['event_id']==b_last['event_id'])
        self.assertEqual(replay['hash'],active['hash'])
        self.assertEqual(self.owner('list_backups')['backups'],[])
        for path in self.home.rglob('*'):
            if path.is_file():
                self.assertNotIn(marker.encode(),path.read_bytes())

    def test_damaged_managed_backup_is_rejected_before_live_state_changes(self):
        a=self.tokens[0]
        self.call(a,'report_state',state_text='before')
        backup=self.owner('backup')
        latest=self.call(a,'report_state',state_text='after')
        path=self.home/'backups'/(backup['backup_id']+'.sqlite3')
        with path.open('r+b') as stream:
            stream.write(b'DAMAGED')
        self.assert_error('INVALID_BACKUP',self.owner,'restore',backup_id=backup['backup_id'])
        self.assertEqual(self.call(a,'get_own_state')['state']['event_id'],latest['event_id'])
        self.assertTrue(self.owner('verify')['ok'])

    def test_interrupted_postcommit_erasure_finishes_on_reopen(self):
        marker='retry-'+uuid4().hex
        self.call(self.tokens[0],'report_state',state_text=marker)
        key=uuid4().hex
        with patch.object(self.s.files,'finish_erasure',side_effect=OSError('transient disk error')):
            self.assert_error('STORAGE_ERROR',self.owner,'delete_session',session_id=self.windows[0]['session_id'],
                              idempotency_key=key)
        self.assertTrue((self.home/'erasure.pending').exists())
        self.s=Store(self.home)
        replay=self.owner('delete_session',session_id=self.windows[0]['session_id'],idempotency_key=key)
        self.assertTrue(replay['deleted'])
        self.assertFalse((self.home/'erasure.pending').exists())
        for path in self.home.rglob('*'):
            if path.is_file():
                self.assertNotIn(marker.encode(),path.read_bytes())

    def test_old_delete_all_retry_preserves_new_data(self):
        first=uuid4().hex
        self.owner('delete_all',idempotency_key=first)
        self.owner('create_subject',name='intermediate')
        self.owner('delete_all')
        final=self.owner('create_subject',name='new after erasures')
        self.owner('delete_all',idempotency_key=first)
        self.assertEqual(self.owner('list_subjects')['subjects'],[final])

    def test_restore_does_not_resurrect_revoked_grant(self):
        issue=self.owner('issue_agent',subject_id=self.subject['subject_id'])
        self.call(issue['token'],'register_instance',name='Short lived')
        backup=self.owner('backup')
        self.owner('revoke_agent',grant_id=issue['grant_id'])
        recovered=self.owner('restore',backup_id=backup['backup_id'])
        self.assertEqual(recovered['revoked_grants'],1)
        self.assert_error('UNAUTHENTICATED',self.call,issue['token'],'get_own_state')
        self.assertEqual(self.call(self.tokens[0],'get_own_state')['instance_id'],self.windows[0]['instance_id'])
        # Alternating restore points keeps destructive replay receipts. A lost
        # HTTP reply cannot rewind twice and discard intervening recovered data.
        newer=self.call(self.tokens[0],'report_state',state_text='new checkpoint')
        later=self.owner('backup')
        old_key=uuid4().hex
        self.owner('restore',backup_id=backup['backup_id'],idempotency_key=old_key)
        self.owner('restore',backup_id=later['backup_id'])
        self.owner('restore',backup_id=backup['backup_id'],idempotency_key=old_key)
        self.assertEqual(self.call(self.tokens[0],'get_own_state')['state']['event_id'],newer['event_id'])

if __name__=='__main__':
    unittest.main()
