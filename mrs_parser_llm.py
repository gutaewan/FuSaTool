import json
import os
import glob
import requests
from typing import Dict, Any, List

# =========================================================
# 1. Configuration
# =========================================================

PROMPT_DIR = "./prompt"
DATA_DIR = "./data"
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

# 일관성 검증 설정
NUM_TRIALS = 2       # 동일한 질문 반복 횟수
TEMPERATURE = 0.1    # 0.0에 가까운 낮은 온도로 일관성 유지

PROMPT_FILES = {
    "system": "system_prompt.txt",
    "dev_tool": "dev_tool_prompt.txt",
    "user": "user_prompt.txt"
}

# =========================================================
# 2. Prompt Manager (Enhanced)
# =========================================================
class PromptManager:
    def __init__(self, prompt_dir: str):
        self.prompt_dir = prompt_dir
        self.prompts = {}
        self._ensure_prompt_dir()

    def _ensure_prompt_dir(self):
        if not os.path.exists(self.prompt_dir):
            os.makedirs(self.prompt_dir)
        # 항상 최신 프롬프트 내용으로 덮어쓰기 (수정 사항 반영을 위해)
        self._create_enhanced_prompts()

    def _create_enhanced_prompts(self):
        """
        LLM이 결손(Missing)을 잘 분석하도록 예시가 포함된 프롬프트 생성
        """
        # 1. System Prompt
        sys_content = """You are an expert Requirements Engineer specialized in ISO 26262.
Your task is to analyze automotive requirements and structure them according to the Meta Requirement Schema (MRS).
You must output ONLY valid JSON."""
        
        with open(os.path.join(self.prompt_dir, PROMPT_FILES["system"]), "w", encoding="utf-8") as f:
            f.write(sys_content)

        # 2. Dev Tool Prompt (규칙 + 예시)
        dev_content = """
### MRS DEFINITION ###
Slots: Anchor, What, When, Constraints, Verification, AcceptanceCriteria, Why, HowType.

### MRS TYPE RULES ###
1. T6_VerificationCentric: Verification AND AcceptanceCriteria present.
2. T5_ConstraintCentric: Constraints present.
3. T4_WhenCentric: When present.
4. T3_HowTypeCentric: HowType present.
5. T2_WhatCentric: What AND Anchor present.
6. T1_WhyCentric: Only Why present.

### EXAMPLES ###

Input: "To prevent fire, the BMS shall stop charging."
Output:
{
  "mrs_type": "T2_WhatCentric",
  "slots": {
    "Why": "To prevent fire",
    "Anchor": "BMS",
    "What": "shall stop charging",
    "When": "ABSENT",
    "Constraints": "ABSENT",
    "Verification": "ABSENT",
    "AcceptanceCriteria": "ABSENT"
  },
  "missing_analysis": [
    "Constraints are missing (Recommended for safety)",
    "Verification is missing"
  ]
}

Input: "The System shall be tested by inspection."
Output:
{
  "mrs_type": "T6_VerificationCentric",
  "slots": {
    "Anchor": "System",
    "What": "shall be tested",
    "Verification": "by inspection",
    "AcceptanceCriteria": "ABSENT"
  },
  "missing_analysis": [
    "AcceptanceCriteria is missing for Verification"
  ]
}
"""
        with open(os.path.join(self.prompt_dir, PROMPT_FILES["dev_tool"]), "w", encoding="utf-8") as f:
            f.write(dev_content)

        # 3. User Prompt
        user_content = """
### TASK ###
Analyze the following requirement.
Output JSON format with 'mrs_type', 'slots', and 'missing_analysis'.

Target Requirement:
"""
        with open(os.path.join(self.prompt_dir, PROMPT_FILES["user"]), "w", encoding="utf-8") as f:
            f.write(user_content)

    def load_prompts(self):
        with open(os.path.join(self.prompt_dir, PROMPT_FILES["system"]), "r", encoding="utf-8") as f:
            self.prompts["system"] = f.read().strip()
        with open(os.path.join(self.prompt_dir, PROMPT_FILES["dev_tool"]), "r", encoding="utf-8") as f:
            self.prompts["dev_tool"] = f.read().strip()
        with open(os.path.join(self.prompt_dir, PROMPT_FILES["user"]), "r", encoding="utf-8") as f:
            self.prompts["user"] = f.read().strip()

    def get_full_prompt(self, req_text: str) -> str:
        return f"{self.prompts['dev_tool']}\n\n{self.prompts['user']}\n\"{req_text}\"\n\nOutput JSON:"

# =========================================================
# 3. Consistency Processor
# =========================================================

