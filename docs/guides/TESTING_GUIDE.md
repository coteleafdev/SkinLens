# 테스트 가이드 (Testing Guide)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.6  
> **작성일:** 2026-05-30  
> **상태:** 초안

---

## 개요

SkinLens 테스트 작성 및 실행 방법입니다.

---

## 1. 테스트 구조

```
tests/
├── test_analyzers.py              # 분석기 단위 테스트
├── test_app_features_api.py       # 앱 기능 API 테스트 (피부 일기, 목표, 업적, 구독, 챌린지)
├── test_auth_api.py               # 인증 API 테스트
├── test_admin_api.py              # 관리자 API 테스트
├── test_customer_api.py           # 고객 API 테스트
├── test_db_api.py                 # 데이터베이스 API 테스트
├── test_enhancements_api.py       # 향상 기능 API 테스트
├── test_full_integration.py       # 전체 시스템 통합 테스트 (앱-엔진서버-웹서버-DB)
├── test_health_api.py             # 헬스 체크 API 테스트
├── test_integration_api.py        # 통합 API 테스트
├── test_logs_api.py               # 로그 API 테스트
├── test_orders_api.py             # 주문 API 테스트
├── test_repository_llm_api.py     # LLM 저장소 API 테스트
├── test_stats_api.py              # 통계 API 테스트
├── test_server.py                 # 서버 통합 테스트 (jobs 라우터 포함)
├── test_upload.py                 # 업로드 테스트
├── test_*.py                      # 기타 단위 테스트
└── fixtures/                      # 테스트 데이터
    ├── images/
    └── json/
```

---

## 2. 단위 테스트

### 2.1 분석기 테스트

```python
# tests/unit/test_analyzer.py
import pytest
from src.scoring.skin_scoring import SkinAnalyzer

def test_analyzer_initialization():
    analyzer = SkinAnalyzer()
    assert analyzer is not None

def test_analyze_all():
    analyzer = SkinAnalyzer()
    result = analyzer.analyze_all("tests/fixtures/images/test.jpg", debug=True)
    assert "overall_score" in result
    assert "measurements" in result
    assert 0 <= result["overall_score"] <= 100

def test_measurements_range():
    analyzer = SkinAnalyzer()
    result = analyzer.analyze_all("tests/fixtures/images/test.jpg", debug=True)
    
    for key, value in result["measurements"].items():
        assert 0 <= value <= 100, f"{key} score out of range: {value}"
```

### 2.2 복원기 테스트

```python
# tests/unit/test_restorer.py
import pytest
from pathlib import Path
from src.restoration.pipeline import run_enhancement_pipeline

def test_enhancement_pipeline():
    cfg = {
        "restorer": "codeformer",
        "codeformer_fidelity": 0.7
    }
    
    result = run_enhancement_pipeline(
        cfg=cfg,
        out_dir=Path("tests/fixtures/output"),
        input_image=Path("tests/fixtures/images/test.jpg"),
        do_restore=True
    )
    
    assert result.restored is not None
    assert result.restored.exists()
```

### 2.3 LLM 테스트

```python
# tests/unit/test_llm.py
import pytest
from unittest.mock import patch, MagicMock
from src.llm.providers import GeminiProvider

@patch('google.generativeai.configure')
def test_gemini_provider_init(mock_configure):
    provider = GeminiProvider(
        api_key="test_key",
        model_name="gemini-2.5-flash"
    )
    assert provider.api_key == "test_key"
    assert provider.model_name == "gemini-2.5-flash"

@patch('google.generativeai.GenerativeModel')
def test_generate_content(mock_model):
    mock_response = MagicMock()
    mock_response.text = "Test response"
    mock_model.return_value.generate.return_value = mock_response
    
    provider = GeminiProvider(api_key="test_key", model_name="gemini-2.5-flash")
    result = provider.generate_content("Test prompt")
    
    assert result == "Test response"
```

---

## 3. 통합 테스트

### 3.1 파이프라인 테스트

```python
# tests/integration/test_pipeline.py
import pytest
from pathlib import Path
from src.cli.skin_analysis_cli import run_analysis_pipeline

def test_full_pipeline():
    result = run_analysis_pipeline(
        input_image=Path("tests/fixtures/images/test.jpg"),
        output_dir=Path("tests/fixtures/output"),
        do_restore=True,
        debug=True,
        include_base64=False,
        llm_report=False  # 테스트에서는 LLM 비활성화
    )
    
    assert result is not None
    assert "input_image" in result
    assert "restored_image" in result
    assert "analysis_result" in result
    assert "customer_info" in result
```

### 3.2 DB 테스트

