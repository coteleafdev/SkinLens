# SkinLens v1 — #3 GUI 단일 `AnalysisService` 흡수 (Phase 1 완료 + 통합 설계)

> #1/#2(DB·LLM God 클래스)는 본문 무수정 기계 분해였지만, **#3은 점수 의미가 실제로 분기된 경로의 통합**이라 성격이 다릅니다.
> 무작정 배선하면 GUI 점수가 조용히 바뀝니다. 이번 단계는 **검증 가능한 안전 기반**을 확정하고, 실제 GUI 전환은 점수 델타 결정·검증을 거치도록 분리했습니다.

## Phase 1 — 완료 (검증됨, 동작 불변)

신규 `src/pipeline/analysis_service.py` — **단일 표준 진입점** `AnalysisService`.
검증된 `run_analysis_pipeline`/`run_analysis_pipeline_async`에 위임하는 얇은 파사드라 **CLI/Engine/Server 동작 불변**이며, 순환참조·회귀 위험 0.

```python
svc = AnalysisService(llm_api_key=key)
result = svc.run(image_path, out_dir, do_restore=True, llm_report=True, use_multi_view_analysis=True)
result = svc.run_request(AnalysisRequest(image_path, out_dir, age=30, ...))   # 객체형
result = await svc.run_async(image_path, out_dir, executor=ex, ...)           # engine/server
```

**검증(통과):** 컴파일 OK. spy 위임 충실성 — 동기/비동기/`run_request` 인자 전달, 생성자 키 주입(+호출측 우선), `base_url=None` 제외 모두 일치.

> 효과: GUI가 흡수할 **표준 진입점**이 생겼습니다. CLI/engine은 선택적으로 이 서비스로 호출을 통일할 수 있으나(동작 동일), 필수는 아닙니다.

---

## 핵심 — GUI vs CLI 점수 경로는 "다른 함수"가 아니라 "다른 결과"

| 단계 | CLI `run_analysis_pipeline` | GUI `skin_analysis_pipeline._cli_body` |
|---|---|---|
| 복원 | `run_enhancement_pipeline` | `run_enhancement_pipeline` (동일) |
| **주 분석** | **`analyze_all_multi_v3`** (정식 다중뷰, lateral 포함) | **`analyze_compare_triple`** (front/restored 비교) |
| 안전장치 | `apply_score_safety_net` | `apply_score_safety_net` (동일) |
| **점수 후처리** | **없음** (raw 점수 사용) | **`apply_score_offset_v2`(max 90) + `filter_measurements`** (GUI 전용) |
| LLM 입력 점수 | raw `overall_score`/`measurements_report` | **offset 보정·필터된** 점수 |
| 제품/피부타입 | 파이프라인 내부 처리 | `_cli_body` 인라인 추론 |

→ **분기 지점이 3곳**(분석 함수, 점수 후처리 유무, LLM 입력 점수원). 단순히 GUI를 `AnalysisService.run()`으로 바꾸면 위 GUI 전용 로직이 사라져 **점수·소견이 달라집니다.** 이것이 #1/#2와 본질적으로 다른 이유입니다.

---

## Phase 2 — GUI 전환 (결정 게이트 + 검증 필요)

전환은 "어떤 동작을 표준으로 둘지" 결정이 선행돼야 합니다. 두 가지 길:

### 옵션 A — GUI 동작을 표준으로 승격 (offset/filter를 파이프라인에 편입)
`apply_score_offset_v2`/`filter_measurements`/compare_triple 기반을 canonical로 보고 `run_analysis_pipeline`(=AnalysisService)에 옵션으로 편입. CLI/engine 점수도 함께 바뀜 → 광범위 검증 필요. **권장하지 않음**(영향 범위 큼).

### 옵션 B — 표준 분석 + GUI 표시측 후처리 레이어 (권장)
GUI가 restore/analyze/LLM은 `AnalysisService.run()`으로 통일(중복 제거)하고, **offset/filter는 결과 dict에 대한 GUI 표시측 후처리**로 분리 유지. 단, 주 분석 함수가 `multi_v3`로 바뀌므로(현 GUI는 `compare_triple`) **점수가 달라질 수 있음** → 아래 검증 필수.

### 옵션 B 구현 스케치
```python
# skin_analysis_pipeline._cli_body 의 restore→analyze→safety_net→LLM 블록을 대체
from src.pipeline.analysis_service import AnalysisService

result = AnalysisService(llm_api_key=_load_llm_api_key()).run(
    Path(args.input), Path(args.out_dir),
    do_restore=args.restore, score_safety_net=True,
    llm_report=True, llm_scores=args.llm_scores,
    use_multi_view_analysis=False,            # GUI 단일 이미지 흐름이면 False
    input_json=getattr(args, "input_json", None),
)
# GUI 표시측 후처리(기존 로직 재사용): result 의 measurements_report 에 offset/filter 적용
display = apply_score_offset_v2(
    {"overall": result["analysis_result"]["overall_score"],
     "measurements": filter_measurements(result["analysis_result"]["measurements_report"])},
    offset_config, weights, max_score_limit=90.0,
)
# 이후 팝업/저장은 display 사용
```
> `apply_score_offset_v2`/`filter_measurements`를 `_cli_body` 내부 nested 함수에서 모듈/`src/gui/score_postprocess.py`로 추출하면 표시측 레이어로 재사용 가능.

### 전환 전 필수 검증 (사용자 환경, 모델 필요)
샌드박스에는 CV/LLM 모델이 없어 점수 동치 검증이 불가합니다. 전환 전 반드시:
1. 대표 이미지 N장에 대해 **현 GUI 경로**와 **AnalysisService 경로** 점수를 각각 산출.
2. 항목별 점수 차이(Δ)를 표로 비교. 허용 임계(예: ±2) 초과 항목 식별.
3. Δ가 큰 항목이 `multi_v3` vs `compare_triple` 차이에서 오는지 분리 확인.
4. 차이가 수용 가능하면 전환, 아니면 옵션 B에서 분석 함수를 `compare_triple`로 맞추는 어댑터를 `AnalysisService`에 추가(분석 함수 선택 파라미터).

---

## 권장 진행 순서

1. **(완료)** AnalysisService 도입 — 단일 진입점 확보.
2. CLI/engine 호출을 선택적으로 `AnalysisService`로 교체(동작 동일, 표면적 통일).
3. `apply_score_offset_v2`/`filter_measurements`를 `src/gui/score_postprocess.py`로 추출(테스트 용이).
4. 대표 이미지로 GUI경로 vs 서비스경로 **점수 Δ 측정**(환경 필요).
5. Δ 수용 시 GUI를 옵션 B로 전환, 필요 시 `AnalysisService`에 분석함수 선택 파라미터 추가.

> 결론: #3은 "코드 중복 제거"와 "점수 정책 통일"이 얽혀 있어, 점수 Δ 결정 없이 자동 전환하면 안 됩니다. 본 단계에서 **안전한 단일 진입점(검증 완료)** 을 확보했고, 남은 전환은 위 검증 게이트를 통과한 뒤 적용을 권장합니다.

## 동봉 산출물
- `skinlens_analysis_service.zip` — 신규 `src/pipeline/analysis_service.py` 드롭인(추가형, **동작 불변**)
- `SkinLens_v1_refactored_db_llm_svc.zip` — #1(DB)+#2(LLM)+AnalysisService 누적 전체 프로젝트
- 본 설계/리뷰 md
