# 피부 타입 자동 감지 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 이미지 분석을 통한 피부 타입 자동 감지 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 설문(survey) 기반으로 피부 타입 입력
- 사용자가 직접 피부 타입 선택 (지성/건성/복합성/민감성)
- 사용자 오류 가능성 (자신의 피부 타입 오인)
- 설문 응답 부담

### 1.2 제안된 기능
- 이미지 분석으로 피부 타입 자동 감지
- 지성/건성/복합성/민감성 4가지 타입 분류
- 설문 입력과 자동 감지 결과 비교
- 사용자 확인 및 수정 가능

### 1.3 기대 효과
- 사용자 편의성 향상 (설문 항목 감소)
- 설문 오류 감소 (자동 감지 기반)
- 분석 정확도 향상 (정확한 피부 타입 기반)
- 사용자 경험 개선

---

## 2. 피부 타입 정의

### 2.1 피부 타입 분류

**지성 (Oily):**
- T존(이마, 코, 턱) 유분 과다
- 모공 크기 큼
- 광택 있음
- 화장 잘 지워짐

**건성 (Dry):**
- 전체적으로 건조함
- 각질 발생
- 모공 작음
- 광택 없음
- 화장 잘 지워지지 않음

**복합성 (Combination):**
- T존은 지성, U존(볼)은 건성/중성
- 모공 크기 불균형
- 부분적으로 유분/건조

**민감성 (Sensitive):**
- 홍조 발생 빈번
- 자극에 민감
- 가려움/따가움
- 염증 반응

### 2.2 감지 특성

**지성 감지 특성:**
- 광택도 (shine_score)
- 모공 크기 (pore_size_score)
- 유분도 (oiliness_score)

**건성 감지 특성:**
- 각질도 (dryness_score)
- 거칠기 (roughness_score)
- 수분도 (hydration_score)

**복합성 감지 특성:**
- T존 vs U존 유분도 차이
- 모공 크기 분포 불균형
- 부분적 광택

**민감성 감지 특성:**
- 홍조도 (redness_score)
- 염증도 (inflammation_score)
- 모세혈관 가시성 (capillary_visibility_score)

---

## 3. 자동 감지 알고리즘

### 3.1 특성 추출

```python
def extract_skin_type_features(analysis_result):
    """피부 타입 감지를 위한 특성 추출"""
    measurements = analysis_result["measurements"]
    
    features = {
        # 지성 관련
        "shine_score": measurements.get("shine_score", 0),
        "pore_size_score": measurements.get("pore_size_score", 0),
        "oiliness_score": calculate_oiliness(measurements),
        
        # 건성 관련
        "dryness_score": measurements.get("dryness_score", 0),
        "roughness_score": measurements.get("roughness_score", 0),
        "hydration_score": calculate_hydration(measurements),
        
        # 복합성 관련
        "t_zone_oiliness": calculate_t_zone_oiliness(measurements),
        "u_zone_oiliness": calculate_u_zone_oiliness(measurements),
        "oiliness_imbalance": calculate_oiliness_imbalance(measurements),
        
        # 민감성 관련
        "redness_score": measurements.get("redness_score", 0),
        "inflammation_score": measurements.get("inflammation_score", 0),
        "capillary_visibility": calculate_capillary_visibility(measurements),
    }
    
    return features
```

### 3.2 T존/U존 분석

```python
def analyze_face_zones(landmarks, image):
    """얼굴 영역 분석 (T존/U존)"""
    # T존: 이마, 코, 턱
    t_zone = extract_t_zone(landmarks, image)
    
    # U존: 볼, 눈 주변
    u_zone = extract_u_zone(landmarks, image)
    
    # 각 영역별 특성 추출
    t_zone_features = extract_region_features(t_zone)
    u_zone_features = extract_region_features(u_zone)
    
    return {
        "t_zone": t_zone_features,
        "u_zone": u_zone_features,
        "imbalance": calculate_imbalance(t_zone_features, u_zone_features)
    }
```

