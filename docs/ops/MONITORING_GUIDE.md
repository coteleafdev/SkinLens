# 모니터링 가이드 (Monitoring Guide)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.6  
> **작성일:** 2026-05-30  
*상태:* 초안

---

## 개요

이 가이드는 SkinLens 시스템을 모니터링하는 방법을 설명합니다.

---

## 모니터링 대상

### 1. 서버 상태

- **CPU 사용률:** 70% 이상 경고
- **메모리 사용률:** 80% 이상 경고
- **디스크 사용률:** 90% 이상 경고
- **GPU 사용률:** 90% 이상 경고
- **GPU 메모리:** 90% 이상 경고

### 2. API 성능

- **응답 시간:** P95 < 2초, P99 < 5초
- **요청률:** 분당 1000회 이상 경고
- **에러율:** 1% 이상 경고, 5% 이상 심각

### 3. 분석 작업

- **대기 시간:** 5분 이상 경고
- **실패율:** 5% 이상 경고
- **처리 시간:** P95 < 3분

### 4. 데이터베이스

- **쿼리 시간:** P95 < 100ms
- **연결 수:** 80% 이상 경고
- **디스크 사용:** 90% 이상 경고

---

## 모니터링 도구

### Prometheus + Grafana (권장)

#### Prometheus 설정

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'skinlens'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

#### Grafana 대시보드

**서버 상태 대시보드:**
- CPU, 메모리, 디스크, GPU 사용률
- 네트워크 트래픽
- 시스템 로드

**API 성능 대시보드:**
- 요청률 (RPS)
- 응답 시간 (P50, P95, P99)
- 에러율
- 엔드포인트별 성능

**분석 작업 대시보드:**
- 작업 큐 크기
- 처리 시간
- 성공/실패율
- LLM API 호출 시간

---

### Health Check

#### 엔드포인트

```bash
curl http://localhost:8000/health
```

**응답:**
```json
{
  "status": "healthy",
  "timestamp": "ISO8601",
  "services": {
    "database": "ok",
    "llm_api": "ok",
    "restoration_model": "ok"
  }
}
```

---

### 로그 모니터링

#### 로그 레벨

- **DEBUG:** 개발용 디버깅 정보
- **INFO:** 일반 운영 정보
- **WARNING:** 경고 (주의 필요)
- **ERROR:** 에러 (즉시 조치 필요)

#### 로그 위치

```bash
# Docker
docker logs -f skinlens

# 직접 실행
tail -f /var/log/skinlens/app.log
```

#### 로그 필터링

```bash
# 에러만 확인
grep ERROR /var/log/skinlens/app.log

# 특정 시간대 확인
grep "2026-05-30 14:" /var/log/skinlens/app.log
```

---

## 알림 설정

### Slack 알림

```yaml
# alertmanager.yml
receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#alerts'
```

### PagerDuty (선택)

```yaml
receivers:
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_SERVICE_KEY'
```

---

## 알림 규칙

### 심각 (Critical)

- 서버 다운
- API 에러율 > 5%
- 데이터베이스 연결 실패
- GPU 오류

### 경고 (Warning)

- CPU 사용률 > 70%
- 메모리 사용률 > 80%
- 응답 시간 P99 > 5초
- 디스크 사용률 > 90%

### 정보 (Info)

- 배포 완료
- 설정 변경
- 정기 백업 완료

---

## 메트릭 수집

### 내장 메트릭

SkinLens는 내장 메트릭 수집 시스템을 제공합니다.

```python
from src.monitoring.metrics_collector import MetricsCollector

collector = MetricsCollector.get_instance()

# 카운터
collector.increment_counter("api_requests")

# 타이머
with collector.measure("image_analysis"):
    analyze_image(image_path)

# 게이지
collector.set_gauge("active_jobs", 5)
```

### 커스텀 메트릭

```python
# 분석 성공률
collector.increment_counter("analysis_success")

# LLM API 호출 시간
with collector.measure("llm_api_call"):
    llm_response = call_llm_api()
```

---

## 성능 분석

### 느린 쿼리 식별

```sql
-- SQLite
SELECT * FROM analysis_stats 
WHERE execution_time_sec > 1.0 
ORDER BY execution_time_sec DESC 
LIMIT 10;
```

### 병목 지점 식별

```python
# 프로파일링
import cProfile

def profile_analysis():
    profiler = cProfile.Profile()
    profiler.enable()
    analyze_image(image_path)
    profiler.disable()
    profiler.print_stats(sort='cumtime')
```

---

## 용량 계획

### 트래픽 예측

- **일일 분석 건수:** 현재 100건 → 예상 1000건
- **평균 처리 시간:** 2분
- **필요 서버 수:** 3대 (수평 확장)

### 스토리지 예측

- **이미지 크기:** 평균 5MB
- **일일 저장량:** 500MB
- **월간 저장량:** 15GB
- **연간 저장량:** 180GB

---

## 보안 모니터링

### 비정상 접근 탐지

- 동일 IP에서 과도한 요청
- 인증 실패 반복
- 의심스러운 파일 업로드

### 로그 감사

```bash
# 인증 실패 로그
grep "authentication failed" /var/log/skinlens/app.log

# 비정상 파일 업로드
grep "invalid file" /var/log/skinlens/app.log
```

---

## 트러블슈팅

### 모니터링 데이터 없음

**문제:** 메트릭이 수집되지 않습니다.

**해결:**
1. Prometheus 설정 확인
2. 네트워크 연결 확인
3. 방화벽 규칙 확인

### 알림 수신 안됨

**문제:** 알림이 도착하지 않습니다.

**해결:**
1. Alertmanager 설정 확인
2. Webhook URL 확인
3. Slack/PagerDuty 설정 확인

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
