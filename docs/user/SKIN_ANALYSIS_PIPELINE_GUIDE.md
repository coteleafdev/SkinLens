# 피부 분석 파이프라인 가이드 (Skin Analysis Pipeline Guide)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

---

## 1. 개요

`skin_analysis_pipeline.py`는 AI Skin Analysis Pipeline의 v3 진입점 파일입니다. `pipeline_core.py`에 구현된 파이프라인 엔진을 통해 RestoreFormer++/CodeFormer 복원 모델을 사용하여 피부 이미지를 보정합니다.

### v1.0 주요 변경사항

- **skin_scoring 통합**: 피부 분석 시스템이 v1.0으로 업그레이드되어 이중구조 출력 지원
  - **레이어A (10개 직교 항목)**: 엔진 정확도용 신호 분해 출력
  - **레이어B (18개 보고서 항목)**: 고객 보고서용 역매핑 출력
- **GUI/CLI 통합**: 단일 파일에서 GUI(PySide6)와 CLI 모두 지원
- **복원 백엔드 선택**: RestoreFormer++와 CodeFormer 중 선택 가능
- **점수 팝업**: 파이프라인 완료 후 원본 vs 결과 점수 비교 팝업 지원

### v1.1 버그수정 / 개선사항

- **`skin_stat` 반환**: `SkinAnalyzerV3.analyze_all()`이 `skin_stat`과 `ref_stat` 파라미터를 지원해 이상 이미지 기준 상대 측정이 활성화됨
- **`dullness_score` 정밀 복원**: `raw_measurements` 보존 경로 구현으로 `tone_score×0.88` 근사 대신 원신호 직접 사용
- **복원 팝업 4열 단순화**: `RestoreScoreResultDialog`를 원본/복원/차이 4열로 단순화 (이상1·이상2 중복 제거)
- **종합 점수 레이어 통일**: 비교 다이얼로그 및 팝업의 종합 점수가 레이어B(`overall_score_report`) 기준으로 통일됨
- **분석 실패 안전 처리**: `_input_has_stressed_pigmentation()` 실패 시 강한 튜닝 적용 방지
- **로깅 lazy 초기화**: `import` 시 즉시 실행되던 로거 설정이 첫 `SkinAnalyzerV3()` 생성 시로 이동
- **CodeFormer `--bg_upsampler` 자동 결정**: RealESRGAN 가중치 파일 존재 여부를 자동 탐색해 크래시 방지
- **CodeFormer 한글 경로 대응**: 입력 이미지를 ASCII 파일명으로 스테이징하여 `cv2.imread` 실패 방지
- **모공 완화 경로 탐색 강화**: `res.restored` 실제 경로를 파일명 패턴보다 먼저 확인
- **VRAM 해제 강화**: `clear_diffusion_pipeline_cache()` 호출 시 `torch.cuda.empty_cache()` 추가

### v1.2 GUI 버그수정 / 개선사항

- **비교 프로세스 고아 방지**: 메인 창 종료 시 `--compare` 서브프로세스도 `kill()` 처리
- **파이프라인 로그 순서 보장**: 메인 프로세스에 `MergedChannels` 적용 — RF++/CF stderr 출력이 로그창 순서대로 표시
- **`--no-analyzer-score-tune` 체크박스 추가**: 복원 후 21항목 점수 자동 튜닝을 GUI에서도 끄고 켤 수 있음
- **로그 멀티라인 분리**: 버퍼 단위 수신 시 개행 포함 데이터가 단일 단락으로 뭉치던 문제 해결
- **비교 프로세스 슬롯 분리**: `finished` 튜플 람다 → `_on_compare_finished` 전용 메서드로 분리

### v1.4 듀얼 이미지 Gemini AI 통합 (2026-05-13)

- **듀얼 이미지 Gemini AI 통합**: `gemini_skin_report.py`에 듀얼 이미지 모드 구현
  - 원본/복원 이미지를 한 번의 API 호출로 Gemini에 전송
  - 두 이미지에 대한 별도의 21개 항목별 소견 생성
  - Max Output Tokens: 단일 모드 8192 → 듀얼 모드 16384
