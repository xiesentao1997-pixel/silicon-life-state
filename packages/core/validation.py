"""Small strict validators shared by all transports and the trusted owner API."""
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone


class DomainError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def fail(code, message, status=400):
    raise DomainError(code, message, status)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def uid(prefix):
    return f'{prefix}_{uuid.uuid4().hex}'


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError):
        fail('INVALID_INPUT', 'Value must be finite JSON.')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def object_args(args):
    if not isinstance(args, dict) or any(not isinstance(k, str) for k in args):
        fail('INVALID_INPUT', 'Expected a JSON object.')
    try:
        size = len(canonical(args).encode('utf-8'))
    except UnicodeEncodeError:
        fail('INVALID_INPUT', 'Invalid Unicode input.')
    if size > 128 * 1024:
        fail('INPUT_TOO_LARGE', 'Maximum input is 128 KiB.', 413)


def fields(args, allowed, required=()):
    unknown = set(args) - set(allowed)
    if unknown:
        fail('UNKNOWN_FIELD', 'Unexpected field: ' + ', '.join(sorted(unknown)))
    missing = set(required) - set(args)
    if missing:
        fail('MISSING_FIELD', 'Missing field: ' + ', '.join(sorted(missing)))


def string(value, name, maxlen=16000, minlen=1):
    if not isinstance(value, str) or not minlen <= len(value.strip()) <= maxlen or len(value)>maxlen:
        fail('INVALID_INPUT', f'{name} must contain {minlen}–{maxlen} characters.')
    return value


def number(value, name, lo, hi):
    if type(value) not in (int, float) or not lo <= value <= hi or not math.isfinite(value):
        fail('INVALID_INPUT', f'{name} must be a number from {lo} to {hi}.')
    return value


def integer(value, name, lo=1, hi=2**63-1):
    if type(value) is not int or not lo <= value <= hi:
        fail('INVALID_INPUT', f'{name} must be an integer from {lo} to {hi}.')
    return value


def choice(value, name, choices):
    if not isinstance(value,str) or value not in choices:
        fail('INVALID_INPUT', f'{name} must be one of ' + ', '.join(sorted(choices)))
    return value


REPORT = {'state_text','state_tags','valence','arousal','dominance','load','cause','cause_unknown',
          'interaction_reference','request_id','shared_to_subject','uncertainty'}
ASSESSMENTS = {'hostile','neutral','uncertain','misunderstanding','supportive','other'}
DECISIONS = {'adopt','partial','reject','defer','disagree'}
META = {'adapter_version','model_version'}
TOOLS = {
    'register_subject': ({'name'},{'name'}),
    'register_instance': ({'name'},{'name'}),
    'start_session': (set(),set()),
    'report_state': (REPORT | META, set()),
    'revise_state': ((REPORT - {'shared_to_subject'}) | META | {'event_id','reason','operation','assessment','expected_version_id'},{'event_id'}),
    'get_own_state': (set(),set()),
    'read_subject_memory': (set(),set()),
    'propose_shared_memory': ({'event_id','note'} | META,{'event_id'}),
    'decide_inheritance': ({'event_id','decision','note','expected_version_id'} | META,{'event_id','decision'}),
    'assess_interaction': ({'assessment','text','interaction_reference','uncertainty'} | META,{'assessment','text'}),
    'express_boundary': ({'text','reason'} | META,{'text'}),
    'request_adjustment': ({'text','reason'} | META,{'text'}),
    'get_request_status': ({'request_id'},{'request_id'}),
    'read_event_history': ({'before','limit'},set()),
    'record_strategy': ({'request_id','stage','text'} | META,{'request_id','stage','text'}),
}
ADMIN = {
    'list_subjects': (set(),set()), 'list_agents': (set(),set()), 'snapshot': ({'subject_id'},set()), 'export': (set(),set()), 'verify': (set(),set()),
    'create_subject': ({'name'},{'name'}), 'create_instance': ({'subject_id','name'},{'subject_id','name'}),
    'connection_grant': ({'instance_id'},{'instance_id'}),
    'issue_agent': ({'subject_id','instance_id'},set()), 'revoke_agent': ({'grant_id'},{'grant_id'}),
    'set_level': ({'subject_id','level'},{'subject_id','level'}),
    'observe': ({'instance_id','text','adapter','adapter_version','interaction_reference'},{'instance_id','text'}),
    'annotate': ({'instance_id','text','interaction_reference'},{'instance_id','text'}),
    'runtime': ({'instance_id','text','metrics','request_id'},{'instance_id','text'}),
    'sample_runtime': ({'instance_id','request_id'},{'instance_id'}),
    'estimate': ({'instance_id','event_id','alpha'},{'instance_id','event_id'}),
    'respond': ({'request_id','stage','text'},{'request_id','stage'}),
    'backup': (set(),set()), 'restore': ({'backup_id'},{'backup_id'}), 'list_backups': (set(),set()),
    'delete_session': ({'session_id'},{'session_id'}), 'delete_subject': ({'subject_id'},{'subject_id'}),
    'delete_all': (set(),set()),
}
READS = {'get_own_state','read_subject_memory','get_request_status','read_event_history',
         'snapshot','verify','export','list_backups','list_agents','list_subjects'}


