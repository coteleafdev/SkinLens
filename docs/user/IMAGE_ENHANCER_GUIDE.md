# 이미지 인핸서 가이드 (Image Enhancer Guide)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

---

## 1. 개요

`image_enhancer.py`는 AI Skin Image Enhancer의 v3 진입점 파일입니다. `pipeline_core.py`에 구현된 파이프라인 엔진을 통해 Stable Diffusion(SD) img2img와 RestoreFormer++/CodeFormer 복원 모델을 결합하여 피부 이미지를 보정하고, 모공·주름·트러블 후처리를 적용합니다.

### v3.0 주요 변경사항

- **skin_scoring 통합**: 피부 분석 시스템이 v3.0으로 업그레이드되어 이중구조 출력 지원
  - **레이어A (10개 직교 항목)**: 엔진 정확도용 신호 분해 출력
  - **레이어B (17개 보고서 항목)**: 고객 보고서용 역매핑 출력
- **GUI/CLI 통합**: 단일 파일에서 GUI(PySide6)와 CLI 모두 지원
- **복원 백엔드 선택**: RestoreFormer++와 CodeFormer 중 선택 가능
- **점수 팝업**: 파이프라인 완료 후 원본 vs 결과 점수 비교 팝업 지원

### v3.1 버그수정 / 개선사항

- **`skin_stat` 반환**: `SkinAnalyzerV3.analyze_all()`이 `skin_stat`과 `ref_stat` 파라미터를 지원해 이상 이미지 기준 상대 측정이 활성화됨
- **`dullness_score` 정밀 복원**: `raw_measurements` 보존 경로 구현으로 `tone_score×0.88` 근사 대신 원신호 직접 사용
- **복원 팝업 4열 단순화**: `RestoreScoreResultDialog`를 원본/복원/차이 4열로 단순화 (이상1·이상2 중복 제거)
- **종합 점수 레이어 통일**: 비교 다이얼로그 및 팝업의 종합 점수가 레이어B(`overall_score_report`) 기준으로 통일됨
- **분석 실패 안전 처리**: `_input_has_stressed_pigmentation()` 실패 시 강한 튜닝 적용 방지
- **로깅 lazy 초기화**: `import` 시 즉시 실행되던 로거 설정이 첫 `SkinAnalyzerV3()` 생성 시로 이동
- **CodeFormer `--bg_upsampler` 자동 결정**: RealESRGAN 가중치 파일 존재 여부를 자동 탐색해 크래시 방지
- **CodeFormer 한글 경로 대응**: 입력 이미지를 ASCII 파일명으로 스테이징하여 `cv2.imread` 실패 방지
- **모공 완화 경로 탐색 강화**: `res.restored` 실제 경로를 파일명 패턴보다 먼저 확인
- **SD 모델 캐시 lock 개선**: 수 분 소요되는 `from_pretrained`를 lock 범위 밖에서 실행해 GUI freeze 방지
- **VRAM 해제 강화**: `clear_diffusion_pipeline_cache()` 호출 시 `torch.cuda.empty_cache()` 추가

### v3.2 GUI 버그수정 / 개선사항

- **비교 프로세스 고아 방지**: 메인 창 종료 시 `--compare` 서브프로세스도 `kill()` 처리
- **파이프라인 로그 순서 보장**: 메인 프로세스에 `MergedChannels` 적용 — RF++/CF stderr 출력이 로그창 순서대로 표시
- **`--sd-only + --sd-after-rf` GUI 차단**: `_validate`에서 명시적 오류 메시지로 차단 (CLI는 경고 후 진행, GUI는 실행 전 차단)
- **미리보기 탐색 순서 수정**: `sd_after_rf` 모드에서 `01_sd_generated`(SD 최종)를 `00_restored`(RF 중간)보다 우선 표시
- **`--no-analyzer-score-tune` 체크박스 추가**: 복원 후 17항목 점수 자동 튜닝을 GUI에서도 끄고 켤 수 있음
- **로그 멀티라인 분리**: 버퍼 단위 수신 시 개행 포함 데이터가 단일 단락으로 뭉치던 문제 해결
- **비교 프로세스 슬롯 분리**: `finished` 튜플 람다 → `_on_compare_finished` 전용 메서드로 분리

### v3.3 `skin_pore_soften.py` 버그수정 / 개선사항

- **`params_from_pipeline` TypeError 크래시 수정**: 기존에는 파라미터를 수동 열거해서 `hf_gamma`, `bilateral_d`, `bilateral_sigma_*`, 피부 마스크 임계값 등 `pipeline_core.PoreSoftenParams`에 없는 필드가 전달되면 `TypeError`가 발생했습니다. `dataclasses.fields()` 기반 자동 동기화로 교체하여 알 수 없는 키를 무시하고, 필드 추가 시 수동 동기화도 불필요해졌습니다.
- **`trouble_sample_radius=0` 무성 무력화 차단**: `_validate_params`에 `trouble_sample_radius < 1` 및 `trouble_max_radius < 1` 검증 추가. 0이면 환형 샘플 두께가 0이 되어 트러블 완화 전체가 조용히 비활성화되던 문제를 경고 + 최솟값 1 클램프로 차단합니다.
- **처리 순서 개선 — 모공 先, 톤 後**: `soften_skin_full` 내부 단계 순서를 `[4]톤 균일화 → [5]모공 억제`에서 `[5]모공 억제 → [4]톤 균일화`로 변경. 고주파 L 감쇠 후 저주파 조정이 적용되어 두 효과가 서로를 상쇄하지 않습니다.

