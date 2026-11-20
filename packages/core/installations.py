"""Owner-issued host grants and host-scoped conversation bindings."""
import hashlib
import hmac
import os
from pathlib import Path
import tempfile

from .validation import digest, fail, fields, now, object_args, string, uid


def public(row):
    return {key:row[key] for key in ('installation_id','subject_id','host','created_at')} | {
        'active': row['digest'] is not None}


def credential(files, generation):
    return 'slsi_' + hmac.new(files.key, ('installation:' + generation).encode(), hashlib.sha256).hexdigest()


def lookup(db, identity):
    row = db.execute('SELECT * FROM installations WHERE installation_id=?',(identity,)).fetchone()
    if row is None:
        fail('NOT_FOUND','Installation not found.',404)
    return row


def authenticate(db, token):
    if not isinstance(token,str) or not token.startswith('slsi_') or len(token)!=69:
        fail('UNAUTHENTICATED','Invalid installation credential.',401)
    row = db.execute('SELECT * FROM installations WHERE digest=?',(digest(token),)).fetchone()
    if row is None:
        fail('UNAUTHENTICATED','Unknown, rotated or revoked installation credential.',401)
    return row


def update_holder(files, row):
    directory = files.home / 'host-grants'
    path = directory / (row['installation_id'] + '.token')
    if row['digest'] is None:
        path.unlink(missing_ok=True)
    elif row['managed']:
        directory.mkdir(mode=0o700, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.rotate-',dir=directory)
        try:
            with os.fdopen(fd,'w',encoding='ascii') as f:
                f.write(credential(files,row['generation'])+'\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp,path)
        finally:
            Path(temp).unlink(missing_ok=True)
    return path


def sync_holders(files,db):
    directory = files.home / 'host-grants'
    if not directory.exists():
        return
    # A power loss between writing and replacing a holder can leave its private
    # temporary copy. The caller owns the same process lock used for rotation.
    for path in directory.glob('.rotate-*'):
        path.unlink(missing_ok=True)
    rows = list(db.execute('SELECT * FROM installations WHERE managed=1'))
    known = {row['installation_id'] for row in rows}
    for path in directory.glob('instal_*.token'):
        if path.stem not in known:
            path.unlink(missing_ok=True)
    for row in rows:
        update_holder(files,row)


def owner(store,db,action,args):
    if action=='list_installations':
        return {'installations':[public(row) for row in db.execute('SELECT * FROM installations ORDER BY rowid')]}
    if action=='issue_installation':
        sid, seed = args['subject_id'], args.get('instance_id')
        if db.execute('SELECT 1 FROM subjects WHERE subject_id=?',(sid,)).fetchone() is None:
            fail('NOT_FOUND','Subject not found.',404)
        if seed:
            if not db.execute('SELECT 1 FROM instances WHERE instance_id=? AND subject_id=?',(seed,sid)).fetchone():
                fail('SCOPE_CONFLICT','Selected instance does not belong to this subject.',409)
            if db.execute('SELECT 1 FROM conversation_bindings WHERE instance_id=?',(seed,)).fetchone():
                fail('ALREADY_BOUND','This instance belongs to another installation. Select a new instance.',409)
        identity, generation = uid('instal'), uid('gen')
        db.execute('''INSERT INTO installations(installation_id,subject_id,host,created_at,generation,digest,seed_instance_id)
                      VALUES(?,?,?,?,?,?,?)''',
                   (identity,sid,args['host'],now(),generation,digest(credential(store.files,generation)),seed))
    else:
        identity = args['installation_id']
        row = lookup(db,identity)
        if action=='rotate_installation' and row['digest'] is None:
            fail('REAUTHORIZATION_REQUIRED','Explicitly restore the revoked installation first.',409)
        if action=='restore_installation' and row['digest'] is not None:
            fail('ALREADY_ACTIVE','This installation is active. Use credential rotation.',409)
        # All descendant credentials become unusable in this same transaction.
        db.execute('''DELETE FROM grants WHERE instance_id IN
                      (SELECT instance_id FROM conversation_bindings WHERE installation_id=?)''',(identity,))
        generation = uid('gen')
        verifier = None if action=='revoke_installation' else digest(credential(store.files,generation))
        db.execute('UPDATE installations SET generation=?,digest=? WHERE installation_id=?',(generation,verifier,identity))
    row = lookup(db,identity)
    # Receipts store an opaque generation, never a usable secret.
    return {**public(row),'generation':row['generation']}


def deliver(files,db,action,result):
    identity = result['installation_id']
    row = lookup(db,identity)
    if row['generation']!=result['generation']:
        fail('CREDENTIAL_SUPERSEDED','This result belongs to an older authorization generation.',410)
    if action!='issue_installation':
        update_holder(files,row)
    return public(row) | ({'token':credential(files,row['generation'])} if row['digest'] else {'revoked':True})


def bind(store,db,token,body,create_instance,get_instance,new_session):
    object_args(body)
    fields(body,{'conversation_id','name'},{'conversation_id'})
    key = digest(string(body['conversation_id'],'conversation_id',256))
    if 'name' in body:
        string(body['name'],'name',256)
    row = authenticate(db,token)
    identity = row['installation_id']
    binding = db.execute('SELECT instance_id,enabled FROM conversation_bindings WHERE installation_id=? AND conversation_hash=?',
                         (identity,key)).fetchone()
    if binding:
        if not binding['enabled']:
            fail('INSTANCE_REVOKED','The owner revoked this conversation grant.',403)
        instance = get_instance(db,binding['instance_id'])
    else:
        seed = row['seed_instance_id']
        if seed:
            instance = get_instance(db,seed)
            prior = db.execute('SELECT grant_id FROM grants WHERE instance_id=?',(seed,)).fetchone()
            if prior:
                # A seeded legacy instance now keys future retries by stable instance ID.
                db.execute('UPDATE receipts SET actor=? WHERE actor=?',(seed,prior['grant_id']))
            db.execute('UPDATE installations SET seed_instance_id=NULL WHERE installation_id=?',(identity,))
        else:
            instance = create_instance(db,row['subject_id'],body.get('name',row['host']+' conversation')[:256])
        db.execute('INSERT INTO conversation_bindings(installation_id,conversation_hash,instance_id) VALUES(?,?,?)',
                   (identity,key,instance['instance_id']))
    if not instance['session_id']:
        instance = new_session(db,instance['instance_id'])
    grant = store._owner(db,'connection_grant',{'instance_id':instance['instance_id']})
    return {**instance,'installation_id':identity,'grant_id':grant['grant_id'],'token':store._grant_token(grant['grant_id'])}
