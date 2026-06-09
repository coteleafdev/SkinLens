# 서버 테스트 가이드 (Server Test Guide)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

## 개요

SkinLens 서버는 CLI 기반으로 작동하며, FastAPI를 통해 REST API를 제공합니다. 본 문서는 서버를 테스트하는 절차를 설명합니다.

---

## 서버 아키텍처

### 구조

```mermaid
graph TB
    subgraph "src/server/"
        Deps[deps.py<br/>공유 상태·의존성·유틸]
        Server[server.py<br/>app 생성·미들웨어·라우터 등록]
        
        subgraph "routers/"
            Jobs[jobs.py<br/>POST/GET /v1/analysis/jobs/*]
            Logs[logs.py<br/>GET /v1/logs/*]
            Stats[stats.py<br/>GET/POST /v1/stats/*]
            Auth[auth.py<br/>POST /v1/auth/login<br/>GET /v1/auth/me]
            Customer[customer.py<br/>GET/DELETE /v1/customer/my/*]
            Admin[admin.py<br/>GET /v1/admin/*<br/>GET /v1/health/db]
        end
    end
    
    Server --> Deps
    Server --> Jobs
    Server --> Logs
    Server --> Stats
    Server --> Auth
    Server --> Customer
    Server --> Admin
```

### 주요 라우터

| 라우터 | 경로 | 설명 |
|--------|------|------|
| jobs | `/v1/analysis/jobs/*` | 분석 작업 생성, 조회, 취소 |
| logs | `/v1/logs/*` | 로그 조회 |
| stats | `/v1/stats/*` | 통계 조회 |
| auth | `/v1/auth/*` | 인증 (로그인, 사용자 정보) |
| customer | `/v1/customer/my/*` | 고객 데이터 관리 |
| admin | `/v1/admin/*` | 관리자 기능, 헬스체크 |

---

## 테스트 절차

### 1. 서버 시작

```mermaid
graph LR
    Start[시작] --> Env[환경 설정]
    Env --> Server[서버 실행]
    Server --> Health[헬스체크]
    Health --> Success[성공]
    Health --> Fail[실패]
    Fail --> Error[에러 확인]
    Error --> Server
```

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
curl http://localhost:8000/v1/health/db

# 예상 응답
{
  "status": "healthy",
  "db_connection": "ok"
}
```

---

### 2. 분석 작업 테스트

```mermaid
sequenceDiagram
    participant C as 클라이언트
    participant S as 서버
    
    C->>S: POST /v1/analysis/jobs
    S-->>C: job_id, status
    
    C->>S: GET /v1/analysis/jobs/{job_id}
    S-->>C: status, progress
    
    loop 진행율 확인
        C->>S: GET /v1/analysis/jobs/{job_id}
        S-->>C: status, progress
    end
    
    S-->>C: status: completed
    C->>S: GET /v1/analysis/jobs/{job_id}
    S-->>C: result
    
    Note over C,S: WebSocket으로 진행율 실시간 수신 가능
```

#### 2.1 작업 생성 (POST /v1/analysis/jobs)

```bash
curl -X POST http://localhost:8000/v1/analysis/jobs \
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

#### 2.2 작업 상태 조회 (GET /v1/analysis/jobs/{job_id})

```bash
curl http://localhost:8000/v1/analysis/jobs/job_abc123
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

#### 2.3 작업 취소 (DELETE /v1/analysis/jobs/{job_id})

```bash
curl -X DELETE http://localhost:8000/v1/analysis/jobs/job_abc123
```

---

### 3. 인증 테스트

```mermaid
sequenceDiagram
    participant C as 클라이언트
    participant S as 서버
    
    C->>S: POST /v1/auth/login<br/>{username, password}
    S-->>C: access_token, token_type
    
    C->>S: GET /v1/auth/me<br/>Authorization: Bearer {token}
    S-->>C: user_info