### v3.4 듀얼 이미지 Gemini AI 통합 (2026-05-13)

- **듀얼 이미지 Gemini AI 통합**: `gemini_skin_report.py`에 듀얼 이미지 모드 구현
  - 원본/복원 이미지를 한 번의 API 호출로 Gemini에 전송
  - 두 이미지에 대한 별도의 17개 항목별 소견 생성
  - Max Output Tokens: 단일 모드 8192 → 듀얼 모드 16384
- **GUI 듀얼 Gemini 점수 열 추가**: 피부분석 비교창에 원본/복원 Gemini 측정 점수 열 분리 표시
- **엑셀 보고서 듀얼 Gemini 점수 및 소견 처리**:
  - 원본 이미지 라벨 위치: 1C → 1B
  - 【원본 이미지 17개 항목별 소견】/【복원 이미지 17개 항목별 소견】 앞 공백행 추가
  - gemini_text 파싱 시 소견 섹션 구분 처리
- **전체 처리시간 로그 추가**: 실행부터 표시까지의 소요시간 로그 출력
- **파이프라인 끝 점수 팝업 비활성화**: GUI 체크박스 숨김 및 기능 비활성화
- **트러블 진행 로그 개선**: 고정 20분할 진행 카운트에서 경과 시간 기반(10초마다 1회)으로 변경. 성분 수에 무관하게 장시간 처리 시 균일하게 진행 상황을 표시합니다.

### v3.4 GUI/CLI 파라미터 제어 개선

- **복원 백엔드 기본값 CodeFormer로 변경**: RestoreFormer++에서 CodeFormer로 기본 복원 백엔드 변경
  - CLI: `--restorer codeformer` 기본
  - GUI: CodeFormer 라디오 버튼 기본 선택
- **CodeFormer fidelity 기본값 1.0으로 변경**: 원본 충실을 기본으로 사용하여 사용자 설정 존중
  - CLI: `--cf-fidelity 1.0` 기본 (기존 0.52)
  - GUI: fidelity 스피너 1.0 기본
- **CodeFormer upscale 기본값 1로 변경**: 업스케일 없음을 기본으로 사용
  - CLI: `--cf-upscale 1` 기본 (기존 2)
  - GUI: upscale 스피너 1 기본
- **모공·톤 후처리 체크박스 GUI 표시**: 기존 숨겨진 체크박스를 GUI에 표시하여 사용자가 명시적으로 pore_soften 활성화/비활성화 제어 가능
- **동작 모드 체크박스 횡 배치**: 동작 모드 그룹박스의 체크박스들을 2행으로 횡 배치하여 공간 효율 개선
- **pore_soften OFF 시 생성 방지**: 체크박스 OFF 또는 `--pore-soften` 미지정 시 pore_soft 출력 파일이 생성되지 않도록 수정
  - 튜닝 함수에서 `pore.enabled = True` 강제 설정 제거 (사용자 선택 존중)
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
diffusers>=0.25.0
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
- `image_enhancer.py` — 진입점 (본 파일)

**핵심 모듈:**
- `pipeline_core.py` — 파이프라인 코어 로직
  - `SdFirstSettings` — SD/복원 설정 dataclass
  - `PoreSoftenParams` — 모공·주름·트러블 후처리 설정 dataclass
  - `run_enhancement_pipeline()` — 메인 파이프라인 진입점
  - SD 모델 모듈 레벨 캐시 (`_sd_cache`)
  - 파이프라인 모드 Enum 분기 (`_PipelineMode`)

- `skin_scoring.py` — 피부 분석 시스템 v3.0
  - 레이어A: 10개 직교 항목 (엔진 출력)
  - 레이어B: 17개 보고서 항목 (표시 출력)
  - 이중구조 출력 지원

**GUI 모듈** (GUI 실행 시만 필요):
- `skin_analysis_gui.py` — 메인 GUI 윈도우
- `skin_measurement_chart_dialog.py` — 17항목 비교 다이얼로그
- `analyzer_compare_gui.py` — 점수 비교 GUI

**선택적 모듈:**
- `skin_pore_soften.py` — 모공·주름·트러블 후처리 라이브러리 (`--pore-soften` 시 필요)

### 2.3 외부 폴더 의존성

**선택적 폴더 (복원 백엔드):**
- `RestoreFormerPlusPlus/` — RestoreFormer++ 복원 모델 (`--restorer restoreformer`, 기본)
  - `RestoreFormerPlusPlus/inference.py` 필요
- `CodeFormer/` — CodeFormer 복원 모델 (`--restorer codeformer`)
  - `CodeFormer/inference_codeformer.py` 필요
  - `CodeFormer/weights/realesrgan/RealESRGAN_x2plus.pth` 또는 `RealESRGAN_x4plus.pth` — 있으면 배경 업스케일 자동 활성화, 없으면 `bg_upsampler=none`으로 자동 폴백

### 2.4 의존성 다이어그램

```
image_enhancer.py
    │
    ├─→ pipeline_core.py
    │       │
    │       ├─→ torch / diffusers (Stable Diffusion, 모듈 레벨 캐시)
    │       ├─→ Pillow (이미지 입출력·리사이즈)
    │       ├─→ RestoreFormerPlusPlus/ 또는 CodeFormer/ (in-process, 모델 캐싱)
    │       └─→ skin_pore_soften.py (모공 후처리, optional)
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
python image_enhancer.py
```

