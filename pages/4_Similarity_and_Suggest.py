import time
import streamlit as st
from api_client import USE_MOCK
from mock_data import mock_similar

st.title("Similarity & Suggest (NFR complement)")

dataset_id = st.session_state.get("dataset_id", "ds_001")
version_id = st.session_state.get("version_id", "v_001")
policy_profile_id = st.session_state.get("policy_profile_id", "pp_001")

req_id = st.session_state.get("selected_req_id", "REQ-0001")
req_id = st.text_input("req_id", req_id)
st.session_state.selected_req_id = req_id

# Similar neighbors
if USE_MOCK:
    sim = mock_similar(req_id)
else:
    from api_client import get_similar
    sim = get_similar(req_id, dataset_id, version_id)

st.subheader("Similar requirements")

neighbors = sim.get("neighbors", [])
if not neighbors:
    st.info("No similar neighbors.")
else:
    show_cols = ["neighbor_req_id", "similarity", "gate_flags"]
    header = st.columns([1.4, 0.8, 2.8])
    for c, k in zip(header, show_cols):
        c.markdown(f"**{k}**")

    for n in neighbors:
        cols = st.columns([1.4, 0.8, 2.8])
        cols[0].write(n.get("neighbor_req_id", ""))
        simv = n.get("similarity", "")
        cols[1].write(f"{simv:.2f}" if isinstance(simv, (int, float)) else simv)
        cols[2].write(n.get("gate_flags", {}))

st.divider()
st.subheader("Generate suggestions (async job)")

nfr_priority = st.multiselect(
    "NFR priority slots",
    ["constraints","verification_method","acceptance_criteria","testability","assumption"],
    default=["constraints","verification_method","acceptance_criteria","testability","assumption"]
)

if "suggest_job_id" not in st.session_state:
    st.session_state.suggest_job_id = None
if "suggest_result" not in st.session_state:
    st.session_state.suggest_result = None

if st.button("Start suggestion job"):
    if USE_MOCK:
        # mock job: 즉시 job_id 발급 후 잠시 뒤 완료되는 것처럼 처리
        st.session_state.suggest_job_id = f"job_mock_{int(time.time())}"
        st.session_state.suggest_started_at = time.time()
        st.session_state.suggest_result = None
    else:
        from api_client import create_suggestions_job
        job = create_suggestions_job(req_id, dataset_id, version_id, policy_profile_id, nfr_priority)
        st.session_state.suggest_job_id = job["job_id"]
        st.session_state.suggest_result = None

job_id = st.session_state.suggest_job_id
if job_id:
    st.info(f"job_id = {job_id}")

    # poll
    if USE_MOCK:
        elapsed = time.time() - st.session_state.get("suggest_started_at", time.time())
        status = "SUCCEEDED" if elapsed > 1.2 else "RUNNING"
        job = {"job_id": job_id, "status": status, "progress": min(1.0, elapsed/1.2), "message": "mock"}
        st.json(job)
        if status == "SUCCEEDED" and st.session_state.suggest_result is None:
            st.session_state.suggest_result = {
                "target_req_id": req_id,
                "candidate_items": [{"slot_name": s, "proposed_value": f"{s} suggestion for {req_id}", "source_req_id": "REQ-0002"} for s in nfr_priority],
                "questions": ["Is there evidence?", "Keep UNKNOWN and escalate?"]
            }
    else:
        from api_client import get_job, get_suggestions_result
        job = get_job(job_id)
        st.json(job)
        if job["status"] == "SUCCEEDED" and st.session_state.suggest_result is None:
            st.session_state.suggest_result = get_suggestions_result(req_id, job_id)

    if st.session_state.suggest_result:
        st.subheader("Suggestion result")
        st.json(st.session_state.suggest_result)

    if st.button("Reset job"):
        st.session_state.suggest_job_id = None
        st.session_state.suggest_result = None

st.divider()
if st.button("Back to Detail"):
    st.session_state.selected_req_id = req_id
    st.switch_page("pages/3_Requirement_Detail.py")