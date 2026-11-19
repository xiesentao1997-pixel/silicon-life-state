"""Authenticated local state ledger. All writers share the same SQLite and OS lock."""
import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from . import projections as view
from .storage import Files, event_hash, verify_db
from .validation import (DomainError, META, READS, REPORT, canonical, digest, fail,
                         now, uid, validate)

STAGES = {
    'CREATED': {'PRESENTED'},
    'PRESENTED': {'ACCEPTED','DECLINED','DEFERRED'},
    'DEFERRED': {'ACCEPTED','DECLINED','NOT_EXECUTED'},
    'ACCEPTED': {'EXECUTED','NOT_EXECUTED'},
    'DECLINED': {'NOT_EXECUTED'},
    'EXECUTED': {'FOLLOW_UP'},
    'NOT_EXECUTED': {'FOLLOW_UP'},
    'FOLLOW_UP': {'FOLLOW_UP'},
}
OWNER = 'local_owner'


def _row(db, sql, params=(), message='Record not found.'):
    row = db.execute(sql,params).fetchone()
    if row is None:
        fail('NOT_FOUND',message,404)
    return dict(row)


def _subject(db, sid):
    return _row(db,'SELECT * FROM subjects WHERE subject_id=?',(sid,))


def _instance(db, iid):
    return _row(db,'''SELECT i.*, (SELECT session_id FROM sessions s WHERE s.instance_id=i.instance_id
                    ORDER BY s.rowid DESC LIMIT 1) AS session_id FROM instances i WHERE instance_id=?''',(iid,))


def _event(db, eid):
    return view.event_dict(_row(db,'SELECT * FROM events WHERE event_id=?',(eid,)))


def _events(db, field=None, value=None):
    columns = {None:'','subject_id':' WHERE subject_id=?','instance_id':' WHERE instance_id=?',
               'session_id':' WHERE session_id=?'}
    rows = db.execute('SELECT * FROM events' + columns[field] + ' ORDER BY seq', (value,) if field else ())
    return [view.event_dict(r) for r in rows]


def _create_subject(db, name):
    row = {'subject_id':uid('sub'),'name':name,'created_at':now(),'level':1}
    db.execute('INSERT INTO subjects VALUES(:subject_id,:name,:created_at,:level)',row)
    return row


def _new_session(db, iid):
    db.execute('INSERT INTO sessions VALUES(?,?,?)',(uid('ses'),iid,now()))
    return _instance(db,iid)


def _create_instance(db, sid, name):
    _subject(db,sid)
    iid = uid('ins')
    db.execute('INSERT INTO instances VALUES(?,?,?,?)',(iid,sid,name,now()))
    return _new_session(db,iid)


def _credentials(db, token):
    if not isinstance(token,str) or not token.isascii() or len(token)>128:
        fail('UNAUTHENTICATED','Invalid agent credential.',401)
    row = db.execute('SELECT grant_id,subject_id,instance_id FROM grants WHERE digest=?',(digest(token),)).fetchone()
    if row is None:
        fail('UNAUTHENTICATED','Invalid or revoked agent credential.',401)
    return dict(row)


def _append(db, instance, kind, source, actor, args, related=()):
    if not instance['session_id']:
        fail('NO_SESSION','Start or register a session first.',409)
    last = db.execute('SELECT hash,version FROM events WHERE session_id=? ORDER BY seq DESC LIMIT 1',
                      (instance['session_id'],)).fetchone()
    payload = {k:v for k,v in args.items() if k not in META | {'idempotency_key'}}
    event = {k:instance[k] for k in ('subject_id','instance_id','session_id')}
    event.update(event_id=uid('evt'),type=kind,source=source,actor=actor,created_at=now(),
                 payload=canonical(payload),related=canonical(list(dict.fromkeys(related))),
                 adapter_version=args.get('adapter_version'),model_version=args.get('model_version'),
                 version=last['version']+1 if last else 1,prev_hash=last['hash'] if last else '',hash='')
    cur = db.execute('''INSERT INTO events(event_id,subject_id,instance_id,session_id,type,source,actor,
                      created_at,payload,related,model_version,adapter_version,prev_hash,hash,version)
                      VALUES(:event_id,:subject_id,:instance_id,:session_id,:type,:source,:actor,:created_at,
                      :payload,:related,:model_version,:adapter_version,:prev_hash,:hash,:version)''',event)
    event['seq'] = cur.lastrowid
    event['hash'] = event_hash(event)
    db.execute('UPDATE events SET hash=? WHERE seq=?',(event['hash'],event['seq']))
    return view.event_dict(event)


