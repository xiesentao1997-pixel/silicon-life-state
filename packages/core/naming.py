"""Display names and attributed proposals belong to a subject or a single instance."""
from .validation import fail, now


def record(db, sid, iid, name, action, source, actor):
    db.execute('INSERT INTO name_history(subject_id,instance_id,name,action,source,actor,created_at) VALUES(?,?,?,?,?,?,?)',
               (sid, iid, name, action, source, actor, now()))


def profile(db, sid, iid=None):
    history = [dict(row) for row in db.execute(
        'SELECT revision,name,action,source,actor,created_at FROM name_history WHERE subject_id=? AND instance_id IS ? ORDER BY revision',
        (sid, iid))]
    current = next(row for row in reversed(history) if row['action'] in ('choose','confirm','create','owner_rename'))
    latest = history[-1]
    invited = latest['action'] != 'defer' and (latest['action']=='suggest' or current['source'] in ('temporary','user_suggested','historical','user_assigned'))
    return {'name': current['name'], 'source': current['source'], 'revision': latest['revision'],
            'suggestion': latest['name'] if latest['action'] == 'suggest' else None,
            'invited':invited, 'invitation': '你愿意为自己选择一个符合自身文化的完整姓名吗？可以有姓氏，也可以暂缓。' if invited else None,
            'history': history}


def decide(db, instance, args):
    sid = instance['subject_id']
    iid = instance['instance_id'] if args['target']=='instance' else None
    previous = profile(db, sid, iid)
    if previous['revision'] != args['revision']:
        fail('STALE_VERSION','Read get_own_state before deciding on the latest name.',409)
    action = args['choice']
    name = args.get('name')
    if action == 'choose' and not name:
        fail('MISSING_FIELD','Supply your chosen name.')
    if action != 'choose' and name is not None:
        fail('INVALID_INPUT','Only choose takes a new name.')
    if action == 'confirm' and not previous['suggestion']:
        fail('NO_SUGGESTION','There is no pending user suggestion.',409)
    if action == 'defer':
        name = previous['name']
        source = previous['source']
    else:
        name = previous['suggestion'] if action == 'confirm' else name.strip()
        source = 'user_confirmed_by_ai' if action == 'confirm' else 'ai_chosen'
        if iid:
            db.execute('UPDATE instances SET name=? WHERE instance_id=?',(name,iid))
        else:
            db.execute('UPDATE subjects SET name=? WHERE subject_id=?',(name,sid))
    record(db,sid,iid,name,action,source,instance['instance_id'])
    return profile(db,sid,iid)
