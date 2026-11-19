"""Read models derived exclusively from stored events. Input is oldest first."""
import json

REQUESTS = {'express_boundary','request_adjustment'}
RESPONSES = {'respond','record_strategy'}
REPORT_VALUES = {'state_text','state_tags','valence','arousal','dominance','load','cause','cause_unknown',
                 'uncertainty','assessment'}


def event_dict(row):
    event = dict(row)
    event['payload'] = json.loads(event['payload'])
    event['related'] = json.loads(event['related'])
    if event['type'] in REQUESTS:
        event['request_id'] = event['event_id']
    elif event['type'] in RESPONSES:
        event['request_id'] = event['payload']['request_id']
    return event


def reports(events):
    effective = {}
    for ev in events:
        eid = ev['event_id']
        if ev['type'] in {'report_state','assess_interaction'}:
            effective[eid] = ev
        elif ev['type']=='revise_state':
            root = ev['related'][0]
            if ev['payload'].get('operation')=='withdraw':
                effective.pop(root,None)
                continue
            if root not in effective:
                continue
            orig = effective[root]
            payload = orig['payload'].copy()
            updates = {k:v for k,v in ev['payload'].items() if k in REPORT_VALUES}
            if updates.get('cause_unknown'):
                payload.pop('cause',None)
            if 'cause' in updates:
                payload.pop('cause_unknown',None)
            payload.update(updates)
            # The original hash always belongs to the raw event only. Projected
            # fields are deliberately marked. Both originals are in event history.
            effective[root] = {**orig,'payload':payload,'projected':True,
                               'revision_id':eid,'revised_at':ev['created_at']}
    return effective


def latest_states(effective):
    by_instance = {}
    for ev in effective.values():
        if ev['type']=='report_state':
            by_instance[ev['instance_id']] = ev
    return by_instance


def request_views(events):
    result = {}
    for ev in events:
        kind = ev['type']
        if kind in REQUESTS:
            rid = ev['event_id']
            result[rid] = {'request_id':rid,'stage':'CREATED','original':ev,'history':[ev]}
        elif kind in RESPONSES:
            request = result.get(ev['payload']['request_id'])
            if request:
                request['stage'] = ev['payload']['stage']
                request['history'].append(ev)
    return result


def memory_view(events):
    raw = {e['event_id']:e for e in events}
    effective = reports(events)
    shared, exposed, decisions = {}, set(), []
    revisions, latest_decisions = {}, {}
    for ev in events:
        kind = ev['type']
        if kind=='revise_state':
            revisions[ev['related'][0]] = ev['event_id']
        elif kind=='propose_shared_memory':
            root = ev['related'][0]
            shared[root] = ev
            exposed.update([root,ev['event_id']])
        elif kind=='decide_inheritance':
            root = ev['related'][0]
            # The statement visible at that point is immutable. Reconstruct the
            # version even for older stored decisions without an explicit link.
            decision={**ev,'applies_to_version_id':revisions.get(root,root)}
            latest_decisions[(root,ev['instance_id'])] = ev['event_id']
            exposed.add(ev['event_id'])
            decisions.append(decision)
    # Include revisions both before and after a proposal, including withdrawals.
    for ev in events:
        if ev['type']=='revise_state' and ev['related'][0] in shared:
            exposed.add(ev['event_id'])
    active, prior = {}, {}
    for decision in decisions:
        root=decision['related'][0]
        current_version=decision['applies_to_version_id']==revisions.get(root,root)
        latest=decision['event_id']==latest_decisions[(root,decision['instance_id'])]
        decision.update(is_current_version=current_version,is_latest_decision=latest)
        if latest:
            target=active if current_version else prior
            target.setdefault(root,[]).append(decision)
    proposals, common, disputed = [], [], []
    for root in reversed(shared):
        data=raw.get(root)
        if data and data['type'] in {'report_state','assess_interaction'}:
            data=effective.get(root)
        if not data:
            continue
        choices=active.get(root,[])
        adoptions=[d for d in choices if d['payload']['decision'] in {'adopt','partial'}]
        scope=None
        if adoptions:
            scope='full' if any(d['payload']['decision']=='adopt' for d in adoptions) else 'partial'
        entry={**data,'proposal_id':shared[root]['event_id'],'adoption_scope':scope,
               'adoptions':adoptions,'decisions':choices,'prior_version_decisions':prior.get(root,[])}
        proposals.append(entry)
        if adoptions:
            common.append(entry)
        if any(d['payload']['decision'] in {'reject','disagree'} for d in choices):
            disputed.append(entry)
    return {'proposals':proposals,'common':common,'disputed':disputed,
            'decisions':decisions[::-1],
            'events':[ev for ev in reversed(events) if ev['event_id'] in exposed]}


def hostile_count(effective):
    return sum(1 for e in effective.values() if e['type']=='assess_interaction'
               and e['payload'].get('assessment')=='hostile')
