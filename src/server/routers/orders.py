"""
orders.py — 주문 관련 API 라우터

주문 생성, 상태 조회, 취소, 고객 구매 이력 조회 기능 제공
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.server.deps import log

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/orders", tags=["orders"])


# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class ShippingAddress(BaseModel):
    recipient: str = Field(..., description="수령인")
    phone: str = Field(..., description="연락처")
    address: str = Field(..., description="주소")
    zip_code: str = Field(..., description="우편번호")


class OrderItem(BaseModel):
    product_id: str = Field(..., description="제품 ID")
    quantity: int = Field(..., gt=0, description="수량")
    price: float = Field(..., gt=0, description="단가")


class CreateOrderRequest(BaseModel):
    customer_id: str = Field(..., description="고객 ID")
    items: List[OrderItem] = Field(..., description="주문 항목 목록")
    shipping_address: ShippingAddress = Field(..., description="배송지 정보")
    payment_method: str = Field(..., description="결제 수단 (credit_card, naver_pay, coupang_pay, kakao_pay, bank_transfer)")
    recommendation_source: Optional[str] = Field(None, description="추천 출처 (skin_analysis 등)")
    analysis_job_id: Optional[str] = Field(None, description="피부 분석 Job ID")


class OrderResponse(BaseModel):
    order_id: str
    status: str
    total_amount: float
    created_at: str
    payment_url: Optional[str] = None


class OrderStatusResponse(BaseModel):
    order_id: str
    status: str
    total_amount: float
    items: List[dict]
    shipping_address: ShippingAddress
    payment_status: str
    shipping_status: str
    created_at: str
    updated_at: str


class CancelOrderRequest(BaseModel):
    reason: str = Field(..., description="취소 사유")


class CancelOrderResponse(BaseModel):
    order_id: str
    status: str
    cancelled_at: str
    refund_amount: float
    refund_status: str


class PurchaseHistoryResponse(BaseModel):
    customer_id: str
    total_orders: int
    total_spent: float
    orders: List[dict]


# ── 데이터베이스 (임시 메모리 저장소) ─────────────────────────────────────────────
# 실제 구현 시 SQLite 또는 Supabase 사용 필요

_orders_db: dict[str, dict] = {}
_order_items_db: dict[str, List[dict]] = {}
_purchase_history_db: dict[str, List[dict]] = {}


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────

def _generate_order_id() -> str:
    """주문 ID 생성 (ORD-YYYYMMDD-NNNN 형식)"""
    date_str = datetime.now().strftime("%Y%m%d")
    random_suffix = str(uuid.uuid4().int)[:4]
    return f"ORD-{date_str}-{random_suffix}"


def _calculate_total_amount(items: List[OrderItem]) -> float:
    """총 주문 금액 계산"""
    return sum(item.quantity * item.price for item in items)


# ── API 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(request: CreateOrderRequest):
    """
    주문 생성
    
    - 주문 생성 시 재고 예약
    - 결제 URL 반환
    """
    order_id = _generate_order_id()
    total_amount = _calculate_total_amount(request.items)
    
    # 주문 생성
    order = {
        "order_id": order_id,
        "customer_id": request.customer_id,
        "status": "pending_payment",
        "total_amount": total_amount,
        "payment_method": request.payment_method,
        "payment_status": "pending",
        "shipping_status": "pending",
        "shipping_address": request.shipping_address.dict(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "recommendation_source": request.recommendation_source,
        "analysis_job_id": request.analysis_job_id,
    }
    
    _orders_db[order_id] = order
    
    # 주문 항목 저장
    order_items = [
        {
            "product_id": item.product_id,
            "product_name": f"Product {item.product_id}",  # 실제 제품명은 DB에서 조회
            "quantity": item.quantity,
            "price": item.price,
            "subtotal": item.quantity * item.price,
        }
        for item in request.items
    ]
    _order_items_db[order_id] = order_items
    
    # 결제 URL 생성 (실제 구현 시 결제 게이트웨이 연동)
    payment_url = f"https://payment.example.com/pay/{order_id}"
    
    log.info(f"주문 생성: {order_id}, 고객: {request.customer_id}, 금액: {total_amount}")
    
    return OrderResponse(
        order_id=order_id,
        status="pending_payment",
        total_amount=total_amount,
        created_at=order["created_at"],
        payment_url=payment_url,
    )


@router.get("/{order_id}", response_model=OrderStatusResponse)
async def get_order_status(order_id: str):
    """
    주문 상태 조회
    """
    if order_id not in _orders_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"주문을 찾을 수 없습니다: {order_id}"
        )
    
    order = _orders_db[order_id]
    items = _order_items_db.get(order_id, [])
    
    return OrderStatusResponse(
        order_id=order["order_id"],
        status=order["status"],
        total_amount=order["total_amount"],
        items=items,
        shipping_address=ShippingAddress(**order["shipping_address"]),
        payment_status=order["payment_status"],
        shipping_status=order["shipping_status"],
        created_at=order["created_at"],
        updated_at=order["updated_at"],
    )


@router.post("/{order_id}/cancel", response_model=CancelOrderResponse)
async def cancel_order(order_id: str, request: CancelOrderRequest):
    """
    주문 취소
    
    - 결제 대기 상태인 경우 즉시 취소
    - 결제 완료 상태인 경우 환불 처리
    """
    if order_id not in _orders_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"주문을 찾을 수 없습니다: {order_id}"
        )
    
    order = _orders_db[order_id]
    
    if order["status"] in ["shipped", "delivered"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 배송 중이거나 배송 완료된 주문은 취소할 수 없습니다."
        )
    
    # 주문 취소 처리
    order["status"] = "cancelled"
    order["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    order["cancelled_reason"] = request.reason
    order["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # 환불 처리 (실제 구현 시 결제 게이트웨이 연동)
    refund_amount = order["total_amount"]
    refund_status = "processing"
    
    log.info(f"주문 취소: {order_id}, 사유: {request.reason}, 환불액: {refund_amount}")
    
    return CancelOrderResponse(
        order_id=order_id,
        status="cancelled",
        cancelled_at=order["cancelled_at"],
        refund_amount=refund_amount,
        refund_status=refund_status,
    )


@router.get("/customers/{customer_id}/purchase-history", response_model=PurchaseHistoryResponse)
async def get_purchase_history(
    customer_id: str,
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
):
    """
    고객 구매 이력 조회
    
    - limit: 조회할 건수 (기본: 20)
    - offset: 오프셋 (기본: 0)
    - status: 상태 필터 (paid, shipped, delivered)
    """
    # 고객의 모든 주문 조회
    customer_orders = [
        order for order in _orders_db.values()
        if order["customer_id"] == customer_id
    ]
    
    # 상태 필터링
    if status:
        customer_orders = [order for order in customer_orders if order["status"] == status]
    
    # 최신순 정렬
    customer_orders.sort(key=lambda x: x["created_at"], reverse=True)
    
    # 페이징
    total_orders = len(customer_orders)
    paginated_orders = customer_orders[offset:offset + limit]
    
    # 총 지출액 계산
    total_spent = sum(
        order["total_amount"]
        for order in customer_orders
        if order["status"] in ["paid", "shipped", "delivered"]
    )
    
    # 주문 상세 정보 구성
    orders = []
    for order in paginated_orders:
        items = _order_items_db.get(order["order_id"], [])
        orders.append({
            "order_id": order["order_id"],
            "status": order["status"],
            "total_amount": order["total_amount"],
            "items": items,
            "purchased_at": order["created_at"],
            "recommendation_source": order.get("recommendation_source"),
            "analysis_job_id": order.get("analysis_job_id"),
        })
    
    return PurchaseHistoryResponse(
        customer_id=customer_id,
        total_orders=total_orders,
        total_spent=total_spent,
        orders=orders,
    )