```

#### 3.1 로그인 (POST /v1/auth/login)

```bash
curl -X POST http://localhost:8000/v1/auth/login \
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

#### 3.2 사용자 정보 조회 (GET /v1/auth/me)

```bash
curl http://localhost:8000/v1/auth/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### 4. 제품 매칭 테스트

```mermaid
graph LR
    Input[설문 JSON 준비] --> Upload[작업 생성 시 포함]
    Upload --> Match[제품 매칭]
    Match --> Result[매칭된 제품 확인]
    
    subgraph "매칭 로직"
        Prescription[처방 항목 50%]
        Concerns[고민사항 30%]
        SkinType[피부 타입 20%]
    end
    
    Match --> Prescription
    Match --> Concerns
    Match --> SkinType
```

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
curl -X POST http://localhost:8000/v1/analysis/jobs \
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
      "match_reason": "처방 항목 매칭: M10 (2.5%), 고민사항 매칭: 여드름, 피부 타입 매칭: oily"
    }
  ]
}
```

---

### 5. 주문 관리 테스트

```mermaid
sequenceDiagram
    participant C as 클라이언트
    participant S as 서버
    
    C->>S: POST /v1/orders (주문 생성)
    S-->>C: order_id, payment_url
    
    C->>S: GET /v1/orders/{order_id} (상태 조회)
    S-->>C: order status
    
    alt 주문 취소
        C->>S: POST /v1/orders/{order_id}/cancel
        S-->>C: cancelled, refund_status
    end
    
    C->>S: GET /v1/orders/customers/{customer_id}/purchase-history
    S-->>C: purchase history
```

#### 5.1 주문 생성 (POST /v1/orders)

```bash
curl -X POST http://localhost:8000/v1/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "user123",
    "items": [
      {
        "product_id": "P001",
        "quantity": 1,
        "price": 45000
      },
      {
        "product_id": "P002",
        "quantity": 2,
        "price": 35000
      }
    ],
    "shipping_address": {
      "recipient": "홍길동",
      "phone": "010-1234-5678",
      "address": "서울시 강남구...",
      "zip_code": "12345"
    },
    "payment_method": "credit_card",
    "recommendation_source": "skin_analysis",
    "analysis_job_id": "job_abc123"
  }'
```

**응답 예시**:
```json
{
  "order_id": "ORD-20260528-001",
  "status": "pending_payment",
  "total_amount": 115000,
  "created_at": "2026-05-28T10:00:00Z",
  "payment_url": "https://payment.example.com/pay/ORD-20260528-001"
}
```

#### 5.2 주문 상태 조회 (GET /v1/orders/{order_id})

```bash
curl http://localhost:8000/v1/orders/ORD-20260528-001
```

**응답 예시**:
```json
{
  "order_id": "ORD-20260528-001",
  "status": "paid",
  "total_amount": 115000,
  "items": [
    {
      "product_id": "P001",
      "product_name": "Product P001",
      "quantity": 1,
      "price": 45000,
      "subtotal": 45000
    }
  ],
  "shipping_address": {
    "recipient": "홍길동",
    "phone": "010-1234-5678",
    "address": "서울시 강남구...",
    "zip_code": "12345"
  },
  "payment_status": "paid",
  "shipping_status": "preparing",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:05:00Z"
}
```

#### 5.3 주문 취소 (POST /v1/orders/{order_id}/cancel)

```bash
curl -X POST http://localhost:8000/v1/orders/ORD-20260528-001/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "상품 변경"
  }'
```

**응답 예시**:
```json
{
  "order_id": "ORD-20260528-001",
  "status": "cancelled",
  "cancelled_at": "2026-05-28T11:00:00Z",
  "refund_amount": 115000,
  "refund_status": "processing"
}
```

#### 5.4 고객 구매 이력 조회 (GET /v1/orders/customers/{customer_id}/purchase-history)

