# Core 1.0
Python stdlib. Import Store, DomainError from packages.core.store. Store(data_dir).tool(token,name,args) is the sole model entry point. Store(data_dir).admin(action,args) trusted installer only; HTTP layer handles interactive authentication. DomainError has status (HTTP), code (stable), and str(error). Unique idempotency_key (8–128 characters) required on mutations. Agent tokens use one credential per independent instance and only see own instance plus explicitly shared subject events. Authoring metadata can be declared with model_version/adapter_version on event writes. UTC timestamps in ISO 8601.

## Models
- register_subject {name,idempotency_key} -> {subject_id,name}. Bound tokens return the authorized subject. Unbound grants may create one.
- register_instance {name,idempotency_key} -> {subject_id,instance_id,session_id,name}. Bound token resumes own instance. User controls additional grants.
- report_state {state_text?,state_tags?:string[],valence?:-1..1,arousal?:0..1,dominance?:0..1,load?:0..100,cause?,cause_unknown?:bool,uncertainty?,shared_to_subject?:bool,interaction_reference?:event_id,request_id?:event_id,idempotency_key}; at least one report field.
- revise_state {event_id,reason?,state_text?,assessment?,operation?:'revise'|'clarify'|'withdraw',...optional report fields,idempotency_key}. Only own report or assessment root is revisable. References latest root revision through related IDs. assessment enum 'hostile'|'neutral'|'uncertain'|'misunderstanding'|'supportive'|'other'.
- get_own_state {} -> {subject_id,instance_id,session_id,state:event|null}
- read_subject_memory {} -> {subject_id,events:[...],proposals:[event],common:[event],disputed:[event],decisions:[event]}; decisions do not change individual state.
- propose_shared_memory {event_id,note?,idempotency_key}
- decide_inheritance {event_id,decision:'adopt'|'partial'|'reject'|'defer'|'disagree',note?,idempotency_key}; event_id is explicitly shared source root or proposal event. Partial requires note naming adopted part.
- assess_interaction {assessment,text,interaction_reference?,uncertainty?,idempotency_key}
- express_boundary / request_adjustment {text,reason?,idempotency_key} -> event with request_id (equal to event_id).
- get_request_status {request_id} -> {request_id,stage,original:event,history:[event]}
- read_event_history {limit?:1..500,before?:seq} -> {events:[event],next_before:int|null}; newest first. Own independent history, other instances available via read_subject_memory by consent.
- record_strategy {request_id,stage:'EXECUTED'|'NOT_EXECUTED'|'FOLLOW_UP',text,idempotency_key}. For execution attestations stage EXECUTED requires subject level 2+ (3 for request_adjustment) and a user ACCEPTED response. Model attestation is agent_direct, never runtime_observed.

Event writes return an event object directly (not wrapped): {seq,event_id,subject_id,instance_id,session_id,type,source,actor,created_at,payload,related:[event_id],model_version,adapter_version,prev_hash,hash,version,request_id?}. Types match tool/action names except auto proposal='propose_shared_memory', decision reply='respond'. Timestamps UTC; event payload is original input excluding reserved metadata. Source values agent_direct, agent_visible_text, runtime_observed, model_estimated, user_annotation. Each instance begins with one session and can open additional sessions with start_session. Latest state projection (instance.state, get_own_state.state) preserves root event identity and merges latest revisions (withdrawals removed); revisions list in independent history.

