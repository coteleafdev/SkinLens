# -*- coding: utf-8 -*-
"""
routers/websocket.py — WebSocket 진행률 트래킹

WebSocket 엔드포인트:
    WS /v3/ws/analyze/{job_id} — 작업 진행률 실시간 전송

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

router = APIRouter(prefix="/v3/ws", tags=["websocket"])


# ── WebSocket 연결 관리자 ─────────────────────────────────────────────────

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
        except Exception as e:
            log.warning(f"Failed to send progress message: {e}", exc_info=True)


# ── WebSocket 엔드포인트 ─────────────────────────────────────────────────────

@router.websocket("/analyze/{job_id}")
async def websocket_analyze(websocket: WebSocket, job_id: str) -> None:
    """작업 진행률 실시간 수신 WebSocket.
    
    클라이언트 연결 예시 (JavaScript):
        const ws = new WebSocket(`ws://server/v3/ws/analyze/${jobId}`);
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
            except Exception as e:
                log.warning("WebSocket 수신 오류: job_id=%s, error=%s", job_id, e)
                break
                
    except WebSocketDisconnect:
        log.info("WebSocket 연결 종료: job_id=%s", job_id)
    except Exception as e:
        log.error("WebSocket 오류: job_id=%s, error=%s", job_id, e)
    finally:
        manager.disconnect(job_id)
