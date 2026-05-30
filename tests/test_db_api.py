"""
DB 관리 API 단위 테스트.

DB Health Check, DB Metrics, 감사 로그 요약 API를 테스트합니다.
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.server
@pytest.mark.requires_jose
@pytest.mark.requires_fastapi
class TestDBHealthCheckAPI:
    """DB Health Check API 테스트."""

    def test_health_db_healthy(self, auth_client, admin_token):
        """DB Health Check 테스트 (정상)."""
        response = auth_client.get("/v1/health/db", headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code in [200, 503]  # DB가 없을 수도 있음
        data = response.json()
        
        if response.status_code == 200:
            assert data["healthy"] is True
            assert "file_size_mb" in data
            assert "row_counts" in data
        else:
            assert data["healthy"] is False
            assert "error" in data

    def test_health_db_unhealthy(self, auth_client, admin_token):
        """DB Health Check 테스트 (비정상)."""
        # DB 경로를 존재하지 않는 경로로 설정
        original_db = os.environ.get("EXECUTION_HISTORY_DB")
        os.environ["EXECUTION_HISTORY_DB"] = "/nonexistent/path.db"
        
        try:
            response = auth_client.get("/v1/health/db", headers={"Authorization": f"Bearer {admin_token}"})
            assert response.status_code == 503
            data = response.json()
            assert data["healthy"] is False
        finally:
            if original_db:
                os.environ["EXECUTION_HISTORY_DB"] = original_db


@pytest.mark.server
@pytest.mark.requires_jose
@pytest.mark.requires_fastapi
class TestDBMetricsAPI:
    """DB Metrics API 테스트."""

    def test_db_metrics_unauthorized(self, auth_client):
        """DB Metrics 테스트 (인증 없음)."""
        response = auth_client.get("/v1/admin/db/metrics")
        assert response.status_code == 401
    
    def test_db_metrics_forbidden(self, auth_client, user_token):
        """DB Metrics 테스트 (권한 없음 - 일반 사용자)."""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = auth_client.get("/v1/admin/db/metrics", headers=headers)
        assert response.status_code == 403
    
    def test_db_metrics_authorized(self, auth_client, admin_token):
        """DB Metrics 테스트 (인증됨)."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.get("/v1/admin/db/metrics", headers=headers)
        
        assert response.status_code in [200, 403]  # 역할 확인 필요
        if response.status_code == 200:
            data = response.json()
            assert "execution_history" in data
            assert "analysis_results" in data
            assert "supabase" in data


@pytest.mark.server
@pytest.mark.requires_jose
@pytest.mark.requires_fastapi
class TestAuditSummaryAPI:
    """감사 로그 요약 API 테스트."""

    def test_audit_summary_unauthorized(self, auth_client):
        """감사 로그 요약 테스트 (인증 없음)."""
        response = auth_client.get("/v1/admin/audit/summary")
        assert response.status_code == 401
    
    def test_audit_summary_forbidden(self, auth_client, user_token):
        """감사 로그 요약 테스트 (권한 없음 - 일반 사용자)."""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = auth_client.get("/v1/admin/audit/summary", headers=headers)
        assert response.status_code == 403
    
    def test_audit_summary_authorized(self, auth_client, admin_token):
        """감사 로그 요약 테스트 (인증됨)."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.get("/v1/admin/audit/summary", headers=headers)
        assert response.status_code in [200, 403]  # 역할 확인 필요
        if response.status_code == 200:
            data = response.json()
            # API 응답 구조에 맞게 필드 확인
            assert any(key in data for key in ["total_records", "success_rate", "period_days", "failed_access"])
    
    def test_audit_summary_custom_days(self, auth_client, admin_token):
        """감사 로그 요약 테스트 (사용자 정의 기간)."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.get("/v1/admin/audit/summary?days=30", headers=headers)
        assert response.status_code in [200, 403]

    def test_audit_logs_unauthorized(self, auth_client):
        """인증 없이 감사 로그 조회 시 401"""
        response = auth_client.get("/v1/admin/audit-logs")
        assert response.status_code == 401

    def test_audit_logs_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 감사 로그 조회 시 403 (admin 전용)"""
        headers = {"Authorization": f"Bearer {analyst_token}"}
        response = auth_client.get("/v1/admin/audit-logs", headers=headers)
        assert response.status_code == 403

    def test_audit_logs_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 감사 로그 조회 성공"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.get("/v1/admin/audit-logs", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "audit_logs" in data
        assert isinstance(data["audit_logs"], list)

    def test_audit_logs_with_filters(self, auth_client, admin_token):
        """필터 파라미터로 감사 로그 조회"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.get(
            "/v1/admin/audit-logs?days=7&limit=10",
            headers=headers
        )
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
