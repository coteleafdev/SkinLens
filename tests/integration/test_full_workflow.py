"""
test_full_workflow.py — 전체 워크플로우 통합 테스트

실제 서버를 띄우고 전체 워크플로우를 테스트합니다.
"""
import pytest
import requests
import time
from pathlib import Path
from typing import Dict, Any

BASE_URL = "http://localhost:8000"


class TestFullWorkflow:
    """전체 워크플로우 테스트"""

    @pytest.fixture
    def auth_token(self):
        """인증 토큰 fixture"""
        login_resp = requests.post(
            f"{BASE_URL}/v1/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        assert login_resp.status_code == 200
        return login_resp.json()["access_token"]

    @pytest.fixture
    def headers(self, auth_token):
        """요청 헤더 fixture"""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_login(self):
        """로그인 테스트"""
        response = requests.post(
            f"{BASE_URL}/v1/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_create_customer(self, headers):
        """고객 정보 등록 테스트"""
        customer_data = {
            "customer_id": "integration_test_customer",
            "name": "통합 테스트 고객",
            "email": "integration_test@example.com",
            "phone": "010-1234-5678"
        }

        response = requests.post(
            f"{BASE_URL}/v1/customer",
            json=customer_data,
            headers=headers
        )

        # 이미 존재하는 경우 200, 새로 생성 시 201
        assert response.status_code in [200, 201]

    def test_create_analysis_job(self, headers):
        """분석 작업 생성 테스트"""
        # 테스트용 이미지 파일 경로
        image_path = Path("tests/fixtures/sample_image.jpg")

        # 이미지 파일이 없으면 테스트 스킵
        if not image_path.exists():
            pytest.skip(f"테스트 이미지 없음: {image_path}")

        with open(image_path, "rb") as f:
            files = {"image": ("sample.jpg", f, "image/jpeg")}
            data = {"customer_id": "integration_test_customer"}

            response = requests.post(
                f"{BASE_URL}/v1/analysis/jobs",
                files=files,
                data=data,
                headers=headers
            )

        assert response.status_code == 200
        job_data = response.json()
        assert "job_id" in job_data
        return job_data["job_id"]

    def test_get_job_status(self, headers):
        """작업 상태 조회 테스트"""
        # 먼저 작업 생성
        image_path = Path("tests/fixtures/sample_image.jpg")
        if not image_path.exists():
            pytest.skip(f"테스트 이미지 없음: {image_path}")

        with open(image_path, "rb") as f:
            files = {"image": ("sample.jpg", f, "image/jpeg")}
            data = {"customer_id": "integration_test_customer"}

            create_resp = requests.post(
                f"{BASE_URL}/v1/analysis/jobs",
                files=files,
                data=data,
                headers=headers
            )

        job_id = create_resp.json()["job_id"]

        # 작업 상태 조회
        response = requests.get(
            f"{BASE_URL}/v1/analysis/jobs/{job_id}",
            headers=headers
        )

        assert response.status_code == 200
        job_data = response.json()
        assert "job_id" in job_data
        assert "status" in job_data

    def test_list_jobs(self, headers):
        """작업 목록 조회 테스트"""
        response = requests.get(
            f"{BASE_URL}/v1/analysis/jobs",
            headers=headers
        )

        assert response.status_code == 200
        jobs = response.json()
        assert isinstance(jobs, list)

    def test_get_customer_info(self, headers):
        """고객 정보 조회 테스트"""
        response = requests.get(
            f"{BASE_URL}/v1/customer/integration_test_customer",
            headers=headers
        )

        assert response.status_code in [200, 404]  # 존재하지 않을 수 있음

    def test_health_check(self):
        """헬스 체크 테스트"""
        response = requests.get(f"{BASE_URL}/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_system_metrics(self, headers):
        """시스템 메트릭 조회 테스트"""
        response = requests.get(
            f"{BASE_URL}/v1/admin/metrics",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "cpu_usage" in data or "memory_usage" in data

    def test_custom_workflow(self, headers):
        """커스텀 워크플로우 테스트: 전체 프로세스 통합"""
        # 1. 고객 정보 등록
        customer_data = {
            "customer_id": "custom_workflow_test",
            "name": "커스텀 워크플로우 테스트",
            "email": "custom_workflow@example.com",
            "phone": "010-5555-5555"
        }
        
        response = requests.post(
            f"{BASE_URL}/v1/customer",
            json=customer_data,
            headers=headers
        )
        assert response.status_code in [200, 201]
        
        # 2. 설문조사 등록
        survey_data = {
            "customer_id": "custom_workflow_test",
            "skin_type": "normal",
            "skin_concerns": ["dryness", "wrinkles"],
            "sensitivity": "low",
            "lifestyle": {
                "sleep_hours": 7,
                "water_intake": 2.0,
                "stress_level": "medium"
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/v1/customer/survey",
            json=survey_data,
            headers=headers
        )
        assert response.status_code in [200, 201]
        
        # 3. 분석 작업 생성
        image_path = Path("tests/fixtures/sample_image.jpg")
        if not image_path.exists():
            pytest.skip(f"테스트 이미지 없음: {image_path}")
        
        with open(image_path, "rb") as f:
            files = {"image": ("sample.jpg", f, "image/jpeg")}
            data = {
                "customer_id": "custom_workflow_test",
                "survey_id": "test_survey"
            }
            
            response = requests.post(
                f"{BASE_URL}/v1/analysis/jobs",
                files=files,
                data=data,
                headers=headers
            )
        
        assert response.status_code == 200
        job_data = response.json()
        job_id = job_data["job_id"]
        
        # 4. 작업 완료 대기
        max_wait = 30  # 최대 30초 대기
        wait_interval = 2  # 2초 간격
        
        for i in range(max_wait // wait_interval):
            response = requests.get(
                f"{BASE_URL}/v1/analysis/jobs/{job_id}",
                headers=headers
            )
            assert response.status_code == 200
            status_data = response.json()
            status = status_data.get("status", "unknown")
            
            if status == "completed":
                break
            elif status == "failed":
                pytest.fail(f"작업 실패: {status_data}")
            
            time.sleep(wait_interval)
        else:
            pytest.fail(f"작업 완료 대기 시간 초과: {max_wait}초")
        
        # 5. 결과 조회 및 검증
        response = requests.get(
            f"{BASE_URL}/v1/analysis/jobs/{job_id}/result",
            headers=headers
        )
        assert response.status_code == 200
        result = response.json()
        
        # 결과 필드 검증
        assert "analysis_result" in result
        assert "overall_score" in result["analysis_result"]
        assert "measurements" in result["analysis_result"]
        
        # 점수 범위 검증
        overall_score = result["analysis_result"]["overall_score"]
        assert 0 <= overall_score <= 100


def run_manual_test():
    """수동 테스트 실행 함수"""
    print("=== 전체 워크플로우 수동 테스트 ===\n")

    # 1. 로그인
    print("1. 로그인...")
    login_resp = requests.post(
        f"{BASE_URL}/v1/auth/login",
        data={"customer_id": "admin", "password": "admin123"}
    )
    if login_resp.status_code != 200:
        print(f"로그인 실패: {login_resp.status_code}")
        return

    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("로그인 성공\n")

    # 2. 고객 정보 등록
    print("2. 고객 정보 등록...")
    customer_data = {
        "customer_id": "manual_test_customer",
        "name": "수동 테스트 고객",
        "email": "manual_test@example.com",
        "phone": "010-9876-5432"
    }
    customer_resp = requests.post(
        f"{BASE_URL}/v1/customer",
        json=customer_data,
        headers=headers
    )
    print(f"고객 등록 결과: {customer_resp.status_code}\n")

    # 3. 분석 작업 생성
    print("3. 분석 작업 생성...")
    image_path = Path("tests/fixtures/sample_image.jpg")
    if not image_path.exists():
        print(f"테스트 이미지 없음: {image_path}")
        print("테스트 이미지를 tests/fixtures/sample_image.jpg에 넣어주세요.")
        return

    with open(image_path, "rb") as f:
        files = {"image": ("sample.jpg", f, "image/jpeg")}
        data = {"customer_id": "manual_test_customer"}

        job_resp = requests.post(
            f"{BASE_URL}/v1/analysis/jobs",
            files=files,
            data=data,
            headers=headers
        )

    if job_resp.status_code != 200:
        print(f"작업 생성 실패: {job_resp.status_code}")
        print(job_resp.text)
        return

    job_id = job_resp.json()["job_id"]
    print(f"작업 생성 성공: {job_id}\n")

    # 4. 작업 상태 확인
    print("4. 작업 상태 확인...")
    for i in range(10):
        status_resp = requests.get(
            f"{BASE_URL}/v1/analysis/jobs/{job_id}",
            headers=headers
        )
        status_data = status_resp.json()
        status = status_data.get("status", "unknown")
        print(f"  상태: {status}")

        if status == "completed":
            print("작업 완료!\n")
            break
        elif status == "failed":
            print("작업 실패!\n")
            print(status_data)
            break

        time.sleep(2)
    else:
        print("작업 완료 대기 시간 초과\n")

    # 5. 결과 조회
    if status == "completed":
        print("5. 결과 조회...")
        result_resp = requests.get(
            f"{BASE_URL}/v1/analysis/jobs/{job_id}/result",
            headers=headers
        )
        if result_resp.status_code == 200:
            result = result_resp.json()
            print(f"결과: {result}\n")
        else:
            print(f"결과 조회 실패: {result_resp.status_code}\n")

    print("=== 테스트 완료 ===")


if __name__ == "__main__":
    run_manual_test()