**기능:** 입력 이미지 선택, 파라미터 설정 (SD strength·복원 백엔드·CodeFormer 파라미터·모공 완화 등), 파이프라인 실행 및 로그 표시, 미리보기, 17항목 비교 다이얼로그

**GUI 레이아웃:**
- **입출력·모드 탭**: 입력 이미지, 산출 폴더, 동작 모드 체크박스들 (횡 배치, v3.4)
- **얼굴 복원 백엔드 그룹박스**: 복원 백엔드 선택(RF++/CodeFormer), CodeFormer 추가 복원 체크박스, CF 파라미터(fidelity, 업스케일)
  - "입출력·모드" 탭의 "동작 모드" 그룹박스 아래에 별도 배치
  - 횡 배치로 공간 효율적 사용
  - 레포 루트 입력 필드는 GUI에서 제거됨 (CLI 전용 `--restoreformer-root`, `--codeformer-root` 사용)
- **생성·복원 탭**: SD 관련 파라미터 (strength, guidance, steps 등)
- **모공·톤 후처리 탭**: 모공 완화 파라미터
- **주름 완화 탭**: 주름 완화 파라미터
- **트러블 완화 탭**: 트러블 완화 파라미터

**GUI 전용 체크박스 (v3.2 추가):**

| 체크박스 | 기본값 | 대응 CLI 인자 | 설명 |
|----------|--------|---------------|------|
| 복원 실행 | ✓ | `--no-restore` | 해제 시 복원 생략 |
| RF++ 후 CodeFormer 추가 복원 | ✓ | `--no-cf-additional` | 해제 시 RF++ 단독 실행 (CodeFormer 백엔드 선택 시 비활성화) |
| SD 생략 — 원본 복사 후 RF만 | — | `--restore-only` | |
| text2img만 | — | `--text2img` | 입력 이미지 무시 |
| RF++ 이후 SD img2img | — | `--sd-after-rf` | |
| SD만 — RF 생략 | — | `--sd-only` | |
| 모공·톤 후처리 | ✓ | `--pore-soften` | v3.4에서 GUI에 표시 (기존 숨김 해제) |
| 파이프라인 끝 점수 팝업 | ✓ | `--no-restore-score-popup` | 해제 시 팝업 끄기 |
| 복원 후 17항목 점수 자동 튜닝 | ✓ | `--no-analyzer-score-tune` | 해제 시 튜닝 끄기 |
| 주름 완화 적용 | — | `--wrinkle-mix` | 모공 후처리 탭 연동 |
| 트러블 완화 적용 | — | `--trouble-mix` | 모공 후처리 탭 연동 |

> **주의:** `SD만`과 `RF++ 이후 SD img2img`는 동시 선택 불가 — GUI에서 실행 전 오류 메시지로 차단됩니다.

**필요 패키지:** `requirements.txt` + `requirements-optional.txt` (PySide6 포함)

### 3.2 CLI 모드

```bash
python image_enhancer.py --cli [인자...]
```

**기본 CLI 명령:**
```bash
python image_enhancer.py --cli -i images/origin.png --out-dir ideal_pipeline_out
```

**주요 인자:**

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `-i, --input` | `images/origin.png` | 입력 이미지 경로 |
| `--out-dir` | `ideal_pipeline_out` | 산출 폴더 |
| `--restorer` | `codeformer` (v3.4) | 복원 백엔드 (`restoreformer` \| `codeformer`) |
| `--cf-additional` | `True` (config.json) | RF++ 복원 후 CodeFormer 추가 복원 (끄려면 `--no-cf-additional`) |
| `--cf-fidelity` | `1.0` (v3.4) | CodeFormer fidelity (0=최대보정, 1=원본충실) |
| `--cf-upscale` | `1` (v3.4) | CodeFormer 업스케일 배수 (1=없음, 2=2배, 4=4배) |
| `--sd-strength` | `0.12` | img2img strength (0~1) |
| `--pore-soften` | off | 모공 완화 후처리 활성화 |
| `--no-restore` | — | 복원 생략 |
| `--restore-only` | — | SD 생략, 복원만 실행 |
| `--sd-only` | — | 복원 생략, SD만 실행 |
| `--sd-after-rf` | — | 복원 후 SD img2img 추가 실행 |
| `--no-restore-score-popup` | — | 점수 팝업 끄기 |
| `--no-analyzer-score-tune` | — | 자동 튜닝 끄기 |

> **참고:** CodeFormer 관련 파라미터(`--cf-fidelity`, `--cf-upscale`, `--cf-additional`)의 기본값은 v3.4에서 직접 설정됩니다. `--cf-additional`만 `config/config.json`에서 로드됩니다.

**필요 패키지:** `requirements.txt` + `scikit-image>=0.21.0`

---

## 4. 파이프라인 모드 (`_PipelineMode`)

`pipeline_core.py` 내부의 `_PipelineMode` Enum으로 실행 경로를 분기합니다.

### 4.1 RF_THEN_SD (기본)

입력 이미지 있음 + 복원 레포 유효. 복원 → (옵션) SD 순서.

```bash
python image_enhancer.py --cli -i images/origin.png
```

**산출 파일:**

