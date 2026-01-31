import pandas as pd
import random

# 분석해야 할 IR Slot 정의
IR_SLOTS = [
    "Why", "What", "How type", "When", 
    "Constraints", "Verification", "Acceptance criteria", "Anchors", "Goal"
]

# (테스트용) 가상의 차종 및 제어기 목록
MOCK_VEHICLES = ["IONIQ5", "EV6", "GV60", "SantaFe_HEV"]
MOCK_CONTROLLERS = ["VCU", "BMS", "MCU", "ICU", "ADAS"]

class RequirementClassifier:
    def __init__(self, use_llm=False):
        self.use_llm = use_llm

    def is_already_classified(self, req_data):
        """데이터가 이미 IR Slot 키를 가지고 있는지 확인"""
        if not isinstance(req_data, dict):
            return False
        keys = req_data.keys()
        for slot in IR_SLOTS:
            if slot in keys:
                return True
        return False

    def mock_llm_classify(self, text):
        """Mock LLM: IR Slot 분류 + 메타데이터(차종/제어기) 생성"""
        result = {}
        for slot in IR_SLOTS:
            # 70% 확률로 데이터 존재 시뮬레이션
            result[slot] = f"Content for {slot}" if random.random() > 0.3 else None
        
        result["original_text"] = text
        return result

    def analyze_list(self, requirements_list):
        """리스트 전체 분석 및 메타데이터 보정"""
        analyzed_results = []
        
        for req in requirements_list:
            processed_req = {}
            
            # 1. IR Slot 분석 (기존 로직 유지)
            if self.is_already_classified(req):
                processed_req = req.copy()
                for slot in IR_SLOTS:
                    if slot not in processed_req:
                        processed_req[slot] = None
            elif self.use_llm:
                text = req if isinstance(req, str) else str(req)
                processed_req = self.mock_llm_classify(text)
            else:
                processed_req = {slot: None for slot in IR_SLOTS}
                processed_req["original_text"] = str(req)

            # 2. [추가] 차종(Vehicle) 및 제어기(Controller) 필드 확인 및 보정
            # 실제 데이터에 없으면 테스트를 위해 랜덤 할당 (실전에서는 'Unknown' 처리 추천)
            if "Vehicle" not in processed_req:
                processed_req["Vehicle"] = random.choice(MOCK_VEHICLES)
            if "Controller" not in processed_req:
                processed_req["Controller"] = random.choice(MOCK_CONTROLLERS)
            
            # 3. ID 부여 (식별용)
            if "ID" not in processed_req:
                processed_req["ID"] = f"REQ-{random.randint(1000, 9999)}"

            analyzed_results.append(processed_req)
                
        return analyzed_results