```bash
curl "http://localhost:8000/v1/orders/customers/user123/purchase-history?limit=10&offset=0"
```

**응답 예시**:
```json
{
  "customer_id": "user123",
  "total_orders": 5,
  "total_spent": 575000,
  "orders": [
    {
      "order_id": "ORD-20260528-001",
      "status": "delivered",
      "total_amount": 115000,
      "items": [
        {
          "product_id": "P001",
          "product_name": "Product P001",
          "quantity": 1,
          "price": 45000,
          "subtotal": 45000
        }
      ],
      "purchased_at": "2026-05-28T10:00:00Z",
      "recommendation_source": "skin_analysis",
      "analysis_job_id": "job_abc123"
    }
  ]
}
```

---

### 6. 동시 요청 테스트

#### 6.1 여러 작업 동시 생성

```bash
# Bash 스크립트로 여러 요청 동시 전송
for i in {1..5}; do
  curl -X POST http://localhost:8000/v1/analysis/jobs \
    -H "Content-Type: application/json" \
    -d "{\"input_image\": \"path/to/image_$i.jpg\"}" &
done
wait
```

#### 6.2 동시성 제한 확인

```bash
# 활성 작업 수 조회
curl http://localhost:8000/v1/stats/active-jobs
```

**응답 예시**:
```json
{
  "active_jobs": 3,
  "max_concurrent": 4
}
```

---

### 7. 진행율 실시간 수신 (WebSocket)

#### 7.1 WebSocket 연결

```bash
# wscat 사용 (설치 필요: npm install -g wscat)
wscat -c ws://localhost:8000/v1/ws/jobs/job_abc123
```

#### 7.2 진행율 메시지 수신

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

#### 7.3 Python WebSocket 클라이언트

```python
import asyncio
import websockets
import json

async def listen_job_progress(job_id):
    uri = f"ws://localhost:8000/v1/ws/jobs/{job_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Progress: {data['progress']}% - {data['message']}")
            
            if data['status'] in ['completed', 'failed']:
                break

asyncio.run(listen_job_progress("job_abc123"))
```

#### 7.4 JavaScript WebSocket 클라이언트

```javascript
const ws = new WebSocket('ws://localhost:8000/v1/ws/jobs/job_abc123');

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

#### 7.5 Flutter WebSocket 클라이언트

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
    final uri = Uri.parse('$baseUrl/v1/ws/jobs/$jobId');
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

### 8. 로그 및 통계 테스트

#### 8.1 로그 조회 (GET /v1/logs)

```bash
curl http://localhost:8000/v1/logs?limit=10
```

#### 8.2 통계 조회 (GET /v1/stats)

```bash
curl http://localhost:8000/v1/stats
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
    uri = f"ws://localhost:8000/v1/ws/jobs/{job_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Progress: {data['progress']}% - {data['message']}")
            
            if data['status'] in ['completed', 'failed']:
                return data

def test_server():
    # 1. 헬스체크
    response = requests.get(f"{BASE_URL}/v1/health/db")
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
    response = requests.post(f"{BASE_URL}/v1/analysis/jobs", json=job_data)
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

## 9. 성능 테스트

### 9.1 부하 테스트 (Apache Bench)

```bash
# Apache Bench 설치
# Ubuntu/Debian: sudo apt-get install apache2-utils
# macOS: brew install httpd

# 100개 요청, 동시 10개
ab -n 100 -c 10 http://localhost:8000/v1/health/db

# POST 요청 테스트 (JSON 파일 사용)
ab -n 50 -c 5 -p request.json -T application/json http://localhost:8000/v1/analysis/jobs
```

### 9.2 부하 테스트 (k6)

```javascript
// load_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '30s', target: 10 },  // 30초 동안 10명까지 증가
    { duration: '1m', target: 10 },   // 1분 동안 10명 유지
    { duration: '30s', target: 0 },   // 30초 동안 0명으로 감소
  ],
};

export default function () {
  let response = http.get('http://localhost:8000/v1/health/db');
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
  sleep(1);
}
```

