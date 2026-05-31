"""
문서 버전 관리 (Documentation Version Management)

이 모듈은 프로젝트 문서의 버전 정보를 중앙에서 관리합니다.
각 문서의 버전, 대상 프로젝트 버전, 마지막 업데이트 날짜 등을 추적합니다.

[DOC_VERSION_STANDARD]
- 문서 버전: X.Y.Z (문서 자체의 수정 횟수)
- 대상 프로젝트 버전: X.Y.Z (문서가 설명하는 프로젝트 버전)
- 마지막 업데이트: YYYY-MM-DD
- 상태: active, deprecated, archived
"""
from __future__ import annotations
from typing import Dict, Optional


DOCS_VERSIONS: Dict[str, Dict[str, str]] = {
    "TESTING_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/TESTING_GUIDE.md"
    },
    "ARCHITECTURE_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/ARCHITECTURE_GUIDE.md"
    },
    "DEVELOPMENT_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/DEVELOPMENT_GUIDE.md"
    },
    "PERFORMANCE_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/PERFORMANCE_GUIDE.md"
    },
    "API_REFERENCE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/api/API_REFERENCE.md"
    },
    "PROJECT_OVERVIEW": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/PROJECT_OVERVIEW.md"
    },
    "CI_CD_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/CI_CD_GUIDE.md"
    },
    "DEPLOYMENT_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/DEPLOYMENT_GUIDE.md"
    },
    "TROUBLESHOOTING_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/TROUBLESHOOTING_GUIDE.md"
    },
    "MONITORING_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/MONITORING_GUIDE.md"
    },
    "SECURITY_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/SECURITY_GUIDE.md"
    },
    "DATA_MODEL": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/db/DATA_MODEL.md"
    },
    "USER_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/user/USER_GUIDE.md"
    },
    "IMAGE_ENHANCER_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/user/IMAGE_ENHANCER_GUIDE.md"
    },
    "EXTERNAL_SYSTEM_INTEGRATION_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md"
    },
    "INTEGRATION_TEST_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/INTEGRATION_TEST_GUIDE.md"
    },
    "INCIDENT_RESPONSE_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/INCIDENT_RESPONSE_GUIDE.md"
    },
    "LINUX_DOCKER_DEPLOYMENT": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/LINUX_DOCKER_DEPLOYMENT.md"
    },
    "SERVER_TEST_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/ops/SERVER_TEST_GUIDE.md"
    },
    "CODEFORMER_PIPELINE_ALGORITHM": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/CODEFORMER_PIPELINE_ALGORITHM.md"
    },
    "JSON_IO_FLOW": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/JSON_IO_FLOW.md"
    },
    "LLM_PROMPT_TEMPLATE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/LLM_PROMPT_TEMPLATE.md"
    },
    "PRESCRIPTION_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/PRESCRIPTION_GUIDE.md"
    },
    "RESTORATION_ENGINE_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/RESTORATION_ENGINE_GUIDE.md"
    },
    "SKIN_SCORING_GUIDE": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/SKIN_SCORING_GUIDE.md"
    },
    "WEIGHT_SYSTEM_DOCUMENTATION": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/guides/WEIGHT_SYSTEM_DOCUMENTATION.md"
    },
    "IMPROVEMENT_PLAN": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/project/IMPROVEMENT_PLAN.md"
    },
    "CODE_REVIEW_HISTORY": {
        "version": "1.0.0",
        "target_project_version": "1.0.0",
        "last_updated": "2026-05-31",
        "status": "active",
        "path": "docs/project/CODE_REVIEW_HISTORY.md"
    },
}


def get_doc_version(doc_name: str) -> Optional[Dict[str, str]]:
    """문서 버전 정보를 가져옵니다.
    
    Args:
        doc_name: 문서 이름 (예: "TESTING_GUIDE")
    
    Returns:
        문서 버전 정보 딕셔너리 또는 None
    """
    return DOCS_VERSIONS.get(doc_name)


def update_doc_version(
    doc_name: str,
    version: Optional[str] = None,
    last_updated: Optional[str] = None,
    status: Optional[str] = None
) -> bool:
    """문서 버전 정보를 업데이트합니다.
    
    Args:
        doc_name: 문서 이름
        version: 새 버전 (선택)
        last_updated: 마지막 업데이트 날짜 (선택)
        status: 상태 (선택)
    
    Returns:
        업데이트 성공 여부
    """
    if doc_name not in DOCS_VERSIONS:
        return False
    
    if version:
        DOCS_VERSIONS[doc_name]["version"] = version
    if last_updated:
        DOCS_VERSIONS[doc_name]["last_updated"] = last_updated
    if status:
        DOCS_VERSIONS[doc_name]["status"] = status
    
    return True


def list_all_docs() -> Dict[str, Dict[str, str]]:
    """모든 문서 버전 정보를 반환합니다."""
    return DOCS_VERSIONS.copy()


def get_active_docs() -> Dict[str, Dict[str, str]]:
    """활성 상태인 문서만 반환합니다."""
    return {
        name: info
        for name, info in DOCS_VERSIONS.items()
        if info.get("status") == "active"
    }


def get_docs_by_target_version(target_version: str) -> Dict[str, Dict[str, str]]:
    """특정 프로젝트 버전을 대상으로 하는 문서를 반환합니다.
    
    Args:
        target_version: 대상 프로젝트 버전 (예: "1.0.0")
    
    Returns:
        해당 버전을 대상으로 하는 문서 딕셔너리
    """
    return {
        name: info
        for name, info in DOCS_VERSIONS.items()
        if info.get("target_project_version") == target_version
    }
