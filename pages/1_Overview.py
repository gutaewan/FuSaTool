import os
import sqlite3
from typing import Dict, Tuple, List

import streamlit as st

# ---- DB ----
ROOT = os.path.dirname(os.path.dirname(__file__))  # FuSaTool/
# Prefer the DB path chosen/used by Data Import in the same Streamlit session.
DB_PATH = st.session_state.get("db_path") or os.getenv("FUSA_DB_PATH", os.path.join(ROOT, "fusa_tool.db"))
DB_PATH = os.path.abspath(DB_PATH)


def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def fetch_all(sql: str, params=()):
    with conn() as c:
        return c.execute(sql, params).fetchall()


# ---- Page ----
st.set_page_config(page_title="Overview", layout="wide")
st.title("Overview")
st.caption(f"DB: {DB_PATH}")
# Keep DB path in session so other pages stay consistent
st.session_state["db_path"] = DB_PATH

# Overview should NOT ask for file upload. Data Import page writes catalogs into DB.

# Make Overview resilient to session_state loss across navigation.
if "dataset_id" not in st.session_state:
    # dataset_id/version_id are useful for other pages, but Overview can run from DB alone.
    st.session_state["dataset_id"] = st.session_state.get("dataset_id", "imported")
    st.session_state["version_id"] = st.session_state.get("version_id", "v1")

dataset_id = st.session_state.get("dataset_id")
version_id = st.session_state.get("version_id")

# ---- catalogs ----
vehicle_models = [
    r["vehicle_model_id"]
    for r in fetch_all("SELECT vehicle_model_id FROM vehicle_models ORDER BY vehicle_model_id")
]
ecus = [r["ecu_id"] for r in fetch_all("SELECT ecu_id FROM ecus ORDER BY ecu_id")]

# Fallback: if catalog tables are empty but scope exists, infer catalogs from scope.
if not vehicle_models or not ecus:
    try:
        vm_from_scope = [r["vm"] for r in fetch_all("SELECT DISTINCT vehicle_model_id AS vm FROM requirements_scope ORDER BY vm")]
        ecu_from_scope = [r["ecu"] for r in fetch_all("SELECT DISTINCT ecu_id AS ecu FROM requirements_scope ORDER BY ecu")]
        if vm_from_scope:
            vehicle_models = vm_from_scope
        if ecu_from_scope:
            ecus = ecu_from_scope
    except Exception:
        pass

# ---- applicability (vehicle model × ECU) ----
rows_app = fetch_all(
    "SELECT vehicle_model_id AS vm, ecu_id AS ecu, is_applicable AS ok FROM vehicle_ecu_applicability"
)
app_map: Dict[Tuple[str, str], int] = {(r["vm"], r["ecu"]): int(r["ok"]) for r in rows_app}


def is_applicable(vm: str, ecu: str) -> bool:
    # Default to applicable if missing (but Data Import is expected to populate full matrix)
    return app_map.get((vm, ecu), 1) == 1


# ---- DB diagnostics (helps detect DB path mismatch or failed import) ----
try:
    vm_cnt = fetch_all("SELECT COUNT(*) AS c FROM vehicle_models")[0]["c"]
    ecu_cnt = fetch_all("SELECT COUNT(*) AS c FROM ecus")[0]["c"]
    app_cnt = fetch_all("SELECT COUNT(*) AS c FROM vehicle_ecu_applicability")[0]["c"]
    raw_cnt = fetch_all("SELECT COUNT(*) AS c FROM requirements_raw")[0]["c"]
    scope_cnt = fetch_all("SELECT COUNT(*) AS c FROM requirements_scope")[0]["c"]
    slots_cnt = fetch_all("SELECT COUNT(*) AS c FROM ir_slots")[0]["c"]

    with st.expander("DB diagnostics", expanded=True):
        st.write({
            "vehicle_models": int(vm_cnt),
            "ecus": int(ecu_cnt),
            "vehicle_ecu_applicability": int(app_cnt),
            "requirements_raw": int(raw_cnt),
            "requirements_scope": int(scope_cnt),
            "ir_slots": int(slots_cnt),
            "db_path": DB_PATH,
        })
except Exception as e:
    st.error(f"DB diagnostics failed: {e}")

if not vehicle_models or not ecus:
    st.warning(
        "차종/ECU 카탈로그가 비어 있습니다. Data Import가 DB에 기록되지 않았거나(또는 다른 DB를 보고 있거나) 입력 데이터에서 차종/ECU를 추정하지 못했을 수 있습니다. 위 DB diagnostics를 확인하세요."
    )
    st.stop()

# ---- Layout ----
left, right = st.columns([1, 3], gap="large")

