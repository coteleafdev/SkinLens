# 테스트 가이드 (Testing Guide)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.7  
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
├── test_alert_system.py           # 알림 시스템 단위 테스트
├── test_prescription_calculator.py # 처방 계산기 단위 테스트
├── test_pipeline_image_utils.py   # 이미지 유틸리티 단위 테스트
├── test_pipeline_core.py          # 파이프라인 코어 단위 테스트
├── test_product_repository.py     # 제품 리포지토리 단위 테스트
├── test_result_parser.py          # 결과 파서 단위 테스트
├── test_supabase_sync.py          # Supabase 동기화 단위 테스트
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

### 2.4 알림 시스템 테스트

```python
# tests/test_alert_system.py
import pytest
from src.notification.alert_system import AlertConfig, AlertSystem

def test_alert_config_defaults():
    config = AlertConfig()
    assert config.slack_webhook_url is None
    assert config.pagerduty_integration_key is None
    assert config.email_enabled is False

def test_alert_system_initialization():
    config = AlertConfig(
        slack_webhook_url="https://hooks.slack.com/test",
        email_enabled=True
    )
    system = AlertSystem(config=config)
    assert system.config.slack_webhook_url == "https://hooks.slack.com/test"
```

### 2.5 처방 계산기 테스트

```python
# tests/test_prescription_calculator.py
import pytest
from src.prescription.prescription_calculator import (
    calculate_skin_assessment_percentage,
    calculate_skin_assessment_recipe
)

def test_calculate_percentage_good():
    percentage = calculate_skin_assessment_percentage(80)
    assert percentage == 0.0

def test_calculate_percentage_critical():
    percentage = calculate_skin_assessment_percentage(30)
    assert percentage == 3.0

def test_calculate_recipe_none_input():
    recipe = calculate_skin_assessment_recipe(None)
    assert recipe == {}
```

### 2.6 이미지 유틸리티 테스트

```python
# tests/test_pipeline_image_utils.py
import pytest
from pathlib import Path
from src.pipeline.image_utils import _ensure_match_resolution

def test_ensure_match_resolution_same_size(tmp_path):
    img = Image.new('RGB', (1000, 1000), color='white')
    input_path = tmp_path / "test.png"
    img.save(input_path)
    
    result_path = _ensure_match_resolution(input_path, (1000, 1000))
    assert result_path == input_path.resolve()
```

### 2.7 파이프라인 코어 테스트

```python
# tests/test_pipeline_core.py
import pytest
from src.pipeline.pipeline_core import (
    format_duration,
    Restorer,
    PipelineSettings
)

def test_format_duration_seconds():
    assert format_duration(5.5) == "5.50s"

def test_format_duration_minutes():
    assert format_duration(90) == "1m 30s"

def test_restorer_values():
    assert Restorer.RESTOREFORMER == "restoreformer"
    assert Restorer.CODEFORMER == "codeformer"
```

### 2.8 제품 리포지토리 테스트

```python
# tests/test_product_repository.py
import pytest
from src.db.product_repository import ProductRepository

def test_add_product(repository):
    product_id = repository.add_product(
        product_id="TEST001",
        product_name="Test Product",
        category="트러블 케어",
        key_ingredients=["니아시나마이드"],
        efficacy="Test efficacy"
    )
    assert product_id > 0

def test_get_product(repository):
    repository.add_product(
        product_id="TEST001",
        product_name="Test Product",
        category="트러블 케어",
        key_ingredients=["니아시나마이드"],
        efficacy="Test efficacy"
    )
    
    product = repository.get_product("TEST001")
    assert product is not None
    assert product["product_name"] == "Test Product"
```

### 2.9 결과 파서 테스트

```python
# tests/test_result_parser.py
import pytest
from src.db.result_parser import extract_overall_scores

def test_extract_overall_scores_normal():
    json_result = {
        "analysis_result": {
            "overall_score": 75.5,
            "overall_score_report": 80.0
        }
    }
    
    orig, rest = extract_overall_scores(json_result)
    assert orig == 75.5
    assert rest == 80.0
```

