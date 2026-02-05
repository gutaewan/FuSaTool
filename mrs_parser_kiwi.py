import json
import re
import yaml
import glob
import os
import requests
from collections import Counter
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set

# kiwipiepy 확인
try:
    from kiwipiepy import Kiwi
except ImportError:
    print("❌ 'kiwipiepy' 라이브러리가 없습니다. 'pip install kiwipiepy'를 실행해주세요.")
    exit(1)

# =========================================================
# 0. Configuration & Static Data
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

# [위계 규칙] 관계 정의
# 논리: Right(후반부)가 존재하려면 Left(전반부)가 반드시 존재해야 함.
#      (Left가 없으면 Right는 무효/Pruning 대상)
HIERARCHY_RELATIONS = [
    {"left": "Constraints", "right": "When", "rel": "requires"},
    {"left": "When", "right": "Constraints", "rel": "refines"},
    {"left": "When", "right": "What", "rel": "triggers"},
    {"left": "Why", "right": "What", "rel": "justifies"},
    {"left": "Constraints", "right": "What", "rel": "qualifies"},
    {"left": "Constraints", "right": "Verification", "rel": "verifiedBy"},
    {"left": "What", "right": "HowType", "rel": "refines"},
    {"left": "What", "right": "Verification", "rel": "verifiedBy"},
    {"left": "Verification", "right": "AcceptanceCriteria", "rel": "acceptedBy"},
    {"left": "AcceptanceCriteria", "right": "Verification", "rel": "requires"},
    # [안전장치] Anchor가 없으면 행위(What)도 성립 불가 (기본 대전제)
    {"left": "Anchor", "right": "What", "rel": "performs"}
]

# [기본 도메인 사전] - 단위나 필수 용어 (자동 추출로 놓칠 수 있는 것들)
BASE_DOMAIN_TERMS = [
    # Units & Common
    "ms", "s", "sec", "msec", "Hz", "V", "A", "mA", "Nm", "kW", "kph", "mph", "%", "deg", "C", "bar",
    "Time", "Voltage", "Current", "Temperature", "Pressure", "Speed", "Torque",
    "ECU", "Sensor", "Actuator", "System", "Function", "Module"
]

# [불용어] - 도메인 용어로 오해하기 쉬운 일반 명사들
STOPWORDS = {
    "경우", "때", "수", "것", "등", "및", "함", "전", "후", "시", 
    "이상", "이하", "초과", "미만", "내", "간", "값", "중", "위", 
    "대해", "관련", "사용", "수행", "동작", "상태", "발생", "기능",
    "포함", "적용", "요구", "확인", "제공", "유지", "설정", "방식",
    "기준", "항목", "내용", "부분", "사이", "다음", "아래", "위해",
    "가능", "필요", "도달", "감지", "판단", "여부", "직후", "이전",
    "도", "분", "초", "회", "개", "번", "가지" 
}

# =========================================================
# [Module 1] Domain Term Extractor (Auto-Learning)
# =========================================================
class DomainTermExtractor:
    def __init__(self):
        self.kiwi = Kiwi()
        self.term_counter = Counter()

    def _is_valid_term(self, word: str, tag: str) -> bool:
        if word in STOPWORDS: return False
        # 한 글자 한글 명사는 노이즈가 많음 (단, 영어는 허용)
        if len(word) == 1 and not re.match(r'[a-zA-Z]', word): return False
        if re.match(r'^\d+$', word): return False
        return True

    def extract(self, items: List[Dict]) -> List[str]:
        print(f"📖 Learning domain terms from {len(items)} items...")
        
        for item in items:
            # 1. 메타데이터 (가중치 높음)
            meta = item.get('meta', {})
            explicit = [meta.get('component'), meta.get('ecu'), item.get('controller'), item.get('vehicle')]
            if 'vehicle_models' in meta: explicit.extend(meta['vehicle_models'])
            
            for term in explicit:
                if term and isinstance(term, str):
                    self.term_counter[term.strip()] += 10

            # 2. 본문 분석 (가중치 보통)
            raw = item.get('raw_text', '')
            if raw:
                tokens = self.kiwi.tokenize(raw)
                for t in tokens:
                    if t.tag in ['NNG', 'NNP', 'SL']:
                        if self._is_valid_term(t.form, t.tag):
                            self.term_counter[t.form] += 1
        
        # 빈도 2 이상인 용어만 추출
        extracted = [term for term, count in self.term_counter.items() if count >= 2]
        # 빈도순 정렬
        extracted.sort(key=lambda x: self.term_counter[x], reverse=True)
        
        print(f"📊 Learned {len(extracted)} domain terms (Top 5: {extracted[:5]})")
        return extracted