### 3.3 분류 모델

```python
class SkinTypeClassifier:
    def __init__(self):
        self.model = self._load_model()
        self.thresholds = {
            "oily": 0.7,
            "dry": 0.7,
            "combination": 0.6,
            "sensitive": 0.65
        }
    
    def classify(self, features):
        """피부 타입 분류"""
        scores = self._calculate_scores(features)
        
        # 최고 점수 타입 선택
        predicted_type = max(scores, key=scores.get)
        confidence = scores[predicted_type]
        
        # 신뢰도 낮으면 "unknown" 반환
        if confidence < 0.5:
            predicted_type = "unknown"
        
        return {
            "skin_type": predicted_type,
            "confidence": confidence,
            "all_scores": scores
        }
    
    def _calculate_scores(self, features):
        """각 타입별 점수 계산"""
        scores = {
            "oily": self._calculate_oily_score(features),
            "dry": self._calculate_dry_score(features),
            "combination": self._calculate_combination_score(features),
            "sensitive": self._calculate_sensitive_score(features)
        }
        
        # 정규화 (0 ~ 1)
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}
        
        return scores
    
    def _calculate_oily_score(self, features):
        """지성 점수 계산"""
        score = (
            features["shine_score"] * 0.4 +
            features["pore_size_score"] * 0.3 +
            features["oiliness_score"] * 0.3
        )
        return score / 100.0
    
    def _calculate_dry_score(self, features):
        """건성 점수 계산"""
        score = (
            features["dryness_score"] * 0.4 +
            features["roughness_score"] * 0.3 +
            (100 - features["hydration_score"]) * 0.3
        )
        return score / 100.0
    
    def _calculate_combination_score(self, features):
        """복합성 점수 계산"""
        score = (
            features["oiliness_imbalance"] * 0.5 +
            (features["t_zone_oiliness"] - features["u_zone_oiliness"]) * 0.5
        )
        return max(0, min(1, score / 50.0))
    
    def _calculate_sensitive_score(self, features):
        """민감성 점수 계산"""
        score = (
            features["redness_score"] * 0.4 +
            features["inflammation_score"] * 0.3 +
            features["capillary_visibility"] * 0.3
        )
        return score / 100.0
```

### 3.4 다중 타입 지원

```python
def classify_multiple_types(features):
    """다중 피부 타입 지원 (예: 지성+민감성)"""
    classifier = SkinTypeClassifier()
    primary_result = classifier.classify(features)
    
    # 2위 타입 확인
    scores = primary_result["all_scores"]
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    if len(sorted_scores) >= 2:
        second_type, second_confidence = sorted_scores[1]
        
        # 2위 타입도 신뢰도 높으면 다중 타입으로 반환
        if second_confidence > 0.4:
            return {
                "skin_types": [
                    primary_result["skin_type"],
                    second_type
                ],
                "primary_type": primary_result["skin_type"],
                "secondary_type": second_type,
                "confidence": primary_result["confidence"],
                "all_scores": scores
            }
    
    return {
        "skin_types": [primary_result["skin_type"]],
        "primary_type": primary_result["skin_type"],
        "secondary_type": None,
        "confidence": primary_result["confidence"],
        "all_scores": scores
    }
```

---

## 4. 데이터 구조

### 4.1 피부 타입 감지 결과

**JSON 구조:**
```json
{
  "skin_types": ["oily", "sensitive"],
  "primary_type": "oily",
  "secondary_type": "sensitive",
  "confidence": 0.82,
  "all_scores": {
    "oily": 0.82,
    "dry": 0.05,
    "combination": 0.08,
    "sensitive": 0.05
  },
  "features": {
    "shine_score": 75.0,
    "pore_size_score": 68.0,
    "oiliness_score": 80.0,
    "dryness_score": 20.0,
    "roughness_score": 25.0,
    "hydration_score": 60.0,
    "t_zone_oiliness": 85.0,
    "u_zone_oiliness": 40.0,
    "oiliness_imbalance": 45.0,
    "redness_score": 55.0,
    "inflammation_score": 40.0,
    "capillary_visibility": 50.0
  },
  "zone_analysis": {
    "t_zone": {
      "oiliness": 85.0,
      "pore_size": 70.0,
      "shine": 80.0
    },
    "u_zone": {
      "oiliness": 40.0,
      "pore_size": 50.0,
      "shine": 45.0
    }
  }
}
```

