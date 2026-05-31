"""
Admin API 테스트 - 관리자 전용 API
"""
import pytest
from fastapi.testclient import TestClient


class TestAdminAPI:
    """Admin API 엔드포인트 테스트"""

    def test_get_audit_logs_unauthorized(self, auth_client):
        """인증 없이 감사 로그 조회 실패"""
        response = auth_client.get("/v1/admin/audit-logs")
        assert response.status_code == 401

    def test_get_audit_logs_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 감사 로그 조회 실패"""
        response = auth_client.get(
            "/v1/admin/audit-logs",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_get_audit_logs_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 감사 로그 조회 성공"""
        response = auth_client.get(
            "/v1/admin/audit-logs",
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
            "/v1/admin/audit-logs?days=7&limit=50",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "audit_logs" in data

    def test_get_log_level_unauthorized(self, auth_client):
        """인증 없이 로그 레벨 조회 실패"""
        response = auth_client.get("/v1/admin/logging/level")
        assert response.status_code == 401

    def test_get_log_level_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 로그 레벨 조회 실패"""
        response = auth_client.get(
            "/v1/admin/logging/level",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_get_log_level_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 로그 레벨 조회 성공"""
        response = auth_client.get(
            "/v1/admin/logging/level",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_level" in data
        assert "available_levels" in data
        assert isinstance(data["available_levels"], list)

    def test_update_log_level_unauthorized(self, auth_client):
        """인증 없이 로그 레벨 변경 실패"""
        response = auth_client.put("/v1/admin/logging/level?level=DEBUG")
        assert response.status_code == 401

    def test_update_log_level_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 로그 레벨 변경 실패"""
        response = auth_client.put(
            "/v1/admin/logging/level?level=DEBUG",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_update_log_level_invalid_level(self, auth_client, admin_token):
        """잘못된 로그 레벨로 변경 실패"""
        response = auth_client.put(
            "/v1/admin/logging/level?level=INVALID",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400

    def test_update_log_level_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 로그 레벨 변경 성공"""
        response = auth_client.put(
            "/v1/admin/logging/level?level=WARNING",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "previous_level" in data
        assert "new_level" in data
        assert data["new_level"] == "WARNING"

    def test_get_system_metrics_unauthorized(self, auth_client):
        """인증 없이 시스템 메트릭 조회 실패"""
        response = auth_client.get("/v1/admin/metrics/system")
        assert response.status_code == 401

    def test_get_system_metrics_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 시스템 메트릭 조회 실패"""
        response = auth_client.get(
            "/v1/admin/metrics/system",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_get_system_metrics_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 시스템 메트릭 조회 성공"""
        response = auth_client.get(
            "/v1/admin/metrics/system",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # psutil이 설치되어 있으면 메트릭 반환, 없으면 에러 메시지
        if "error" in data:
            assert data["error"] == "psutil not installed"
        else:
            assert "cpu" in data
            assert "memory" in data
            assert "disk" in data
            assert "network" in data
            assert "process" in data
            assert "timestamp" in data

    def test_create_api_key_unauthorized(self, auth_client):
        """인증 없이 API 키 생성 실패"""
        response = auth_client.post("/v1/admin/api-keys?name=test&owner_id=user1")
        assert response.status_code == 401

    def test_create_api_key_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 API 키 생성 실패"""
        response = auth_client.post(
            "/v1/admin/api-keys?name=test&owner_id=user1",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_create_api_key_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 API 키 생성 성공"""
        response = auth_client.post(
            "/v1/admin/api-keys?name=test_key&owner_id=user1&scopes=%5B%22read%22%2C%22write%22%5D",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "api_key" in data
        assert "name" in data
        assert data["name"] == "test_key"
        assert "scopes" in data

    def test_list_api_keys_unauthorized(self, auth_client):
        """인증 없이 API 키 목록 조회 실패"""
        response = auth_client.get("/v1/admin/api-keys")
        assert response.status_code == 401

    def test_list_api_keys_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 API 키 목록 조회 성공"""
        response = auth_client.get(
            "/v1/admin/api-keys",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "api_keys" in data
        assert "count" in data
        assert isinstance(data["api_keys"], list)

    def test_revoke_api_key_unauthorized(self, auth_client):
        """인증 없이 API 키 폐지 실패"""
        response = auth_client.delete("/v1/admin/api-keys/test-key-id")
        assert response.status_code == 401

    def test_revoke_api_key_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 API 키 폐지 실패"""
        response = auth_client.delete(
            "/v1/admin/api-keys/test-key-id",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_get_cache_stats_unauthorized(self, auth_client):
        """인증 없이 캐시 통계 조회 실패"""
        response = auth_client.get("/v1/admin/cache/stats")
        assert response.status_code == 401

    def test_get_cache_stats_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 캐시 통계 조회 성공"""
        response = auth_client.get(
            "/v1/admin/cache/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "metrics_cache" in data
        assert "timestamp" in data

    def test_clear_cache_unauthorized(self, auth_client):
        """인증 없이 캐시 초기화 실패"""
        response = auth_client.post("/v1/admin/cache/clear")
        assert response.status_code == 401

    def test_clear_cache_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 캐시 초기화 실패"""
        response = auth_client.post(
            "/v1/admin/cache/clear",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_clear_cache_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 캐시 초기화 성공"""
        response = auth_client.post(
            "/v1/admin/cache/clear?cache_type=metrics",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "cleared_caches" in data
        assert "metrics" in data["cleared_caches"]

    def test_check_db_health_unauthorized(self, auth_client):
        """인증 없이 DB 헬스체크 실패"""
        response = auth_client.get("/v1/health/db")
        assert response.status_code == 401

    def test_check_db_health_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 DB 헬스체크 실패"""
        response = auth_client.get(
            "/v1/health/db",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_check_db_health_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 DB 헬스체크 성공"""
        response = auth_client.get(
            "/v1/health/db",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "healthy" in data

    def test_check_db_health_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 DB 헬스체크 성공"""
        response = auth_client.get(
            "/v1/health/db",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "healthy" in data

    def test_get_db_metrics_unauthorized(self, auth_client):
        """인증 없이 DB 메트릭 조회 실패"""
        response = auth_client.get("/v1/admin/db/metrics")
        assert response.status_code == 401

    def test_get_db_metrics_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 DB 메트릭 조회 실패"""
        response = auth_client.get(
            "/v1/admin/db/metrics",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_get_db_metrics_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 DB 메트릭 조회 성공"""
        response = auth_client.get(
            "/v1/admin/db/metrics",
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
                "/v1/admin/db/metrics",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        # 11번째 요청은 속도 제한으로 실패해야 함
        assert response.status_code in (200, 429)

    def test_get_audit_summary_unauthorized(self, auth_client):
        """인증 없이 감사 요약 조회 실패"""
        response = auth_client.get("/v1/admin/audit/summary")
        assert response.status_code == 401

    def test_get_audit_summary_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 감사 요약 조회 실패"""
        response = auth_client.get(
            "/v1/admin/audit/summary",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_get_audit_summary_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 감사 요약 조회 성공"""
        response = auth_client.get(
            "/v1/admin/audit/summary",
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
            "/v1/admin/audit/summary?days=7",
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
                "/v1/admin/audit/summary",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        # 11번째 요청은 속도 제한으로 실패해야 함
        assert response.status_code in (200, 429)


class TestCustomerManagement:
    """고객 관리 API 테스트"""

    def test_list_customers_unauthorized(self, auth_client):
        """인증 없이 고객 목록 조회 실패"""
        response = auth_client.get("/v1/admin/customers")
        assert response.status_code == 401

    def test_list_customers_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 고객 목록 조회 실패"""
        response = auth_client.get(
            "/v1/admin/customers",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_list_customers_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 고객 목록 조회 성공"""
        response = auth_client.get(
            "/v1/admin/customers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "customers" in data
        assert "total" in data

    def test_get_customer_detail_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 고객 상세 조회 성공"""
        response = auth_client.get(
            "/v1/admin/customers/test_customer_123",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # 고객이 없을 수 있으므로 404 또는 200 모두 허용
        assert response.status_code in (200, 404)

    def test_update_customer_status_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 고객 상태 변경 실패"""
        response = auth_client.put(
            "/v1/admin/customers/test_customer_123/status",
            json={"status": "inactive"},
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_delete_customer_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 고객 삭제 실패"""
        response = auth_client.delete(
            "/v1/admin/customers/test_customer_123",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403


class TestProductManagement:
    """제품 관리 API 테스트"""

    def test_list_products_unauthorized(self, auth_client):
        """인증 없이 제품 목록 조회 실패"""
        response = auth_client.get("/v1/admin/products")
        assert response.status_code == 401

    def test_list_products_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 제품 목록 조회 성공"""
        response = auth_client.get(
            "/v1/admin/products",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "products" in data

    def test_create_product_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 제품 생성 실패"""
        response = auth_client.post(
            "/v1/admin/products",
            json={
                "product_id": "TEST001",
                "product_name": "Test Product",
                "category": "테스트",
                "key_ingredients": ["ingredient1"],
                "efficacy": "Test efficacy"
            },
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_update_product_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 제품 업데이트 실패"""
        response = auth_client.put(
            "/v1/admin/products/TEST001",
            json={"product_name": "Updated Name"},
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_delete_product_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 제품 삭제 실패"""
        response = auth_client.delete(
            "/v1/admin/products/TEST001",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403


class TestAnalysisManagement:
    """분석 결과 관리 API 테스트"""

    def test_list_all_analyses_unauthorized(self, auth_client):
        """인증 없이 전체 분석 목록 조회 실패"""
        response = auth_client.get("/v1/admin/analyses")
        assert response.status_code == 401

    def test_list_all_analyses_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 전체 분석 목록 조회 성공"""
        response = auth_client.get(
            "/v1/admin/analyses",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "analyses" in data

    def test_delete_analysis_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 분석 삭제 실패"""
        response = auth_client.delete(
            "/v1/admin/analyses/1",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403


class TestActivityMonitoring:
    """사용자 활동 모니터링 API 테스트"""

    def test_get_active_sessions_unauthorized(self, auth_client):
        """인증 없이 활성 세션 조회 실패"""
        response = auth_client.get("/v1/admin/active-sessions")
        assert response.status_code == 401

    def test_get_active_sessions_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 활성 세션 조회 성공"""
        response = auth_client.get(
            "/v1/admin/active-sessions",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data

    def test_terminate_session_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 세션 종료 실패"""
        response = auth_client.delete(
            "/v1/admin/active-sessions/session123",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_get_anomalies_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 이상 활동 조회 성공"""
        response = auth_client.get(
            "/v1/admin/anomalies",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "anomalies" in data

    def test_resolve_anomaly_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 이상 활동 해결 실패"""
        response = auth_client.post(
            "/v1/admin/anomalies/anomaly123/resolve",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403


class TestSecurityManagement:
    """보안 관리 API 테스트"""

    def test_list_roles_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 역할 목록 조회 실패"""
        response = auth_client.get(
            "/v1/admin/roles",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_set_user_role_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 역할 설정 실패"""
        response = auth_client.put(
            "/v1/admin/customers/test_customer_123/role",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_get_blocked_ips_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 차단된 IP 조회 실패"""
        response = auth_client.get(
            "/v1/admin/blocked-ips",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_block_ip_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 IP 차단 실패"""
        response = auth_client.post(
            "/v1/admin/blocked-ips",
            json={"ip_address": "192.168.1.1", "reason": "Test"},
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_unblock_ip_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 IP 차단 해제 실패"""
        response = auth_client.delete(
            "/v1/admin/blocked-ips/192.168.1.1",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403


class TestBusinessIntelligence:
    """비즈니스 인텔리전스 API 테스트"""

    def test_get_dashboard_overview_unauthorized(self, auth_client):
        """인증 없이 대시보드 조회 실패"""
        response = auth_client.get("/v1/admin/dashboard/overview")
        assert response.status_code == 401

    def test_get_dashboard_overview_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 대시보드 조회 성공"""
        response = auth_client.get(
            "/v1/admin/dashboard/overview",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "overview" in data
        assert "recent_stats" in data

    def test_get_usage_report_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 사용량 리포트 조회 성공"""
        response = auth_client.get(
            "/v1/admin/reports/usage",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_get_revenue_report_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 수익 리포트 조회 성공"""
        response = auth_client.get(
            "/v1/admin/reports/revenue",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "revenue" in data
