# -*- coding: utf-8 -*-
"""
routers/websocket.py — WebSocket 진행률 트래킹

WebSocket 엔드포인트:
    WS /v1/ws/analyze/{job_id} — 작업 진행률 실시간 전송

메시지 형식:
    {"type": "progress", "stage": "restore", "percent": 30, "message": "복원 중..."}
    {"type": "complete", "result": {...}}
    {"type": "error", "error": "에러 메시지"}
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.server.deps import job_dir, read_job_meta, log
from src.utils.config import load_config as _load_config

router = APIRouter(prefix="/v1/ws", tags=["websocket"])


# ── WebSocket 연결 관리자 ─────────────────────────────────────────────────

# config.json에서 WebSocket 설정 로드
_config = _load_config()
_server_config = _config.get("server", {})
_websocket_config = _server_config.get("websocket", {})
_max_connections = _websocket_config.get("max_connections", 100)
_connection_timeout = _websocket_config.get("connection_timeout", 300)


class ConnectionManager:
    """WebSocket 연결 관리자 (연결 수 제한, 타임아웃, 하트비트 포함)."""

    def __init__(self, max_connections: int = _max_connections, connection_timeout: int = _connection_timeout) -> None:
        """
        Args:
            max_connections: 최대 동시 연결 수
            connection_timeout: 연결 타임아웃 (초)
        """
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict] = {}  # 연결 메타데이터
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self._monitor_task: Optional[asyncio.Task] = None

    async def connect(self, job_id: str, websocket: WebSocket) -> bool:
        """작업 ID에 WebSocket 연결 등록.

        Returns:
            연결 성공 여부 (연결 수 초과 시 False)
        """
        # 연결 수 제한 확인
        if len(self.active_connections) >= self.max_connections:
            log.warning("WebSocket 연결 거부: 최대 연결 수 초과 (job_id=%s, 현재=%d, 최대=%d)",
                       job_id, len(self.active_connections), self.max_connections)
            await websocket.close(code=1008, reason="Maximum connections exceeded")
            return False

        await websocket.accept()
        self.active_connections[job_id] = websocket
        self.connection_metadata[job_id] = {
            "connected_at": asyncio.get_event_loop().time(),
            "last_heartbeat": asyncio.get_event_loop().time(),
            "client_ip": websocket.client.host if websocket.client else "unknown",
        }
        log.info("WebSocket 연결: job_id=%s, 연결 수=%d, IP=%s",
                 job_id, len(self.active_connections), self.connection_metadata[job_id]["client_ip"])

        # 모니터링 태스크 시작 (이미 실행 중이면 스킵)
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_connections())

        return True

    def disconnect(self, job_id: str) -> None:
        """작업 ID 연결 해제."""
        if job_id in self.active_connections:
            del self.active_connections[job_id]
        if job_id in self.connection_metadata:
            del self.connection_metadata[job_id]
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
                # 하트비트 갱신
                if job_id in self.connection_metadata:
                    self.connection_metadata[job_id]["last_heartbeat"] = asyncio.get_event_loop().time()
            except (RuntimeError, ConnectionError, ValueError) as e:  # [FIX P2] 구체적 예외
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
            except (RuntimeError, ConnectionError, ValueError) as e:  # [FIX P2] 구체적 예외
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
            except (RuntimeError, ConnectionError, ValueError) as e:  # [FIX P2] 구체적 예외
                log.warning("WebSocket 에러 전송 실패: job_id=%s, error=%s", job_id, e)
            finally:
                self.disconnect(job_id)

    async def _monitor_connections(self) -> None:
        """연결 상태 모니터링 (타임아웃 감지)."""
        while True:
            await asyncio.sleep(30)  # 30초마다 확인
            current_time = asyncio.get_event_loop().time()
            timeout_connections = []

            for job_id, metadata in self.connection_metadata.items():
                # 타임아웃 확인
                if current_time - metadata["last_heartbeat"] > self.connection_timeout:
                    timeout_connections.append(job_id)
                    log.warning("WebSocket 타임아웃: job_id=%s, IP=%s",
                               job_id, metadata["client_ip"])

            # 타임아웃 연결 종료
            for job_id in timeout_connections:
                if job_id in self.active_connections:
                    try:
                        await self.active_connections[job_id].close(code=1000, reason="Connection timeout")
                    except (RuntimeError, ConnectionError) as e:  # [FIX P2] 구체적 예외
                        log.error("WebSocket 타임아웃 종료 실패: job_id=%s, error=%s", job_id, e)
                    self.disconnect(job_id)

    def get_connection_stats(self) -> Dict:
        """연결 통계 반환."""
        return {
            "active_connections": len(self.active_connections),
            "max_connections": self.max_connections,
            "connection_timeout": self.connection_timeout,
            "connections": [
                {
                    "job_id": job_id,
                    "connected_at": metadata["connected_at"],
                    "last_heartbeat": metadata["last_heartbeat"],
                    "client_ip": metadata["client_ip"],
                }
                for job_id, metadata in self.connection_metadata.items()
            ]
        }


# 전역 연결 관리자
manager = ConnectionManager()


# ── 진행률 콜백 함수 (파이프라인에서 호출) ───────────────────────────────────

_progress_callbacks: Dict[str, asyncio.Queue] = {}


def register_progress_callback(job_id: str) -> asyncio.Queue:
    """작업 ID에 진행률 콜백 큐 등록."""
    queue = asyncio.Queue()
    _progress_callbacks[job_id] = queue
    return queue


def unregister_progress_callback(job_id: str) -> None:
    """작업 ID 진행률 콜백 큐 해제."""
    if job_id in _progress_callbacks:
        del _progress_callbacks[job_id]


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
        except (RuntimeError, ConnectionError, ValueError) as e:  # [FIX P2] 구체적 예외
            log.warning(f"Failed to send progress message: {e}", exc_info=True)


# ── WebSocket 엔드포인트 ─────────────────────────────────────────────────────

@router.websocket("/analyze/{job_id}")
async def websocket_analyze(websocket: WebSocket, job_id: str) -> None:
    """작업 진행률 실시간 수신 WebSocket.
    
    클라이언트 연결 예시 (JavaScript):
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
    """
    await manager.connect(job_id, websocket)
    
    try:
        # 작업 상태 확인 및 전송
        meta = read_job_meta(job_id)
        status = meta.get("status", "unknown")
        
        if status == "pending":
            await websocket.send_json({
                "type": "status",
                "status": "pending",
                "message": "작업 대기 중..."
            })
        elif status == "running":
            await websocket.send_json({
                "type": "status",
                "status": "running",
                "message": "작업 진행 중..."
            })
        elif status == "succeeded":
            await websocket.send_json({
                "type": "complete",
                "result": meta.get("artifacts", {})
            })
            return
        elif status == "failed":
            await websocket.send_json({
                "type": "error",
                "error": meta.get("error", "알 수 없는 오류")
            })
            return
        
        # 연결 유지 (클라이언트가 연결을 끊을 때까지 대기)
        while True:
            try:
                # 핑/퐁으로 연결 유지
                await websocket.receive_text()
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
            except (RuntimeError, ConnectionError) as e:  # [FIX P2] 구체적 예외
                log.warning("WebSocket 수신 오류: job_id=%s, error=%s", job_id, e)
                break
                
    except WebSocketDisconnect:
        log.info("WebSocket 연결 종료: job_id=%s", job_id)
    except (RuntimeError, ConnectionError) as e:  # [FIX P2] 구체적 예외
        log.error("WebSocket 오류: job_id=%s, error=%s", job_id, e)
    finally:
        manager.disconnect(job_id)
