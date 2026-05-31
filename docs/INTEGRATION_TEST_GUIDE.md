# 통합 테스트 가이드 (Integration Test Guide)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

실제 서버 운용 환경에서 고객 정보와 원본 사진을 입력으로 주어 결과가 제대로 나오는지 시뮬레이션하는 방법을 설명합니다.

---

## 개요

통합 테스트는 실제 서버를 띄우고 전체 워크플로우를 테스트하여 시스템이 예상대로 동작하는지 확인합니다.

**테스트 범위:**
- 인증 (로그인)
- 고객 정보 등록 및 조회
- 이미지 업로드 및 분석 작업 생성
- 작업 상태 모니터링
- 분석 결과 조회
- 시스템 헬스 체크

---

## 전제 조건

### 1. 서버 실행

테스트를 실행하기 전에 서버가 실행 중이어야 합니다.

```bash
# 개발 모드
python -m src.server.server

# 또는 uvicorn 사용
uvicorn src.server.server:app --reload
```

서버가 정상적으로 실행되면 다음 URL로 접근할 수 있어야 합니다:
- Base URL: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

### 2. 테스트 이미지 준비

테스트용 이미지 파일을 `tests/fixtures/` 디렉토리에 준비하세요.

```
tests/fixtures/
├── normal_skin.jpg          # 정상 피부
├── acne_skin.jpg            # 여드름 피부
├── pigmentation_skin.jpg    # 색소침착 피부
├── aging_skin.jpg           # 노화 피부
└── sample_image.jpg         # 일반 테스트용
```

**이미지 요구사항:**
- 형식: JPG, PNG
- 크기: 권장 1024x1024 이상
- 내용: 다양한 피부 타입 (정상, 여드름, 색소침착, 노화 등)

---

## 테스트 파일 구조

```
tests/
├── integration/
│   ├── __init__.py
│   ├── test_full_workflow.py      # 단일 워크플로우 테스트
│   ├── test_batch_workflow.py     # 배치 테스트
│   └── README.md                  # 테스트 파일 설명
└── fixtures/
    ├── __init__.py
    └── test_cases.json            # 테스트 케이스 설정
```

---

## 테스트 스크립트

### 1. 단일 워크플로우 테스트 (test_full_workflow.py)

전체 워크플로우를 하나씩 순차적으로 테스트합니다.

**테스트 항목:**
- 로그인
- 고객 정보 등록
- 분석 작업 생성 (이미지 업로드)
- 작업 상태 조회
- 작업 목록 조회
- 고객 정보 조회
- 헬스 체크
- 시스템 메트릭 조회

**pytest로 실행:**
```bash
pytest tests/integration/test_full_workflow.py -v
```

**수동으로 실행:**
```bash
python tests/integration/test_full_workflow.py
```

**실행 예시:**
```
=== 전체 워크플로우 수동 테스트 ===

1. 로그인...
로그인 성공

2. 고객 정보 등록...
고객 등록 결과: 200

3. 분석 작업 생성...
작업 생성 성공: abc123-def456-ghi789

4. 작업 상태 확인...
  상태: processing
  상태: processing
  상태: completed
작업 완료!

5. 결과 조회...
결과: {"skin_type": "normal", "scores": {...}}

=== 테스트 완료 ===
```

### 2. 배치 테스트 (test_batch_workflow.py)

여러 테스트 케이스를 순차적으로 실행하여 다양한 시나리오를 테스트합니다.

**테스트 케이스 설정:**
`tests/fixtures/test_cases.json` 파일에서 테스트 케이스를 설정합니다.

```json
{
  "test_cases": [
    {
      "name": "정상 피부 테스트",
      "customer_id": "test_normal_skin",
      "image_file": "normal_skin.jpg",
      "expected_results": {
        "skin_type": "normal",
        "trouble_score": {
          "acne": "low",
          "redness": "low",
          "pigmentation": "low"
        }
      }
    },
    {
      "name": "여드름 피부 테스트",
      "customer_id": "test_acne_skin",
      "image_file": "acne_skin.jpg",
      "expected_results": {
        "skin_type": "acne",
        "trouble_score": {
          "acne": "high",
          "redness": "medium",
          "pigmentation": "low"
        }
      }
    }
  ]
}
```

**pytest로 실행:**
```bash
pytest tests/integration/test_batch_workflow.py -v
```

**수동으로 실행:**
```bash
python tests/integration/test_batch_workflow.py
```

**실행 예시:**
```
=== 배치 워크플로우 수동 테스트 ===

로그인...
로그인 성공

테스트 케이스 2개 로드

테스트 케이스: 정상 피부 테스트
  고객 등록: 200
  작업 생성: abc123
  작업 완료
  결과 조회 완료

테스트 케이스: 여드름 피부 테스트
  고객 등록: 200
  작업 생성: def456
  작업 완료
  결과 조회 완료

=== 배치 테스트 결과 요약 ===
✅ 정상 피부 테스트: completed
✅ 여드름 피부 테스트: completed

완료: 2/2

=== 상세 결과 ===

정상 피부 테스트:
  예상: {"skin_type": "normal", ...}
  실제: {"skin_type": "normal", ...}

여드름 피부 테스트:
  예상: {"skin_type": "acne", ...}
  실제: {"skin_type": "acne", ...}
```

