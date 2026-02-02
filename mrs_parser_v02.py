import json
import re
import yaml
import glob
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any

# =========================================================
# 0. Embedded Configuration (기본 설정)
# =========================================================

DEFAULT_MRS_CONFIG = """
mrs_schema:
  version: "1.0"
  mrs_only_types:
    type_order:
      - T6_VerificationCentric
      - T5_ConstraintCentric
      - T4_WhenCentric
      - T3_HowTypeCentric
      - T2_WhatCentric
      - T1_WhyCentric

    types:
      T1_WhyCentric:
        match:
          all: [{slot: Why, state_in: [OK]}]
      T2_WhatCentric:
        match:
          all: [{slot: What, state_in: [OK]}, {slot: Anchor, state_in: [OK]}]
      T3_HowTypeCentric:
        match:
          all: [{slot: HowType, state_in: [OK]}]
      T4_WhenCentric:
        match:
          all: [{slot: When, state_in: [OK]}]
      T5_ConstraintCentric:
        match:
          all: [{slot: Constraints, state_in: [OK]}]
      T6_VerificationCentric:
        match:
          all: [{slot: Verification, state_in: [OK]}, {slot: AcceptanceCriteria, state_in: [OK]}]

  type_slot_expectations:
    matrix:
      T1_WhyCentric:
        Why: M
        Anchor: R
        What: R
        HowType: O
        When: O
        Constraints: O
        Verification: O
        AcceptanceCriteria: O
      T2_WhatCentric:
        Why: R
        Anchor: M
        What: M
        HowType: R
        When: M
        Constraints: R
        Verification: R
        AcceptanceCriteria: O
      T3_HowTypeCentric:
        Why: R
        Anchor: M
        What: M
        HowType: M
        When: M
        Constraints: R
        Verification: R
        AcceptanceCriteria: O
      T4_WhenCentric:
        Why: R
        Anchor: M
        What: M
        HowType: R
        When: M
        Constraints: R
        Verification: R
        AcceptanceCriteria: O
      T5_ConstraintCentric:
        Why: R
        Anchor: M
        What: M
        HowType: R
        When: R
        Constraints: M
        Verification: R
        AcceptanceCriteria: O
      T6_VerificationCentric:
        Why: R
        Anchor: M
        What: M
        HowType: O
        When: R
        Constraints: R
        Verification: M
        AcceptanceCriteria: M
"""

# =========================================================
# 1. Constants & Patterns
# =========================================================

PATTERNS = {
    "Why": r"(to prevent|in order to|ensure|guarantee|목적|위해|보장|방지|hazard|risk|우려)",
    "Anchor": r"(ecu|controller|sensor|actuator|module|component|system|can|signal|message|data|제어기|센서|모듈|시스템|신호|패킷|bms|vcu|mcu|inverter|radar|lidar|camera|esp|abs)",
    "What": r"(shall|must|should|will|해야 한다|한다|수행한다|전송한다|제공한다|유지해야 한다|제한한다|개방해야 한다|차단해야 한다)",
    "HowType": r"(detect|mitigate|transition|limit|warn|redundancy|monitor|fallback|diagnose|감지|완화|전환|제한|경고|이중화|대체|무시|억제)",
    "When": r"(when|if|upon|during|in case of|while|after|before|조건|~시|~경우|~동안|발생 시|도달 시|수신 시|상태에서)",
    "Constraints": r"(\d+(\.\d+)?\s*(ms|s|sec|msec|hz|v|a|m|nm|kph|%)|within|at least|no more than|ftti|latency|period|이내|이상|미만|초과|주기적으로)",
    "Verification": r"(test|verify|validate|analysis|inspection|review|시험|분석|검토|검사|실증)",
    "AcceptanceCriteria": r"(pass|fail|acceptance|criteria|threshold|deemed|합격|불합격|기준|판정|허용)",
    
    # Strong patterns for OK state
    "Strong_Constraints": r"(\d+(\.\d+)?)\s*(ms|s|sec|msec|hz|v|a|nm|kph)|(tbd)",
    "Strong_When": r"(if|when|upon|during|in case of).*(,|then)|(\w+)\s*(시|경우|동안)\b",
    "Strong_Verification": r"(test|analysis|inspection|review).*(shall|must)|(시험|분석|검토).*(통해|으로)",
    "Strong_AC": r"(pass|fail|threshold).*(<|>|=|be)|기준.*(만족|초과|미만)"
}

# =========================================================
# 2. Data Structures
# =========================================================

class SlotState(str, Enum):
    OK = "OK"
    WEAK = "WEAK"
    VAGUE = "VAGUE"
    ABSENT = "ABSENT"

