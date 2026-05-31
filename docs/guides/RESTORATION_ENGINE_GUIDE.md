# 복원 엔진 추가 가이드 (Restoration Engine Guide)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

이 가이드는 SkinLens에 새로운 복원 엔진을 추가하는 방법을 설명합니다.

## 개요

SkinLens는 Strategy Pattern과 Factory Pattern을 사용하여 복원 엔진을 추상화했습니다. 새로운 엔진을 추가하려면 다음 단계를 따르세요.

## 1. BaseRestorer 상속 클래스 구현

`src/restoration/strategies/` 디렉토리에 새로운 엔진 클래스를 생성합니다.

```python
# src/restoration/strategies/new_restorer.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.restoration.base import BaseRestorer
from src.restoration.registry import RestorerRegistry


@RestorerRegistry.register(
    "new_restorer_v1",
    aliases=["new_restorer", "nr"],
    metadata={
        "version": "1.0.0",
        "supported_devices": ["cuda", "cpu"],
        "description": "새로운 복원 엔진"
    }
)
class NewRestorer(BaseRestorer):
    """새로운 복원 엔진 구현."""
    
    def __init__(self, config: Dict[str, Any] = None) -> None:
        super().__init__(config)
        self.validate_config(["repo"])
    
    def restore(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """복원 수행."""
        # 전처리
        processed_input = self.preprocess(input_path)
        
        # 복원 로직 구현
        # ... 복원 코드 ...
        
        # 후처리
        processed_output = self.postprocess(output_path)
        
        return {
            "output_path": str(processed_output),
            "metadata": {}
        }
    
    def get_name(self) -> str:
        return "new_restorer_v1"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def load_model(self) -> None:
        """모델 로드 (필요시)."""
        # in-process 실행을 위해 모델 미리 로드
        pass
    
    def unload_model(self) -> None:
        """모델 언로드 (필요시)."""
        # 메모리 해제
        pass
    
    def preprocess(self, input_path: Path) -> Path:
        """전처리 (선택)."""
        return input_path
    
    def postprocess(self, output_path: Path) -> Path:
        """후처리 (선택)."""
        return output_path
    
    def cleanup(self) -> None:
        """리소스 정리 (선택)."""
        pass
    
    def get_supported_devices(self) -> list[str]:
        return ["cuda", "cpu"]
```

## 2. 파이프라인 통합

`src/pipeline/pipeline_core.py`의 `_create_restorer_strategy()` 함수에 새 엔진을 추가합니다.

```python
def _create_restorer_strategy(
    backend: Restorer,
    cfg: PipelineSettings,
) -> BaseRestorer:
    from src.restoration.strategies.codeformer_restorer import CodeFormerRestorer
    from src.restoration.strategies.restoreformer_restorer import RestoreFormerRestorer
    from src.restoration.strategies.new_restorer import NewRestorer  # 추가
    
    if backend is Restorer.CODEFORMER:
        return CodeFormerRestorer(config={...})
    elif backend is Restorer.RESTOREFORMER:
        return RestoreFormerRestorer(config={...})
    elif backend is Restorer.NEW_RESTORER:  # 추가
        return NewRestorer(config={
            "repo": cfg.new_restorer_repo,
            "device": cfg.new_restorer_device,
        })
    else:
        raise ValueError(f"지원하지 않는 복원 백엔드: {backend}")
```

## 3. Enum 추가

`src/pipeline/pipeline_core.py`의 `Restorer` Enum에 새 엔진을 추가합니다.

```python
class Restorer(Enum):
    RESTOREFORMER = auto()
    CODEFORMER = auto()
    NEW_RESTORER = auto()  # 추가
```

## 4. 설정 추가

`config/config.json`에 새 엔진 설정을 추가합니다.

```json
{
  "pipeline": {
    "restorer": "new_restorer",
    "new_restorer_repo": "/path/to/new_restorer",
    "new_restorer_device": "cuda"
  }
}
```

## 5. 테스트

테스트 파일을 생성하여 새 엔진을 검증합니다.

```python
# tests/test_new_restorer.py
import pytest
from src.restoration.strategies.new_restorer import NewRestorer

def test_new_restorer_instantiation():
    config = {"repo": "/tmp/test"}
    restorer = NewRestorer(config)
    assert restorer.get_name() == "new_restorer_v1"
    assert restorer.get_version() == "1.0.0"

def test_new_restorer_restore():
    # 복원 테스트
    pass
```

## BaseRestorer 메서드 가이드

### 필수 메서드

- `restore(input_path, output_path, **kwargs)`: 복원 수행
- `get_name()`: 엔진 이름 반환
- `get_version()`: 버전 반환

### 선택적 메서드

- `load_model()`: 모델 미리 로드 (in-process 실행용)
- `unload_model()`: 모델 언로드 (메모리 해제)
- `preprocess(input_path)`: 전처리
- `postprocess(output_path)`: 후처리
- `cleanup()`: 리소스 정리
- `get_supported_devices()`: 지원 디바이스 목록

## 레지스트리 사용법

### 엔진 등록

```python
@RestorerRegistry.register("engine_name", aliases=["alias1", "alias2"])
class MyRestorer(BaseRestorer):
    ...
```

### 엔진 조회

```python
# 클래스 조회
restorer_class = RestorerRegistry.get("engine_name")

# 인스턴스 생성
restorer = RestorerRegistry.create("engine_name", config={"repo": "/path"})

# 설정 기반 생성
restorer = RestorerRegistry.create_from_config(config)

# 메타데이터 조회
metadata = RestorerRegistry.get_metadata("engine_name")

# 사용 가능한 엔진 목록
engines = RestorerRegistry.list_available()
```

## 주의사항

1. **BaseRestorer 상속**: 모든 엔진은 `BaseRestorer`를 상속받아야 합니다.
2. **설정 유효성 검사**: `validate_config()`를 사용하여 필수 설정을 검증하세요.
3. **에러 처리**: 적절한 예외 처리를 구현하세요.
4. **테스트**: 단위 테스트와 통합 테스트를 작성하세요.
5. **문서화**: docstring을 사용하여 메서드를 문서화하세요.

## 예제: 기존 엔진 참조

기존 엔진 구현을 참고하세요:
- `src/restoration/strategies/codeformer_restorer.py`
- `src/restoration/strategies/restoreformer_restorer.py`

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