class MRSConsistencyParser:
    def __init__(self):
        self.pm = PromptManager(PROMPT_DIR)
        self.pm.load_prompts()

    def _call_llm(self, req_id: str, full_prompt: str, system_msg: str) -> Dict[str, Any]:
        payload = {
            "model": MODEL_NAME,
            "system": system_msg,
            "prompt": full_prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": TEMPERATURE, "num_ctx": 4096}
        }
        try:
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
            response.raise_for_status()
            return json.loads(response.json().get('response', '{}'))
        except Exception as e:
            print(f"    ⚠️ Call failed: {e}")
            return {}

    def _compare_results(self, r1: Dict, r2: Dict) -> bool:
        if not r1 or not r2: return False
        if r1.get("mrs_type") != r2.get("mrs_type"): return False
        
        s1 = r1.get("slots", {})
        s2 = r2.get("slots", {})
        
        # 키 집합만 같으면 값은 약간 달라도 넘어갈지, 값도 같아야 할지 결정
        # 여기서는 값도 느슨하게 비교 (공백/대소문자 무시)
        all_keys = set(s1.keys()) | set(s2.keys())
        for k in all_keys:
            v1 = str(s1.get(k, "")).strip().lower()
            v2 = str(s2.get(k, "")).strip().lower()
            if v1 in ["none", "absent", "null", ""] and v2 in ["none", "absent", "null", ""]:
                continue
            if v1 != v2: return False
        return True

    def parse(self, item: Dict[str, Any]) -> Dict[str, Any]:
        req_id = item.get('req_id', item.get('id', 'N/A'))
        raw_text = item.get('raw_text', '')

        system_msg = self.pm.prompts["system"]
        full_prompt = self.pm.get_full_prompt(raw_text)

        print(f"\n🔸 Processing [{req_id}] (Consistency Check x{NUM_TRIALS})...")
        
        res1 = self._call_llm(req_id, full_prompt, system_msg)
        print(f"    Attempt 1: {res1.get('mrs_type', 'Fail')}")
        
        res2 = self._call_llm(req_id, full_prompt, system_msg)
        print(f"    Attempt 2: {res2.get('mrs_type', 'Fail')}")
        
        is_consistent = self._compare_results(res1, res2)
        final_status = "CONFIRMED" if is_consistent else "INCONSISTENT"
        final_result = res1 if res1 else res2
        
        return {
            "id": req_id,
            "raw_text": raw_text,
            "status": final_status,
            "consistency_match": is_consistent,
            "trials": [res1, res2],
            "final_result": final_result
        }

# =========================================================
# 4. Main Execution
# =========================================================

def run_consistency_parser():
    parser = MRSConsistencyParser()

    items = []
    json_files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    if not json_files and os.path.exists("FuSaReq_new_augmented.json"):
        json_files = ["FuSaReq_new_augmented.json"]

    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                content = json.load(f)
                if isinstance(content, list): items.extend(content)
                elif isinstance(content, dict) and 'requirements' in content: items.extend(content['requirements'])
        except: pass

    print(f"\n🚀 [MRS Consistency Parser]")
    print(f"   Model: {MODEL_NAME}")
    print(f"   Total Requirements: {len(items)}")

    results_summary = {"CONFIRMED": 0, "INCONSISTENT": 0}

    for idx, item in enumerate(items, 1):
        out = parser.parse(item)
        
        print("-" * 80)
        status_icon = "✅" if out['status'] == "CONFIRMED" else "⚠️"
        print(f"{status_icon} Result: {out['status']}")
        
        res = out['final_result']
        if res:
            mrs_type = res.get('mrs_type', 'Unknown')
            slots = res.get('slots', {})
            missing = res.get('missing_analysis', []) # [NEW] 결손 정보 가져오기
            
            print(f"   🧠 MRS Type: {mrs_type}")
            
            # 1) Detected Content 출력
            active_content = []
            for k, v in slots.items():
                if v and str(v).strip().upper() not in ["NONE", "ABSENT", "NULL", ""]:
                    active_content.append(f"{k}: \"{v}\"")
            
            if active_content:
                print(f"   📝 Detected Content:")
                for content in active_content:
                    print(f"      - {content}")
            else:
                print(f"      (No valid slots extracted)")

            # 2) Missing Analysis 출력 [추가된 부분]
            if missing:
                print(f"   🚫 Missing Analysis:")
                for m in missing:
                    print(f"      - {m}")
            else:
                print(f"   ✨ No Missing Parts Detected")

            # 3) 불일치 시 상세 정보
            if out['status'] == "INCONSISTENT":
                t1 = out['trials'][0].get('mrs_type')
                t2 = out['trials'][1].get('mrs_type')
                print(f"   ❌ Mismatch Details:")
                print(f"      Try 1: {t1}")
                print(f"      Try 2: {t2}")
        
        results_summary[out['status']] += 1

    print("\n" + "="*80)
    print(f"📈 Final Summary")
    print(f"   Total: {len(items)}")
    print(f"   ✅ Confirmed: {results_summary['CONFIRMED']}")
    print(f"   ⚠️  Inconsistent: {results_summary['INCONSISTENT']}")
    print("="*80)

if __name__ == "__main__":
    run_consistency_parser()