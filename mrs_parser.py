import json
import re
import yaml
import glob
import os
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Union

# =========================================================
# 1. Configuration & Constants (Data-Driven)
# =========================================================

# 정규식 패턴 사전 (Lexical Cues & Patterns)
PATTERNS = {
    # [Slot Detection Keywords]
    "Why": r"(to prevent|in order to|ensure|guarantee|목적|위해|보장|방지|hazard|risk)",
    "Anchor": r"(ecu|controller|sensor|actuator|module|component|system|can|signal|message|data|제어기|센서|모듈|시스템|신호)",
    "What": r"(shall|must|should|will|해야 한다|한다|수행한다|전송한다|제공한다)",
    "HowType": r"(detect|mitigate|transition|limit|warn|redundancy|monitor|fallback|diagnose|감지|완화|전환|제한|경고|이중화)",
    "When": r"(when|if|upon|during|in case of|while|after|before|조건|~시|~경우|~동안|발생 시)",
    "Constraints": r"(\d+(\.\d+)?\s*(ms|s|sec|msec|hz|v|a|m)|within|at least|no more than|ftti|latency|period|이내|이상|미만|초과)",
    "Verification": r"(test|verify|validate|analysis|inspection|review|시험|분석|검토|검사|실증)",
    "AcceptanceCriteria": r"(pass|fail|acceptance|criteria|threshold|deemed|합격|불합격|기준|판정|허용)",

    # [Strong Structure Patterns for OK State]
    # 단순히 키워드가 있는 것을 넘어, 구체적인 수치나 구조가 있는지 확인
    "Strong_Constraints": r"(\d+(\.\d+)?)\s*(ms|s|sec|msec|hz|v|a)|(tbd)",
    "Strong_When": r"(if|when|upon|during|in case of).*(,|then)|(\w+)\s*시\b",
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
    spans: List[tuple] = field(default_factory=list) # (start, end)

@dataclass
class ParsedRequirement:
    id: str
    raw_text: str
    normalized_text: str
    vehicle: str = ""
    controller: str = ""
    safety_goal: str = ""
    safe_state: str = ""
    ftti: str = ""
    
    # Analysis Results
    slots: Dict[str, SlotData] = field(default_factory=dict)
    mrs_type: str = "Unknown"
    missing_items: List[Dict[str, Any]] = field(default_factory=list)

# =========================================================
# 3. Parsing Logic Class
# =========================================================

class MRSParser:
    def __init__(self, yaml_rule_content: str):
        """
        YAML 규칙을 로드하여 파서를 초기화합니다.
        """
        self.rules = yaml.safe_load(yaml_rule_content)
        self.type_defs = self.rules['mrs_schema']['mrs_only_types']
        self.expectations = self.rules['mrs_schema']['type_slot_expectations']['matrix']
        
    def _normalize(self, text: str) -> str:
        """1단계: 텍스트 정규화 (전처리)"""
        if not text: return ""
        text = text.lower()
        # 단위 통일
        text = re.sub(r'\b(msec|milliseconds)\b', 'ms', text)
        text = re.sub(r'\b(sec|seconds)\b', 's', text)
        # 줄바꿈 제거
        text = text.replace('\n', ' ').strip()
        return text

    def _determine_slot_state(self, slot_name: str, text: str) -> SlotData:
        """2단계: 슬롯 후보 탐지 및 상태(State) 판정"""
        keyword_pat = PATTERNS.get(slot_name)
        if not keyword_pat:
            return SlotData()

        # 1. 후보 탐지 (Candidates)
        matches = list(re.finditer(keyword_pat, text))
        if not matches:
            return SlotData(state=SlotState.ABSENT)

        candidates = [m.group() for m in matches]
        spans = [m.span() for m in matches]
        state = SlotState.WEAK # 기본적으로 키워드가 있으면 WEAK 시작

        # 2. 강력한 구조 확인 (OK 판정)
        # YAML 규칙의 'missing_definition' 등과 연계 가능하나, 여기선 정규식으로 구현
        strong_key = f"Strong_{slot_name}"
        if strong_key in PATTERNS:
            if re.search(PATTERNS[strong_key], text):
                state = SlotState.OK
        else:
            # Anchor, What 등은 키워드가 명확하면 OK로 간주 (단순화)
            state = SlotState.OK

        return SlotData(state=state, candidates=candidates, spans=spans)

    def _determine_mrs_type(self, slots: Dict[str, SlotData]) -> str:
        """3단계: MRS-Only 타입 결정 (결정론적 우선순위)"""
        # YAML에 정의된 순서대로 검사 (T6 -> T5 -> ... -> T1)
        type_order = self.type_defs['type_order']
        
        for t_name in type_order:
            criteria = self.type_defs['types'][t_name]['match']
            match = True
            
            # 'all' 조건 검사
            if 'all' in criteria:
                for cond in criteria['all']:
                    slot_name = cond['slot']
                    allowed_states = cond['state_in'] # e.g., [OK]
                    if slots[slot_name].state.name not in allowed_states:
                        match = False
                        break
            
            # 'any' 조건 검사 (하나라도 만족하면 통과이나, all과 결합시 논리 주의)
            # 여기서는 YAML 구조상 all 조건을 만족하고 any 조건이 있다면 그것도 만족해야 한다고 가정
            if match and 'any' in criteria:
                any_match = False
                for cond in criteria['any']:
                    slot_name = cond['slot']
                    allowed_states = cond['state_in']
                    if slots[slot_name].state.name in allowed_states:
                        any_match = True
                        break
                if not any_match:
                    match = False
            
            if match:
                return t_name
                
        return "Unknown"

    def _apply_missingness_rules(self, req: ParsedRequirement):
        """4단계: 결손 라벨링 규칙 엔진 (S -> A -> P -> D 스테이지)"""
        if req.mrs_type not in self.expectations:
            return

        exp_map = self.expectations[req.mrs_type] # e.g., {Why: R, Anchor: M...}
        missing_report = []

        # --- Stage S: Severity Candidates (초기 라벨) ---
        for slot, expectation in exp_map.items():
            if req.slots[slot].state == SlotState.ABSENT:
                item = {"slot": slot, "label": MissingLabel.NONE, "rationale": ""}
                
                if expectation == 'M':
                    item["label"] = MissingLabel.ACTIONABLE
                    item["rationale"] = f"Rule S-M1: Mandatory slot '{slot}' is missing."
                elif expectation == 'R':
                    item["label"] = MissingLabel.DEFERRED
                    item["rationale"] = f"Rule S-R1: Recommended slot '{slot}' is missing."
                elif expectation == 'O':
                    item["label"] = MissingLabel.PERMISSIBLE
                    item["rationale"] = f"Rule S-O1: Optional slot '{slot}' is missing."
                
                missing_report.append(item)

        # --- Stage A: Anchor Driven Overrides ---
        # Rule A-ANC0: Anchor가 WEAK/ABSENT면 하류 슬롯(When, Constraints...)은 Deferred로 격하
        anchor_state = req.slots['Anchor'].state
        if anchor_state in [SlotState.WEAK, SlotState.VAGUE, SlotState.ABSENT]:
            target_slots = ['When', 'Constraints', 'Verification', 'AcceptanceCriteria']
            for item in missing_report:
                if item['slot'] in target_slots:
                    item['label'] = MissingLabel.DEFERRED
                    item['rationale'] += " [Override A-ANC0: Anchor weak]"

        # Rule A-WT1: What 결손은 항상 Actionable
        for item in missing_report:
            if item['slot'] == 'What':
                item['label'] = MissingLabel.ACTIONABLE
                item['rationale'] = "Rule A-WT1: Core requirement missing."

        # --- Stage P: Permissible Rules ---
        # Rule P-VV1: Verification이 없어도 (When+Constraints+Anchor+What이 OK)면 Permissible
        # (테스트 조건이 명확하여 명시적 Verification 키워드가 없어도 된다는 논리)
        if req.slots['Verification'].state == SlotState.ABSENT:
            if (req.slots['Anchor'].state == SlotState.OK and 
                req.slots['What'].state == SlotState.OK and
                req.slots['When'].state == SlotState.OK and
                req.slots['Constraints'].state == SlotState.OK):
                
                for item in missing_report:
                    if item['slot'] == 'Verification':
                        item['label'] = MissingLabel.PERMISSIBLE
                        item['rationale'] = "Rule P-VV1: Test closure exists (When+Constraints), explicit method deferred."

        req.missing_items = missing_report

    def parse(self, json_data: dict) -> ParsedRequirement:
        """단일 JSON 객체를 파싱하여 결과 반환"""
        raw_text = json_data.get('raw_text', '')
        norm_text = self._normalize(raw_text)

        # 1. 객체 생성
        req = ParsedRequirement(
            id=json_data.get('id', 'N/A'),
            raw_text=raw_text,
            normalized_text=norm_text,
            vehicle=json_data.get('vehicle', ''),
            controller=json_data.get('controller', ''),
            safety_goal=json_data.get('Safety Goal', ''),
            safe_state=json_data.get('Safe States', ''),
            ftti=json_data.get('FTTI', '')
        )

        # 2. 슬롯 상태 분석
        for slot in PATTERNS.keys():
            if slot.startswith("Strong_"): continue # 패턴용 키 제외
            req.slots[slot] = self._determine_slot_state(slot, norm_text)

        # 3. 타입 결정
        req.mrs_type = self._determine_mrs_type(req.slots)

        # 4. 결손 분석
        self._apply_missingness_rules(req)

        return req

# =========================================================
# 4. Execution Example
# =========================================================

def load_data_and_run(yaml_path='MRS.yaml', data_dir='./data/'):
    # 1. YAML 로드 (파일이 없으면 프롬프트의 내용을 사용한다고 가정)
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()
    except FileNotFoundError:
        print(f"⚠️ {yaml_path} 파일을 찾을 수 없습니다. 예제 실행을 위해 내장된 YAML을 사용합니다.")
        # [여기에 프롬프트에 제공된 YAML 전체 내용이 들어갑니다. 편의상 생략하고 핵심 구조만 모사합니다.]
        # 실제 사용시에는 제공해주신 전체 YAML 텍스트를 파일로 저장하거나 여기에 문자열로 넣어야 합니다.
        # 예시를 위해 최소한의 YAML 문자열을 정의합니다.
        yaml_content = """
mrs_schema:
  mrs_only_types:
    type_order: [T6_VerificationCentric, T5_ConstraintCentric, T4_WhenCentric, T2_WhatCentric, T1_WhyCentric]
    types:
      T6_VerificationCentric:
        match: { all: [{slot: Verification, state_in: [OK]}, {slot: AcceptanceCriteria, state_in: [OK]}] }
      T5_ConstraintCentric:
        match: { all: [{slot: Constraints, state_in: [OK]}] }
      T4_WhenCentric:
        match: { all: [{slot: When, state_in: [OK]}] }
      T2_WhatCentric:
        match: { all: [{slot: What, state_in: [OK]}, {slot: Anchor, state_in: [OK]}] }
      T1_WhyCentric:
        match: { all: [{slot: Why, state_in: [OK]}] }
  type_slot_expectations:
    matrix:
      T5_ConstraintCentric:
        Why: R
        Anchor: M
        What: M
        HowType: R
        When: R
        Constraints: M
        Verification: R
        AcceptanceCriteria: O
        """

    parser = MRSParser(yaml_content)

    # 2. JSON 데이터 읽기
    json_files = glob.glob(os.path.join(data_dir, "*.json"))
    
    # (테스트용 더미 데이터 생성 - 파일이 없을 경우)
    if not json_files:
        print("⚠️ ./data/ 폴더에 JSON 파일이 없습니다. 테스트 데이터를 생성합니다.")
        dummy_data = [
            {
                "id": "REQ-001",
                "vehicle": "EV_Platform",
                "controller": "BMS",
                "raw_text": "The BMS shall stop charging within 200ms if voltage exceeds 4.2V.",
                "Safety Goal": "Prevent Overcharge",
                "FTTI": "500ms"
            },
            {
                "id": "REQ-002", 
                "vehicle": "General", 
                "controller": "ADAS", 
                "raw_text": "To prevent collision, the system shall warn the driver.", 
                # Constraints가 없고, When도 명확치 않음 -> T1 or T2 예상
            }
        ]
        items_to_process = dummy_data
    else:
        items_to_process = []
        for jf in json_files:
            with open(jf, 'r', encoding='utf-8') as f:
                content = json.load(f)
                if isinstance(content, list): items_to_process.extend(content)
                else: items_to_process.append(content)

    # 3. 파싱 및 결과 출력
    print("\n" + "="*60)
    print(f"🧬 MRS Parser Execution Report")
    print("="*60)
    
    for item in items_to_process:
        result = parser.parse(item)
        
        print(f"\n🔹 ID: {result.id}")
        print(f"   RAW: \"{result.raw_text}\"")
        print(f"   TYPE: {result.mrs_type}")
        
        # 슬롯 상태 출력
        states_str = ", ".join([f"{k}={v.state.name}" for k,v in result.slots.items() if v.state != SlotState.ABSENT])
        print(f"   SLOTS: {states_str}")
        
        # 결손 분석 출력
        if result.missing_items:
            print("   ⚠️  MISSING ANALYSIS:")
            for m in result.missing_items:
                print(f"      - [{m['label']}] {m['slot']}: {m['rationale']}")
        else:
            print("   ✅ COMPLETE (No actionable missing items)")

if __name__ == "__main__":
    # 실행
    load_data_and_run()