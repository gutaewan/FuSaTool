import json
import re
import yaml
import glob
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

# =========================================================
# 0. Configuration
# =========================================================

DEFAULT_MRS_CONFIG = """
mrs_schema:
  mrs_only_types:
    type_order: [T6_VerificationCentric, T5_ConstraintCentric, T4_WhenCentric, T3_HowTypeCentric, T2_WhatCentric, T1_WhyCentric]
    types:
      T1_WhyCentric: { match: { all: [{slot: Why, state_in: [OK]}] } }
      T2_WhatCentric: { match: { all: [{slot: What, state_in: [OK]}, {slot: Anchor, state_in: [OK]}] } }
      T3_HowTypeCentric: { match: { all: [{slot: HowType, state_in: [OK]}] } }
      T4_WhenCentric: { match: { all: [{slot: When, state_in: [OK]}] } }
      T5_ConstraintCentric: { match: { all: [{slot: Constraints, state_in: [OK]}] } }
      T6_VerificationCentric: { match: { all: [{slot: Verification, state_in: [OK]}, {slot: AcceptanceCriteria, state_in: [OK]}] } }
"""

ANCHOR_KEYWORDS = r"(ecu|controller|sensor|actuator|module|component|system|can|signal|message|data|bus|interface|" \
                  r"bms|vcu|mcu|inverter|motor|engine|battery|cell|pack|relay|hvil|lidar|radar|camera|ultrasonic|esp|abs|tcs|mdps|epb|" \
                  r"제어기|센서|모듈|시스템|신호|패킷|장치|배터리|인버터|모터|엔진|카메라|레이더|라이더|조향|제동|구동)"

PATTERNS = {
    "Why": r"(to prevent|in order to|ensure|guarantee|purpose|goal|목적|위해|보장|방지|hazard|risk|우려|위험)",
    "Anchor": ANCHOR_KEYWORDS,
    "What": r"(shall|must|should|will|request|command|perform|provide|maintain|limit|open|close|stop|start|" \
            r"해야 한다|한다|수행한다|전송한다|제공한다|유지해야 한다|제한한다|개방해야 한다|차단해야 한다|금지한다|멈춰야 한다)",
    "HowType": r"(detect|mitigate|transition|limit|warn|redundancy|monitor|fallback|diagnose|inhibit|ignore|override|" \
               r"감지|완화|전환|제한|경고|이중화|대체|무시|억제|진입|해제|금지)",
    "When": r"(when|if|upon|during|in case of|while|after|before|whenever|condition|" \
            r"조건|~시|~경우|~동안|발생 시|도달 시|수신 시|상태에서|직후|이전)",
    "Constraints": r"(\d+|within|at least|no more than|less than|greater than|ftti|latency|period|frequency|range|min|max|" \
                   r"이내|이상|미만|초과|주기적으로|최소|최대|범위)",
    "Verification": r"(test|verify|validate|analysis|inspection|review|check|demonstration|" \
                    r"시험|분석|검토|검사|실증|확인)",
    "AcceptanceCriteria": r"(pass|fail|acceptance|criteria|threshold|deemed|tolerance|margin|" \
                          r"합격|불합격|기준|판정|허용|오차)",
    
    "Strong_Constraints": r"(\d+(\.\d+)?)\s*(ms|s|sec|msec|hz|v|a|ma|nm|kw|kph|mph|%|deg|c|bar)|(tbd)",
    "Strong_When": r"(if|when|upon|during|in case of)\s+.*(,|\bthen\b)|(\w+)\s*(시|경우|동안)\b",
    "Strong_Verification": r"(test|analysis|inspection|review)\s+(method|report|result)|(시험|분석|검토)\s*(보고서|결과|방법)",
    "Strong_AcceptanceCriteria": r"(pass|fail)\s+(criteria|condition)|(기준|조건).*(만족|초과|미만|이하|이상)",
    "Strong_Anchor": ANCHOR_KEYWORDS
}

class SlotState(str, Enum):
    OK = "OK"
    WEAK = "WEAK"
    ABSENT = "ABSENT"

@dataclass
class ParseResult:
    id: str
    mrs_type: str
    type_rationale: str # [추가] 결정 이유
    slots: Dict[str, SlotState]

# =========================================================
# 1. Helper Logic (Rationale Logic Added)
# =========================================================
def determine_mrs_type(slots: Dict[str, SlotState], config: dict) -> Tuple[str, str]:
    """
    Returns: (Type Name, Rationale String)
    """
    type_defs = config['mrs_schema']['mrs_only_types']
    
    for t_name in type_defs['type_order']:
        criteria = type_defs['types'][t_name]['match']
        match = True
        reasons = []
        
        # Check 'all' conditions
        for cond in criteria.get('all', []):
            slot_name = cond['slot']
            current_state = slots.get(slot_name, SlotState.ABSENT)
            
            if current_state.name not in cond['state_in']:
                match = False
                break
            else:
                # 이유 기록 (예: Constraints=OK)
                reasons.append(f"{slot_name}={current_state.name}")
        
        if match:
            rationale = ", ".join(reasons)
            return t_name, rationale

    return "Unknown", "No matching criteria found"

