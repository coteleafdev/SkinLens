"""
Orders API 테스트 - 주문 관련 API
"""
import pytest
from fastapi.testclient import TestClient
from src.server.routers.orders import (
    _orders_db,
    _order_items_db,
    _purchase_history_db,
    CreateOrderRequest,
    OrderItem,
    ShippingAddress,
)


class TestOrdersAPI:
    """Orders API 엔드포인트 테스트"""

    def setup_method(self):
        """각 테스트 전에 데이터베이스 초기화"""
        _orders_db.clear()
        _order_items_db.clear()
        _purchase_history_db.clear()

    def test_create_order_success(self, auth_client):
        """주문 생성 성공"""
        request_data = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 2,
                    "price": 15000.0
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "credit_card",
            "recommendation_source": "skin_analysis",
            "analysis_job_id": "job123"
        }
        
        response = auth_client.post("/v1/orders", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert "order_id" in data
        assert data["status"] == "pending_payment"
        assert data["total_amount"] == 30000.0
        assert "payment_url" in data
        assert "created_at" in data

    def test_create_order_multiple_items(self, auth_client):
        """여러 상품 주문 생성"""
        request_data = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 2,
                    "price": 15000.0
                },
                {
                    "product_id": "prod002",
                    "quantity": 1,
                    "price": 25000.0
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "naver_pay"
        }
        
        response = auth_client.post("/v1/orders", json=request_data)
        assert response.status_code == 201
        data = response.json()
        assert data["total_amount"] == 55000.0

    def test_create_order_invalid_quantity(self, auth_client):
        """잘못된 수량으로 주문 생성 실패"""
        request_data = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 0,  # 유효하지 않은 수량
                    "price": 15000.0
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "credit_card"
        }
        
        response = auth_client.post("/v1/orders", json=request_data)
        assert response.status_code == 422  # Validation error

    def test_create_order_invalid_price(self, auth_client):
        """잘못된 가격으로 주문 생성 실패"""
        request_data = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 1,
                    "price": -1000.0  # 유효하지 않은 가격
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "credit_card"
        }
        
        response = auth_client.post("/v1/orders", json=request_data)
        assert response.status_code == 422  # Validation error

    def test_get_order_status_success(self, auth_client):
        """주문 상태 조회 성공"""
        # 먼저 주문 생성
        create_request = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 1,
                    "price": 15000.0
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "credit_card"
        }
        
        create_response = auth_client.post("/v1/orders", json=create_request)
        order_id = create_response.json()["order_id"]
        
        # 주문 상태 조회
        response = auth_client.get(f"/v1/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert "status" in data
        assert "total_amount" in data
        assert "items" in data
        assert "shipping_address" in data
        assert "payment_status" in data
        assert "shipping_status" in data

    def test_get_order_status_not_found(self, auth_client):
        """존재하지 않는 주문 조회 실패"""
        response = auth_client.get("/v1/orders/nonexistent")
        assert response.status_code == 404

    def test_cancel_order_success(self, auth_client):
        """주문 취소 성공"""
        # 먼저 주문 생성
        create_request = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 1,
                    "price": 15000.0
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "credit_card"
        }
        
        create_response = auth_client.post("/v1/orders", json=create_request)
        order_id = create_response.json()["order_id"]
        
        # 주문 취소
        cancel_request = {"reason": "단순 변심"}
        response = auth_client.post(f"/v1/orders/{order_id}/cancel", json=cancel_request)
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert data["status"] == "cancelled"
        assert "cancelled_at" in data
        assert "refund_amount" in data
        assert "refund_status" in data

    def test_cancel_order_not_found(self, auth_client):
        """존재하지 않는 주문 취소 실패"""
        cancel_request = {"reason": "단순 변심"}
        response = auth_client.post("/v1/orders/nonexistent/cancel", json=cancel_request)
        assert response.status_code == 404

    def test_cancel_shipped_order(self, auth_client):
        """이미 배송된 주문 취소 실패"""
        # 주문 생성
        create_request = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 1,
                    "price": 15000.0
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "credit_card"
        }
        
        create_response = auth_client.post("/v1/orders", json=create_request)
        order_id = create_response.json()["order_id"]
        
        # 주문 상태를 shipped로 변경
        _orders_db[order_id]["status"] = "shipped"
        
        # 주문 취소 시도
        cancel_request = {"reason": "단순 변심"}
        response = auth_client.post(f"/v1/orders/{order_id}/cancel", json=cancel_request)
        assert response.status_code == 400

    def test_get_purchase_history_success(self, auth_client):
        """고객 구매 이력 조회 성공"""
        # 여러 주문 생성
        for i in range(3):
            create_request = {
                "customer_id": "customer123",
                "items": [
                    {
                        "product_id": f"prod00{i}",
                        "quantity": 1,
                        "price": 15000.0
                    }
                ],
                "shipping_address": {
                    "recipient": "홍길동",
                    "phone": "010-1234-5678",
                    "address": "서울시 강남구",
                    "zip_code": "12345"
                },
                "payment_method": "credit_card"
            }
            auth_client.post("/v1/orders", json=create_request)
        
        # 구매 이력 조회
        response = auth_client.get("/v1/orders/customers/customer123/purchase-history")
        assert response.status_code == 200
        data = response.json()
        assert data["customer_id"] == "customer123"
        assert data["total_orders"] == 3
        assert "total_spent" in data
        assert "orders" in data
        assert len(data["orders"]) == 3

    def test_get_purchase_history_with_status_filter(self, auth_client):
        """상태 필터와 함께 구매 이력 조회"""
        # 주문 생성
        create_request = {
            "customer_id": "customer123",
            "items": [
                {
                    "product_id": "prod001",
                    "quantity": 1,
                    "price": 15000.0
                }
            ],
            "shipping_address": {
                "recipient": "홍길동",
                "phone": "010-1234-5678",
                "address": "서울시 강남구",
                "zip_code": "12345"
            },
            "payment_method": "credit_card"
        }
        
        create_response = auth_client.post("/v1/orders", json=create_request)
        order_id = create_response.json()["order_id"]
        
        # 주문 상태를 paid로 변경
        _orders_db[order_id]["status"] = "paid"
        
        # paid 상태만 필터링하여 조회
        response = auth_client.get("/v1/orders/customers/customer123/purchase-history?status=paid")
        assert response.status_code == 200
        data = response.json()
        assert all(order["status"] == "paid" for order in data["orders"])

    def test_get_purchase_history_with_pagination(self, auth_client):
        """페이지네이션과 함께 구매 이력 조회"""
        # 여러 주문 생성
        for i in range(5):
            create_request = {
                "customer_id": "customer123",
                "items": [
                    {
                        "product_id": f"prod00{i}",
                        "quantity": 1,
                        "price": 15000.0
                    }
                ],
                "shipping_address": {
                    "recipient": "홍길동",
                    "phone": "010-1234-5678",
                    "address": "서울시 강남구",
                    "zip_code": "12345"
                },
                "payment_method": "credit_card"
            }
            auth_client.post("/v1/orders", json=create_request)
        
        # 페이지네이션 적용 (limit=2, offset=0)
        response = auth_client.get("/v1/orders/customers/customer123/purchase-history?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total_orders"] == 5
        assert len(data["orders"]) == 2

    def test_generate_order_id_format(self):
        """주문 ID 형식 검증"""
        from src.server.routers.orders import _generate_order_id
        order_id = _generate_order_id()
        assert order_id.startswith("ORD-")
        assert len(order_id.split("-")) == 3

    def test_calculate_total_amount(self):
        """총 주문 금액 계산 검증"""
        from src.server.routers.orders import _calculate_total_amount
        items = [
            OrderItem(product_id="prod001", quantity=2, price=15000.0),
            OrderItem(product_id="prod002", quantity=1, price=25000.0)
        ]
        total = _calculate_total_amount(items)
        assert total == 55000.0

    def test_order_response_model(self):
        """주문 응답 모델 검증"""
        from src.server.routers.orders import OrderResponse
        response = OrderResponse(
            order_id="ORD-123",
            status="pending_payment",
            total_amount=30000.0,
            created_at="2024-01-01T00:00:00Z",
            payment_url="https://payment.example.com/pay/ORD-123"
        )
        assert response.order_id == "ORD-123"
        assert response.status == "pending_payment"
        assert response.total_amount == 30000.0

    def test_shipping_address_model(self):
        """배송지 모델 검증"""
        address = ShippingAddress(
            recipient="홍길동",
            phone="010-1234-5678",
            address="서울시 강남구",
            zip_code="12345"
        )
        assert address.recipient == "홍길동"
        assert address.phone == "010-1234-5678"
