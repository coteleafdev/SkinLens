# 코드 리뷰 및 변경 이력 (Code Review & Change History)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

---

## 개요

이 문서는 SkinLens v1.0의 코드 리뷰 결과, 변경 명세서, 리팩토링 계획을 시간 순서대로 정리한 것입니다.

---

## 3. 전체 코드 리뷰 v3 (2026-05-24)

### 리뷰 범위
- 총 라인 수: 27,414 라인 / 120+ 파일
- 테스트: 5,009 라인
- 검증 방법: Python 런타임 직접 실행 검증

### 수정 완료 항목

**P0 (Critical 버그 - 7건):**
- P0-1: PCR 처방 조건 역전 수정
- P0-2: BaseRestorer 추상 메서드 미구현 수정
- P0-3: skin_type_score 역산 상수 고정 수정
- P0-4: WebSocket asyncio 이벤트 루프 충돌 수정
- P0-5: SSRF 도메인명 차단 수정
- P0-6: path traversal 방어 수정
- P0-7: 고객 공유 패스워드 수정

**P1 (단기 - 8건):**
- P1-8: PCR av_total 하드코딩 수정
- P1-9: 믹스 코드 중복 시 base% 이중 계상 수정
- P1-10: roughness_score compose 함수 누락 수정
- P1-11: 데드 코드 서브점수 수정
- P1-12: LLM provider 추론 로직 수정
- P1-13~14: scripts logging import 수정
- P1-15: fidelity 기본값 수정

**P2 (중기 - 8건):**
- P2-16~19: 가짜 테스트 개선
- P2-20: BackgroundTasks 기본값 수정
- P2-21: Strategy Pattern 실제 사용
- P2-22: bp_optimizer.py CURRENT_BPS 이중 관리 수정
- P2-23: log vs logger 이름 통일

**P3 (장기 - 7건):**
- P3-24: 가중치 체계 삼원화 명시적 문서화
- P3-25: Markdown 설정 → config.json 이전 (이미 완료)
- P3-26: AGE_GROUP_MAPPING config 이전
- P3-27: subprocess cold-start → in-process 모델 상주 (이미 구현)
- P3-28: Python 3.8 호환성 (일부만 수정)
- P3-29: pytorch-lightning 업그레이드
- P3-30: deprecated alias DeprecationWarning (이미 구현)

### 추가 개선 사항

**복원 엔진 추상화 강화:**
- BaseRestorer에 전처리/후처리 훅 메서드 추가
- 모델 로드/언로드 라이프사이클 메서드 추가
- RestorerRegistry에 팩토리 메서드 추가
- RESTORATION_ENGINE_GUIDE.md 작성

### 수정 파일 목록
- `src/prescription/prescription_calculator.py`
- `src/restoration/base.py`
- `src/restoration/registry.py`
- `src/restoration/strategies/codeformer_restorer.py`
- `src/restoration/strategies/restoreformer_restorer.py`
- `src/pipeline/pipeline_core.py`
- `src/scoring/skin_scoring.py`
- `src/server/routers/jobs.py`
- `src/server/deps.py`
- `src/server/routers/auth.py`
- `src/llm/llm_reporter.py`
- `scripts/bp_optimizer.py`
- `scripts/score_bias_monitor.py`
- `config/config.json`
- `requirements-core.txt`
- `src/telegram/monitors.py`
- 다수 로거 이름 통일 파일 (23개)

---

## 1. 코드 리뷰 (2026-05-15)

### 전체 지표 요약

| 지표 | 값 | 비고 |
|---|---|---|
| 총 라인 수 | 23,904 | Python 46개 파일 |
| 문법 오류 | 0 | 전 파일 AST 파싱 통과 |
| bare except | 0 | 양호 |
| silent except (except: pass) | 66건 | 16개 파일 |
| print() 직접 사용 | 311건 | logger 미사용 |
| 최대 함수 길이 | 531줄 | `image_enhancer._cli()` |
| TODO/BUG 주석 | 25건 | 미해결 이슈 포함 |

### 주요 이슈

**CRIT — 즉시 수정 필요:**

1. **`server.py` — `_safe_filename()` Path traversal 취약점**
   - `os.path.basename(name)`만 적용
   - `../`·공백·제어문자·`.php/.sh` 위장 파일명 차단 필요
   - **수정 방향:** 허용 확장자 whitelist 추가, 정규식 검증

---

## 2. 듀얼 이미지 Gemini AI 통합 (2026-05-13)

### 변경 파일
- `gemini_skin_report.py` — 듀얼 이미지 프롬프트 빌더, API 호출, JSON 파싱 추가
- `skin_measurement_chart_dialog.py` — 듀얼 Gemini 점수 열 추가, 엑셀 보고서 업데이트

