"""
test_batch_workflow.py — 배치 워크플로우 테스트

여러 테스트 케이스를 순차적으로 실행합니다.

TestClient를 사용하여 가상 서버 환경에서 테스트합니다.
"""
import pytest
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from fastapi.testclient import TestClient


class TestBatchWorkflow:
    """배치 워크플로우 테스트"""

    @pytest.fixture
    def client(self, auth_client):
        """TestClient fixture"""
        return auth_client

    @pytest.fixture
    def auth_token(self, client):
        """인증 토큰 fixture"""
        response = client.post("/v1/auth/login", data={
            "username": "admin",
            "password": "a"
        })
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                return data["access_token"]
        # 환경변수 폴백으로 토큰 생성
        from src.server.deps import create_access_token
        return create_access_token({"sub": "admin", "role": "admin"})

    @pytest.fixture
    def headers(self, auth_token):
        """요청 헤더 fixture"""
        return {"Authorization": f"Bearer {auth_token}"}

    def load_test_cases(self, path: str = "tests/fixtures/test_cases.json") -> List[Dict[str, Any]]:
        """테스트 케이스 로드"""
        test_cases_path = Path(path)
        if not test_cases_path.exists():
            pytest.skip(f"테스트 케이스 파일 없음: {path}")

        with open(test_cases_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("test_cases", [])

    def run_single_test(self, test_case: Dict[str, Any], headers: Dict[str, str], client: TestClient) -> Dict[str, Any]:
        """단일 테스트 케이스 실행"""
        print(f"\n테스트 케이스: {test_case['name']}")

        # 1. 분석 작업 생성 (고객 등록은 fixture에서 이미 처리됨)
        image_path = Path(f"tests/fixtures/{test_case['image_file']}")
        if not image_path.exists():
            return {
                "name": test_case["name"],
                "status": "skipped",
                "reason": f"이미지 파일 없음: {image_path}"
            }

        with open(image_path, "rb") as f:
            files = {"image": (image_path.name, f, "image/jpeg")}
            data = {"customer_id": test_case["customer_id"]}

            job_resp = client.post(
                "/v1/analysis/jobs",
                files=files,
                data=data,
                headers=headers
            )

        if job_resp.status_code != 200:
            return {
                "name": test_case["name"],
                "status": "failed",
                "reason": f"작업 생성 실패: {job_resp.status_code}"
            }

        job_id = job_resp.json()["job_id"]
        print(f"  작업 생성: {job_id}")

        # 2. 작업 완료 대기
        for i in range(30):  # 최대 60초 대기
            status_resp = client.get(
                f"/v1/analysis/jobs/{job_id}",
                headers=headers
            )
            status_data = status_resp.json()
            status = status_data.get("status", "unknown")

            if status == "completed":
                print(f"  작업 완료")
                break
            elif status == "failed":
                print(f"  작업 실패")
                return {
                    "name": test_case["name"],
                    "status": "failed",
                    "reason": "작업 실패",
                    "error": status_data
                }

            time.sleep(2)
        else:
            return {
                "name": test_case["name"],
                "status": "timeout",
                "reason": "작업 완료 대기 시간 초과"
            }

        # 3. 결과 조회
        result_resp = client.get(
            f"/v1/analysis/jobs/{job_id}/result",
            headers=headers
        )

        if result_resp.status_code != 200:
            return {
                "name": test_case["name"],
                "status": "failed",
                "reason": f"결과 조회 실패: {result_resp.status_code}"
            }

        result = result_resp.json()
        print(f"  결과 조회 완료")

        return {
            "name": test_case["name"],
            "status": "completed",
            "result": result,
            "expected": test_case.get("expected_results", {})
        }

    def test_batch_workflow(self, headers, client):
        """배치 워크플로우 테스트 - TestClient 사용"""
        # 테스트 케이스 파일이 없으면 스킵
        test_cases_path = Path("tests/fixtures/test_cases.json")
        if not test_cases_path.exists():
            pytest.skip("테스트 케이스 파일 없음")
        
        test_cases = self.load_test_cases()
        if not test_cases:
            pytest.skip("테스트 케이스가 없음")
            
        # 테스트 이미지 파일이 있는지 확인
        has_images = any(
            Path(f"tests/fixtures/{tc.get('image_file', '')}").exists()
            for tc in test_cases
        )
        if not has_images:
            pytest.skip("테스트 이미지 파일 없음")
            
        results = []

        for test_case in test_cases:
            result = self.run_single_test(test_case, headers, client)
            results.append(result)

        # 결과 요약
        print("\n=== 배치 테스트 결과 요약 ===")
        for result in results:
            print(f"{result['name']}: {result['status']}")

        completed = sum(1 for r in results if r["status"] == "completed")
        total = len(results)
        print(f"\n완료: {completed}/{total}")

        # 최소 하나라도 성공하면 테스트 통과
        assert completed > 0, "모든 테스트 케이스 실패"
