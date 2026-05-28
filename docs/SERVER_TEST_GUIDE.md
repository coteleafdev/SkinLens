# 서버 테스트 가이드

> **프로젝트:** SkinLens v1.0
> **마지막 수정:** 2026-05-28

## 개요

SkinLens 서버는 CLI 기반으로 작동하며, FastAPI를 통해 REST API를 제공합니다. 본 문서는 서버를 테스트하는 절차를 설명합니다.

---

## 서버 아키텍처

### 구조

```
src/server/
    deps.py             ← 공유 상태·의존성·유틸 (app 미포함)
    server.py           ← app 생성·미들웨어·라우터 등록
    routers/
        jobs.py         ← POST/GET /v3/analysis/jobs/*
        logs.py         ← GET /v3/logs/*
        stats.py        ← GET/POST /v3/stats/*
        auth.py         ← POST /v3/auth/login, GET /v3/auth/me
        customer.py     ← GET/DELETE /v3/customer/my/*
        admin.py        ← GET /v3/admin/*, GET /v3/health/db
```

### 주요 라우터

| 라우터 | 경로 | 설명 |
|--------|------|------|
| jobs | `/v3/analysis/jobs/*` | 분석 작업 생성, 조회, 취소 |
| logs | `/v3/logs/*` | 로그 조회 |
| stats | `/v3/stats/*` | 통계 조회 |
| auth | `/v3/auth/*` | 인증 (로그인, 사용자 정보) |
| customer | `/v3/customer/my/*` | 고객 데이터 관리 |
| admin | `/v3/admin/*` | 관리자 기능, 헬스체크 |

---

## 테스트 절차

### 1. 서버 시작

#### 1.1 환경 설정

```bash
# 환경 변수 설정 (선택사항)
export SKIN_API_MAX_WORKERS=4
export SKIN_API_MAX_CONCURRENT=4
export JWT_SECRET_KEY=your-secret-key
```

#### 1.2 서버 실행

```bash
# 프로젝트 루트로 이동
cd c:/Project/SkinLens v1

# 서버 시작
python -m uvicorn src.server.server:app --host 0.0.0.0 --port 8000 --reload
```

#### 1.3 서버 상태 확인

```bash
# 헬스체크
curl http://localhost:8000/v3/health/db

# 예상 응답
{
  "status": "healthy",
  "db_connection": "ok"
}
```

---

### 2. 분석 작업 테스트

#### 2.1 작업 생성 (POST /v3/analysis/jobs)

```bash
curl -X POST http://localhost:8000/v3/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input_image": "path/to/image.jpg",
    "restorer": "codeformer",
    "llm_scores": true,
    "score_safety_net": true
  }'
```

**응답 예시**:
```json
{
  "job_id": "job_abc123",
  "status": "pending",
  "created_at": "2026-05-28T10:00:00Z"
}
```

#### 2.2 작업 상태 조회 (GET /v3/analysis/jobs/{job_id})

```bash
curl http://localhost:8000/v3/analysis/jobs/job_abc123
```

**응답 예시**:
```json
{
  "job_id": "job_abc123",
  "status": "completed",
  "progress": 100,
  "result": {
    "original_image": "path/to/original.jpg",
    "restored_image": "path/to/restored.jpg",
    "llm_analysis": {
      "original": {...},
      "restored": {...},
      "matched_products": [...]
    }
  }
}
```

#### 2.3 작업 취소 (DELETE /v3/analysis/jobs/{job_id})

```bash
curl -X DELETE http://localhost:8000/v3/analysis/jobs/job_abc123
```

---

### 3. 인증 테스트

#### 3.1 로그인 (POST /v3/auth/login)

```bash
curl -X POST http://localhost:8000/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "password"
  }'
```

**응답 예시**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### 3.2 사용자 정보 조회 (GET /v3/auth/me)

```bash
curl http://localhost:8000/v3/auth/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### 4. 제품 매칭 테스트

#### 4.1 설문 JSON 파일 준비

```json
{
  "survey": {
    "skin_concerns": ["여드름", "홍조"],
    "skin_types": ["oily"]
  }
}
```

#### 4.2 작업 생성 시 설문 JSON 포함

```bash
curl -X POST http://localhost:8000/v3/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input_image": "path/to/image.jpg",
    "input_json": {
      "survey": {
        "skin_concerns": ["여드름", "홍조"],
        "skin_types": ["oily"]
      }
    },
    "llm_scores": true
  }'
```

#### 4.3 매칭된 제품 확인

작업 완료 후 `result.llm_analysis.matched_products`에서 매칭된 제품 확인:

```json
{
  "matched_products": [
    {
      "product_id": "P001",
      "product_name": "CÔTELEAF 트러블 케어 세럼",
      "category": "트러블 케어",
      "key_ingredients": ["나이아신아마이드", "살리실산", "티트리 오일"],
      "match_score": 0.85,
      "match_reason": "처방 항목 매칭: M14 (2.5%), 고민사항 매칭: 여드름, 피부 타입 매칭: oily"
    }
  ]
}
```

---

### 5. 동시 요청 테스트

#### 5.1 여러 작업 동시 생성

```bash
# Bash 스크립트로 여러 요청 동시 전송
for i in {1..5}; do
  curl -X POST http://localhost:8000/v3/analysis/jobs \
    -H "Content-Type: application/json" \
    -d "{\"input_image\": \"path/to/image_$i.jpg\"}" &