```python
# tests/integration/test_db.py
import pytest
from src.db.skin_analysis_db import SkinAnalysisDB
import tempfile
import os

def test_save_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = SkinAnalysisDB(db_path=db_path)
        
        # 저장
        analysis_id = db.save_analysis(
            original_path="/path/to/input.jpg",
            restored_path="/path/to/output.jpg",
            json_result={"overall_score": 75},
            customer_id="CUST001"
        )
        
        # 조회
        analyses = db.get_analyses_by_customer("CUST001")
        assert len(analyses) == 1
        assert analyses[0]["overall_score"] == 75
```

---

## 4. E2E 테스트

### 4.1 서버 E2E 테스트

```python
# tests/e2e/test_server.py
import pytest
from fastapi.testclient import TestClient
from src.server.main import app

client = TestClient(app)

def test_create_job():
    response = client.post(
        "/v1/analysis/jobs",
        files={"image": open("tests/fixtures/images/test.jpg", "rb")},
        data={
            "customer_id": "CUST001",
            "gender": "female",
            "age": 30
        }
    )
    
    assert response.status_code == 201
    assert "job_id" in response.json()

def test_get_job_status():
    # 먼저 Job 생성
    create_response = client.post(
        "/v1/analysis/jobs",
        files={"image": open("tests/fixtures/images/test.jpg", "rb")}
    )
    job_id = create_response.json()["job_id"]
    
    # 상태 조회
    response = client.get(f"/v1/analysis/jobs/{job_id}")
    
    assert response.status_code == 200
    assert "status" in response.json()
```

---

## 5. 테스트 실행

### 5.1 전체 테스트

```bash
# 전체 테스트 실행
pytest

# 상세 출력
pytest -v

# 커버리지
pytest --cov=src --cov-report=html
```

### 5.2 특정 테스트

```bash
# 앱 기능 API 테스트
pytest tests/test_app_features_api.py

# 전체 시스템 통합 테스트
pytest tests/test_full_integration.py

# 서버 통합 테스트
pytest tests/test_server.py

# 특정 API 테스트
pytest tests/test_auth_api.py
pytest tests/test_admin_api.py
pytest tests/test_customer_api.py

# 특정 테스트 함수
pytest tests/test_server.py::TestE2EIntegration::test_confirm_skin_type
pytest tests/test_server.py::TestE2EIntegration::test_reclassify_skin_type
```

### 5.3 병렬 실행

```bash
# 병렬 실행 (pytest-xdist 필요)
pip install pytest-xdist
pytest -n auto
```

---

## 6. 테스트 커버리지

### 6.1 커버리지 목표

| 모듈 | 목표 커버리지 |
|------|-------------|
| src/scoring/ | 80% |
| src/restoration/ | 70% |
| src/llm/ | 60% |
| src/server/ | 75% |
| src/db/ | 80% |

### 6.2 커버리지 확인

```bash
# HTML 리포트
pytest --cov=src --cov-report=html
open htmlcov/index.html

# 터미널 리포트
pytest --cov=src --cov-report=term-missing
```

---

## 7. Mock 사용

### 7.1 LLM Mock

```python
# tests/conftest.py
import pytest
from unittest.mock import patch

@pytest.fixture
def mock_llm_response():
    with patch('src.llm.providers.GeminiProvider.generate_content') as mock:
        mock.return_value = "Mocked LLM response"
        yield mock
```

### 7.2 API Mock

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from src.server.main import app

@pytest.fixture
def client():
    return TestClient(app)
```

---

## 8. 테스트 데이터

### 8.1 이미지 픽스처

```
tests/fixtures/images/
├── test_pigmentation.jpg
├── test_redness.jpg
├── test_pores.jpg
└── test_normal.jpg
```

### 8.2 JSON 픽스처

```
tests/fixtures/json/
├── input_survey.json
├── expected_result.json
└── error_response.json
```

---

## 9. CI/CD 통합

### 9.1 GitHub Actions

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      - name: Install dependencies
        run: |
          pip install -r requirements-core.txt
          pip install pytest pytest-cov
      - name: Run tests
        run: pytest --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## 10. 테스트 작성 가이드라인

### 10.1 명명 규칙

- 파일명: `test_<module>.py`
- 함수명: `test_<function>_<scenario>`
- 클래스명: `Test<Class>`

### 10.2 AAA 패턴

```python
def test_example():
    # Arrange (준비)
    input_data = {"value": 10}
    
    # Act (실행)
    result = process(input_data)
    
    # Assert (검증)
    assert result == 20
```

### 10.3 테스트 격리

- 각 테스트는 독립적이어야 함
- 테스트 간 의존성 없음
- `setUp()`, `tearDown()` 사용

---

## 참고 문서

- `DEVELOPMENT_GUIDE.md` - 개발 가이드
- `ARCHITECTURE_GUIDE.md` - 아키텍처 가이드
- `CI_CD_GUIDE.md` - CI/CD 가이드

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
