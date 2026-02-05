import json
import yaml
import os
import re
import requests
from typing import List, Dict, Any

# =========================================================
# 0. Configuration
# =========================================================

DATA_FILE = "./data/FuSaReq_new_augmented.json"
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

# LLM에게 지시할 스키마 (추출용)
MRS_SCHEMA = """
- req_id: Requirement ID
- anchor: The subject component/system (Who) - can be a list
- action: The main action performed (What) - can be a list
- action_kind: Type of action (e.g., detect, mitigate, transition)
- when: Condition or trigger (When)
- constraints: Performance limits (e.g., within 200ms)
- verification: How to verify (e.g., Test, Inspection)
- acceptance_criteria: Pass/Fail criteria
- why: Rationale or intent (Why)
"""

# =========================================================
# Helper Functions
# =========================================================

def safe_str(val):
    """리스트나 None을 안전하게 문자열로 변환 (출력 및 비교용)"""
    if val is None:
        return "-"
    if isinstance(val, list):
        # 리스트 내부의 None 제거 후 문자열 병합
        clean_list = [str(v).strip() for v in val if v]
        return ", ".join(clean_list) if clean_list else "-"
    return str(val).strip()

def safe_lower(val):
    """비교 로직용 소문자 변환"""
    return safe_str(val).lower()

# =========================================================
# 1. Step 1: MRS Extraction (LLM)
# =========================================================

def call_ollama(prompt: str, system_msg: str = "") -> str:
    payload = {
        "model": MODEL_NAME, "prompt": prompt, "system": system_msg,
        "stream": False, "format": "json"
    }
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        print(f"Error calling Ollama: {e}")
        return "{}"

def extract_mrs_from_reqs(reqs: List[Dict]) -> List[Dict]:
    extracted_data = []
    print(f"--- Step 1: Extracting MRS from {len(reqs)} requirements ---")

    for req in reqs:
        req_text = req.get('raw_text', '')
        req_id = req.get('req_id', 'UNKNOWN')
        
        system_prompt = "You are a functional safety expert. Extract MRS fields from the requirement text into JSON format."
        user_prompt = f"""
        Extract MRS fields based on:
        {MRS_SCHEMA}

        Requirement: "{req_text}"

        Return JSON. Keys: req_id, anchor, action, action_kind, when, constraints, verification, acceptance_criteria, why.
        If missing, use null. Ensure 'req_id' is "{req_id}".
        """
        
        print(f"Processing {req_id}...")
        response_json = call_ollama(user_prompt, system_prompt)
        
        try:
            mrs_obj = json.loads(response_json)
            mrs_obj['raw_text'] = req_text
            if 'req_id' not in mrs_obj: mrs_obj['req_id'] = req_id
            extracted_data.append(mrs_obj)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON for {req_id}")

    return extracted_data

# =========================================================
# 2. Step 2: Rule Engine (Full Implementation)
# =========================================================

