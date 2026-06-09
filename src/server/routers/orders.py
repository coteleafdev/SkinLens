"""
orders.py — 주문 관련 API 라우터

주문 생성, 상태 조회, 취소, 고객 구매 이력 조회, 결제 콜백, 배송 상태 업데이트, 피드백 기능 제공
"""
from __future__ import annotations

import logging
import uuid
import barcode
import re
from barcode.writer import ImageWriter
from datetime import datetime, timezone
from typing import List, Optional
from io import BytesIO
import base64

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.server.deps import log, get_db
from src.db.skin_analysis_db import SkinAnalysisDB

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
    barcode: Optional[str] = None  # 바코드 이미지 (base64)
    barcode_number: Optional[str] = None  # 바코드 번호


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


class PaymentCallbackRequest(BaseModel):
    order_id: str = Field(..., description="주문 ID")
    payment_id: str = Field(..., description="결제 ID")
    payment_status: str = Field(..., description="결제 상태 (success, failed)")
    paid_amount: float = Field(..., description="결제 금액")
    paid_at: str = Field(..., description="결제 시간")


class PaymentCallbackResponse(BaseModel):
    order_id: str
    status: str
    payment_status: str
    message: str


class UpdateShippingStatusRequest(BaseModel):
    order_id: str = Field(..., description="주문 ID")
    shipping_status: str = Field(..., description="배송 상태 (pending, shipped, delivered)")
    tracking_number: Optional[str] = Field(None, description="운송장 번호")
    shipped_at: Optional[str] = Field(None, description="발송 시간")
    delivered_at: Optional[str] = Field(None, description="배송 완료 시간")


class ShippingStatusResponse(BaseModel):
    order_id: str
    shipping_status: str
    tracking_number: Optional[str]
    message: str


class ProductFeedbackRequest(BaseModel):
    order_id: str = Field(..., description="주문 ID")
    product_id: str = Field(..., description="제품 ID")
    rating: int = Field(..., ge=1, le=5, description="평점 (1-5)")
    comment: Optional[str] = Field(None, description="리뷰 코멘트")
    would_repurchase: Optional[bool] = Field(None, description="재구매 의사")


class ProductFeedbackResponse(BaseModel):
    feedback_id: str
    order_id: str
    product_id: str
    rating: int
    created_at: str
    message: str


class ProductFeedbackListResponse(BaseModel):
    product_id: str
    total_reviews: int
    average_rating: float
    reviews: List[dict]


class ReadyMadeProductResponse(BaseModel):
    product_id: str
    product_name: str
    category: str
    price: float
    stock_quantity: int
    description: Optional[str] = None


class ReadyMadeProductsListResponse(BaseModel):
    ready_made_products: List[ReadyMadeProductResponse]
    total_products: int


# ── 바코드 생성 함수 ─────────────────────────────────────────────────────────────

def generate_barcode(order_id: str) -> tuple[str, str]:
    """
    바코드 생성 (번호와 이미지)
    
    Args:
        order_id: 주문 ID
        
    Returns:
        (바코드 이미지 base64, 바코드 번호)
    """
    # 주문 ID에서 숫자만 추출하여 바코드 번호 생성
    numbers_only = re.sub(r'[^0-9]', '', order_id)
    barcode_number = numbers_only[:12].ljust(12, "0")
    
    # 바코드 이미지 생성
    try:
        code128 = barcode.get_barcode_class('code128')
        barcode_instance = code128(barcode_number, writer=ImageWriter())
        
        # 메모리에 이미지 생성
        buffer = BytesIO()
        barcode_instance.write(buffer, options={
            'module_width': 2,
            'module_height': 50,
            'font_size': 10,
            'text_distance': 5,
            'quiet_zone': 6.5,
        })
        
        # Base64 인코딩
        buffer.seek(0)
        barcode_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
        barcode_image = f"data:image/png;base64,{barcode_image}"
    except Exception as e:
        log.error(f"바코드 이미지 생성 실패: {order_id}, error={e}")
        barcode_image = ""  # 실패 시 빈 문자열
    
    return barcode_image, barcode_number