- **GUI 듀얼 Gemini 점수 열 추가**: 피부분석 비교창에 원본/복원 Gemini 측정 점수 열 분리 표시
- **엑셀 보고서 듀얼 Gemini 점수 및 소견 처리**:
  - 원본 이미지 라벨 위치: 1C → 1B
  - 【원본 이미지 21개 항목별 소견】/【복원 이미지 21개 항목별 소견】 앞 공백행 추가
  - gemini_text 파싱 시 소견 섹션 구분 처리
- **전체 처리시간 로그 추가**: 실행부터 표시까지의 소요시간 로그 출력
- **파이프라인 끝 점수 팝업 비활성화**: GUI 체크박스 숨김 및 기능 비활성화
- **트러블 진행 로그 개선**: 고정 20분할 진행 카운트에서 경과 시간 기반(10초마다 1회)으로 변경. 성분 수에 무관하게 장시간 처리 시 균일하게 진행 상황을 표시합니다.

### v1.4 GUI/CLI 파라미터 제어 개선

- **복원 백엔드 기본값 CodeFormer로 변경**: RestoreFormer++에서 CodeFormer로 기본 복원 백엔드 변경
  - CLI: `--restorer codeformer` 기본
  - GUI: CodeFormer 라디오 버튼 기본 선택
- **CodeFormer fidelity 기본값 1.0으로 변경**: 원본 충실을 기본으로 사용하여 사용자 설정 존중
  - CLI: `--cf-fidelity 1.0` 기본 (기존 0.52)
  - GUI: fidelity 스피너 1.0 기본
- **CodeFormer upscale 기본값 1로 변경**: 업스케일 없음을 기본으로 사용
  - CLI: `--cf-upscale 1` 기본 (기존 2)
  - GUI: upscale 스피너 1 기본
- **동작 모드 체크박스 횡 배치**: 동작 모드 그룹박스의 체크박스들을 2행으로 횡 배치하여 공간 효율 개선
  - 색소 부담 입력 시 `pore.enabled = False`는 유지 (안전장치)
- **CodeFormer fidelity 사용자 설정 존중**: 튜닝 함수에서 `codeformer_fidelity` 강제 낮춤 제거
  - 기존: 일반 입력 시 무조건 0.08로 강제 낮춤 (뿌옇음 방지)
  - 변경: 사용자가 명시적으로 설정한 fidelity 값을 존중
- **이전 실행 파일 참조 방지**: `final_pipeline_artifact_path`에서 현재 실행에서 pore_soft가 생성되지 않았으면 파일 시스템의 오래된 pore_soft 파일도 참조하지 않도록 수정
  - CLI와 GUI 동일하게 적용
  - 미리보기 로직에서도 체크박스 상태에 따라 파일 확인 여부 분리
- **CLI/GUI 동작 통일**: CLI와 GUI에서 파라미터 제어 방식이 완전히 동일하게 동작

---

## 2. 파일 의존성

### 2.1 Python 패키지 의존성

**필수 패키지** (`requirements.txt`):
```
torch>=2.1.0
torchvision>=0.16.0
transformers>=4.36.0
accelerate>=0.26.0
safetensors>=0.4.0
numpy>=1.24.0
Pillow>=10.0.0
opencv-python>=4.8.0
```

**GUI 전용 패키지** (`requirements-optional.txt`):
```
PySide6>=6.5.0
scikit-image>=0.21.0
markdown>=3.5.0
```

### 2.2 Python 파일 의존성

**메인 파일:**
- `skin_analysis_pipeline.py` — 진입점 (본 파일)

**핵심 모듈:**
- `pipeline_core.py` — 파이프라인 코어 로직
  - `PipelineSettings` — 복원 설정 dataclass
  - `run_enhancement_pipeline()` — 메인 파이프라인 진입점
  - 파이프라인 모드 Enum 분기 (`_PipelineMode`)