# =========================================================
# [Module 2] Parser Data Structures
# =========================================================
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
# Stage 1: Kiwi Candidate Generator
# =========================================================
class KiwiCandidateGenerator:
    def __init__(self, learned_terms: List[str]):
        self.kiwi = Kiwi()
        self.domain_terms = list(set(BASE_DOMAIN_TERMS + learned_terms))
        self._register_user_words()
        
        self.regex_patterns = {
            "When": r"(if|when|upon|during|in case of|while|after|before|조건|~시|~경우|~동안|발생 시)[^,.]*",
            "Why": r"(to prevent|in order to|ensure|guarantee|목적|위해|보장|방지)[^,.]*"
        }

    def _register_user_words(self):
        for term in self.domain_terms:
            self.kiwi.add_user_word(term, tag='NNP', score=10)
    
    def _normalize(self, text: str) -> str:
        return text.strip()

    def generate(self, item: dict) -> ParseResult:
        raw_text = self._normalize(item.get('raw_text', ''))
        req_id = item.get('req_id', item.get('id', 'N/A'))
        result = ParseResult(id=req_id, raw_text=raw_text)
        
        tokens = self.kiwi.tokenize(raw_text)
        candidates = {k: [] for k in ["Anchor", "What", "Constraints", "Verification", "AcceptanceCriteria", "HowType", "When", "Why"]}
        
        # 반복문 제어를 위해 while 사용 (토큰 건너뛰기 등 유연성 확보)
        i = 0
        while i < len(tokens):
            token = tokens[i]
            form, tag = token.form, token.tag
            is_consumed = False # 현재 토큰이 특정 슬롯으로 처리되었는지 여부
            
            # 1. [Constraints] 숫자(SN) + 단위
            # 수치 뒤에 오는 것이 단위(SL, NNB, NNG)라면 Constraints로 묶음
            if tag == 'SN':
                phrase = form
                # 뒤에 단위가 있는지 확인
                if i + 1 < len(tokens):
                    next_t = tokens[i+1]
                    # SL(영어단위), NNB(의존명사: 번, 개, 초), NNG(일반명사: 도, 분)
                    if next_t.tag in ['SL', 'NNB', 'NNG'] or next_t.form in ['ms', 's', 'V', 'A', '도', '분', '초']:
                        phrase += next_t.form
                        is_consumed = True # 뒤 토큰까지 소모했다고 가정할 수도 있음(여기선 단순 병합)
                
                candidates["Constraints"].append(phrase)
                # 숫자는 Anchor가 될 수 없으므로 consumed 처리
                is_consumed = True

            # 2. [What] 동사(VV) 및 명사형 동사(NNG+XSV) 처리 ★핵심 수정★
            
            # Case A: 명사(NNG) + 파생접미사(XSV: 하, 되, 시키) -> 명사형 동사
            # 예: "가속(NNG) + 하(XSV)" -> "가속하(What)"
            if tag in ['NNG', 'NNP'] and i + 1 < len(tokens):
                next_t = tokens[i+1]
                if next_t.tag in ['XSV']:  # -하, -되, -시키 등
                    # 접미사 뒤에 어미(E...)가 붙으면 더 길게 가져옴
                    phrase = form + next_t.form
                    lookahead = 2
                    while i + lookahead < len(tokens) and tokens[i+lookahead].tag.startswith('E'):
                        phrase += tokens[i+lookahead].form
                        lookahead += 1
                    
                    candidates["What"].append(phrase)
                    is_consumed = True # 명사였지만 동사로 쓰였으므로 Anchor 후보에서 제외!
            
            # Case B: 명사(NNG) + 동사 '하다/되다'(VV) 가 분리된 경우
            # 예: "동작(NNG) + 을(JKO) + 한다(VV)" -> "동작을 한다(What)"
            # 예: "동작(NNG) + 한다(VV)"
            if tag in ['NNG', 'NNP'] and not is_consumed:
                # 바로 뒤나, 조사 뒤에 '하다/되다'가 오는지 체크
                # 간단히 바로 뒤에 '하다' 계열이 오는 경우만 What으로 병합 (복잡성 방지)
                if i + 1 < len(tokens):
                    next_t = tokens[i+1]
                    if next_t.tag == 'VV' and next_t.form in ['하', '되', '시키']:
                        phrase = form + next_t.form
                        # 어미 추가
                        lookahead = 2
                        while i + lookahead < len(tokens) and tokens[i+lookahead].tag.startswith('E'):
                            phrase += tokens[i+lookahead].form
                            lookahead += 1
                        candidates["What"].append(phrase)
                        is_consumed = True

            # Case C: 순수 동사(VV)
            if tag == 'VV':
                # '하', '되' 같은 보조적 동사가 단독으로 쓰인게 아니라면
                if form not in ['하', '되'] or (i > 0 and tokens[i-1].tag not in ['NNG', 'NNP']): 
                    phrase = form
                    lookahead = 1
                    while i + lookahead < len(tokens) and tokens[i+lookahead].tag.startswith('E'):
                        phrase += tokens[i+lookahead].form
                        lookahead += 1
                    candidates["What"].append(phrase)
                    is_consumed = True

            # 3. [Anchor] 명사(NNG, NNP, SL)
            # ★중요★: 위에서 명사형 동사(is_consumed)로 판명된 경우 Anchor에 넣지 않음
            if tag in ['NNG', 'NNP', 'SL'] and not is_consumed:
                # 도메인 용어이거나 조사가 붙은 경우
                if form in self.domain_terms or (i+1 < len(tokens) and tokens[i+1].tag in ['JKS', 'JX', 'JC', 'JKO']):
                    candidates["Anchor"].append(form)

            i += 1
        
        # 4. 정규식 보조 (When, Why)
        for slot, pat in self.regex_patterns.items():
            matches = re.finditer(pat, raw_text, re.IGNORECASE)
            for m in matches:
                candidates[slot].append(m.group().strip())

        # 5. 결과 정리
        for slot, cands in candidates.items():
            unique_cands = sorted(list(set(cands)), key=len, reverse=True)
            state = SlotState.WEAK if unique_cands else SlotState.ABSENT
            result.slots[slot] = SlotData(candidates=unique_cands, state=state)

        return result