| 파일명 | 조건 | 설명 |
|--------|------|------|
| `00_input_{stem}.png` | 항상 | 입력 RGB 스테이징 (원본 해상도 유지) |
| `00_restored_{stem}.png` | 복원 성공 시 | 복원(RF++/CF) 결과 |
| `01_sd_generated_{stem}.png` | `--sd-after-rf` 시 | SD img2img 결과 |
| `02_pore_soft_{stem}.png` | `--pore-soften` 시 | 모공 완화 결과 |

### 4.2 RESTORE_ONLY (`--restore-only`)

SD 생략. 원본 스테이징 → 복원만 실행.

```bash
python image_enhancer.py --cli -i images/origin.png --restore-only
```

**산출:** `00_input_{stem}.png` → `01_restored_{stem}.png`

### 4.3 SD_ONLY (`--sd-only`)

복원 생략. 입력 이미지를 SD img2img만 처리.

```bash
python image_enhancer.py --cli -i images/origin.png --sd-only
```

**산출:** `00_input_{stem}.png` → `00_sd_generated_{stem}.png`

### 4.4 TEXT2IMG_OR_NORESTORE

입력 없음(text2img) 또는 `--no-restore`. SD 먼저 → (옵션) 복원.

```bash
python image_enhancer.py --cli --no-restore -i images/origin.png
```

---

## 5. 복원 파이프라인 상세

복원 파이프라인은 두 가지 백엔드(RestoreFormer++, CodeFormer)를 지원하며, 각 백엔드의 동작 방식과 파라미터를 이해하는 것이 중요합니다.

**[업데이트 2026-05-24]** In-process 실행으로 전환 완료. 성능 향상: 85-98%.

**이전:** subprocess 실행 (매 요청마다 20-60초 모델 로딩)
**이후:** In-process 실행 (모델 캐싱, 첫 요청 4.15초, 이후 1.33초)

- 모델이 메모리에 상주하여 반복 로딩 제거
- GPU 메모리 효율적 사용
- 자동 subprocess fallback 메커니즘
- 구성 파일 기반 실행 제어 (`config/in_process_config.json`)

**참고:** `model-serving-refactor/FINAL_SUMMARY.md`

### 5.1 RestoreFormer++ (RF++)

**개요**
- RestoreFormerPlusPlus는 얼굴 복원에 특화된 최신 AI 모델
- 딥러닝 기반의 얼굴 구조 복원 및 텍스처 개선
- 기본 복원 백엔드로 사용

**동작 방식**
1. **입력 이미지 분석**: 얼굴 영역 감지 및 특징 추출
2. **구조 복원**: 딥러닝 네트워크로 얼굴 구조(눈, 코, 입 등) 복원
3. **텍스처 개선**: 피부 텍스처 세부 디테일 복원
4. **출력**: 고해상도 복원 이미지 (기본 2x 업스케일)

**파라미터**
| 파라미터 | CLI 인자 | 기본값 | 설명 |
|----------|----------|--------|------|
| `restoreformer_repo` | `--restoreformer-root` | `./RestoreFormerPlusPlus` | 레포 루트 (CLI 전용) |
| `codeformer_fidelity` | `--cf-fidelity` | `1.0` (config.json) | 0=최대 보정, 1=원본 충실 |
| `codeformer_upscale` | `--cf-upscale` | `2` (config.json) | 업스케일 배수 |
| `codeformer_additional` | `--cf-additional` | `True` (config.json) | RF++ 후 CodeFormer 추가 복원 여부 |

**레포 구조**
```
RestoreFormerPlusPlus/
    inference.py                    ← 필수
    weights/
        restoreformer_plus_plus.pth  ← 모델 가중치
```

### 5.2 CodeFormer (CF)

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

**`codeformer_bg_upsampler` 자동 결정 (v3.1):**  
`SdFirstSettings.__post_init__` 시 아래 경로를 탐색합니다. 파일이 있으면 `"realesrgan"`, 없으면 `"none"`으로 자동 설정되어 가중치 미설치 환경의 크래시를 방지합니다.

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

6. **후처리 (옵션)**
   - 모공 완화 (`--pore-soften`)
   - 주름 완화 (`--wrinkle-mix`)
   - 트러블 완화 (`--trouble-mix`)

**설정 파일 로드**
- `config/config.json`에서 점수 파라미터 로드
- 파일 수정 시 자동 감지 및 재로드 (서버 환경 지원)

---

> **주의 (CLI):** `--sd-only`와 `--sd-after-rf`를 동시에 지정하면 `--sd-only`가 우선 적용되고 경고가 출력된 후 계속 실행됩니다.  
> **주의 (GUI):** 동일 조합은 실행 전에 오류 메시지로 차단됩니다.

### 3.3 오류 JSON 출력

오류 발생 시 JSON 형식으로 오류 정보가 출력되어 외부 모니터링이 가능합니다:

```json
{
  "error": true,
  "error_type": "FileNotFoundError",
  "error_message": "입력 이미지를 찾을 수 없습니다",
  "timestamp": "2026-04-29T12:34:56.789012",
  "input_image": "images/origin.png",
  "output_dir": "ideal_pipeline_out"
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
python image_enhancer.py --cli -i images/origin.png --output-json result.json
```
오류 발생 시 `result.json`에 오류 JSON이 저장됩니다.

**디버그 모드**:
```bash
python image_enhancer.py --cli -i images/origin.png --debug
```
`--debug` 모드에서는 오류 JSON에 `error_traceback` 필드가 포함됩니다.

