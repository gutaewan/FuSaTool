import json
import re
import yaml
import glob
import os
import requests
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any

# =========================================================
# 0. Configuration & Patterns
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
    slots: Dict[str, SlotState]

# =========================================================
# 1. Helper Logic
# =========================================================
def determine_mrs_type(slots: Dict[str, SlotState], config: dict) -> str:
    type_defs = config['mrs_schema']['mrs_only_types']
    for t_name in type_defs['type_order']:
        criteria = type_defs['types'][t_name]['match']
        match = True
        for cond in criteria.get('all', []):
            current_state = slots.get(cond['slot'], SlotState.ABSENT)
            if current_state.name not in cond['state_in']:
                match = False; break
        if match:
            return t_name
    return "Unknown"

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

        mrs_type = determine_mrs_type(slots, self.config)
        return ParseResult(req_id, mrs_type, slots)

# =========================================================
# 3. Ollama (Mistral) Parser
# =========================================================
class OllamaParser:
    def __init__(self, config, model="mistral"):
        self.config = config
        self.model = model
        self.api_url = "http://localhost:11434/api/generate"
        
        # 프롬프트 템플릿
        self.system_prompt = """
You are an expert Requirements Engineer. Analyze the automotive requirement text based on the MRS (Meta Requirement Schema).
Slots: [Why, Anchor, What, HowType, When, Constraints, Verification, AcceptanceCriteria]
States: [OK, WEAK, ABSENT]
- OK: Clearly defined with specific values or strong structure.
- WEAK: Present but vague or missing specific details.
- ABSENT: Not mentioned.

Determine the 'mrs_type' from: [T1_WhyCentric, T2_WhatCentric, T3_HowTypeCentric, T4_WhenCentric, T5_ConstraintCentric, T6_VerificationCentric].
- T6: Verification + AcceptanceCriteria are OK.
- T5: Constraints is OK.
- T4: When is OK.
- T3: HowType is OK.
- T2: What + Anchor are OK.
- T1: Why is OK.
(Prioritize T6 > T5 > T4 > T3 > T2 > T1)

Return ONLY a JSON object:
{
  "mrs_type": "...",
  "slots": { "Why": "...", "Anchor": "...", ... }
}
"""

    def parse(self, item: dict) -> ParseResult:
        req_id = item.get('req_id', item.get('id', 'N/A'))
        raw_text = item.get('raw_text', '')
        
        prompt = f"{self.system_prompt}\n\nRequirement: \"{raw_text}\"\nJSON Output:"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            result_json = response.json()
            
            # LLM 응답 파싱
            llm_output = json.loads(result_json.get('response', '{}'))
            
            # 슬롯 상태 매핑
            slots = {}
            parsed_slots = llm_output.get('slots', {})
            for key in ["Why", "Anchor", "What", "HowType", "When", "Constraints", "Verification", "AcceptanceCriteria"]:
                state_str = parsed_slots.get(key, "ABSENT").upper()
                # Enum 변환 안전장치
                if state_str in ["OK", "WEAK", "ABSENT"]:
                    slots[key] = SlotState(state_str)
                else:
                    slots[key] = SlotState.ABSENT
            
            mrs_type = llm_output.get('mrs_type', "Unknown")
            
            return ParseResult(req_id, mrs_type, slots)

        except requests.exceptions.ConnectionError:
            print("❌ Error: Cannot connect to Ollama. Make sure Ollama is running (`ollama serve`).")
            return ParseResult(req_id, "ConnectionError", {})
        except Exception as e:
            print(f"⚠️  LLM Error on {req_id}: {e}")
            return ParseResult(req_id, "Error", {})

# =========================================================
# 4. Reporting
# =========================================================
def format_slots_line(slots: Dict[str, SlotState]) -> str:
    active = []
    for k, v in slots.items():
        if v == SlotState.OK: active.append(f"{k}(OK)")
        elif v == SlotState.WEAK: active.append(f"{k}(WEAK)")
    return ", ".join(active) if active else "(None)"

def run_ollama_comparison():
    config = yaml.safe_load(DEFAULT_MRS_CONFIG)
    rule_parser = AdvancedRuleParser(config)
    
    # [변경] ReferenceParser 대신 OllamaParser 사용
    print("⏳ Initializing Ollama (Mistral)...")
    llm_parser = OllamaParser(config, model="mistral")

    # 데이터 로드
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

    print(f"\n🚀 [Rule-based vs Ollama(Mistral) Comparison]")
    print(f"   Total Requirements: {len(items)}")
    print(f"   Note: This process may take time depending on your GPU/CPU speed.\n")
    
    stats = {"match": 0, "mismatch": 0, "error": 0}

    for idx, item in enumerate(items, 1):
        r_res = rule_parser.parse(item)
        l_res = llm_parser.parse(item) # 실제 LLM 호출
        
        if l_res.mrs_type in ["ConnectionError", "Error"]:
            stats["error"] += 1
            if l_res.mrs_type == "ConnectionError": break # 연결 안되면 중단
            continue

        print("\n" + "="*80)
        print(f"🔸 Item #{idx} : [{item.get('req_id', 'N/A')}]")
        print(f"   Raw Text: \"{item.get('raw_text', '').strip()}\"")
        print("-" * 80)
        
        print(f"   🤖 [Rule Parser] Type: {r_res.mrs_type:<20} | Slots: {format_slots_line(r_res.slots)}")
        print(f"   🦙 [Ollama LLM ] Type: {l_res.mrs_type:<20} | Slots: {format_slots_line(l_res.slots)}")
        
        print("-" * 80)
        if r_res.mrs_type == l_res.mrs_type:
            print(f"   ✅ TYPE MATCH")
            stats['match'] += 1
        else:
            print(f"   ❌ TYPE MISMATCH")
            stats['mismatch'] += 1
        
        # 상세 비교
        diffs = []
        check_slots = ["Why", "Anchor", "What", "HowType", "When", "Constraints", "Verification", "AcceptanceCriteria"]
        match_slots = 0
        for k in check_slots:
            r_val = r_res.slots.get(k, SlotState.ABSENT)
            l_val = l_res.slots.get(k, SlotState.ABSENT)
            if r_val == l_val:
                match_slots += 1
            else:
                diffs.append(f"{k}(Rule:{r_val.name}!=LLM:{l_val.name})")

        agree_pct = (match_slots / len(check_slots)) * 100
        print(f"   📊 Slot Agreement: {agree_pct:.1f}%")
        
        if diffs:
            print(f"   ⚠️  Diffs: {', '.join(diffs)}")

    print("\n" + "="*80)
    print(f"📈 Comparison Summary")
    print(f"   Total: {len(items)}")
    print(f"   Matches: {stats['match']} | Mismatches: {stats['mismatch']} | Errors: {stats['error']}")
    if stats['match'] + stats['mismatch'] > 0:
        acc = (stats['match'] / (stats['match'] + stats['mismatch'])) * 100
        print(f"   Agreement Rate: {acc:.1f}%")
    print("="*80)

if __name__ == "__main__":
    run_ollama_comparison()