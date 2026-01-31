from __future__ import annotations
import json
import os
import uuid
from typing import Any, Dict, Optional

TMP_DIR = os.path.join(os.path.dirname(__file__), "tmp")

def ensure_tmp_dir() -> str:
    os.makedirs(TMP_DIR, exist_ok=True)
    return TMP_DIR

def get_or_create_session_id(session_state: Dict[str, Any]) -> str:
    sid = session_state.get("session_id")
    if not sid:
        sid = str(uuid.uuid4())
        session_state["session_id"] = sid
    return sid

def session_file_path(session_id: str) -> str:
    ensure_tmp_dir()
    return os.path.join(TMP_DIR, f"session_{session_id}.json")

def save_session_blob(session_state: Dict[str, Any], blob: Dict[str, Any]) -> None:
    sid = get_or_create_session_id(session_state)
    path = session_file_path(sid)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False, indent=2)

def load_session_blob(session_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sid = get_or_create_session_id(session_state)
    path = session_file_path(sid)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None