class MissingLabel(str, Enum):
    ACTIONABLE = "ActionableMissing"
    PERMISSIBLE = "PermissibleMissing"
    DEFERRED = "DeferredMissing"
    NONE = "None"

@dataclass
class SlotData:
    state: SlotState = SlotState.ABSENT
    candidates: List[str] = field(default_factory=list)
    spans: List[tuple] = field(default_factory=list)

@dataclass
class ParsedRequirement:
    id: str
    raw_text: str
    normalized_text: str
    mrs_type: str = "Unknown"
    slots: Dict[str, SlotData] = field(default_factory=dict)
    missing_items: List[Dict[str, Any]] = field(default_factory=list)
    # Meta fields
    vehicle: str = ""
    controller: str = ""
    safety_goal: str = ""
    safe_state: str = ""
    ftti: str = ""

# =========================================================
# 3. Parser Logic
# =========================================================

class MRSParser:
    def __init__(self, yaml_content: str = None):
        if not yaml_content:
            yaml_content = DEFAULT_MRS_CONFIG
        
        try:
            self.rules = yaml.safe_load(yaml_content)
            schema = self.rules['mrs_schema']
            self.type_defs = schema['mrs_only_types']
            self.expectations = schema['type_slot_expectations']['matrix']
        except Exception as e:
            print(f"⚠️  Config Error ({e}). Using embedded defaults.")
            self.rules = yaml.safe_load(DEFAULT_MRS_CONFIG)
            self.type_defs = self.rules['mrs_schema']['mrs_only_types']
            self.expectations = self.rules['mrs_schema']['type_slot_expectations']['matrix']

    def _normalize(self, text: str) -> str:
        if not text: return ""
        text = text.lower()
        text = re.sub(r'\b(msec|milliseconds)\b', 'ms', text)
        text = re.sub(r'\b(sec|seconds)\b', 's', text)
        return text.replace('\n', ' ').strip()

    def _determine_slot_state(self, slot_name: str, text: str) -> SlotData:
        keyword_pat = PATTERNS.get(slot_name)
        if not keyword_pat: return SlotData()

        matches = list(re.finditer(keyword_pat, text))
        if not matches: return SlotData(state=SlotState.ABSENT)

        candidates = [m.group() for m in matches]
        spans = [m.span() for m in matches]
        state = SlotState.WEAK

        strong_key = f"Strong_{slot_name}"
        if strong_key in PATTERNS and re.search(PATTERNS[strong_key], text):
            state = SlotState.OK
        elif slot_name not in ["Constraints", "When", "Verification", "AcceptanceCriteria"]:
            state = SlotState.OK

        return SlotData(state=state, candidates=candidates, spans=spans)

    def _determine_mrs_type(self, slots: Dict[str, SlotData]) -> str:
        type_order = self.type_defs['type_order']
        for t_name in type_order:
            criteria = self.type_defs['types'][t_name]['match']
            match = True
            if 'all' in criteria:
                for cond in criteria['all']:
                    if slots[cond['slot']].state.name not in cond['state_in']:
                        match = False; break
            if match: return t_name
        return "Unknown"

    def _apply_missingness_rules(self, req: ParsedRequirement):
        if req.mrs_type not in self.expectations: return
        exp_map = self.expectations[req.mrs_type]
        missing_report = []

        for slot, expectation in exp_map.items():
            if req.slots[slot].state == SlotState.ABSENT:
                item = {"slot": slot, "label": MissingLabel.NONE, "rationale": ""}
                if expectation == 'M':
                    item["label"] = MissingLabel.ACTIONABLE
                    item["rationale"] = f"[Required] {slot} is mandatory for {req.mrs_type}."
                elif expectation == 'R':
                    item["label"] = MissingLabel.DEFERRED
                    item["rationale"] = f"[Recommended] {slot} is missing."
                elif expectation == 'O':
                    item["label"] = MissingLabel.PERMISSIBLE
                    item["rationale"] = f"[Optional] {slot} is missing."
                missing_report.append(item)

        # Rule overrides (Anchor, Permissible check)
        if req.slots['Anchor'].state != SlotState.OK:
            for item in missing_report:
                if item['slot'] in ['When', 'Constraints', 'Verification']:
                    item['label'] = MissingLabel.DEFERRED
                    item['rationale'] += " (Deferred: Weak Anchor)"
        
        if req.slots['Verification'].state == SlotState.ABSENT:
            if req.slots['When'].state == SlotState.OK and req.slots['Constraints'].state == SlotState.OK:
                 for item in missing_report:
                    if item['slot'] == 'Verification':
                        item['label'] = MissingLabel.PERMISSIBLE
                        item['rationale'] = "Permissible: Test logic implied via When+Constraints."

        req.missing_items = missing_report

    def parse(self, json_data: dict) -> ParsedRequirement:
        # [수정됨] JSON 구조에 맞게 데이터 추출 로직 변경
        
        # 1. Raw Text 추출
        raw_text = json_data.get('raw_text', '')
        if not raw_text and 'ir_record' in json_data: # 혹시 raw_text가 없고 ir_record만 있는 경우 대비
             # anchors의 첫번째 quote를 raw_text 대용으로 쓸 수도 있음 (fallback)
             pass
        
        norm_text = self._normalize(raw_text)

        # 2. 메타데이터(Meta) 추출
        # 제공된 JSON은 'meta' 키 아래에 상세 정보가 있음
        meta = json_data.get('meta', {})
        safety = json_data.get('safety', {}) # safety 키도 참고

        # Vehicle (List -> String)
        vehicle_list = meta.get('vehicle_models', [])
        if isinstance(vehicle_list, list):
            vehicle_str = ", ".join(vehicle_list)
        else:
            vehicle_str = str(vehicle_list)

        # Controller (Component or ECU)
        controller_str = meta.get('component') or meta.get('ecu') or json_data.get('controller', '')

        # Safety Attributes
        # meta에 있으면 meta 우선, 없으면 safety 딕셔너리 확인
        sg_str = meta.get('SafetyGoal') or meta.get('goal') or safety.get('SafetyGoal', '')
        ss_str = meta.get('SafeState') or safety.get('SafeState', {}).get('description', '')
        ftti_str = meta.get('FTTI') or safety.get('FTTI', '')

        req = ParsedRequirement(
            id=json_data.get('req_id', json_data.get('id', 'N/A')),
            raw_text=raw_text,
            normalized_text=norm_text,
            vehicle=vehicle_str,
            controller=controller_str,
            safety_goal=sg_str,
            safe_state=ss_str,
            ftti=ftti_str
        )

        # 3. 슬롯 및 타입 분석
        for slot in PATTERNS.keys():
            if slot.startswith("Strong_"): continue
            req.slots[slot] = self._determine_slot_state(slot, norm_text)

        req.mrs_type = self._determine_mrs_type(req.slots)
        self._apply_missingness_rules(req)
        
        return req

