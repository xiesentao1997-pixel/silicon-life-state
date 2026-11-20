"""Read-only projection. Reuse the owner's effective states and original event IDs."""
def record(event):
    payload = event["payload"]
    text = payload.get("state_text") or payload.get("text") or payload.get("note")
    if not text:
        text = " · ".join(payload.get("state_tags", [])) or " ".join(
            f"{key}={value}" for key, value in payload.items()
            if key in {"valence", "arousal", "dominance", "load", "estimated_valence", "assessment", "decision"})
    return {key: event[key] for key in ("subject_id", "instance_id", "event_id", "source", "type", "created_at", "seq")} | {
        "text": text or "", "revision_id": event.get("revision_id"), "payload": payload}


def feed(store, sid=None, iid=None):
    subjects = store.admin("list_subjects", {})["subjects"]
    sid = sid or (subjects[0]["subject_id"] if subjects else None)
    result = {"subjects": [{"id": s["subject_id"], "name": s["name"]} for s in subjects],
              "subject_id": sid, "instances": [], "states": [], "requests": [], "observations": [], "shared": []}
    if sid is None:
        return result
    snap = store.admin("snapshot", {"subject_id": sid})
    result["instances"] = [{"id": i["instance_id"], "name": i["name"]} for i in snap["instances"]]
    selected = [i for i in snap["instances"] if not iid or i["instance_id"] == iid]
    result["states"] = [record(i["state"]) for i in selected if i["state"]]
    def matches(e):
        return not iid or iid == e["instance_id"]
    result["requests"] = [record(r["original"]) | {"stage": r["stage"]} for r in snap["requests"] if matches(r["original"])]
    result["observations"] = [record(e) for e in snap["events"] if matches(e) and
                              e["source"] in {"agent_visible_text", "model_estimated"}][:20]
    result["shared"] = [record(e) for e in snap["memory"]["proposals"]][:30]
    return result