### 4.2 데이터베이스 스키마

**analyses 테이블 확장:**
```sql
ALTER TABLE analyses ADD COLUMN detected_skin_types TEXT;  -- JSON array
ALTER TABLE analyses ADD COLUMN skin_type_confidence REAL;
ALTER TABLE analyses ADD COLUMN skin_type_features TEXT;  -- JSON
ALTER TABLE analyses ADD COLUMN skin_type_source TEXT;  -- 'auto', 'survey', 'manual'
```

**피부 타입 검증 테이블 (skin_type_validations):**
```sql
CREATE TABLE skin_type_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    survey_skin_types TEXT,  -- JSON array (설문 입력)
    detected_skin_types TEXT,  -- JSON array (자동 감지)
    user_confirmed_skin_types TEXT,  -- JSON array (사용자 확인)
    is_correct INTEGER,  -- 0: 오류, 1: 정확
    created_at TEXT NOT NULL,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
);
```

---

## 5. 통합 방법

### 5.1 설문과 자동 감지 비교

```python
def compare_skin_types(survey_types, detected_types):
    """설문 입력과 자동 감지 결과 비교"""
    survey_set = set(survey_types)
    detected_set = set(detected_types)
    
    # 일치 여부 확인
    if survey_set == detected_set:
        return {
            "match": True,
            "match_type": "exact",
            "survey_types": survey_types,
            "detected_types": detected_types
        }
    
    # 부분 일치 확인
    intersection = survey_set & detected_set
    if intersection:
        return {
            "match": False,
            "match_type": "partial",
            "survey_types": survey_types,
            "detected_types": detected_types,
            "common_types": list(intersection)
        }
    
    # 불일치
    return {
        "match": False,
        "match_type": "none",
        "survey_types": survey_types,
        "detected_types": detected_types
    }
```

### 5.2 사용자 확인 플로우

```python
def confirm_skin_type(analysis_id, user_confirmed_types):
    """사용자가 피부 타입 확인"""
    # 검증 데이터 저장
    insert_skin_type_validation(
        analysis_id=analysis_id,
        survey_types=get_survey_types(analysis_id),
        detected_types=get_detected_types(analysis_id),
        user_confirmed_types=user_confirmed_types,
        is_correct=1  # 사용자 확인 = 정확
    )
    
    # 최종 피부 타입 업데이트
    update_analysis_skin_types(
        analysis_id=analysis_id,
        skin_types=user_confirmed_types,
        source="manual"
    )
```

### 5.3 학습 데이터 수집

```python
def collect_training_data():
    """학습 데이터 수집 (검증 결과 기반)"""
    validations = get_all_validations()
    
    training_data = []
    
    for validation in validations:
        if validation["is_correct"]:
            # 사용자 확인된 데이터를 학습 데이터로 사용
            features = get_skin_type_features(validation["analysis_id"])
            label = validation["user_confirmed_skin_types"]
            
            training_data.append({
                "features": features,
                "label": label
            })
    
    return training_data
```

---

## 6. API 변경 사항

### 6.1 분석 결과 확장

**Response 추가 필드:**
```json
{
  "analysis": {
    "skin_type_detection": {
      "skin_types": ["oily", "sensitive"],
      "primary_type": "oily",
      "secondary_type": "sensitive",
      "confidence": 0.82,
      "all_scores": {
        "oily": 0.82,
        "dry": 0.05,
        "combination": 0.08,
        "sensitive": 0.05
      }
    }
  }
}
```

### 6.2 피부 타입 확인 엔드포인트