# =========================================================
# Stage 2: LLM Selector (Enhanced Anchor Logic)
# =========================================================
class LLMSelector:
    def __init__(self, model="mistral"):
        self.model = model
        self.api_url = "http://localhost:11434/api/generate"

    def select(self, result: ParseResult) -> ParseResult:
        active_candidates = {k: v.candidates for k, v in result.slots.items() if v.candidates}
        
        if not active_candidates:
            result.logs.append("ℹ️ No candidates to verify.")
            return result

        # [핵심 수정] 사용자님이 정의한 3가지 기준을 프롬프트 규칙으로 변환
        prompt = f"""
You are an expert Requirements Analyst.
I have extracted candidate keywords using a morphological analyzer (Kiwi).
Kiwi extracts all nouns, verbs, and numbers without context.
Your job is to apply **CONTEXTUAL LOGIC** to filter these candidates.

Requirement: "{result.raw_text}"
Candidates: {json.dumps(active_candidates, ensure_ascii=False)}

### ⚠️ CRITICAL FILTERING RULES (MUST FOLLOW) ⚠️ ###

1. **Anchor: Distinguish Subject vs. Object**
   - Kiwi captures ALL nouns. You must identify the **Active Agent** (Subject).
   - **Rule**: If 'Candidate A' acts upon 'Candidate B', then 'A' is the Anchor. 'B' is the Target/Object (Ignore B).
   - *Example*: "Diagnostic Tool checks BMS" -> Anchor: ["Diagnostic Tool"] (NOT BMS).
   - *Exception*: If the sentence is Passive ("BMS is checked"), then 'BMS' is the Anchor.

2. **Constraints: Distinguish Limit vs. ID**
   - Kiwi captures ALL numbers. You must identify **Performance Limits** (Time, Voltage, etc.).
   - **Rule**: Identifiers (CAN ID, HEX codes, Addresses, Version numbers) are **NOT** constraints.
   - *Example*: "Send CAN ID 0x100 every 10ms" -> Constraints: ["10ms"] (Ignore 0x100).

3. **What: Distinguish Main Action vs. Modifier**
   - Kiwi captures ALL verbs. You must identify the **Main Clause Action** (Shall/Must).
   - **Rule**: Ignore verbs used as adjectives, modifiers, or inside 'If/When' conditions.
   - *Example*: "Controller *detecting* error *shall shut down*" -> What: ["shall shut down"] (Ignore 'detecting' - it's a modifier/condition).

### INSTRUCTIONS ###
1. Select the BEST span(s) for each slot based on the rules above.
2. Return a **LIST** of strings for each slot.
3. If all candidates for a slot are invalid (e.g., only IDs found for Constraints), return "NONE".
4. Return JSON object: {{ "SlotName": ["SelectedSpan1", ...] }}
"""
        payload = {
            "model": self.model, "prompt": prompt, "format": "json", "stream": False,
            "options": {"temperature": 0.0} # 결정론적 답변을 위해 0.0 유지
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=20)
            resp.raise_for_status()
            llm_out = json.loads(resp.json().get('response', '{}'))
            
            for slot, selection in llm_out.items():
                if slot in result.slots:
                    # 결과를 리스트로 정규화
                    valid_selections = []
                    raw_list = selection if isinstance(selection, list) else ([selection] if isinstance(selection, str) else [])
                    
                    for val in raw_list:
                        if val and str(val).upper() not in ["NONE", "ABSENT", "NULL", ""]:
                            valid_selections.append(val)
                    
                    if valid_selections:
                        result.slots[slot].selected = valid_selections
                        result.slots[slot].state = SlotState.OK
                    else:
                        result.slots[slot].selected = []
                        result.slots[slot].state = SlotState.ABSENT

        except Exception as e:
            result.logs.append(f"⚠️ LLM Error: {e}")
            
        return result
    
