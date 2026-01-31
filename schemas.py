from dataclasses import dataclass
from typing import List, Optional, Union, Dict, Literal

IRSlotName = Literal[
    "intent",
    "goal",
    "action_statement",
    "action_type",
    "trigger_condition",
    "constraints",
    "verification_method",
    "acceptance_criteria",
    "anchors",
    "testability",
    "assumption",
]

SlotStatus = Literal["CONFIRMED", "UNKNOWN", "PROPOSED", "CONFLICTED"]

@dataclass
class Anchor:
    doc_id: str = "DOC-1"
    page: int = 0
    line: int = 0
    span_start: int = 0
    span_end: int = 0
    quote: str = ""

@dataclass
class IRSlot:
    slot_name: IRSlotName
    value: Optional[Union[str, List[str]]] = None
    status: SlotStatus = "UNKNOWN"
    confidence: float = 0.0
    anchors: Optional[List[Anchor]] = None