def generate_label_data(order_id: str, order: dict, items: list) -> dict:
    """
    라벨 프린터용 데이터 생성
    
    Args:
        order_id: 주문 ID
        order: 주문 정보
        items: 주문 항목 목록
        
    Returns:
        라벨 데이터 딕셔너리
    """
    # 바코드 생성
    barcode_image, barcode_number = generate_barcode(order_id)
    
    # 라벨 데이터 구성
    label_data = {
        "order_id": order_id,
        "barcode_number": barcode_number,
        "barcode_image": barcode_image,
        "customer_id": order.get("customer_id", ""),
        "shipping_address": order.get("shipping_address", {}),
        "items": [
            {
                "product_id": item.get("product_id", ""),
                "product_name": item.get("product_name", ""),
                "quantity": item.get("quantity", 0),
                "price": item.get("price", 0.0),
            }
            for item in items
        ],
        "total_amount": order.get("total_amount", 0.0),
        "created_at": order.get("created_at", ""),
        "label_format": {
            "width": 100,  # mm
            "height": 150,  # mm
            "dpi": 300,
        },
        "label_content": {
            "header": "CÔTELLEAF",
            "title": "배송 라벨",
            "order_info": f"주문번호: {order_id}",
            "barcode": barcode_number,
            "footer": "고객센터: 1588-0000"
        }
    }
    
    return label_data


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
async def create_order(request: CreateOrderRequest, db: SkinAnalysisDB = Depends(get_db)):
    """
    주문 생성
    
    - 주문 생성 시 재고 예약
    - 결제 URL 반환
    - DB에 주문 정보 저장
    """
    order_id = _generate_order_id()
    total_amount = _calculate_total_amount(request.items)
    
    # 바코드 생성 (라벨 프린터용)
    barcode_image, barcode_number = generate_barcode(order_id)
    
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
        "barcode_number": barcode_number,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "recommendation_source": request.recommendation_source,
        "analysis_job_id": request.analysis_job_id,
    }
    
    # DB에 주문 저장
    try:
        # 재고 확인
        for item in request.items:
            if not db.check_stock(item.product_id, item.quantity):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"재고 부족: {item.product_id}"
                )
        
        # 재고 차감
        for item in request.items:
            if not db.deduct_stock(item.product_id, item.quantity):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"재고 차감 실패: {item.product_id}"
                )
        
        db.save_order(
            order_id=order_id,
            customer_id=request.customer_id,
            status="pending_payment",
            total_amount=total_amount,
            payment_method=request.payment_method,
            payment_status="pending",
            shipping_status="pending",
            shipping_address=request.shipping_address.dict(),
            barcode_number=barcode_number,
            recommendation_source=request.recommendation_source,
            analysis_job_id=request.analysis_job_id,
        )
        
        # 주문 항목 저장
        for item in request.items:
            db.save_order_item(
                order_id=order_id,
                product_id=item.product_id,
                product_name=f"Product {item.product_id}",
                quantity=item.quantity,
                price=item.price,
                subtotal=item.quantity * item.price,
            )
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소에만 저장
        log.warning(f"주문 DB 저장 실패: {order_id}, error='DB 메서드가 없습니다'")
    except Exception as e:
        # DB 저장 실패 시 재고 복구 시도
        log.error(f"주문 DB 저장 실패: {order_id}, error={e}")
        for item in request.items:
            try:
                db.add_stock(item.product_id, item.quantity)
            except:
                pass
    
    _orders_db[order_id] = order
    
    # 주문 항목 저장 (메모리 저장소)
    order_items = [
        {
            "product_id": item.product_id,
            "product_name": f"Product {item.product_id}",
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
        barcode=barcode_image,
        barcode_number=barcode_number,
    )


@router.get("/{order_id}/label", response_model=dict)
async def get_order_label(order_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """
    라벨 프린터용 데이터 생성
    
    - 바코드 이미지
    - 주문 정보
    - 제품 정보
    - 배송 정보
    """
    # DB에서 주문 조회 시도
    try:
        order = db.get_order(order_id)
        if not order:
            # 메모리 저장소에서 조회
            if order_id not in _orders_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"주문을 찾을 수 없습니다: {order_id}"
                )
            order = _orders_db[order_id]
            items = _order_items_db.get(order_id, [])
        else:
            # DB에서 주문 항목 조회
            items = db.get_order_items(order_id)
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
        if order_id not in _orders_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"주문을 찾을 수 없습니다: {order_id}"
            )
        order = _orders_db[order_id]
        items = _order_items_db.get(order_id, [])
    
    # 라벨 데이터 생성
    label_data = generate_label_data(order_id, order, items)
    
    return label_data