**엔드포인트:** `POST /v3/analyses/{analysis_id}/confirm-skin-type`

**Request:**
```json
{
  "skin_types": ["oily", "sensitive"]
}
```

**Response:**
```json
{
  "analysis_id": 123,
  "confirmed_skin_types": ["oily", "sensitive"],
  "previous_detected_types": ["oily", "sensitive"],
  "survey_types": ["oily"],
  "match_type": "partial"
}
```

### 6.3 피부 타입 재감지

**엔드포인트:** `POST /v3/analyses/{analysis_id}/reclassify-skin-type`

**Request:**
```json
{
  "force_reclassification": true
}
```

**Response:**
```json
{
  "analysis_id": 123,
  "new_skin_types": ["oily", "sensitive"],
  "previous_skin_types": ["oily"],
  "confidence": 0.82
}
```

---

## 7. 클라이언트 구현 (Flutter)

### 7.1 피부 타입 감지 결과 표시

```dart
class SkinTypeDetectionResult extends StatelessWidget {
  final SkinTypeDetection detection;
  
  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '자동 감지된 피부 타입',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: detection.skinTypes.map((type) {
                return Chip(
                  label: Text(getSkinTypeName(type)),
                  backgroundColor: getSkinTypeColor(type),
                );
              }).toList(),
            ),
            SizedBox(height: 8),
            Text(
              '신뢰도: ${(detection.confidence * 100).toStringAsFixed(0)}%',
              style: TextStyle(color: Colors.grey),
            ),
            SizedBox(height: 8),
            _buildScoreBars(detection.allScores),
          ],
        ),
      ),
    );
  }
  
  Widget _buildScoreBars(Map<String, double> scores) {
    return Column(
      children: scores.entries.map((entry) {
        return Padding(
          padding: EdgeInsets.symmetric(vertical: 4),
          child: Row(
            children: [
              SizedBox(
                width: 80,
                child: Text(getSkinTypeName(entry.key)),
              ),
              Expanded(
                child: LinearProgressIndicator(
                  value: entry.value,
                  backgroundColor: Colors.grey[200],
                ),
              ),
              SizedBox(width: 8),
              Text('${(entry.value * 100).toStringAsFixed(0)}%'),
            ],
          ),
        );
      }).toList(),
    );
  }
}
```

### 7.2 피부 타입 확인 다이얼로그

```dart
class SkinTypeConfirmationDialog extends StatefulWidget {
  final List<String> detectedTypes;
  final List<String> surveyTypes;
  final Function(List<String>) onConfirm;
  
  @override
  _SkinTypeConfirmationDialogState createState() =>
      _SkinTypeConfirmationDialogState();
}

class _SkinTypeConfirmationDialogState
    extends State<SkinTypeConfirmationDialog> {
  List<String> selectedTypes = [];
  
  @override
  void initState() {
    super.initState();
    selectedTypes = List.from(widget.detectedTypes);
  }
  
  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('피부 타입 확인'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('자동 감지된 피부 타입:'),
          SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: SKIN_TYPES.map((type) {
              return FilterChip(
                label: Text(getSkinTypeName(type)),
                selected: selectedTypes.contains(type),
                onSelected: (selected) {
                  setState(() {
                    if (selected) {
                      selectedTypes.add(type);
                    } else {
                      selectedTypes.remove(type);
                    }
                  });
                },
              );
            }).toList(),
          ),
          if (widget.surveyTypes.isNotEmpty) ...[
            SizedBox(height: 16),
            Text('설문 입력: ${widget.surveyTypes.map(getSkinTypeName).join(', ')}'),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text('취소'),
        ),
        ElevatedButton(
          onPressed: () {
            widget.onConfirm(selectedTypes);
            Navigator.pop(context);
          },
          child: Text('확인'),
        ),
      ],
    );
  }
}
```

### 7.3 설문 단순화

