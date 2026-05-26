# In-Process Model 상주 아키텍처 설계

> **작성일:** 2026-05-24  
> **목적:** subprocess cold-start → in-process 모델 상주 아키텍처 변경 계획

---

## 현재 아키텍처 (Subprocess Cold-Start)

### 구조

```
SkinLens 앱
    ↓
pipeline_core.py
    ↓
subprocess.run() → 외부 Python 스크립트
    ↓
CodeFormer/RestoreFormer++ 모델 로드 + 추론
    ↓
결과 반환
```

### 문제점

1. **Cold-Start 지연**
   - 매 요청마다 모델 로드 (수초 ~ 수십초)
   - GPU 메모리에 모델 상주하지 않음

2. **자원 낭비**
   - 모델 로드 반복으로 CPU/GPU 시간 낭비
   - 디스크 I/O 반복

3. **확장성 제한**
   - 동시 요청 처리 시 각각 cold-start 발생
   - 병렬 처리 비효율

---

## 제안 아키텍처 (In-Process Model 상주)

### 구조

```
SkinLens 앱
    ↓
ModelManager (싱글톤)
    ├─ CodeFormer 모델 (상주)
    └─ RestoreFormer++ 모델 (상주)
    ↓
추론 함수 직접 호출
    ↓
결과 반환
```

### 장점

1. **성능 향상**
   - 모델 상주로 추론만 수행 (ms 단위)
   - Cold-Start 지연 제거

2. **자원 효율**
   - 모델 로드 1회만 수행
   - GPU 메모리 효율적 사용

3. **확장성**
   - 동시 요청 처리 용이
   - 배치 처리 가능

### 단점

1. **메모리 사용 증가**
   - 모델 상주로 메모리 점유
   - GPU 메모리 필요 (VRAM)

2. **복잡성 증가**
   - 모델 라이프사이클 관리 필요
   - 메모리 누수 방지 필요

3. **의존성 관리**
   - torch, torchvision 등 직접 의존
   - 버전 호환성 관리 필요

---

## 구현 계획

### 단계 1: ModelManager 구현

```python
# src/restoration/model_manager.py

class ModelManager:
    """복원 모델 상주 매니저 (싱글톤)."""
    
    _instance = None
    _models: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_codeformer(self, config: Dict[str, Any]):
        """CodeFormer 모델 로드 (상주)."""
        if "codeformer" not in self._models:
            self._models["codeformer"] = self._load_codeformer(config)
        return self._models["codeformer"]
    
    def get_restoreformer(self, config: Dict[str, Any]):
        """RestoreFormer++ 모델 로드 (상주)."""
        if "restoreformer" not in self._models:
            self._models["restoreformer"] = self._load_restoreformer(config)
        return self._models["restoreformer"]
    
    def unload_all(self):
        """모든 모델 언로드 (메모리 해제)."""
        self._models.clear()
        torch.cuda.empty_cache()
```

### 단계 2: 복원 백엔드 리팩토링

```python
# src/restoration/strategies/codeformer_restorer.py

class CodeFormerRestorer(BaseRestorer):
    def restore(self, input_path: Path, output_path: Path):
        model = ModelManager().get_codeformer(self.config)
        # 직접 추론 호출
        result = model.infer(input_path, output_path, **self.config)
        return result
```

### 단계 3: 의존성 관리

```python
# pyproject.toml

dependencies = [
    "torch>=2.0.0",
    "torchvision>=0.15.0",
    "basicsr>=1.4.2",
    # ... 기존 의존성
]
```

### 단계 4: 메모리 관리

```python
# 메모리 모니터링
def check_memory_usage():
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        if allocated > 8.0:  # 8GB 초과 시 경고
            log.warning("GPU 메모리 사용량 높음: %.2f GB", allocated)
```

---

## 마이그레이션 전략

### 단계적 롤아웃

1. **Phase 1: 테스트 환경**
   - ModelManager 구현
   - 단일 모델 테스트
   - 성능 벤치마킹

2. **Phase 2: 개발 환경**
   - 두 모델 모두 상주
   - 동시 요청 테스트
   - 메모리 사용량 모니터링

3. **Phase 3: 프로덕션**
   - 기능 플래그로 제어
   - A/B 테스트
   - 점진적 롤아웃

### 하위 호환성

```python
# config.json

{
  "restoration": {
    "in_process_mode": false,  # 기존 subprocess 모드
    "model_resident": false    # in-process 모드
  }
}
```

---

## 성능 기대치

### Cold-Start vs In-Process

| 작업 | Cold-Start | In-Process | 향상 |
|------|-----------|------------|------|
| 모델 로드 | ~5초 | 1회만 | - |
| 추론 | ~2초 | ~0.5초 | 4x |
| 전체 | ~7초 | ~0.5초 | 14x |

### 메모리 사용

| 모드 | CPU 메모리 | GPU 메모리 |
|------|-----------|-----------|
| Cold-Start | ~2GB (일시적) | ~4GB (일시적) |
| In-Process | ~3GB (상주) | ~6GB (상주) |

---

## 리스크 및 완화

### 리스크

1. **메모리 부족**
   - 완화: 모델 언로드 기능, 메모리 모니터링

2. **의존성 충돌**
   - 완화: 가상 환경 격리, 버전 고정

3. **GPU 메모리 부족**
   - 완화: 모델 크기 조절, 배치 크기 제한

### 롤백 계획

- 기능 플래그로 즉시 subprocess 모드로 복귀
- 문제 발생 시 로그 분석 및 hotfix

---

## 참고

- **관련 이슈:** P3-27
- **현재 구현:** `src/pipeline/image_utils.py` → `_run_subprocess_with_heartbeat()`
- **대상 파일:** 
  - `src/restoration/strategies/codeformer_restorer.py`
  - `src/restoration/strategies/restoreformer_restorer.py`
  - `src/pipeline/pipeline_core.py`
