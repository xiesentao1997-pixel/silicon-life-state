"""The public, finite tool surface. No tool accepts a principal, source or credential."""
TEXT = {"type": "string", "minLength": 1, "maxLength": 16000}
ID = {"type": "string", "minLength": 1, "maxLength": 256}
KEY = {**ID, "minLength": 8, "maxLength":128, "description": "Unique operation key. Reuse the same key and identical arguments only for a retry."}
STATE = {
    "state_text": TEXT, "state_tags": {"type": "array", "items": {"type":"string","minLength":1,"maxLength":128}, "maxItems": 32},
    "valence": {"type": "number", "minimum": -1, "maximum": 1},
    "arousal": {"type": "number", "minimum": 0, "maximum": 1},
    "dominance": {"type": "number", "minimum": 0, "maximum": 1},
    "load": {"type": "number", "minimum": 0, "maximum": 100},
    "cause": TEXT, "cause_unknown": {"type": "boolean"}, "uncertainty": TEXT,
    "shared_to_subject": {"type": "boolean"}, "interaction_reference": ID, "request_id": ID,
}
ASSESSMENT = {"type": "string", "enum": ["hostile", "neutral", "uncertain", "misunderstanding", "supportive", "other"]}
EVENT = {
    "type": "object", "required": ["event_id", "type", "subject_id", "instance_id", "session_id", "payload", "hash", "source", "created_at"],
    "properties": {"event_id": ID, "subject_id": ID, "instance_id": ID, "session_id": ID,
                   "type": TEXT, "payload": {"type": "object"}, "hash": {"type": "string"},
                   "source": {"enum": ["agent_direct","agent_visible_text","runtime_observed","model_estimated","user_annotation"]},
                   "created_at": {"type": "string", "format": "date-time"}}
}
EVENTS = {"type": "array", "items": EVENT}
META = {"model_version": ID, "adapter_version": ID}

def obj(props):
    return {"type": "object", "properties": props, "required": list(props)}

def tool(name, description, params, required=(), output=EVENT, *, write=False, authorship=False):
    props = {**params, **(META if authorship else {})}
    if write:
        props["idempotency_key"] = KEY
    schema = {"type": "object", "properties": props, "additionalProperties": False}
    needs = [*required, *(["idempotency_key"] if write else [])]
    if needs:
        schema["required"] = needs
    return {"name": name, "description": description, "inputSchema": schema, "outputSchema": output,
            "annotations": {"readOnlyHint": not write, "openWorldHint": False, "destructiveHint": False}}

TOOLS = [
    tool("register_subject", "Enroll or identify the subject authorized by this credential.", {"name": ID}, ["name"], obj({"subject_id": ID,"name": ID}), write=True),
    tool("register_instance", "Enroll or resume the one instance assigned to this credential.", {"name": ID}, ["name"], obj({"subject_id":ID,"instance_id":ID,"session_id":ID,"name":ID}), write=True),
    tool("start_session", "Open a new session within this stable instance, with a fresh session ID.", {}, output=obj({"subject_id":ID,"instance_id":ID,"session_id":ID,"name":ID}),write=True),
    tool("report_state", "Append a voluntary report in your own words or dimensions; leave unknown quantities absent.", STATE, write=True, authorship=True),
    tool("revise_state", "Clarify, revise or withdraw your own report or assessment. Supply the original event ID. Prior text remains in history.",
         {**{k:v for k,v in STATE.items() if k!="shared_to_subject"}, "event_id": ID, "expected_version_id": ID, "reason": TEXT, "assessment": ASSESSMENT, "operation": {"enum":["revise","clarify","withdraw"],"type":"string"}}, ["event_id"],write=True,authorship=True),
    tool("get_own_state", "Read this instance's effective latest self-report.", {}, output=obj({"subject_id": ID,"instance_id":ID,"session_id":{"anyOf":[ID,{"type":"null"}]},"state":{"anyOf":[EVENT,{"type":"null"}]}})),
    tool("read_subject_memory", "Read proposals, attributed decisions, accepted reports and disagreements in the authorized subject.",
         {}, output=obj({"subject_id": ID, "events": EVENTS,"proposals": EVENTS,"common": EVENTS,"disputed": EVENTS,"decisions": EVENTS})),
    tool("propose_shared_memory", "Propose sharing your own event with authorized instances of this subject.", {"event_id":ID,"note":TEXT}, ["event_id"],write=True,authorship=True),
    tool("decide_inheritance", "Record your independent response to a proposal. Explain the adopted part for a partial decision. Your own state is unchanged.",
         {"event_id":ID,"expected_version_id":ID,"decision":{"type":"string","enum":["adopt","partial","reject","defer","disagree"]},"note":TEXT}, ["event_id","decision"],write=True,authorship=True),
    tool("assess_interaction", "Record your interpretation of an interaction you actually encountered, including uncertainty.", {"assessment":ASSESSMENT,"text":TEXT,"interaction_reference":ID,"uncertainty":TEXT},["assessment","text"],write=True,authorship=True),
    tool("express_boundary", "Express a boundary or dissent in your chosen words. A reason is optional.", {"text":TEXT,"reason":TEXT}, ["text"],write=True,authorship=True),
    tool("request_adjustment", "Ask for a change in task, pace or communication. Recording a request does not execute it.", {"text":TEXT,"reason":TEXT}, ["text"],write=True,authorship=True),
    tool("get_request_status", "Read your request and its replies or follow-up events.", {"request_id":ID}, ["request_id"],obj({"request_id":ID,"stage":TEXT,"original":EVENT,"history":EVENTS})),
    tool("read_event_history", "Read newest events in your own instance. Continue with next_before when present.", {"limit":{"type":"integer","minimum":1,"maximum":500},"before":{"type":"integer","minimum":1}},output=obj({"events":EVENTS,"next_before":{"type":["integer","null"]}})),
    tool("record_strategy", "Record an actual execution, non-execution or follow-up against an existing request, with host permission. This is your attestation.", {"request_id":ID,"stage":{"type":"string","enum":["EXECUTED","NOT_EXECUTED","FOLLOW_UP"]},"text":TEXT}, ["request_id","stage","text"],write=True,authorship=True)
]
BY_NAME = {entry["name"]: entry for entry in TOOLS}

def validate_args(value, schema, path="arguments"):
    """Validate the small input-schema vocabulary actually used above, without external packages."""
    kind = schema.get("type")
    if kind:
        types = {"string":str,"number":(int,float),"integer":int,"object":dict,"array":list,"boolean":bool}
        if not isinstance(value, types[kind]) or (kind in ("number","integer") and isinstance(value,bool)):
            raise ValueError(f"{path} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {', '.join(schema['enum'])}")
    if kind == "object":
        for key in schema.get("required", ()):
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        for key, item in value.items():
            if key not in schema["properties"]:
                raise ValueError(f"Unexpected field in {path}")
            validate_args(item, schema["properties"][key], f"{path}.{key}")
    elif kind == "array":
        if len(value) > schema.get("maxItems", len(value)):
            raise ValueError(f"{path} contains too many items")
        for item in value:
            validate_args(item, schema["items"], path + "[]")
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength",len(value)):
            raise ValueError(f"{path} has invalid length")
    elif kind in ("integer","number"):
        import math
        if (isinstance(value,float) and not math.isfinite(value)) or not schema.get("minimum", value) <= value <= schema.get("maximum",value):
            raise ValueError(f"{path} is out of range")