@router.patch("/{order_id}/status", response_model=OrderStatusResponse)
async def update_order_status(
    order_id: str, 
    status: str,
    db: SkinAnalysisDB = Depends(get_db)
):
    """
    주문 상태 업데이트
    
    - 주문 상태 변경 (pending_payment, paid, processing, shipped, delivered, cancelled)
    """
    # 유효한 상태 검증
    valid_statuses = ["pending_payment", "paid", "processing", "shipped", "delivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"유효하지 않은 상태입니다: {status}. 유효한 상태: {', '.join(valid_statuses)}"
        )
    
    # DB에서 주문 조회 시도
    try:
        order = db.get_order(order_id)
        if not order:
            # 메모리 저장소에서 조회
            if order_id not in _orders_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"주문을 찾을 수 없습니다: {order_id}"
                )
            order = _orders_db[order_id]
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
        if order_id not in _orders_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"주문을 찾을 수 없습니다: {order_id}"
            )
        order = _orders_db[order_id]
    
    # 상태 업데이트
    try:
        db.update_order_status(order_id, status)
    except AttributeError:
        pass  # DB 메서드가 없는 경우 메모리 저장소만 업데이트
    
    _orders_db[order_id]["status"] = status
    _orders_db[order_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    log.info(f"주문 상태 업데이트: {order_id}, status={status}")
    
    # 업데이트된 주문 정보 반환
    return await get_order_status(order_id, db)


@router.get("/customer/{customer_id}", response_model=PurchaseHistoryResponse)
async def get_customer_orders(customer_id: str, limit: int = 50, db: SkinAnalysisDB = Depends(get_db)):
    """
    고객 주문 내역 조회
    """
    # DB에서 고객 주문 목록 조회 시도
    try:
        orders = db.get_customer_orders(customer_id, limit)
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
        orders = []
        for order_id, order in _orders_db.items():
            if order.get("customer_id") == customer_id:
                orders.append(order)
        orders = orders[:limit]
    
    # 총 주문 수와 총 지출 금액 계산
    total_orders = len(orders)
    total_spent = sum(order["total_amount"] for order in orders)
    
    return PurchaseHistoryResponse(
        customer_id=customer_id,
        total_orders=total_orders,
        total_spent=total_spent,
        orders=orders,
    )


@router.get("/{order_id}", response_model=OrderStatusResponse)
async def get_order_status(order_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """
    주문 상태 조회
    """
    # DB에서 주문 조회 시도
    try:
        order = db.get_order(order_id)
        if order:
            # DB에서 주문 항목 조회
            items = db.get_order_items(order_id)
        else:
            # 메모리 저장소에서 조회
            if order_id not in _orders_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"주문을 찾을 수 없습니다: {order_id}"
                )
            order = _orders_db[order_id]
            items = _order_items_db.get(order_id, [])
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
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
        shipping_address=ShippingAddress(**order["shipping_address"]) if isinstance(order["shipping_address"], dict) else order["shipping_address"],
        payment_status=order["payment_status"],
        shipping_status=order["shipping_status"],
        created_at=order["created_at"],
        updated_at=order["updated_at"],
    )


