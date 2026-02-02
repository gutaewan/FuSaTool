import json
import re
import yaml
import glob
import os
import requests
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# =========================================================
# 0. Configuration & Hierarchy Rules
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

# [위계 관계 정의]
# 좌측(Superior)이 없으면 우측(Subordinate)은 무조건 ABSENT 처리
HIERARCHY_RELATIONS = [
    # 관계 1: 주체(Anchor) -> 행위(What)
    # 해석: Anchor가 없으면 What은 성립할 수 없음 (누가 하는지 모르므로)
    {"superior": "Anchor", "subordinate": ["What"]},
    
    # 관계 2: 행위(What) -> 조건(When), 제약(Constraints), 방법(HowType)
    # 해석: 무엇을 하는지(What)가 없으면, 언제/어떻게/얼마나(Conditions)는 무의미함
    {"superior": "What", "subordinate": ["When", "Constraints", "HowType"]},
    
    # 관계 3: 검증(Verification) -> 기준(AcceptanceCriteria)
    # 해석: 검증 행위(Test)가 상위, 기준(Criteria)은 검증의 하위 요소
    # (주의: 기준만 있고 검증이 없는 경우는 허용될 수도 있으나, 여기선 엄격한 위계 적용 시 Verification이 주체)
    {"superior": "Verification", "subordinate": ["AcceptanceCriteria"]}
]

ANCHOR_KEYWORDS = r"(ecu|controller|sensor|actuator|module|component|system|can|signal|message|data|bus|interface|" \
                  r"bms|vcu|mcu|inverter|motor|engine|battery|cell|pack|relay|hvil|lidar|radar|camera|ultrasonic|esp|abs|tcs|mdps|epb|" \
                  r"제어기|센서|모듈|시스템|신호|패킷|장치|배터리|인버터|모터|엔진|카메라|레이더|라이더|조향|제동|구동)"

PATTERNS = {
    "Why": r"(to prevent|in order to|ensure|guarantee|purpose|goal|목적|위해|보장|방지|hazard|risk|우려|위험)[^,.]*",
    "Anchor": ANCHOR_KEYWORDS,
    "What": r"(shall|must|should|will|request|command|perform|provide|maintain|limit|open|close|stop|start|" \
            r"해야 한다|한다|수행한다|전송한다|제공한다|유지해야 한다|제한한다|개방해야 한다|차단해야 한다|금지한다|멈춰야 한다)[^,.]*",
    "HowType": r"(detect|mitigate|transition|limit|warn|redundancy|monitor|fallback|diagnose|inhibit|ignore|override|" \
               r"감지|완화|전환|제한|경고|이중화|대체|무시|억제|진입|해제|금지)[^,.]*",
    "When": r"(when|if|upon|during|in case of|while|after|before|whenever|condition|" \
            r"조건|~시|~경우|~동안|발생 시|도달 시|수신 시|상태에서|직후|이전)[^,.]*",
    "Constraints": r"(\d+(\.\d+)?\s*(ms|s|sec|msec|hz|v|a|ma|nm|kw|kph|mph|%|deg|c|bar)|within|at least|no more than|ftti|latency|" \
                   r"이내|이상|미만|초과|주기적으로|최소|최대|범위)[^,.]*",
    "Verification": r"(test|verify|validate|analysis|inspection|review|check|demonstration|" \
                    r"시험|분석|검토|검사|실증|확인)[^,.]*",
    "AcceptanceCriteria": r"(pass|fail|acceptance|criteria|threshold|deemed|tolerance|margin|" \
                          r"합격|불합격|기준|판정|허용|오차)[^,.]*"
}

class SlotState(str, Enum):
    OK = "OK"
    WEAK = "WEAK"
    ABSENT = "ABSENT"

@dataclass
class SlotData:
    candidates: List[str] = field(default_factory=list)
    selected: Optional[str] = None
    state: SlotState = SlotState.ABSENT

@dataclass
class ParseResult:
    id: str
    raw_text: str
    mrs_type: str = "Unknown"
    type_rationale: str = ""
    slots: Dict[str, SlotData] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