- `skin_scoring.py` — 피부 분석 시스템 v1.0
  - 레이어A: 10개 직교 항목 (엔진 출력)
  - 레이어B: 21개 보고서 항목 (표시 출력)
  - 이중구조 출력 지원

**GUI 모듈** (GUI 실행 시만 필요):
- `skin_analysis_gui.py` — 메인 GUI 윈도우
- `skin_measurement_chart_dialog.py` — 21항목 비교 다이얼로그
- `analyzer_compare_gui.py` — 점수 비교 GUI

### 2.3 외부 폴더 의존성

**선택적 폴더 (복원 백엔드):**
- `RestoreFormerPlusPlus/` — RestoreFormer++ 복원 모델 (`--restorer restoreformer`, 기본)
  - `RestoreFormerPlusPlus/inference.py` 필요
- `CodeFormer/` — CodeFormer 복원 모델 (`--restorer codeformer`)
  - `CodeFormer/inference_codeformer.py` 필요
  - `CodeFormer/weights/realesrgan/RealESRGAN_x2plus.pth` 또는 `RealESRGAN_x4plus.pth` — 있으면 배경 업스케일 자동 활성화, 없으면 `bg_upsampler=none`으로 자동 폴백

### 2.4 의존성 다이어그램

```
skin_analysis_pipeline.py
    │
    ├─→ pipeline_core.py
    │       │
    │       ├─→ Pillow (이미지 입출력·리사이즈)
    │       └─→ RestoreFormerPlusPlus/ 또는 CodeFormer/ (in-process, 모델 캐싱)
    │
    ├─→ skin_scoring.py
    │       │
    │       ├─→ opencv-python (CV 파이프라인)
    │       ├─→ scikit-image (LBP, Gabor, blob_log)
    │       └─→ numpy
    │
    └─→ GUI 모듈 (PySide6 실행 시만)
            │
            ├─→ skin_analysis_gui.py
            ├─→ skin_measurement_chart_dialog.py
            └─→ analyzer_compare_gui.py
```

---

## 3. 실행 모드

### 3.1 GUI 모드

```bash
python skin_analysis_pipeline.py
```

**기능:** 입력 이미지 선택, 파라미터 설정 (SD strength·복원 백엔드·CodeFormer 파라미터·모공 완화 등), 파이프라인 실행 및 로그 표시, 미리보기, 17항목 비교 다이얼로그

**GUI 레이아웃:**
- **입출력·모드 탭**: 입력 이미지, 산출 폴더, 동작 모드 체크박스들 (횡 배치, v1.4)
- **얼굴 복원 백엔드 그룹박스**: 복원 백엔드 선택(RF++/CodeFormer), CodeFormer 추가 복원 체크박스, CF 파라미터(fidelity, 업스케일)
  - "입출력·모드" 탭의 "동작 모드" 그룹박스 아래에 별도 배치
  - 횡 배치로 공간 효율적 사용
  - 레포 루트 입력 필드는 GUI에서 제거됨 (CLI 전용 `--restoreformer-root`, `--codeformer-root` 사용)

**GUI 전용 체크박스 (v1.2 추가):**

| 체크박스 | 기본값 | 대응 CLI 인자 | 설명 |
|----------|--------|---------------|------|
| 복원 실행 | ✓ | `--no-restore` | 해제 시 복원 생략 |
| RF++ 후 CodeFormer 추가 복원 | ✓ | `--no-cf-additional` | 해제 시 RF++ 단독 실행 (CodeFormer 백엔드 선택 시 비활성화) |
| 파이프라인 끝 점수 팝업 | ✓ | `--no-restore-score-popup` | 해제 시 팝업 끄기 |
| 복원 후 17항목 점수 자동 튜닝 | ✓ | `--no-analyzer-score-tune` | 해제 시 튜닝 끄기 |

**필요 패키지:** `requirements.txt` + `requirements-optional.txt` (PySide6 포함)

### 3.2 CLI 모드

```bash
python skin_analysis_pipeline.py --cli [인자...]
```

**기본 CLI 명령:**
```bash
python skin_analysis_pipeline.py --cli -i images/origin.png --out-dir reference_pipeline_out
```

