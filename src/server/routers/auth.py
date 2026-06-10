"""
routers/auth.py — 인증 엔드포인트

POST /v1/auth/login
POST /v1/auth/refresh
POST /v1/auth/logout
POST /v1/auth/change-password
POST /v1/auth/forgot-password
POST /v1/auth/reset-password
GET  /v1/auth/me
"""
from __future__ import annotations

import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, Form, Request
from pydantic import BaseModel

from src.db.skin_analysis_db import SkinAnalysisDB
from src.utils.config import load_config
from src.server.deps import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    get_current_customer,
    get_refresh_token_expire_days,
    limiter,
    log,
    log_audit,
    pwd_context,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    username: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── 의존성 ───────────────────────────────────────────────────────────────────

def get_auth_db():
    """SkinAnalysisDB 인스턴스 반환 (인증용)"""
    # 테스트 환경에서는 환경변수 우선
    import os
    db_path = os.environ.get("SKIN_ANALYSIS_DB")
    if not db_path:
        config = load_config()
        db_path = config.get("database", {}).get("skin_analysis_db", {}).get("path", "data/skin_analysis.db")
    return SkinAnalysisDB(db_path=db_path)


def _verify_pw(plain: str, stored: str) -> bool:
    """bcrypt 해시($2b$...)면 verify, 아니면 상수 시간 비교."""
    if stored.startswith("$2"):
        return pwd_context.verify(plain, stored)
    return hmac.compare_digest(plain.encode(), stored.encode())


def _verify_pw_env(plain: str, stored: str) -> bool:
    """환경변수 기반 인증용 비밀번호 검증 (단순 비교)"""
    return hmac.compare_digest(plain.encode(), stored.encode())