# =========================================================
# 4. Main Execution
# =========================================================

def run_parser():
    # 1. 설정 로드
    parser = MRSParser() # Default YAML 사용

    # 2. JSON 데이터 로드
    data_dir = './data/'
    items_to_process = []
    
    # glob으로 json 파일 찾기
    json_files = glob.glob(os.path.join(data_dir, "*.json"))
    
    if json_files:
        print(f"📂 Parsing files in {data_dir}...")
        for jf in json_files:
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # [수정됨] JSON Root가 리스트인지, dict 내 'requirements' 리스트인지 확인
                    if isinstance(data, list):
                        items_to_process.extend(data)
                    elif isinstance(data, dict):
                        if 'requirements' in data:
                            items_to_process.extend(data['requirements'])
                        else:
                            # 단일 객체 혹은 다른 포맷
                            items_to_process.append(data)
            except Exception as e:
                print(f"⚠️ Error reading {jf}: {e}")
    else:
        print("⚠️ No JSON files found. Please check ./data/ folder.")
        return

    # 3. 결과 출력
    print(f"🔍 Total Requirements Found: {len(items_to_process)}")
    print("\n" + "="*80)
    print(f"{'ID':<12} | {'Type':<20} | {'Controller':<10} | {'Missing Logic'}")
    print("="*80)

    for item in items_to_process:
        res = parser.parse(item)
        
        # 결손 정보 요약
        missing_summary = ""
        if res.missing_items:
            # Actionable한 것만 우선 표시
            act_miss = [m['slot'] for m in res.missing_items if m['label'] == MissingLabel.ACTIONABLE]
            if act_miss:
                missing_summary = f"🔴 Missing: {', '.join(act_miss)}"
            else:
                missing_summary = f"🟡 Deferred/Permissible items"
        else:
            missing_summary = "✅ OK"

        print(f"{res.id:<12} | {res.mrs_type:<20} | {res.controller:<10} | {missing_summary}")
        
        # 상세 내용 (옵션: 필요시 주석 해제)
        # print(f"  [Text] {res.raw_text[:60]}...")
        # print(f"  [Meta] Model: {res.vehicle} / SG: {res.safety_goal} / FTTI: {res.ftti}")
        # print(f"  [Slots] " + ", ".join([f"{k}={v.state.name}" for k,v in res.slots.items() if v.state != SlotState.ABSENT]))
        # print("-" * 80)

if __name__ == "__main__":
    run_parser()