**주요 인자:**

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `-i, --input` | `images/origin.png` | 입력 이미지 경로 |
| `--out-dir` | `reference_pipeline_out` | 산출 폴더 |
| `--restorer` | `codeformer` (v1.4) | 복원 백엔드 (`restoreformer` \| `codeformer`) |
| `--cf-additional` | `True` (config.json) | RF++ 복원 후 CodeFormer 추가 복원 (끄려면 `--no-cf-additional`) |
| `--cf-fidelity` | `1.0` (v1.4) | CodeFormer fidelity (0=최대보정, 1=원본충실) |
| `--cf-upscale` | `1` (v1.4) | CodeFormer 업스케일 배수 (1=없음, 2=2배, 4=4배) |
| `--no-restore` | — | 복원 생략 |
| `--no-restore-score-popup` | — | 점수 팝업 끄기 |
| `--no-analyzer-score-tune` | — | 자동 튜닝 끄기 |

> **참고:** CodeFormer 관련 파라미터(`--cf-fidelity`, `--cf-upscale`, `--cf-additional`)의 기본값은 v1.4에서 직접 설정됩니다. `--cf-additional`만 `config/config.json`에서 로드됩니다.

**필요 패키지:** `requirements.txt` + `scikit-image>=0.21.0`

---

## 4. 파이프라인 모드 (`_PipelineMode`)

`pipeline_core.py` 내부의 `_PipelineMode` Enum으로 실행 경로를 분기합니다.

### 4.1 RESTORE_ONLY (기본)

입력 이미지 있음 + 복원 레포 유효. 복원만 실행.

```bash
python skin_analysis_pipeline.py --cli -i images/origin.png
```

**산출 파일:**

| 파일명 | 조건 | 설명 |
|--------|------|------|
| `00_input_{stem}.png` | 항상 | 입력 RGB 스테이징 (원본 해상도 유지) |
| `01_restored_{stem}.png` | 복원 성공 시 | 복원(RF++/CF) 결과 |

### 4.2 ANALYZE_ONLY (`--no-restore`)

복원 생략. 원본 이미지를 직접 분석.

```bash
python skin_analysis_pipeline.py --cli -i images/origin.png --no-restore
```

**산출:** `00_input_{stem}.png` → 원본 이미지 직접 분석

---

## 5. 복원 파이프라인 상세

**개요**
- CodeFormer는 얼굴 복원 및 업스케일에 널리 사용되는 모델
- 코드 기반의 얼굴 특성 복원
- 배경 업스케일 옵션 지원 (RealESRGAN)

**동작 방식**
1. **얼굴 감지**: 입력 이미지에서 얼굴 영역 자동 감지
2. **코드 복원**: F-Code 기반 얼굴 특성 복원
3. **fidelity 조절**: 복원 강도 조절 (0=최대 보정, 1=원본 충실)
4. **업스케일**: 지정된 배수로 해상도 증가
5. **배경 처리**: RealESRGAN으로 배경 업스케일 (옵션)

**파라미터**
| 파라미터 | CLI 인자 | 기본값 | 설명 |
|----------|----------|--------|------|
| `codeformer_repo` | `--codeformer-root` | `./CodeFormer` (자동 탐색) | 레포 루트 |
| `codeformer_fidelity` | `--cf-fidelity` | `1.0` | 0=최대 보정, 1=원본 충실 |
| `codeformer_upscale` | `--cf-upscale` | `2` | 업스케일 배수 |
| `codeformer_bg_upsampler` | — | `"auto"` → 자동 결정 | RealESRGAN 배경 업스케일 여부 |

**`codeformer_bg_upsampler` 자동 결정 (v1.1):**  
`PipelineSettings.__post_init__` 시 아래 경로를 탐색합니다. 파일이 있으면 `"realesrgan"`, 없으면 `"none"`으로 자동 설정되어 가중치 미설치 환경의 크래시를 방지합니다.

