# 복원 이미지 기반 원본 점수 정확도 향상 — 설계 문서

> 작성일: 2026-05-27  
> 마지막 수정: 2026-05-28  
> 대상 버전: SkinLens v1  
> 관련 파일: `src/llm/llm_reporter.py`, `src/llm/llm_prompt_builder.py`, `docs/LLM_PROMPT_TEMPLATE.md`, `config/config.json`

---

## 1. 문제 정의

### 1.1 기존 방식의 한계

현재 `generate_dual_report()`는 원본·복원 이미지를 Gemini에 전달하지만,
Gemini에게 요청하는 작업은 **두 이미지를 각각 독립적으로 18개 항목 점수 산출**이다.

```
기존 프롬프트 핵심 지시:
"첨부된 두 장의 얼굴 사진(원본, 복원)을 분석하여
 각 이미지에 대한 18개 항목 점수를 직접 산출하고 소견을 작성하시오."
```

이 방식에서 복원 이미지는 **별도 분석 대상**일 뿐, 원본 점수의 정확도에 기여하지 않는다.

### 1.2 원본 이미지 단독 분석의 오탐 원인

| 오탐 원인 | 구체적 현상 | 영향 항목 |
|---|---|---|
| 조명 불균일 | 그림자가 주름·음영으로 오판 | 주름, 탄력 |
| 피부 수분·유분 | 반사광이 홍조·여드름으로 오판 | 홍조, 여드름 |
| 촬영 초점 흐림 | 모공 경계 불명확 → 과대평가 | 모공 |
| 색온도 편차 | 피부 톤 왜곡 | 기미, 톤 |
| JPEG 압축 아티팩트 | 색소 경계 번짐 | 기미, 주근깨 |

복원 이미지(GAN 복원)는 이 요인들이 제거된 **이상적 상태**이므로,
복원본에서 피부 구조를 먼저 파악한 뒤 원본에서 해당 구조가 얼마나
가려지거나 과장되었는지를 역산하면 원본 점수의 정확도가 높아진다.

---

## 2. 설계 목표

```
복원 이미지 → 피부 구조의 기준선(Reference) 확립
원본 이미지 → 기준선 대비 실제 상태를 역산
최종 출력   → 원본 점수 1세트 (정확도 향상)
```

| 항목 | 기존 방식 | 신규 방식 |
|---|---|---|
| 복원 이미지 역할 | 별도 분석 대상 | **원본 판단의 기준선** |
| Gemini 작업 | 두 이미지 각각 독립 점수 산출 | 복원 먼저 해석 → 원본 역산 |
| 출력 점수 세트 | 원본 + 복원 (2세트) | **원본 1세트** (정확도 향상) |
| 소견 구조 | 각각 독립 소견 | 복원 기반 → 원본 보정 소견 |

---

## 3. 아키텍처 설계

### 3.1 전체 흐름

```
generate_dual_report()
    │
    ├── [기존 유지] 처방전 계산, 제품 매칭
    │
    ├── [신규] _build_reference_guided_prompt()
    │       ↓
    │   프롬프트 3단계 지시:
    │     Step 1. 복원본 기준선 파악
    │     Step 2. 원본 → 오탐 요인 보정 역산
    │     Step 3. 최종 원본 점수 산출
    │
    ├── _call_llm([orig, ideal])          ← 이미지 순서 고정: 원본→복원
    │
    └── [신규] _parse_reference_guided_response()
            ↓
        JSON 파싱: orig_scores(18개) + 산출근거 + 소견
            ↓
        _build_orig_report_from_reference()
            ↓
        SkinLLMReport (원본 1개, 정확도 향상)
```

### 3.2 신규 진입점 메서드

```python
# LlmSkinReporter에 추가되는 public 메서드
def generate_reference_guided_report(
    self,
    orig_image_path: str | Path,
    ideal_image_path: str | Path,
    orig_measurements_report: Dict[str, Any],
    orig_overall_score: float,
    orig_perceived_age: float,
    ideal_measurements_report: Dict[str, Any],
    provide_scores: bool = True,
    product_info: Optional[str] = None,
) -> SkinLLMReport:
    """복원 이미지를 레퍼런스로 사용하여 원본 점수 정확도를 높인 보고서 반환."""
```

기존 `generate_dual_report()`는 **그대로 유지**한다. 신규 메서드는 완전히 독립적인 경로로 동작한다.

### 3.3 프롬프트 설계 — 3단계 순차 지시

Gemini가 3단계를 **순서대로** 따르도록 명시적으로 지시한다.
순서를 강제하지 않으면 두 이미지를 독립적으로 분석하는 기존 패턴으로 회귀한다.

