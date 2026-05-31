"""
routers/upload.py — 청크 업로드 및 파일 업로드 개선

기능:
- 청크 업로드 (대용량 파일)
- 업로드 일시정지/재개
- 업로드 진행률 추적

엔드포인트:
- POST /v1/upload/init - 업로드 세션 초기화
- POST /v1/upload/chunk - 청크 업로드
- POST /v1/upload/complete - 업로드 완료
- POST /v1/upload/cancel - 업로드 취소
- GET /v1/upload/progress/{session_id} - 업로드 진행률 조회
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from src.server.deps import get_current_customer, limiter, log, _safe_filename, validate_path_within_directory

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/upload", tags=["upload"])


# ── 업로드 세션 관리 ───────────────────────────────────────────────────────

@dataclass
class UploadSession:
    """업로드 세션 정보"""
    session_id: str
    file_name: str
    file_size: int
    chunk_size: int
    total_chunks: int
    uploaded_chunks: set[int] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    temp_dir: Optional[Path] = None
    file_hash: Optional[str] = None
    owner_customer_id: Optional[str] = None  # [FIX P0] 세션 소유권 검증용


# 전역 업로드 세션 저장소
_upload_sessions: Dict[str, UploadSession] = {}


def _validate_session_ownership(session: UploadSession, current_customer: Dict) -> None:
    """[FIX P0] 세션 소유권 검증"""
    if session.owner_customer_id is None:
        raise HTTPException(status_code=500, detail="Session has no owner")
    
    customer_id = current_customer.get("sub")
    if customer_id != session.owner_customer_id:
        # 관리자는 모든 세션에 접근 가능
        if current_customer.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied: not the session owner")


def _get_temp_dir() -> Path:
    """임시 디렉토리 경로 반환"""
    from src.server.deps import jobs_root
    temp_dir = jobs_root() / "temp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def _cleanup_session(session_id: str) -> None:
    """업로드 세션 정리"""
    if session_id in _upload_sessions:
        session = _upload_sessions[session_id]
        if session.temp_dir and session.temp_dir.exists():
            shutil.rmtree(session.temp_dir, ignore_errors=True)
        del _upload_sessions[session_id]
        log.info("업로드 세션 정리: session_id=%s", session_id)


# ── 업로드 엔드포인트 ─────────────────────────────────────────────────────

@router.post("/init")
async def init_upload(
    file_name: str,
    file_size: int,
    chunk_size: int = 5 * 1024 * 1024,  # 기본 5MB
    file_hash: Optional[str] = None,
    current_customer: Optional[Dict] = Depends(get_current_customer),
):
    """업로드 세션 초기화.

    Args:
        file_name: 파일 이름
        file_size: 파일 크기 (bytes)
        chunk_size: 청크 크기 (bytes, 기본 5MB)
        file_hash: 파일 해시 (SHA-256, 선택적)
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    # [FIX P0] 파일 이름 정제 (traversal 방지)
    safe_file_name = _safe_filename(file_name)
    if not safe_file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    # 파일 크기 검증
    from src.server.deps import MAX_UPLOAD_BYTES
    if file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size ({MAX_UPLOAD_BYTES} bytes)"
        )

    # 세션 ID 생성
    session_id = str(uuid.uuid4())

    # 임시 디렉토리 생성
    temp_dir = _get_temp_dir() / session_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 전체 청크 수 계산
    total_chunks = (file_size + chunk_size - 1) // chunk_size

    # 세션 생성
    session = UploadSession(
        session_id=session_id,
        file_name=safe_file_name,  # [FIX P0] 정제된 파일 이름 사용
        file_size=file_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        temp_dir=temp_dir,
        file_hash=file_hash,
        owner_customer_id=current_customer.get("sub"),  # [FIX P0] 소유자 저장
    )
    _upload_sessions[session_id] = session

    log.info(
        "업로드 세션 초기화: session_id=%s, file_name=%s, file_size=%d, chunks=%d",
        session_id, file_name, file_size, total_chunks
    )

    return {
        "session_id": session_id,
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
        "file_name": file_name,
        "file_size": file_size,
    }


