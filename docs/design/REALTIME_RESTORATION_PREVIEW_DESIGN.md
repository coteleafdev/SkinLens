# 실시간 복원 프리뷰 설계 (Realtime Restoration Preview Design)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

이 문서는 복원 강도 슬라이더를 통한 실시간 복원 프리뷰 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 전체 복원 후 결과 확인
- 복원 강도 조절 불가
- 사용자 선호도 반영 어려움
- 재복원 필요 시 전체 재처리

### 1.2 제안된 기능
- 복원 강도 슬라이더 (0 ~ 100)
- 실시간 프리뷰 (슬라이더 조절 시 즉시 반영)
- 다양한 복원 강도 옵션 (경량/중간/강력)
- 사용자 선호도에 맞는 복원 강도 선택

### 1.3 기대 효과
- 사용자 만족도 향상 (선호도 반영)
- 재복원 횟수 감소
- 사용자 경험 개선
- 개인화된 복원 결과

---

## 2. 복원 강도 파라미터

### 2.1 복원 강도 정의

**복원 강도 (restoration_strength):**
- 범위: 0 ~ 100
- 0: 복원 없음 (원본 이미지)
- 30: 경량 복원 (자연스러운 보정)
- 50: 중간 복원 (기본값)
- 70: 강력 복원 (확실한 개선)
- 100: 최대 복원 (최대 개선)

### 2.2 복원 엔진 파라미터 매핑

**CodeFormer 파라미터:**
- `fidelity`: 충실도 (높으면 원본 유지, 낮으면 복원 강화)
- `upscale`: 업스케일 강도
- `bg_upsampler`: 배경 업스케일러

**복원 강도별 파라미터:**
```python
RESTORATION_STRENGTH_MAP = {
    0: {
        "fidelity": 1.0,  # 원본 유지
        "upscale": 1,
        "bg_upsampler": None
    },
    30: {
        "fidelity": 0.8,  # 경량 복원
        "upscale": 1,
        "bg_upsampler": None
    },
    50: {
        "fidelity": 0.5,  # 중간 복원 (기본)
        "upscale": 2,
        "bg_upsampler": "realesrgan"
    },
    70: {
        "fidelity": 0.3,  # 강력 복원
        "upscale": 2,
        "bg_upsampler": "realesrgan"
    },
    100: {
        "fidelity": 0.1,  # 최대 복원
        "upscale": 2,
        "bg_upsampler": "realesrgan"
    }
}
```

### 2.3 선형 보간

**중간 강도 계산:**
```python
def get_restoration_params(strength: int) -> Dict[str, Any]:
    """복원 강도에 따른 파라미터 계산 (선형 보간)"""
    strength = max(0, min(100, strength))
    
    # 가장 가까운 두 강도 찾기
    strength_points = sorted(RESTORATION_STRENGTH_MAP.keys())
    
    for i in range(len(strength_points) - 1):
        low = strength_points[i]
        high = strength_points[i + 1]
        
        if low <= strength <= high:
            # 선형 보간
            ratio = (strength - low) / (high - low)
            low_params = RESTORATION_STRENGTH_MAP[low]
            high_params = RESTORATION_STRENGTH_MAP[high]
            
            return {
                "fidelity": low_params["fidelity"] * (1 - ratio) + high_params["fidelity"] * ratio,
                "upscale": low_params["upscale"] if ratio < 0.5 else high_params["upscale"],
                "bg_upsampler": low_params["bg_upsampler"] if ratio < 0.5 else high_params["bg_upsampler"]
            }
    
    return RESTORATION_STRENGTH_MAP[50]  # 기본값
```

---

## 3. 실시간 프리뷰 구현

### 3.1 클라이언트 측 프리뷰