# =========================================================
# Stage 1: Candidate Generator (High Recall)
# =========================================================
class CandidateGenerator:
    def _normalize(self, text: str) -> str:
        if not text: return ""
        text = text.lower().replace('\n', ' ').strip()
        text = re.sub(r'\b(msec|milliseconds)\b', 'ms', text)
        text = re.sub(r'\b(sec|seconds)\b', 's', text)
        return text

    def generate(self, item: dict) -> ParseResult:
        text = self._normalize(item.get('raw_text', ''))
        req_id = item.get('req_id', item.get('id', 'N/A'))
        
        result = ParseResult(id=req_id, raw_text=item.get('raw_text', ''))
        
        for slot, pat in PATTERNS.items():
            matches = list(re.finditer(pat, text))
            candidates = []
            seen = set()
            for m in matches:
                span = m.group().strip()
                if len(span) < 2 or span in seen: continue
                candidates.append(span)
                seen.add(span)
            
            # 후보가 있으면 일단 WEAK로 설정 (나중에 LLM이 선택)
            initial_state = SlotState.WEAK if candidates else SlotState.ABSENT
            result.slots[slot] = SlotData(candidates=candidates, state=initial_state)
            
        return result

# =========================================================
# Stage 2: LLM Selector (Final Presence Check)
# =========================================================
class LLMSelector:
    """
    LLM에게 모든 후보를 보여주고, 문맥상 존재하는 것들을 선택하게 함.
    이 단계에서 LLM이 'NONE'을 반환하면 해당 요소는 없다고 판단함.
    """
    def __init__(self, model="mistral"):
        self.model = model
        self.api_url = "http://localhost:11434/api/generate"

    def select(self, result: ParseResult) -> ParseResult:
        # 후보가 있는 슬롯만 LLM에게 질문
        active_candidates = {k: v.candidates for k, v in result.slots.items() if v.candidates}
        
        if not active_candidates:
            result.logs.append("ℹ️ No candidates to verify with LLM.")
            return result

        prompt = f"""
You are an expert Requirements Analyst.
I have extracted candidate spans for MRS slots.
Your task is to SELECT the most accurate span for each slot from the candidates.

Requirement: "{result.raw_text}"
Candidates: {json.dumps(active_candidates, ensure_ascii=False)}

Instructions:
1. Select the one best span for each slot.
2. If none of the candidates are correct/relevant in this context, return "NONE".
3. Return ONLY a JSON object: {{ "SlotName": "SelectedSpan" }}
"""
        payload = {
            "model": self.model, "prompt": prompt, "format": "json", "stream": False,
            "options": {"temperature": 0.0}
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=20)
            resp.raise_for_status()
            llm_out = json.loads(resp.json().get('response', '{}'))
            
            for slot, selection in llm_out.items():
                if slot in result.slots:
                    if selection and selection != "NONE":
                        result.slots[slot].selected = selection
                        result.slots[slot].state = SlotState.OK
                    else:
                        result.slots[slot].selected = None
                        result.slots[slot].state = SlotState.ABSENT # LLM 판단하에 결손
            
            result.logs.append("✅ LLM Presence Verification Completed.")
            
        except Exception as e:
            result.logs.append(f"⚠️ LLM Error: {e}")
            
        return result

