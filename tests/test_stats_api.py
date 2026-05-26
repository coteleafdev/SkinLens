"""
Stats API 테스트 - 관리자/분석가용 통계 엔드포인트
"""
import pytest
from fastapi.testclient import TestClient


class TestStatsAPI:
    """Stats API 엔드포인트 테스트"""

    def test_analysis_stats_unauthorized(self, auth_client):
        """인증 없이 분석 통계 조회 시 401"""
        response = auth_client.get("/v3/stats/analysis")
        assert response.status_code == 401

    def test_analysis_stats_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 분석 통계 조회 시 403"""
        response = auth_client.get(
            "/v3/stats/analysis",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_analysis_stats_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 분석 통계 조회 성공"""
        response = auth_client.get(
            "/v3/stats/analysis",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert "stats" in response.json()
        assert isinstance(response.json()["stats"], list)

    def test_analysis_stats_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 분석 통계 조회 성공"""
        response = auth_client.get(
            "/v3/stats/analysis",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert "stats" in response.json()

    def test_analysis_stats_with_days_param(self, auth_client, admin_token):
        """days 파라미터로 기간 설정"""
        response = auth_client.get(
            "/v3/stats/analysis?days=30",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_model_performance_unauthorized(self, auth_client):
        """인증 없이 모델 성능 조회 시 401"""
        response = auth_client.get("/v3/stats/model-performance")
        assert response.status_code == 401

    def test_model_performance_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 모델 성능 조회 시 403"""
        response = auth_client.get(
            "/v3/stats/model-performance",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_model_performance_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 모델 성능 조회 성공"""
        response = auth_client.get(
            "/v3/stats/model-performance",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert "performance" in response.json()

    def test_score_trends_unauthorized(self, auth_client):
        """인증 없이 점수 추이 조회 시 401"""
        response = auth_client.get("/v3/stats/score-trends")
        assert response.status_code == 401

    def test_score_trends_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 점수 추이 조회 시 403"""
        response = auth_client.get(
            "/v3/stats/score-trends",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_score_trends_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 점수 추이 조회 성공"""
        response = auth_client.get(
            "/v3/stats/score-trends",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert "trends" in response.json()

    def test_llm_api_stats_unauthorized(self, auth_client):
        """인증 없이 LLM API 통계 조회 시 401"""
        response = auth_client.get("/v3/stats/llm-api")
        assert response.status_code == 401

    def test_llm_api_stats_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 LLM API 통계 조회 성공"""
        response = auth_client.get(
            "/v3/stats/llm-api",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert "stats" in response.json()

    def test_image_metadata_unauthorized(self, auth_client):
        """인증 없이 이미지 메타데이터 조회 시 401"""
        response = auth_client.get("/v3/stats/image-metadata")
        assert response.status_code == 401

    def test_image_metadata_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 이미지 메타데이터 조회 성공"""
        response = auth_client.get(
            "/v3/stats/image-metadata",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert "metadata" in response.json()

    def test_errors_unauthorized(self, auth_client):
        """인증 없이 에러 조회 시 401"""
        response = auth_client.get("/v3/stats/errors")
        assert response.status_code == 401

    def test_errors_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 에러 조회 시 403"""
        response = auth_client.get(
            "/v3/stats/errors",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_errors_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 에러 조회 성공"""
        response = auth_client.get(
            "/v3/stats/errors",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert "errors" in response.json()

    def test_resolve_error_unauthorized(self, auth_client):
        """인증 없이 에러 해결 시 401"""
        response = auth_client.post("/v3/stats/errors/1/resolve", data={"resolution_note": "test"})
        assert response.status_code == 401

    def test_resolve_error_forbidden_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 에러 해결 시도 시 403 (admin 전용)"""
        response = auth_client.post(
            "/v3/stats/errors/1/resolve",
            data={"resolution_note": "test"},
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 403

    def test_resolve_error_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 에러 해결 성공"""
        response = auth_client.post(
            "/v3/stats/errors/1/resolve",
            data={"resolution_note": "test resolution"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]  # 200: 성공, 404: error_id 없음

    def test_system_health_unauthorized(self, auth_client):
        """인증 없이 시스템 헬스 조회 시 401"""
        response = auth_client.get("/v3/stats/system-health")
        assert response.status_code == 401

    def test_system_health_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 시스템 헬스 조회 성공"""
        response = auth_client.get(
            "/v3/stats/system-health",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert "health" in response.json()

    def test_summary_unauthorized(self, auth_client):
        """인증 없이 통계 요약 조회 시 401"""
        response = auth_client.get("/v3/stats/summary")
        assert response.status_code == 401

    def test_summary_authorized_analyst(self, auth_client, analyst_token):
        """분석가 권한으로 통계 요약 조회 성공"""
        response = auth_client.get(
            "/v3/stats/summary",
            headers={"Authorization": f"Bearer {analyst_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), dict)