**Flutter 구현:**
```dart
class RestorationPreviewSlider extends StatefulWidget {
  final String originalImagePath;
  final Function(int) onStrengthChanged;
  
  @override
  _RestorationPreviewSliderState createState() => _RestorationPreviewSliderState();
}

class _RestorationPreviewSliderState extends State<RestorationPreviewSlider> {
  double _strength = 50.0;
  Uint8List? _previewImage;
  bool _isProcessing = false;
  
  Future<void> _updatePreview(double strength) async {
    if (_isProcessing) return;
    
    setState(() {
      _isProcessing = true;
      _strength = strength;
    });
    
    try {
      // 서버에 프리뷰 요청
      final preview = await _requestPreview(strength.toInt());
      setState(() {
        _previewImage = preview;
      });
      
      widget.onStrengthChanged(strength.toInt());
    } catch (e) {
      print('프리뷰 업데이트 실패: $e');
    } finally {
      setState(() {
        _isProcessing = false;
      });
    }
  }
  
  Future<Uint8List> _requestPreview(int strength) async {
    // 저해상도 프리뷰 요청 (빠른 응답)
    final response = await http.post(
      Uri.parse('$baseUrl/v1/restoration/preview'),
      headers: {'Authorization': 'Bearer $token'},
      body: jsonEncode({
        'image_path': widget.originalImagePath,
        'strength': strength,
        'preview_size': 512  // 저해상도 프리뷰
      }),
    );
    
    if (response.statusCode == 200) {
      return response.bodyBytes;
    } else {
      throw Exception('프리뷰 요청 실패');
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 프리뷰 이미지
        Container(
          height: 300,
          child: _previewImage != null
              ? Image.memory(_previewImage!)
              : Image.file(File(widget.originalImagePath)),
        ),
        SizedBox(height: 16),
        
        // 복원 강도 슬라이더
        Slider(
          value: _strength,
          min: 0,
          max: 100,
          divisions: 20,
          label: '${_strength.toInt()}%',
          onChanged: _isProcessing ? null : _updatePreview,
        ),
        
        // 프리셋 버튼
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _buildPresetButton('경량', 30),
            _buildPresetButton('중간', 50),
            _buildPresetButton('강력', 70),
          ],
        ),
      ],
    );
  }
  
  Widget _buildPresetButton(String label, int strength) {
    return ElevatedButton(
      onPressed: _isProcessing ? null : () => _updatePreview(strength.toDouble()),
      child: Text(label),
    );
  }
}
```

### 3.2 서버 측 프리뷰 엔드포인트

**엔드포인트:** `POST /v1/restoration/preview`

**Request:**
```json
{
  "image_path": "/path/to/image.jpg",
  "strength": 50,
  "preview_size": 512
}
```

**Response:**
- Content-Type: image/jpeg
- 프리뷰 이미지 (저해상도)

**구현:**
```python
@router.post("/preview")
async def restoration_preview(
    image_path: str = Form(...),
    strength: int = Form(50),
    preview_size: int = Form(512),
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """복원 프리뷰 생성 (저해상도, 빠른 응답)"""
    try:
        # 이미지 로드
        image = cv2.imread(image_path)
        if image is None:
            raise HTTPException(status_code=404, detail="image not found")
        
        # 저해상도로 리사이징 (빠른 처리)
        h, w = image.shape[:2]
        scale = preview_size / max(h, w)
        preview_image = cv2.resize(image, None, fx=scale, fy=scale)
        
        # 복원 파라미터 계산
        params = get_restoration_params(strength)
        
        # 복원 처리 (저해상도)
        restored_preview = apply_restoration(preview_image, params)
        
        # JPEG로 인코딩
        _, buffer = cv2.imencode('.jpg', restored_preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        return Response(content=buffer.tobytes(), media_type="image/jpeg")
        
    except Exception as e:
        log.error(f"복원 프리뷰 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="preview generation failed")
```

### 3.3 캐싱 전략

**프리뷰 캐시:**
```python
class PreviewCache:
    """프리뷰 이미지 캐시"""
    
    def __init__(self, max_size: int = 100):
        self.cache: Dict[str, bytes] = {}
        self.max_size = max_size
    
    def get(self, image_path: str, strength: int) -> Optional[bytes]:
        key = f"{image_path}_{strength}"
        return self.cache.get(key)
    
    def set(self, image_path: str, strength: int, data: bytes):
        key = f"{image_path}_{strength}"
        
        # 캐시 크기 제한
        if len(self.cache) >= self.max_size:
            # 가장 오래된 항목 삭제
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[key] = data
    
    def clear(self):
        self.cache.clear()
```

---

## 4. 최종 복원 적용

### 4.1 API 파라미터 추가