---

## 5. 복원 백엔드 (`SdFirstSettings.restorer`)

### 5.1 RestoreFormer++

```bash
python image_enhancer.py --cli -i images/origin.png --restorer restoreformer
```

| 설정 | CLI 인자 | 기본값 |
|------|----------|--------|
| `restoreformer_repo` | `--restoreformer-root` | `./RestoreFormerPlusPlus` (자동 탐색) |

**레포 구조:**
```
RestoreFormerPlusPlus/
    inference.py    ← 필수
```

### 5.2 CodeFormer (기본, v3.4)

```bash
python image_enhancer.py --cli -i images/origin.png --restorer codeformer
```

| 필드 | CLI 인자 | 기본값 | 설명 |
|------|----------|--------|------|
| `codeformer_repo` | `--codeformer-root` | `./CodeFormer` (자동 탐색) | 레포 루트 |
| `codeformer_fidelity` | `--cf-fidelity` | `1.0` (v3.4) | 0=최대 보정, 1=원본 충실 |
| `codeformer_upscale` | `--cf-upscale` | `1` (v3.4) | 업스케일 배수 (1=없음, 2=2배, 4=4배) |
| `codeformer_bg_upsampler` | — | `"auto"` → 자동 결정 | RealESRGAN 배경 업스케일 여부 |

**`codeformer_bg_upsampler` 자동 결정 (v3.1):**  
`SdFirstSettings.__post_init__` 시 아래 경로를 탐색합니다. 파일이 있으면 `"realesrgan"`, 없으면 `"none"`으로 자동 설정되어 가중치 미설치 환경의 크래시를 방지합니다.

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

## 6. SD 설정 (`SdFirstSettings`)

`pipeline_core.SdFirstSettings` dataclass의 전체 필드입니다.

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `sd_model_id` | `"CompVis/stable-diffusion-v1-4"` | HuggingFace 모델 ID |
| `sd_prompt` | `DEFAULT_PROMPT_SKIN` | img2img / text2img 프롬프트 |
| `sd_negative_prompt` | `DEFAULT_NEGATIVE_PROMPT_SKIN` | 네거티브 프롬프트 |
| `sd_device` | `"cuda"` | 추론 디바이스 (`"cuda"` \| `"cpu"`) |
| `sd_dtype` | `"float16"` | 모델 dtype (`"float16"` \| `"float32"`) |
| `sd_guidance_img2img` | `5.5` | CFG guidance scale |
| `sd_num_inference_steps_img2img` | `40` | 추론 스텝 수 |
| `sd_max_side` | `768` | img2img 입력 긴 변 상한 (px) |
| `restorer` | `Restorer.CODEFORMER` (v3.4) | 복원 백엔드 Enum |
| `restoreformer_repo` | `None` → 자동 탐색 | RestoreFormerPlusPlus 레포 경로 |
| `codeformer_repo` | `None` → 자동 탐색 | CodeFormer 레포 경로 |
| `codeformer_fidelity` | `1.0` (v3.4) | CodeFormer fidelity_weight |
| `codeformer_upscale` | `1` (v3.4) | CodeFormer 업스케일 배수 |
| `codeformer_bg_upsampler` | `"auto"` → 자동 결정 | RealESRGAN 배경 업스케일 여부 |

**CUDA 자동 폴백:** `sd_device="cuda"`여도 `torch.cuda.is_available()==False`이면 CPU·float32로 자동 폴백합니다. `cfg` 객체는 변경되지 않으므로 GPU 인식 후 재실행 시 다시 CUDA를 사용합니다.

**SD 모델 캐시 (`_sd_cache`):** 키 형식은 `"{model_id}|{mode}|{device}|{dtype}"`. 매 파이프라인 호출마다 재로드하지 않습니다. VRAM 해제 시 `clear_diffusion_pipeline_cache()`를 호출하면 `gc.collect()` + `torch.cuda.empty_cache()`까지 수행합니다.

---

## 7. 모공 완화 후처리 (`PoreSoftenParams`)

`pipeline_core.PoreSoftenParams` dataclass의 전체 필드입니다. 실제 처리는 `skin_pore_soften.py`의 `soften_skin_full()`에서 수행됩니다.

**내부 처리 파이프라인 순서 (v3.3 기준):**

| 단계 | 처리 내용 | 비고 |
|------|-----------|------|
| [1] 피부 마스크 | YCrCb + HSV 교차 검증, 모폴로지, 페더링 | 항상 실행 |
| [2] 주름 마스크 | L 분산 + Sobel 교차 검출 | `wrinkle_mix > 0` 시 |
| [3] 트러블 마스크 | a채널 홍조 + 명암 대비 교차 검출 | `trouble_mix > 0` 시 |
| **[5] 모공 억제** | L 고주파 감마 억제 | 항상 실행, **v3.3에서 [4] 앞으로 이동** |
| **[4] 톤 균일화** | L·ab 저주파 블렌딩 | `tone_*_mix > 0` 시, **v3.3에서 [5] 뒤로 이동** |
| [6] 주름 완화 | 멀티스케일 가우시안 블렌딩 | `wrinkle_mix > 0` 시 |
| [7] 트러블 완화 | 연결 성분별 환형 샘플 inpainting | `trouble_mix > 0` 시 |
| [8] Bilateral | L 채널 직접 처리 | `bilateral_mix > 0` 시 |
| [9] 최종 합성 | 처리 결과 × 피부마스크 + 원본 × (1-마스크) | 항상 실행 |

