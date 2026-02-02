import pandas as pd
from langchain_community.llms import Ollama

IR_SLOTS = ["Why", "What", "How type", "When", "Constraints", "Verification", "Acceptance criteria", "Anchors", "Goal"]

class RequirementGenerator:
    def __init__(self, model_name="llama3"):
        self.model_name = model_name

    def _get_missing_slots(self, row):
        """행 데이터에서 비어있는 IR Slot(결손부) 식별"""
        missing = []
        for slot in IR_SLOTS:
            val = row.get(slot)
            if not val or str(val).lower() in ["none", "nan", "", "-", "unknown"]:
                missing.append(slot)
        return missing

    def _find_context(self, current_row, missing_slots, full_df):
        """[전략 1] 동일 제어기 내에서 결손부 문맥 검색"""
        context = {}
        my_controller = current_row.get("_controller", "")
        if not my_controller:
            return {}

        relevant_df = full_df[full_df["_controller"].astype(str).str.contains(my_controller, regex=False, na=False)]

        for slot in missing_slots:
            valid_vals = relevant_df[
                relevant_df[slot].notna() & 
                (relevant_df[slot].astype(str).str.len() > 1) &
                (relevant_df["ID"] != current_row["ID"])
            ][slot].unique()
            
            if len(valid_vals) > 0:
                context[slot] = list(valid_vals[:3])
                
        return context

    def generate_suggestion(self, current_row, target_level, full_df):
        """
        요구사항 제안 생성 (각 축별 보완 사항 명시)
        """
        # 1. 결손부 파악
        missing_slots = self._get_missing_slots(current_row)
        
        if not missing_slots:
            return {
                "status": "skipped",
                "message": "이미 모든 축(IR Slots)의 정보가 포함되어 있습니다.",
                "suggestion": None
            }

        # 2. [전략 1] 동일 제어기 내 문맥 검색
        found_context = self._find_context(current_row, missing_slots, full_df)

        # 3. 프롬프트 구성 (분석적 제안 유도)
        missing_slots_str = ", ".join(missing_slots)

        if found_context:
            # --- 전략 1: 문맥 기반 채우기 ---
            context_str = "\n".join([f"- {k} (참조): {v}" for k, v in found_context.items()])
            strategy_msg = "동일 제어기 내 유사 정보를 바탕으로 결손 축을 보완합니다."
            
            prompt = f"""
            당신은 기능안전 요구사항(ISO 26262) 전문가입니다.
            현재 요구사항은 다음 축(IR Slots)에 대한 정보가 누락되어 있습니다: [{missing_slots_str}]
            
            [목표]: 
            1. 누락된 축에 대해 제공된 [참조 정보]를 활용하여 내용을 보완하세요.
            2. Level {target_level} 수준의 명확하고 검증 가능한 문장으로 재작성하세요.
            
            [입력 정보]:
            - 원본 텍스트: "{current_row.get('Requirement', '')}"
            - 참조 정보 (Context):
            {context_str}
            
            [출력 형식 (반드시 지킬 것)]:
            1. **[보완 분석]**: 각 누락된 축({missing_slots_str})별로 어떤 내용을 추가했는지 설명하세요.
            2. **[제안된 요구사항]**: 최종적으로 완성된 요구사항 문장 (한국어).
            
            [주의사항]:
            - [참조 정보]에 없는 내용은 절대 창작하지 마세요.
            - 출력은 반드시 **한국어(Korean)**로 작성하세요.
            """
        else:
            # --- 전략 2: 가이드 제공 ---
            strategy_msg = "참조 정보가 없어, 각 축별로 필요한 정보를 가이드합니다."
            
            prompt = f"""
            당신은 기능안전 요구사항(ISO 26262) 전문가입니다.
            현재 요구사항은 다음 축(IR Slots)에 대한 정보가 누락되어 있습니다: [{missing_slots_str}]
            하지만 참조할만한 문맥 정보가 없습니다.
            
            [목표]: 
            1. 각 누락된 축({missing_slots_str})에 대해, Level {target_level} 달성을 위해 어떤 정보가 구체화되어야 하는지 제안하세요.
            2. 사용자가 내용을 채울 수 있도록 Placeholder(<...>)가 포함된 템플릿 문장을 작성하세요.
            
            [입력 정보]:
            - 원본 텍스트: "{current_row.get('Requirement', '')}"
            
            [출력 형식 (반드시 지킬 것)]:
            1. **[보완 분석]**: 각 누락된 축별로 어떤 구체적 정보(예: 시간값, 신호명 등)가 필요한지 조언하세요.
            2. **[제안된 템플릿]**: 꺽쇠 괄호(<...>)를 사용하여 사용자가 채워야 할 부분을 표시한 문장 (한국어).
            
            [주의사항]:
            - 내용을 임의로 창작하지 말고 가이드만 제공하세요.
            - 출력은 반드시 **한국어(Korean)**로 작성하세요.
            """

        # 4. LLM 호출
        try:
            llm = Ollama(model=self.model_name)
            response = llm.invoke(prompt)
            
            if len(response.strip()) < 5:
                return {"status": "error", "message": "LLM 응답 오류", "suggestion": None}

            return {
                "status": "success",
                "message": strategy_msg,
                "suggestion": response.strip(),
                "missing_slots": missing_slots
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"LLM Error: {str(e)}",
                "suggestion": None
            }