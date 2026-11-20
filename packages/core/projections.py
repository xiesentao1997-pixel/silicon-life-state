"""Read models derived exclusively from stored events. Input is oldest first."""
import json
from heapq import heappop, heappush

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


def revised_report(original, revision):
    """Apply only fields that revise the statement, keeping its original ID."""
    payload = original['payload'].copy()
    updates = {k: v for k, v in revision['payload'].items() if k in REPORT_VALUES}
    if updates.get('cause_unknown'):
        payload.pop('cause', None)
    if 'cause' in updates:
        payload.pop('cause_unknown', None)
    payload.update(updates)
    return {**original, 'payload': payload, 'projected': True,
            'revision_id': revision['event_id'], 'revised_at': revision['created_at']}


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
            effective[root] = revised_report(effective[root], ev)
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


def subject_summary(sid, memory):
    """Replay shared state statements in sequence order. Preserve exact author labels.

    Each distribution vote is the newest unretracted shared root from an instance,
    ordered by the original report sequence. Correcting an older root never moves
    it ahead of a later report. A withdrawal can expose a previous shared state.
    """
    states, roots, active, queues = {}, set(), set(), {}
    trend, changes = [], []
    for ev in reversed(memory['events']):
        event_id, iid, kind = ev['event_id'], ev['instance_id'], ev['type']
        if kind == 'report_state':
            roots.add(event_id)
            states[event_id] = ev
            continue
        if kind not in {'revise_state', 'propose_shared_memory'} or not ev['related']:
            continue
        root = ev['related'][0]
        if kind == 'revise_state':
            changes.append(ev)
        if root not in roots:
            continue
        if kind == 'propose_shared_memory':
            if root in active or root not in states:
                continue
            active.add(root)
            heappush(queues.setdefault(iid, []), (-states[root]['seq'], root))
            operation = 'share'
        else:
            operation = ev['payload'].get('operation', 'revise')
            if operation == 'withdraw':
                states.pop(root, None)
            elif root in states:
                states[root] = revised_report(states[root], ev)
            if root not in active:
                continue
        queue = queues[iid]
        while queue and queue[0][1] not in states:
            heappop(queue)
        current = states[queue[0][1]] if queue else None
        report = states.get(root)
        trend.append({
            'event_id': event_id, 'seq': ev['seq'], 'created_at': ev['created_at'],
            'instance_id': iid, 'report_id': root, 'operation': operation,
            'version_id': (report.get('revision_id', root) if report else event_id),
            'state_text': report['payload'].get('state_text') if report else None,
            'current_report_id': current['event_id'] if current else None,
            'current_version_id': current.get('revision_id', current['event_id']) if current else None,
            'current_state_text': current['payload'].get('state_text') if current else None,
        })

    distribution = {}
    for queue in queues.values():
        if queue:
            current = states[queue[0][1]]
            label = current['payload'].get('state_text')
            group = distribution.setdefault(label, {
                'state_text': label, 'count': 0, 'instance_ids': [], 'report_ids': []})
            group['count'] += 1
            group['instance_ids'].append(current['instance_id'])
            group['report_ids'].append(current['event_id'])
    return {
        'subject_id': sid, 'method': 'latest_effective_shared_report_per_instance_v1',
        'distribution': list(distribution.values()),
        'current_reports': [ev for root, ev in reversed(states.items()) if root in active],
        'trend': trend, 'changes': changes,
        'common': memory['common'], 'disputed': memory['disputed'],
    }


def subject_summaries(subjects, memory):
    # An owner snapshot may span subjects. Keep each subject's shared ledger
    # separate even when names or state labels coincide.
    partitions = {s['subject_id']: {'events': [], 'common': [], 'disputed': []} for s in subjects}
    for field in ('events', 'common', 'disputed'):
        for event in memory[field]:
            partitions[event['subject_id']][field].append(event)
    return [subject_summary(sid, partition) for sid, partition in partitions.items()]


def hostile_count(effective):
    return sum(1 for e in effective.values() if e['type']=='assess_interaction'
               and e['payload'].get('assessment')=='hostile')