## Owner actions
Reads omit idempotency_key. Mutations supply it, including backup/restore/delete. IDs use opaque strings with prefixes. Owner access must be authenticated by caller.
- snapshot {} -> {subjects:[{subject_id,name,created_at,level}],instances:[{subject_id,instance_id,session_id,name,created_at,state:event|null}],events:[event],requests:[{request_id,stage,original:event,history:[event]}],memory:{proposals:[event],common:[event],disputed:[event],decisions:[event]},stats:{confirmed_hostile:int},generated_at}. Events newest first. Current state only concerns model's own direct reports, level defaults to 1.
- create_subject {name} -> subject row.
- create_instance {subject_id,name} -> instance row.
- issue_agent {subject_id?,instance_id?} -> {token,grant_id,subject_id,instance_id}. Provide instance_id to bind to user-created instance. Omitting subject and instance creates an enrollment token limited to one new subject then one instance. Only one live token per instance.
- revoke_agent {grant_id} -> {revoked:true}
- observe {instance_id,text,adapter?,adapter_version?,interaction_reference?} -> event. Explicit observation.
- annotate {instance_id,text,interaction_reference?} -> event.
- estimate {instance_id,event_id,alpha?} -> event; source model_estimated, uses source report valence and load (or configured alpha), payload exposes alpha, input values and estimated valence. Does not affect state.
- sample_runtime {instance_id,request_id?} measures a local SQLite query once and returns a runtime_observed event.
- runtime {instance_id,text,metrics?,request_id?} -> event; must be emitted by trusted runtime observer, not exposed as a user-typed metric.
- set_level {subject_id,level:1|2|3} -> subject row; scope governs execution claims.
- respond {request_id,stage:'PRESENTED'|'ACCEPTED'|'DECLINED'|'DEFERRED'|'EXECUTED'|'NOT_EXECUTED'|'FOLLOW_UP',text?} -> request projection as get_request_status. UI explicitly presents on showing original (not automatic on snapshot). Owner EXECUTED is user_annotation about host action; should describe what happened. DEFERRED may transition to a later decision.
- verify {} -> {ok,events,errors}. export {} -> snapshot with all events and sessions, excludes tokens/grants/internal receipts.
- backup {} -> {backup_id,created_at}; list_backups {} -> {backups:[{backup_id,created_at}]}.
- restore {backup_id} -> {restored:true,backup_id}. Validates managed backup before atomic replacement. Only grant IDs with identical currently authorized scopes survive restoration. No raw import.
- delete_session {session_id}, delete_subject {subject_id}, delete_all {} -> {deleted:true,purged_backups:int}. Drops affected rows and dependent events, revokes affected agents, purges managed backup snapshots, scrubs receipts and recomputes surviving chains. Externally exported files, filesystem snapshots and device backups remain user-controlled.

## Session rotation and restore scope
start_session {idempotency_key} opens another session under the same window and returns {instance_id,subject_id,session_id,name}; registering that same instance resumes its most recent session. Snapshot accepts optional subject_id and includes sessions and report_states. report_states contains every effective, non-withdrawn report root with its merged fields and any revision_id; events retains the complete raw submission timeline. Shared memory projections (proposals/common/disputed) carry the shared source event and proposal_id. Memory events include proposal and revision evidence. Restore retains only backup grants that match a currently live credential and identical scope. If current credential storage is unreadable all agent grants are revoked; issue replacement credentials from the owner dashboard.

Memory version handling: each projected proposal lists adoption_scope (full/partial/null), adoptions with exact decision payloads and notes, and prior_version_decisions. Only a decision on the current report version enters current common/disputed views. decide_inheritance accepts expected_version_id; absence means the original version, so for revised proposals pass revision_id returned by read_subject_memory. revise_state accepts an optional expected_version_id for optimistic concurrency. Stale writes return STALE_VERSION and do not append a decision. Original decisions and earlier assessments remain visible in the evidence ledger.

Managed backups are installation-bound SQLite snapshots accompanied by a byte-for-byte HMAC signature. Recovery validates the signature, SQLite structure, and event chains before replacing the live database. A backup copied from another installation without its protected issuance.key cannot be restored. Keep the whole data directory together for device migration. A local operator who controls all files also controls the key; signatures are not third-party attestations.

Owner read endpoints list_subjects and list_agents return {subjects:[...]} and {grants:[{grant_id,subject_id,instance_id,created_at}]}. Grant inventory is excluded from export. A durable nonidentifying erasure marker allows the next managed operation to complete interrupted SQLite journal truncation and compaction before returning data.
