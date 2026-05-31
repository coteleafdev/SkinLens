"""
routers/integration.py — 외부 시스템 연동 API

POST /v1/webhooks
GET  /v1/webhooks
PUT  /v1/webhooks/{id}
DELETE /v1/webhooks/{id}
POST /v1/integration/customers/sync
POST /v1/integration/products/sync
GET  /v1/integration/sync-logs
POST /v1/oauth/authorize
POST /v1/oauth/token
GET  /v1/oauth/providers
POST /v1/oauth/providers
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import httpx

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.db.skin_analysis_db import SkinAnalysisDB
from src.server.deps import get_current_customer
from src.utils.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["integration"])


# ── Pydantic Models ─────────────────────────────────────────────────────────────

class WebhookCreateRequest(BaseModel):
    url: str
    events: List[str]
    secret_key: Optional[str] = None


class WebhookUpdateRequest(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


class SyncRequest(BaseModel):
    source_system: str
    target_system: str
    direction: str  # "in" or "out"


class OAuthProviderCreateRequest(BaseModel):
    provider_name: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: Optional[List[str]] = None


class OAuthAuthorizeRequest(BaseModel):
    provider_name: str
    customer_id: str


class OAuthTokenRequest(BaseModel):
    provider_name: str
    customer_id: str
    code: str


# ── 웹훅 관리 ─────────────────────────────────────────────────────────────

@router.post("/v1/webhooks")
async def create_webhook(
    request_data: WebhookCreateRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """웹훅 등록"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    customer_id = current_customer.get("sub")
    webhook_id = str(uuid.uuid4())
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db.create_webhook(
            webhook_id=webhook_id,
            customer_id=customer_id,
            url=request_data.url,
            events=request_data.events,
            secret_key=request_data.secret_key,
        )
        
        if not success:
            raise HTTPException(status_code=409, detail="Webhook ID already exists")
        
        return {"webhook_id": webhook_id, "message": "Webhook created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("웹훅 생성 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create webhook")


@router.get("/v1/webhooks")
async def list_webhooks(
    active_only: bool = True,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """웹훅 목록 조회"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    customer_id = current_customer.get("sub")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        webhooks = db.get_webhooks(customer_id=customer_id, active_only=active_only)
        return {"webhooks": webhooks, "total": len(webhooks)}
    except Exception as e:
        log.error("웹훅 목록 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve webhooks")


@router.put("/v1/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    request_data: WebhookUpdateRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """웹훅 업데이트"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db.update_webhook(
            webhook_id=webhook_id,
            url=request_data.url,
            events=request_data.events,
            is_active=request_data.is_active,
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Webhook not found or no changes")
        
        return {"message": "Webhook updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("웹훅 업데이트 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update webhook")


@router.delete("/v1/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """웹훅 삭제"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db.delete_webhook(webhook_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Webhook not found")
        
        return {"message": "Webhook deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("웹훅 삭제 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete webhook")


# ── 웹훅 트리거 (내부 사용) ─────────────────────────────────────────────────

async def trigger_webhook(
    webhook_url: str,
    event_type: str,
    payload: Dict[str, Any],
    secret_key: Optional[str] = None,
) -> bool:
    """웹훅 호출"""
    try:
        headers = {"Content-Type": "application/json"}
        if secret_key:
            import hmac
            import hashlib
            signature = hmac.new(
                secret_key.encode(),
                str(payload).encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = signature
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                webhook_url,
                json={"event": event_type, "data": payload},
                headers=headers,
            )
            return response.status_code == 200
    except Exception as e:
        log.error("웹훅 호출 실패: %s", e)
        return False


# ── 외부 시스템 동기화 ─────────────────────────────────────────────────────

@router.post("/v1/integration/customers/sync")
async def sync_customers(
    request_data: SyncRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """고객 데이터 동기화"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        log_id = db.create_sync_log(
            sync_type="customers",
            direction=request_data.direction,
            source_system=request_data.source_system,
            target_system=request_data.target_system,
        )
        
        # 실제 동기화 로직 (예시)
        records_count = 0
        if request_data.direction == "in":
            # 외부 시스템에서 데이터 가져오기
            customers = db.list_customers(limit=1000)
            records_count = len(customers)
        else:
            # 외부 시스템으로 데이터 보내기
            customers = db.list_customers(limit=1000)
            records_count = len(customers)
        
        db.update_sync_log(log_id, status="completed", records_count=records_count)
        
        return {"sync_log_id": log_id, "records_count": records_count, "status": "completed"}
    except Exception as e:
        log.error("고객 동기화 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to sync customers")


@router.post("/v1/integration/products/sync")
async def sync_products(
    request_data: SyncRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """제품 데이터 동기화"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        log_id = db.create_sync_log(
            sync_type="products",
            direction=request_data.direction,
            source_system=request_data.source_system,
            target_system=request_data.target_system,
        )
        
        # 실제 동기화 로직 (예시)
        records_count = 0
        if request_data.direction == "in":
            products = db.list_products(limit=1000)
            records_count = len(products)
        else:
            products = db.list_products(limit=1000)
            records_count = len(products)
        
        db.update_sync_log(log_id, status="completed", records_count=records_count)
        
        return {"sync_log_id": log_id, "records_count": records_count, "status": "completed"}
    except Exception as e:
        log.error("제품 동기화 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to sync products")


@router.get("/v1/integration/sync-logs")
async def get_sync_logs(
    sync_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """동기화 로그 조회"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        logs = db.get_sync_logs(sync_type=sync_type, status=status, limit=limit)
        return {"logs": logs, "total": len(logs)}
    except Exception as e:
        log.error("동기화 로그 조회 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve sync logs")


# ── OAuth/SSO ───────────────────────────────────────────────────────────────

@router.post("/v1/oauth/providers")
async def create_oauth_provider(
    request_data: OAuthProviderCreateRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """OAuth 제공자 등록 (관리자 전용)"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")
    
    provider_id = str(uuid.uuid4())
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        success = db.create_oauth_provider(
            provider_id=provider_id,
            provider_name=request_data.provider_name,
            client_id=request_data.client_id,
            client_secret=request_data.client_secret,
            redirect_uri=request_data.redirect_uri,
            scopes=request_data.scopes,
        )
        
        if not success:
            raise HTTPException(status_code=409, detail="Provider already exists")
        
        return {"provider_id": provider_id, "message": "OAuth provider created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("OAuth 제공자 등록 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create OAuth provider")


@router.get("/v1/oauth/providers")
async def list_oauth_providers(
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """OAuth 제공자 목록 조회 (관리자 전용)"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = current_customer.get("role", "customer")
    if role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다.")
    
    # 간단한 구현 - 실제로는 DB에서 목록 조회 필요
    return {"providers": [], "total": 0}


@router.post("/v1/oauth/authorize")
async def oauth_authorize(
    request_data: OAuthAuthorizeRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """OAuth 인증 URL 생성"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        provider = db.get_oauth_provider(request_data.provider_name)
        
        if not provider:
            raise HTTPException(status_code=404, detail="OAuth provider not found")
        
        # OAuth 인증 URL 생성 (예시)
        state = str(uuid.uuid4())
        auth_url = f"https://{request_data.provider_name}.com/oauth/authorize?client_id={provider['client_id']}&redirect_uri={provider['redirect_uri']}&state={state}"
        
        return {"auth_url": auth_url, "state": state}
    except HTTPException:
        raise
    except Exception as e:
        log.error("OAuth 인증 URL 생성 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate auth URL")


@router.post("/v1/oauth/token")
async def oauth_token(
    request_data: OAuthTokenRequest,
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """OAuth 토큰 교환"""
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        db = SkinAnalysisDB(db_path="results/skin_analysis.db")
        provider = db.get_oauth_provider(request_data.provider_name)
        
        if not provider:
            raise HTTPException(status_code=404, detail="OAuth provider not found")
        
        # 실제 OAuth 토큰 교환 로직 (예시)
        token_id = str(uuid.uuid4())
        access_token = "mock_access_token_" + str(uuid.uuid4())
        
        db.save_oauth_token(
            token_id=token_id,
            customer_id=request_data.customer_id,
            provider_id=provider["id"],
            access_token=access_token,
            expires_in=3600,
        )
        
        return {"access_token": access_token, "token_type": "Bearer", "expires_in": 3600}
    except HTTPException:
        raise
    except Exception as e:
        log.error("OAuth 토큰 교환 실패: %s", e)
        raise HTTPException(status_code=500, detail="Failed to exchange token")