```bash
# k6 설치
# macOS: brew install k6
# Ubuntu: https://k6.io/docs/getting-started/installation

# 테스트 실행
k6 run load_test.js
```

### 9.3 부하 테스트 (Locust)

```python
# locustfile.py
from locust import HttpUser, task, between

class SkinAnalysisUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def health_check(self):
        self.client.get("/v1/health/db")
    
    @task(3)
    def create_job(self):
        self.client.post("/v1/analysis/jobs", json={
            "input_image": "test.jpg",
            "llm_scores": True
        })
```

```bash
# Locust 설치
pip install locust

# 테스트 실행 (웹 UI)
locust -f locustfile.py --host=http://localhost:8000
```

### 9.4 응답 시간 측정

```bash
# curl로 응답 시간 측정
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/v1/health/db

# curl-format.txt
time_namelookup:  %{time_namelookup}\n
time_connect:     %{time_connect}\n
time_appconnect:  %{time_appconnect}\n
time_pretransfer: %{time_pretransfer}\n
time_starttransfer: %{time_starttransfer}\n
time_total:       %{time_total}\n
```

### 9.5 메모리/CPU 사용량 모니터링

```bash
# htop 설치
# Ubuntu/Debian: sudo apt-get install htop
# macOS: brew install htop

# htop 실행
htop

# 또는 psutil 사용
pip install psutil

# Python 스크립트로 모니터링
import psutil
import time

while True:
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    print(f"CPU: {cpu}%, Memory: {memory}%")
    time.sleep(1)
```

---

## 10. 보안 테스트

### 10.1 인증/인가 테스트

```bash
# 1. 로그인 후 토큰 받기
TOKEN=$(curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}' \
  | jq -r '.access_token')

# 2. 토큰 없이 요청 (401 예상)
curl http://localhost:8000/v1/auth/me

# 3. 토큰으로 요청 (200 예상)
curl http://localhost:8000/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"

# 4. 만료된 토큰으로 요청 (401 예상)
curl http://localhost:8000/v1/auth/me \
  -H "Authorization: Bearer invalid_token"
```

### 10.2 권한 테스트

```bash
# 관리자 전용 엔드포인트 테스트
curl http://localhost:8000/v1/admin/users \
  -H "Authorization: Bearer $USER_TOKEN"  # 403 예상

curl http://localhost:8000/v1/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN"  # 200 예상
```

### 10.3 SQL 인젝션 방지 테스트

```bash
# SQL 인젝션 시도
curl -X POST http://localhost:8000/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input_image": "test.jpg",
    "customer_id": "admin'; DROP TABLE users; --"
  }'
```

### 10.4 XSS 방지 테스트

```bash
# XSS 시도
curl -X POST http://localhost:8000/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input_image": "test.jpg",
    "customer_id": "<script>alert(1)</script>"
  }'
```

### 10.5 Rate Limiting 테스트

```bash
# Rate Limit 테스트 (3회/분 제한)
for i in {1..5}; do
  curl -X POST http://localhost:8000/v1/analysis/jobs \
    -H "Content-Type: application/json" \
    -d '{"input_image": "test.jpg"}'
  echo "---"
done
```

---

## 11. 에러 핸들링 테스트

### 11.1 잘못된 입력 데이터 테스트

```bash
# 1. 필수 필드 누락
curl -X POST http://localhost:8000/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{}'  # 422 예상

# 2. 잘못된 데이터 타입
curl -X POST http://localhost:8000/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{"input_image": 123}'  # 422 예상

# 3. 유효하지 않은 이미지 파일
curl -X POST http://localhost:8000/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{"input_image": "nonexistent.jpg"}'  # 404 예상
```

### 11.2 네트워크 오류 시나리오