# =========================================================
# Stage 3: Hierarchy Validator
# =========================================================
class HierarchyValidator:
    def validate(self, result: ParseResult) -> ParseResult:
        slots = result.slots
        logs = result.logs
        
        # 관계 규칙 순회
        for rule in HIERARCHY_RELATIONS:
            left_key = rule['left']   # 전반부 (필수 조건)
            right_key = rule['right'] # 후반부 (종속 대상)
            relation = rule.get('rel', 'related')
            
            # 로직: "후반부(Right)는 있는데(OK), 전반부(Left)가 없다면(ABSENT) -> 문제 발생"
            # 조치: 후반부(Right)를 신뢰할 수 없으므로 제거(Prune)
            if slots[right_key].state == SlotState.OK and slots[left_key].state == SlotState.ABSENT:
                
                old_val = slots[right_key].selected
                
                # 후반부 슬롯 무효화
                slots[right_key].state = SlotState.ABSENT
                slots[right_key].selected = []
                
                logs.append(f"✂️ [Hierarchy] Pruned '{right_key}' ({old_val}) because source '{left_key}' is missing (Relation: {relation}).")

        return result

# =========================================================
# Stage 4: Type Determiner
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

# =========================================================
# Main Execution Flow
# =========================================================
def run_kiwi_pipeline():
    # 0. Data Load (전체 데이터를 먼저 로드해야 학습 가능)
    items = []
    files = glob.glob(os.path.join('./data/', "*.json"))
    if not files and os.path.exists("FuSaReq_new_augmented.json"): files = ["FuSaReq_new_augmented.json"]
    
    for jf in files:
        with open(jf, 'r', encoding='utf-8') as f:
            c = json.load(f)
            if isinstance(c, list): items.extend(c)
            elif isinstance(c, dict) and 'requirements' in c: items.extend(c['requirements'])

    if not items:
        print("❌ No data found.")
        return

    # 1. Domain Term Learning (Extractor 실행)
    print("🧠 [Step 1] Extracting domain terms from data...")
    extractor = DomainTermExtractor()
    learned_terms = extractor.extract(items)

    # 2. Pipeline Initialization (학습된 용어 전달)
    print("⏳ [Step 2] Initializing Parser with learned terms...")
    generator = KiwiCandidateGenerator(learned_terms)
    selector = LLMSelector(model="mistral")
    validator = HierarchyValidator()

    print(f"\n🚀 [Step 3] Running MRS Kiwi-Hybrid Parser")
    print(f"   Flow: TermLearn -> Kiwi(Morph) -> LLM(Select) -> Logic(Hierarchy)")
    print(f"   Total Requirements: {len(items)}\n")

    for idx, item in enumerate(items, 1):
        # 3.1 Generate
        res = generator.generate(item)
        # 3.2 Select
        res = selector.select(res)
        # 3.3 Validate
        res = validator.validate(res)
        # 3.4 Type
        determine_type(res, DEFAULT_MRS_CONFIG)

        # Output
        print("\n" + "="*80)
        print(f"🔸 [{res.id}] {res.mrs_type} (Reason: {res.type_rationale})")
        print(f"   \"{res.raw_text}\"")
        print("-" * 80)
        
        for slot, data in res.slots.items():
            if data.candidates:
                icon = "✅" if data.state == SlotState.OK else "⬜"
                if data.selected:
                    sel_text = str(data.selected) # ['BMS', 'VCU'] 처럼 출력됨
                else:
                    sel_text = "(NONE)"
                cands_disp = str(data.candidates[:3]) + ("..." if len(data.candidates)>3 else "")
                print(f"   {icon} {slot:<12} | Selected: {sel_text:<20} | Candidates: {cands_disp}")
        
        if res.logs:
            print(f"   📝 Logs:")
            for log in res.logs: print(f"      {log}")

if __name__ == "__main__":
    run_kiwi_pipeline()