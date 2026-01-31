import random

random.seed(7)

DATASET_ID = "ds_001"
VERSION_ID = "v_001"
POLICY_PROFILE_ID = "pp_001"

def mock_readiness_cards():
    return {"verification": 0.62, "acceptance": 0.44, "constraints": 0.58, "evidence": 0.71}

def mock_requirements(n=60):
    items = []
    for i in range(1, n + 1):
        items.append({
            "req_id": f"REQ-{i:04d}",
            "source": random.choice(["OEM", "SupplierA", "SupplierB"]),
            "domain": random.choice(["brake", "steering", "body", "powertrain"]),
            "component": random.choice(["BrakeECU", "SteerECU", "BodyECU", "GatewayECU"]),
            "goal": random.choice(["SG-01", "SG-02", "SG-12", "SG-20"]),
            "action_type": random.choice(["detect", "mitigate", "transition", "limit", "warn", "redundancy"]),
            "underspec": round(random.uniform(0.1, 0.9), 2),
            "overspec": round(random.uniform(0.0, 0.8), 2),
            "evidence": round(random.uniform(0.2, 0.95), 2),
            "verifiability": round(random.uniform(0.1, 0.95), 2),
            "unknown_count": random.randint(0, 5),
        })
    return items

REQS = mock_requirements()

def mock_list_requirements(search="", sort="underspec_desc"):
    rows = REQS
    if search:
        s = search.lower()
        rows = [r for r in rows if s in r["req_id"].lower() or s in r["component"].lower() or s in (r.get("goal","").lower())]
    if sort == "overspec_desc":
        rows = sorted(rows, key=lambda x: x["overspec"], reverse=True)
    else:
        rows = sorted(rows, key=lambda x: x["underspec"], reverse=True)
    return {"total": len(rows), "items": rows}

def mock_requirement(req_id: str):
    r = next((x for x in REQS if x["req_id"] == req_id), None)
    if not r:
        return None
    return {
        "req_id": req_id,
        "raw_text": f"[Mock] {req_id}: The system shall ...\n- Trigger: ...\n- Constraint: ...\n- Verification: ...",
        "meta": {k: r.get(k) for k in ["source","domain","component","goal","action_type"]}
    }

def mock_ir(req_id: str):
    slot_names = ["intent","goal","action_statement","action_type","trigger_condition","constraints",
                  "verification_method","acceptance_criteria","testability","assumption"]
    seed = sum(ord(c) for c in req_id)
    slots = []
    for idx, s in enumerate(slot_names):
        unknown = ((seed + idx) % 5) == 0
        slots.append({
            "slot_name": s,
            "value": None if unknown else f"{s} value for {req_id}",
            "status": "UNKNOWN" if unknown else "CONFIRMED",
            "confidence": 0.35 if unknown else 0.82,
            "anchors": [{
                "doc_ref": {"doc_id":"DOC-1","page":1,"line":10+idx},
                "span_start":0,"span_end":10,
                "quote": f"evidence for {s}"
            }]
        })
    unknown_fields = [x["slot_name"] for x in slots if x["status"] == "UNKNOWN"]
    return {"req_id": req_id, "ir_version":"ir_001", "standard_granularity_level":"L1",
            "slots": slots, "residual": [], "unknown_fields": unknown_fields}

def mock_scores():
    import random
    return {
        "underspec": round(random.random(), 2),
        "overspec": round(random.random(), 2),
        "evidence": round(random.random(), 2),
        "verifiability": round(random.random(), 2),
    }

def mock_similar(req_id: str):
    pool = [r for r in REQS if r["req_id"] != req_id][:10]
    neighbors = []
    for i, r in enumerate(pool):
        neighbors.append({
            "neighbor_req_id": r["req_id"],
            "similarity": round(0.6 + random.random() * 0.35, 2),
            "gate_flags": {"action_type_match": i % 2 == 0, "goal_match": i % 3 == 0, "component_match": i % 4 == 0}
        })
    return {"neighbors": neighbors}

# suggestions job mock (Streamlit session_state에서 처리할 예정)