@router.post("/chunk")
async def upload_chunk(
    session_id: str,
    chunk_number: int,
    chunk: UploadFile,
    current_customer: Optional[Dict] = Depends(get_current_customer),
):
    """청크 업로드.

    Args:
        session_id: 업로드 세션 ID
        chunk_number: 청크 번호 (0-based)
        chunk: 청크 데이터
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    # 세션 확인
    if session_id not in _upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found")

    session = _upload_sessions[session_id]
    
    # [FIX P0] 세션 소유권 검증
    _validate_session_ownership(session, current_customer)

    # 청크 번호 검증
    if chunk_number < 0 or chunk_number >= session.total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk number")

    # 이미 업로드된 청크 확인
    if chunk_number in session.uploaded_chunks:
        log.info("이미 업로드된 청크: session_id=%s, chunk_number=%d", session_id, chunk_number)
        return {"status": "already_uploaded", "chunk_number": chunk_number}

    # 청크 저장
    chunk_path = session.temp_dir / f"chunk_{chunk_number}"
    try:
        with open(chunk_path, "wb") as f:
            shutil.copyfileobj(chunk.file, f)
        session.uploaded_chunks.add(chunk_number)
        log.info(
            "청크 업로드 완료: session_id=%s, chunk_number=%d, progress=%d/%d",
            session_id, chunk_number, len(session.uploaded_chunks), session.total_chunks
        )
    except Exception as e:
        log.error("청크 업로드 실패: session_id=%s, chunk_number=%d, error=%s", session_id, chunk_number, e)
        raise HTTPException(status_code=500, detail=f"Failed to upload chunk: {str(e)}")

    return {
        "status": "uploaded",
        "chunk_number": chunk_number,
        "uploaded_chunks": len(session.uploaded_chunks),
        "total_chunks": session.total_chunks,
    }


@router.post("/complete")
async def complete_upload(
    session_id: str,
    current_customer: Optional[Dict] = Depends(get_current_customer),
):
    """업로드 완료 및 파일 합치기.

    Args:
        session_id: 업로드 세션 ID
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    # 세션 확인
    if session_id not in _upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found")

    session = _upload_sessions[session_id]
    
    # [FIX P0] 세션 소유권 검증
    _validate_session_ownership(session, current_customer)

    # 모든 청크 업로드 확인
    if len(session.uploaded_chunks) != session.total_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"Not all chunks uploaded ({len(session.uploaded_chunks)}/{session.total_chunks})"
        )

    # 파일 합치기
    output_path = session.temp_dir / session.file_name
    try:
        with open(output_path, "wb") as outfile:
            for i in range(session.total_chunks):
                chunk_path = session.temp_dir / f"chunk_{i}"
                with open(chunk_path, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)

        # 파일 해시 검증 (제공된 경우)
        if session.file_hash:
            sha256_hash = hashlib.sha256()
            with open(output_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            calculated_hash = sha256_hash.hexdigest()
            if calculated_hash != session.file_hash:
                raise HTTPException(
                    status_code=400,
                    detail=f"File hash mismatch (expected: {session.file_hash}, calculated: {calculated_hash})"
                )

        log.info("업로드 완료: session_id=%s, file_name=%s, file_size=%d", session_id, session.file_name, session.file_size)

        # 최종 파일 경로 반환 (jobs 디렉토리로 이동)
        from src.server.deps import jobs_root
        final_path = jobs_root() / session.file_name
        
        # [FIX P0] 경로 traversal 방지
        validate_path_within_directory(final_path, jobs_root())
        
        shutil.move(str(output_path), str(final_path))

        # 세션 정리
        _cleanup_session(session_id)

        return {
            "status": "completed",
            "file_name": session.file_name,
            "file_size": session.file_size,
            "file_path": str(final_path),
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error("업로드 완료 실패: session_id=%s, error=%s", session_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to complete upload: {str(e)}")


@router.post("/cancel")
async def cancel_upload(
    session_id: str,
    current_customer: Optional[Dict] = Depends(get_current_customer),
):
    """업로드 취소.

    Args:
        session_id: 업로드 세션 ID
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    # 세션 확인
    if session_id not in _upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found")

    session = _upload_sessions[session_id]
    
    # [FIX P0] 세션 소유권 검증
    _validate_session_ownership(session, current_customer)

    log.info("업로드 취소: session_id=%s", session_id)

    # 세션 정리
    _cleanup_session(session_id)

    return {"status": "cancelled", "session_id": session_id}


@router.get("/progress/{session_id}")
async def get_upload_progress(
    session_id: str,
    current_customer: Optional[Dict] = Depends(get_current_customer),
):
    """업로드 진행률 조회.

    Args:
        session_id: 업로드 세션 ID
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    # 세션 확인
    if session_id not in _upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found")

    session = _upload_sessions[session_id]
    
    # [FIX P0] 세션 소유권 검증
    _validate_session_ownership(session, current_customer)

    progress_percent = (len(session.uploaded_chunks) / session.total_chunks) * 100

    return {
        "session_id": session_id,
        "file_name": session.file_name,
        "file_size": session.file_size,
        "uploaded_chunks": len(session.uploaded_chunks),
        "total_chunks": session.total_chunks,
        "progress_percent": round(progress_percent, 2),
        "created_at": session.created_at.isoformat(),
    }
