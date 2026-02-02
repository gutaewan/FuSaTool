import pandas as pd
import random

IR_SLOTS = ["Why", "What", "How type", "When", "Constraints", "Verification", "Acceptance criteria", "Anchors", "Goal"]

class RequirementClassifier:
    def __init__(self, use_llm=False):
        self.use_llm = use_llm

    def is_already_classified(self, req_data):
        if not isinstance(req_data, dict): return False
        for slot in IR_SLOTS:
            if slot in req_data: return True
        return False

    def mock_llm_classify(self, text):
        result = {}
        for slot in IR_SLOTS:
            result[slot] = f"Content" if random.random() > 0.3 else None
        result["original_text"] = text
        return result

    def _ensure_list(self, value):
        if value is None: return []
        if isinstance(value, list): return value
        return [str(value)]

    def _deep_search(self, data, target_keys):
        if not isinstance(data, dict): return None
        target_keys_lower = {k.lower() for k in target_keys}
        
        # 1. 현재 레벨
        for k, v in data.items():
            if k.lower() in target_keys_lower:
                if v is not None and v != "": return v
        
        # 2. 하위 레벨
        for k, v in data.items():
            if isinstance(v, dict):
                found = self._deep_search(v, target_keys)
                if found: return found
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        found = self._deep_search(item, target_keys)
                        if found: return found
        return None

    def analyze_list(self, requirements_list):
        analyzed_results = []
        
        for req in requirements_list:
            processed_req = {}
            if isinstance(req, dict):
                processed_req = req.copy()
            else:
                processed_req = {"original_text": str(req)}

            # IR Slot (기존 로직)
            if self.use_llm and not self.is_already_classified(req):
                text = req.get("text", str(req)) if isinstance(req, dict) else str(req)
                processed_req.update(self.mock_llm_classify(text))
            else:
                for slot in IR_SLOTS:
                    if slot not in processed_req: processed_req[slot] = None

            # ----------------------------------------------------------
            # 1. 차종 (Vehicle)
            # ----------------------------------------------------------
            raw_v = None
            if "meta" in processed_req and isinstance(processed_req["meta"], dict):
                raw_v = processed_req["meta"].get("vehicle_models")
            if not raw_v:
                raw_v = self._deep_search(processed_req, ["vehicle_models", "vehicle_model", "vehicle"])
            processed_req["Vehicle"] = self._ensure_list(raw_v)
            if not processed_req["Vehicle"]: processed_req["Vehicle"] = ["Unknown"]

            # ----------------------------------------------------------
            # 2. 제어기 (Controller)
            # ----------------------------------------------------------
            raw_c = None
            if "meta" in processed_req and isinstance(processed_req["meta"], dict):
                raw_c = processed_req["meta"].get("component") or processed_req["meta"].get("ecu")
            if not raw_c:
                raw_c = self._deep_search(processed_req, ["component", "components", "ecu", "controller"])
            processed_req["Controller"] = self._ensure_list(raw_c)
            if not processed_req["Controller"]: processed_req["Controller"] = ["Common"]

            # ----------------------------------------------------------
            # [NEW] 3. 레벨 (Standard Granularity Level) 추출
            # ----------------------------------------------------------
            raw_level = self._deep_search(processed_req, ["standard_granularity_level", "granularity_level", "level"])
            processed_req["Level"] = str(raw_level) if raw_level else "Unknown"

            # 4. ID
            raw_id = self._deep_search(processed_req, ["id", "req_id", "ID"])
            processed_req["ID"] = str(raw_id) if raw_id else f"REQ-{random.randint(1000,9999)}"

            analyzed_results.append(processed_req)
                
        return analyzed_results