```bash
# 1. 타임아웃 테스트
curl --max-time 1 http://localhost:8000/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{"input_image": "large_image.jpg"}'

# 2. 연결 끊김 시뮬레이션
# iptables 사용 (Linux)
sudo iptables -A INPUT -p tcp --dport 8000 -j DROP
# 테스트 후 복구
sudo iptables -D INPUT -p tcp --dport 8000 -j DROP
```

### 11.3 DB 연결 실패 테스트

```bash
# DB 파일 삭제 후 테스트
rm execution_history.db
curl http://localhost:8000/v1/health/db  # 500 예상

# DB 복구 후 테스트
# DB 파일이 자동 생성되어야 함
```

### 11.4 외부 API 실패 테스트

```bash
# LLM API 키 없이 테스트
unset GEMINI_API_KEY
curl -X POST http://localhost:8000/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{"input_image": "test.jpg", "llm_report": true}'  # 500 예상
```

---

## 12. 통합 테스트

### 12.1 전체 흐름 테스트

```mermaid
graph LR
    A[피부 분석] --> B[제품 추천]
    B --> C[주문 생성]
    C --> D[결제]
    D --> E[배송]
```

```python
# integration_test.py
import requests
import json
import asyncio
import websockets

BASE_URL = "http://localhost:8000"

async def test_full_flow():
    # 1. 피부 분석
    job_response = requests.post(f"{BASE_URL}/v1/analysis/jobs", json={
        "input_image": "test.jpg",
        "llm_scores": True,
        "input_json": {
            "survey": {
                "skin_concerns": ["여드름"],
                "skin_types": ["oily"]
            }
        }
    })
    job_id = job_response.json()["job_id"]
    
    # 2. 진행율 수신
    uri = f"ws://localhost:8000/v1/ws/jobs/{job_id}"
    async with websockets.connect(uri) as ws:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if data['status'] == 'completed':
                break
    
    # 3. 결과 확인
    result_response = requests.get(f"{BASE_URL}/v1/analysis/jobs/{job_id}")
    result = result_response.json()
    matched_products = result.get("result", {}).get("llm_analysis", {}).get("matched_products", [])
    
    # 4. 주문 생성
    if matched_products:
        order_response = requests.post(f"{BASE_URL}/v1/orders", json={
            "customer_id": "user123",
            "items": [
                {
                    "product_id": matched_products[0]["product_id"],
                    "quantity": 1,
                    "price": 45000
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구...",
                "zip_code": "12345"
            },
            "payment_method": "credit_card",
            "recommendation_source": "skin_analysis",
            "analysis_job_id": job_id
        })
        order_id = order_response.json()["order_id"]
        print(f"Order created: {order_id}")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
```

### 12.2 WebSocket 연결 유지 테스트

```python
# websocket_keepalive_test.py
import asyncio
import websockets
import json

async def test_websocket_keepalive():
    uri = "ws://localhost:8000/v1/ws/jobs/test_job"
    try:
        async with websockets.connect(uri) as ws:
            # 5분 동안 연결 유지
            for i in range(300):
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                data = json.loads(msg)
                print(f"Message {i}: {data['status']}")
                if data['status'] in ['completed', 'failed']:
                    break
    except asyncio.TimeoutError:
        print("WebSocket connection timeout")

if __name__ == "__main__":
    asyncio.run(test_websocket_keepalive())
```

---

## 13. 데이터 백업 및 복구 테스트

### 13.1 DB 백업 테스트

```bash
# SQLite 백업
cp execution_history.db execution_history.db.backup
cp results/skin_analysis.db results/skin_analysis.db.backup

# 백업 파일 확인
ls -lh *.backup
```

### 13.2 데이터 복구 테스트

```bash
# DB 삭제
rm execution_history.db

# 백업 복구
cp execution_history.db.backup execution_history.db

# 데이터 확인
curl http://localhost:8000/v1/stats
```

