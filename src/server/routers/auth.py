"""
routers/auth.py — 인증 엔드포인트

POST /v1/auth/login
GET  /v1/auth/me
"""
from __future__ import annotations

import hmac
import os
import sqlite3
from datetime import timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, Form, Request

from src.db.skin_analysis_db import SkinAnalysisDB
from src.utils.config import load_config
from src.server.deps import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_customer,
    limiter,
    log,
    log_audit,
    pwd_context,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ── 의존성 ───────────────────────────────────────────────────────────────────

def get_auth_db():
    """SkinAnalysisDB 인스턴스 반환 (인증용)"""
    config = load_config()
    db_path = config.get("database", {}).get("sqlite_path", "results/skin_analysis.db")
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

    access_token = create_access_token(
        data={"sub": customer_id, "role": user_role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

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
    except (sqlite3.Error, ValueError, AttributeError) as e:  # [FIX P2] 구체적 예외 + AttributeError 추가
        log.warning("감사 로그 기록 실패: %s", e)

    return {
        "access_token": access_token,
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