**Job 생성 엔드포인트:**
```
POST /v1/analysis/jobs
```

**추가 파라미터:**
- `restoration_strength`: (int, optional) 복원 강도 (기본: 50)

### 4.2 파이프라인 통합

**파라미터 전달:**
```python
def run_analysis_pipeline(
    input_image: str,
    restoration_strength: int = 50,
    # ... 기존 파라미터
):
    # 복원 파라미터 계산
    restoration_params = get_restoration_params(restoration_strength)
    
    # 복원 처리
    restored_image = run_restorer(
        cfg=config,
        input_path=input_image,
        output_path=output_path,
        fidelity=restoration_params["fidelity"],
        upscale=restoration_params["upscale"],
        bg_upsampler=restoration_params["bg_upsampler"],
    )
    
    # ... 분석 처리
```

---

## 5. 사용자 경험

### 5.1 프리뷰 흐름

1. **이미지 업로드**
   - 원본 이미지 표시
   - 복원 강도 슬라이더 표시 (기본 50)

2. **슬라이더 조절**
   - 실시간 프리뷰 업데이트
   - 로딩 인디케이터 표시
   - 캐시된 프리뷰 사용 (빠른 응답)

3. **프리셋 선택**
   - 경량/중간/강력 버튼
   - 즉시 해당 강도로 프리뷰

4. **최종 적용**
   - 선택한 강도로 전체 복원
   - 분석 진행

### 5.2 UI/UX 고려사항

**슬라이더:**
- 범위: 0 ~ 100
- 단위: 5단계 (0, 20, 40, 60, 80, 100)
- 라벨: "경량" ~ "최대"

**프리뷰:**
- 전후 비교 (슬라이더 드래그 시)
- 저해상도 프리뷰 (빠른 응답)
- 로딩 인디케이터

**프리셋:**
- 경량 (30): 자연스러운 보정
- 중간 (50): 기본값
- 강력 (70): 확실한 개선

---

## 6. 성능 최적화

### 6.1 프리뷰 최적화

**저해상도 프리뷰:**
- 프리뷰 해상도: 512x512
- 전체 복원 해상도: 원본 크기
- 처리 시간: ~1초 (프리뷰), ~10초 (전체)

**캐싱:**
- 프리뷰 캐시 (최대 100개)
- LRU (Least Recently Used) 정책
- 메모리 사용: ~50MB

### 6.2 병렬 처리

**프리뷰 생성:**
- ThreadPoolExecutor 사용
- 최대 2개 동시 프리뷰
- 타임아웃: 5초

---

## 7. 구현 단계

### Phase 1: 백엔드
1. 복원 강도 파라미터 매핑
2. 선형 보간 함수 구현
3. 프리뷰 엔드포인트 구현
4. 캐싱 시스템 구현

### Phase 2: 파이프라인
1. restoration_strength 파라미터 추가
2. 파라미터 전달 로직 수정
3. 복원 엔진 파라미터 적용

### Phase 3: API
1. Job 생성 엔드포인트 파라미터 추가
2. 프리뷰 엔드포인트 추가

### Phase 4: 클라이언트 UI
1. 복원 강도 슬라이더 위젯
2. 프리뷰 이미지 표시
3. 프리셋 버튼
4. 캐싱 로직

### Phase 5: 테스트
1. 단위 테스트
2. 통합 테스트
3. 성능 테스트
4. UI 테스트

---

## 8. 일정 추정

- 백엔드: 2일
- 파이프라인: 1일
- API: 0.5일
- 클라이언트 UI: 2일
- 테스트: 1.5일
- **총계: 7일**

---

## 9. 성공 지표

- 프리뷰 응답 시간: < 2초
- 사용자 만족도: +15% 향상
- 재복원 횟수: -40% 감소
- 프리뷰 캐시 적중률: 80% 이상

---

## 10. 롤백 계횸

- 복원 강도 파라미터 비활성화
- 기본값(50) 고정 사용
- 프리뷰 엔드포인트 비활성화
- 클라이언트 UI에서 슬라이더 숨김

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (v1.0에서 마이그레이션) | Cascade |
| 0.1.0 | 2026-05-24 | 실시간 복원 프리뷰 설계 문서 초기 작성 | Cascade |
