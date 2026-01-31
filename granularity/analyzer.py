from __future__ import annotations
import re
from typing import Dict, Any, List, Tuple
from .schema import LEVEL_PROFILES_L1_L5, LEVEL_PROFILES_L1_L3

UNIT_PAT = re.compile(r"\b\d+(?:\.\d+)?\s*(ms|s|sec|초|분|km/h|kph|%|V|A|Hz|Nm|℃|도)\b", re.IGNORECASE)

def extract_slots_from_req(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    입력 JSON에 이미 ir_record.slots가 있다면 그대로 사용.
    없다면 최소 필드(meta.goal, safety_intent 등) 기반으로 빈 슬롯 생성.
    Anchors는 반드시 있어야 하므로, 원문 전체를 기본 anchor로 둘 수도 있음(MVP).
    """
    meta = req.get("meta", {}) or {}
    ir = req.get("ir_record", {}) or {}
    slots_list = ir.get("slots", []) or []

    slots = {s.get("slot_name"): s for s in slots_list if isinstance(s, dict) and s.get("slot_name")}
    raw = req.get("raw_text", "") or ""

    def _val(name: str) -> str:
        s = slots.get(name, {}) or {}
        v = s.get("value")
        return "" if v is None else str(v)

    # canonical mapping (현재는 “입력 구조에 맞춰” 점진적으로 확장)
    out = {
        "Goal": str(meta.get("goal") or _val("goal") or ""),
        "Why": str(_val("intent") or _val("safety_intent") or ""),
        "What": str(_val("action_statement") or ""),
        "HowType": str(_val("action_type") or ""),
        "When": str(_val("trigger_condition") or _val("trigger") or _val("condition") or ""),
        "Constraints": str(_val("constraints") or ""),
        "Verification": str(_val("verification_method") or _val("verification") or ""),
        "AcceptanceCriteria": str(_val("acceptance_criteria") or ""),
        # Anchors: 입력에 anchors가 없으면 MVP로 raw_text 전체 anchor 1개를 부여(나중에 강화)
        "Anchors": slots.get("anchors", {}).get("anchors") if "anchors" in slots else None,
        "raw_text": raw,
    }

    if not out["Anchors"]:
        out["Anchors"] = [{"quote": raw[:2000], "note": "MVP fallback anchor (raw_text excerpt)"}] if raw else []

    return out

def compute_missing_excess(
    slots: Dict[str, Any],
    target_level: str,
    profile_mode: str = "L1_L5",
) -> Tuple[List[str], List[str], List[str]]:
    """
    return: (missing_slots, weak_anchor_slots, excess_slots)
    - missing: required but empty
    - weak_anchor: has value but anchors empty
    - excess: beyond target level but filled
    """
    prof = LEVEL_PROFILES_L1_L5 if profile_mode == "L1_L5" else LEVEL_PROFILES_L1_L3
    required = prof[target_level]

    missing, weak = [], []
    anchors = slots.get("Anchors") or []
    for k in required:
        if k == "Anchors":
            if len(anchors) == 0:
                missing.append("Anchors")
            continue
        v = (slots.get(k) or "").strip()
        if not v:
            missing.append(k)

    # weak anchors: anchors 존재 여부는 필수, 추가로 “값 있는데 anchor 빈 경우”를 잡고 싶다면
    # slot별 anchor 구조를 나중에 확장. MVP에서는 Anchors만 체크.
    if (slots.get("Anchors") is None) or len(anchors) == 0:
        weak.append("Anchors")

    # excess (간단 규칙)
    excess = []
    for k in ["Constraints", "Verification", "AcceptanceCriteria"]:
        if k not in required and (slots.get(k) or "").strip():
            excess.append(k)

    # L1에서는 수치/단위가 있으면 excess 힌트로 추가
    if target_level == "L1" and UNIT_PAT.search(slots.get("raw_text", "") or ""):
        if "Constraints" not in excess:
            excess.append("Constraints")

    return missing, weak, excess

def infer_dataset_level_distribution(reqs: List[Dict[str, Any]], profile_mode: str = "L1_L5") -> Dict[str, float]:
    """
    데이터셋 전체 요구사항의 “충족 슬롯 수”를 기반으로 레벨 분포를 대략 추정(기준 수립용).
    """
    prof = LEVEL_PROFILES_L1_L5 if profile_mode == "L1_L5" else LEVEL_PROFILES_L1_L3
    levels = list(prof.keys())
    counts = {lv: 0 for lv in levels}

    for r in reqs:
        slots = extract_slots_from_req(r)
        # 레벨별로 required 중 채워진 수가 가장 높은 레벨을 잡는 단순 휴리스틱
        best_lv, best_score = levels[0], -1
        for lv in levels:
            required = [x for x in prof[lv] if x != "Anchors"]
            score = sum(1 for k in required if (slots.get(k) or "").strip())
            if score > best_score:
                best_lv, best_score = lv, score
        counts[best_lv] += 1

    total = max(1, len(reqs))
    return {lv: counts[lv] / total for lv in levels}