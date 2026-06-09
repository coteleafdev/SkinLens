"""
Logs API 테스트 - 관리자/분석가용 로그 엔드포인트
"""
import pytest
from fastapi.testclient import TestClient


class TestLogsAPI:
    """Logs API 엔드포인트 테스트"""

    def test_get_logs_unauthorized(self, auth_client):
        """인증 없이 로그 조회 시 401"""
        response = auth_client.get("/v1/logs/")
        assert response.status_code == 401

    def test_get_logs_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 로그 조회 시 403"""
        response = auth_client.get(
            "/v1/logs/",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_get_logs_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 로그 조회 성공"""
        response = auth_client.get(
            "/v1/logs/",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "logs" in data
        assert isinstance(data["logs"], list)

    def test_get_logs_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 로그 조회 성공"""
        response = auth_client.get(
            "/v1/logs/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_get_logs_with_level_param(self, auth_client, admin_token):
        """level 파라미터로 로그 필터링"""
        response = auth_client.get(
            "/v1/logs/?level=ERROR",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_get_logs_with_invalid_level(self, auth_client, admin_token):
        """잘못된 level 파라미터 시 400"""
        response = auth_client.get(
            "/v1/logs/?level=INVALID",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400

    def test_get_logs_with_limit_param(self, auth_client, admin_token):
        """limit 파라미터로 결과 개수 제한"""
        response = auth_client.get(
            "/v1/logs/?limit=10",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_get_logs_with_hours_param(self, auth_client, admin_token):
        """hours 파라미터로 기간 설정"""
        response = auth_client.get(
            "/v1/logs/?hours=24",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_download_logs_unauthorized(self, auth_client):
        """인증 없이 로그 다운로드 시 401"""
        response = auth_client.get("/v1/logs/download")
        assert response.status_code == 401

    def test_download_logs_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 로그 다운로드 시 403"""
        response = auth_client.get(
            "/v1/logs/download",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_download_logs_authorized_analyst_csv(self, auth_client, analyst_token):
        """분석가 권한으로 CSV 로그 다운로드 성공"""
        response = auth_client.get(
            "/v1/logs/download?format=csv",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code in [200, 404]  # 200: 성공, 404: 로그 없음
        if response.status_code == 200:
            assert "text/csv" in response.headers.get("content-type", "")

    def test_download_logs_authorized_analyst_json(self, auth_client, analyst_token):
        """분석가 권한으로 JSON 로그 다운로드 성공"""
        response = auth_client.get(
            "/v1/logs/download?format=json",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code in [200, 404]  # 200: 성공, 404: 로그 없음
        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")

    def test_download_logs_with_invalid_format(self, auth_client, admin_token):
        """잘못된 format 파라미터 시 400"""
        response = auth_client.get(
            "/v1/logs/download?format=xml",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400

    def test_download_logs_with_level_param(self, auth_client, admin_token):
        """level 파라미터로 다운로드 로그 필터링"""
        response = auth_client.get(
            "/v1/logs/download?format=csv&level=ERROR",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]

    def test_download_logs_with_hours_param(self, auth_client, admin_token):
        """hours 파라미터로 다운로드 기간 설정"""
        response = auth_client.get(
            "/v1/logs/download?format=csv&hours=24",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]
