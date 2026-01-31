import streamlit as st
from api_client import USE_MOCK
from mock_data import mock_requirement, mock_ir, mock_scores
from db import upsert_requirement, upsert_ir_slots, list_slots, get_slot, add_audit, list_audit

st.title("Requirement Detail")

dataset_id = st.session_state.get("dataset_id", "ds_001")
version_id = st.session_state.get("version_id", "v_001")

req_id = st.session_state.get("selected_req_id", "REQ-0001")
req_id = st.text_input("req_id", req_id)
st.session_state.selected_req_id = req_id

# ---- Load from mock or backend ----
if USE_MOCK:
    detail = mock_requirement(req_id)
    ir = mock_ir(req_id)
    scores = mock_scores()
else:
    from api_client import get_requirement, get_requirement_ir, get_requirement_scores
    detail = get_requirement(req_id, dataset_id, version_id)
    ir = get_requirement_ir(req_id, version_id)
    scores = get_requirement_scores(req_id, version_id)

if not detail:
    st.error("Requirement not found.")
    st.stop()

# ---- Persist snapshot to DB (idempotent) ----
upsert_requirement(detail)
upsert_ir_slots(req_id, ir.get("slots", []))

left, right = st.columns([1.3, 1.0])

with left:
    st.subheader("Raw text")
    st.code(detail.get("raw_text", ""), language="text")

with right:
    st.subheader("Scores")
    st.json(scores)

st.divider()

# ---- Slot editor ----
st.subheader("IR Slot Editor (Decision + Audit)")

slots = list_slots(req_id)
slot_names = [s["slot_name"] for s in slots] if slots else []
if not slot_names:
    st.info("No IR slots stored yet.")
    st.stop()

colA, colB, colC = st.columns([2, 1, 1])
selected_slot = colA.selectbox("slot_name", options=slot_names, index=0)
actor = colB.text_input("actor", value=st.session_state.get("actor", "reviewer"))
st.session_state["actor"] = actor

slot = get_slot(req_id, selected_slot)
prev_state = {
    "value": slot.get("value"),
    "status": slot.get("status"),
    "confidence": slot.get("confidence"),
    "anchors": slot.get("anchors"),
}

# Anchors 확인
with st.expander("Anchors (evidence)"):
    anchors = slot.get("anchors") or []
    if not anchors:
        st.warning("No anchors. Confirm는 지양(또는 금지)하는 것이 안전합니다.")
    for a in anchors:
        doc_ref = (a.get("doc_ref") or {})
        st.caption(f"{doc_ref.get('doc_id','')} p{doc_ref.get('page','')} l{doc_ref.get('line','')}")
        q = a.get("quote")
        if q:
            st.write(q)

# value 편집(문자열로 편집 → 저장 시 문자열/리스트는 후속에서 다듬어도 됨)
cur_value = slot.get("value")
value_text = st.text_area(
    "value (edit)",
    value="" if cur_value is None else (", ".join(cur_value) if isinstance(cur_value, list) else str(cur_value)),
    height=80
)

status = st.selectbox(
    "status",
    options=["CONFIRMED", "UNKNOWN", "PROPOSED", "CONFLICTED"],
    index=["CONFIRMED","UNKNOWN","PROPOSED","CONFLICTED"].index(slot.get("status","UNKNOWN"))
)

rationale = st.text_area("rationale (why this decision?)", height=80)

# 정책: anchors 없으면 CONFIRMED 금지(원하면 완화 가능)
anchors_exist = bool(slot.get("anchors"))
confirm_blocked = (status == "CONFIRMED" and not anchors_exist)

if confirm_blocked:
    st.error("Anchors가 없으므로 CONFIRMED 저장을 막았습니다. (UNKNOWN/PROPOSED로 두고 리뷰 큐에서 관리 권장)")

save_disabled = confirm_blocked or (not rationale.strip())

if st.button("Save decision", disabled=save_disabled):
    # value 처리: 현재는 단순 문자열 저장(후속에 list/structured 지원 확대)
    next_value = value_text.strip() if value_text.strip() else None
    next_state = {
        "value": next_value,
        "status": status,
        "confidence": slot.get("confidence"),
        "anchors": slot.get("anchors"),
    }

    # DB 업데이트: 슬롯 단위 upsert
    upsert_ir_slots(req_id, [{
        "slot_name": selected_slot,
        "value": next_value,
        "status": status,
        "confidence": slot.get("confidence"),
        "anchors": slot.get("anchors"),
    }])

    # Audit log
    add_audit(req_id, selected_slot, prev_state, next_state, rationale=rationale.strip(), actor=actor)

    st.success("Saved. (slot updated + audit appended)")
    st.rerun()

# ---- Lightweight slot list (no dataframe) ----
st.divider()
st.subheader("IR Slots (read-only list)")

show_cols = ["slot_name", "status", "confidence", "value"]
header = st.columns([1.2, 1.2, 0.8, 3.0])
for c, k in zip(header, show_cols):
    c.markdown(f"**{k}**")

for s in list_slots(req_id):
    cols = st.columns([1.2, 1.2, 0.8, 3.0])
    cols[0].write(s.get("slot_name",""))
    cols[1].write(s.get("status",""))
    conf = s.get("confidence","")
    cols[2].write(f"{conf:.2f}" if isinstance(conf, (int, float)) else conf)
    v = s.get("value", None)
    cols[3].write("" if v is None else (", ".join(v) if isinstance(v, list) else str(v)))

# ---- Audit viewer ----
st.divider()
st.subheader("Audit log (latest)")

aud = list_audit(req_id, limit=30)
if not aud:
    st.info("No audit records yet.")
else:
    for a in aud:
        with st.expander(f"#{a['audit_id']} {a['slot_name']} by {a.get('actor','')} @ {a.get('created_at','')}"):
            st.write("rationale:", a.get("rationale",""))
            st.json({"prev": a.get("prev_json"), "next": a.get("next_json")})

# Nav
c1, c2 = st.columns(2)
with c1:
    if st.button("Go to Similarity/Suggest"):
        st.session_state.selected_req_id = req_id
        st.switch_page("pages/4_Similarity_and_Suggest.py")
with c2:
    if st.button("Back to Explorer"):
        st.switch_page("pages/2_Requirements_Explorer.py")