> **v3.3 처리 순서 변경:** 단계 번호(4/5)는 로그에 원래 번호로 표시되지만, 실행 순서는 `[5]모공 先 → [4]톤 後`로 변경되었습니다. 모공(고주파 L 감쇠) 완료 후 톤(저주파 조정)을 적용해야 두 효과가 서로를 상쇄하지 않습니다.

### 7.1 기본 사용

```bash
python image_enhancer.py --cli -i images/origin.png --pore-soften
```

**v3.4 동작 변경:**
- `--pore-soften` 미지정 시 pore_soft 출력 파일이 생성되지 않음
- 이전 실행의 pore_soft 파일이 있어도 참조하지 않음 (현재 실행 결과만 사용)
- 체크박스 OFF 시 pore_soft 파일 확인하지 않음 (GUI 미리보기)
- CLI와 GUI 동일하게 동작

### 7.2 파라미터 전체

**모공·질감:**

| 필드 | CLI 인자 | 기본값 | 설명 |
|------|----------|--------|------|
| `enabled` | `--pore-soften` | `False` | 모공 완화 활성화 |
| `strength` | `--pore-strength` | `0.32` | 모공 완화 강도 (0~1) |
| `sigma_low` | `--pore-sigma-low` | `4.0` | 저주파 분리 sigma |
| `mask_feather` | `--pore-mask-feather` | `6.0` | 마스크 feather 반경 (px) |
| `hf_gamma` | `--hf-gamma` | `1.5` | 고주파 감마 커브 지수 (0.1~) |
| `bilateral_mix` | `--pore-bilateral-mix` | `0.0` | bilateral 필터 혼합 비율 |
| `bilateral_d` | — | `9` | bilateral 필터 직경 (px, 홀수) |
| `bilateral_sigma_color` | — | `42.0` | bilateral 색 sigma |
| `bilateral_sigma_space` | — | `42.0` | bilateral 공간 sigma |
| `tone_l_mix` | — | `0.0` | L채널 톤 보정 혼합 비율 |
| `tone_l_sigma` | — | `28.0` | L채널 톤 보정 sigma |
| `tone_ab_mix` | — | `0.0` | ab채널 색조 보정 혼합 비율 |
| `tone_ab_sigma` | — | `12.0` | ab채널 색조 보정 sigma |

> **참고:** 위 파라미터들은 튜닝 함수(`--analyzer-score-tune`)에 의해 자동 조정될 수 있습니다. 사용자가 명시적으로 설정한 값은 존중됩니다 (v3.4).

**주름:**

| 필드 | CLI 인자 | 기본값 | 설명 |
|------|----------|--------|------|
| `wrinkle_mix` | `--wrinkle-mix` | `0.0` | 주름 완화 강도 (0~1) |
| `wrinkle_sigma_fine` | — | `2.0` | 잔주름 탐지 sigma |
| `wrinkle_sigma_coarse` | — | `5.0` | 굵은 주름 탐지 sigma |
| `wrinkle_fine_weight` | — | `0.4` | 잔주름 가중치 (0~1) |
| `wrinkle_edge_restore` | — | `0.0` | 주름 엣지 복원 비율 |
| `wrinkle_det_sigma` | — | `5.0` | 주름 검출 sigma |
| `wrinkle_det_thresh` | — | `12.0` | 주름 검출 임계값 |

**트러블 (잡티·여드름):**

| 필드 | CLI 인자 | 기본값 | 설명 |
|------|----------|--------|------|
| `trouble_mix` | `--trouble-mix` | `0.0` | 트러블 완화 강도 (0~1) |
| `trouble_a_thresh` | — | `140` | a채널 트러블 임계값 |
| `trouble_contrast_thresh` | — | `12.0` | 대비 트러블 임계값 |
| `trouble_sample_radius` | `--trouble-sample-radius` | `10` | 베이스 색 환형 샘플 반경 (px, **최솟값 1**) |
| `trouble_max_radius` | `--trouble-max-radius` | `16` | 최대 트러블 반경 제한 (px, **최솟값 1**) |
| `trouble_feather` | `--trouble-feather` | `3.0` | 트러블 마스크 feather |

> **주의 (v3.3):** `trouble_sample_radius=0`으로 설정하면 환형 샘플 두께가 0이 되어 트러블 완화가 전체 무력화됩니다. `_validate_params`에서 자동으로 1로 클램프되고 경고가 출력됩니다.

**피부 마스크 임계값 (고급):**

`skin_pore_soften.py` 직접 호출 시 또는 CLI(`skin_pore_soften.py --input ... --cr-min ...`)에서 조정 가능합니다. `pipeline_core`를 통한 호출 시에는 기본값이 사용됩니다.

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `cr_min` / `cr_max` | 133 / 180 | YCrCb Cr 채널 피부 범위 |
| `cb_min` / `cb_max` | 77 / 127 | YCrCb Cb 채널 피부 범위 |
| `hsv_s_min` | 15 | HSV 채도 최솟값 |
| `hsv_v_min` | 50 | HSV 명도 최솟값 |
| `hsv_h_max` | 25 | HSV 색상 최댓값 (0~25, 170~180도 포함) |
| `exclude_dark_v_thresh` | 50 | V < 이 값인 어두운 영역 마스크 제외 |
| `exclude_white_s_thresh` | 20 | 흰 영역(S<20, V>200) 마스크 제외 |
| `morph_open_ksize` | 5 | 마스크 모폴로지 오픈 커널 크기 |
| `morph_close_ksize` | 15 | 마스크 모폴로지 클로즈 커널 크기 |

