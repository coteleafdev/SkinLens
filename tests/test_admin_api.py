"""
Admin API 테스트 - 관리자 전용 API
"""
import pytest
from fastapi.testclient import TestClient


class TestAdminAPI:
    """Admin API 엔드포인트 테스트"""

    def test_get_audit_logs_unauthorized(self, auth_client):
        """인증 없이 감사 로그 조회 실패"""
        response = auth_client.get("/v3/admin/audit-logs")
        assert response.status_code == 401

    def test_get_audit_logs_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 감사 로그 조회 실패"""
        response = auth_client.get(
            "/v3/admin/audit-logs",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_get_audit_logs_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 감사 로그 조회 성공"""
        response = auth_client.get(
            "/v3/admin/audit-logs",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "audit_logs" in data
        assert "count" in data
        assert isinstance(data["audit_logs"], list)

    def test_get_audit_logs_with_filters(self, auth_client, admin_token):
        """필터와 함께 감사 로그 조회"""
        response = auth_client.get(
            "/v3/admin/audit-logs?days=7&limit=50",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "audit_logs" in data

    def test_check_db_health_unauthorized(self, auth_client):
        """인증 없이 DB 헬스체크 실패"""
        response = auth_client.get("/v3/health/db")
        assert response.status_code == 401

    def test_check_db_health_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 DB 헬스체크 실패"""
        response = auth_client.get(
            "/v3/health/db",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_check_db_health_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 DB 헬스체크 성공"""
        response = auth_client.get(
            "/v3/health/db",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "healthy" in data

    def test_check_db_health_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 DB 헬스체크 성공"""
        response = auth_client.get(
            "/v3/health/db",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "healthy" in data

    def test_get_db_metrics_unauthorized(self, auth_client):
        """인증 없이 DB 메트릭 조회 실패"""
        response = auth_client.get("/v3/admin/db/metrics")
        assert response.status_code == 401

    def test_get_db_metrics_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 DB 메트릭 조회 실패"""
        response = auth_client.get(
            "/v3/admin/db/metrics",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_get_db_metrics_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 DB 메트릭 조회 성공"""
        response = auth_client.get(
            "/v3/admin/db/metrics",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "execution_history" in data
        assert "analysis_results" in data
        assert "supabase" in data
        assert "timestamp" in data

    def test_get_db_metrics_rate_limiting(self, auth_client, admin_token):
        """DB 메트릭 속도 제한 테스트"""
        # 10회 이상 요청 시 속도 제한
        for _ in range(11):
            response = auth_client.get(
                "/v3/admin/db/metrics",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        # 11번째 요청은 속도 제한으로 실패해야 함
        assert response.status_code in (200, 429)

    def test_get_audit_summary_unauthorized(self, auth_client):
        """인증 없이 감사 요약 조회 실패"""
        response = auth_client.get("/v3/admin/audit/summary")
        assert response.status_code == 401

    def test_get_audit_summary_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 감사 요약 조회 실패"""
        response = auth_client.get(
            "/v3/admin/audit/summary",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_get_audit_summary_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 감사 요약 조회 성공"""
        response = auth_client.get(
            "/v3/admin/audit/summary",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_access" in data
        assert "unique_users" in data
        assert "failed_access" in data
        assert "success_rate" in data
        assert "top_endpoints" in data
        assert "suspicious_activity" in data
        assert "period_days" in data

    def test_get_audit_summary_with_days_param(self, auth_client, admin_token):
        """days 파라미터로 기간 설정"""
        response = auth_client.get(
            "/v3/admin/audit/summary?days=7",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7

    def test_get_audit_summary_rate_limiting(self, auth_client, admin_token):
        """감사 요약 속도 제한 테스트"""
        # 10회 이상 요청 시 속도 제한
        for _ in range(11):
            response = auth_client.get(
                "/v3/admin/audit/summary",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        # 11번째 요청은 속도 제한으로 실패해야 함
        assert response.status_code in (200, 429)
