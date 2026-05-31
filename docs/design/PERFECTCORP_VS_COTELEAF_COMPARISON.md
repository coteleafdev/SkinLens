# Perfect Corp vs COTELEAF 측정항목 비교 (Perfect Corp vs COTELEAF Comparison)

> **문서 버전:** 1.1.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-06-01  
> **상태:** 활성

---

## 비교 기호

| 기호 | 의미 |
|---|---|
| ✅ 대응 | 항목 개념이 일치하거나 동등한 측정을 수행 |
| ⚠ 부분 대응 | 유사 개념이나 측정 범위·방식에 차이 있음 |
| ➕ COTELEAF 전용 | Perfect Corp에 없는 COTELEAF 고유 항목 |
| ➖ Perfect Corp 전용 | COTELEAF에 없는 Perfect Corp 항목 |

---

## 1. 항목별 대응 비교표

| # | Perfect Corp 항목 | COTELEAF 항목 | 대응 | 비고 |
|---|---|---|---|---|
| 1 | Spots | `melasma_score` (기미·잡티) | ✅ | PC는 색소반 통합. COTELEAF는 melasma 면적 기반 |
| 2 | Spots | `freckle_score` (주근깨) | ✅ | PC의 Spots에 주근깨 포함. COTELEAF는 별도 blob 개수 항목으로 분리 |
| 3 | Redness | `redness_score` (홍조) | ✅ | 동일 개념. PC: 딥러닝 분류 / COTELEAF: a\* 채널 z-score + 면적 |
| 4 | Redness | `post_inflammatory_erythema_score` (염증후 홍반) | ⚠ | COTELEAF는 홍조를 미만성·염증성으로 세분화. PC는 단일 Redness |
| 5 | Acne | `acne_score` (여드름) | ✅ | 동일 개념. PC: 딥러닝 / COTELEAF: HSV-V 돌출 + a\* 복합 |
| 6 | — | `post_acne_pigment_score` (여드름 후 색소) | ➕ | PC 미포함. COTELEAF 고유: 여드름 흔적·PIH 홍반 측정 |
| 7 | Pores | `pore_size_score` (모공 크기) | ✅ | 동일 개념. PC: 딥러닝 / COTELEAF: LoG blob sigma |
| 8 | — | `pore_sagging_score` (모공 처짐) | ➕ | PC 미포함. COTELEAF 고유: 타원비 elongation 측정 |
| 9 | Wrinkles | `eye_wrinkle_score` (눈가 주름) | ✅ | PC: Wrinkles 통합 (Periocular 포함). COTELEAF: ROI 세분화 |
| 10 | Wrinkles | `nasolabial_wrinkle_score` (팔자 주름) | ✅ | PC: Wrinkles 통합 (Nasolabial 포함). COTELEAF: ROI 세분화 |
| 11 | Wrinkles | `fine_deep_wrinkle_score` (잔·깊은 주름) | ✅ | PC: Wrinkles 통합. COTELEAF: 전역 local_std 분포 비율 |
| 12 | Texture | `roughness_score` (피부결 거칠기) | ✅ | 동일 개념. PC: 딥러닝 / COTELEAF: LBP(r=1,2,3) 분산 |
| 13 | — | `skin_tone_score` (피부 톤) | ➕ | PC 미포함 (Fitzpatrick 별도 제품). COTELEAF: ITA 각도 |
| 14 | Radiance | `dullness_score` (칙칙함) | ⚠ | 역방향 측정 (Radiance↑ = dullness↓). 개념 동일. PC: 딥러닝 / COTELEAF: L\*·S·highlight 가중합 |
| 15 | — | `uneven_tone_score` (톤 불균일) | ➕ | PC 미포함. COTELEAF 고유: strip-norm L\* 분산 + 비대칭 |
| 16 | Firmness | `jawline_blur_score` (턱선 탄력) | ⚠ | PC: 전체 얼굴 탄력. COTELEAF: 턱선 ROI Canny edge 한정 |
| 17 | Firmness | `cheek_sagging_score` (볼 처짐) | ➕ | PC 미포함. COTELEAF v1.0 추가: 볼 영역 처짐 측정 |
| 18 | Moisture | `skin_type_score` (수분) | ✅ | 동일 개념. PC: 딥러닝 / COTELEAF: HSV 각질 + dry_pixel_ratio |
| 19 | Oiliness | `oily_score` (피지) | ✅ | PC: 딥러닝 / COTELEAF: HSV S채널 기반 (v1.0 추가) |
| 20 | Dark Circles | — | ➖ | COTELEAF 미포함. 눈 밑 다크서클 측정 항목 부재 |
| 21 | Eyebags | — | ➖ | COTELEAF 미포함. 눈 밑 지방 팽창 측정 항목 부재 |
| 22 | Tear Trough | — | ➖ | COTELEAF 미포함. 눈물고랑(꺼짐) 측정 항목 부재 |
| 23 | Droopy Upper Eyelid | — | ➖ | COTELEAF 미포함. 눈꺼풀 처짐 측정 항목 부재 |
| 24 | Droopy Lower Eyelid | — | ➖ | COTELEAF 미포함. 아래 눈꺼풀 처짐 측정 항목 부재 |

---

## 2. 카테고리별 커버리지 요약

