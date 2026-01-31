import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


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

# DB path (local to project by default; can override via env var)
ROOT = os.path.dirname(os.path.dirname(__file__))  # FuSaTool/
DB_PATH = os.path.abspath(os.getenv("FUSA_DB_PATH", os.path.join(ROOT, "fusa_tool.db")))


def _conn() -> sqlite3.Connection:
    # Prefer the DB path shared across pages in this Streamlit session
    try:
        effective_path = st.session_state.get("db_path") or DB_PATH
    except Exception:
        effective_path = DB_PATH

    effective_path = os.path.abspath(effective_path)
    conn = sqlite3.connect(effective_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
# ------------------ helpers for robust catalog/applicability ------------------


# Helper: coerce any value to SQLite-safe scalar
def _to_sqlite_scalar(v: Any) -> Any:
    """Coerce values to SQLite-safe scalar types.

    SQLite driver accepts: None, str, int, float, bytes. For dict/list/other objects,
    serialize to JSON or string to avoid "Error binding parameter" issues.
    """
    if v is None:
        return None
    if isinstance(v, (str, int, float, bytes)):
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicle_models (
          vehicle_model_id TEXT PRIMARY KEY,
          name TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ecus (
          ecu_id TEXT PRIMARY KEY,
          name TEXT,
          domain TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicle_ecu_applicability (
          vehicle_model_id TEXT NOT NULL,
          ecu_id TEXT NOT NULL,
          is_applicable INTEGER NOT NULL,
          note TEXT,
          PRIMARY KEY (vehicle_model_id, ecu_id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requirements_raw (
          req_id TEXT PRIMARY KEY,
          dataset_id TEXT,
          version_id TEXT,
          source TEXT,
          domain TEXT,
          raw_text TEXT,
          meta_json TEXT,
          created_at TEXT,
          updated_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requirements_scope (
          req_id TEXT NOT NULL,
          vehicle_model_id TEXT NOT NULL,
          ecu_id TEXT NOT NULL,
          PRIMARY KEY (req_id, vehicle_model_id, ecu_id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_slots (
          req_id TEXT NOT NULL,
          slot_name TEXT NOT NULL,
          value_json TEXT,
          status TEXT,
          confidence REAL,
          anchors_json TEXT,
          standard_granularity_level TEXT,
          updated_at TEXT,
          PRIMARY KEY (req_id, slot_name)
        )
        """
    )

    # --- lightweight migrations for older DB files (CREATE TABLE IF NOT EXISTS won't add new columns) ---
    def _ensure_columns(table: str, required: Dict[str, str]) -> None:
        cols = [row["name"] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        existing = set(cols)
        for col, ctype in required.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")

    # requirements_raw: older DBs may miss dataset_id/version_id
    _ensure_columns(
        "requirements_raw",
        {
            "dataset_id": "TEXT",
            "version_id": "TEXT",
            "source": "TEXT",
            "domain": "TEXT",
            "raw_text": "TEXT",
            "meta_json": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
    )

    # ir_slots: keep forward-compatible if DB was created earlier
    _ensure_columns(
        "ir_slots",
        {
            "value_json": "TEXT",
            "status": "TEXT",
            "confidence": "REAL",
            "anchors_json": "TEXT",
            "standard_granularity_level": "TEXT",
            "updated_at": "TEXT",
        },
    )

    # indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scope_vehicle_ecu ON requirements_scope(vehicle_model_id, ecu_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_slots_status ON ir_slots(status)")

    conn.commit()
    conn.close()


def upsert_vehicle_models(items: List[Dict[str, Any]]) -> None:
    conn = _conn()
    for x in items or []:
        conn.execute(
            """
            INSERT INTO vehicle_models(vehicle_model_id, name)
            VALUES(?, ?)
            ON CONFLICT(vehicle_model_id) DO UPDATE SET
              name=excluded.name
            """,
            (x.get("vehicle_model_id"), x.get("name")),
        )
    conn.commit()
    conn.close()


def upsert_ecus(items: List[Dict[str, Any]]) -> None:
    conn = _conn()
    for x in items or []:
        conn.execute(
            """
            INSERT INTO ecus(ecu_id, name, domain)
            VALUES(?, ?, ?)
            ON CONFLICT(ecu_id) DO UPDATE SET
              name=excluded.name,
              domain=excluded.domain
            """,
            (x.get("ecu_id"), x.get("name"), x.get("domain")),
        )
    conn.commit()
    conn.close()


def upsert_applicability(items: List[Dict[str, Any]]) -> None:
    conn = _conn()
    for x in items or []:
        conn.execute(
            """
            INSERT INTO vehicle_ecu_applicability(vehicle_model_id, ecu_id, is_applicable, note)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(vehicle_model_id, ecu_id) DO UPDATE SET
              is_applicable=excluded.is_applicable,
              note=excluded.note
            """,
            (
                x.get("vehicle_model_id"),
                x.get("ecu_id"),
                int(x.get("is_applicable", 1)),
                x.get("note"),
            ),
        )
    conn.commit()
    conn.close()


# ------------------ helpers for robust catalog/applicability ------------------
def reset_catalog_tables() -> None:
    """Reset catalog/applicability tables so Overview reflects the current import."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM vehicle_ecu_applicability")
    cur.execute("DELETE FROM vehicle_models")
    cur.execute("DELETE FROM ecus")
    conn.commit()
    conn.close()


def build_full_applicability(vehicle_models: List[str], ecus: List[str], observed_pairs: set) -> List[Dict[str, Any]]:
    """Build full vehicle×ECU applicability matrix.

    - observed_pairs: set[(vehicle_model_id, ecu_id)] observed from requirements_scope.
    - Non-observed pairs are stored as is_applicable=0 so Overview can render NA.
    """
    rows: List[Dict[str, Any]] = []
    for vm in vehicle_models:
        for ecu in ecus:
            if (vm, ecu) in observed_pairs:
                rows.append({"vehicle_model_id": vm, "ecu_id": ecu, "is_applicable": 1, "note": "observed in scope"})
            else:
                rows.append({"vehicle_model_id": vm, "ecu_id": ecu, "is_applicable": 0, "note": "not observed in input (may be unknown)"})
    return rows


def upsert_requirements_raw(
    items: List[Dict[str, Any]],
    dataset_id: Optional[str] = None,
    version_id: Optional[str] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    for x in items or []:
        req_id = x.get("req_id")
        if not req_id:
            continue

        # Coerce to SQLite-safe types (some inputs may contain dict/list objects)
        req_id_s = _to_sqlite_scalar(req_id)
        raw_text = _to_sqlite_scalar(x.get("raw_text", ""))
        source = _to_sqlite_scalar(x.get("source"))
        domain = _to_sqlite_scalar(x.get("domain"))
        meta = x.get("meta", {}) or {}
        meta_json = _to_sqlite_scalar(meta)

        try:
            conn.execute(
                """
                INSERT INTO requirements_raw(req_id, dataset_id, version_id, source, domain, raw_text, meta_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(req_id) DO UPDATE SET
                  dataset_id=excluded.dataset_id,
                  version_id=excluded.version_id,
                  source=excluded.source,
                  domain=excluded.domain,
                  raw_text=excluded.raw_text,
                  meta_json=excluded.meta_json,
                  updated_at=excluded.updated_at
                """,
                (
                    req_id_s,
                    _to_sqlite_scalar(dataset_id),
                    _to_sqlite_scalar(version_id),
                    source,
                    domain,
                    raw_text,
                    meta_json,
                    now,
                    now,
                ),
            )
        except Exception as e:
            # Re-raise with context so the UI shows exactly which record caused the failure
            raise RuntimeError(
                f"SQLite write failed in requirements_raw for req_id={req_id_s!r}. "
                f"Types: source={type(x.get('source')).__name__}, domain={type(x.get('domain')).__name__}, "
                f"raw_text={type(x.get('raw_text')).__name__}, meta={type(meta).__name__}. "
                f"Original error: {e}"
            )

    conn.commit()
    conn.close()


def upsert_scope(items: List[Dict[str, Any]]) -> None:
    conn = _conn()
    for x in items or []:
        req_id = x.get("req_id")
        vm = x.get("vehicle_model_id")
        ecu = x.get("ecu_id")
        if not (req_id and vm and ecu):
            continue
        conn.execute(
            "INSERT OR IGNORE INTO requirements_scope(req_id, vehicle_model_id, ecu_id) VALUES(?, ?, ?)",
            (req_id, vm, ecu),
        )
    conn.commit()
    conn.close()


def upsert_ir_slots(req_id: str, slots: List[Dict[str, Any]]) -> None:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    for s in slots or []:
        slot_name = s.get("slot_name")
        if not slot_name:
            continue

        value = s.get("value", None)
        status = s.get("status", "UNKNOWN")
        confidence = s.get("confidence", None)
        anchors = s.get("anchors", None)
        std_level = s.get("standard_granularity_level", None)

        conn.execute(
            """
            INSERT INTO ir_slots(req_id, slot_name, value_json, status, confidence, anchors_json, standard_granularity_level, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(req_id, slot_name) DO UPDATE SET
              value_json=excluded.value_json,
              status=excluded.status,
              confidence=excluded.confidence,
              anchors_json=excluded.anchors_json,
              standard_granularity_level=excluded.standard_granularity_level,
              updated_at=excluded.updated_at
            """,
            (
                req_id,
                str(slot_name),
                json.dumps(value, ensure_ascii=False),
                str(status),
                float(confidence) if isinstance(confidence, (int, float)) else None,
                json.dumps(anchors, ensure_ascii=False),
                std_level,
                now,
            ),
        )

    conn.commit()
    conn.close()


# ------------------------- UI PAGE -------------------------

# ------------------------- UI PAGE -------------------------

st.set_page_config(page_title="Data Import", layout="wide")

render_top_nav("pages/0_Data_import.py", title="Data Import")


# Title placeholder at the original position (top)
_title = st.empty()

# Default title before upload
_title.title("Data Import")

st.caption(f"DB: {DB_PATH}")
# Share DB path across pages in this Streamlit session
st.session_state["db_path"] = os.path.abspath(DB_PATH)

init_db()

# Persistent upload state across page navigation
if "uploaded_payload" not in st.session_state:
    st.session_state["uploaded_payload"] = None
if "uploaded_filename" not in st.session_state:
    st.session_state["uploaded_filename"] = None
if "uploaded_bytes" not in st.session_state:
    st.session_state["uploaded_bytes"] = None
if "uploaded_at" not in st.session_state:
    st.session_state["uploaded_at"] = None

# Nonce to reset the file_uploader widget when clearing loaded JSON
if "uploader_nonce" not in st.session_state:
    st.session_state["uploader_nonce"] = 0

# If a JSON is already loaded, keep it across navigation.
# Streamlit's file_uploader cannot re-show a previously selected file, so we display the loaded filename.
if st.session_state.get("uploaded_payload") is not None and st.session_state.get("uploaded_filename"):
    st.success(
        f"현재 로드된 JSON: {st.session_state['uploaded_filename']} (세션 유지)"
        + (f" • loaded_at={st.session_state.get('uploaded_at')}" if st.session_state.get("uploaded_at") else "")
    )

with st.expander("JSON 업로드/교체", expanded=(st.session_state.get("uploaded_payload") is None)):
    uploaded = st.file_uploader(
        "FuSa requirements JSON 선택",
        type=["json"],
        key=f"fusa_json_uploader_{st.session_state['uploader_nonce']}",
        help="이미 로드된 JSON은 세션에 유지됩니다. 새 파일을 업로드하면 기존 로드된 JSON을 대체합니다.",
    )


# Update title after upload
if uploaded is not None:
    _title.title(f"Data Import — {uploaded.name}")
elif st.session_state.get("uploaded_filename"):
    _title.title(f"Data Import — {st.session_state['uploaded_filename']}")

# Optional: clear cached upload
if st.button("Clear loaded JSON", help="업로드/파싱된 JSON을 세션에서 제거하고 업로더를 초기화합니다."):
    # Clear cached payload/meta
    for k in [
        "uploaded_filename",
        "uploaded_payload",
        "uploaded_bytes",
        "uploaded_at",
        "jsonc_stripped",
        "dataset_id",
        "version_id",
        "policy_profile_id",
        "import_completed",
    ]:
        if k in st.session_state:
            del st.session_state[k]

    # Reset uploader by changing its key
    st.session_state["uploader_nonce"] = int(st.session_state.get("uploader_nonce", 0)) + 1

    # Rerun (compat)
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()

# If user navigates away and comes back, `uploaded` can be None.
# In that case, reuse the cached parsed payload from session_state.
if uploaded is None and st.session_state.get("uploaded_payload") is None:
    st.info("JSON 파일을 업로드해 주세요.")
    st.stop()

# JSONC comment stripper for JSON with comments
def _strip_json_comments(text: str) -> str:
    """Remove // and /* */ comments from JSON-like text (JSONC).

    This is a minimal, string-aware stripper to avoid removing comment markers inside quotes.
    """
    out = []
    i = 0
    n = len(text)
    in_str = False
    esc = False

    while i < n:
        ch = text[i]

        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue

        # not in string
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue

        # line comment //...
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in ("\n", "\r"):
                i += 1
            continue

        # block comment /* ... */
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2 if i + 1 < n else 0
            continue

        out.append(ch)
        i += 1

    return "".join(out)

# Parse immediately (use getvalue() to avoid empty reads on reruns)
if uploaded is not None:
    try:
        _raw_bytes = uploaded.getvalue()
        st.session_state["uploaded_bytes"] = _raw_bytes
        st.session_state["uploaded_at"] = datetime.utcnow().isoformat()
        _text = _raw_bytes.decode("utf-8")

        try:
            payload = json.loads(_text)
            st.session_state["jsonc_stripped"] = False
        except json.JSONDecodeError:
            # Try JSONC (JSON with comments)
            _clean = _strip_json_comments(_text)
            payload = json.loads(_clean)
            st.session_state["jsonc_stripped"] = True

        st.session_state["uploaded_filename"] = uploaded.name
        st.session_state["uploaded_payload"] = payload

        if st.session_state.get("jsonc_stripped"):
            st.info("JSONC(주석 포함) 형식으로 감지되어 주석을 제거한 뒤 파싱했습니다.")

    except Exception as e:
        st.error(f"JSON 파싱 실패: {e}")
        st.caption(
            "힌트: 표준 JSON은 /* ... */ 또는 // ... 주석을 허용하지 않습니다. 해당 주석을 제거하거나 JSONC 자동 제거 기능을 사용하세요."
        )
        st.stop()
else:
    # Reuse cached payload across navigation
    payload = st.session_state.get("uploaded_payload")
    if payload is not None:
        st.caption("업로드된 JSON을 세션 캐시에서 재사용 중입니다. (다른 페이지로 이동 후 돌아와도 유지됩니다.)")
        if st.session_state.get("uploaded_bytes"):
            st.caption(f"cached_size={len(st.session_state['uploaded_bytes'])} bytes")

# ---------- 1) Detect schema ----------
is_fusareq = isinstance(payload, dict) and "dataset_info" in payload and "requirements" in payload
if not is_fusareq:
    st.error("이 페이지는 현재 FuSaReq.json 포맷(dataset_info + requirements[])만 지원합니다.")
    st.stop()

dataset_info = payload.get("dataset_info", {}) or {}
reqs = payload.get("requirements", []) or []

dataset_id = dataset_info.get("dataset_id", "ds_001")
version_id = dataset_info.get("version_id", "v_001")
policy_profile_id = dataset_info.get("policy_profile_id", "default")

st.session_state["dataset_id"] = dataset_id
st.session_state["version_id"] = version_id
st.session_state["policy_profile_id"] = policy_profile_id

c1, c2, c3, c4 = st.columns(4)
c1.metric("dataset_id", dataset_id)
c2.metric("version_id", version_id)
c3.metric("policy_profile_id", policy_profile_id)
c4.metric("requirements", len(reqs))


def parse_vehicle_models_from_source(source: str) -> list[str]:
    """Infer vehicle model ids from meta.source.

    Expected patterns:
      - "CarB-SUV" -> ["CarB-SUV"]
      - "CarC-Truck" -> ["CarC-Truck"]
      - "CarA/B-EV" -> ["CarA-EV", "CarB-EV"]
      - "Common" -> []
    """
    if not source:
        return []
    s = source.strip()
    if s.lower() == "common":
        return []

    if "/" in s and "-" in s:
        left, suffix = s.split("-", 1)
        parts = [p.strip() for p in left.split("/") if p.strip()]
        return [f"{p}-{suffix}" for p in parts]

    if "/" in s and "-" not in s:
        return [p.strip() for p in s.split("/") if p.strip()]

    return [s]


# collect vehicle models (inferred) + ecus (from component)
vehicle_set = set()
ecu_set = set()

for r in reqs:
    meta = r.get("meta", {}) or {}
    source = (meta.get("source") or "").strip()

    # ECU/component can be stored under different keys depending on organization
    component = (
        (meta.get("component") or "").strip()
        or (meta.get("ecu_id") or "").strip()
        or (meta.get("ecu") or "").strip()
        or (meta.get("controller") or "").strip()
        or (meta.get("module") or "").strip()
        or (r.get("ecu_id") or "").strip()
    )
    if component:
        ecu_set.add(component)

    # Vehicle model can be encoded in source; if not, try explicit meta fields
    vms = parse_vehicle_models_from_source(source)
    if not vms:
        explicit_vm = (
            (meta.get("vehicle_model") or "").strip()
            or (meta.get("vehicle_model_id") or "").strip()
            or (meta.get("model") or "").strip()
            or (meta.get("platform") or "").strip()
        )
        if explicit_vm:
            vms = [explicit_vm]

    for vm in vms:
        if vm:
            vehicle_set.add(vm)

vehicle_models = sorted(vehicle_set)
ecus = sorted(ecu_set)

# Manual override UI to ensure catalogs are never empty
st.subheader("Catalog override (optional)")
st.caption("추정된 카탈로그가 비어있거나 부정확하면 아래에서 직접 보정하세요. (콤마 구분)")

vm_override = st.text_input(
    "Vehicle models (comma-separated)",
    value=",".join(vehicle_models) if vehicle_models else "ALL",
)
ecu_override = st.text_input(
    "ECUs (comma-separated)",
    value=",".join(ecus) if ecus else "UNKNOWN_ECU",
)

vehicle_models = [x.strip() for x in vm_override.split(",") if x.strip()]
ecus = [x.strip() for x in ecu_override.split(",") if x.strip()]

# Safety fallback: ensure non-empty catalogs
if not vehicle_models:
    vehicle_models = ["ALL"]
if not ecus:
    ecus = ["UNKNOWN_ECU"]

st.subheader("Inferred catalogs (from JSON)")
st.write(f"- inferred vehicle_models: {vehicle_models}")
st.write(f"- inferred ecus(components): {ecus}")
st.caption("주의: meta.source 기반 차종 추정입니다. Common은 모든 차종 공통으로 처리합니다.")

# --- Catalog preview for confirmation ---
with st.expander("Catalog preview", expanded=True):
    st.write({
        "vehicle_models_count": len(vehicle_models),
        "vehicle_models": vehicle_models,
        "ecus_count": len(ecus),
        "ecus": ecus,
        "sample_applicable_pairs": sorted(list(applicable_pairs))[:20] if 'applicable_pairs' in locals() else [],
    })

# ---------- 3) Build DB rows ----------
vehicle_model_rows = [{"vehicle_model_id": vm, "name": vm} for vm in vehicle_models]
ecu_rows = [{"ecu_id": e, "name": e, "domain": None} for e in ecus]

requirements_rows = []
scope_rows = []
ir_slot_rows_by_req = {}  # req_id -> list[slotdict]
applicable_pairs = set()  # (vehicle_model_id, ecu_id) observed

for r in reqs:
    req_id = r.get("req_id")
    if not req_id:
        continue

    meta = r.get("meta", {}) or {}
    source = (meta.get("source") or "").strip()
    component = (
        (meta.get("component") or "").strip()
        or (meta.get("ecu_id") or "").strip()
        or (meta.get("ecu") or "").strip()
        or (meta.get("controller") or "").strip()
        or (meta.get("module") or "").strip()
        or (r.get("ecu_id") or "").strip()
    )
    goal = meta.get("goal")

    # If ECU is missing, keep the requirement visible in heatmap by mapping to a placeholder ECU.
    if not component:
        component = "UNKNOWN_ECU"

    raw_text = r.get("raw_text", "")

    meta_json = {"source": source, "component": component, "goal": goal}

    requirements_rows.append(
        {
            "req_id": req_id,
            "raw_text": raw_text,
            "source": source,
            "domain": None,
            "meta": meta_json,
        }
    )

    vms = parse_vehicle_models_from_source(source)
    if (source or "").strip().lower() == "common" or not vms:
        # Apply to all known vehicle models if source is Common or cannot be parsed
        vms = vehicle_models[:]

    for vm in vms:
        if component:
            scope_rows.append({"req_id": req_id, "vehicle_model_id": vm, "ecu_id": component})
            applicable_pairs.add((vm, component))

    ir_record = r.get("ir_record", {}) or {}
    std_level = ir_record.get("standard_granularity_level")

    slots = []
    for s in ir_record.get("slots", []) or []:
        slots.append(
            {
                "slot_name": s.get("slot_name"),
                "value": s.get("value"),
                "status": s.get("status", "CONFIRMED"),
                "confidence": None,
                "anchors": None,
                "standard_granularity_level": std_level,
            }
        )

    for uf in ir_record.get("unknown_fields", []) or []:
        slots.append(
            {
                "slot_name": uf,
                "value": None,
                "status": "UNKNOWN",
                "confidence": None,
                "anchors": None,
                "standard_granularity_level": std_level,
            }
        )

    ir_slot_rows_by_req[req_id] = slots

# Build full vehicle×ECU applicability matrix so Overview can render NA vs applicable
applicability_rows = build_full_applicability(vehicle_models, ecus, applicable_pairs)

# ---------- 4) Import action ----------
st.divider()
st.subheader("Import into SQLite")

dry_run = st.checkbox("Dry-run (DB에 쓰지 않음)", value=False)

if st.button(
    "Save to DB (SQLite Commit)",
    type="primary",
    help="파싱/카탈로그 추정 결과를 SQLite(DB)에 실제로 저장합니다. Overview는 DB를 읽어 히트맵을 생성합니다.",
):
    try:
        if not dry_run:
            # Reset and write catalogs/applicability for this import
            reset_catalog_tables()

            if vehicle_model_rows:
                upsert_vehicle_models(vehicle_model_rows)
            if ecu_rows:
                upsert_ecus(ecu_rows)
            if applicability_rows:
                upsert_applicability(applicability_rows)

            # Write requirements + scope + IR slots
            upsert_requirements_raw(requirements_rows, dataset_id=dataset_id, version_id=version_id)
            if scope_rows:
                upsert_scope(scope_rows)

            for rid, slots in ir_slot_rows_by_req.items():
                upsert_ir_slots(rid, slots)

            # Persist identifiers in session_state for other pages
            st.session_state["dataset_id"] = dataset_id
            st.session_state["version_id"] = version_id
            st.session_state["import_completed"] = True
            st.session_state["db_path"] = os.path.abspath(DB_PATH)

        st.success("완료되었습니다." if not dry_run else "Dry-run 완료(쓰기 없음).")

        # Auto-navigate to Overview on successful commit
        if not dry_run:
            st.switch_page("pages/1_Overview.py")

        if not dry_run:
            conn = _conn()
            cur = conn.cursor()
            vm_cnt = cur.execute("SELECT COUNT(*) FROM vehicle_models").fetchone()[0]
            ecu_cnt = cur.execute("SELECT COUNT(*) FROM ecus").fetchone()[0]
            app_cnt = cur.execute("SELECT COUNT(*) FROM vehicle_ecu_applicability").fetchone()[0]
            raw_cnt = cur.execute("SELECT COUNT(*) FROM requirements_raw").fetchone()[0]
            scope_cnt = cur.execute("SELECT COUNT(*) FROM requirements_scope").fetchone()[0]
            slots_cnt = cur.execute("SELECT COUNT(*) FROM ir_slots").fetchone()[0]
            conn.close()

            st.caption("Import 완료 검증 (DB row counts)")
            st.write({
                "vehicle_models": vm_cnt,
                "ecus": ecu_cnt,
                "vehicle_ecu_applicability": app_cnt,
                "requirements_raw": raw_cnt,
                "requirements_scope": scope_cnt,
                "ir_slots": slots_cnt,
            })

        st.caption("다음: Overview에서 차종×ECU 히트맵을 그리거나 Explorer에서 (차종/ECU)로 필터링하세요.")

    except Exception as e:
        # 에러 메시지가 터미널에서 잘리는 경우가 많아서 UI에 강제로 풀 출력
        st.session_state["last_import_error"] = repr(e)
        st.error("SQLite 저장 중 오류가 발생했습니다. 아래 상세 오류를 확인하세요.")
        st.code(repr(e), language="text")
        st.exception(e)
        st.stop()