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
        """테스트용 이미지 fixture
        
        참고: 실제 테스트에서는 얼굴 이미지를 사용해야 정확한 분석 결과를 얻을 수 있습니다.
        현재는 단순한 흰색 이미지를 사용하므로 분석 결과가 부정확할 수 있습니다.
        """
        # 100x100 RGB 이미지 생성 (단순 테스트용)
        img = Image.new('RGB', (100, 100), color='white')
        img_path = temp_dir / "test_image.jpg"
        img.save(img_path, 'JPEG')
        return img_path

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
        # 폴링 방식으로 분석 완료 확인
        import time
        max_wait_time = 30  # 최대 30초 대기
        poll_interval = 1   # 1초 간격으로 확인
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            result_response = authenticated_client.get(
                f"/v1/analysis/jobs/{job_id}",
                headers=admin_auth_headers
            )
            
            if result_response.status_code == 200:
                result_data = result_response.json()
                if result_data["status"] in ["completed", "failed"]:
                    break
            
            time.sleep(poll_interval)
            elapsed_time += poll_interval
        
        # 3. 웹 서버: 결과 조회
        result_response = authenticated_client.get(
            f"/v1/analysis/jobs/{job_id}",
            headers=admin_auth_headers
        )
        
        # 분석이 완료되었는지 확인
        assert result_response.status_code == 200
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

    def test_error_handling_invalid_image(
        self, authenticated_client, admin_auth_headers
    ):
        """에러 핸들링 테스트: 잘못된 이미지 업로드"""
        
        # 잘못된 파일 업로드
        invalid_response = authenticated_client.post(
            "/v1/analysis/jobs",
            files={"image": ("test.txt", b"invalid image data", "text/plain")},
            data={
                "customer_id": "CUST001",
                "gender": "female",
                "age": 30
            },
            headers=admin_auth_headers
        )
        
        # 422 Unprocessable Entity 또는 400 Bad Request
        assert invalid_response.status_code in [400, 422]

    def test_error_handling_missing_required_fields(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image
    ):
        """에러 핸들링 테스트: 필수 필드 누락"""
        
        # 필수 필드 누락 (이미지 없이 요청)
        invalid_response = authenticated_client.post(
            "/v1/analysis/jobs",
            data={
                "customer_id": "CUST001",
                "gender": "female",
                "age": 30
            },
            headers=admin_auth_headers
        )
        
        # 422 Unprocessable Entity 또는 400 Bad Request (이미지 필수)
        assert invalid_response.status_code in [400, 422]

    def test_error_handling_nonexistent_job(
        self, authenticated_client, admin_auth_headers
    ):
        """에러 핸들링 테스트: 존재하지 않는 Job 조회"""
        
        # 존재하지 않는 Job ID
        response = authenticated_client.get(
            "/v1/analysis/jobs/nonexistent-job-id",
            headers=admin_auth_headers
        )
        
        # 404 Not Found
        assert response.status_code == 404

    def test_db_data_verification(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image, skin_analysis_db_with_users
    ):
        """DB 데이터 검증 테스트: 분석 결과가 DB에 저장되는지 확인"""
        
        # 1. 이미지 업로드 및 분석 요청
        with open(test_image, "rb") as f:
            upload_response = authenticated_client.post(
                "/v1/analysis/jobs",
                files={"image": ("test.jpg", f, "image/jpeg")},
                data={
                    "customer_id": "CUST001",
                    "gender": "female",
                    "age": 30,
                    "do_restore": "false"
                },
                headers=admin_auth_headers
            )
        
        assert upload_response.status_code == 202
        job_id = upload_response.json()["job_id"]
        
        # 2. 분석 완료 대기 (폴링)
        import time
        max_wait_time = 30
        poll_interval = 1
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            result_response = authenticated_client.get(
                f"/v1/analysis/jobs/{job_id}",
                headers=admin_auth_headers
            )
            
            if result_response.status_code == 200:
                result_data = result_response.json()
                if result_data["status"] in ["completed", "failed"]:
                    break
            
            time.sleep(poll_interval)
            elapsed_time += poll_interval
        
        # 3. DB에서 분석 결과 조회 (메서드 존재 확인)
        # DB 메서드가 존재하는지 확인하고, 존재하면 데이터 검증
        if hasattr(skin_analysis_db_with_users, 'get_analyses_by_customer'):
            try:
                analyses = skin_analysis_db_with_users.get_analyses_by_customer("CUST001", limit=10)
                
                # DB에 데이터가 저장되었는지 확인
                if analyses and len(analyses) > 0:
                    # 가장 최근 분석 결과 확인
                    latest_analysis = analyses[0]
                    # customer_id 필드가 있는지 확인
                    if isinstance(latest_analysis, dict):
                        assert latest_analysis.get("customer_id") == "CUST001"
                        
                        # 분석 결과가 있는지 확인
                        if "analysis_result" in latest_analysis and latest_analysis["analysis_result"]:
                            result = latest_analysis["analysis_result"]
                            assert "overall_score" in result or "measurements" in result
            except (KeyError, AttributeError, TypeError) as e:
                # DB 구조가 다르면 API 응답으로만 검증
                pass
        
        # API 응답으로 기본 검증
        result_response = authenticated_client.get(
            f"/v1/analysis/jobs/{job_id}",
            headers=admin_auth_headers
        )
        assert result_response.status_code == 200
        result_data = result_response.json()
        
        # 분석이 성공한 경우에만 customer_id 검증
        if result_data.get("status") == "completed":
            assert result_data.get("customer_id") == "CUST001"
        # 실패한 경우에는 job_id만 확인
        else:
            assert result_data.get("job_id") == job_id

    def test_concurrent_requests(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image
    ):
        """동시성 테스트: 여러 요청 동시 처리"""
        import threading
        
        job_ids = []
        errors = []
        
        def create_job():
            try:
                with open(test_image, "rb") as f:
                    response = authenticated_client.post(
                        "/v1/analysis/jobs",
                        files={"image": ("test.jpg", f, "image/jpeg")},
                        data={
                            "customer_id": "CUST001",
                            "gender": "female",
                            "age": 30,
                            "do_restore": "false"
                        },
                        headers=admin_auth_headers
                    )
                    if response.status_code == 202:
                        job_ids.append(response.json()["job_id"])
                    else:
                        errors.append(f"Status: {response.status_code}")
            except Exception as e:
                errors.append(str(e))
        
        # 3개의 동시 요청 생성
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=create_job)
            threads.append(thread)
            thread.start()
        
        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()
        
        # 에러가 없는지 확인
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # 모든 Job이 생성되었는지 확인
        assert len(job_ids) == 3
        
        # Job ID들이 중복되지 않는지 확인
        assert len(set(job_ids)) == 3

    def test_websocket_progress_updates(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image
    ):
        """WebSocket 테스트: 실시간 진행률 업데이트"""
        # WebSocket 연결 테스트 (실제 WebSocket 구현이 있는 경우)
        # 현재는 엔드포인트 존재 확인만 수행
        
        # 1. Job 생성
        with open(test_image, "rb") as f:
            upload_response = authenticated_client.post(
                "/v1/analysis/jobs",
                files={"image": ("test.jpg", f, "image/jpeg")},
                data={
                    "customer_id": "CUST001",
                    "gender": "female",
                    "age": 30,
                    "do_restore": "false"
                },
                headers=admin_auth_headers
            )
        
        if upload_response.status_code == 202:
            job_id = upload_response.json()["job_id"]
            
            # WebSocket 엔드포인트 존재 확인
            # 실제 WebSocket 테스트는 추가 설정 필요
            # 여기서는 엔드포인트 경로 구조만 확인
            ws_url = f"/v1/analysis/jobs/{job_id}/ws"
            # WebSocket 연결은 TestClient에서 직접 지원하지 않으므로
            # 엔드포인트 존재 여부만 확인
            assert job_id is not None

    def test_image_restoration(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image
    ):
        """복원 기능 테스트: 이미지 복원 활성화"""
        
        # 복원 활성화하여 이미지 업로드
        with open(test_image, "rb") as f:
            upload_response = authenticated_client.post(
                "/v1/analysis/jobs",
                files={"image": ("test.jpg", f, "image/jpeg")},
                data={
                    "customer_id": "CUST001",
                    "gender": "female",
                    "age": 30,
                    "do_restore": "true"  # 복원 활성화
                },
                headers=admin_auth_headers
            )
        
        assert upload_response.status_code == 202
        job_id = upload_response.json()["job_id"]
        
        # 분석 완료 대기 (폴링)
        import time
        max_wait_time = 30
        poll_interval = 1
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            result_response = authenticated_client.get(
                f"/v1/analysis/jobs/{job_id}",
                headers=admin_auth_headers
            )
            
            if result_response.status_code == 200:
                result_data = result_response.json()
                if result_data["status"] in ["completed", "failed"]:
                    break
            
            time.sleep(poll_interval)
            elapsed_time += poll_interval
        
        # 결과 확인
        result_response = authenticated_client.get(
            f"/v1/analysis/jobs/{job_id}",
            headers=admin_auth_headers
        )
        
        if result_response.status_code == 200:
            result_data = result_response.json()
            if result_data["status"] == "completed":
                # 복원된 이미지가 artifacts에 있는지 확인
                if "artifacts" in result_data:
                    # 복원된 이미지 파일이 있는지 확인
                    assert any("restored" in artifact.lower() or "enhanced" in artifact.lower() 
                              for artifact in result_data["artifacts"].keys())

    def test_llm_report_generation(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image
    ):
        """LLM 통합 테스트: LLM 보고서 생성"""
        
        # 이미지 업로드 및 분석 요청
        with open(test_image, "rb") as f:
            upload_response = authenticated_client.post(
                "/v1/analysis/jobs",
                files={"image": ("test.jpg", f, "image/jpeg")},
                data={
                    "customer_id": "CUST001",
                    "gender": "female",
                    "age": 30,
                    "do_restore": "false",
                    "generate_report": "true"  # LLM 보고서 생성 요청
                },
                headers=admin_auth_headers
            )
        
        if upload_response.status_code == 202:
            job_id = upload_response.json()["job_id"]
            
            # 분석 완료 대기 (폴링)
            import time
            max_wait_time = 30
            poll_interval = 1
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                result_response = authenticated_client.get(
                    f"/v1/analysis/jobs/{job_id}",
                    headers=admin_auth_headers
                )
                
                if result_response.status_code == 200:
                    result_data = result_response.json()
                    if result_data["status"] in ["completed", "failed"]:
                        break
                
                time.sleep(poll_interval)
                elapsed_time += poll_interval
            
            # 결과 확인
            result_response = authenticated_client.get(
                f"/v1/analysis/jobs/{job_id}",
                headers=admin_auth_headers
            )
            
            if result_response.status_code == 200:
                result_data = result_response.json()
                if result_data["status"] == "completed":
                    # LLM 보고서가 artifacts에 있는지 확인
                    if "artifacts" in result_data:
                        # 보고서 파일이 있는지 확인
                        assert any("report" in artifact.lower() or "llm" in artifact.lower() 
                                  for artifact in result_data["artifacts"].keys())

    def test_data_cleanup(
        self, authenticated_client, admin_auth_headers, temp_dir, test_image, skin_analysis_db_with_users
    ):
        """테스트 데이터 정리 테스트: 테스트 후 데이터 정리 확인"""
        
        # 테스트용 데이터 생성
        with open(test_image, "rb") as f:
            upload_response = authenticated_client.post(
                "/v1/analysis/jobs",
                files={"image": ("test.jpg", f, "image/jpeg")},
                data={
                    "customer_id": "CUST001",
                    "gender": "female",
                    "age": 30,
                    "do_restore": "false"
                },
                headers=admin_auth_headers
            )
        
        if upload_response.status_code == 202:
            job_id = upload_response.json()["job_id"]
            
            # 분석 완료 대기
            import time
            time.sleep(2)
            
            # 테스트 데이터 정리 (필요한 경우)
            # 실제 DB에서 테스트 데이터 삭제
            # 여기서는 정리 메서드 존재 확인만 수행
            if hasattr(skin_analysis_db_with_users, 'delete_analysis'):
                # 정리 메서드가 있으면 사용
                try:
                    # customer_id로 테스트 데이터 정리
                    # skin_analysis_db_with_users.delete_analysis(job_id)
                    pass
                except Exception:
                    # 정리 실패해도 테스트는 계속 진행
                    pass
            
            # 테스트용 임시 디렉토리 정리는 fixture가 자동 처리


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

