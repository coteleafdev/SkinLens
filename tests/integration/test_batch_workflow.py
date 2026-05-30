"""
test_batch_workflow.py — 배치 워크플로우 테스트

여러 테스트 케이스를 순차적으로 실행합니다.
"""
import pytest
import requests
import json
import time
from pathlib import Path
from typing import Dict, Any, List

BASE_URL = "http://localhost:8000"


class TestBatchWorkflow:
    """배치 워크플로우 테스트"""

    @pytest.fixture
    def auth_token(self):
        """인증 토큰 fixture"""
        login_resp = requests.post(
            f"{BASE_URL}/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        assert login_resp.status_code == 200
        return login_resp.json()["access_token"]

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

    def run_single_test(self, test_case: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """단일 테스트 케이스 실행"""
        print(f"\n테스트 케이스: {test_case['name']}")

        # 1. 고객 정보 등록
        customer_data = {
            "customer_id": test_case["customer_id"],
            "name": test_case["name"],
            "email": f"{test_case['customer_id']}@example.com",
            "phone": "010-0000-0000"
        }

        customer_resp = requests.post(
            f"{BASE_URL}/v3/customer",
            json=customer_data,
            headers=headers
        )
        print(f"  고객 등록: {customer_resp.status_code}")

        # 2. 분석 작업 생성
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

            job_resp = requests.post(
                f"{BASE_URL}/v3/analysis/jobs",
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

        # 3. 작업 완료 대기
        for i in range(30):  # 최대 60초 대기
            status_resp = requests.get(
                f"{BASE_URL}/v3/analysis/jobs/{job_id}",
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

        # 4. 결과 조회
        result_resp = requests.get(
            f"{BASE_URL}/v3/analysis/jobs/{job_id}/result",
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

    def test_batch_workflow(self, headers):
        """배치 워크플로우 테스트"""
        test_cases = self.load_test_cases()
        results = []

        for test_case in test_cases:
            result = self.run_single_test(test_case, headers)
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


def run_batch_test():
    """배치 테스트 수동 실행 함수"""
    print("=== 배치 워크플로우 수동 테스트 ===\n")

    # 1. 로그인
    print("로그인...")
    login_resp = requests.post(
        f"{BASE_URL}/v3/auth/login",
        data={"customer_id": "admin", "password": "admin123"}
    )
    if login_resp.status_code != 200:
        print(f"로그인 실패: {login_resp.status_code}")
        return

    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("로그인 성공\n")

    # 2. 테스트 케이스 로드
    test_cases_path = Path("tests/fixtures/test_cases.json")
    if not test_cases_path.exists():
        print(f"테스트 케이스 파일 없음: {test_cases_path}")
        return

    with open(test_cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        test_cases = data.get("test_cases", [])

    print(f"테스트 케이스 {len(test_cases)}개 로드\n")

    # 3. 배치 실행
    batch_tester = TestBatchWorkflow()
    results = []

    for test_case in test_cases:
        result = batch_tester.run_single_test(test_case, headers)
        results.append(result)

    # 4. 결과 요약
    print("\n=== 배치 테스트 결과 요약 ===")
    for result in results:
        status_emoji = {
            "completed": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "timeout": "⏰"
        }
        emoji = status_emoji.get(result["status"], "❓")
        print(f"{emoji} {result['name']}: {result['status']}")

    completed = sum(1 for r in results if r["status"] == "completed")
    total = len(results)
    print(f"\n완료: {completed}/{total}")

    # 5. 상세 결과 출력
    print("\n=== 상세 결과 ===")
    for result in results:
        if result["status"] == "completed":
            print(f"\n{result['name']}:")
            print(f"  예상: {result.get('expected', {})}")
            print(f"  실제: {result.get('result', {})}")


if __name__ == "__main__":
    run_batch_test()