@router.get("/statistics/sales", response_model=dict)
async def get_sales_statistics(
    start_date: str,
    end_date: str,
    db: SkinAnalysisDB = Depends(get_db)
):
    """
    판매 통계 조회 (관리자용)
    
    - 기간별 총 주문 수
    - 총 매출액
    - 평균 주문 금액
    """
    try:
        stats = db.get_sales_statistics(start_date, end_date)
        return stats
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "total_orders": 0,
            "total_revenue": 0.0,
            "average_order_value": 0.0,
        }


@router.get("/statistics/popular-products", response_model=dict)
async def get_popular_products(limit: int = 10, db: SkinAnalysisDB = Depends(get_db)):
    """
    인기 제품 조회 (관리자용)
    
    - 판매량 기준 인기 제품
    - 총 판매량 및 매출액
    """
    try:
        products = db.get_popular_products(limit)
        return {
            "popular_products": products,
            "limit": limit,
        }
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "popular_products": [],
            "limit": limit,
        }


@router.get("/statistics/daily-sales", response_model=dict)
async def get_daily_sales(days: int = 30, db: SkinAnalysisDB = Depends(get_db)):
    """
    일별 판매 추이 조회 (관리자용)
    
    - 일별 주문 수
    - 일별 매출액
    """
    try:
        daily_sales = db.get_daily_sales(days)
        return {
            "daily_sales": daily_sales,
            "days": days,
        }
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "daily_sales": [],
            "days": days,
        }


@router.get("/notifications/{customer_id}/settings", response_model=dict)
async def get_notification_settings(customer_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """
    알림 설정 조회
    
    - 고객별 알림 설정 조회
    - 분석 완료 알림 활성화 여부
    - 디바이스 토큰 및 플랫폼 정보
    """
    try:
        settings = db.get_notification_settings(customer_id)
        if not settings:
            # 기본 설정 반환
            return {
                "customer_id": customer_id,
                "analysis_complete_enabled": True,
                "device_token": None,
                "platform": None,
            }
        return settings
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "customer_id": customer_id,
            "analysis_complete_enabled": True,
            "device_token": None,
            "platform": None,
        }


@router.put("/notifications/{customer_id}/settings", response_model=dict)
async def update_notification_settings(
    customer_id: str,
    analysis_complete_enabled: bool,
    device_token: Optional[str] = None,
    platform: Optional[str] = None,
    db: SkinAnalysisDB = Depends(get_db)
):
    """
    알림 설정 업데이트
    
    - 분석 완료 알림 활성화/비활성화
    - 디바이스 토큰 등록
    - 플랫폼 정보 업데이트
    """
    try:
        db.update_notification_settings(customer_id, analysis_complete_enabled, device_token, platform)
        return {
            "success": True,
            "message": "알림 설정이 업데이트되었습니다.",
            "settings": {
                "customer_id": customer_id,
                "analysis_complete_enabled": analysis_complete_enabled,
                "device_token": device_token,
                "platform": platform,
            }
        }
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "success": True,
            "message": "알림 설정이 업데이트되었습니다 (메모리 저장소)",
            "settings": {
                "customer_id": customer_id,
                "analysis_complete_enabled": analysis_complete_enabled,
            }
        }


@router.post("/notifications/send", response_model=dict)
async def send_notification(
    customer_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: Optional[dict] = None,
    db: SkinAnalysisDB = Depends(get_db)
):
    """
    알림 전송 (관리자용)
    
    - 특정 고객에게 알림 전송
    - 알림 타입: order, shipping, delivery, promotion 등
    """
    try:
        success = db.send_notification(customer_id, notification_type, title, message, data)
        if success:
            return {
                "success": True,
                "message": "알림이 전송되었습니다.",
            }
        else:
            return {
                "success": False,
                "message": "알림 전송 실패 (알림 비활성화 또는 고객을 찾을 수 없음)",
            }
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "success": True,
            "message": "알림 전송 완료 (메모리 저장소)",
        }