### 2.10 Supabase 동기화 테스트

```python
# tests/test_supabase_sync.py
import pytest
from src.db.supabase_sync import SupabaseConfig

def test_default_config():
    config = SupabaseConfig()
    assert config.url == ""
    assert config.key == ""
    assert config.bucket == "skin-images"
    assert config.table == "skin_analyses"
    assert config.enabled is True

@patch.dict('os.environ', {
    'SUPABASE_URL': 'https://test.supabase.co',
    'SUPABASE_KEY': 'test-key'
})
def test_from_env():
    config = SupabaseConfig.from_env()
    assert config.url == "https://test.supabase.co"
    assert config.key == "test-key"
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

### 4.2 전체 시스템 통합 테스트

```python
# tests/test_full_integration.py
"""
전체 시스템 통합 테스트: 앱-엔진서버-웹서버-DB 연동

테스트 시나리오:
1. 앱 클라이언트가 웹 서버에 이미지 업로드
2. 웹 서버가 엔진 서버에 분석 요청
3. 엔진 서버가 이미지 분석 수행
4. 분석 결과를 DB에 저장
5. 앱 클라이언트가 결과 조회
"""

def test_full_flow_image_upload_to_result_retrieval(
    authenticated_client, admin_auth_headers, temp_dir, test_image
):
    """전체 플로우 테스트: 이미지 업로드 → 엔진 서버 분석 → DB 저장 → 결과 조회"""
    
    # 1. 앱 클라이언트: 이미지 업로드
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
    
    # 2. 엔진 서버: 백그라운드 분석 수행 (폴링 방식)
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
    
    # 3. 웹 서버: 결과 조회
    result_response = authenticated_client.get(
        f"/v1/analysis/jobs/{job_id}",
        headers=admin_auth_headers
    )
    
    assert result_response.status_code == 200
    result_data = result_response.json()
    assert result_data["status"] in ["completed", "failed"]
    assert result_data["customer_id"] == "CUST001"

def test_engine_server_analysis_direct(temp_dir, test_image):
    """엔진 서버 직접 호출 테스트"""
    from src.scoring.skin_scoring import SkinAnalyzer
    
    analyzer = SkinAnalyzer()
    result = analyzer.analyze_all(str(test_image), debug=False)
    
    assert result is not None
    assert "overall_score" in result
    assert "measurements" in result
    assert 0 <= result["overall_score"] <= 100
```

#### 추가 통합 테스트

전체 시스템 통합 테스트에는 다음과 같은 추가 테스트가 포함됩니다:

**에러 핸들링 테스트**
- `test_error_handling_invalid_image`: 잘못된 이미지 업로드 테스트
- `test_error_handling_missing_required_fields`: 필수 필드 누락 테스트
- `test_error_handling_nonexistent_job`: 존재하지 않는 Job 조회 테스트

**DB 데이터 검증**
- `test_db_data_verification`: 분석 결과가 DB에 저장되는지 확인

**동시성 테스트**
- `test_concurrent_requests`: 여러 요청 동시 처리 테스트

**기능 테스트**
- `test_websocket_progress_updates`: WebSocket 진행률 업데이트 테스트
- `test_image_restoration`: 이미지 복원 기능 테스트
- `test_llm_report_generation`: LLM 보고서 생성 테스트

**데이터 정리**
- `test_data_cleanup`: 테스트 데이터 정리 확인

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

# 단위 테스트 (새로 추가된 모듈)
pytest tests/test_alert_system.py
pytest tests/test_prescription_calculator.py
pytest tests/test_pipeline_image_utils.py
pytest tests/test_pipeline_core.py
pytest tests/test_product_repository.py
pytest tests/test_result_parser.py
pytest tests/test_supabase_sync.py

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
*마지막 수정: 2026-05-31*
