import streamlit as st

# ------------------------- Top navigation (horizontal) -------------------------
PAGES = [
    ("📥 Data Import", "pages/0_Data_import.py"),
    ("🗺️ Overview", "pages/1_Overview.py"),
    ("📚 Explorer", "pages/2_Requirements_Explorer.py"),
    ("🔎 Detail", "pages/3_Requirement_Detail.py"),
    ("🧠 Similarity", "pages/4_Similarity_and_Suggest.py"),
]


def _hide_sidebar_css() -> None:
    """Hide Streamlit's default left multipage navigation."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarNav"] { display: none !important; }
        section.main { padding-left: 1rem !important; }
        .block-container { padding-top: 2.3rem; }

        /* Tighten spacing around the top nav divider and first header */
        div[data-testid="stVerticalBlock"] hr { margin: 0.25rem 0 0.45rem 0; }
        h1, h2, h3 { margin-top: 0.35rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_top_nav(current_path: str, title: str = "") -> None:
    """Render a top horizontal navigation bar for page navigation."""
    _hide_sidebar_css()

    nav_cols = st.columns([1] * len(PAGES) + [1.8])

    for i, (name, path) in enumerate(PAGES):
        is_current = (path == current_path)

        if is_current:
            nav_cols[i].markdown(
                "<div style='padding:0.40rem 0.55rem;border-radius:999px;"
                "border:1px solid rgba(49,51,63,0.25);background:rgba(49,51,63,0.08);"
                "text-align:center;font-weight:600;'>✅ "
                + name
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            if nav_cols[i].button(name, use_container_width=True, key=f"nav_{current_path}_{path}"):
                st.switch_page(path)

    with nav_cols[-1]:
        parts = []
        fn = st.session_state.get("uploaded_filename")
        if fn:
            parts.append(f"📄 {fn}")
        ds = st.session_state.get("dataset_id")
        ver = st.session_state.get("version_id")
        if ds and ver:
            parts.append(f"🗂️ {ds}/{ver}")
        if parts:
            st.markdown(
                "<div style='padding:0.30rem 0.55rem;border-radius:10px;"
                "border:1px solid rgba(49,51,63,0.18);background:rgba(49,51,63,0.04);"
                "text-align:right;font-size:0.85rem;'>"
                + " • ".join(parts)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='text-align:right;color:rgba(49,51,63,0.6);font-size:0.85rem;'>No dataset loaded</div>",
                unsafe_allow_html=True,
            )

    if title:
        st.markdown(
            f"<div style='margin-top:0.05rem;margin-bottom:0.10rem;opacity:0.75;font-size:0.9rem;'>{title}</div>",
            unsafe_allow_html=True,
        )

    st.divider()


from api_client import USE_MOCK
from mock_data import mock_requirement, mock_ir, mock_scores
import db

# alias for readability + ImportError resilience
upsert_requirement = db.upsert_requirement
upsert_ir_slots = db.upsert_ir_slots

db_get_requirement = db.get_requirement
list_requirement_ids = getattr(db, "list_requirement_ids", None)
if list_requirement_ids is None:
    def list_requirement_ids(limit: int = 5000):
        """Fallback: derive req_ids from list_requirements when helper is missing."""
        try:
            rows = db.list_requirements(limit=limit)
            return [r.get("req_id") for r in rows if r.get("req_id")]
        except Exception:
            return []
list_slots = db.list_slots
get_slot = db.get_slot
add_audit = db.add_audit
list_audit = db.list_audit

render_top_nav("pages/3_Requirement_Detail.py", "Requirement Detail")
st.title("Requirement Detail")

# Use dataset/version selected elsewhere (Data Import / Explorer)
dataset_id = st.session_state.get("dataset_id", "ds_001")
version_id = st.session_state.get("version_id", "v_001")

# Selected requirement comes from Explorer drill-down
req_id_from_state = st.session_state.get("selected_req_id", "")

with st.expander("Debug / Context", expanded=False):
    st.write(
        {
            "uploaded_filename": st.session_state.get("uploaded_filename"),
            "dataset_id": dataset_id,
            "version_id": version_id,
            "selected_req_id": req_id_from_state,
            "USE_MOCK": USE_MOCK,
            "selected_req_record": bool(st.session_state.get("selected_req_record")),
            "session_keys_hint": [k for k in st.session_state.keys() if "req" in k.lower() or "require" in k.lower()],
        }
    )


# --- Helper: Try to look up requirement from session_state cache if not in SQLite
def _lookup_req_from_session(req_id: str):
    """Best-effort lookup of a requirement record from session_state caches."""
    if not req_id:
        return None

    # Highest-priority handoff: Explorer can pass the selected record directly
    sel = st.session_state.get("selected_req_record")
    if isinstance(sel, dict) and sel.get("req_id") == req_id:
        return sel

    # Common cache patterns used in this app (try several keys)
    candidates = []
    for key in [
        "requirements_by_id",
        "requirements_index",
        "requirements_cache_by_id",
        "requirements",
        "requirements_cache",
        "loaded_requirements",
        "parsed_requirements",
        "fusa_requirements",
    ]:
        if key in st.session_state:
            candidates.append((key, st.session_state.get(key)))

    # Direct dict mapping
    for key, obj in candidates:
        if isinstance(obj, dict) and req_id in obj:
            return obj[req_id]

    # List of records
    for key, obj in candidates:
        if isinstance(obj, list):
            for r in obj:
                if isinstance(r, dict) and r.get("req_id") == req_id:
                    return r

    return None


def _normalize_record_shape(rec: dict):
    """Normalize an imported JSON record into the shape expected by this page/db."""
    if not isinstance(rec, dict):
        return None

    meta = rec.get("meta") or {}
    raw_text = rec.get("raw_text") or rec.get("text") or ""

    # Some loaders nest IR under ir_record
    ir_record = rec.get("ir_record") or {}
    slots = ir_record.get("slots") or []

    detail = {
        "req_id": rec.get("req_id"),
        "meta": meta,
        "raw_text": raw_text,
    }

    ir = {"slots": slots}
    return detail, ir

# If nothing was passed from Explorer, allow selecting from DB
available_ids = []
try:
    available_ids = list_requirement_ids(limit=5000) or []
except Exception as e:
    available_ids = []
    st.warning(f"DB list_requirement_ids failed: {e}")

if (not req_id_from_state) and available_ids:
    picked = st.selectbox("Select a requirement", options=[""] + available_ids, index=0)
    if picked:
        st.session_state["selected_req_id"] = picked
        req_id_from_state = picked

# Always allow manual override
req_id = st.text_input("req_id", value=req_id_from_state)
req_id = (req_id or "").strip()
st.session_state["selected_req_id"] = req_id

if not req_id:
    st.info("No requirement selected. Go to Explorer and click Open, or select one above.")
    st.stop()

# ---- Load from mock or backend ----
# NOTE: Even when USE_MOCK is enabled, fall back to SQLite if the record exists.
if USE_MOCK:
    detail = mock_requirement(req_id)
    ir = mock_ir(req_id)
    scores = mock_scores()

    # If mock data doesn't contain this req_id, but SQLite does, show the real record.
    if not detail:
        _db_detail = db_get_requirement(req_id)
        if _db_detail:
            detail = _db_detail
            ir = {"slots": list_slots(req_id)}
            scores = {"note": "USE_MOCK enabled, but this req_id was loaded from SQLite."}
else:
    # Try API first (if configured). If it fails, fall back to local SQLite DB.
    detail = None
    ir = {"slots": []}
    scores = {}

    try:
        from api_client import get_requirement, get_requirement_ir, get_requirement_scores

        detail = get_requirement(req_id, dataset_id, version_id)
        ir = get_requirement_ir(req_id, version_id) or {"slots": []}
        scores = get_requirement_scores(req_id, version_id) or {}

        # If API is reachable but returns empty/None payloads, fall back to SQLite.
        # (This avoids the "Requirement not found" case when DB actually has the record.)
        if not detail:
            raise RuntimeError("API returned empty detail; fallback to SQLite")
    except Exception as e:
        # 1) First try SQLite
        detail = db_get_requirement(req_id)
        if detail:
            ir = {"slots": list_slots(req_id)}
            scores = {"note": f"API unavailable; loaded from SQLite. ({e})"}
        else:
            # 2) If not in SQLite yet, try in-memory JSON cache from Data Import / Explorer
            rec = _lookup_req_from_session(req_id)
            if rec:
                norm = _normalize_record_shape(rec)
                if norm:
                    detail, ir = norm
                    scores = {"note": "Loaded from session cache (not yet committed to SQLite)."}

                    # Best-effort persist to SQLite so next navigation works
                    try:
                        upsert_requirement(detail)
                    except Exception:
                        pass
                    try:
                        upsert_ir_slots(req_id, ir.get("slots", []))
                    except Exception:
                        pass
                else:
                    scores = {"note": "Session cache record found but could not normalize."}
            else:
                scores = {"note": "Not found in SQLite, and no session cache record was available."}
                detail = None
                ir = {"slots": []}

# If not found, show why (but keep it compact)
if detail is None:
    with st.expander("Why not found? (debug)", expanded=True):
        st.write({
            "req_id": req_id,
            "in_sqlite": bool(db_get_requirement(req_id)),
            "has_selected_req_record": bool(st.session_state.get("selected_req_record")),
            "cache_keys_checked": [
                "selected_req_record",
                "requirements_by_id",
                "requirements_index",
                "requirements_cache_by_id",
                "requirements",
                "requirements_cache",
                "loaded_requirements",
                "parsed_requirements",
                "fusa_requirements",
            ],
        })

if not detail:
    st.error("Requirement not found.")
    st.stop()

# ---- Persist snapshot to DB (idempotent) ----
try:
    upsert_requirement(detail)
except Exception:
    pass
try:
    upsert_ir_slots(req_id, ir.get("slots", []))
except Exception:
    pass

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
slot_names = [s.get("slot_name") for s in slots] if slots else []
if not slot_names:
    st.info("No IR slots stored yet.")
    st.stop()

colA, colB, colC = st.columns([2, 1, 1])
selected_slot = colA.selectbox("slot_name", options=slot_names, index=0)
actor = colB.text_input("actor", value=st.session_state.get("actor", "reviewer"))
st.session_state["actor"] = actor

slot = get_slot(req_id, selected_slot) or {}
prev_state = {
    "value": slot.get("value"),
    "status": slot.get("status"),
    "confidence": slot.get("confidence"),
    "anchors": slot.get("anchors"),
}

with st.expander("Anchors (evidence)"):
    anchors = slot.get("anchors") or []
    if not anchors:
        st.warning("No anchors. Confirm는 지양(또는 금지)하는 것이 안전합니다.")
    for a in anchors:
        doc_ref = (a.get("doc_ref") or {}) if isinstance(a, dict) else {}
        st.caption(f"{doc_ref.get('doc_id','')} p{doc_ref.get('page','')} l{doc_ref.get('line','')}")
        q = a.get("quote") if isinstance(a, dict) else None
        if q:
            st.write(q)

cur_value = slot.get("value")
value_text = st.text_area(
    "value (edit)",
    value=""
    if cur_value is None
    else (", ".join(cur_value) if isinstance(cur_value, list) else str(cur_value)),
    height=80,
)

status = st.selectbox(
    "status",
    options=["CONFIRMED", "UNKNOWN", "PROPOSED", "CONFLICTED"],
    index=["CONFIRMED", "UNKNOWN", "PROPOSED", "CONFLICTED"].index(slot.get("status", "UNKNOWN")),
)

rationale = st.text_area("rationale (why this decision?)", height=80)

anchors_exist = bool(slot.get("anchors"))
confirm_blocked = (status == "CONFIRMED" and not anchors_exist)

if confirm_blocked:
    st.error("Anchors가 없으므로 CONFIRMED 저장을 막았습니다. (UNKNOWN/PROPOSED로 두고 리뷰 큐에서 관리 권장)")

save_disabled = confirm_blocked or (not rationale.strip())

if st.button("Save decision", disabled=save_disabled):
    next_value = value_text.strip() if value_text.strip() else None
    next_state = {
        "value": next_value,
        "status": status,
        "confidence": slot.get("confidence"),
        "anchors": slot.get("anchors"),
    }

    upsert_ir_slots(
        req_id,
        [
            {
                "slot_name": selected_slot,
                "value": next_value,
                "status": status,
                "confidence": slot.get("confidence"),
                "anchors": slot.get("anchors"),
            }
        ],
    )

    add_audit(req_id, selected_slot, prev_state, next_state, rationale=rationale.strip(), actor=actor)

    st.success("Saved. (slot updated + audit appended)")
    st.rerun()

st.divider()
st.subheader("IR Slots (read-only list)")

show_cols = ["slot_name", "status", "confidence", "value"]
header = st.columns([1.2, 1.2, 0.8, 3.0])
for c, k in zip(header, show_cols):
    c.markdown(f"**{k}**")

for s in list_slots(req_id):
    cols = st.columns([1.2, 1.2, 0.8, 3.0])
    cols[0].write(s.get("slot_name", ""))
    cols[1].write(s.get("status", ""))
    conf = s.get("confidence", "")
    cols[2].write(f"{conf:.2f}" if isinstance(conf, (int, float)) else conf)
    v = s.get("value", None)
    cols[3].write("" if v is None else (", ".join(v) if isinstance(v, list) else str(v)))

st.divider()
st.subheader("Audit log (latest)")

aud = list_audit(req_id, limit=30)
if not aud:
    st.info("No audit records yet.")
else:
    for a in aud:
        with st.expander(f"#{a['audit_id']} {a['slot_name']} by {a.get('actor','')} @ {a.get('created_at','')}"):
            st.write("rationale:", a.get("rationale", ""))
            st.json({"prev": a.get("prev_json"), "next": a.get("next_json")})

c1, c2 = st.columns(2)
with c1:
    if st.button("Go to Similarity/Suggest"):
        st.session_state["selected_req_id"] = req_id
        st.switch_page("pages/4_Similarity_and_Suggest.py")
with c2:
    if st.button("Back to Explorer"):
        st.switch_page("pages/2_Requirements_Explorer.py")