```dart
class SimplifiedSurveyForm extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 기존 설문 항목들
        SurveyField('성별', ...),
        SurveyField('연령대', ...),
        SurveyField('피부 고민사항', ...),
        
        // 피부 타입은 자동 감지로 대체
        // SurveyField('피부 타입', ...),  // 제거
        
        // 대신 안내 메시지
        Card(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(Icons.auto_awesome, color: Colors.blue),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '피부 타입은 이미지 분석으로 자동 감지됩니다.',
                    style: TextStyle(color: Colors.grey),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
```

---

## 8. 모델 학습

### 8.1 학습 데이터 준비

```python
def prepare_training_dataset():
    """학습 데이터셋 준비"""
    # 검증된 데이터 수집
    validations = get_validated_validations(min_confidence=0.7)
    
    # 특성 추출
    X = []
    y = []
    
    for validation in validations:
        features = extract_skin_type_features(validation["analysis_id"])
        label = validation["user_confirmed_skin_types"]
        
        X.append(features)
        y.append(label)
    
    # 다중 라벨 인코딩
    mlb = MultiLabelBinarizer(classes=["oily", "dry", "combination", "sensitive"])
    y_encoded = mlb.fit_transform(y)
    
    return X, y_encoded, mlb
```

### 8.2 모델 훈련

```python
def train_skin_type_model():
    """피부 타입 분류 모델 훈련"""
    X, y, mlb = prepare_training_dataset()
    
    # 특성 스케일링
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # 모델 훈련 (Random Forest)
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42
    )
    model.fit(X_scaled, y)
    
    # 모델 저장
    joblib.dump({
        "model": model,
        "scaler": scaler,
        "mlb": mlb
    }, "skin_type_model.pkl")
    
    return model
```

### 8.3 모델 평가

```python
def evaluate_skin_type_model():
    """모델 평가"""
    X, y, mlb = prepare_training_dataset()
    
    # 훈련/테스트 분할
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # 모델 로드
    model_data = joblib.load("skin_type_model.pkl")
    model = model_data["model"]
    scaler = model_data["scaler"]
    
    # 예측
    X_test_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_test_scaled)
    
    # 평가
    accuracy = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average='macro')
    
    print(f"Accuracy: {accuracy:.3f}")
    print(f"F1 Score: {f1:.3f}")
    
    return accuracy, f1
```

---

## 9. 구현 단계

### Phase 1: 특성 추출
1. T존/U존 분석 구현
2. 피부 타입 특성 추출 로직
3. 광택/유분/수분도 계산

### Phase 2: 분류 모델
1. 규칙 기반 분류기 구현
2. 다중 타입 지원
3. 신뢰도 계산

### Phase 3: 데이터베이스
1. analyses 테이블 확장
2. skin_type_validations 테이블 생성
3. 마이그레이션 스크립트

### Phase 4: API
1. 분석 결과 확장
2. 피부 타입 확인 엔드포인트
3. 재감지 엔드포인트

### Phase 5: 클라이언트 UI
1. 자동 감지 결과 표시
2. 확인 다이얼로그
3. 설문 단순화

### Phase 6: 모델 학습
1. 학습 데이터 수집
2. 모델 훈련
3. 모델 평가

### Phase 7: 테스트
1. 단위 테스트
2. 통합 테스트
3. 정확도 테스트

---

## 10. 일정 추정

- 특성 추출: 2일
- 분류 모델: 2일
- 데이터베이스: 1일
- API: 1일
- 클라이언트 UI: 2일
- 모델 학습: 2일
- 테스트: 2일
- **총계: 12일**

---

## 11. 성공 지표

- 자동 감지 정확도: 85% 이상
- 사용자 확인률: 90% 이상
- 설문 응답 시간: -30% 감소
- 사용자 만족도: +10% 향상
- 피부 타입 오류율: -50% 감소

---

## 12. 롤백 계획

- 자동 감지 비활성화 플래그
- 설문 기반 피부 타입 입력으로 복귀
- 검증 데이터 보존 (추후 학습용)

---

*작성일: 2026-05-24*
