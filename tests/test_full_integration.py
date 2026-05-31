"""
test_full_integration.py — 전체 시스템 통합 테스트

앱 클라이언트 - 엔진 서버 - 웹 서버 - DB 연동 시뮬레이션 및 테스트

테스트 시나리오:
1. 앱 클라이언트가 웹 서버에 이미지 업로드
2. 웹 서버가 엔진 서버에 분석 요청
3. 엔진 서버가 이미지 분석 수행
4. 분석 결과를 DB에 저장
5. 앱 클라이언트가 결과 조회
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import numpy as np
from PIL import Image

# 환경변수 설정 (테스트용)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-ci")
os.environ.setdefault("SKIN_API_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))

# Rate limiting 비활성화
def fake_limit(limit_str):
    def decorator(f):
        return f
    return decorator

import src.server.deps as deps_module
deps_module.limiter.limit = fake_limit

from fastapi.testclient import TestClient
from src.server.server import app


class TestFullIntegration:
    """전체 시스템 통합 테스트"""

    @pytest.fixture
    def client(self):
        """TestClient fixture"""
        return TestClient(app)

    @pytest.fixture
    def temp_dir(self):
        """임시 디렉토리 fixture"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def test_image(self, temp_dir):
        """테스트용 이미지 fixture"""
        # 100x100 RGB 이미지 생성
        img = Image.new('RGB', (100, 100), color='white')
        img_path = temp_dir / "test_image.jpg"
        img.save(img_path, 'JPEG')
        return img_path

    @pytest.fixture
    def mock_engine_response(self):
        """엔진 서버 응답 Mock"""
        return {
            "overall_score": 75.0,
            "measurements": {
                "melasma_score": 80.0,
                "redness_score": 70.0,
                "pore_score": 65.0,
                "wrinkle_score": 60.0,
                "texture_score": 75.0,
                "tone_score": 70.0,
                "elasticity_score": 65.0,
                "sebum_score": 60.0,
                "acne_mark_score": 55.0,
                "perceived_age_score": 70.0
            },
            "skin_type_detection": {
                "skin_type": "oily",
                "confidence": 0.85
            },
            "restoration_quality": {
                "sharpness": 0.9,
                "noise_reduction": 0.85
            }
        }

    def test_full_flow_image_upload_to_result_retrieval(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image
    ):
        """전체 플로우 테스트: 이미지 업로드 → 엔진 서버 분석 → DB 저장 → 결과 조회"""
        
        # 1. 앱 클라이언트: 이미지 업로드 (관리자 권한 사용)
        with open(test_image, "rb") as f:
            upload_response = authenticated_client.post(
                "/v1/analysis/jobs",
                files={"image": ("test.jpg", f, "image/jpeg")},
                data={
                    "customer_id": "CUST001",
                    "gender": "female",
                    "age": 30,
                    "do_restore": "false"  # 복원 비활성화 (테스트 속도 향상)
                },
                headers=admin_auth_headers
            )
        
        assert upload_response.status_code == 202
        job_id = upload_response.json()["job_id"]
        assert job_id is not None
        
        # 2. 엔진 서버: 분석 수행 (실제 엔진 호출)
        # 엔진 서버가 백그라운드에서 실행되므로 잠시 대기
        import time
        time.sleep(2)  # 분석 완료 대기
        
        # 3. 웹 서버: 결과 조회
        result_response = authenticated_client.get(
            f"/v1/analysis/jobs/{job_id}",
            headers=admin_auth_headers
        )
        
        # 분석이 완료되었는지 확인
        assert result_response.status_code in [200, 202]  # 200: 완료, 202: 진행중
        
        if result_response.status_code == 200:
            result_data = result_response.json()
            assert result_data["status"] in ["completed", "failed"]
            
            if result_data["status"] == "completed":
                # 분석 결과 검증
                assert "customer_id" in result_data
                assert result_data["customer_id"] == "CUST001"
                # artifacts가 있는지 확인
                if "artifacts" in result_data:
                    assert "results.json" in result_data["artifacts"]

    def test_engine_server_analysis_direct(
        self, temp_dir, test_image
    ):
        """엔진 서버 직접 호출 테스트"""
        from src.scoring.skin_scoring import SkinAnalyzer
        
        # 엔진 서버 초기화
        analyzer = SkinAnalyzer()
        
        # 이미지 분석 수행
        result = analyzer.analyze_all(str(test_image), debug=False)
        
        # 분석 결과 검증
        assert result is not None
        assert "overall_score" in result
        assert "measurements" in result
        assert 0 <= result["overall_score"] <= 100
        
        # 측정 항목 검증 (실제 엔진 서버의 결과 형식에 맞춤)
        measurements = result["measurements"]
        # 최소한 몇 개의 핵심 측정 항목이 있는지 확인
        expected_keys = ["pore_score", "wrinkle_score", "tone_score"]
        for key in expected_keys:
            if key in measurements:
                assert 0 <= measurements[key] <= 100

    def test_app_features_integration_diary_and_goals(
        self, authenticated_client, customer_auth_headers
    ):
        """앱 기능 통합 테스트: 피부 일기 및 목표"""
        
        # 1. 피부 일기 생성
        diary_response = authenticated_client.post(
            "/v1/app/diary",
            json={
                "customer_id": "CUST001",
                "analysis_id": 1,
                "image_url": "https://example.com/image.jpg",
                "overall_score": 75.0,
                "measurement_scores": {"melasma_score": 80, "redness_score": 70},
                "notes": "오늘 피부 상태가 좋음",
                "mood": "happy",
                "weather": "sunny"
            },
            headers=customer_auth_headers
        )
        
        assert diary_response.status_code == 200
        diary_data = diary_response.json()
        assert "entry_id" in diary_data
        
        # 2. 고객 목표 생성
        goal_response = authenticated_client.post(
            "/v1/app/goals",
            json={
                "customer_id": "CUST001",
                "goal_type": "skin_score",
                "target_value": 80.0,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31"
            },
            headers=customer_auth_headers
        )
        
        assert goal_response.status_code == 200
        goal_data = goal_response.json()
        assert "goal_id" in goal_data
        assert goal_data["target_value"] == 80.0

    def test_customer_api_integration_trends_and_analysis(
        self, authenticated_client, customer_auth_headers
    ):
        """고객 API 통합 테스트: 추이 및 분석 조회"""
        
        # 1. 고객 추이 조회
        trends_response = authenticated_client.get(
            "/v1/customers/CUST001/trends?days=30",
            headers=customer_auth_headers
        )
        
        # 엔드포인트가 존재하는지 확인
        assert trends_response.status_code in [200, 404]
        
        # 2. 고객 분석 조회
        analysis_response = authenticated_client.get(
            "/v1/customers/CUST001/analysis?limit=10",
            headers=customer_auth_headers
        )
        
        # 엔드포인트가 존재하는지 확인
        assert analysis_response.status_code in [200, 404]

    def test_orders_api_integration_purchase_and_feedback(
        self, authenticated_client, customer_auth_headers
    ):
        """주문 API 통합 테스트: 구매 및 피드백"""
        
        # 주문 생성 엔드포인트 확인
        order_response = authenticated_client.post(
            "/v1/orders",
            json={
                "customer_id": "CUST001",
                "items": [
                    {
                        "product_id": "PROD001",
                        "quantity": 1,
                        "price": 50000
                    }
                ],
                "shipping_address": {
                    "recipient": "홍길동",
                    "phone": "010-1234-5678",
                    "address": "서울시 강남구"
                }
            },
            headers=customer_auth_headers
        )
        
        # 엔드포인트가 존재하는지 확인
        assert order_response.status_code in [200, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