---

## 사용 방법

### 방법 1: pytest로 실행 (권장)

```bash
# 전체 통합 테스트
pytest tests/integration/ -v

# 특정 테스트 파일만
pytest tests/integration/test_full_workflow.py -v

# 특정 테스트 메서드만
pytest tests/integration/test_full_workflow.py::TestFullWorkflow::test_login -v

# 상세 출력
pytest tests/integration/ -v -s
```

### 방법 2: 수동으로 실행

```bash
# 단일 워크플로우 테스트
python tests/integration/test_full_workflow.py

# 배치 테스트
python tests/integration/test_batch_workflow.py
```

### 방법 3: Python 코드에서 직접 실행

```python
from tests.integration.test_full_workflow import run_manual_test

# 단일 테스트 실행
run_manual_test()
```

---

## 테스트 케이스 추가

### 새로운 테스트 케이스 추가 (test_cases.json)

```json
{
  "test_cases": [
    {
      "name": "새로운 테스트 케이스",
      "customer_id": "test_new_case",
      "image_file": "new_test_image.jpg",
      "expected_results": {
        "skin_type": "expected_type",
        "trouble_score": {
          "acne": "low",
          "redness": "low",
          "pigmentation": "low"
        }
      }
    }
  ]
}
```

### 새로운 테스트 메서드 추가 (test_full_workflow.py)

```python
def test_custom_workflow(self, headers):
    """커스텀 워크플로우 테스트"""
    # 1. 고객 정보 등록
    customer_data = {
        "customer_id": "custom_test",
        "name": "커스텀 테스트",
        "email": "custom@example.com",
        "phone": "010-0000-0000"
    }
    response = requests.post(
        f"{BASE_URL}/v1/customer",
        json=customer_data,
        headers=headers
    )
    assert response.status_code in [200, 201]

    # 2. 추가 테스트 로직
    # ...
```

---

## 문제 해결

### 1. 서버 연결 실패

**에러 메시지:**
```
ConnectionError: Failed to establish connection
```

**해결 방법:**
- 서버가 실행 중인지 확인: `http://localhost:8000`
- 방화벽 설정 확인
- 포트가 다른 경우 `BASE_URL` 변수 수정

### 2. 인증 실패

**에러 메시지:**
```
401 Unauthorized
```

**해결 방법:**
- admin 계정이 존재하는지 확인
- 비밀번호가 올바른지 확인 (기본: admin123)
- JWT 토큰이 만료되지 않았는지 확인

### 3. 이미지 파일 없음

**에러 메시지:**
```
테스트 이미지 없음: tests/fixtures/sample_image.jpg
```

**해결 방법:**
- `tests/fixtures/` 디렉토리에 이미지 파일을 넣으세요
- 이미지 파일명이 `test_cases.json` 설정과 일치하는지 확인

### 4. 작업 타임아웃

**에러 메시지:**
```
작업 완료 대기 시간 초과
```

**해결 방법:**
- 작업이 너무 오래 걸리는지 확인
- 대기 시간을 늘리기 위해 코드 수정
- 서버 로그에서 작업 실패 원인 확인

### 5. 고객 이미 존재

**에러 메시지:**
```
고객이 이미 존재합니다
```

**해결 방법:**
- 이미 존재하는 고객 ID를 사용하는 경우 정상 동작 (200 반환)
- 새로운 고객 ID를 사용하세요

---

## 커스터마이징

### 다른 서버 URL 사용

`BASE_URL` 변수를 수정하세요:

```python
# tests/integration/test_full_workflow.py
BASE_URL = "http://your-server:8000"

# tests/integration/test_batch_workflow.py
BASE_URL = "http://your-server:8000"
```

### 다른 인증 정보 사용

```python
login_resp = requests.post(
    f"{BASE_URL}/v1/auth/login",
    data={"customer_id": "your_id", "password": "your_password"}
)
```

### 대기 시간 조정

```python
# 작업 완료 대기 시간 (초)
for i in range(30):  # 60초 대기
    # ...
    time.sleep(2)
```

---

## CI/CD 통합

### GitHub Actions 예시

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements-core.txt
          pip install pytest requests
      - name: Start server
        run: python -m src.server.server &
      - name: Wait for server
        run: sleep 10
      - name: Run integration tests
        run: pytest tests/integration/ -v
```

---

## 참고 문서

- **API 레퍼런스**: `docs/api/API_REFERENCE.md`
- **보안 가이드**: `docs/ops/SECURITY_GUIDE.md`
- **데이터 모델**: `docs/db/DATA_MODEL.md`
- **단위 테스트**: `tests/README_SERVER_TESTS.md`

---

## 지원

테스트 실행 중 문제가 발생하면:

1. 서버 로그 확인
2. 테스트 이미지 파일 확인
3. API 레퍼런스 확인
4. 이슈 트래커에 문제 보고

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
