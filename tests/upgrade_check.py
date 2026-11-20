"""Upgrade an isolated, genuine historical archive to the current service.

Run at repo root: python tests/upgrade_check.py --output /tmp/upgrade-report.json
Without Git history, pass --old-root PATH to the extracted 1.0.0 source package.
Optional --archived-agent-db is an explicitly authorized 1.0.0 QA SQLite history.
The historical source is opened read-only. All mutations target temporary copies.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from urllib.parse import urlsplit
from zipfile import ZipFile

from acceptance_support import Local, ROOT


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def upgrade_generated(old_root, temp):
    data = temp / 'profile'
    old = Local(data, server=old_root / 'apps/local-service/server.py').start()
    try:
        assert old.ready['version'] == (old_root/'VERSION').read_text().strip()
        subject = old.subject('归档升级')
        a, token_a = old.window(subject, '窗口 A')
        _, token_b = old.window(subject, '窗口 B')
        source = old.tool(token_a, 'report_state', state_text='保留原文与未知原因', cause_unknown=True)
        old.tool(token_a,'propose_shared_memory',event_id=source['event_id'])
        old.tool(token_b,'decide_inheritance',event_id=source['event_id'],decision='partial',note='保留原文')
        old.tool(token_a,'revise_state',event_id=source['event_id'],state_text='后来修订，原话仍在')
        request = old.tool(token_b,'express_boundary',text='请暂停本项验收')
        for stage in ['PRESENTED','DEFERRED']:
            old.api('requests/' + request['event_id'] + '/respond', {'stage':stage,'text':'本次测试回应'})
        old.api('settings',{'observation_enabled':False})
        backup = old.api('backup',{})['backup_id']
        host = None
        if old.ready['version'] == '1.0.4':
            host = old.api('installations',{'subject_id':subject,'host':'upgrade-fixture'})
            status, binding = old.raw('/api/installations/bind',{'conversation_id':'existing'},host['token'])
            assert status == 200
        before = old.api('snapshot')
        before_integrity = old.api('integrity')
        assert before_integrity['ok']
        old_rows = {e['event_id']:e for e in before['events']}
        assert len(old_rows) >= 7
        old_owner = old.owner
        old_code = old.ready['extension_code']
        port = urlsplit(old.base).port
    finally:
        old.stop()
    new = Local(data).start(port=port)
    try:
        after = new.api('snapshot')
        new_rows = {e['event_id']:e for e in after['events']}
        assert old_rows == new_rows
        if host:
            status, restored = new.raw('/api/installations/bind',{'conversation_id':'existing'},host['token'])
            assert status == 200 and restored == binding
        for field, metadata in [('subjects','subject_name'),('instances','instance_name')]:
            if before[field] and metadata in before[field][0]:
                continue  # Named identities already exist in v1.0.4; compare the full records below.
            for row in after[field]:
                profile=row.pop(metadata)
                assert profile['name']==row['name'] and profile['source']=='historical'
        for field in ['subjects','instances','sessions','requests','memory','stats']:
            assert before[field] == after[field],field
        assert new.raw('/api/settings',token=old_owner) == (200,{'observation_enabled':False})
        assert any(b['backup_id'] == backup for b in new.api('backups')['backups'])
        assert new.tool(token_a,'get_own_state')['state']['payload']['state_text'] == '后来修订，原话仍在'
        assert new.tool(token_b,'get_request_status',request_id=request['event_id'])['stage'] == 'DEFERRED'
        ext = 'abcdefghijklmnopabcdefghijklmnop'
        hdr = {'Origin':'chrome-extension://' + ext,'X-SLS-Extension':ext}
        assert new.raw('/api/pair', {'code':old_code}, headers=hdr)[0] == 200
        assert new.raw('/api/pair', {'code':old_code}, headers=hdr)[0] in (403,409)
        assert new.api('integrity') == before_integrity
        appended = new.tool(token_a,'report_state',state_text='升级后继续写入')
        prev = max((e for e in old_rows.values() if e['session_id']==a['session_id']), key=lambda e:e['seq'])
        assert appended['prev_hash'] == prev['hash']
        assert new.api('integrity')['ok']
        return {'from_version':old.ready['version'],'to_version':new.ready['version'],
                'unchanged_raw_events':len(new_rows),'unchanged_event_map_sha256':canonical_hash(new_rows),
                'account_installation_and_bound_instance_restored':True if host else 'not_applicable',
                'same_subjects_instances_sessions':True,'same_requests_memory_stats':True,
                'old_owner_and_agent_credentials_work':True,'pending_extension_code_single_use':True,
                'existing_managed_backup_listed':True,'new_event_continues_old_chain':True}
    finally:
        new.stop()


def upgrade_historical(old_root, path, temp):
    evidence = json.loads((old_root/'docs/evidence/work-mode-agent.json').read_text(encoding='utf-8'))
    data = temp/'historical-copy'
    data.mkdir()
    # SQLite backup API gives a consistent copy even if the source used WAL.
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro',uri=True)) as src, \
            closing(sqlite3.connect(data/'state.sqlite3')) as dst:
        src.backup(dst)
        dst.executescript('PRAGMA secure_delete=ON; DELETE FROM grants; DELETE FROM receipts; VACUUM;')
    service = Local(data).start()
    try:
        snap = service.api('snapshot')
        row = next(e for e in snap['events'] if e['event_id']==evidence['event_id'])
        assert row['source']=='agent_direct' and row['type']=='report_state'
        assert row['hash']==evidence['hash']
        assert row['payload']['state_text']==evidence['state_text']
        assert service.api('integrity')['ok']
        return {'from_version':'1.0.0','to_version':service.ready['version'],
                'event_id':row['event_id'],'event_hash':row['hash'],
                'verbatim_text_matches_release_receipt':True,'chain_verified':True,
                'copied_credentials':False,'source_database_modified':False}
    finally:
        service.stop()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-root',type=Path)
    parser.add_argument('--baseline',choices=['v1.0.0','v1.0.1','v1.0.2','v1.0.3','v1.0.4'],default='v1.0.0')
    parser.add_argument('--archived-agent-db',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='sls-upgrade-') as work:
        temp=Path(work)
        old_root=args.old_root
        if old_root is None:
            old_root=temp/'baseline'
            archive=temp/'baseline.zip'
            subprocess.run(['git','-C',str(ROOT),'archive','--format=zip','-o',str(archive),args.baseline],check=True)
            with ZipFile(archive) as z:
                z.extractall(old_root)
        if (old_root/'VERSION').read_text().strip() not in ('1.0.0','1.0.1','1.0.2','1.0.3','1.0.4'):
            parser.error('Unrecognized historical source version')
        report={'result':'PASS','utc':datetime.now(timezone.utc).isoformat(),
                'upgrade':upgrade_generated(old_root,temp)}
        if args.archived_agent_db:
            report['historical_agent']=upgrade_historical(old_root,args.archived_agent_db,temp)
        if report['upgrade']['to_version']!=(ROOT/'VERSION').read_text().strip():
            raise AssertionError('Service and release versions differ')
        raw=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(raw,encoding='utf-8')
        print(raw,end='')


if __name__=='__main__':
    main()