def check_customer_access(current_customer: Dict[str, Any], target_customer_id: str) -> None:
    """JWT sub 클레임이 요청 customer_id와 일치하는지 검증.
    
    [FIX 2026-05-24] 최소 임시 조치 - customer 데이터 격리.
    admin만 다른 customer 데이터 접근 허용.
    """
    if current_customer.get("role") == "admin":
        return  # admin은 모든 데이터 접근 가능
    
    if current_customer.get("sub") != target_customer_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden: customer data access denied")


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    request: Request = None,
):
    """로그인 및 JWT 토큰 발급.

    [FIX P1] DB 기반 사용자 인증으로 전환
    - users 테이블에서 사용자 조회
    - bcrypt로 비밀번호 해시 검증
    - 환경변수 기반 인증은 폴백으로 유지 (마이그레이션 기간)
    """
    # [FIX P1] DB 기반 인증 시도
    db = get_auth_db()
    user = db.get_user_by_username(username)
    
    if user:
        # DB 사용자 인증
        if not _verify_pw(password, user["password_hash"]):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        user_role = user["role"]
        customer_id = user.get("customer_id") or username
        
        log.info("[AUTH] DB 사용자 로그인 성공: username=%s, role=%s", username, user_role)
    else:
        # [폴백] 환경변수 기반 인증 (마이그레이션 기간)
        ADMIN_PASSWORD    = os.environ.get("ADMIN_PASSWORD", "")
        ANALYST_PASSWORD  = os.environ.get("ANALYST_PASSWORD", "")
        CUSTOMER_PASSWORD = os.environ.get("CUSTOMER_PASSWORD", "")

        if not ADMIN_PASSWORD or not ANALYST_PASSWORD:
            log.warning(
                "ADMIN_PASSWORD / ANALYST_PASSWORD 환경변수가 설정되지 않았습니다. "
                "프로덕션 환경에서는 반드시 설정해야 합니다."
            )
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Authentication not configured")

        if username.startswith("admin"):
            if not ADMIN_PASSWORD or not _verify_pw_env(password, ADMIN_PASSWORD):
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Invalid credentials")
            user_role = "admin"
        elif username.startswith("analyst"):
            if not ANALYST_PASSWORD or not _verify_pw_env(password, ANALYST_PASSWORD):
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Invalid credentials")
            user_role = "analyst"
        else:
            if not CUSTOMER_PASSWORD or not _verify_pw_env(password, CUSTOMER_PASSWORD):
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Invalid credentials")
            user_role = "customer"
        
        customer_id = username
        log.warning("[AUTH] 환경변수 기반 인증 사용 (폴백): username=%s, role=%s", username, user_role)

    # Access Token 생성
    access_token = create_access_token(
        data={"sub": customer_id, "role": user_role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    
    # Refresh Token 생성
    refresh_token = secrets.token_urlsafe(32)
    refresh_expire_days = get_refresh_token_expire_days()
    refresh_expires_at = (datetime.now(timezone.utc) + timedelta(days=refresh_expire_days)).isoformat()
    
    db.create_refresh_token(refresh_token, customer_id, refresh_expires_at)

    try:
        log_audit(
            db=db,
            actor_customer_id=customer_id,
            target_customer_id=None,
            endpoint="/v1/auth/login",
            method="POST",
            user_role=user_role,
            request=request,
            success=True,
        )
    except (sqlite3.Error, ValueError, AttributeError) as e:
        log.warning("감사 로그 기록 실패: %s", e)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type":   "bearer",
        "customer_id":  customer_id,
        "role":         user_role,
        "expires_in":   ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me")
async def get_current_user(
    current_customer: Dict[str, Any] = Depends(get_current_customer),
):
    """현재 인증된 사용자 정보."""
    if current_customer is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "customer_id": current_customer.get("sub"),
        "role":        current_customer.get("role"),
    }


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(
    request: RefreshTokenRequest,
    http_request: Request = None,
):
    """리프레시 토큰으로 새로운 액세스 토큰 발급."""
    db = get_auth_db()
    
    # 리프레시 토큰 조회
    refresh_token_data = db.get_refresh_token(request.refresh_token)
    if not refresh_token_data:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # 만료 확인
    from datetime import datetime, timezone
    expires_at = datetime.fromisoformat(refresh_token_data["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Refresh token expired")
    
    customer_id = refresh_token_data["customer_id"]
    
    # 사용자 정보 조회
    user = db.get_user_by_customer_id(customer_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User not found")
    
    # 새로운 액세스 토큰 생성
    new_access_token = create_access_token(
        data={"sub": customer_id, "role": user["role"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    
    try:
        log_audit(
            db=db,
            actor_customer_id=customer_id,
            target_customer_id=None,
            endpoint="/v1/auth/refresh",
            method="POST",
            user_role=user["role"],
            request=http_request,
            success=True,
        )
    except (sqlite3.Error, ValueError, AttributeError) as e:
        log.warning("감사 로그 기록 실패: %s", e)
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout")
async def logout(
    request: RefreshTokenRequest,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    http_request: Request = None,
):
    """로그아웃 (리프레시 토큰 폐기)."""
    db = get_auth_db()
    
    # 리프레시 토큰 폐기
    db.revoke_refresh_token(request.refresh_token)
    
    try:
        log_audit(
            db=db,
            actor_customer_id=current_customer.get("sub"),
            target_customer_id=None,
            endpoint="/v1/auth/logout",
            method="POST",
            user_role=current_customer.get("role"),
            request=http_request,
            success=True,
        )
    except (sqlite3.Error, ValueError, AttributeError) as e:
        log.warning("감사 로그 기록 실패: %s", e)
    
    return {"message": "Logged out successfully"}


@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: ChangePasswordRequest,
    current_customer: Dict[str, Any] = Depends(get_current_customer),
    http_request: Request = None,
):
    """비밀번호 변경."""
    db = get_auth_db()
    
    customer_id = current_customer.get("sub")
    user = db.get_user_by_customer_id(customer_id)
    
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    
    # 기존 비밀번호 확인
    if not _verify_pw(request.old_password, user["password_hash"]):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid old password")
    
    # 새 비밀번호 해시
    new_password_hash = pwd_context.hash(request.new_password)
    
    # 비밀번호 업데이트
    db.update_user_password(user["username"], new_password_hash)
    
    # 모든 리프레시 토큰 폐기
    db.revoke_all_refresh_tokens(customer_id)
    
    try:
        log_audit(
            db=db,
            actor_customer_id=customer_id,
            target_customer_id=customer_id,
            endpoint="/v1/auth/change-password",
            method="POST",
            user_role=current_customer.get("role"),
            request=http_request,
            success=True,
        )
    except (sqlite3.Error, ValueError, AttributeError) as e:
        log.warning("감사 로그 기록 실패: %s", e)
    
    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(
    request: ForgotPasswordRequest,
    http_request: Request = None,
):
    """비밀번호 찾기 (리셋 토큰 발송 요청)."""
    db = get_auth_db()
    
    # 사용자 조회
    user = db.get_user_by_username(request.username)
    if not user:
        # 보안을 위해 사용자가 없어도 성공 응답 (사용자 존재 여부 노출 방지)
        return {"message": "If the user exists, a password reset link will be sent"}
    
    # 리셋 토큰 생성
    reset_token = secrets.token_urlsafe(32)
    from datetime import datetime, timedelta, timezone
    reset_expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    
    db.create_password_reset_token(reset_token, user["customer_id"], reset_expires_at)
    
    # 실제로는 이메일 전송 로직이 필요하지만, 여기서는 토큰만 반환
    # 프로덕션에서는 이메일 전송 서비스와 연동 필요
    log.info("[AUTH] 비밀번호 리셋 토큰 생성: username=%s, customer_id=%s", request.username, user["customer_id"])
    
    try:
        log_audit(
            db=db,
            actor_customer_id=user["customer_id"],
            target_customer_id=user["customer_id"],
            endpoint="/v1/auth/forgot-password",
            method="POST",
            user_role=user["role"],
            request=http_request,
            success=True,
        )
    except (sqlite3.Error, ValueError, AttributeError) as e:
        log.warning("감사 로그 기록 실패: %s", e)
    
    return {
        "message": "If the user exists, a password reset link will be sent",
        "reset_token": reset_token  # 테스트용, 프로덕션에서는 이메일로 전송
    }


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: ResetPasswordRequest,
    http_request: Request = None,
):
    """비밀번호 재설정 (리셋 토큰으로 새 비밀번호 설정)."""
    db = get_auth_db()
    
    # 리셋 토큰 조회
    reset_token_data = db.get_password_reset_token(request.token)
    if not reset_token_data:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")
    
    # 만료 확인
    from datetime import datetime, timezone
    expires_at = datetime.fromisoformat(reset_token_data["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Reset token expired")
    
    customer_id = reset_token_data["customer_id"]
    
    # 사용자 조회
    user = db.get_user_by_customer_id(customer_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    
    # 새 비밀번호 해시
    new_password_hash = pwd_context.hash(request.new_password)
    
    # 비밀번호 업데이트
    db.update_user_password(user["username"], new_password_hash)
    
    # 리셋 토큰 사용 표시
    db.mark_password_reset_token_used(request.token)
    
    # 모든 리프레시 토큰 폐기
    db.revoke_all_refresh_tokens(customer_id)
    
    try:
        log_audit(
            db=db,
            actor_customer_id=customer_id,
            target_customer_id=customer_id,
            endpoint="/v1/auth/reset-password",
            method="POST",
            user_role=user["role"],
            request=http_request,
            success=True,
        )
    except (sqlite3.Error, ValueError, AttributeError) as e:
        log.warning("감사 로그 기록 실패: %s", e)
    
    return {"message": "Password reset successfully"}
