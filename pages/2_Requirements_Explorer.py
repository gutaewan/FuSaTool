import os
import sqlite3
from typing import Dict, List, Optional, Tuple


import streamlit as st

# ------------------------- Top navigation (horizontal) -------------------------
PAGES = [
    ("📥 Data Import", "pages/0_Data_import.py"),
    ("🗺️ Overview", "pages/1_Overview.py"),
    ("📚 Explorer", "pages/2_Requirements_Explorer.py"),
    ("🔎 Detail", "pages/3_Requirement_Detail.py"),
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
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_top_nav(current_path: str, title: str = "") -> None:
    """Render a top horizontal navigation bar for page navigation."""
    _hide_sidebar_css()

    # Slightly more intuitive nav: icons + clear current page + a right-side status badge.
    nav_cols = st.columns([1] * len(PAGES) + [1.8], vertical_alignment="center")

    for i, (name, path) in enumerate(PAGES):
        is_current = (path == current_path)

        if is_current:
            # Current page: show a non-clickable, clearly marked pill.
            nav_cols[i].markdown(
                f"<div style='padding:0.45rem 0.6rem;border-radius:999px;"
                f"border:1px solid rgba(49,51,63,0.25);background:rgba(49,51,63,0.08);"
                f"text-align:center;font-weight:600;'>✅ {name}</div>",
                unsafe_allow_html=True,
            )
        else:
            if nav_cols[i].button(name, use_container_width=True, key=f"nav_{current_path}_{path}"):
                st.switch_page(path)

    # Right-side status
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
                "<div style='padding:0.35rem 0.6rem;border-radius:10px;"
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
        st.caption(title)

    st.divider()

# ------------------------------
# DB helpers
# ------------------------------
ROOT = os.path.dirname(os.path.dirname(__file__))  # FuSaTool/
DB_PATH = st.session_state.get("db_path") or os.getenv("FUSA_DB_PATH", os.path.join(ROOT, "fusa_tool.db"))
DB_PATH = os.path.abspath(DB_PATH)


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def fetch_all(sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
    with conn() as c:
        return c.execute(sql, params).fetchall()


def fetch_one(sql: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute(sql, params).fetchone()


# ------------------------------
# Page
# ------------------------------
st.set_page_config(page_title="Requirements Explorer", layout="wide")
render_top_nav("pages/2_Requirements_Explorer.py", "Requirements Explorer")
st.title("Requirements Explorer")
st.caption(f"DB: {DB_PATH}")
# Keep DB path stable across navigation
st.session_state["db_path"] = DB_PATH

# IDs used by other pages (optional)
dataset_id = st.session_state.get("dataset_id", "imported")
version_id = st.session_state.get("version_id", "v1")

# ------------------------------
# Catalogs (from DB)
# ------------------------------
vehicle_models = [r["vehicle_model_id"] for r in fetch_all("SELECT vehicle_model_id FROM vehicle_models ORDER BY vehicle_model_id")]
ecus = [r["ecu_id"] for r in fetch_all("SELECT ecu_id FROM ecus ORDER BY ecu_id")]

# Fallback: infer from scope if catalog tables are empty
if not vehicle_models:
    vehicle_models = [r["vm"] for r in fetch_all("SELECT DISTINCT vehicle_model_id AS vm FROM requirements_scope ORDER BY vm")]
if not ecus:
    ecus = [r["ecu"] for r in fetch_all("SELECT DISTINCT ecu_id AS ecu FROM requirements_scope ORDER BY ecu")]

if not vehicle_models or not ecus:
    st.warning("DB에 차종/ECU 카탈로그가 없습니다. Data Import에서 Save to DB (SQLite Commit) 완료 후 다시 시도하세요.")
    st.stop()

# Default selection comes from Overview drill-down
pre_vm = st.session_state.get("selected_vehicle_model_id")
pre_ecu = st.session_state.get("selected_ecu_id")

# ------------------------------
# Filters
# ------------------------------
left, right = st.columns([1, 3], gap="large")

with left:
    st.subheader("Filters")

    vm_sel = st.selectbox(
        "차종(vehicle model)",
        options=vehicle_models,
        index=(vehicle_models.index(pre_vm) if pre_vm in vehicle_models else 0),
    )

    ecu_sel = st.selectbox(
        "ECU",
        options=ecus,
        index=(ecus.index(pre_ecu) if pre_ecu in ecus else 0),
    )

    # keep selection for other pages
    st.session_state["selected_vehicle_model_id"] = vm_sel
    st.session_state["selected_ecu_id"] = ecu_sel

    st.divider()
    search = st.text_input("Search (req_id / raw_text / source)", "")
    sort = st.selectbox(
        "Sort",
        ["unknown_desc", "unknown_asc", "textlen_desc", "req_id_asc"],
        index=0,
        help="unknown_*는 IR 슬롯 중 UNKNOWN 개수 기준. textlen_desc는 raw_text 길이 기준(임시 overspec proxy).",
    )

    page_size = st.selectbox("Rows per page", [10, 20, 50, 100], index=1)

# ------------------------------
# Query builders
# ------------------------------

def build_where(vm: str, ecu: str, q: str) -> Tuple[str, List]:
    where = ["sc.vehicle_model_id = ?", "sc.ecu_id = ?"]
    params: List = [vm, ecu]

    if q:
        like = f"%{q}%"
        where.append("(r.req_id LIKE ? OR r.raw_text LIKE ? OR r.source LIKE ?)")
        params.extend([like, like, like])

    return " AND ".join(where), params


def order_by(sort_key: str) -> str:
    if sort_key == "unknown_desc":
        return "unknown_count DESC, r.req_id ASC"
    if sort_key == "unknown_asc":
        return "unknown_count ASC, r.req_id ASC"
    if sort_key == "textlen_desc":
        return "LENGTH(COALESCE(r.raw_text,'')) DESC, r.req_id ASC"
    return "r.req_id ASC"


# ------------------------------
# Fetch total + page
# ------------------------------
where_sql, where_params = build_where(vm_sel, ecu_sel, search)

# total distinct requirements in this scope
row_total = fetch_one(
    f"""
    SELECT COUNT(DISTINCT r.req_id) AS total
    FROM requirements_scope sc
    JOIN requirements_raw r ON r.req_id = sc.req_id
    WHERE {where_sql}
    """,
    tuple(where_params),
)

total = int(row_total["total"]) if row_total else 0

max_page = max(1, (total + int(page_size) - 1) // int(page_size))

with left:
    page = st.number_input("Page", min_value=1, max_value=max_page, value=1, step=1)

offset = (int(page) - 1) * int(page_size)

# main list: join raw + aggregate unknown slots
rows = fetch_all(
    f"""
    WITH scoped AS (
      SELECT DISTINCT sc.req_id
      FROM requirements_scope sc
      WHERE {where_sql}
    ),
    unk AS (
      SELECT req_id, COUNT(*) AS unknown_count
      FROM ir_slots
      WHERE status = 'UNKNOWN'
      GROUP BY req_id
    )
    SELECT
      r.req_id AS req_id,
      COALESCE(r.source, '') AS source,
      COALESCE(r.domain, '') AS domain,
      ? AS vehicle_model_id,
      ? AS ecu_id,
      COALESCE(unk.unknown_count, 0) AS unknown_count,
      LENGTH(COALESCE(r.raw_text,'')) AS text_len,
      SUBSTR(COALESCE(r.raw_text,''), 1, 120) AS raw_text_preview
    FROM scoped s
    JOIN requirements_raw r ON r.req_id = s.req_id
    LEFT JOIN unk ON unk.req_id = r.req_id
    ORDER BY {order_by(sort)}
    LIMIT ? OFFSET ?
    """,
    tuple(where_params) + (vm_sel, ecu_sel, int(page_size), int(offset)),
)

# ------------------------------
# Render
# ------------------------------
with right:
    st.subheader("Results")
    st.caption(f"Scope: VM={vm_sel} / ECU={ecu_sel} · Total: {total}")

    if total == 0:
        st.info("선택한 (차종, ECU) 범위에 요구사항이 없습니다.")
        st.stop()

    # table header
    header = st.columns([1.2, 1.2, 1.0, 1.0, 0.8, 0.8, 3.0])
    header[0].markdown("**Open**")
    header[1].markdown("**req_id**")
    header[2].markdown("**source**")
    header[3].markdown("**domain**")
    header[4].markdown("**unknown**")
    header[5].markdown("**len**")
    header[6].markdown("**raw_text (preview)**")

    # rows
    for r in rows:
        cols = st.columns([1.2, 1.2, 1.0, 1.0, 0.8, 0.8, 3.0])

        # open button
        if cols[0].button("Open", key=f"open_{r['req_id']}"):
            st.session_state["selected_req_id"] = r["req_id"]
            st.switch_page("pages/3_Requirement_Detail.py")

        cols[1].write(r["req_id"])
        cols[2].write(r["source"])  # may be empty
        cols[3].write(r["domain"])  # may be empty

        unk = int(r["unknown_count"]) if r["unknown_count"] is not None else 0
        cols[4].write(f"{unk}")
        cols[5].write(str(int(r["text_len"]) if r["text_len"] is not None else 0))
        cols[6].write(r["raw_text_preview"])

    st.divider()

    st.subheader("Quick actions")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.write("- Overview로 돌아가서 다른 (차종, ECU) 조합을 선택할 수 있습니다.")
        if st.button("Go to Overview"):
            st.switch_page("pages/1_Overview.py")
    with c2:
        st.write("- (차종, ECU) 선택은 좌측 필터에서 변경할 수 있습니다.")

# Keep a fallback selectbox for keyboard-driven navigation
st.divider()
st.subheader("Open detail (fallback)")
options = [r["req_id"] for r in rows]
selected = st.selectbox("Select req_id", options=options, index=0 if options else None)
if st.button("Go to Requirement Detail", disabled=(not bool(selected))):
    st.session_state["selected_req_id"] = selected
    st.switch_page("pages/3_Requirement_Detail.py")