with left:
    st.subheader("Filters")
    vm_sel = st.multiselect("차종(vehicle model)", vehicle_models, default=vehicle_models)
    ecu_sel = st.multiselect("ECU", ecus, default=ecus)

    metric = st.radio(
        "셀 값(metric)",
        ["#Requirements", "#UnknownSlots", "UnknownSlots per Requirement"],
        index=0,
    )

    st.divider()
    st.write("Drill-down (fallback)")
    fallback_vm = st.selectbox("차종 선택", vm_sel if vm_sel else vehicle_models)
    fallback_ecu = st.selectbox("ECU 선택", ecu_sel if ecu_sel else ecus)

    if not is_applicable(fallback_vm, fallback_ecu):
        st.info("선택한 (차종, ECU) 조합은 비적용(NA)입니다.")

    if st.button("이 조합으로 Explorer 열기", type="primary", disabled=(not is_applicable(fallback_vm, fallback_ecu))):
        st.session_state["selected_vehicle_model_id"] = fallback_vm
        st.session_state["selected_ecu_id"] = fallback_ecu
        st.switch_page("pages/2_Requirements_Explorer.py")

# ---- Matrix data (no pandas) ----
# counts: (vm, ecu) -> n_reqs
rows_req = fetch_all(
    """
SELECT s.vehicle_model_id AS vm, s.ecu_id AS ecu, COUNT(DISTINCT s.req_id) AS n_req
FROM requirements_scope s
GROUP BY s.vehicle_model_id, s.ecu_id
"""
)
req_map: Dict[Tuple[str, str], int] = {(r["vm"], r["ecu"]): int(r["n_req"]) for r in rows_req}

# unknown slots: (vm, ecu) -> n_unknown_slots (sum across reqs in that scope)
rows_unk = fetch_all(
    """
SELECT sc.vehicle_model_id AS vm, sc.ecu_id AS ecu, COUNT(*) AS n_unk
FROM requirements_scope sc
JOIN ir_slots sl ON sl.req_id = sc.req_id
WHERE sl.status = 'UNKNOWN'
GROUP BY sc.vehicle_model_id, sc.ecu_id
"""
)
unk_map: Dict[Tuple[str, str], int] = {(r["vm"], r["ecu"]): int(r["n_unk"]) for r in rows_unk}

# apply filters to axes
vm_axis = [x for x in vehicle_models if x in set(vm_sel)]
ecu_axis = [x for x in ecus if x in set(ecu_sel)]

if not vm_axis or not ecu_axis:
    right.warning("필터 결과가 비어 있습니다.")
    st.stop()


def cell_value(vm: str, ecu: str) -> float:
    if not is_applicable(vm, ecu):
        return 0.0
    nreq = req_map.get((vm, ecu), 0)
    nunk = unk_map.get((vm, ecu), 0)
    if metric == "#Requirements":
        return float(nreq)
    if metric == "#UnknownSlots":
        return float(nunk)
    return float(nunk) / float(nreq) if nreq > 0 else 0.0


matrix: List[List[float]] = [[cell_value(vm, ecu) for vm in vm_axis] for ecu in ecu_axis]