def _readable(db, instance, eid):
    ev = _event(db,eid)
    if ev['subject_id'] != instance['subject_id']:
        fail('FORBIDDEN','Event outside authorized subject.',403)
    if ev['instance_id']!=instance['instance_id']:
        shared = view.memory_view(_events(db,'subject_id',instance['subject_id']))['events']
        if not any(r['event_id']==eid for r in shared):
            fail('FORBIDDEN','This event has not been shared.',403)
    return ev


def _references(db, instance, args):
    links=[]
    for field in ('interaction_reference','request_id'):
        if field in args:
            ev = _readable(db,instance,args[field])
            if field=='request_id' and ev['type'] not in view.REQUESTS:
                fail('INVALID_REFERENCE','request_id must refer to a request.')
            links.append(ev['event_id'])
    return links


def _owned_root(db, instance, eid):
    ev = _event(db,eid)
    if ev['instance_id']!=instance['instance_id']:
        fail('FORBIDDEN','Only the authoring instance may edit or share this event.',403)
    return ev


def _request(db, rid):
    original = _event(db,rid)
    if original['type'] not in view.REQUESTS:
        fail('INVALID_REFERENCE','Event is not a request.')
    return view.request_views(_events(db,'instance_id',original['instance_id']))[rid]


def _advance_request(db, request, stage, actor, args, agent):
    original = request['original']
    if stage not in STAGES[request['stage']]:
        fail('INVALID_TRANSITION',f"Cannot move from {request['stage']} to {stage}.",409)
    if agent and stage not in {'EXECUTED','NOT_EXECUTED','FOLLOW_UP'}:
        fail('FORBIDDEN','User decisions require owner authorization.',403)
    if stage in {'EXECUTED','FOLLOW_UP'} and not args.get('text'):
        fail('MISSING_FIELD','Describe the observed action or follow-up.')
    level = _subject(db,original['subject_id'])['level']
    if stage=='EXECUTED' and level < (3 if original['type']=='request_adjustment' else 2):
        fail('LEVEL_REQUIRED','This execution requires an enabled adjustment level.',409)
    result = _append(db,_instance(db,original['instance_id']),
                     'record_strategy' if agent else 'respond',
                     'agent_direct' if agent else 'user_annotation', actor,args,
                     [original['event_id'],request['history'][-1]['event_id']])
    return result if agent else _request(db,original['event_id'])


def _snapshot(db, sid=None):
    if sid:
        _subject(db,sid)
    filt,params = (' WHERE subject_id=?',(sid,)) if sid else ('',())
    subjects = [dict(r) for r in db.execute('SELECT * FROM subjects'+filt+' ORDER BY rowid',params)]
    instances = [_instance(db,r[0]) for r in db.execute('SELECT instance_id FROM instances'+filt+' ORDER BY rowid',params)]
    sessions = [dict(r) for r in db.execute('''SELECT s.*,i.subject_id FROM sessions s JOIN instances i
         ON i.instance_id=s.instance_id'''+(' WHERE i.subject_id=?' if sid else '')+' ORDER BY s.rowid',params)]
    events = _events(db,'subject_id',sid) if sid else _events(db)
    effective = view.reports(events)
    states = view.latest_states(effective)
    for inst in instances:
        inst['state'] = states.get(inst['instance_id'])
    report_states=[ev for ev in reversed(effective.values()) if ev['type']=='report_state']
    return {'subjects':subjects,'instances':instances,'sessions':sessions,'events':events[::-1],
            'report_states':report_states,
            'requests':list(view.request_views(events).values())[::-1],'memory':view.memory_view(events),
            'stats':{'confirmed_hostile':view.hostile_count(effective)},'generated_at':now()}


def _receipt(db, actor, action, args):
    key = digest(args['idempotency_key'])
    sign = digest(canonical([action,args]))
    row = db.execute('SELECT digest,result FROM receipts WHERE actor=? AND key=?',(actor,key)).fetchone()
    if row is None:
        return key,sign,None
    if row['digest']!=sign:
        fail('IDEMPOTENCY_CONFLICT','That key belongs to different input.',409)
    return key,sign,json.loads(row['result'])


