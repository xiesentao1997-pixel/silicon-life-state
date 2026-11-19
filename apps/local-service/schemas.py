"""Machine-readable local owner API. GET /api/schema with a paired owner credential."""
def ref(name):
    return {"$ref": "#/components/schemas/" + name}


def obj(props, required=None, strict=False):
    result = {"type": "object", "properties": props, "required": list(props) if required is None else required}
    if strict:
        result["additionalProperties"] = False
    return result


def enum(*items):
    return {"type": "string", "enum": list(items)}


def array(item):
    return {"type": "array", "items": item}


STRING = {"type": "string"}
BOOL = {"type": "boolean"}
INT = {"type": "integer"}
KEY = {"type": "string", "minLength": 8, "maxLength": 128}
ID = {"type": "string", "minLength": 1, "maxLength": 256}
DATE = {"type": "string", "format": "date-time"}
TEXT = {"type": "string", "minLength": 1, "maxLength": 16000}
STAGES = enum("PRESENTED", "ACCEPTED", "DECLINED", "DEFERRED", "EXECUTED", "NOT_EXECUTED", "FOLLOW_UP")
TARGET = enum("dashboard", "extension")
SOURCES = enum("agent_visible_text", "agent_direct", "user_annotation", "model_estimated", "runtime_observed")


def write(props=None, required=None):
    props = props or {}
    needs = list(props) if required is None else list(required)
    return obj({**props, "idempotency_key": KEY}, needs + ["idempotency_key"], strict=True)


def observation(source, props, required):
    return write({"source": {"const": source}, "subject_id": ID, "instance_id": ID, **props},
                 ["source", "instance_id", *required])


def deletion(scope):
    fields = {"scope": {"const": scope}, "confirm": {"const": True}}
    if scope != "all":
        fields["id"] = ID
    return write(fields)


