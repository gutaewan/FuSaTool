import os
import time
import requests
from typing import Any, Dict, Optional

API_BASE = os.getenv("API_BASE", "http://localhost:8000/api/v1")
USE_MOCK = os.getenv("USE_MOCK", "1") == "1"

def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def _post(path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{API_BASE}{path}", json=json_body, timeout=30)
    r.raise_for_status()
    return r.json()

# ---- API wrappers (OpenAPI와 1:1 매핑) ----

def get_readiness_cards(dataset_id: str, version_id: str) -> Dict[str, Any]:
    return _get("/metrics/readiness-cards", {"dataset_id": dataset_id, "version_id": version_id})

def get_heatmap(dataset_id: str, version_id: str, group_by: str, metric: str) -> Dict[str, Any]:
    return _get("/metrics/heatmap", {"dataset_id": dataset_id, "version_id": version_id, "group_by": group_by, "metric": metric})

def get_scatter(dataset_id: str, version_id: str, group_by: str) -> Dict[str, Any]:
    return _get("/metrics/scatter", {"dataset_id": dataset_id, "version_id": version_id, "group_by": group_by})

def list_requirements(dataset_id: str, version_id: str, search: str = "", sort: str = "underspec_desc") -> Dict[str, Any]:
    return _get("/requirements", {"dataset_id": dataset_id, "version_id": version_id, "search": search, "sort": sort})

def get_requirement(req_id: str, dataset_id: str, version_id: str) -> Dict[str, Any]:
    return _get(f"/requirements/{req_id}", {"dataset_id": dataset_id, "version_id": version_id})

def get_requirement_ir(req_id: str, version_id: str) -> Dict[str, Any]:
    return _get(f"/requirements/{req_id}/ir", {"version_id": version_id})

def get_requirement_scores(req_id: str, version_id: str) -> Dict[str, Any]:
    return _get(f"/requirements/{req_id}/scores", {"version_id": version_id})

def get_similar(req_id: str, dataset_id: str, version_id: str) -> Dict[str, Any]:
    return _get(f"/requirements/{req_id}/similar", {"dataset_id": dataset_id, "version_id": version_id})

def create_suggestions_job(req_id: str, dataset_id: str, version_id: str, policy_profile_id: str, nfr_priority: list[str]) -> Dict[str, Any]:
    body = {
        "dataset_id": dataset_id,
        "version_id": version_id,
        "policy_profile_id": policy_profile_id,
        "nfr_priority": nfr_priority,
    }
    return _post(f"/requirements/{req_id}/suggestions", body)

def get_job(job_id: str) -> Dict[str, Any]:
    return _get(f"/jobs/{job_id}", {})

def get_suggestions_result(req_id: str, job_id: str) -> Dict[str, Any]:
    return _get(f"/requirements/{req_id}/suggestions/result", {"job_id": job_id})