def detect_issues(mrs_data: List[Dict]) -> List[Dict]:
    print(f"--- Step 2: Running Rule Engine on {len(mrs_data)} profiles ---")
    issues = []

    def parse_time(val):
        match = re.search(r'(\d+)\s*(ms|s|sec)', str(val))
        if match:
            num, unit = match.groups()
            return float(num) * (1000 if 's' in unit and 'ms' not in unit else 1)
        return None

    grouped_by_aa = {} 
    all_profiles = mrs_data 

    for item in mrs_data:
        # [S-01] Structural Check
        if not item.get('when'):
             issues.append({
                "rule_id": "S-01", "type": "EngineHealthIssue", "issue_type": "condition_not_structured",
                "req_ids": [item.get('req_id')], "details": "Missing 'When' condition."
            })

        # [S-02] Why without Anchor
        if item.get('why') and not item.get('anchor'):
            issues.append({
                "rule_id": "S-02", "type": "CatalogIntegrityIssue", "issue_type": "why_without_anchor",
                "req_ids": [item.get('req_id')], "details": f"Rationale exists but Anchor is missing."
            })

        # Grouping Logic
        a_key = safe_lower(item.get('anchor'))
        act_key = safe_lower(item.get('action'))
        group_key = f"{a_key}|{act_key}"
        if group_key not in grouped_by_aa: grouped_by_aa[group_key] = []
        grouped_by_aa[group_key].append(item)

    # Within AnchorAction Logic
    for key, items in grouped_by_aa.items():
        if len(items) < 2: continue

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                rec_a, rec_b = items[i], items[j]
                
                when_a, when_b = safe_lower(rec_a.get('when')), safe_lower(rec_b.get('when'))
                const_a, const_b = safe_lower(rec_a.get('constraints')), safe_lower(rec_b.get('constraints'))
                how_a, how_b = safe_lower(rec_a.get('action_kind')), safe_lower(rec_b.get('action_kind'))

                is_same_when = (when_a != "-" and when_b != "-" and when_a == when_b)
                
                if is_same_when:
                    issues.append({
                        "rule_id": "W-02", "type": "WithinAnchorActionWhenIssue", "issue_type": "duplicate_when",
                        "req_ids": [rec_a['req_id'], rec_b['req_id']], "details": f"Duplicate condition '{when_a}'."
                    })

                if is_same_when and const_a != "-" and const_b != "-" and const_a != const_b:
                    issues.append({
                        "rule_id": "C-01", "type": "ConstraintConflictIssue", "issue_type": "incompatible_constraints",
                        "req_ids": [rec_a['req_id'], rec_b['req_id']], "details": f"Constraint mismatch: '{const_a}' vs '{const_b}'."
                    })

                # [C-02] FTTI Check
                time_a, time_b = parse_time(const_a), parse_time(const_b)
                if is_same_when and time_a and time_b and time_a != time_b:
                     issues.append({
                        "rule_id": "C-02", "type": "ConstraintConflictIssue", "issue_type": "inconsistent_ftti",
                        "req_ids": [rec_a['req_id'], rec_b['req_id']], "details": f"FTTI mismatch: {time_a}ms vs {time_b}ms."
                    })

                if how_a != "-" and how_b != "-" and how_a != how_b:
                     issues.append({
                        "rule_id": "H-01", "type": "HowTypeMismatchIssue", "issue_type": "howtype_divergence",
                        "req_ids": [rec_a['req_id'], rec_b['req_id']], "details": f"Action types differ: '{how_a}' vs '{how_b}'."
                    })

    # Cross Anchor Logic
    for i in range(len(all_profiles)):
        for j in range(i + 1, len(all_profiles)):
            rec_a, rec_b = all_profiles[i], all_profiles[j]
            
            ank_a, ank_b = safe_lower(rec_a.get('anchor')), safe_lower(rec_b.get('anchor'))
            if ank_a == ank_b: continue 

            act_a, act_b = safe_lower(rec_a.get('action')), safe_lower(rec_b.get('action'))
            when_a, when_b = safe_lower(rec_a.get('when')), safe_lower(rec_b.get('when'))

            is_same_when = (when_a == when_b) and when_a != "-"
            
            # [X-01] Duplication
            if act_a == act_b and act_a != "-":
                issues.append({
                    "rule_id": "X-01", "type": "CrossAnchorOverlapIssue", "issue_type": "duplication",
                    "req_ids": [rec_a['req_id'], rec_b['req_id']], "details": f"Anchors '{ank_a}' and '{ank_b}' perform identical action '{act_a}'."
                })

            # [X-03] Contradiction
            if is_same_when:
                pairs = [("open", "close"), ("start", "stop"), ("enable", "disable")]
                for p1, p2 in pairs:
                    if (p1 in act_a and p2 in act_b) or (p2 in act_a and p1 in act_b):
                        issues.append({
                            "rule_id": "X-03", "type": "CrossAnchorOverlapIssue", "issue_type": "potential_conflict",
                            "req_ids": [rec_a['req_id'], rec_b['req_id']], "details": f"CONFLICT: '{ank_a}' does '{act_a}' vs '{ank_b}' does '{act_b}'."
                        })
                        break
    return issues

# =========================================================
# 3. Step 3: Reporting & Visualization (DEFINED HERE)
# =========================================================

def generate_report(issues: List[Dict]) -> str:
    print(f"--- Step 3: Generating Analysis Report ---")
    if not issues: return "No significant issues found."

    issues_summary = json.dumps(issues, indent=2)
    system_prompt = "You are a Functional Safety QA assistant. Report issues clearly."
    user_prompt = f"""
    Issues detected:
    {issues_summary}

    Generate a professional markdown report.
    - Group by issue type.
    - Explain the risk.
    - Suggest resolutions.
    """
    return call_ollama(user_prompt, system_prompt)

def format_mrs_table(mrs_data: List[Dict]) -> str:
    """MRS 데이터를 마크다운 표 형식으로 변환"""
    print(f"--- Step 4: Formatting MRS Data Table ---")
    
    # Table Header
    md = "\n## 📊 Extracted MRS Data\n\n"
    md += "| Req ID | Anchor | Action | When | Constraints | Verification |\n"
    md += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    
    # Table Rows
    for item in mrs_data:
        req_id = safe_str(item.get('req_id'))
        anchor = safe_str(item.get('anchor'))
        action = safe_str(item.get('action'))
        when = safe_str(item.get('when'))
        constraints = safe_str(item.get('constraints'))
        verification = safe_str(item.get('verification'))
        
        # 표 깨짐 방지
        row = [req_id, anchor, action, when, constraints, verification]
        row = [r.replace("|", "/") for r in row]
        
        md += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} |\n"
    
    md += "\n> **Note**: 'Anchor' and 'Action' fields may contain multiple values separated by commas.\n"
    return md

# =========================================================
# Main Execution
# =========================================================

def main():
    if not os.path.exists(DATA_FILE):
        print(f"Error: Data file not found at {DATA_FILE}")
        return

    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
        reqs = data if isinstance(data, list) else data.get('requirements', [])

    # 1. MRS Extraction
    mrs_data = extract_mrs_from_reqs(reqs)
    
    # 2. Rule Engine
    issues = detect_issues(mrs_data)

    # 3. Generate Analysis Report (LLM)
    analysis_text = generate_report(issues)

    # 4. Append MRS Data Table (Python) - 함수가 위에서 정의되었으므로 이제 정상 작동
    mrs_table_text = format_mrs_table(mrs_data)
    
    final_document = analysis_text + "\n\n" + "-"*40 + "\n" + mrs_table_text

    print("\n================ FINAL OUTPUT ================\n")
    print(final_document)
    
    with open("analysis_report_v2.md", "w", encoding='utf-8') as f:
        f.write(final_document)
    print(f"\n💾 Report saved to 'analysis_report_v2.md'")

if __name__ == "__main__":
    main()