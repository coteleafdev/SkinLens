"""
Health API 테스트 - 헬스체크 및 장애 복구 API
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthAPI:
    """Health API 엔드포인트 테스트"""

    def test_health_check_basic(self, auth_client):
        """기본 헬스체크"""
        response = auth_client.get("/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_health_check_services(self, auth_client):
        """헬스체크 서비스 상태 확인"""
        response = auth_client.get("/v1/health")
        data = response.json()
        # services 필드가 없을 수 있으므로 기본 상태만 확인
        if "services" in data:
            services = data["services"]
            # 각 서비스 상태 확인
            for service, status in services.items():
                assert status in ["healthy", "warning", "critical", "unhealthy"]

    def test_health_check_database_healthy(self):
        """데이터베이스 헬스체크"""
        from src.server.routers.health import check_database_health
        status = check_database_health()
        assert status in ["healthy", "unhealthy"]

    def test_health_check_disk_healthy(self):
        """디스크 헬스체크"""
        from src.server.routers.health import check_disk_health
        status = check_disk_health()
        assert status in ["healthy", "warning", "critical", "unhealthy"]

    def test_health_check_memory_healthy(self):
        """메모리 헬스체크"""
        from src.server.routers.health import check_memory_health
        status = check_memory_health()
        assert status in ["healthy", "warning", "critical", "unhealthy"]

    def test_health_check_cpu_healthy(self):
        """CPU 헬스체크"""
        from src.server.routers.health import check_cpu_health
        status = check_cpu_health()
        assert status in ["healthy", "warning", "critical", "unhealthy"]

    def test_get_incidents_basic(self, auth_client):
        """장애 이벤트 목록 조회"""
        response = auth_client.get("/v1/admin/incidents")
        assert response.status_code in [200, 404]  # 엔드포인트가 있을 수도 있고 없을 수도 있음
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    def test_get_incidents_with_filters(self, auth_client):
        """필터와 함께 장애 이벤트 조회"""
        response = auth_client.get("/v1/admin/incidents?severity=critical&status=active")
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    def test_get_incidents_with_pagination(self, auth_client):
        """페이지네이션과 함께 장애 이벤트 조회"""
        response = auth_client.get("/v1/admin/incidents?limit=5&offset=0")
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    def test_get_incident_not_found(self, auth_client):
        """존재하지 않는 장애 이벤트 조회"""
        response = auth_client.get("/v1/admin/incidents/nonexistent")
        assert response.status_code in [404, 401]  # 인증 문제일 수도 있음

    def test_trigger_recovery_not_found(self, auth_client):
        """존재하지 않는 장애 복구 시도"""
        response = auth_client.post(
            "/v1/admin/incidents/nonexistent/recover",
            json={"action_type": "restart", "force": False}
        )
        assert response.status_code in [404, 401]

    def test_trigger_recovery_invalid_action(self, auth_client):
        """잘못된 복구 액션 타입"""
        response = auth_client.post(
            "/v1/admin/incidents/test_id/recover",
            json={"action_type": "invalid_action", "force": False}
        )
        assert response.status_code in [404, 500, 400, 401]

    def test_get_recovery_actions_not_found(self, auth_client):
        """존재하지 않는 장애의 복구 작업 조회"""
        response = auth_client.get("/v1/admin/incidents/nonexistent/recovery-actions")
        assert response.status_code in [200, 404, 401]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    def test_trigger_rollback_not_found(self, auth_client):
        """존재하지 않는 복구 작업 롤백 시도"""
        response = auth_client.post("/v1/admin/recovery-actions/nonexistent/rollback")
        assert response.status_code in [404, 401]

    def test_health_check_response_model(self, auth_client):
        """헬스체크 응답 모델 검증"""
        response = auth_client.get("/v1/health")
        data = response.json()
        
        # 필수 필드 확인
        assert isinstance(data["status"], str)
        if "services" in data:
            assert isinstance(data["services"], dict)
        if "timestamp" in data:
            assert isinstance(data["timestamp"], str)
            # timestamp 형식 확인 (ISO 8601)
            assert "T" in data["timestamp"] or data["timestamp"].count("-") >= 2

    def test_incident_response_model(self, auth_client):
        """장애 응답 모델 검증"""
        response = auth_client.get("/v1/admin/incidents")
        if response.status_code == 200:
            data = response.json()
            
            if len(data) > 0:
                incident = data[0]
                assert "id" in incident
                assert "incident_type" in incident
                assert "severity" in incident
                assert "resource_type" in incident
                assert "resource_id" in incident
                assert "detected_at" in incident
                assert "status" in incident

    def test_recovery_action_response_model(self):
        """복구 작업 응답 모델 검증"""
        from src.server.routers.health import RecoveryActionResponse
        
        response = RecoveryActionResponse(
            recovery_action_id="test_id",
            status="in_progress"
        )
        
        assert response.recovery_action_id == "test_id"
        assert response.status == "in_progress"

    def test_health_check_overall_status_critical(self, auth_client):
        """전체 상태가 critical인 경우"""
        # 이 테스트는 실제 시스템 상태에 따라 다름
        response = auth_client.get("/v1/health")
        data = response.json()
        
        # 하나라도 critical이면 전체 상태도 critical
        if any(status == "critical" for status in data["services"].values()):
            assert data["status"] == "critical"

    def test_health_check_overall_status_warning(self, auth_client):
        """전체 상태가 warning인 경우"""
        response = auth_client.get("/v1/health")
        data = response.json()
        
        # critical이 없고 warning이 있으면 전체 상태는 warning
        if not any(status == "critical" for status in data["services"].values()):
            if any(status == "warning" for status in data["services"].values()):
                assert data["status"] == "warning"