def document():
    schemas = {
        "Subject": obj({"subject_id": ID, "name": ID, "created_at": DATE, "level": INT}),
        "Instance": obj({"subject_id": ID, "instance_id": ID, "session_id": ID, "name": ID}),
        "Event": obj({"event_id": ID, "subject_id": ID, "instance_id": ID, "session_id": ID,
                      "seq": INT, "type": STRING, "source": SOURCES, "actor": STRING,
                      "created_at": DATE, "hash": STRING, "prev_hash": STRING, "version": INT,
                      "related": array(ID), "payload": {"type": "object"}}),
        "Request": obj({"request_id": ID, "stage": STRING, "original": ref("Event"), "history": array(ref("Event"))}),
        "Backup": obj({"backup_id": ID, "created_at": DATE}),
        "Grant": obj({"token": STRING, "grant_id": ID,
                      "stdio": obj({"command": STRING, "args": {"type":"array","items":STRING,"minItems":1,"maxItems":1}}), "instance_id": {"type": ["string", "null"]},
                      "subject_id": {"type": ["string", "null"]}}),
        "Settings": obj({"observation_enabled": BOOL}),
        "Snapshot": obj({"subjects": array(ref("Subject")), "instances": array(ref("Instance")), "events": array(ref("Event")),
                         "report_states": array(ref("Event")), "requests": array(ref("Request")), "memory": {"type": "object"}, "stats": {"type": "object"},
                         "generated_at": DATE}),
        "Error": obj({"error": obj({"code": STRING, "message": STRING})}),
    }
    paths = {}

    def route(path, method, name, result, body=None, public=False):
        desc = {"operationId": name,
                "responses": {"200": {"description": "Success", "content": {"application/json": {"schema": result}}},
                              "default": {"description": "Request rejected", "content": {"application/json": {"schema": ref("Error")}}}}}
        if body is not None:
            desc["requestBody"] = {"required": True, "content": {"application/json": {"schema": body}}}
        if public:
            desc["security"] = []
        paths.setdefault("/api/" + path, {})[method] = desc
        return desc

    route("health", "get", "health", obj({"ok": BOOL, "version": STRING, "local_only": BOOL}), public=True)
    route("pair", "post", "exchangeOneTimeCode", obj({"token": STRING, "expires_in": INT, "role": {"const": "owner"}}),
          obj({"code": STRING}, strict=True), public=True)
    route("pair/code", "post", "createPairCode", obj({"code": STRING, "expires_in": INT, "expires_at": DATE, "server_time": DATE, "target": TARGET}),
          obj({"target": TARGET, "idempotency_key": KEY, "replaces": STRING}, ["idempotency_key"], strict=True))
    route("pair/status", "post", "getPairCodeStatus", obj({"state": enum("active","expired","used","replaced","unavailable"),
          "expires_in": INT, "expires_at": DATE, "server_time": DATE, "target": TARGET}, ["state", "expires_in"]),
          obj({"code": STRING}, strict=True))
    route("hosts/preview", "post", "previewHostConfig", obj({"plan_id":STRING,"can_write":BOOL,
          "preview":STRING,"target":{"type":["string","null"]},"status":{"type":"object"}}),
          obj({"host":enum("claude","codex","other"),"transport":enum("stdio","http"),
               "subject_id":ID,"instance_id":ID,"idempotency_key":KEY},["host","subject_id","instance_id"],strict=True))
    for step in ("apply","copy","probe","status"):
        route("hosts/"+step, "post", step+"HostConfig", {"type":"object"},
              obj({"plan_id":STRING,"confirm":BOOL,"idempotency_key":KEY},
                  ["plan_id"] if step=="status" else ["plan_id","confirm"],strict=True))
    route("logout", "post", "revokeCurrentBrowser", obj({"revoked": BOOL}), obj({"idempotency_key": KEY}, [], strict=True))
    route("settings", "get", "getSettings", ref("Settings"))
    route("settings", "post", "setSettings", ref("Settings"),
          write({"observation_enabled": BOOL}))
    route("snapshot", "get", "snapshot", ref("Snapshot"))["parameters"] = [
        {"in": "query", "name": "subject_id", "required": False, "schema": ID}]
    route("export", "get", "export", ref("Snapshot"))
    route("backups", "get", "listBackups", obj({"backups": array(ref("Backup"))}))
    route("integrity", "get", "verifyDatabase", obj({"ok": BOOL, "events": INT, "errors": array(STRING)}))
    route("schema", "get", "ownerSchema", {"type": "object"})
    route("subjects", "get", "listSubjects", obj({"subjects": array(ref("Subject"))}))
    route("subjects", "post", "createSubject", ref("Subject"), write({"name": ID}))
    route("instances", "post", "createInstance", ref("Instance"), write({"subject_id": ID, "name": ID}))
    route("credentials", "get", "listAgentGrants", obj({"grants": array(obj({
        "grant_id": ID, "subject_id": {"type": ["string","null"]},
        "instance_id": {"type": ["string","null"]}, "created_at": DATE}))}))
    route("credentials", "post", "issueAgent", ref("Grant"), write({"subject_id": ID, "instance_id": ID}, []))
    route("credentials/revoke", "post", "revokeAgent", obj({"revoked": BOOL}), write({"grant_id": ID}))
    route("level", "post", "setLevel", ref("Subject"), write({"subject_id": ID, "level": {"type":"integer","minimum":1,"maximum":3}}))
    route("observations", "post", "recordAttributedObservation", ref("Event"), {"oneOf": [
        observation("agent_visible_text", {"text": TEXT, "adapter": ID, "adapter_version": ID, "interaction_reference": ID}, ["text"]),
        observation("user_annotation", {"text": TEXT, "interaction_reference": ID}, ["text"]),
        observation("model_estimated", {"event_id": ID, "alpha": {"type": "number", "minimum": 0, "maximum": 1}}, ["event_id"])
    ]})
    route("chat/connect", "post", "connectModel", obj({
        "chat_id":ID, "instance_id":ID, "session_id":ID, "model":STRING,
        "provider_status":enum("model_listed","model_unlisted","catalog_unavailable"),
        "tools":array(STRING), "idle_timeout_seconds":INT}),
        obj({"instance_id":ID,"base_url":STRING,"model":ID,"api_key":{"type":"string","writeOnly":True},
             "allow_remote":BOOL,"idempotency_key":KEY},["instance_id","base_url","model"], strict=True))
    route("chat/message", "post", "sendChatMessage", obj({
        "reply":STRING,"model":STRING,"status":enum("answered","tool_limit"),"tool_errors":array(obj({"tool":STRING,"code":STRING})),
        "tool_events":array(obj({"ok":BOOL,"event_id":ID,"source":STRING,
                                                           "type":STRING,"created_at":DATE}))}),
        write({"chat_id":ID,"text":TEXT}))
    route("chat/close", "post", "closeModelChat", obj({"closed":BOOL}),
          obj({"chat_id":ID,"idempotency_key":KEY},["chat_id"], strict=True))
    route("runtime/sample", "post", "measureLocalRuntime", ref("Event"),
          write({"instance_id": ID, "request_id": ID}, ["instance_id"]))
    route("requests/{request_id}/respond", "post", "respond", ref("Request"),
          write({"stage": STAGES, "text": TEXT}, ["stage"]))["parameters"] = [
              {"name":"request_id","in":"path","required":True,"schema":ID}]
    route("backup", "post", "createBackup", ref("Backup"), write())
    route("restore", "post", "restoreBackup", obj({"restored": BOOL, "backup_id": ID}), write({"backup_id": ID}))
    route("delete", "post", "deleteData", obj({"deleted": BOOL, "purged_backups": INT}),
          {"oneOf": [deletion(scope) for scope in ("subject","session","all")]})
    return {"openapi": "3.1.0", "info": {"title": "Silicon Life State · owner API", "version": "1.0.1"},
            "servers": [{"url": "/"}], "paths": paths,
            "components": {"schemas": schemas, "securitySchemes": {"ownerBearer": {"type": "http", "scheme": "bearer"}}},
            "security": [{"ownerBearer": []}]}


if __name__ == "__main__":
    import json
    print(json.dumps(document(), indent=2, ensure_ascii=False))