> **참고 (v3.3):** `pipeline_core`의 `_run_pore_soften_stage`는 `asdict(params)`로 `params_from_pipeline`을 호출합니다. v3.3에서 `params_from_pipeline`이 `dataclasses.fields()` 기반으로 교체되어 위 피부 마스크 임계값 필드들도 `skin_pore_soften.PoreSoftenParams`에 존재하므로 자동으로 전달됩니다.

**디버그:**

| 필드 | 설명 |
|------|------|
| `save_mask` | 모공 마스크 저장 경로 |
| `save_wrinkle_mask` | 주름 마스크 저장 경로 |
| `save_trouble_mask` | 트러블 마스크 저장 경로 |

### 7.3 CLI 사용 예시

```bash
python image_enhancer.py --cli -i images/origin.png \
    --pore-soften \
    --pore-strength 0.32 \
    --pore-sigma-low 4.0 \
    --pore-mask-feather 6.0 \
    --pore-bilateral-mix 0.0 \
    --wrinkle-mix 0.4 \
    --trouble-mix 0.5
```

---

## 8. skin_scoring 이중구조 출력

### 8.1 레이어A (10개 직교 항목)

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

**이상 이미지 기준 상대 측정 (`ref_stat`, v3.1):**
```python
ideal_result = analyzer.analyze_all("ideal.jpg")
orig_result  = analyzer.analyze_all(
    "origin.jpg",
    ref_stat=ideal_result["skin_stat"],
)
```

### 8.2 레이어B (17개 보고서 항목)

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

> `*dullness_score`: v3.0 직교 분해에서 제거된 항목. v3.1에서 `raw_measurements` 보존 경로를 통해 원신호 직접 복원. 보고서 출력 시 `*직접` 또는 `*v3근사` 표기로 구분됩니다.

**접근:**
```python
result = analyzer.analyze_all("face.jpg")
measurements_b  = result["measurements_v17"]      # 레이어B — 17개 보고서
overall_score_b = result["overall_score_report"]  # 레이어B 종합
```

### 8.3 사용 예시

```python
from skin_scoring import SkinAnalyzerV3

analyzer = SkinAnalyzerV3()
result   = analyzer.analyze_all("face.jpg")

# 레이어A (10개 직교)
print(f"엔진 종합 점수: {result['overall_score']}")
print(f"엔진 측정: {result['measurements']}")

# 레이어B (17개 보고서)
print(f"보고서 종합 점수: {result['overall_score_report']}")
print(f"보고서 측정: {result['measurements_v17']}")

# dullness_score 복원 방식 확인
print("dullness 복원:", "직접" if "dullness_score" in result.get("raw_measurements", {}) else "tone근사")

# 보고서 출력 문자열 (*직접/*v3근사 표기 포함)
analyzer.print_results_report(result)

# 이상 이미지 기준 상대 측정
ideal = analyzer.analyze_all("ideal.jpg")
orig  = analyzer.analyze_all("origin.jpg", ref_stat=ideal["skin_stat"])
```

---

## 9. 점수 튜닝 (`--analyzer-score-tune`)

복원 사용 시 skin_scoring 레이어B 17항목이 입력보다 오르기 쉽도록 파라미터를 자동 튜닝합니다.

**기본 켜짐 / 끄기:**

CLI:
```bash
python image_enhancer.py --cli -i images/origin.png                           # 켜짐
python image_enhancer.py --cli -i images/origin.png --no-analyzer-score-tune  # 끄기
```

GUI: 입출력·모드 탭 → **「복원 후 17항목 점수 자동 튜닝」** 체크박스로 제어 (v3.2 추가)

**튜닝 내용:**
- 모공·톤·주름·트러블 후처리 강도 조정
- 색소 부담이 큰 입력은 홍조·모공늘어짐 보호용 완화 튜닝
- **분석 실패 안전 처리 (v3.1):** `skin_scoring` import 오류·예외 발생 시 `None` 반환 → 강한 튜닝 적용 방지, 경고 출력 후 건너뜀
- **사용자 선택 존중 (v3.4):**
  - 튜닝 함수에서 `pore.enabled = True` 강제 설정 제거 (사용자가 명시적으로 끈 경우 유지)
  - 튜닝 함수에서 `codeformer_fidelity` 강제 낮춤 제거 (사용자가 명시적으로 설정한 값 존중)

---

## 10. 점수 팝업 (`--restore-score-popup`)

파이프라인 완료 후 원본 vs 결과 점수 비교 팝업을 표시합니다.

**기본 켜짐 / 끄기:**

CLI:
```bash
python image_enhancer.py --cli -i images/origin.png                            # 켜짐
python image_enhancer.py --cli -i images/origin.png --no-restore-score-popup   # 끄기
```

GUI: 입출력·모드 탭 → **「파이프라인 끝 점수 팝업」** 체크박스로 제어

**v3.1 변경:** 팝업 테이블이 6열(이상1/이상2 중복)에서 4열(항목/원본/복원/차이)로 단순화됩니다. 종합 점수도 레이어B(`overall_score_report`) 기준으로 통일됩니다.

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