### 13.3 장애 복구 시나리오

```bash
# 1. DB 손상 시뮬레이션
echo "corrupted data" > execution_history.db

# 2. 서버 재시작
# 서버가 자동으로 복구 시도

# 3. 백업 복구
cp execution_history.db.backup execution_history.db
```

---

## 14. 모니터링 및 로깅 테스트

### 14.1 로그 레벨 테스트

```bash
# DEBUG 레벨 로그 확인
curl http://localhost:8000/v1/logs?level=DEBUG&limit=10

# ERROR 레벨 로그 확인
curl http://localhost:8000/v1/logs?level=ERROR&limit=10
```

### 14.2 메트릭 수집 테스트

```bash
# 활성 작업 수 확인
curl http://localhost:8000/v1/stats/active-jobs

# 시스템 헬스 확인
curl http://localhost:8000/v1/health/db
```

### 14.3 알림 시스템 테스트

```python
# alert_test.py
import requests

# 알림 테스트 엔드포인트 (실제 구현 필요)
response = requests.post("http://localhost:8000/v1/admin/test-alert", json={
    "type": "error",
    "message": "테스트 알림"
})
print(response.json())
```

---

## 15. 배포 테스트

### 15.1 Docker 컨테이너 테스트

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "src.server.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Docker 이미지 빌드
docker build -t skinlens-server .

# 컨테이너 실행
docker run -p 8000:8000 -e GEMINI_API_KEY=your_key skinlens-server

# 컨테이너 테스트
curl http://localhost:8000/v1/health/db
```

### 15.2 Kubernetes 배포 테스트

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: skinlens-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: skinlens
  template:
    metadata:
      labels:
        app: skinlens
    spec:
      containers:
      - name: server
        image: skinlens-server:latest
        ports:
        - containerPort: 8000
        env:
        - name: GEMINI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-secrets
              key: gemini-api-key
```

```bash
# Kubernetes 배포
kubectl apply -f k8s-deployment.yaml

# 배포 확인
kubectl get pods

# 서비스 테스트
kubectl port-forward svc/skinlens-server 8000:8000
curl http://localhost:8000/v1/health/db
```

### 15.3 CI/CD 파이프라인 테스트

```yaml
# .github/workflows/ci.yml
name: CI/CD

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.12
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    - name: Run tests
      run: |
        pytest tests/
    - name: Build Docker image
      run: |
        docker build -t skinlens-server .
```

---

## 16. 클라이언트별 테스트

### 16.1 Flutter 앱 통합 테스트

```dart
// integration_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

void main() {
  testWidgets('Flutter 앱 통합 테스트', (WidgetTester tester) async {
    // 앱 시작
    await tester.pumpWidget(MyApp());
    
    // 이미지 선택
    await tester.tap(find.text('이미지 선택'));
    await tester.pumpAndSettle();
    
    // 분석 시작
    await tester.tap(find.text('분석 시작'));
    await tester.pumpAndSettle();
    
    // 결과 확인
    expect(find.text('분석 완료'), findsOneWidget);
  });
}
```

### 16.2 웹 브라우저 테스트

```javascript
// browser_test.js (Playwright)
const { test, expect } = require('@playwright/test');

test('웹 브라우저 테스트', async ({ page }) => {
  await page.goto('http://localhost:8000/docs');
  
  // API 문서 로드 확인
  await expect(page.locator('h1')).toContainText('Skin Analysis API');
  
  // 헬스체크 테스트
  const response = await page.request.get('http://localhost:8000/v1/health/db');
  expect(response.status()).toBe(200);
});
```

### 16.3 CLI 도구 테스트

```bash
# CLI 테스트
python src/gui/skin_analysis_pipeline.py --cli -i test.jpg --out-dir ./test_output

# 결과 확인
ls -lh ./test_output
cat ./test_output/results.json
```

---

## 17. 문제 해결

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

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