```
CodeFormer/weights/realesrgan/RealESRGAN_x2plus.pth   ← 탐색 대상
CodeFormer/weights/realesrgan/RealESRGAN_x4plus.pth   ← 탐색 대상
CodeFormer/weights/RealESRGAN_x2plus.pth              ← 대체 경로
```

**레포 구조**
```
CodeFormer/
    inference_codeformer.py          ← 필수
    weights/
        CodeFormer/
            codeformer.pth           ← 자동 다운로드 또는 사전 배치
        realesrgan/
            RealESRGAN_x2plus.pth    ← 배경 업스케일 (옵션)
```

### 5.3 복원 파이프라인 흐름 (기본: RF++ → CodeFormer)

**단계별 동작**

1. **입력 이미지 스테이징**
   - 원본 이미지를 RGB로 변환
   - 파일명 스테이징 (한글 경로 문제 해결)
   - 출력: `00_input_{stem}.png`

2. **RestoreFormer++ 복원**
   - RF++ 모델로 1차 복원 수행
   - 얼굴 구조 및 텍스처 복원
   - 출력: `00_restored_{stem}.png`

3. **CodeFormer 추가 복원** (cf-additional=True, 기본)
   - RF++ 결과를 CodeFormer로 추가 복원
   - fidelity=1.0으로 점수 경향 맞춤
   - 2x 업스케일 적용
   - 최종 복원 이미지 출력: `01_restored_{stem}.png`
   - cf-additional=False 시 이 단계 생략

4. **점수 분석**
   - 원본 이미지 분석 (18개 측정 항목)
   - 복원 이미지 분석 (ref_stat 기준)
   - 점수 튜닝 적용

5. **점수 안전장치** (2026-05-25 수정)
   - 패스스루 조건: 복원 점수 >= 원본 점수 - 5.0이면 안전장치 적용하지 않음
   - 복원 점수 < 원본 점수 - 5.0: 안전장치 적용 (개별 항목 클램프 비활성화, 종합 점수 기반만 유지)

**설정 파일 로드**
- `config/config.json`에서 점수 파라미터 로드
- 파일 수정 시 자동 감지 및 재로드 (서버 환경 지원)

---

### 5.3 오류 JSON 출력

오류 발생 시 JSON 형식으로 오류 정보가 출력되어 외부 모니터링이 가능합니다:

```json
{
  "error": true,
  "error_type": "FileNotFoundError",
  "error_message": "입력 이미지를 찾을 수 없습니다",
  "timestamp": "2026-04-29T12:34:56.789012",
  "input_image": "images/origin.png",
  "output_dir": "reference_pipeline_out"
}
```

**오류 JSON 필드**:
- `error`: 항상 `true`
- `error_type`: 오류 타입 (예: `FileNotFoundError`, `ValueError`)
- `error_message`: 오류 메시지
- `timestamp`: 오류 발생 시간 (ISO 8601)
- `input_image`: 입력 이미지 경로
- `output_dir`: 출력 디렉토리 경로
- `error_traceback`: 스택 트레이스 (`--debug` 모드일 때만 포함)

**오류 JSON 파일 저장**:
```bash
python skin_analysis_pipeline.py --cli -i images/origin.png --output-json result.json
```
오류 발생 시 `result.json`에 오류 JSON이 저장됩니다.

**디버그 모드**:
```bash
python skin_analysis_pipeline.py --cli -i images/origin.png --debug
```
`--debug` 모드에서는 오류 JSON에 `error_traceback` 필드가 포함됩니다.

---

## 6. 복원 백엔드 (`PipelineSettings.restorer`)

### 5.1 RestoreFormer++

```bash
python skin_analysis_pipeline.py --cli -i images/origin.png --restorer restoreformer
```

| 설정 | CLI 인자 | 기본값 |
|------|----------|--------|
| `restoreformer_repo` | `--restoreformer-root` | `./RestoreFormerPlusPlus` (자동 탐색) |

**레포 구조:**
```
RestoreFormerPlusPlus/
    inference.py    ← 필수
```

### 6.2 CodeFormer (기본, v1.4)

