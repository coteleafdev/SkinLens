# SkinLens v1.0 - 개발 가이드

> 최종 수정: 2026-05-24

이 문서는 SkinLens v1.0 프로젝트의 개발 표준, 모범 사례, 아키텍처 가이드라인, 코드 품질 체크리스트, 테스트 전략을 설명합니다.

---

## 목차

1. [Import 가이드라인](#1-import-가이드라인)
2. [순환 Import 해결 패턴](#2-순환-import-해결-패턴)
3. [GUI 의존성 분리](#3-gui-의존성-분리)
4. [코드 구조](#4-코드-구조)
5. [리팩토링 가이드라인](#5-리팩토링-가이드라인)
6. [코드 품질 체크리스트](#6-코드-품질-체크리스트)
7. [테스트 가이드라인](#7-테스트-가이드라인)
8. [로깅 시스템](#8-로깅-시스템)

---

## 1. Import 가이드라인

### 1.1 절대 경로 사용

**규칙:** 모든 프로젝트 내부 import는 `from src.` 접두사를 사용합니다.

```python
# ✅ 올바른 예
from src.pipeline.pipeline_core import Restorer
from src.scoring.skin_scoring import SkinAnalyzerV3
from src.utils.utils import setup_logging

# ❌ 피해야 할 예
from pipeline_core import Restorer
from skin_scoring import SkinAnalyzerV3
```

### 1.2 스크립트 파일 Import

**규칙:** `scripts/` 디렉토리의 파일은 프로젝트 루트를 `sys.path`에 추가합니다.

```python
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline.pipeline_core import Restorer
```

### 1.3 외부 의존성 Lazy Import

**규칙:** ML 라이브러리(torch, cv2, skimage) 등 선택적 의존성은 try-except로 처리합니다.

```python
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
```

---

## 2. 순환 Import 해결 패턴

### 2.1 문제 상황

순환 import는 두 모듈이 서로를 import할 때 발생합니다:

```
v3_compose.py → skin_scoring.py → v3_compose.py (순환!)
```

### 2.2 해결 패턴: Lazy Import

**패턴:** 함수 내부에서 import를 지연 실행합니다.

```python
# v3_compose.py
def _get_v3_weights() -> Dict[str, float]:
    """config.json에서 v3_weights를 로드합니다."""
    # Lazy import로 순환 import 방지
    from src.scoring.skin_scoring import _load_scoring_config
    config = _load_scoring_config()
    v3_weights = config.get("v3_weights", {})
    return v3_weights
```

### 2.3 적용 사례

| 파일 | Lazy Import 대상 | 이유 |
|---|---|---|
| `v3_compose.py` | `_load_scoring_config` | skin_scoring과 순환 import 방지 |
| `utils.py` | `analyze_compare_triple` | GUI 의존 제거 |
| `utils.py` | `apply_safety_net_logic` | safety_net과 순환 import 방지 |
| `skin_scoring.py` | `face_detector`, `cv2`, `skimage` | ML 라이브러리 선택적 로드 |

### 2.4 Lazy Import 사용 기준

**사용해야 할 때:**
- 순환 import가 발생할 때
- 선택적 의존성(PySide6, torch 등)이 있을 때
- 모듈 로드 시간을 최적화해야 할 때

**사용하지 말아야 할 때:**
- 항상 필요한 표준 라이브러리
- 성능에 영향이 없는 경우
- 코드 가독성이 저해될 때

---

## 3. GUI 의존성 분리

### 3.1 문제 상황

서버 환경에서 PySide6가 없으면 import 실패:

```python
# 문제: analyzer_compare_gui.py
from PySide6.QtWidgets import ...  # 서버에서 ImportError

def analyze_compare_triple(...):
    # 이 함수는 PySide6를 전혀 사용하지 않음
    ...
```

### 3.2 해결 패턴: 모듈 분리

**패턴:** GUI 의존 없는 함수를 별도 파일로 분리합니다.

```python
# src/skin/core/analyze_utils.py (GUI 의존 없음)
def analyze_compare_triple(orig_path, ideal1_path, ideal2_path):
    from src.scoring.skin_scoring import SkinAnalyzerV3
    an = SkinAnalyzerV3()
    ...
    return orig, ideal1, ideal2
```

```python
# src/utils/utils.py (GUI 의존 제거)
def apply_score_safety_net(...):
    # [REFACTOR P1-18] GUI 의존 제거
    from src.skin.core.analyze_utils import analyze_compare_triple
    ...
```

### 3.3 분리된 모듈

| 원래 위치 | 분리된 위치 | 이유 |
|---|---|---|
| `analyzer_compare_gui.py` | `analyze_utils.py` | 서버 환경에서 PySide6 없이 사용 |

---

## 4. 코드 구조

### 4.1 디렉토리 구조

```
src/
├── cli/              # CLI 도구
├── db/               # 데이터베이스
├── gui/              # GUI 애플리케이션
├── llm/              # LLM 통합
├── pipeline/         # 복원 파이프라인
├── prescription/     # 처방 계산
├── restoration/      # 복원 엔진
│   ├── base.py       # BaseRestorer 추상 클래스
│   ├── registry.py   # RestorerRegistry 레지스트리
│   └── strategies/   # 복원 엔진 구현체
├── scoring/          # 점수 계산
├── server/           # FastAPI 서버
├── skin/             # 피부 분석 코어
│   ├── compose/      # 점수 조합
│   ├── core/         # 핵심 모듈
│   └── scoring/      # 점수 로직
└── utils/            # 유틸리티
```

### 4.2 모듈 의존성 규칙

**하위 → 상위 의존 허용:**
- `skin/core/` → 표준 라이브러리만
- `skin/compose/` → `skin/core/`, `scoring/`
- `scoring/` → `skin/core/`
- `pipeline/` → 독립 (표준 라이브러리만)
- `utils/` → `skin/`, `scoring/` (lazy import)

**상위 → 하위 의존 금지:**
- `server/` → `gui/` (금지)
- `cli/` → `gui/` (금지)

---

## 5. 리팩토링 가이드라인

### 5.1 God Module 식별

**신호:**
- 1,000라인 이상의 단일 파일
- 25개 이상의 import
- 다양한 책임 (GUI, 파이프라인, LLM 등)

**예시:** `skin_scoring.py` (1,525라인, 25개 이상의 import)

### 5.2 리팩토링 전략

**단계 1: 책임 분리**
- 단일 책임 원칙 (SRP) 적용
- 기능별로 모듈 분리

**단계 2: 인터페이스 추출**
- Public API 정의
- 내부 구현 숨기기

**단계 3: 의존성 주입**
- 순환 의존 제거
- 테스트 가능성 향상

---

## 6. 코드 품질 체크리스트

### 6.1 기능 점검 (Functionality)

**핵심 분석 파이프라인**
- [ ] 얼굴 검출: 다양한 조명/각도에서 성공
- [ ] ROI 분할: FaceROI 기준값 정확성
- [ ] 도메인 분석 (18개 항목): 각 항목 점수 합리성
- [ ] 직교 점수 조합 (v3): 10개 직교 출력 정확성

**보고서 레이어**
- [ ] LLM 소견 생성: JSON 파싱 성공
- [ ] 처방 계산: 믹스 코드 매핑 정확성

### 6.2 성능 점검 (Performance)

- [ ] 분석 시간: 단일 이미지 < 30초
- [ ] 메모리 사용: < 4GB
- [ ] 병렬 처리: 멀티프로세서 활용

### 6.3 안정성/신뢰성 (Reliability)

- [ ] 에러 처리: 네트워크, 파일 시스템, DB 에러
- [ ] 로깅: 중요 이벤트 로깅
- [ ] 복구력: 일시적 오류 후 자동 복구

### 6.4 코드 품질 (Code Quality)

- [ ] 타입 힌트: 함수 시그니처에 타입 명시
- [ ] 독스트링: public 함수/클래스에 독스트링
- [ ] 네이밍: 명확하고 일관된 네이밍
- [ ] 복잡도: 함수 복잡도 < 10

### 6.5 보안 (Security)

- [ ] 입력 유효성: 모든 입력 검증
- [ ] 인증/권한: API 인증 구현
- [ ] 비밀 관리: API 키 환경 변수화

### 6.6 배포/운영 (Deployment/Operations)

- [ ] 설정 관리: config.json 외부화
- [ ] 로그 관리: 로그 레벨 조절 가능
- [ ] 모니터링: 헬스 체크 엔드포인트

---

## 7. 테스트 가이드라인

### 7.1 Import 의존성 테스트

**목적:** import 순서에 의존하는 로직이 없는지 확인합니다.

```python
class TestImportDependency:
    def test_import_order_independence(self):
        """import 순서에 의존하지 않는지 확인"""
        import_orders = [
            ["src.skin.core.face_roi", "src.skin.core.score_constants"],
            ["src.skin.core.score_constants", "src.skin.core.face_roi"],
        ]
        
        for order in import_orders:
            for module_name in order:
                if module_name in sys.modules:
                    del sys.modules[module_name]
            
            for module_name in order:
                __import__(module_name)
```

### 7.2 GUI 독립성 테스트

**목적:** GUI 모듈 없이도 핵심 기능이 import되는지 확인합니다.

```python
def test_gui_independence(self):
    """GUI 모듈 없이도 핵심 기능이 import되는지 확인"""
    from src.skin.core.analyze_utils import analyze_compare_triple
    assert callable(analyze_compare_triple)
```

### 7.3 테스트 실행

```bash
# import 의존성 테스트만 실행
pytest tests/test_integration.py::TestImportDependency -v

# 전체 테스트 실행
pytest tests/ -v
```

### 7.4 테스트 커버리지

**목표:** 전체 코드베이스 80% 이상 커버리지

**우선순위:**
1. 핵심 비즈니스 로직 (scoring, prescription)
2. 파이프라인 (pipeline)
3. LLM 통합 (llm)
4. GUI (gui)

### 7.5 단위 테스트

**규칙:**
- 독립적: 다른 테스트에 의존하지 않음
- 빠름: < 1초
- 명확: 실패 시 원인 명확

```python
def test_melasma_score_calculation():
    analyzer = SkinAnalyzerV3()
    result = analyzer.analyze(test_image)
    assert 0 <= result['melasma_score'] <= 100
```

### 7.6 통합 테스트

**규칙:**
- 실제 환경 시뮬레이션
- 전체 파이프라인 테스트
- 외부 의존성 모킹

```python
def test_full_pipeline():
    with mock_llm_response():
        result = run_pipeline(test_image)
        assert result['overall_score'] is not None
```

---

## 8. 모범 사례

### 8.1 함수 분리

```python
# ✅ 좋은 예: 함수 내 lazy import
def get_weights():
    from src.scoring.skin_scoring import _load_config
    return _load_config()

# ❌ 피해야 할 예: 모듈 레벨 import로 순환 유발
from src.scoring.skin_scoring import _load_config
def get_weights():
    return _load_config()
```

### 8.2 에러 처리

```python
# ✅ 좋은 예: 구체적인 예외 처리
try:
    from src.skin.core.analyze_utils import analyze_compare_triple
except ImportError as e:
    raise ImportError(
        "apply_score_safety_net 은 analyze_utils 모듈이 필요합니다: "
        f"analyze_compare_triple import 실패 — {_e}"
    ) from _e

# ❌ 피해야 할 예: 모호한 예외 처리
try:
    from src.skin.core.analyze_utils import analyze_compare_triple
except ImportError:
    pass
```

---

## 8. 로깅 시스템

### 8.1 중앙 집중식 로깅 설정

**위치:** `src/utils/utils.py`의 `setup_logging()` 함수

**특징:**
- `logging.config.dictConfig`를 사용하여 모든 로거에 일관된 포맷 적용
- 외부 라이브러리(CodeFormer 등)의 로거도 동일한 포맷으로 통제
- GUI와 CLI 모두에서 동일한 로그 형식 사용

### 8.2 로그 포맷

**표준 로그 포맷:**
```
%(asctime)s [%(levelname)s] %(name)s:%(pathname)s:%(lineno)d: %(message)s
```

**예시 출력:**
```
16:24:44 [INFO] codeformer:C:\Project\SkinLens v1\model-serving-refactor\src\codeformer.py:43: CodeFormer wrapper initialized (device: cuda)
```

**포맷 설명:**
- `%(asctime)s`: 시간 (HH:MM:SS)
- `%(levelname)s`: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
- `%(name)s`: 로거 이름
- `%(pathname)s`: 전체 파일 경로 (추적 가능성 위해 전체 경로 사용)
- `%(lineno)d`: 라인 번호
- `%(message)s`: 로그 메시지

### 8.3 로거 설정

**루트 로거:**
- 모든 로그의 기본 핸들러
- `dictConfig`를 통해 일관된 포맷 적용

**외부 라이브러리 로거:**
- `codeformer` 로거: 명시적으로 설정하여 포맷 강제 적용
- `apply_formatter_to_all_loggers()` 함수로 동적 로거에 포맷 재적용

**노이즈 억제:**
- matplotlib, PIL, urllib3, httpx 등의 로그 레벨을 WARNING으로 설정

### 8.4 사용 방법

**기본 사용:**
```python
from src.utils.utils import setup_logging
import logging

# 로깅 설정 (프로그램 시작 시 한 번만 호출)
setup_logging()

# 로그 사용
log = logging.getLogger(__name__)
log.info("분석 시작")
log.debug("디버그 정보")
log.error("에러 발생")
```

**외부 라이브러리 로거 포맷 재적용:**
```python
from src.utils.utils import apply_formatter_to_all_loggers

# CodeFormer 등 외부 라이브러리 로드 후
apply_formatter_to_all_loggers()
```

### 8.5 config.json 설정

```json
{
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s [%(levelname)s] %(name)s:%(pathname)s:%(lineno)d: %(message)s",
    "datefmt": "%H:%M:%S",
    "db_logging": {
      "enabled": true,
      "retention_days": 7
    }
  }
}
```

**설정 항목:**
- `level`: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
- `format`: 로그 형식 (전체 파일 경로와 라인번호 포함)
- `datefmt`: 시간 형식
- `db_logging.enabled`: DB 로깅 활성화 여부
- `db_logging.retention_days`: 로그 보관 기간 (일)

### 8.6 DB 로깅

**기능:**
- 로그를 SQLite DB에 자동 저장
- 실행 이력 추적 및 문제 해결 지원
- 롤링 방식으로 오래된 로그 자동 삭제

**사용:**
```python
from src.utils.utils import setup_logging

setup_logging(enable_db_logging=True)
```

---

## 9. 참고 문서

- [Python Import System](https://docs.python.org/3/reference/import.html)
- [Circular Imports in Python](https://stackoverflow.com/questions/73206603/python-circular-imports)
- [Lazy Loading in Python](https://docs.python.org/3/library/importlib.html)