# =========================================================
# Stage 3: Hierarchy Validator (Strict Logic)
# =========================================================
class HierarchyValidator:
    """
    LLM이 선택을 마친 후, 위계 규칙(Hierarchy)을 적용하여 논리적 결함을 제거함.
    규칙: 상위 요소(Superior)가 ABSENT이면 하위 요소(Subordinate)는 강제로 ABSENT 처리.
    """
    def validate(self, result: ParseResult) -> ParseResult:
        slots = result.slots
        logs = result.logs
        
        for rule in HIERARCHY_RELATIONS:
            sup_name = rule['superior']
            sub_names = rule['subordinate']
            
            sup_slot = slots.get(sup_name)
            
            # 상위 요소가 없으면 (ABSENT)
            if sup_slot.state == SlotState.ABSENT:
                for sub_name in sub_names:
                    sub_slot = slots.get(sub_name)
                    
                    # 하위 요소가 있는데(OK) 상위가 없으므로 무효화
                    if sub_slot.state == SlotState.OK:
                        old_val = sub_slot.selected
                        sub_slot.state = SlotState.ABSENT
                        sub_slot.selected = None
                        logs.append(f"✂️ [Hierarchy] Pruned '{sub_name}' ('{old_val}') because Superior '{sup_name}' is missing.")
                    
                    # 하위 요소가 이미 없는 경우는 '타당한 결손'이므로 아무것도 안 함 (Pass)
                    
        return result

# =========================================================
# Stage 4: Final Type Determination
# =========================================================
def determine_type(result: ParseResult, config_yaml: str):
    config = yaml.safe_load(config_yaml)
    type_defs = config['mrs_schema']['mrs_only_types']
    
    states = {k: v.state for k, v in result.slots.items()}
    
    for t_name in type_defs['type_order']:
        criteria = type_defs['types'][t_name]['match']
        match = True
        reasons = []
        for cond in criteria.get('all', []):
            cur = states.get(cond['slot'], SlotState.ABSENT)
            if cur.name not in cond['state_in']:
                match = False; break
            reasons.append(f"{cond['slot']}={cur.name}")
        
        if match:
            result.mrs_type = t_name
            result.type_rationale = ", ".join(reasons)
            return

def run_hierarchy_parser():
    # Pipeline
    generator = CandidateGenerator()
    selector = LLMSelector(model="mistral")
    validator = HierarchyValidator()

    # Data Load
    data_dir = './data/'
    items = []
    files = glob.glob(os.path.join(data_dir, "*.json"))
    if not files and os.path.exists("FuSaReq_new_augmented.json"): files = ["FuSaReq_new_augmented.json"]
    
    for jf in files:
        with open(jf, 'r', encoding='utf-8') as f:
            c = json.load(f)
            if isinstance(c, list): items.extend(c)
            elif isinstance(c, dict) and 'requirements' in c: items.extend(c['requirements'])

    print(f"\n🚀 [Hierarchy-Based MRS Parser]")
    print(f"   Logic: Subordinate exists ONLY IF Superior exists.")
    print(f"   Flow: Rule(Gen) -> LLM(Verify) -> Logic(Enforce Hierarchy)")
    print(f"   Total Requirements: {len(items)}\n")

    for idx, item in enumerate(items, 1):
        # 1. Generate (Recall)
        res = generator.generate(item)
        
        # 2. LLM Verify (Precision)
        # LLM에게 먼저 물어봐서 상위/하위 요소가 진짜 있는지 확인
        res = selector.select(res)
        
        # 3. Hierarchy Enforce (Logic)
        # LLM 결과를 바탕으로 "상위 요소 부재 시 하위 요소 제거" 수행
        res = validator.validate(res)
        
        # 4. Final Type
        determine_type(res, DEFAULT_MRS_CONFIG)

        # Output
        print("\n" + "="*80)
        print(f"🔸 [{res.id}] {res.mrs_type} (Reason: {res.type_rationale})")
        print(f"   \"{res.raw_text}\"")
        print("-" * 80)
        
        for slot, data in res.slots.items():
            if data.candidates:
                icon = "✅" if data.state == SlotState.OK else "⬜"
                # 선택된 게 있으면 보여주고, 없으면 (NONE)
                sel_text = f"\"{data.selected}\"" if data.selected else "(NONE)"
                
                # 시각적으로 상위 요소가 없어서 잘린 경우 Log에서 확인 가능
                print(f"   {icon} {slot:<12} | {sel_text}")
        
        if res.logs:
            print(f"   📝 Logs:")
            for log in res.logs: print(f"      {log}")

if __name__ == "__main__":
    run_hierarchy_parser()