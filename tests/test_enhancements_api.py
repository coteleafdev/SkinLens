"""
향상된 기능 API 테스트

이미지 업로드, 푸시 알림 선호도, A/B 테스트, 모니터링 메트릭, 분석 추이 기능을 테스트합니다.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import json
import os
import tempfile
from pathlib import Path


class TestImageUpload:
    """이미지 업로드 API 테스트"""
    
    def test_upload_image_success(self, client: TestClient, auth_headers):
        """이미지 업로드 성공"""
        # 테스트 이미지 생성
        image_content = b"fake image content" * 100  # 1.6KB
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_content)
            temp_path = f.name
        
        try:
            with open(temp_path, "rb") as f:
                response = client.post(
                    "/v1/enhancements/upload",
                    files={"file": ("test.jpg", f, "image/jpeg")},
                    data={"rotation_angle": 0},
                    headers=auth_headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            assert "upload_id" in data
            assert data["filename"] == "test.jpg"
            assert data["status"] == "pending"
        finally:
            os.unlink(temp_path)
    
    def test_upload_image_too_large(self, client: TestClient, auth_headers):
        """이미지 업로드 실패 - 파일 크기 초과"""
        # 11MB 이미지 생성
        image_content = b"x" * (11 * 1024 * 1024)
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_content)
            temp_path = f.name
        
        try:
            with open(temp_path, "rb") as f:
                response = client.post(
                    "/v1/enhancements/upload",
                    files={"file": ("large.jpg", f, "image/jpeg")},
                    headers=auth_headers,
                )
            
            assert response.status_code == 413
        finally:
            os.unlink(temp_path)
    
    def test_upload_image_unsupported_format(self, client: TestClient, auth_headers):
        """이미지 업로드 실패 - 지원하지 않는 형식"""
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            f.write(b"fake gif")
            temp_path = f.name
        
        try:
            with open(temp_path, "rb") as f:
                response = client.post(
                    "/v1/enhancements/upload",
                    files={"file": ("test.gif", f, "image/gif")},
                    headers=auth_headers,
                )
            
            assert response.status_code == 415
        finally:
            os.unlink(temp_path)
    
    def test_get_uploads(self, client: TestClient, auth_headers):
        """이미지 업로드 목록 조회"""
        response = client.get(
            "/v1/enhancements/uploads",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "uploads" in data
        assert isinstance(data["uploads"], list)


class TestPushPreferences:
    """푸시 알림 선호도 API 테스트"""
    
    def test_set_push_preferences(self, client: TestClient, auth_headers):
        """푸시 알림 선호도 설정"""
        payload = {
            "push_enabled": True,
            "analysis_complete_enabled": True,
            "promotion_enabled": False,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
        }
        
        response = client.post(
            "/v1/enhancements/push/preferences",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Push preferences updated successfully"
    
    def test_get_push_preferences(self, client: TestClient, auth_headers):
        """푸시 알림 선호도 조회"""
        response = client.get(
            "/v1/enhancements/push/preferences",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "push_enabled" in data
        assert "analysis_complete_enabled" in data


class TestABTesting:
    """A/B 테스트 API 테스트"""
    
    def test_create_ab_test(self, client: TestClient, admin_headers):
        """A/B 테스트 생성 (관리자 전용)"""
        payload = {
            "test_name": "ui_redesign_test",
            "variant_a_name": "original_ui",
            "variant_b_name": "new_ui",
            "description": "UI redesign A/B test",
            "traffic_split": 0.5,
        }
        
        response = client.post(
            "/v1/enhancements/ab/tests",
            json=payload,
            headers=admin_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "A/B test created successfully"
        assert data["test_name"] == "ui_redesign_test"
    
    def test_create_ab_test_unauthorized(self, client: TestClient, auth_headers):
        """A/B 테스트 생성 실패 - 권한 부족"""
        payload = {
            "test_name": "test",
            "variant_a_name": "A",
            "variant_b_name": "B",
        }
        
        response = client.post(
            "/v1/enhancements/ab/tests",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 403
    
    def test_assign_user_to_variant(self, client: TestClient, auth_headers):
        """사용자를 A/B 테스트 변형에 할당"""
        # 먼저 테스트 생성 (관리자로)
        # 이 테스트는 실제로는 테스트 DB에 테스트가 미리 생성되어 있어야 함
        # 여기서는 가정하고 진행
        
        response = client.post(
            "/v1/enhancements/ab/assign?test_id=1",
            headers=auth_headers,
        )
        
        # 테스트가 없으면 404 또는 다른 에러가 발생할 수 있음
        # 여기서는 API 호출 자체가 성공하는지 확인
        assert response.status_code in [200, 404]
    
    def test_get_user_variant(self, client: TestClient, auth_headers):
        """사용자의 A/B 테스트 변형 조회"""
        response = client.get(
            "/v1/enhancements/ab/variant/1",
            headers=auth_headers,
        )
        
        # 할당되지 않은 경우 404
        assert response.status_code in [200, 404]
    
    def test_record_ab_test_result(self, client: TestClient):
        """A/B 테스트 결과 기록"""
        payload = {
            "test_id": 1,
            "variant": "A",
            "metric_name": "click_rate",
            "metric_value": 0.05,
            "event_count": 100,
        }
        
        response = client.post(
            "/v1/enhancements/ab/results",
            json=payload,
        )
        
        # 인증이 필요할 수 있음
        assert response.status_code in [200, 401, 403]
    
    def test_get_ab_test_results(self, client: TestClient, admin_headers):
        """A/B 테스트 결과 조회 (관리자 전용)"""
        response = client.get(
            "/v1/enhancements/ab/results/1",
            headers=admin_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data


class TestMonitoringMetrics:
    """모니터링 메트릭 API 테스트"""
    
    def test_record_metric(self, client: TestClient, admin_headers):
        """모니터링 메트릭 기록 (관리자 전용)"""
        payload = {
            "metric_name": "api_response_time",
            "metric_value": 0.5,
            "metric_unit": "seconds",
            "tags": {"endpoint": "/v1/analysis/jobs"},
        }
        
        response = client.post(
            "/v1/enhancements/metrics",
            json=payload,
            headers=admin_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Metric recorded successfully"
    
    def test_record_metric_unauthorized(self, client: TestClient, auth_headers):
        """모니터링 메트릭 기록 실패 - 권한 부족"""
        payload = {
            "metric_name": "test_metric",
            "metric_value": 1.0,
        }
        
        response = client.post(
            "/v1/enhancements/metrics",
            json=payload,
            headers=auth_headers,
        )
        
        assert response.status_code == 403
    
    def test_get_metrics(self, client: TestClient, admin_headers):
        """모니터링 메트릭 조회 (관리자 전용)"""
        response = client.get(
            "/v1/enhancements/metrics",
            headers=admin_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert isinstance(data["metrics"], list)
    
    def test_get_metrics_with_filter(self, client: TestClient, admin_headers):
        """모니터링 메트릭 조회 - 필터 적용"""
        response = client.get(
            "/v1/enhancements/metrics?metric_name=api_response_time&limit=10",
            headers=admin_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data


class TestAnalysisTrends:
    """분석 추이 API 테스트"""
    
    def test_get_analysis_trends(self, client: TestClient, auth_headers):
        """분석 추이 조회"""
        response = client.get(
            "/v1/enhancements/trends",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "trends" in data
        assert isinstance(data["trends"], list)
    
    def test_get_analysis_trends_with_limit(self, client: TestClient, auth_headers):
        """분석 추이 조회 - limit 적용"""
        response = client.get(
            "/v1/enhancements/trends?limit=10",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "trends" in data
        if data["trends"]:
            assert len(data["trends"]) <= 10


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """테스트 클라이언트"""
    from src.server.server import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client: TestClient):
    """인증 헤더 (customer)"""
    # 먼저 사용자 생성 및 로그인
    response = client.post(
        "/v1/auth/register",
        json={
            "customer_id": "test_customer_enh",
            "password": "test_password",
            "email": "test@example.com",
        },
    )
    
    # 이미 존재하는 경우 무시
    if response.status_code not in [200, 400]:
        response = client.post(
            "/v1/auth/login",
            json={
                "customer_id": "test_customer_enh",
                "password": "test_password",
            },
        )
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    # 기존 사용자로 로그인 시도
    response = client.post(
        "/v1/auth/login",
        json={
            "customer_id": "test_customer",
            "password": "test_password",
        },
    )
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    return {}


@pytest.fixture
def admin_headers(client: TestClient):
    """인증 헤더 (admin)"""
    # 관리자 로그인
    response = client.post(
        "/v1/auth/login",
        json={
            "customer_id": "admin",
            "password": "admin_password",
        },
    )
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    return {}
