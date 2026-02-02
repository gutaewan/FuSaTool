import json
import re
import os
import textwrap
from langchain_community.llms import Ollama
from tabulate import tabulate
from langchain_ollama import OllamaLLM

# ==============================================================================
# [설정]
FILENAME = "FuSaReq01.json" 
MODEL_NAME = "mistral"
# MODEL_NAME = "Ollama"          
# ==============================================================================

# [핵심 변경] 단순 리스트가 아니라, 각 Slot별 상세 평가 기준을 정의합니다.
IR_DEFINITIONS = {
    "Why": "The rationale or justification for the requirement. Does it explain 'Why' this function is needed for safety? (e.g., linked to Safety Goal)",
    "What": "The core function or action. Does it clearly describe 'What' the system shall do? (Subject + Action Verb)",
    "How type": "Qualitative or quantitative attributes of the action. Does it describe the 'manner' of operation? (e.g., forcefully, gradually, visually)",
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
        print(f"🤖 LLM 모델({model_name}) 로딩 중...")
        self.llm = Ollama(model=model_name)

    def clean_json_string(self, json_str):
        json_str = re.sub(r'```json\s*', '', json_str)
        json_str = re.sub(r'```\s*$', '', json_str)
        return json_str.strip()

    def evaluate(self, req_id, requirement_text):
        
        # [핵심 변경] 딕셔너리를 프롬프트에 넣기 좋은 문자열로 변환
        definitions_text = "\n".join([f"- {key}: {desc}" for key, desc in IR_DEFINITIONS.items()])

        prompt = f"""
        You are an Expert Requirements Engineer based on ISO 26262.
        
        Analyze the following requirement based on the 9 IR Slots defined below.
        You MUST follow the specific definitions provided for each slot to assign a score.
        You should provide the answer in Korean for every requirement and every slot.
        
        [Evaluation Rubric (Definitions)]:
        {definitions_text}

        [Scoring Criteria (1-5)]:
        1: Missing (The slot information is completely absent)
        2: Vague (Mentioned but very ambiguous or abstract)
        3: Average (Understandable but lacks specific details/values)
        4: Good (Clear, specific, and unambiguous)
        5: Excellent (Perfectly defined, quantified with tolerances where applicable)

        [Target Requirement]:
        ID: {req_id}
        Text: "{requirement_text}"

        [Output Format]:
        Output ONLY a valid JSON object. Do not explain outside the JSON.
        You must give the answer in Korean for every requirement and every slot.
        Keys must be exactly: {", ".join(IR_SLOTS)}
        
        Example:
        {{
            "Why": {{"score": 1, "reason": "No safety rationale or justification provided."}},
            "Constraints": {{"score": 5, "reason": "Specific timing constraint (500ms) is clearly defined."}}
        }}
        """

        try:
            response = self.llm.invoke(prompt)
            cleaned_response = self.clean_json_string(response)
            return json.loads(cleaned_response)
        except Exception as e:
            print(f"   ❌ 평가 실패 ({req_id}): {e}")
            return None

def load_requirements(filename):
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
    req_id = item.get("id") or item.get("req_id") or item.get("ID") or f"REQ_{index+1}"
    text = item.get("text") or item.get("requirement") or item.get("description") or item.get("raw_text")
    if isinstance(item, str):
        text = item
        req_id = f"REQ_{index+1}"
    return req_id, text

def print_results(req_id, text, results):
    if not results: return

    table_data = []
    total_score = 0
    
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"

    for slot in IR_SLOTS:
        data = results.get(slot, {"score": 0, "reason": "N/A"})
        score = data['score']
        reason = data['reason']
        total_score += score
        
        if score >= 4: s_disp = f"{GREEN}{score}{RESET}"
        elif score >= 3: s_disp = f"{YELLOW}{score}{RESET}"
        else: s_disp = f"{RED}{score}{RESET}"
        
        wrapped_reason = "\n".join(textwrap.wrap(reason, width=60))
        table_data.append([slot, s_disp, wrapped_reason])

    print("\n" + "="*80)
    print(f"📄 {BOLD}요구사항 원문 분석 결과{RESET}")
    print("="*80)
    print(f"🆔 {CYAN}ID:{RESET} {req_id}")
    print(f"📝 {CYAN}Text:{RESET}\n")
    print(f"   \"{text}\"")
    print("-" * 80)
    print(tabulate(table_data, headers=["IR Slot", "Score", "Evaluation Reason"], tablefmt="grid"))
    
    avg_score = total_score / len(IR_SLOTS)
    print(f"\n📈 {BOLD}종합 평균 점수: {avg_score:.2f} / 5.0{RESET}")
    print("="*80 + "\n")

# --- 메인 실행 ---
if __name__ == "__main__":
    print(f"📂 '{FILENAME}' 로드 중...")
    requirements = load_requirements(FILENAME)
    
    if not requirements:
        print("데이터 없음.")
        exit()

    evaluator = RequirementEvaluator(model_name=MODEL_NAME)

    for idx, item in enumerate(requirements):
        r_id, r_text = extract_text_and_id(item, idx)
        
        if not r_text:
            continue

        print(f"\n🔄 [Progress]: {idx+1}/{len(requirements)} 분석 중...")
        # 원본 데이터는 너무 길면 생략 가능, 필요시 주석 해제
        # print(f"📥 [Raw Input]: {json.dumps(item, ensure_ascii=False)}")
        
        results = evaluator.evaluate(r_id, r_text)
        print_results(r_id, r_text, results)