```bash
python skin_analysis_pipeline.py --cli -i images/origin.png --restorer codeformer
```

| 필드 | CLI 인자 | 기본값 | 설명 |
|------|----------|--------|------|
| `codeformer_repo` | `--codeformer-root` | `./CodeFormer` (자동 탐색) | 레포 루트 |
| `codeformer_fidelity` | `--cf-fidelity` | `1.0` (v1.4) | 0=최대 보정, 1=원본 충실 |
| `codeformer_upscale` | `--cf-upscale` | `1` (v1.4) | 업스케일 배수 (1=없음, 2=2배, 4=4배) |
| `codeformer_bg_upsampler` | — | `"auto"` → 자동 결정 | RealESRGAN 배경 업스케일 여부 |

**`codeformer_bg_upsampler` 자동 결정 (v1.1):**  
`PipelineSettings.__post_init__` 시 아래 경로를 탐색합니다. 파일이 있으면 `"realesrgan"`, 없으면 `"none"`으로 자동 설정되어 가중치 미설치 환경의 크래시를 방지합니다.

```
CodeFormer/weights/realesrgan/RealESRGAN_x2plus.pth   ← 탐색 대상
CodeFormer/weights/realesrgan/RealESRGAN_x4plus.pth   ← 탐색 대상
CodeFormer/weights/RealESRGAN_x2plus.pth              ← 대체 경로
```

**레포 구조:**
```
CodeFormer/
    inference_codeformer.py          ← 필수
    weights/
        CodeFormer/
            codeformer.pth           ← 자동 다운로드 또는 사전 배치
        realesrgan/
            RealESRGAN_x2plus.pth    ← 있으면 bg_upsampler=realesrgan 자동 활성화
```

---

## 7. skin_scoring 이중구조 출력

### 7.1 레이어A (10개 직교 항목)

| 항목 | 가중치 | 설명 |
|------|--------|------|
| `pigmentation_cov` | 0.120 | 색소 면적 (melasma+pigment_mark) |
| `spot_density` | 0.100 | 반점 밀도 (lentigo blob 이산) |
| `diffuse_redness` | 0.120 | 홍조 (a* 전역 z-score) |
| `focal_lesion` | 0.140 | 국소 병변 (acne+red_mark) |
| `pore_score` | 0.120 | 모공 (크기·처짐 가중 합산) |
| `wrinkle_score` | 0.130 | 주름 (eye·nasolabial·fine_deep) |
| `roughness_score` | 0.080 | 피부결 (LBP 직접 전달) |
| `tone_score` | 0.100 | 톤·균일도 (ITA+uniformity) |
| `elasticity_score` | 0.050 | 탄력 (jawline+cheek_sagging) |
| `skin_type_score` | 0.040 | 피부 타입 (skin_type_score 직접 전달) |

**접근:**
```python
result = analyzer.analyze_all("face.jpg")
measurements_a = result["measurements"]      # 레이어A — 10개 직교
overall_score_a = result["overall_score"]    # 레이어A 종합
skin_stat       = result["skin_stat"]        # 피부 통계 (ref_stat 비교용)
```

**이상 이미지 기준 상대 측정 (`ref_stat`, v1.1):**
```python
ref_result = analyzer.analyze_all("reference.jpg")
orig_result  = analyzer.analyze_all(
    "origin.jpg",
    ref_stat=ref_result["skin_stat"],
)
```

### 7.2 레이어B (18개 보고서 항목)

**항목:**
- 색소: `melasma_score`, `lentigo_score`, `pigment_mark_score`
- 홍조, 홍반: `redness_score`, `post_inflammatory_erythema_score`
- 트러블·흔적: `acne_score`, `post_acne_pigment_score`
- 모공: `pore_size_score`, `pore_sagging_score`
- 주름: `eye_wrinkle_score`, `nasolabial_wrinkle_score`, `fine_deep_wrinkle_score`
- 텍스처: `roughness_score`
- 톤·밝기: `skin_tone_score`, `dullness_score`\*, `uneven_tone_score`
- 탄력: `jawline_blur_score`
- 수분: `skin_type_score`

