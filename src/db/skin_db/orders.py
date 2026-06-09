"""orders 도메인 저장소 Mixin."""
import logging
import sqlite3
import json
import threading
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone  # [FIX] timezone 추가(원본 누락)
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.utils.config import load_config as _load_config

log = logging.getLogger(__name__)


class OrdersMixin:
    """orders 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def save_order_item(
        self,
        order_id: str,
        product_id: str,
        product_name: str,
        quantity: int,
        price: float,
        subtotal: float,
    ) -> bool:
        """주문 항목 저장"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO order_items 
                (order_id, product_id, product_name, quantity, price, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, product_id, product_name, quantity, price, subtotal),
            )
            self._conn.commit()
            log.info("[DB] 주문 항목 저장: order_id=%s, product_id=%s", order_id, product_id)
            return True


    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """주문 조회 (암호화된 주소 처리)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, customer_id, status, total_amount, payment_method, payment_status,
                       shipping_status, shipping_address, barcode_number, recommendation_source,
                       analysis_job_id, created_at, updated_at
                FROM orders WHERE id = ?
                """,
                (order_id,),
            )
            row = cursor.fetchone()
            if row:
                # 암호화된 주소는 그대로 반환 (보안 유지)
                return {
                    "order_id": row[0],
                    "customer_id": row[1],
                    "status": row[2],
                    "total_amount": row[3],
                    "payment_method": row[4],
                    "payment_status": row[5],
                    "shipping_status": row[6],
                    "shipping_address": row[7],  # 암호화된 상태 유지
                    "barcode_number": row[8],
                    "recommendation_source": row[9],
                    "analysis_job_id": row[10],
                    "created_at": row[11],
                    "updated_at": row[12],
                }
            return None


    def get_order_items(self, order_id: str) -> List[Dict[str, Any]]:
        """주문 항목 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, order_id, product_id, product_name, quantity, price, subtotal, created_at
                FROM order_items WHERE order_id = ?
                """,
                (order_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]


    def get_customer_orders(self, customer_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """고객 주문 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, customer_id, status, total_amount, payment_status, shipping_status,
                       created_at, updated_at
                FROM orders WHERE customer_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]


    def update_order_status(self, order_id: str, status: str) -> bool:
        """주문 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (status, order_id),
            )
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 주문 상태 업데이트: order_id=%s, status=%s", order_id, status)
            return updated

    # ── 재고 관리 ─────────────────────────────────────────────────────────────


    def check_stock(self, product_id: str, quantity: int) -> bool:
        """재고 확인"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT stock_quantity, is_active FROM products WHERE product_id = ?
                """,
                (product_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            stock_quantity, is_active = row
            return is_active and stock_quantity >= quantity


    def deduct_stock(self, product_id: str, quantity: int) -> bool:
        """재고 차감"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE products SET stock_quantity = stock_quantity - ? 
                WHERE product_id = ? AND stock_quantity >= ?
                """,
                (quantity, product_id, quantity),
            )
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 재고 차감: product_id=%s, quantity=%s", product_id, quantity)
            return updated


    def get_product_stock(self, product_id: str) -> Optional[Dict[str, Any]]:
        """제품 재고 정보 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT product_id, product_name, stock_quantity, price, is_active
                FROM products WHERE product_id = ?
                """,
                (product_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "product_id": row[0],
                    "product_name": row[1],
                    "stock_quantity": row[2],
                    "price": row[3],
                    "is_active": bool(row[4]),
                }
            return None


    def add_stock(self, product_id: str, quantity: int) -> bool:
        """재고 추가"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE products SET stock_quantity = stock_quantity + ? 
                WHERE product_id = ?
                """,
                (quantity, product_id),
            )
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 재고 추가: product_id=%s, quantity=%s", product_id, quantity)
            return updated


    def get_sales_statistics(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """판매 통계 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(total_amount) as total_revenue,
                    AVG(total_amount) as average_order_value
                FROM orders 
                WHERE created_at >= ? AND created_at <= ?
                """,
                (start_date, end_date),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "total_orders": row[0] or 0,
                    "total_revenue": row[1] or 0.0,
                    "average_order_value": row[2] or 0.0,
                }
            return {
                "total_orders": 0,
                "total_revenue": 0.0,
                "average_order_value": 0.0,
            }


    def get_popular_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        """인기 제품 조회 (판매량 기준)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT 
                    product_id,
                    product_name,
                    SUM(quantity) as total_quantity,
                    SUM(subtotal) as total_revenue
                FROM order_items
                GROUP BY product_id, product_name
                ORDER BY total_quantity DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]


    def get_daily_sales(self, days: int = 30) -> List[Dict[str, Any]]:
        """일별 판매 추이 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as orders,
                    SUM(total_amount) as revenue
                FROM orders
                WHERE created_at >= DATE('now', '-' || ? || ' days')
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                """,
                (days,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]


    def get_customer_purchase_pattern(self, customer_id: str) -> Dict[str, Any]:
        """고객별 구매 패턴 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(total_amount) as total_spent,
                    AVG(total_amount) as average_order_value,
                    MAX(created_at) as last_purchase_date
                FROM orders
                WHERE customer_id = ?
                """,
                (customer_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": customer_id,
                    "total_orders": row[0] or 0,
                    "total_spent": row[1] or 0.0,
                    "average_order_value": row[2] or 0.0,
                    "last_purchase_date": row[3],
                }
            return {
                "customer_id": customer_id,
                "total_orders": 0,
                "total_spent": 0.0,
                "average_order_value": 0.0,
                "last_purchase_date": None,
            }

    # ── 알림 관리 ─────────────────────────────────────────────────────────────


    def save_order(
        self,
        order_id: str,
        customer_id: str,
        status: str,
        total_amount: float,
        payment_method: str,
        payment_status: str,
        shipping_status: str,
        shipping_address: Dict[str, str],
        barcode_number: str,
        recommendation_source: Optional[str] = None,
        analysis_job_id: Optional[str] = None,
    ) -> bool:
        """주문 저장 (암호화 적용)"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                # 배송 주소 암호화
                encrypted_address = self._encrypt_address(shipping_address)
                
                cursor.execute(
                    """
                    INSERT INTO orders 
                    (id, customer_id, status, total_amount, payment_method, payment_status, 
                     shipping_status, shipping_address, barcode_number, recommendation_source, analysis_job_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (order_id, customer_id, status, total_amount, payment_method, payment_status,
                     shipping_status, encrypted_address, barcode_number, 
                     recommendation_source, analysis_job_id),
                )
                self._conn.commit()
                log.info("[DB] 주문 저장 (암호화 적용): order_id=%s, customer_id=%s", order_id, customer_id)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] 주문 이미 존재: order_id=%s", order_id)
                return False

    # ── 피부 일기 ─────────────────────────────────────────────────────────────