```
Step 1 — 복원본 기준선 파악 (이미지 2번 먼저 분석)
  복원 이미지에서 아래 항목의 실제 피부 구조를 파악하십시오.
  - 주름: 위치, 방향, 깊이 추정
  - 모공: 분포 부위, 크기 범위
  - 색소: 기미·주근깨 위치와 농도
  - 탄력: 턱선 명확도, 볼 처짐 정도
  - 홍조: 분포 부위와 강도

Step 2 — 원본 오탐 요인 역산 (이미지 1번 분석)
  원본 이미지에서 Step 1의 구조가 아래 요인에 의해
  가려지거나 과장된 정도를 판단하십시오.
  - 조명 불균일: 그림자가 주름·음영처럼 보이는 영역
  - 광택·반사: 피부 유분이 홍조·발적처럼 보이는 영역
  - 초점 흐림: 모공 경계가 불명확한 영역
  - 색온도 편차: 전반적 피부 톤 왜곡
  - 압축 아티팩트: 색소 경계 번짐

Step 3 — 최종 원본 점수 산출
  Step 1(기준선)과 Step 2(보정)를 바탕으로
  원본 이미지의 18개 항목 점수를 산출하십시오.
  각 항목에 대해 '보정이 적용된 이유'를 correction_reason 필드에 기재하십시오.
```

### 3.4 응답 JSON 구조 (신규)

```json
{
  "reference_baseline": {
    "주름": "복원본에서 관찰된 기준선 서술",
    "모공": "복원본에서 관찰된 기준선 서술",
    "색소": "복원본에서 관찰된 기준선 서술",
    "탄력": "복원본에서 관찰된 기준선 서술",
    "홍조": "복원본에서 관찰된 기준선 서술"
  },
  "orig_metric_scores": {
    "melasma_score": 72.0,
    "freckle_score": 68.0,
    "...": "..."
  },
  "orig_metric_opinions": {
    "melasma_score": "원본 소견 (보정 내용 반영)",
    "...": "..."
  },
  "correction_reasons": {
    "melasma_score": "복원본 대비 조명으로 인한 색조 왜곡 보정 적용",
    "acne_score":    "반사광으로 인한 홍조 과장 요소 제거",
    "...": "..."
  },
  "orig_overall_score": 74.5,
  "orig_perceived_age": 38.0,
  "orig_overall_opinion": "종합 소견 5~8문장",
  "recommendation": "관리 권고사항"
}
```

### 3.5 기존 방식과 병행 운용

```
config.json:
  "llm": {
    "scoring_mode": "reference_guided"  // "independent"(기존) | "reference_guided"(신규)
  }
```

`scoring_mode`가 `"reference_guided"`이면 `generate_dual_report()` 내부에서
자동으로 `generate_reference_guided_report()`로 라우팅한다.
`"independent"`(기본값)이면 기존 방식을 유지한다.

---

## 4. 수정 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|---|---|---|
| `src/llm/llm_reporter.py` | 추가 | `generate_reference_guided_report()` 신규 public 메서드 |
| `src/llm/llm_reporter.py` | 추가 | `_parse_reference_guided_response()` 신규 private 메서드 |
| `src/llm/llm_reporter.py` | 수정 | `generate_dual_report()` — `scoring_mode` 분기 추가 |
| `src/llm/llm_prompt_builder.py` | 추가 | `_build_reference_guided_prompt()` 신규 함수 |
| `src/llm/llm_prompt_builder.py` | 추가 | `_build_score_criteria_section()` 신규 함수 (점수 기준 제공) |
| `docs/LLM_PROMPT_TEMPLATE.md` | 추가 | `REFERENCE_GUIDED_PROMPT` 섹션 추가 |
| `docs/LLM_PROMPT_TEMPLATE.md` | 수정 | "사용자" → "고객님" 표현 변경, 점수 기준 섹션 추가 |
| `config/config.json` | 추가 | `llm.scoring_mode` 필드 추가 |
| `config/config.json` | 추가 | `score_criteria` 섹션 추가 (점수 스케일, 등급 라벨) |
| `src/gui/compare_dialog.py` | 수정 | "보정 점수" → "복원 점수" 용어 변경 |
| `src/gui/compare_dialog.py` | 수정 | 복원 LLM 측정 없을 때 '-' 표시 로직 추가 |
| `src/server/deps.py` | 수정 | 동시 요청 처리 개선 (max_workers, max_concurrent_jobs) |

---

## 5. 점수 처리 로직

### 5.1 기존 `_apply_score_correction()` 재사용