> `*dullness_score`: v1.0 직교 분해에서 제거된 항목. v1.1에서 `raw_measurements` 보존 경로를 통해 원신호 직접 복원. 보고서 출력 시 `*직접` 또는 `*v3근사` 표기로 구분됩니다.

**접근:**
```python
result = analyzer.analyze_all("face.jpg")
measurements_b  = result["measurements_v18"]      # 레이어B — 18개 보고서
overall_score_b = result["overall_score_report"]  # 레이어B 종합
```

### 7.3 사용 예시

```python
from skin_scoring import SkinAnalyzerV3

analyzer = SkinAnalyzerV3()
result   = analyzer.analyze_all("face.jpg")

# 레이어A (10개 직교)
print(f"엔진 종합 점수: {result['overall_score']}")
print(f"엔진 측정: {result['measurements']}")

# 레이어B (18개 보고서)
print(f"보고서 종합 점수: {result['overall_score_report']}")
print(f"보고서 측정: {result['measurements_v18']}")

# dullness_score 복원 방식 확인
print("dullness 복원:", "직접" if "dullness_score" in result.get("raw_measurements", {}) else "tone근사")

# 보고서 출력 문자열 (*직접/*v3근사 표기 포함)
analyzer.print_results_report(result)

# 이상 이미지 기준 상대 측정
ref = analyzer.analyze_all("reference.jpg")
orig  = analyzer.analyze_all("origin.jpg", ref_stat=ref["skin_stat"])
```

---

## 9. 점수 튜닝 (`--analyzer-score-tune`)

복원 사용 시 skin_scoring 레이어B 17항목이 입력보다 오르기 쉽도록 파라미터를 자동 튜닝합니다.

**기본 켜짐 / 끄기:**

CLI:
```bash
python skin_analysis_pipeline.py --cli -i images/origin.png                           # 켜짐
python skin_analysis_pipeline.py --cli -i images/origin.png --no-analyzer-score-tune  # 끄기
```

GUI: 입출력·모드 탭 → **「복원 후 17항목 점수 자동 튜닝」** 체크박스로 제어 (v1.2 추가)

**튜닝 내용:**
- 모공·톤·주름·트러블 후처리 강도 조정
- 색소 부담이 큰 입력은 홍조·모공늘어짐 보호용 완화 튜닝
- **분석 실패 안전 처리 (v1.1):** `skin_scoring` import 오류·예외 발생 시 `None` 반환 → 강한 튜닝 적용 방지, 경고 출력 후 건너뜀
- **사용자 선택 존중 (v1.4):**
  - 튜닝 함수에서 `pore.enabled = True` 강제 설정 제거 (사용자가 명시적으로 끈 경우 유지)
  - 튜닝 함수에서 `codeformer_fidelity` 강제 낮춤 제거 (사용자가 명시적으로 설정한 값 존중)

---

## 10. 점수 팝업 (`--restore-score-popup`)

파이프라인 완료 후 원본 vs 결과 점수 비교 팝업을 표시합니다.

**기본 켜짐 / 끄기:**

CLI:
```bash
python skin_analysis_pipeline.py --cli -i images/origin.png                            # 켜짐
python skin_analysis_pipeline.py --cli -i images/origin.png --no-restore-score-popup   # 끄기
```

GUI: 입출력·모드 탭 → **「파이프라인 끝 점수 팝업」** 체크박스로 제어

**v1.1 변경:** 팝업 테이블이 6열(이상1/이상2 중복)에서 4열(항목/원본/복원/차이)로 단순화됩니다. 종합 점수도 레이어B(`overall_score_report`) 기준으로 통일됩니다.

---

## 11. 설치

### 11.1 전체 설치 (GUI + CLI)

```bash
pip install -r requirements.txt
pip install -r requirements-optional.txt
```

### 11.2 CLI 전용 설치

```bash
pip install -r requirements.txt
pip install scikit-image>=0.21.0
```

### 11.3 CUDA 사용 시

