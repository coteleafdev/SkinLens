# WebSocket 진행률 전송 설계 (WebSocket Progress Design)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

---

## 개요

SkinLens v1.0에서 스마트폰 앱에 피부 분석 진행률을 실시간으로 전송하기 위해 WebSocket을 사용합니다.

## 아키텍처

```
스마트폰 앱 ←→ WebSocket ←→ FastAPI Server ←→ Pipeline ←→ report_progress()
```

## WebSocket 연결

### 엔드포인트

`WS /v1/ws/analyze/{job_id}`

### 클라이언트 연결 예시 (JavaScript)

```javascript
const ws = new WebSocket(`ws://server/v1/ws/analyze/${jobId}`);
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'progress') {
        updateProgressBar(data.percent, data.message);
    } else if (data.type === 'complete') {
        showResult(data.result);
    } else if (data.type === 'error') {
        showError(data.error);
    }
};
```

## 연결 관리자 (ConnectionManager)

### 역할

WebSocket 연결을 job_id별로 관리합니다.

### 구현

```python
class ConnectionManager:
    """WebSocket 연결 관리자."""

    def __init__(self) -> None:
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        """작업 ID에 WebSocket 연결 등록."""
        await websocket.accept()
        self.active_connections[job_id] = websocket
        log.info("WebSocket 연결: job_id=%s, 연결 수=%d", job_id, len(self.active_connections))

    def disconnect(self, job_id: str) -> None:
        """작업 ID 연결 해제."""
        if job_id in self.active_connections:
            del self.active_connections[job_id]
            log.info("WebSocket 연결 해제: job_id=%s, 연결 수=%d", job_id, len(self.active_connections))

    async def send_progress(self, job_id: str, stage: str, percent: int, message: str) -> None:
        """진행률 메시지 전송."""
        if job_id in self.active_connections:
            websocket = self.active_connections[job_id]
            try:
                await websocket.send_json({
                    "type": "progress",
                    "stage": stage,
                    "percent": percent,
                    "message": message
                })
            except Exception as e:
                log.warning("WebSocket 진행률 전송 실패: job_id=%s, error=%s", job_id, e)
                self.disconnect(job_id)

    async def send_complete(self, job_id: str, result: Dict) -> None:
        """완료 메시지 전송."""
        if job_id in self.active_connections:
            websocket = self.active_connections[job_id]
            try:
                await websocket.send_json({
                    "type": "complete",
                    "result": result
                })
            except Exception as e:
                log.warning("WebSocket 완료 전송 실패: job_id=%s, error=%s", job_id, e)
            finally:
                self.disconnect(job_id)

    async def send_error(self, job_id: str, error: str) -> None:
        """에러 메시지 전송."""
        if job_id in self.active_connections:
            websocket = self.active_connections[job_id]
            try:
                await websocket.send_json({
                    "type": "error",
                    "error": error
                })
            except Exception as e:
                log.warning("WebSocket 에러 전송 실패: job_id=%s, error=%s", job_id, e)
            finally:
                self.disconnect(job_id)
```

## 진행률 보고 함수 (report_progress)

### 역할

파이프라인에서 호출되어 WebSocket으로 진행률 전송합니다.

### 구현

```python
async def report_progress(job_id: str, stage: str, percent: int, message: str) -> None:
    """진행률 보고 (파이프라인에서 호출)."""
    # WebSocket으로 전송
    await manager.send_progress(job_id, stage, percent, message)
    
    # 콜백 큐에도 전송 (다른 컴포넌트에서 활용 가능)
    if job_id in _progress_callbacks:
        try:
            await _progress_callbacks[job_id].put({
                "stage": stage,
                "percent": percent,
                "message": message
            })
        except Exception as e:
            logger.warning(f"Failed to send progress message: {e}", exc_info=True)
```

## 파이프라인에서의 진행률 보고

### jobs.py에서의 호출 순서

```python
# 작업 시작
await report_progress(job_id, "init", 0, "작업 시작 중...")

# 이미지 복원 단계
if meta.get("do_restore", True):
    await report_progress(job_id, "restore", 10, "이미지 복원 중...")

# 피부 분석 단계
await report_progress(job_id, "analysis", 30, "피부 분석 중...")

# 결과 처리 단계
await report_progress(job_id, "processing", 80, "결과 처리 중...")

# 작업 완료
await report_progress(job_id, "complete", 100, "작업 완료")
```

## 메시지 형식

### 진행률 메시지

```json
{
  "type": "progress",
  "stage": "analysis",
  "percent": 30,
  "message": "피부 분석 중..."
}
```

### 완료 메시지

```json
{
  "type": "complete",
  "result": {...}
}
```

### 에러 메시지

```json
{
  "type": "error",
  "error": "에러 메시지"
}
```

## 진행률 단계

| 단계 | 퍼센트 | 메시지 |
|------|--------|--------|
| init | 0% | 작업 시작 중... |
| restore | 10% | 이미지 복원 중... |
| analysis | 30% | 피부 분석 중... |
| processing | 80% | 결과 처리 중... |
| complete | 100% | 작업 완료 |

## 전체 흐름

1. 스마트폰 앱이 WebSocket 연결 (`/v1/ws/analyze/{job_id}`)
2. 서버가 연결 수락 및 job_id로 연결 관리
3. 파이프라인 실행 중 `report_progress()` 호출
4. WebSocket으로 진행률 메시지 전송
5. 스마트폰 앱이 메시지 수신 및 UI 업데이트
6. 작업 완료 시 complete 메시지 전송
7. 연결 종료

## 특징

- **실시간 전송**: WebSocket을 통해 실시간으로 진행률 전송
- **비동기 처리**: asyncio를 사용하여 비동기적으로 메시지 전송
- **연결 관리**: job_id별로 연결을 관리하여 여러 클라이언트 지원
- **에러 처리**: 연결 실패 시 자동으로 연결 해제
- **콜백 큐**: 다른 컴포넌트에서도 진행률을 활용할 수 있도록 콜백 큐 제공

## 사용처

- **src/server/routers/websocket.py**: WebSocket 엔드포인트 및 연결 관리
- **src/server/routers/jobs.py**: 파이프라인에서 진행률 보고 호출
- **스마트폰 앱**: 진행률 수신 및 UI 업데이트

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
| 0.1.0 | 2026-05-24 | WebSocket 진행률 전송 설계 문서 초기 작성 | Cascade |