| 카테고리 | Perfect Corp | COTELEAF v1.0 | 차이 |
|---|---|---|---|
| **색소** | Spots (통합 1개) | melasma + freckle (2개) | COTELEAF가 기미·주근깨 세분화 |
| **홍조** | Redness (1개) | redness + post_inflammatory_erythema_score (2개) | COTELEAF가 미만성·염증성 세분화 |
| **트러블·흔적** | Acne (1개) | acne + post_acne_pigment (2개) | COTELEAF에 자국(흔적) 항목 추가 |
| **모공** | Pores (1개) | pore_size + pore_sagging (2개) | COTELEAF가 크기·처짐 세분화 |
| **주름** | Wrinkles (1개, 세부 분류 제공) | eye + nasolabial + fine_deep (3개) | COTELEAF가 ROI별 독립 측정 |
| **텍스처** | Texture (1개) | roughness (1개) | 동일 |
| **톤·밝기** | Radiance (1개) | skin_tone + dullness + uneven_tone (3개) | COTELEAF가 색조·광채·균일도 세분화 |
| **탄력** | Firmness (1개) | jawline_blur + cheek_sagging (2개) | PC: 전체 얼굴 / COTELEAF: 턱선·볼 세분화 |
| **수분** | Moisture (1개) | skin_type_score (1개) | 동일 |
| **피지** | Oiliness (1개) | **없음** | ❌ COTELEAF 미커버 (oily_score는 내부 처리용) |
| **눈 주변** | Dark Circles + Eyebags + Tear Trough + Droopy ×2 (5개) | **없음** | ❌ COTELEAF 미커버 |
| **피부 톤** | (Fitzpatrick 별도 제품) | skin_tone + uneven_tone (2개) | COTELEAF가 ITA·분산 측정 |

---

## 3. COTELEAF 전용 항목 (Perfect Corp 대비 차별화)

| 항목 | 설명 | 차별화 포인트 |
|---|---|---|
| `post_acne_pigment_score` | 여드름 후 색소 (PIH·여드름 흔적) | 여드름 치료 전후 추적에 필수. PC 미포함 |
| `pore_sagging_score` | 모공 처짐 (타원비) | 노화·탄력 저하로 인한 모공 변형 측정. PC 미포함 |
| `skin_tone_score` | ITA 각도 기반 피부 톤 | 색조 화장품 추천에 연계 가능. PC는 별도 제품 |
| `uneven_tone_score` | 톤 불균일 (L\* 분산·비대칭) | 피부 균일도 정밀 측정. PC 미포함 |
| `post_inflammatory_erythema_score` | 염증후 홍반 세분화 | 미만성·집중형 홍조 구분. 치료 타깃팅 정밀화 |
| `cheek_sagging_score` | 볼 처짐 (v1.0 추가) | 턱선 외 볼 영역 처짐 측정. PC 미포함 |

---

## 4. Perfect Corp 전용 항목 (COTELEAF 미커버)

| 항목 | 설명 | COTELEAF 보완 가능성 |
|---|---|---|
| Dark Circles | 눈 밑 다크서클 | 눈 주변 ROI + L\* 명도 기반으로 추가 가능 |
| Eyebags | 눈 밑 지방 팽창 | 눈 주변 3D 형태 분석 필요 (현재 2D CV 한계) |
| Tear Trough | 눈물고랑 꺼짐 | 3D depth 또는 shadow 분석 필요 |
| Oiliness | 피지·유분 | oily_score는 내부 처리용으로 보고서 미포함. 보고서용으로 추가 필요 |
| Droopy Upper Eyelid | 위 눈꺼풀 처짐 | 랜드마크 기반 눈꺼풀 비율 분석으로 추가 가능 |
| Droopy Lower Eyelid | 아래 눈꺼풀 처짐 | 동일 |

---

## 5. 측정 방식 비교

| 구분 | Perfect Corp | COTELEAF skin_scoring |
|---|---|---|
| **핵심 방식** | 딥러닝 분류 모델 (End-to-End) | CV 규칙 기반 (LAB·HSV·Sobel·LBP·LoG) |
| **학습 데이터** | 70,000+ 의료급 이미지 | 자체 캘리브레이션 기반 |
| **입력 모드** | 정면·좌·우 3장 (180° 매핑) | 단일 정면 이미지 |
| **처리 속도** | 약 2초 | 실시간 (단일 이미지) |
| **점수 체계** | 0~100 (항목별) | 10~90 (5등급 기준) |
| **설명 가능성** | 낮음 (블랙박스 DL) | 높음 (채널·임계 명시적 정의) |
| **커스터마이징** | Expert Mode API (픽셀 수준 데이터 제공) | breakpoint·가중치 직접 수정 가능 |
| **얼굴 매핑** | 180° 3뷰 (정확도 높음) | 정면 단일 (측면 미커버) |

---

## 6. 항목 수 비교 요약

| 구분 | Perfect Corp | COTELEAF v1.0 |
|---|---|---|
| 총 항목 수 | **15개** | **18개** |
| 완전 대응 | — | 9개 ✅ |
| 부분 대응 | — | 2개 ⚠ |
| COTELEAF 전용 | — | 5개 ➕ |
| Perfect Corp 전용 | 6개 ➖ | — |
| 미커버 카테고리 | — | 눈 주변(4개) + 피지(1개) |

> **참고:** COTELEAF v1.0 OUTPUT_KEYS에는 총 24개 항목이 있으나, 보고서용 카테고리(_LEGACY_MEASUREMENT_CATEGORIES)에는 18개 항목만 포함됩니다. 추가 항목(6개: pih_score, focal_lesion, noise_score, color_balance_score, detail_score, oily_score)은 내부 처리용으로 사용됩니다.

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.1.0 | 2026-06-01 | v1.0 기준 갱신: 보고서용 항목 17개 → 18개, oily_score, cheek_sagging_score 추가. OUTPUT_KEYS 총 24개 (내부 처리용 6개 포함). 코드 버전 v3.4 → v1.0으로 통일 | Cascade |
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
| 0.1.0 | 2026-04-29 | Perfect Corp vs COTELEAF 측정항목 비교 문서 초기 작성 (v3.2 기준) | Cascade |