@router.get("/statistics/customer/{customer_id}", response_model=dict)
async def get_customer_purchase_pattern(customer_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """
    고객별 구매 패턴 조회
    
    - 총 주문 수
    - 총 지출 금액
    - 평균 주문 금액
    - 마지막 구매일
    """
    try:
        pattern = db.get_customer_purchase_pattern(customer_id)
        return pattern
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "customer_id": customer_id,
            "total_orders": 0,
            "total_spent": 0.0,
            "average_order_value": 0.0,
            "last_purchase_date": None,
        }


@router.get("/products/{product_id}/stock", response_model=dict)
async def get_product_stock(product_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """
    제품 재고 정보 조회
    
    - 재고 수량 조회
    - 제품 가격 조회
    - 활성 상태 조회
    """
    # DB에서 제품 재고 조회 시도
    try:
        stock_info = db.get_product_stock(product_id)
        if not stock_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"제품을 찾을 수 없습니다: {product_id}"
            )
        return stock_info
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "product_id": product_id,
            "product_name": f"Product {product_id}",
            "stock_quantity": 999,  # 무제한 재고
            "price": 0.0,
            "is_active": True,
        }


@router.post("/products/{product_id}/stock", response_model=dict)
async def update_product_stock(product_id: str, quantity: int, action: str = "add", db: SkinAnalysisDB = Depends(get_db)):
    """
    제품 재고 업데이트 (관리자용)
    
    - 재고 추가 (action=add)
    - 재고 차감 (action=deduct)
    """
    try:
        if action == "add":
            success = db.add_stock(product_id, quantity)
            message = f"재고 {quantity}개 추가 완료"
        elif action == "deduct":
            success = db.deduct_stock(product_id, quantity)
            message = f"재고 {quantity}개 차감 완료"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 액션입니다: {action}"
            )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="재고 업데이트 실패"
            )
        
        # 업데이트된 재고 정보 조회
        stock_info = db.get_product_stock(product_id)
        return {
            "success": True,
            "message": message,
            "stock_info": stock_info
        }
    except AttributeError:
        # DB 메서드가 없는 경우 기본 응답
        return {
            "success": True,
            "message": f"재고 {quantity}개 {action} 완료 (메모리 저장소)",
            "stock_info": {
                "product_id": product_id,
                "stock_quantity": 999,
            }
        }


