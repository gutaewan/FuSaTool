from __future__ import annotations

CANONICAL_SLOTS = [
    "Goal",
    "Why",
    "What",
    "HowType",
    "When",
    "Constraints",
    "Verification",
    "AcceptanceCriteria",
    "Anchors",
]

# 레벨별 “필수 슬롯” (dataset 상대 기준)
LEVEL_PROFILES_L1_L5 = {
    "L1": ["Goal", "Why", "What", "Anchors"],
    "L2": ["Goal", "Why", "What", "HowType", "When", "Anchors"],
    "L3": ["Goal", "Why", "What", "HowType", "When", "Constraints", "Verification", "Anchors"],
    "L4": ["Goal", "Why", "What", "HowType", "When", "Constraints", "Verification", "Anchors"],
    "L5": ["Goal", "Why", "What", "HowType", "When", "Constraints", "Verification", "AcceptanceCriteria", "Anchors"],
}

LEVEL_PROFILES_L1_L3 = {
    "L1": LEVEL_PROFILES_L1_L5["L1"],
    "L2": LEVEL_PROFILES_L1_L5["L2"],
    "L3": LEVEL_PROFILES_L1_L5["L3"],
}