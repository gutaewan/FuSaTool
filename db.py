# db.py
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv("FUSA_DB_PATH", os.path.join(os.path.dirname(__file__), "fusa_tool.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS requirements_raw (
        req_id TEXT PRIMARY KEY,
        source TEXT,
        domain TEXT,
        component TEXT,
        goal TEXT,
        action_type TEXT,
        raw_text TEXT,
        meta_json TEXT,
        updated_at TEXT
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
        updated_at TEXT,
        PRIMARY KEY (req_id, slot_name)
    )
    """
    )

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS decisions_audit (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        req_id TEXT NOT NULL,
        slot_name TEXT NOT NULL,
        action TEXT NOT NULL,         -- e.g., SAVE_SLOT
        prev_json TEXT,
        next_json TEXT,
        rationale TEXT,
        actor TEXT,
        created_at TEXT
    )
    """
    )

    # Review queue용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_slots_status ON ir_slots(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_req ON decisions_audit(req_id)")

    conn.commit()
    conn.close()


def upsert_requirement(detail: Dict[str, Any]) -> None:
    req_id = detail["req_id"]
    meta = detail.get("meta", {}) or {}
    now = datetime.utcnow().isoformat()

    conn = _conn()
    conn.execute(
        """
        INSERT INTO requirements_raw (req_id, source, domain, component, goal, action_type, raw_text, meta_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(req_id) DO UPDATE SET
          source=excluded.source,
          domain=excluded.domain,
          component=excluded.component,
          goal=excluded.goal,
          action_type=excluded.action_type,
          raw_text=excluded.raw_text,
          meta_json=excluded.meta_json,
          updated_at=excluded.updated_at
    """,
        (
            req_id,
            meta.get("source"),
            meta.get("domain"),
            meta.get("component"),
            meta.get("goal"),
            meta.get("action_type"),
            detail.get("raw_text", ""),
            json.dumps(meta, ensure_ascii=False),
            now,
        ),
    )
    conn.commit()
    conn.close()


def upsert_ir_slots(req_id: str, slots: List[Dict[str, Any]]) -> None:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    for s in slots:
        slot_name = s.get("slot_name")
        value = s.get("value", None)
        status = s.get("status", "UNKNOWN")
        confidence = s.get("confidence", None)
        anchors = s.get("anchors", None)

        conn.execute(
            """
            INSERT INTO ir_slots (req_id, slot_name, value_json, status, confidence, anchors_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(req_id, slot_name) DO UPDATE SET
              value_json=excluded.value_json,
              status=excluded.status,
              confidence=excluded.confidence,
              anchors_json=excluded.anchors_json,
              updated_at=excluded.updated_at
        """,
            (
                req_id,
                str(slot_name),
                json.dumps(value, ensure_ascii=False),
                str(status),
                float(confidence) if isinstance(confidence, (int, float)) else None,
                json.dumps(anchors, ensure_ascii=False),
                now,
            ),
        )
    conn.commit()
    conn.close()


def get_requirement(req_id: str) -> Optional[Dict[str, Any]]:
    conn = _conn()
    row = conn.execute("SELECT * FROM requirements_raw WHERE req_id=?", (req_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["meta"] = json.loads(d["meta_json"]) if d.get("meta_json") else {}
    return d


def list_requirements(
    source: Optional[str] = None,
    component: Optional[str] = None,
    goal: Optional[str] = None,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    """Compatibility helper for pages that expect list_requirements().

    Returns rows from requirements_raw with optional filters.
    """
    conn = _conn()
    q = "SELECT * FROM requirements_raw WHERE 1=1"
    args: List[Any] = []

    if source:
        q += " AND source=?"
        args.append(source)
    if component:
        q += " AND component=?"
        args.append(component)
    if goal:
        q += " AND goal=?"
        args.append(goal)

    q += " ORDER BY req_id LIMIT ?"
    args.append(limit)

    rows = conn.execute(q, tuple(args)).fetchall()
    conn.close()

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d["meta_json"]) if d.get("meta_json") else {}
        out.append(d)
    return out


def list_versions() -> List[Dict[str, Any]]:
    """Compatibility helper.

    This tool currently stores a single SQLite DB without a versions table.
    Return a single synthetic version entry so pages importing list_versions won't crash.
    """
    return [
        {
            "version_id": "v_001",
            "label": "default",
            "note": "No versions table yet; single default version.",
        }
    ]


def list_slots(req_id: str) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT * FROM ir_slots WHERE req_id=? ORDER BY slot_name
    """,
        (req_id,),
    ).fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["value"] = json.loads(d["value_json"]) if d.get("value_json") else None
        d["anchors"] = json.loads(d["anchors_json"]) if d.get("anchors_json") else None
        out.append(d)
    return out


def get_slot(req_id: str, slot_name: str) -> Optional[Dict[str, Any]]:
    conn = _conn()
    r = conn.execute(
        """
        SELECT * FROM ir_slots WHERE req_id=? AND slot_name=?
    """,
        (req_id, slot_name),
    ).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    d["value"] = json.loads(d["value_json"]) if d.get("value_json") else None
    d["anchors"] = json.loads(d["anchors_json"]) if d.get("anchors_json") else None
    return d


def add_audit(req_id: str, slot_name: str, prev: Any, next_: Any, rationale: str, actor: str) -> None:
    now = datetime.utcnow().isoformat()
    conn = _conn()
    conn.execute(
        """
        INSERT INTO decisions_audit (req_id, slot_name, action, prev_json, next_json, rationale, actor, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            req_id,
            slot_name,
            "SAVE_SLOT",
            json.dumps(prev, ensure_ascii=False),
            json.dumps(next_, ensure_ascii=False),
            rationale,
            actor,
            now,
        ),
    )
    conn.commit()
    conn.close()


def list_audit(req_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT * FROM decisions_audit WHERE req_id=? ORDER BY audit_id DESC LIMIT ?
    """,
        (req_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def review_queue(limit: int = 200) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT r.req_id, r.component, r.goal, r.action_type,
               s.slot_name, s.status, s.confidence, s.updated_at
        FROM ir_slots s
        JOIN requirements_raw r ON r.req_id = s.req_id
        WHERE s.status != 'CONFIRMED'
        ORDER BY CASE s.status
                    WHEN 'CONFLICTED' THEN 0
                    WHEN 'PROPOSED' THEN 1
                    WHEN 'UNKNOWN' THEN 2
                    ELSE 9
                 END,
                 COALESCE(s.confidence, 0.0) ASC,
                 s.updated_at ASC
        LIMIT ?
    """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]