done
wait
```

#### 5.2 동시성 제한 확인

```bash
# 활성 작업 수 조회
curl http://localhost:8000/v3/stats/active-jobs
```

**응답 예시**:
```json
{
  "active_jobs": 3,
  "max_concurrent": 4
}
```

---

### 6. 진행율 실시간 수신 (WebSocket)

#### 6.1 WebSocket 연결

```bash
# wscat 사용 (설치 필요: npm install -g wscat)
wscat -c ws://localhost:8000/v3/ws/jobs/job_abc123
```

#### 6.2 진행율 메시지 수신

**수신 메시지 예시**:
```json
{
  "job_id": "job_abc123",
  "status": "processing",
  "progress": 45,
  "message": "이미지 복원 중..."
}
```

**완료 메시지 예시**:
```json
{
  "job_id": "job_abc123",
  "status": "completed",
  "progress": 100,
  "message": "분석 완료",
  "result": {
    "original_image": "path/to/original.jpg",
    "restored_image": "path/to/restored.jpg"
  }
}
```

#### 6.3 Python WebSocket 클라이언트

```python
import asyncio
import websockets
import json

async def listen_job_progress(job_id):
    uri = f"ws://localhost:8000/v3/ws/jobs/{job_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Progress: {data['progress']}% - {data['message']}")
            
            if data['status'] in ['completed', 'failed']:
                break

asyncio.run(listen_job_progress("job_abc123"))
```

#### 6.4 JavaScript WebSocket 클라이언트

```javascript
const ws = new WebSocket('ws://localhost:8000/v3/ws/jobs/job_abc123');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress}% - ${data.message}`);
  
  if (data.status === 'completed') {
    console.log('Result:', data.result);
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket connection closed');
};
```

#### 6.5 Flutter WebSocket 클라이언트

```dart
import 'dart:async';
import 'package:web_socket_channel/web_socket_channel.dart';

class JobProgressListener {
  final String jobId;
  final String baseUrl = 'ws://localhost:8000';
  late WebSocketChannel _channel;
  final StreamController<Map<String, dynamic>> _progressController = StreamController.broadcast();

  JobProgressListener({required this.jobId});

  Stream<Map<String, dynamic>> get progressStream => _progressController.stream;

  void connect() {
    final uri = Uri.parse('$baseUrl/v3/ws/jobs/$jobId');
    _channel = WebSocketChannel.connect(uri);

    _channel.stream.listen(
      (message) {
        final data = Map<String, dynamic>.from(
          // JSON 디코딩 (dart:convert 필요)
          // import 'dart:convert';
          jsonDecode(message as String)
        );
        print('Progress: ${data['progress']}% - ${data['message']}');
        _progressController.add(data);

        if (data['status'] == 'completed' || data['status'] == 'failed') {
          disconnect();
        }
      },
      onError: (error) {
        print('WebSocket error: $error');
      },
      onDone: () {
        print('WebSocket connection closed');
      },
    );
  }

  void disconnect() {
    _channel.sink.close();
    _progressController.close();
  }
}

// 사용 예시
void main() async {
  final listener = JobProgressListener(jobId: 'job_abc123');
  listener.connect();

  listener.progressStream.listen((data) {
    print('Received: $data');
  });

  // 작업 완료 대기
  await Future.delayed(Duration(minutes: 5));
  listener.disconnect();
}
```

---

### 7. 로그 및 통계 테스트

#### 7.1 로그 조회 (GET /v3/logs)

```bash
curl http://localhost:8000/v3/logs?limit=10
```

#### 7.2 통계 조회 (GET /v3/stats)

```bash
curl http://localhost:8000/v3/stats
```

**응답 예시**:
```json
{
  "total_jobs": 100,
  "completed_jobs": 95,
  "failed_jobs": 5,
  "average_duration": 45.2
}
```

---

## 자동화 테스트

### Python 테스트 스크립트 (WebSocket 포함)

```python
import requests
import json
import asyncio
import websockets

BASE_URL = "http://localhost:8000"

async def listen_job_progress(job_id):
    """WebSocket으로 진행율 실시간 수신"""
    uri = f"ws://localhost:8000/v3/ws/jobs/{job_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Progress: {data['progress']}% - {data['message']}")
            
            if data['status'] in ['completed', 'failed']:
                return data

def test_server():
    # 1. 헬스체크
    response = requests.get(f"{BASE_URL}/v3/health/db")
    print(f"Health Check: {response.json()}")
    
    # 2. 작업 생성
    job_data = {
        "input_image": "path/to/image.jpg",
        "llm_scores": True,
        "input_json": {
            "survey": {
                "skin_concerns": ["여드름"],
                "skin_types": ["oily"]
            }
        }
    }
    response = requests.post(f"{BASE_URL}/v3/analysis/jobs", json=job_data)
    job_id = response.json()["job_id"]
    print(f"Job Created: {job_id}")
    
    # 3. WebSocket으로 진행율 수신
    result = asyncio.run(listen_job_progress(job_id))
    print(f"Job Result: {result}")
    
    # 4. 매칭된 제품 확인
    matched_products = result.get("result", {}).get("llm_analysis", {}).get("matched_products", [])
    print(f"Matched Products: {matched_products}")

if __name__ == "__main__":
    test_server()
```

---

## 문제 해결

### 서버 시작 실패

**문제**: `ModuleNotFoundError: No module named 'fastapi'`

**해결**:
```bash
pip install fastapi uvicorn
```

### 작업 생성 실패

**문제**: `422 Unprocessable Entity`

**해결**: 요청 본문이 올바른 JSON 형식인지 확인

### 동시성 제한 초과

**문제**: `429 Too Many Requests`

**해결**: `SKIN_API_MAX_CONCURRENT` 환경 변수 증가

---

## 참고 문서

- `config/config.json` - 서버 설정
- `src/server/server.py` - 서버 메인 파일
- `src/server/routers/` - 라우터 구현
- `docs/PRESCRIPTION_GUIDE.md` - 처방전 가이드
