import json
import re
import os
from langchain_community.llms import Ollama
from tabulate import tabulate

# ==============================================================================
# [설정 변경]
# 1. 파일명 설정
FILENAME = "FuSaReq01.json" 
# 2. 모델 변경 (llama3 -> mistral)
MODEL_NAME = "mistral"          
# ==============================================================================

# [핵심 변경] 단순 리스트가 아니라, 각 Slot별 상세 평가 기준을 정의합니다.
IR_DEFINITIONS = {
    "Why": "The rationale or justification for the requirement. Does it explain 'Why' this function is needed for safety? (e.g., linked to Safety Goal)",
    "What": "The core function or action. Does it clearly describe 'What' the system shall do? (Subject + Action Verb)",
    "How": "Qualitative or quantitative attributes of the action. Does it describe the 'manner' of operation? (e.g., forcefully, gradually, visually)",
    "When": "The trigger condition or state. Does it specify 'When' the action executes? (e.g., Pre-conditions, Triggers)",
    "Constraints": "Performance limits or bounds. Does it include specific values like FTTI, Latency, Voltage limits, or Tolerance?",
    "Verification": "How to verify this requirement. Is the requirement testable? Does it imply a verification method?",
    "Acceptance criteria": "The pass/fail criteria. What specific outcome defines success?",
    "Anchors": "References to other IDs, interfaces, or system elements. Are the inputs/outputs or related components clearly identified?"
}

# 키 리스트만 따로 추출 (순서 보장용)
IR_SLOTS = list(IR_DEFINITIONS.keys())

class RequirementEvaluator:
    def __init__(self, model_name="mistral"):
        print(f"🤖 LLM 모델 초기화 중: {model_name}...")
        self.llm = Ollama(model=model_name)

    def clean_json_string(self, json_str):
        """LLM 출력에서 JSON만 추출"""
        json_str = re.sub(r'```json\s*', '', json_str)
        json_str = re.sub(r'```\s*$', '', json_str)
        return json_str.strip()

    def evaluate(self, req_id, requirement_text):
        """요구사항 텍스트 평가"""
        
        prompt = f"""
        You are an Expert Requirements Engineer based on ISO 26262.
        
        Analyze the following requirement based on the 9 IR Slots.
        For each slot, assign a score from 1 to 5 and provide a reason in Korean.
        You should complement your evaluation with specific details from the requirement text.
        If the requirement is already well-defined for a slot, you don't need to add extra information.
        
        [Scoring Criteria (1-5)]:
        1: Missing (The slot information is completely absent)
        2: Vague (Mentioned but very ambiguous or abstract)
        3: Average (Understandable but lacks specific details/values)
        4: Good (Clear, specific, and unambiguous)
        5: Excellent (Perfectly defined, quantified with tolerances where applicable)

        [IR Slots]: {", ".join(IR_SLOTS)}

        [Target Requirement]:
        ID: {req_id}
        Text: "{requirement_text}"

        [Output Format]:
        Output ONLY a valid JSON object. Keys must be exactly the IR Slots.
        You must provide the answer in Korean.
        Example:
        {{
            "Why": {{"score": 1, "reason": "이유 설명..."}},
            "What": {{"score": 5, "reason": "이유 설명..."}}
        }}
        """

        try:
            # LLM 호출
            response = self.llm.invoke(prompt)
            cleaned_response = self.clean_json_string(response)
            return json.loads(cleaned_response)
        except Exception as e:
            print(f"   ❌ 평가 실패 ({req_id}): {e}")
            return None

def load_requirements(filename):
    """JSON 파일 로드"""
    if not os.path.exists(filename):
        print(f"❌ 파일을 찾을 수 없습니다: {filename}")
        return []

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        req_list = []
        if isinstance(data, list):
            req_list = data
        elif isinstance(data, dict):
            for key in ["requirements", "reqs", "data", "items"]:
                if key in data and isinstance(data[key], list):
                    req_list = data[key]
                    break
            if not req_list:
                req_list = [data]
        
        return req_list
    except Exception as e:
        print(f"❌ JSON 로드 에러: {e}")
        return []

def extract_text_and_id(item, index):
    """ID와 텍스트 추출"""
    req_id = item.get("id") or item.get("req_id") or item.get("ID") or f"REQ_{index+1}"
    text = item.get("text") or item.get("requirement") or item.get("description") or item.get("raw_text")
    
    if isinstance(item, str):
        text = item
        req_id = f"REQ_{index+1}"
        
    return req_id, text

def print_results(req_id, text, results):
    """결과 출력"""
    if not results: return

    table_data = []
    total_score = 0
    
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"

    for slot in IR_SLOTS:
        data = results.get(slot, {"score": 0, "reason": "N/A"})
        score = data['score']
        reason = data['reason']
        total_score += score
        
        if score >= 4: s_disp = f"{GREEN}{score}{RESET}"
        elif score >= 3: s_disp = f"{YELLOW}{score}{RESET}"
        else: s_disp = f"{RED}{score}{RESET}"
            
        table_data.append([slot, s_disp, reason])

    print("-" * 80)
    print(tabulate(table_data, headers=["IR Slot", "Score", "Reason"], tablefmt="simple"))
    print("-" * 80)
    print(f"📈 평균 점수: {total_score/len(IR_SLOTS):.2f} / 5.0")
    print("="*80 + "\n")

# --- 메인 실행 ---
if __name__ == "__main__":
    print(f"📂 '{FILENAME}' 파일을 로드합니다...")
    requirements = load_requirements(FILENAME)
    
    if not requirements:
        print("평가할 데이터가 없습니다.")
        exit()

    print(f"✅ 총 {len(requirements)}개의 요구사항을 찾았습니다.\n")
    
    # Mistral 모델로 초기화
    evaluator = RequirementEvaluator(model_name=MODEL_NAME)

    for idx, item in enumerate(requirements):
        r_id, r_text = extract_text_and_id(item, idx)
        
        if not r_text:
            continue

        print(f"\n{'='*80}")
        print(f"📌 [처리 중] Index {idx+1} / {len(requirements)}")
        
        # [수정됨] 입력받은 JSON 데이터(Raw) 출력
        print(f"📥 [입력 데이터 확인]:")
        # JSON을 보기 좋게 정렬하여 출력 (한글 깨짐 방지)
        print(json.dumps(item.get("raw_text", item), indent=2, ensure_ascii=False))
        # print("-" * 80)

        # 평가 수행
        print(f"   ⏳ Mistral 분석 시작...")
        results = evaluator.evaluate(r_id, r_text)
        
        # 결과 출력
        print_results(r_id, r_text, results)