### 주요 기능
1. 원본/복원 이미지를 한 번의 API 호출로 Gemini에 전송
2. 두 이미지에 대한 별도의 18개 항목별 소견 생성
3. GUI에 원본/복원 Gemini 측정 점수 열 분리 표시
4. 엑셀 보고서에 원본/복원 소견 구분 출력
5. 전체 처리시간 로그 추가

### API 설정
- 단일 이미지 모드: Max Output Tokens 8192
- 듀얼 이미지 모드: Max Output Tokens 16384
- Temperature: 0.3

### JSON 응답 구조 (듀얼 모드)
```json
{
  "original_metric_opinions": { ... },  // 원본 이미지 18개 항목 소견
  "restored_metric_opinions": { ... }, // 복원 이미지 18개 항목 소견
  "original_overall_opinion": "...",   // 원본 종합 소견
  "restored_overall_opinion": "...",  // 복원 종합 소견
  "recommendation": "..."               // 관리 권고사항
}
```

---

## 3. 피부 분석 시스템 v3.5 변경 명세서 (2026-05-05)

### 배경 및 문제 정의

**시스템 개요:**
COTELEAF 피부 분석 시스템은 입력 원본 사진과 CodeFormer로 복원한 이상 이미지를 각각 분석하여 18개 항목의 점수를 비교함으로써 피부 상태를 정량화하는 플랫폼입니다. 핵심 사용자 경험은 **"복원 이미지가 원본보다 명확히 높은 점수를 받아야 한다"**는 것입니다.

### v3.4 기준 실측 점수차

| 항목 | 원본 | 복원 | 차이(Δ) |
|------|------|------|---------|
| melasma_score | 54.0 | 54.0 | **±0** |
| freckle_score | 42.0 | 42.0 | **±0** |
| pore_size_score | 66.0 | 78.0 | +12 |
| roughness_score | 66.0 | 82.0 | +16 |
| fine_deep_wrinkle_score | 66.0 | 80.4 | +14 |
| acne_score | 50.0 | 66.0 | +16 |
| **overall_score** | **62.8** | **66.7** | **+3.9** |

목표(Δ ≈ 15점)와 실측(Δ +3.9점) 간에 약 11점 격차가 존재했습니다.

### 기존 시스템의 구조적 문제

**문제 1: 20점 단위 강제 양자화**
- 모든 `_score` 항목이 분석 직후 10 / 30 / 50 / 70 / 90 의 5단계 정수로 강제 반올림
- 연속적인 측정값 차이가 양자화 경계에 걸리면 완전히 소거

**문제 2: 원시 신호와 점수 간 비선형 매핑**
- 원시 신호의 큰 변화가 점수에는 작게 반영

### v3.5 변경 사항

1. 양자화 제거: 연속 점수 사용
2. 원시 신호 반영 비율 증가
3. 복원 효과 점수 계산 로직 개선

---

## 4. ExecutionHistoryDB 리팩토링 (2026-05-20)

### 현재 상태

**ExecutionHistoryDB 클래스 구조:**
- **위치**: `src/cli/execution_history.py` L182-L1932
- **크기**: 1,750줄
- **메서드**: 42개 (공개 37개, 내부 5개)
- **문제**: 단일 클래스가 너무 많은 책임을 담당 (God Object)

### 리팩토링 계획

**Repository 패턴 분리:**

1. **ExecutionHistoryDB** (유지)
   - 연결·스키마·내부 유틸 (9개 메서드)

2. **ExecutionStatsRepository** (분리)
   - 실행 이력 관리 (4개 메서드)
   - `log_execution`, `get_recent_executions`, `get_statistics`, `cleanup_old_records`

3. **AnalysisStatsRepository** (분리)
   - 분석 통계 (8개 메서드)
   - `record_analysis_stat`, `get_analysis_stat`, `record_model_performance`, `get_model_performance`, `record_score_trend`, `get_score_trends`

4. **ErrorAuditRepository** (분리)
   - 에러/감사 (6개 메서드)
   - `get_error_summary`, `record_error`, `get_audit_log`, `record_audit_event`

### 상태

**전체 완료** ✅ (2026-05-20)

---

## 5. 참고 문서

- `DEVELOPMENT_GUIDE.md` - 개발 가이드
- `ARCHITECTURE_GUIDE.md` - 아키텍처 가이드
- `SKIN_SCORING_GUIDE.md` - 스코어링 가이드

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (v3.6에서 마이그레이션) | Cascade |
| 0.6.0 | 2026-05-24 | 코드 리뷰 및 변경 이력 초기 작성 | Cascade |