```bash
# PyTorch CUDA 설치 (예: CUDA 11.8)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 나머지 패키지
pip install -r requirements.txt
```

---

## 12. 문제 해결

### 12.1 `ImportError: No module named 'PySide6'`

```bash
pip install PySide6>=6.5.0
```

### 12.2 `ModuleNotFoundError: No module named 'pipeline_core'`

`skin_analysis_pipeline.py`와 같은 디렉토리에서 실행해야 합니다:

```cmd
cd "c:\Project\AI Skin v3"
python skin_analysis_pipeline.py
```

### 12.3 RestoreFormer++ 오류

`RestoreFormerPlusPlus/inference.py`가 있는지 확인하세요:

```bash
git clone https://github.com/wzhouxiff/RestoreFormerPlusPlus.git
```

### 12.4 CodeFormer 크래시 (`realesrgan` 관련)

v1.1에서는 RealESRGAN 가중치 파일 존재 여부를 자동 탐색하여 크래시를 방지합니다. 구버전 사용 중이라면 v1.1로 업데이트하거나, 코드에서 직접 `"none"`으로 강제 설정할 수 있습니다:

```python
from pipeline_core import PipelineSettings, Restorer
cfg = PipelineSettings(
    restorer=Restorer.CODEFORMER,
    codeformer_bg_upsampler="none",
)
```

가중치를 설치하려면:
```
CodeFormer/weights/realesrgan/RealESRGAN_x2plus.pth
```

### 12.5 CodeFormer 한글 경로 오류

v1.1에서 입력 이미지를 ASCII 파일명(`cf_input.png`)으로 임시 스테이징하여 처리하므로 한글 경로도 정상 동작합니다. 이전 버전에서 오류가 발생했다면 v1.1로 업데이트하세요.

### 12.6 `skin_scoring` import 실패

```bash
pip install scikit-image>=0.21.0
```

### 12.7 `ref_stat` 비교가 작동하지 않는 경우

v1.1 미만 `skin_scoring`를 사용 중입니다. 지원 여부를 확인하세요:

```python
import inspect, skin_scoring
params = inspect.signature(skin_scoring.SkinAnalyzerV3.analyze_all).parameters
print("ref_stat 지원:", "ref_stat" in params)
```

### 12.8 복원 점수 팝업에 이상1·이상2 열이 표시되는 경우

v1.0 이전 `analyzer_compare_gui.py`를 사용 중입니다. v1.1에서는 원본/복원/차이 4열로 단순화됩니다.

### 12.9 GUI 로그창에서 출력 순서가 뒤섞이는 경우

v1.1 이전 `skin_analysis_gui.py`에서는 메인 파이프라인 프로세스의 stdout과 stderr를 별도 슬롯으로 처리해 버퍼 타이밍 차이로 로그 순서가 뒤섞였습니다. v1.2에서 `MergedChannels`로 통합되어 해결됩니다.

### 12.10 GUI 종료 후 비교 다이얼로그 프로세스가 잔존하는 경우

v1.1 이전 `skin_analysis_gui.py`에서는 창 닫기 시 `--compare` 서브프로세스를 kill하지 않아 고아 프로세스가 남는 문제가 있었습니다. v1.2에서 `closeEvent`에서 `_compare_process.kill()`을 호출하도록 수정되어 해결됩니다.

### 12.11 GUI에서 자동 튜닝을 끄고 싶은 경우

v1.1 이전에는 CLI만 가능했습니다. v1.2에서 입출력·모드 탭의 **「복원 후 17항목 점수 자동 튜닝」** 체크박스를 해제하면 됩니다.

---

## 13. 도움말

```bash
python skin_analysis_pipeline.py --cli --help
```

```bash
python skin_analysis_pipeline.py --analyze images/origin.png   # 단일 이미지 분석 (레이어B 측정항목)
python skin_analysis_pipeline.py --compare orig.png ref.png  # 측정항목 비교 다이얼로그
```

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
| 0.5.0 | 2026-05-13 | 이미지 인핸서 가이드 초기 작성 | Cascade |