class Store:
    def __init__(self, data_dir):
        self.files = Files(data_dir)

    def authenticate_agent(self, token):
        with self._guard(), self.files.connect() as db:
            return _credentials(db,token)

    @contextlib.contextmanager
    def _guard(self):
        with self.files.lock():
            try:
                yield
            except sqlite3.IntegrityError as exc:
                raise DomainError('CONFLICT','The operation conflicts with existing data.',409) from exc
            except sqlite3.DatabaseError as exc:
                raise DomainError('DATABASE_ERROR','Could not read or write the local database. Verify or restore a backup.',503) from exc
            except OSError as exc:
                raise DomainError('STORAGE_ERROR','The requested local storage operation failed.',503) from exc

    def tool(self, token, name, args):
        return self._dispatch(False,token,name,args)

    def admin(self, action, args):
        return self._dispatch(True,None,action,args)

    def _dispatch(self, owner, token, action, args):
        validate(action,args,owner)
        with self._guard():
            if owner and action in {'backup','restore','list_backups'}:
                return self._maintenance(action,args)
            with self.files.connect() as db:
                db.execute('BEGIN' if action in READS else 'BEGIN IMMEDIATE')
                grant = None if owner else _credentials(db,token)
                actor = OWNER if owner else grant['grant_id']
                if action not in READS:
                    key,sign,result = _receipt(db,actor,action,args)
                    if result is not None:
                        db.commit()
                        if action.startswith('delete_'):
                            self.files.finish_erasure(db)
                        return self._deliver(db,action,result)
                if owner:
                    result = self._owner(db,action,args)
                else:
                    result = self._agent(db,grant,action,args)
                if action not in READS:
                    db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)',(actor,key,action,sign,canonical(result)))
                db.commit()
                if action.startswith('delete_'):
                    self.files.finish_erasure(db)
                return self._deliver(db,action,result)

    def _grant_token(self,gid):
        return 'sls_'+hmac.new(self.files.key,gid.encode(),hashlib.sha256).hexdigest()

    def _deliver(self,db,action,result):
        if action=='issue_agent':
            if not db.execute('SELECT 1 FROM grants WHERE grant_id=?',(result['grant_id'],)).fetchone():
                fail('CREDENTIAL_REVOKED','This credential has already been revoked.',410)
            return {**result,'token':self._grant_token(result['grant_id'])}
        return result

    def _agent(self,db,grant,action,args):
        sid,iid,actor = grant['subject_id'],grant['instance_id'],grant['grant_id']
        if action=='register_subject':
            if sid:
                return _subject(db,sid)
            subject = _create_subject(db,args['name'])
            db.execute('UPDATE grants SET subject_id=? WHERE grant_id=?',(subject['subject_id'],actor))
            return subject
        if not sid:
            fail('SUBJECT_REQUIRED','Register a subject before using this credential.',409)
        if action=='register_instance':
            if iid:
                instance = _instance(db,iid)
                return instance if instance['session_id'] else _new_session(db,iid)
            instance = _create_instance(db,sid,args['name'])
            db.execute('UPDATE grants SET instance_id=? WHERE grant_id=?',(instance['instance_id'],actor))
            return instance
        if not iid:
            fail('INSTANCE_REQUIRED','Register your instance first.',409)
        instance = _instance(db,iid)
        if action=='start_session':
            return _new_session(db,iid)
        if action=='get_own_state':
            states = view.latest_states(view.reports(_events(db,'instance_id',iid)))
            return {**instance,'state':states.get(iid)}
        if action=='read_subject_memory':
            return {'subject_id':sid,**view.memory_view(_events(db,'subject_id',sid))}
        if action=='read_event_history':
            limit = args.get('limit',100)
            result = list(db.execute('SELECT * FROM events WHERE instance_id=? AND seq<? ORDER BY seq DESC LIMIT ?',
                                     (iid,args.get('before',2**63-1),limit+1)))
            events=[view.event_dict(r) for r in result[:limit]]
            return {'events':events,'next_before':events[-1]['seq'] if len(result)>limit else None}
        if action in {'get_request_status','record_strategy'}:
            req = _request(db,args['request_id'])
            if req['original']['instance_id']!=iid:
                fail('FORBIDDEN','Request belongs to a different instance.',403)
            if action=='get_request_status':
                return req
            return _advance_request(db,req,args['stage'],actor,args,True)
        links = _references(db,instance,args)
        if action=='revise_state':
            root = _owned_root(db,instance,args['event_id'])
            if root['type'] not in {'report_state','assess_interaction'}:
                fail('INVALID_REFERENCE','Only original reports and assessments can be revised.')
            changes = set(args) & (REPORT | {'assessment','reason'})
            if not changes and args.get('operation')!='withdraw':
                fail('EMPTY_REVISION','Specify corrected content, a clarification, or a withdrawal.')
            if 'assessment' in args and root['type']!='assess_interaction':
                fail('INVALID_REFERENCE','An assessment can only revise an interaction judgment.')
            previous = [r for r in _events(db,'instance_id',iid) if r['type']=='revise_state' and r['related'][0]==root['event_id']]
            version_id=previous[-1]['event_id'] if previous else root['event_id']
            if args.get('expected_version_id',version_id)!=version_id:
                fail('STALE_VERSION','Read the latest revision before revising.',409)
            if previous and previous[-1]['payload'].get('operation')=='withdraw':
                fail('WITHDRAWN','A withdrawn report is closed; submit a new report.',409)
            links = [root['event_id']] + ([previous[-1]['event_id']] if previous else []) + links
        elif action=='propose_shared_memory':
            root = _owned_root(db,instance,args['event_id'])
            if root['type'] not in {'report_state','assess_interaction','express_boundary','request_adjustment'}:
                fail('INVALID_REFERENCE','Select an original report, assessment, or request.')
            links = [root['event_id']]
        elif action=='decide_inheritance':
            root = _readable(db,instance,args['event_id'])
            if root['type']=='propose_shared_memory':
                root = _event(db,root['related'][0])
            memory = view.memory_view(_events(db,'subject_id',sid))
            proposal = next((ev for ev in memory['proposals'] if ev['event_id']==root['event_id']),None)
            if not proposal:
                fail('NOT_SHARED','No current proposal for this event.',409)
            version_id=proposal.get('revision_id',root['event_id'])
            if args.get('expected_version_id',root['event_id'])!=version_id:
                fail('STALE_VERSION','Read the latest proposal and pass its revision_id.',409)
            links = [root['event_id'],proposal['proposal_id']]
            if proposal.get('revision_id'):
                links.append(proposal['revision_id'])
        result = _append(db,instance,action,'agent_direct',actor,args,links)
        if action=='report_state' and args.get('shared_to_subject'):
            _append(db,instance,'propose_shared_memory','agent_direct',actor,{'event_id':result['event_id']},[result['event_id']])
        return result

    def _owner(self,db,action,args):
        if action in {'snapshot','export'}:
            return _snapshot(db,args.get('subject_id'))
        if action=='verify':
            return verify_db(db)
        if action=='create_subject':
            return _create_subject(db,args['name'])
        if action=='create_instance':
            return _create_instance(db,args['subject_id'],args['name'])
        if action=='issue_agent':
            sid,iid = args.get('subject_id'),args.get('instance_id')
            if iid:
                inst = _instance(db,iid)
                if sid and inst['subject_id']!=sid:
                    fail('SCOPE_CONFLICT','Instance and subject do not match.',409)
                sid=inst['subject_id']
                if db.execute('SELECT 1 FROM grants WHERE instance_id=?',(iid,)).fetchone():
                    fail('ALREADY_BOUND','Revoke the existing instance credential before replacing it.',409)
            if sid:
                _subject(db,sid)
            gid = uid('grt')
            db.execute('INSERT INTO grants VALUES(?,?,?,?,?)',(gid,digest(self._grant_token(gid)),sid,iid,now()))
            return {'grant_id':gid,'subject_id':sid,'instance_id':iid}
        if action=='list_subjects':
            return {'subjects':[dict(r) for r in db.execute('SELECT * FROM subjects ORDER BY rowid')]}
        if action=='list_agents':
            rows=db.execute('SELECT grant_id,subject_id,instance_id,created_at FROM grants ORDER BY rowid DESC')
            return {'grants':[dict(r) for r in rows]}
        if action=='revoke_agent':
            gid = args['grant_id']
            cur = db.execute('DELETE FROM grants WHERE grant_id=?',(gid,))
            if not cur.rowcount:
                fail('NOT_FOUND','Credential not found.',404)
            db.execute('DELETE FROM receipts WHERE actor=?',(gid,))
            return {'revoked':True,'grant_id':gid}
        if action=='set_level':
            _subject(db,args['subject_id'])
            db.execute('UPDATE subjects SET level=? WHERE subject_id=?',(args['level'],args['subject_id']))
            return _subject(db,args['subject_id'])
        if action=='respond':
            return _advance_request(db,_request(db,args['request_id']),args['stage'],OWNER,args,False)
        if action.startswith('delete_'):
            return self._erase(db,action,args)
        instance = _instance(db,args['instance_id'])
        links = _references(db,instance,args)
        if action in {'observe','annotate','runtime'}:
            source = {'observe':'agent_visible_text','annotate':'user_annotation','runtime':'runtime_observed'}[action]
            return _append(db,instance,action,source,'local_runtime' if action=='runtime' else OWNER,args,links)
        if action=='sample_runtime':
            start=time.perf_counter_ns()
            count = db.execute('SELECT count(*) FROM events WHERE instance_id=?',(instance['instance_id'],)).fetchone()[0]
            elapsed=(time.perf_counter_ns()-start)/1e6
            payload={**args,'text':'SQLite local instance event-count query.',
                     'metrics':{'instance_event_count':count,'query_elapsed_ms':elapsed}}
            return _append(db,instance,'runtime','runtime_observed','local_runtime',payload,links)
        if action=='estimate':
            root = _owned_root(db,instance,args['event_id'])
            effective = view.reports(_events(db,'instance_id',instance['instance_id'])).get(root['event_id'])
            if not effective or root['type']!='report_state' or 'valence' not in effective['payload']:
                fail('MISSING_OBSERVATION','A current report with valence is required.')
            vals = effective['payload']
            if 'alpha' not in args and 'load' not in vals:
                fail('MISSING_OBSERVATION','Supply alpha or choose a report with load.')
            alpha = args['alpha'] if 'alpha' in args else 0.25/(1 + vals['load']/60)
            inputs={'valence':vals['valence']}
            if 'load' in vals:
                inputs['load']=vals['load']
            payload={**args,'alpha':alpha,'inputs':inputs,'valence':vals['valence']*(1-alpha),
                     'formula':'v + alpha * (0 - v)','steps':1}
            links = [root['event_id']]
            if effective.get('revision_id'):
                links.append(effective['revision_id'])
            return _append(db,instance,action,'model_estimated','local_estimator',payload,links)
        fail('UNKNOWN_ACTION','Unknown owner action.',404)

    def _erase(self,db,action,args):
        if action=='delete_subject':
            _subject(db,args['subject_id'])
        if action=='delete_session':
            _row(db,'SELECT session_id FROM sessions WHERE session_id=?',(args['session_id'],))
        # Pre-clean snapshots BEFORE committing deletion, even on retry.
        self.files.mark_erasure()
        purged=self.files.purge_backups()
        self._sync_dir(self.files.backups)
        if action=='delete_all':
            # Nonidentifying receipts prevent a retried former erasure from
            # deleting data newly created after another completed erasure.
            db.execute("DELETE FROM receipts WHERE action NOT IN ('delete_all','delete_session','delete_subject')")
            db.execute('DELETE FROM grants')
            db.execute('DELETE FROM subjects')
            return {'deleted':True,'purged_backups':purged}
        all_events=_events(db)
        field = 'subject_id' if action=='delete_subject' else 'session_id'
        target=args[field]
        removed_ids={e['event_id'] for e in all_events if e[field]==target}
        # Related IDs always address earlier events (validated on append), so
        # one chronological traversal closes the transitive dependency set.
        for ev in all_events:
            if removed_ids.intersection(ev['related']):
                removed_ids.add(ev['event_id'])
        identifiers={target}|removed_ids
        if action=='delete_subject':
            instances=[r[0] for r in db.execute('SELECT instance_id FROM instances WHERE subject_id=?',(target,))]
            grants=[r[0] for r in db.execute('SELECT grant_id FROM grants WHERE subject_id=?',(target,))]
            identifiers.update(instances)
            for iid in instances:
                identifiers.update(r[0] for r in db.execute('SELECT session_id FROM sessions WHERE instance_id=?',(iid,)))
        else:
            iid=_row(db,'SELECT instance_id FROM sessions WHERE session_id=?',(target,))['instance_id']
            grants=[r[0] for r in db.execute('SELECT grant_id FROM grants WHERE instance_id=?',(iid,))]
        identifiers.update(grants)
        # Include related audit events and the replay cache. Serialized response
        # values may contain original content, including historical projections.
        for row in list(db.execute('SELECT actor,key,result FROM receipts')):
            if row['actor'] in grants or any(ident in row['result'] for ident in identifiers):
                db.execute('DELETE FROM receipts WHERE actor=? AND key=?',(row['actor'],row['key']))
        db.executemany('DELETE FROM events WHERE event_id=?',((eid,) for eid in removed_ids))
        db.executemany('DELETE FROM grants WHERE grant_id=?',((gid,) for gid in grants))
        if action=='delete_subject':
            db.execute('DELETE FROM subjects WHERE subject_id=?',(target,))
        else:
            db.execute('DELETE FROM sessions WHERE session_id=?',(target,))
        affected_sessions={e['session_id'] for e in all_events if e['event_id'] in removed_ids}
        for session in affected_sessions:
            self._rechain(db,session)
        return {'deleted':True,'purged_backups':purged}

    @staticmethod
    def _rechain(db,session):
        previous=''
        for version,row in enumerate(list(db.execute('SELECT * FROM events WHERE session_id=? ORDER BY seq',(session,))),1):
            ev=dict(row)
            if ev['prev_hash']==previous and ev['version']==version:
                previous=ev['hash']
                continue
            ev.update(prev_hash=previous,version=version)
            previous_hash=event_hash(ev)
            db.execute('UPDATE events SET prev_hash=?,hash=?,version=? WHERE seq=?',
                       (previous,previous_hash,version,ev['seq']))
            previous=previous_hash
            # Invalidate replay receipts carrying superseded integrity metadata.
            # Preserve idempotence by updating their serialized snapshot in-place.
            for cached in list(db.execute('SELECT actor,key,result FROM receipts WHERE instr(result,?)>0',(ev['event_id'],))):
                value=json.loads(cached['result'])
                def refresh(node):
                    if isinstance(node,dict):
                        if node.get('event_id')==ev['event_id'] and 'hash' in node:
                            node.update(hash=previous_hash,prev_hash=ev['prev_hash'],version=version)
                        for child in node.values():
                            refresh(child)
                    elif isinstance(node,list):
                        for child in node:
                            refresh(child)
                refresh(value)
                db.execute('UPDATE receipts SET result=? WHERE actor=? AND key=?',(canonical(value),cached['actor'],cached['key']))

    def _maintenance(self,action,args):
        self.files.clean_temporary()
        if action=='list_backups':
            items=[]
            for path in self.files.backups.glob('bak_*.sqlite3'):
                created=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat().replace('+00:00','Z')
                items.append({'backup_id':path.stem,'created_at':created})
            return {'backups':sorted(items,key=lambda i:i['created_at'],reverse=True)}
        if action=='restore':
            return self._restore(args)
        with self.files.connect() as db:
            key,sign,result=_receipt(db,OWNER,'backup',args)
            if result:
                if self.files.backup_path(result['backup_id']).is_file():
                    return result
                fail('BACKUP_PURGED','This backup was removed.',410)
            # Deterministic for a single owner's retry; contains no user input.
            bid='bak_'+hmac.new(self.files.key,('backup:'+key).encode(),hashlib.sha256).hexdigest()[:32]
            final=self.files.backup_path(bid)
            if not final.exists():
                tmp=self.files.backups/'backup.tmp'
                tmp.touch(mode=0o600)
                with contextlib.closing(sqlite3.connect(tmp)) as dest:
                    dest.row_factory=sqlite3.Row
                    db.backup(dest)
                    dest.execute('PRAGMA journal_mode=DELETE')
                    if not verify_db(dest)['ok']:
                        fail('INVALID_BACKUP','The database failed integrity verification.',409)
                signature_tmp=self.files.backups/'signature.tmp'
                with open(signature_tmp,'x',encoding='ascii',opener=lambda p,f:os.open(p,f,0o600)) as f:
                    f.write(self._backup_signature(tmp,bid))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(signature_tmp,final.with_suffix('.sig'))
                os.replace(tmp,final)
                self._sync_dir(self.files.backups)
            created=datetime.fromtimestamp(final.stat().st_mtime,timezone.utc).isoformat().replace('+00:00','Z')
            result={'backup_id':bid,'created_at':created}
            db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)',(OWNER,key,'backup',sign,canonical(result)))
            return result

    def _backup_signature(self,path,bid):
        mac=hmac.new(self.files.key,('managed-backup-v1:'+bid).encode(),hashlib.sha256)
        with path.open('rb') as file:
            for chunk in iter(lambda:file.read(1024*1024),b''):
                mac.update(chunk)
        return mac.hexdigest()

    @staticmethod
    def _sync_dir(directory):
        if os.name!='nt':
            fd=os.open(directory,os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _restore(self,args):
        bid=args['backup_id']
        path=self.files.backup_path(bid)
        if not path.is_file():
            fail('NOT_FOUND','Managed backup not found.',404)
        signature_file=path.with_suffix('.sig')
        if (not signature_file.is_file() or signature_file.stat().st_size!=64
                or not hmac.compare_digest(signature_file.read_bytes(),self._backup_signature(path,bid).encode())):
            fail('INVALID_BACKUP','Managed backup signature does not match this installation.',409)
        key=digest(args['idempotency_key'])
        sign=digest(canonical(['restore',args]))
        live_grants=set()
        control_receipts=[]
        # A corrupt live file can still be replaced; uncertain credentials are
        # not carried forward into the recovered installation.
        try:
            with self.files.connect() as current:
                _,_,result=_receipt(current,OWNER,'restore',args)
                if result:
                    return result
                if verify_db(current)['ok']:
                    live_grants=set(tuple(r) for r in current.execute('SELECT grant_id,digest,subject_id,instance_id FROM grants'))
                    # A retried old restore must not undo another newer restore.
                    # These results contain only counters and opaque backup IDs.
                    control_receipts=[tuple(r) for r in current.execute(
                        "SELECT actor,key,action,digest,result FROM receipts WHERE actor=? AND "
                        "action IN ('restore','delete_all','delete_session','delete_subject')",(OWNER,))]
                current.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except (sqlite3.DatabaseError,UnicodeError,ValueError):
            live_grants.clear()
            control_receipts.clear()
        tmp=self.files.home/'recovery.tmp'
        tmp.touch(mode=0o600)
        try:
            with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as source, \
                 contextlib.closing(sqlite3.connect(tmp,isolation_level=None)) as dest:
                source.row_factory=sqlite3.Row
                source.execute('PRAGMA trusted_schema=OFF')
                if not verify_db(source)['ok']:
                    fail('INVALID_BACKUP','Backup failed integrity verification.',409)
                source.backup(dest)
                dest.row_factory=sqlite3.Row
                dest.execute('PRAGMA trusted_schema=OFF')
                dest.execute('PRAGMA journal_mode=DELETE')
                dest.execute('PRAGMA secure_delete=ON')
                dest.execute('BEGIN IMMEDIATE')
                removed=0
                for grant in list(dest.execute('SELECT grant_id,digest,subject_id,instance_id FROM grants')):
                    if tuple(grant) not in live_grants:
                        dest.execute('DELETE FROM grants WHERE grant_id=?',(grant[0],))
                        dest.execute('DELETE FROM receipts WHERE actor=?',(grant[0],))
                        removed+=1
                dest.executemany('INSERT OR REPLACE INTO receipts VALUES(?,?,?,?,?)',control_receipts)
                result={'backup_id':bid,'restored':True,'revoked_grants':removed}
                dest.execute('INSERT OR REPLACE INTO receipts VALUES(?,?,?,?,?)',(OWNER,key,'restore',sign,canonical(result)))
                dest.commit()
                if not verify_db(dest)['ok']:
                    fail('INVALID_BACKUP','Restored database failed integrity verification.',409)
            # Every connection controlled by this installation is now closed.
            for suffix in ('-wal','-shm','-journal'):
                Path(str(self.files.path)+suffix).unlink(missing_ok=True)
            os.replace(tmp,self.files.path)
            self._sync_dir(self.files.home)
            return result
        finally:
            self.files.clean_temporary()