`image_enhancer.py`와 같은 디렉토리에서 실행해야 합니다:

```cmd
cd "c:\Project\AI Skin v3"
python image_enhancer.py
```

### 12.3 CUDA 사용 불가 메시지

```
[안내] torch.cuda 사용 불가 — Stable Diffusion 을 cpu·float32 로 실행합니다
```

CPU 전용으로 자동 폴백되어 실행됩니다. `SdFirstSettings` 객체는 변경되지 않으므로 GPU 인식 후 재실행 시 자동으로 CUDA를 사용합니다.

### 12.4 RestoreFormer++ 오류

`RestoreFormerPlusPlus/inference.py`가 있는지 확인하세요:

```bash
git clone https://github.com/wzhouxiff/RestoreFormerPlusPlus.git
```

### 12.5 CodeFormer 크래시 (`realesrgan` 관련)

v3.1에서는 RealESRGAN 가중치 파일 존재 여부를 자동 탐색하여 크래시를 방지합니다. 구버전 사용 중이라면 v3.1로 업데이트하거나, 코드에서 직접 `"none"`으로 강제 설정할 수 있습니다:

```python
from pipeline_core import SdFirstSettings, Restorer
cfg = SdFirstSettings(
    restorer=Restorer.CODEFORMER,
    codeformer_bg_upsampler="none",
)
```

가중치를 설치하려면:
```
CodeFormer/weights/realesrgan/RealESRGAN_x2plus.pth
```

### 12.6 CodeFormer 한글 경로 오류

v3.1에서 입력 이미지를 ASCII 파일명(`cf_input.png`)으로 임시 스테이징하여 처리하므로 한글 경로도 정상 동작합니다. 이전 버전에서 오류가 발생했다면 v3.1로 업데이트하세요.

### 12.7 `skin_scoring` import 실패

```bash
pip install scikit-image>=0.21.0
```

### 12.8 `ref_stat` 비교가 작동하지 않는 경우

v3.1 미만 `skin_scoring`를 사용 중입니다. 지원 여부를 확인하세요:

```python
import inspect, skin_scoring
params = inspect.signature(skin_scoring.SkinAnalyzerV3.analyze_all).parameters
print("ref_stat 지원:", "ref_stat" in params)
```

### 12.9 복원 점수 팝업에 이상1·이상2 열이 표시되는 경우

v3.0 이전 `analyzer_compare_gui.py`를 사용 중입니다. v3.1에서는 원본/복원/차이 4열로 단순화됩니다.

### 12.10 GUI 로그창에서 출력 순서가 뒤섞이는 경우

v3.1 이전 `skin_analysis_gui.py`에서는 메인 파이프라인 프로세스의 stdout과 stderr를 별도 슬롯으로 처리해 버퍼 타이밍 차이로 로그 순서가 뒤섞였습니다. v3.2에서 `MergedChannels`로 통합되어 해결됩니다.

### 12.11 GUI 종료 후 비교 다이얼로그 프로세스가 잔존하는 경우

v3.1 이전 `skin_analysis_gui.py`에서는 창 닫기 시 `--compare` 서브프로세스를 kill하지 않아 고아 프로세스가 남는 문제가 있었습니다. v3.2에서 `closeEvent`에서 `_compare_process.kill()`을 호출하도록 수정되어 해결됩니다.

### 12.12 GUI에서 자동 튜닝을 끄고 싶은 경우

v3.1 이전에는 CLI만 가능했습니다. v3.2에서 입출력·모드 탭의 **「복원 후 17항목 점수 자동 튜닝」** 체크박스를 해제하면 됩니다.

### 12.13 모공 완화 실행 시 `TypeError: unexpected keyword argument` 오류

v3.2 이전 `skin_pore_soften.py`의 `params_from_pipeline`은 파라미터를 수동 열거해서 `hf_gamma`, `bilateral_d`, `bilateral_sigma_*`, 피부 마스크 임계값(`cr_min` 등) 등이 전달되면 TypeError가 발생했습니다. v3.3에서 `dataclasses.fields()` 기반으로 교체되어 해결됩니다.

### 12.14 트러블 완화가 적용되지 않는 경우

`trouble_mix > 0`인데도 아무 효과가 없다면 `trouble_sample_radius=0`으로 설정된 경우일 수 있습니다. v3.3에서는 자동으로 1로 클램프되고 경고가 출력됩니다. 로그에서 `trouble_sample_radius` 관련 경고 메시지를 확인하세요.

### 12.15 톤 균일화와 모공 억제를 동시에 사용할 때 효과가 약한 경우

v3.2 이전에는 `[4]톤 균일화 → [5]모공 억제` 순서로 처리되어 톤 조정이 모공 억제에 의해 부분 상쇄됐습니다. v3.3에서 순서가 `[5]모공 억제 → [4]톤 균일화`로 변경되어 두 효과가 독립적으로 적용됩니다.

---

## 13. 도움말

```bash
python image_enhancer.py --cli --help
```

```bash
python image_enhancer.py --analyze images/origin.png   # 단일 이미지 분석 (레이어B 측정항목)
python image_enhancer.py --compare orig.png ideal.png  # 측정항목 비교 다이얼로그
```

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (v3.5에서 마이그레이션) | Cascade |
| 0.5.0 | 2026-05-13 | 이미지 인핸서 가이드 초기 작성 | Cascade |