with right:
    st.subheader("Heatmap")

    # 1) render as lightweight HTML heatmap (no matplotlib)
    flat = [v for row in matrix for v in row]
    vmax = max(flat) if flat else 0.0

    def shade(v: float) -> str:
        if vmax <= 0:
            return "#ffffff"
        r = v / vmax
        base = 255
        depth = int(180 * min(max(r, 0.0), 1.0))
        red = base - depth
        green = base - int(depth * 0.6)
        blue = 255
        return f"rgb({red},{green},{blue})"

    MAX_HTML_VMS = 30
    MAX_HTML_ECUS = 40
    vm_h = vm_axis[:MAX_HTML_VMS]
    ecu_h = ecu_axis[:MAX_HTML_ECUS]

    html: List[str] = []
    html.append("<div style='overflow:auto; border:1px solid #ddd; border-radius:8px;'>")
    html.append("<table style='border-collapse:collapse; font-size:12px; min-width:900px;'>")

    # header
    html.append("<tr>")
    html.append(
        "<th style='position:sticky; left:0; background:#fafafa; border:1px solid #eee; padding:6px; text-align:left;'>ECU \\ VM</th>"
    )
    for vm in vm_h:
        html.append(
            "<th style='background:#fafafa; border:1px solid #eee; padding:6px; text-align:center; white-space:nowrap;'>"
            + vm
            + "</th>"
        )
    html.append("</tr>")

    # rows
    for ecu in ecu_h:
        html.append("<tr>")
        html.append(
            "<th style='position:sticky; left:0; background:#fafafa; border:1px solid #eee; padding:6px; text-align:left; white-space:nowrap;'>"
            + ecu
            + "</th>"
        )

        for vm in vm_h:
            applicable = is_applicable(vm, ecu)
            v = cell_value(vm, ecu)
            nreq = req_map.get((vm, ecu), 0)

            if not applicable:
                label = "NA"
                bg = "#f2f2f2"
            else:
                label = "-" if nreq == 0 else (
                    f"{v:.2f}" if metric == "UnknownSlots per Requirement" else f"{int(v)}"
                )
                bg = "#ffffff" if nreq == 0 else shade(v)

            html.append(
                "<td style='border:1px solid #eee; padding:6px; text-align:center; background:" + bg + ";'>"
                + label
                + "</td>"
            )

        html.append("</tr>")

    html.append("</table></div>")

    if len(vm_axis) > MAX_HTML_VMS or len(ecu_axis) > MAX_HTML_ECUS:
        st.caption(
            f"히트맵은 성능을 위해 일부만 표시합니다. (VM {len(vm_h)}/{len(vm_axis)}, ECU {len(ecu_h)}/{len(ecu_axis)})"
        )

    st.markdown("\n".join(html), unsafe_allow_html=True)
    st.caption("위 히트맵은 시각적 개요용입니다. 아래 Clickable Grid(또는 좌측 fallback)를 사용해 드릴다운하세요.")

    # 2) clickable grid (practical limit)
    MAX_VMS = 20
    MAX_ECUS = 30
    too_big = len(vm_axis) > MAX_VMS or len(ecu_axis) > MAX_ECUS

    if too_big:
        st.info(
            f"축이 큽니다(VM={len(vm_axis)}, ECU={len(ecu_axis)}). 버튼 그리드는 좌측 fallback 드릴다운을 사용하세요."
        )
    else:
        flat2 = [v for row in matrix for v in row]
        vmax2 = max(flat2) if flat2 else 0.0

        st.markdown("### Clickable Grid")
        st.caption("각 셀 버튼을 누르면 해당 (차종, ECU) 요구사항 목록으로 이동합니다. NA는 비활성화됩니다.")

        header_cols = st.columns([2] + [1] * len(vm_axis))
        header_cols[0].markdown("**ECU \\ VM**")
        for j, vm in enumerate(vm_axis):
            header_cols[j + 1].markdown(f"**{vm}**")

        for i, ecu in enumerate(ecu_axis):
            cols = st.columns([2] + [1] * len(vm_axis))
            cols[0].markdown(f"**{ecu}**")

            for j, vm in enumerate(vm_axis):
                val = matrix[i][j]
                nreq = req_map.get((vm, ecu), 0)
                applicable = is_applicable(vm, ecu)

                level = 0
                if vmax2 > 0:
                    ratio = val / vmax2
                    if ratio > 0.66:
                        level = 3
                    elif ratio > 0.33:
                        level = 2
                    elif ratio > 0:
                        level = 1

                if not applicable:
                    label = "NA"
                else:
                    label = "-" if nreq == 0 else (
                        f"{val:.2f}" if metric == "UnknownSlots per Requirement" else f"{int(val)}"
                    )

                dot = "○"
                if level == 1:
                    dot = "◔"
                if level == 2:
                    dot = "◑"
                if level == 3:
                    dot = "●"

                if cols[j + 1].button(
                    f"{dot} {label}",
                    key=f"cell_{ecu}_{vm}",
                    disabled=(not applicable),
                ):
                    st.session_state["selected_vehicle_model_id"] = vm
                    st.session_state["selected_ecu_id"] = ecu
                    st.switch_page("pages/2_Requirements_Explorer.py")

    st.divider()

    st.subheader("Top Hotspots")
    scored = []
    for ecu in ecu_axis:
        for vm in vm_axis:
            if not is_applicable(vm, ecu):
                continue
            nreq = req_map.get((vm, ecu), 0)
            if nreq == 0:
                continue
            nunk = unk_map.get((vm, ecu), 0)
            score = (nunk / nreq) if nreq else 0.0
            scored.append((score, vm, ecu, nreq, nunk))

    scored.sort(reverse=True, key=lambda x: x[0])
    top = scored[:10]

    if not top:
        st.write("표시할 hotspot이 없습니다.")
    else:
        for score, vm, ecu, nreq, nunk in top:
            cols = st.columns([3, 3, 2, 2, 2])
            cols[0].write(f"VM: **{vm}**")
            cols[1].write(f"ECU: **{ecu}**")
            cols[2].write(f"req: {nreq}")
            cols[3].write(f"unknown: {nunk}")
            if cols[4].button("열기", key=f"hot_{vm}_{ecu}"):
                st.session_state["selected_vehicle_model_id"] = vm
                st.session_state["selected_ecu_id"] = ecu
                st.switch_page("pages/2_Requirements_Explorer.py")