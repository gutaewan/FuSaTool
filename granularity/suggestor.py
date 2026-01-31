from __future__ import annotations
from typing import Dict, Any, List

def suggest_missing_with_llm(
    raw_text: str,
    current_slots: Dict[str, Any],
    missing_slots: List[str],
    target_level: str,
) -> Dict[str, str]:
    """
    여기를 나중에 OpenAI API / 로컬 LLM으로 교체.
    지금은 placeholder로 최소 제안을 반환.
    """
    out: Dict[str, str] = {}
    for s in missing_slots:
        if s == "Why":
            out[s] = "(PROPOSED) 안전 의도(Why) 문장을 추가하세요."
        elif s == "What":
            out[s] = "(PROPOSED) 시스템이 수행해야 할 행동(What)을 명시하세요."
        elif s == "HowType":
            out[s] = "(PROPOSED) detect/mitigate/transition/limit/warn/redundancy 중 선택하세요."
        elif s == "When":
            out[s] = "(PROPOSED) 발동 조건/트리거(When)를 명시하세요."
        elif s == "Constraints":
            out[s] = "(PROPOSED) FTTI/타이밍/성능/모드 제약을 명시하세요."
        elif s == "Verification":
            out[s] = "(PROPOSED) 시험/분석/리뷰 등 검증 방법을 명시하세요."
        elif s == "AcceptanceCriteria":
            out[s] = "(PROPOSED) pass/fail 기준을 명시하세요."
        elif s == "Goal":
            out[s] = "(PROPOSED) Safety Goal 또는 Goal 참조를 명시하세요."
        elif s == "Anchors":
            out[s] = "(PROPOSED) 원문 근거(Anchors)를 연결하세요."
    return out