def validate(name, args, owner=False):
    object_args(args)
    rules = ADMIN if owner else TOOLS
    if not isinstance(name,str) or name not in rules:
        fail('UNKNOWN_ACTION','Unknown action.',404)
    allowed, required = rules[name]
    if name not in READS:
        allowed, required = allowed | {'idempotency_key'}, required | {'idempotency_key'}
    fields(args,allowed,required)
    for key, val in args.items():
        if key == 'state_tags':
            if not isinstance(val,list) or len(val)>32:
                fail('INVALID_INPUT','state_tags must be a list of at most 32 strings.')
            for tag in val:
                string(tag,'state_tags',128)
        elif key in {'arousal','dominance','alpha','valence','load'}:
            number(val,key,-1 if key=='valence' else 0,100 if key=='load' else 1)
        elif key in {'cause_unknown','shared_to_subject'}:
            if type(val) is not bool:
                fail('INVALID_INPUT',f'{key} must be boolean.')
        elif key == 'metrics':
            if not isinstance(val,dict) or len(val)>64:
                fail('INVALID_INPUT','metrics must be an object with up to 64 numeric values.')
            for metric, reading in val.items():
                string(metric,'metric',128)
                number(reading,metric,-1e100,1e100)
        elif key in {'level','limit','before'}:
            integer(val,key,1,{'level':3,'limit':500}.get(key,2**63-1))
        elif key == 'assessment':
            choice(val,key,ASSESSMENTS)
        elif key=='decision':
            choice(val,key,DECISIONS)
        elif key=='operation':
            choice(val,key,{'revise','clarify','withdraw'})
        elif key=='stage':
            choice(val,key,{'PRESENTED','ACCEPTED','DECLINED','DEFERRED','EXECUTED','NOT_EXECUTED','FOLLOW_UP'})
        elif key=='idempotency_key':
            string(val,key,128,8)
        elif key in {'model_version','adapter_version','name','adapter','interaction_reference'} or key.endswith('_id'):
            string(val,key,256)
        else:
            string(val,key)
    if args.get('decision')=='partial' and 'note' not in args:
        fail('MISSING_FIELD','Partial adoption requires note describing the adopted part.')
    if name=='report_state' and not (set(args) & (REPORT - {'interaction_reference','request_id','shared_to_subject'})):
        fail('EMPTY_REPORT','Supply at least one report field.')
    if args.get('cause_unknown') and args.get('cause'):
        fail('INVALID_INPUT','A known cause conflicts with cause_unknown.')