@router.post("/{order_id}/cancel", response_model=CancelOrderResponse)
async def cancel_order(order_id: str, request: CancelOrderRequest, db: SkinAnalysisDB = Depends(get_db)):
    """
    주문 취소
    
    - 결제 대기 상태인 경우 즉시 취소
    - 결제 완료 상태인 경우 환불 처리
    - 배송 중/완료 상태는 취소 불가
    """
    # DB에서 주문 조회 시도
    try:
        order = db.get_order(order_id)
        if not order:
            # 메모리 저장소에서 조회
            if order_id not in _orders_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"주문을 찾을 수 없습니다: {order_id}"
                )
            order = _orders_db[order_id]
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
        if order_id not in _orders_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"주문을 찾을 수 없습니다: {order_id}"
            )
        order = _orders_db[order_id]
    
    # 취소 가능 상태 검증
    if order["status"] in ["shipped", "delivered"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 배송 중이거나 배송 완료된 주문은 취소할 수 없습니다."
        )
    
    if order["status"] == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 취소된 주문입니다."
        )
    
    # 환불 금액 계산
    refund_amount = order["total_amount"]
    if order["payment_status"] == "paid":
        # 결제 완료 상태인 경우 환불 처리
        refund_status = "processing"  # 환불 처리 중
        message = "결제 취소 및 환불 처리가 시작되었습니다."
    else:
        # 결제 대기 상태인 경우 즉시 취소
        refund_status = "not_required"  # 환불 불필요
        refund_amount = 0.0
        message = "주문이 취소되었습니다."
    
    # 주문 취소 처리
    try:
        db.update_order_status(order_id, "cancelled")
    except AttributeError:
        pass  # DB 메서드가 없는 경우 메모리 저장소만 업데이트
    
    _orders_db[order_id]["status"] = "cancelled"
    _orders_db[order_id]["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    _orders_db[order_id]["cancelled_reason"] = request.reason
    _orders_db[order_id]["refund_status"] = refund_status
    _orders_db[order_id]["refund_amount"] = refund_amount
    _orders_db[order_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # 재고 복구 (결제 완료 상태인 경우만)
    if order["payment_status"] == "paid":
        try:
            for item in _order_items_db.get(order_id, []):
                db.add_stock(item["product_id"], item["quantity"])
            log.info(f"재고 복구 완료: {order_id}")
        except AttributeError:
            pass  # DB 메서드가 없는 경우 무시
    
    log.info(f"주문 취소: {order_id}, reason={request.reason}, refund_amount={refund_amount}")
    
    return CancelOrderResponse(
        order_id=order_id,
        status="cancelled",
        cancelled_at=_orders_db[order_id]["cancelled_at"],
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


@router.post("/payment/callback", response_model=PaymentCallbackResponse)
async def payment_callback(request: PaymentCallbackRequest, db: SkinAnalysisDB = Depends(get_db)):
    """
    결제 콜백 (결제 게이트웨이에서 호출)
    
    - 결제 성공 시 주문 상태 업데이트
    - 결제 실패 시 주문 취소
    """
    # DB에서 주문 조회 시도
    try:
        order = db.get_order(request.order_id)
        if not order:
            # 메모리 저장소에서 조회
            if request.order_id not in _orders_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"주문을 찾을 수 없습니다: {request.order_id}"
                )
            order = _orders_db[request.order_id]
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
        if request.order_id not in _orders_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"주문을 찾을 수 없습니다: {request.order_id}"
            )
        order = _orders_db[request.order_id]
    
    # 결제 상태 업데이트
    if request.payment_status == "success":
        # 결제 성공
        try:
            db.update_order_status(request.order_id, "paid")
        except AttributeError:
            pass  # DB 메서드가 없는 경우 메모리 저장소만 업데이트
        
        _orders_db[request.order_id]["payment_status"] = "paid"
        _orders_db[request.order_id]["status"] = "paid"
        _orders_db[request.order_id]["payment_id"] = request.payment_id
        _orders_db[request.order_id]["paid_amount"] = request.paid_amount
        _orders_db[request.order_id]["paid_at"] = request.paid_at
        _orders_db[request.order_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        log.info(f"결제 성공: order_id={request.order_id}, payment_id={request.payment_id}")
        
        return PaymentCallbackResponse(
            order_id=request.order_id,
            status="paid",
            payment_status="success",
            message="결제가 완료되었습니다."
        )
    else:
        # 결제 실패
        db.update_order_status(request.order_id, "cancelled")
        _orders_db[request.order_id]["payment_status"] = "failed"
        _orders_db[request.order_id]["status"] = "cancelled"
        _orders_db[request.order_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        log.warning(f"결제 실패: order_id={request.order_id}, payment_id={request.payment_id}")
        
        return PaymentCallbackResponse(
            order_id=request.order_id,
            status="cancelled",
            payment_status="failed",
            message="결제에 실패했습니다."
        )


@router.get("/{order_id}/tracking", response_model=dict)
async def get_order_tracking(order_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """
    배송 추적 정보 조회
    
    - 운송장 번호 조회
    - 배송 상태 및 배송 시간 조회
    """
    # DB에서 주문 조회 시도
    try:
        order = db.get_order(order_id)
        if not order:
            # 메모리 저장소에서 조회
            if order_id not in _orders_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"주문을 찾을 수 없습니다: {order_id}"
                )
            order = _orders_db[order_id]
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
        if order_id not in _orders_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"주문을 찾을 수 없습니다: {order_id}"
            )
        order = _orders_db[order_id]
    
    # 배송 추적 정보 구성
    tracking_info = {
        "order_id": order_id,
        "shipping_status": order.get("shipping_status", "pending"),
        "tracking_number": order.get("tracking_number"),
        "shipped_at": order.get("shipped_at"),
        "delivered_at": order.get("delivered_at"),
        "estimated_delivery": None,  # 실제 구현 시 배송사 API에서 조회
        "tracking_history": [
            {
                "status": "pending",
                "location": "창고",
                "timestamp": order.get("created_at"),
                "description": "주문 접수"
            }
        ]
    }
    
    # 배송 시작 기록 추가
    if order.get("shipped_at"):
        tracking_info["tracking_history"].append({
            "status": "shipped",
            "location": "배송 센터",
            "timestamp": order.get("shipped_at"),
            "description": "배송 시작"
        })
    
    # 배송 완료 기록 추가
    if order.get("delivered_at"):
        tracking_info["tracking_history"].append({
            "status": "delivered",
            "location": "수령지",
            "timestamp": order.get("delivered_at"),
            "description": "배송 완료"
        })
    
    return tracking_info


@router.post("/shipping/status", response_model=ShippingStatusResponse)
async def update_shipping_status(request: UpdateShippingStatusRequest, db: SkinAnalysisDB = Depends(get_db)):
    """
    배송 상태 업데이트 (관리자 또는 배송 시스템에서 호출)
    
    - 배송 시작: 운송장 번호 등록
    - 배송 완료: 배송 완료 시간 기록
    """
    # DB에서 주문 조회 시도
    try:
        order = db.get_order(request.order_id)
        if not order:
            # 메모리 저장소에서 조회
            if request.order_id not in _orders_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"주문을 찾을 수 없습니다: {request.order_id}"
                )
            order = _orders_db[request.order_id]
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소 사용
        if request.order_id not in _orders_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"주문을 찾을 수 없습니다: {request.order_id}"
            )
        order = _orders_db[request.order_id]
    
    # 배송 상태 업데이트
    _orders_db[request.order_id]["shipping_status"] = request.shipping_status
    _orders_db[request.order_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if request.tracking_number:
        _orders_db[request.order_id]["tracking_number"] = request.tracking_number
    if request.shipped_at:
        _orders_db[request.order_id]["shipped_at"] = request.shipped_at
    if request.delivered_at:
        _orders_db[request.order_id]["delivered_at"] = request.delivered_at
    
    # 주문 상태도 함께 업데이트
    try:
        if request.shipping_status == "shipped":
            db.update_order_status(request.order_id, "shipped")
            _orders_db[request.order_id]["status"] = "shipped"
            # 배송 시작 알림 전송
            try:
                db.send_notification(
                    customer_id=_orders_db[request.order_id]["customer_id"],
                    notification_type="shipping",
                    title="배송 시작",
                    message=f"주문 {request.order_id}의 배송이 시작되었습니다.",
                    data={"order_id": request.order_id, "tracking_number": request.tracking_number}
                )
            except AttributeError:
                pass
        elif request.shipping_status == "delivered":
            db.update_order_status(request.order_id, "delivered")
            _orders_db[request.order_id]["status"] = "delivered"
            # 배송 완료 알림 전송
            try:
                db.send_notification(
                    customer_id=_orders_db[request.order_id]["customer_id"],
                    notification_type="delivery",
                    title="배송 완료",
                    message=f"주문 {request.order_id}이 배송 완료되었습니다.",
                    data={"order_id": request.order_id}
                )
            except AttributeError:
                pass
    except AttributeError:
        # DB 메서드가 없는 경우 메모리 저장소만 업데이트
        if request.shipping_status == "shipped":
            _orders_db[request.order_id]["status"] = "shipped"
        elif request.shipping_status == "delivered":
            _orders_db[request.order_id]["status"] = "delivered"
    
    log.info(f"배송 상태 업데이트: {request.order_id}, status={request.shipping_status}")
    
    return ShippingStatusResponse(
        order_id=request.order_id,
        shipping_status=request.shipping_status,
        tracking_number=request.tracking_number,
        message="배송 상태가 업데이트되었습니다."
    )


@router.post("/feedback", response_model=ProductFeedbackResponse)
async def submit_product_feedback(request: ProductFeedbackRequest, db: SkinAnalysisDB = Depends(get_db)):
    """
    제품 피드백 등록
    
    - 구매한 제품에 대한 리뷰 등록
    - 평점, 코멘트, 재구매 의사 저장
    """
    # 피드백 ID 생성
    feedback_id = f"FB-{uuid.uuid4().hex[:8]}"
    
    # DB에 피드백 저장
    db.create_product_feedback(
        feedback_id=feedback_id,
        order_id=request.order_id,
        customer_id="",  # 주문에서 customer_id 조회 필요
        product_id=request.product_id,
        rating=request.rating,
        comment=request.comment,
        would_repurchase=request.would_repurchase,
    )
    
    log.info(f"피드백 등록: {feedback_id}, 제품: {request.product_id}, 평점: {request.rating}")
    
    return ProductFeedbackResponse(
        feedback_id=feedback_id,
        order_id=request.order_id,
        product_id=request.product_id,
        rating=request.rating,
        created_at=datetime.now(timezone.utc).isoformat(),
        message="피드백이 등록되었습니다."
    )


@router.get("/products/{product_id}/feedback", response_model=ProductFeedbackListResponse)
async def get_product_feedback(product_id: str, limit: int = 20, db: SkinAnalysisDB = Depends(get_db)):
    """
    제품 피드백 조회
    
    - 특정 제품의 모든 리뷰 조회
    - 평균 평점 계산
    """
    # DB에서 피드백 조회
    feedbacks = db.get_product_feedback(product_id, limit)
    
    # 평균 평점 조회
    average_rating = db.get_product_average_rating(product_id)
    
    # 리뷰 목록 구성
    return ProductFeedbackListResponse(
        product_id=product_id,
        total_reviews=len(feedbacks),
        average_rating=average_rating,
        reviews=feedbacks
    )


@router.get("/products/ready-made", response_model=ReadyMadeProductsListResponse)
async def get_ready_made_products(db: SkinAnalysisDB = Depends(get_db)):
    """
    기성품 목록 조회
    
    - 미리 준비된 5종의 기성품 목록 조회
    - 재고 수량, 가격, 카테고리 정보 제공
    """
    # DB에서 기성품 목록 조회 (is_ready_made=1)
    try:
        products = db.get_ready_made_products()
        ready_made_products = [
            ReadyMadeProductResponse(
                product_id=p["product_id"],
                product_name=p["product_name"],
                category=p["category"],
                price=p["price"],
                stock_quantity=p["stock_quantity"],
                description=p.get("description")
            )
            for p in products
        ]
        
        return ReadyMadeProductsListResponse(
            ready_made_products=ready_made_products,
            total_products=len(ready_made_products)
        )
    except AttributeError:
        # DB 메서드가 없는 경우 빈 목록 반환
        log.warning("get_ready_made_products 메서드가 없습니다. 빈 목록을 반환합니다.")
        return ReadyMadeProductsListResponse(
            ready_made_products=[],
            total_products=0
        )
