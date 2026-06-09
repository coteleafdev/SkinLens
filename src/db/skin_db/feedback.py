"""feedback 도메인 저장소 Mixin."""
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


class FeedbackMixin:
    """feedback 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_product_feedback(
        self,
        feedback_id: str,
        order_id: str,
        customer_id: str,
        product_id: str,
        rating: int,
        comment: Optional[str] = None,
        would_repurchase: Optional[bool] = None,
    ) -> bool:
        """제품 피드백 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO product_feedback 
                (feedback_id, order_id, customer_id, product_id, rating, comment, would_repurchase)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, order_id, customer_id, product_id, rating, comment, 1 if would_repurchase else 0 if would_repurchase is not None else None),
            )
            self._conn.commit()
            log.info("[DB] 제품 피드백 생성: feedback_id=%s, product_id=%s, rating=%s", feedback_id, product_id, rating)
            return True


    def get_product_feedback(self, product_id: str, limit: int = 20) -> List[Dict]:
        """제품별 피드백 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT feedback_id, order_id, customer_id, product_id, rating, comment, would_repurchase, created_at
                FROM product_feedback
                WHERE product_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (product_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]


    def get_customer_feedback(self, customer_id: str, limit: int = 20) -> List[Dict]:
        """고객별 피드백 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT feedback_id, order_id, customer_id, product_id, rating, comment, would_repurchase, created_at
                FROM product_feedback
                WHERE customer_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]


    def get_product_average_rating(self, product_id: str) -> float:
        """제품 평균 평점 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT AVG(rating) as avg_rating
                FROM product_feedback
                WHERE product_id = ?
                """,
                (product_id,),
            )
            row = cursor.fetchone()
            return round(row[0], 1) if row and row[0] else 0.0

    # ── 주문 관리 ─────────────────────────────────────────────────────────────