신규 방식도 기존 하이브리드 보정 로직을 그대로 재사용한다.

```
최종 점수 = CV분석기 점수 × analyzer_weight
           + Gemini(reference_guided) 점수 × llm_weight
```

차이점: Gemini 점수가 복원 기준선을 반영한 **보정된 점수**라는 점에서
기존 방식의 독립 분석 점수보다 CV 분석기 점수와의 불일치가 줄어드는 효과가 있다.

### 5.2 `correction_reasons` 필드 활용

`_parse_reference_guided_response()`에서 `correction_reasons`를 파싱하여
`MetricOpinion.opinion` 뒤에 `[산출근거: ...]` 형태로 appendix한다.
디버그 로그에도 기록한다.

---

## 6. 항목별 보정 기대 효과

| 항목 | 오탐 원인 | 복원 기반 보정 효과 |
|---|---|---|
| 여드름 (acne_score) | 반사광·수분이 홍조로 오판 | 복원본에서 실제 병변 구조 확인 후 광택 제거분 역산 |
| 기미 (melasma_score) | 색온도·그림자로 경계 왜곡 | 복원본의 색소 경계를 기준으로 원본 왜곡 보정 |
| 모공 (pore_size_score) | 초점 흐림으로 과대평가 | 복원본의 선명한 모공 크기를 기준으로 역산 |
| 눈가 주름 (eye_wrinkle_score) | 그림자·눈밑 다크서클 혼동 | 복원본의 주름 선 명확도를 기준으로 보정 |
| 피부 톤 (skin_tone_score) | 조명 색온도 편차 | 복원본의 균일한 톤을 기준으로 원본 편차 역산 |

---

## 7. 제약 사항

- GAN 복원 품질이 낮으면(CodeFormer 신뢰도 < 0.5) 기준선 자체가 부정확해진다. 복원 신뢰도 점수를 프롬프트에 함께 전달하는 것이 권장된다.
- Gemini의 Step 1 → Step 2 → Step 3 순서 준수는 프롬프트 강제에 의존하므로, 응답에 `reference_baseline` 필드가 없으면 기존 방식으로 폴백한다.
- 처리 시간은 기존 대비 약 +8% 증가 (입력 토큰 동일, prefill 구조 변화만 발생).

---

## 8. 최신 변경 사항 (2026-05-28)

### 8.1 점수 기준 섹션 추가
- **변경**: CV 분석기 측정 점수 대신 점수 평가 기준 제공
- **이유**: LLM이 CV 점수에 의존하지 않고 독립적으로 점수를 산출하도록 유도
- **구현**:
  - `config/config.json`에 `score_criteria` 섹션 추가 (점수 스케일, 등급 라벨)
  - `llm_prompt_builder.py`에 `_build_score_criteria_section()` 함수 추가
  - 프롬프트 템플릿에서 `{cv_scores_section}` → `{score_criteria_section}` 변경

### 8.2 LLM 프롬프트 용어 정제
- **변경**: "사용자" → "고객님" 표현 변경
- **이유**: 고객 친화적 표현 사용
- **구현**:
  - 프롬프트 템플릿 내 "사용자" 표현을 "고객님"으로 변경
  - 소견 작성 가이드라인에 "고객님" 표현 사용 지시 추가

### 8.3 GUI 용어 정리
- **변경**: "보정 점수" → "복원 점수" 용어 변경
- **이유**: 용어 일관성 확보
- **구현**:
  - 18항목 비교창 테이블 헤더 변경
  - 비교창 타이틀 및 레전드 텍스트 변경
  - 엑셀 내보내기 메타데이터 텍스트 변경

### 8.4 복원 LLM 측정 표시 로직
- **변경**: `reference_guided` 모드에서 복원 LLM 측정 없을 때 '-' 표시
- **이유**: 복원 LLM 측정이 없음을 명확히 표시
- **구현**:
  - GUI 비교창에서 복원 LLM 측정 여부 확인 후 조건부 표시
  - 엑셀 내보내기에서 복원 LLM 측정 없을 때 '-' 표시
  - 텍스트 소견의 "분석 메타데이터" 섹션에서도 '-' 표시

### 8.5 동시 요청 처리 개선
- **변경**: 서버 동시 요청 처리 용량 증가
- **이유**: CLI 비동기 모드에서 다중 요청 처리 개선
- **구현**:
  - `ThreadPoolExecutor` `max_workers`를 환경변수 `SKIN_API_MAX_WORKERS`로 설정 가능 (기본값 4)
  - `JOB_SEMAPHORE` 기본값을 2에서 4로 상향 조정
  - `config.json` `max_concurrent_jobs`를 4로 변경