# =========================================================
# 2. Advanced Rule-Based Parser
# =========================================================
class AdvancedRuleParser:
    def __init__(self, config):
        self.config = config

    def _normalize(self, text: str) -> str:
        if not text: return ""
        text = text.lower().replace('\n', ' ').strip()
        text = re.sub(r'\b(msec|milliseconds)\b', 'ms', text)
        text = re.sub(r'\b(sec|seconds)\b', 's', text)
        return text

    def parse(self, item: dict) -> ParseResult:
        text = self._normalize(item.get('raw_text', ''))
        req_id = item.get('req_id', item.get('id', 'N/A'))
        
        slots = {}
        # Stage 1: Lexical
        for slot in ["Why", "Anchor", "What", "HowType", "When", "Constraints", "Verification", "AcceptanceCriteria"]:
            pat = PATTERNS.get(slot)
            if pat and re.search(pat, text):
                slots[slot] = SlotState.WEAK
            else:
                slots[slot] = SlotState.ABSENT

        # Stage 2: Structural
        for slot in ["Constraints", "When", "Verification", "AcceptanceCriteria"]:
            strong_key = f"Strong_{slot}"
            if slots[slot] == SlotState.WEAK:
                if strong_key in PATTERNS and re.search(PATTERNS[strong_key], text):
                    slots[slot] = SlotState.OK
        
        if slots["Anchor"] == SlotState.WEAK: slots["Anchor"] = SlotState.OK
        if slots["What"] == SlotState.WEAK: slots["What"] = SlotState.OK

        # Stage 3: Relation Correction
        if slots["Anchor"] == SlotState.ABSENT:
            if slots["When"] == SlotState.OK: slots["When"] = SlotState.WEAK
            if slots["Constraints"] == SlotState.OK: slots["Constraints"] = SlotState.WEAK

        if slots["What"] == SlotState.ABSENT:
            if slots["HowType"] == SlotState.OK: slots["HowType"] = SlotState.WEAK

        # [변경] Rationale 함께 수신
        mrs_type, rationale = determine_mrs_type(slots, self.config)
        return ParseResult(req_id, mrs_type, rationale, slots)

# =========================================================
# 3. Reference Parser
# =========================================================
class ReferenceParser:
    def __init__(self, config):
        self.config = config

    def parse(self, item: dict) -> ParseResult:
        req_id = item.get('req_id', item.get('id', 'N/A'))
        ir_slots = item.get('ir_record', {}).get('slots', [])
        
        slots = {}
        for key in ["Why", "Anchor", "What", "HowType", "When", "Constraints", "Verification", "AcceptanceCriteria"]:
            slots[key] = SlotState.ABSENT

        for s_item in ir_slots:
            name = s_item['slot_name']
            status = s_item.get('status', 'MISSING')
            if name == "Anchors": name = "Anchor"
            
            if name in slots:
                if status == "CONFIRMED": slots[name] = SlotState.OK
                elif status == "INCONSISTENT": slots[name] = SlotState.WEAK
                else: slots[name] = SlotState.ABSENT

        # [변경] Rationale 함께 수신
        mrs_type, rationale = determine_mrs_type(slots, self.config)
        return ParseResult(req_id, mrs_type, rationale, slots)

# =========================================================
# 4. Reporting
# =========================================================
def format_slots_line(slots: Dict[str, SlotState]) -> str:
    active = []
    for k, v in slots.items():
        if v == SlotState.OK: active.append(f"{k}")
        elif v == SlotState.WEAK: active.append(f"~{k}") # WEAK는 물결표시 등 약어 처리
    return ", ".join(active) if active else "(None)"

def run_explainable_comparison():
    config = yaml.safe_load(DEFAULT_MRS_CONFIG)
    rule_parser = AdvancedRuleParser(config)
    ref_parser = ReferenceParser(config)

    data_dir = './data/'
    items = []
    target_files = glob.glob(os.path.join(data_dir, "*.json"))
    if not target_files and os.path.exists("FuSaReq_new_augmented.json"):
        target_files = ["FuSaReq_new_augmented.json"]

    for jf in target_files:
        with open(jf, 'r', encoding='utf-8') as f:
            content = json.load(f)
            if isinstance(content, dict) and 'requirements' in content:
                items.extend(content['requirements'])
            elif isinstance(content, list):
                items.extend(content)

    print(f"\n🚀 [MRS Explainable Comparison]")
    print(f"   Target Files: {len(target_files)} | Total Requirements: {len(items)}")
    
    stats = {"match": 0, "mismatch": 0}

    for idx, item in enumerate(items, 1):
        r_res = rule_parser.parse(item)
        l_res = ref_parser.parse(item)
        
        print("\n" + "="*80)
        print(f"🔸 [{item.get('req_id', 'N/A')}]")
        print(f"   \"{item.get('raw_text', '').strip()}\"")
        print("-" * 80)
        
        # Rule Result with Rationale
        print(f"   🤖 [Rule] {r_res.mrs_type:<20} (Reason: {r_res.type_rationale})")
        print(f"            Slots: {format_slots_line(r_res.slots)}")
        
        # Ground Truth Result with Rationale
        print(f"   🧠 [Ref ] {l_res.mrs_type:<20} (Reason: {l_res.type_rationale})")
        print(f"            Slots: {format_slots_line(l_res.slots)}")
        
        print("-" * 80)
        
        if r_res.mrs_type == l_res.mrs_type:
            print(f"   ✅ MATCH")
            stats['match'] += 1
        else:
            print(f"   ❌ MISMATCH")
            stats['mismatch'] += 1
            
            # Why mismatch?
            # 타입이 다른 이유는 주로 "슬롯 상태 판단"이 달라서임
            # 결정적인 차이(Rationale에 포함된 슬롯들)를 비교
            print(f"      🔎 Diagnosis:")
            check_slots = ["Verification", "AcceptanceCriteria", "Constraints", "When", "HowType", "What", "Anchor"]
            
            for k in check_slots:
                if r_res.slots[k] != l_res.slots[k]:
                    print(f"         - {k}: Rule={r_res.slots[k].name} vs Ref={l_res.slots[k].name}")

    print("\n" + "="*80)
    print(f"📈 Accuracy: {(stats['match']/len(items)*100):.1f}% ({stats['match']}/{len(items)})")
    print("="*80)

if __name__ == "__main__":
    run_explainable_comparison()