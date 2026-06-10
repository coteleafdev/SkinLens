# 통합 테스트 가이드

실제 서버를 띄우고 전체 워크플로우를 테스트하는 방법입니다.

## 전제 조건

1. 서버가 실행 중이어야 합니다:
   ```bash
   python -m src.server.server
   ```
   또는
   ```bash
   uvicorn src.server.server:app --reload
   ```

2. 테스트용 이미지 파일이 필요합니다:
   ```
   tests/fixtures/
   ├── normal_skin.jpg
   ├── acne_skin.jpg
   ├── pigmentation_skin.jpg
   └── aging_skin.jpg
   ```

## 테스트 파일

### 1. test_full_workflow.py

단일 워크플로우를 테스트합니다.

**pytest로 실행:**
```bash
pytest tests/integration/test_full_workflow.py -v
```

**수동으로 실행:**
```bash
python tests/integration/test_full_workflow.py
```

**테스트 항목:**
- 로그인
- 고객 정보 등록
- 분석 작업 생성
- 작업 상태 조회
- 작업 목록 조회
- 고객 정보 조회
- 헬스 체크
- 시스템 메트릭 조회

### 2. test_batch_workflow.py

여러 테스트 케이스를 순차적으로 실행합니다.

**pytest로 실행:**
```bash
pytest tests/integration/test_batch_workflow.py -v
```

**수동으로 실행:**
```bash
python tests/integration/test_batch_workflow.py
```

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
    }
  ]
}
```

## 테스트 이미지 준비

테스트 이미지를 `tests/fixtures/` 디렉토리에 넣으세요.

**이미지 요구사항:**
- 형식: JPG, PNG
- 크기: 권장 1024x1024 이상
- 내용: 다양한 피부 타입 (정상, 여드름, 색소침착, 노화 등)

## 사용 예시

### 단일 테스트 실행

```bash
# 서버 시작
python -m src.server.server

# 다른 터미널에서 테스트 실행
python tests/integration/test_full_workflow.py
```

### 배치 테스트 실행

```bash
# 테스트 케이스 설정
# tests/fixtures/test_cases.json 수정

# 배치 테스트 실행
python tests/integration/test_batch_workflow.py
```

### pytest로 실행

```bash
# 전체 통합 테스트
pytest tests/integration/ -v

# 특정 테스트만
pytest tests/integration/test_full_workflow.py::TestFullWorkflow::test_login -v
```

## 결과 확인

테스트 결과는 콘솔에 출력됩니다.

**성공한 경우:**
```
=== 전체 워크플로우 수동 테스트 ===

1. 로그인...
로그인 성공

2. 고객 정보 등록...
고객 등록 결과: 200

3. 분석 작업 생성...
작업 생성 성功: abc123

4. 작업 상태 확인...
  상태: processing
  상태: completed
작업 완료!

5. 결과 조회...
결�: {...}

=== 테스트 완료 ===
```

**실패한 경우:**
- 로그인 실패: 서버가 실행 중인지 확인
- 이미지 업로드 실패: 이미지 파일이 있는지 확인
- 작업 타임아웃: 작업이 너무 오래 걸리는지 확인

## 문제 해결

### 서버 연결 실패
```
ConnectionError: Failed to establish connection
```
- 서버가 실행 중인지 확인: `http://localhost:8000`
- 방화벽 설정 확인

### 인증 실패
```
401 Unauthorized
```
- admin 계정이 존재하는지 확인
- 비밀번호가 올바른지 확인

### 이미지 파일 없음
```
테스트 이미지 없음: tests/fixtures/sample_image.jpg
```
- `tests/fixtures/` 디렉토리에 이미지 파일을 넣으세요

## 추가 기능

### 커스텀 테스트 케이스 추가

`test_full_workflow.py`에 새로운 테스트 메서드를 추가하세요:

```python
def test_custom_workflow(self, headers):
    """커스텀 워크플로우 테스트: 전체 프로세스 통합"""
    # 1. 고객 정보 등록
    # 2. 설문조사 등록
    # 3. 분석 작업 생성
    # 4. 작업 완료 대기
    # 5. 결과 조회 및 검증
    # 구현 완료됨 (2026-06-10)
```

### 다른 서버 URL 사용

`BASE_URL` 변수를 수정하세요:

```python
BASE_URL = "http://your-server:8000"
```

## 참고

- API 레퍼런스: `docs/api/API_REFERENCE.md`
- 보안 가이드: `docs/ops/SECURITY_GUIDE.md`
- 단위 테스트: `tests/` 디렉토리
