"""products 도메인 저장소 Mixin."""
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


class ProductsMixin:
    """products 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_product(
        self,
        product_id: str,
        product_name: str,
        category: str,
        key_ingredients: List[str],
        efficacy: str,
        target_skin_types: Optional[List[str]] = None,
        target_concerns: Optional[List[str]] = None,
        is_ready_made: bool = False,
        description: Optional[str] = None,
    ) -> bool:
        """제품 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO products
                    (product_id, product_name, category, key_ingredients, efficacy,
                     target_skin_types, target_concerns, is_ready_made, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_id,
                    product_name,
                    category,
                    json.dumps(key_ingredients, ensure_ascii=False),
                    efficacy,
                    json.dumps(target_skin_types, ensure_ascii=False) if target_skin_types else None,
                    json.dumps(target_concerns, ensure_ascii=False) if target_concerns else None,
                    1 if is_ready_made else 0,
                    description,
                ))
                self._conn.commit()
                log.info("[DB] 제품 생성: product_id=%s, is_ready_made=%s", product_id, is_ready_made)
                return True
            except sqlite3.IntegrityError:
                return False


    def update_product(
        self,
        product_id: str,
        product_name: Optional[str] = None,
        category: Optional[str] = None,
        key_ingredients: Optional[List[str]] = None,
        efficacy: Optional[str] = None,
    ) -> bool:
        """제품 정보 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            updates = []
            params = []
            
            if product_name:
                updates.append("product_name = ?")
                params.append(product_name)
            if category:
                updates.append("category = ?")
                params.append(category)
            if key_ingredients:
                updates.append("key_ingredients = ?")
                params.append(json.dumps(key_ingredients, ensure_ascii=False))
            if efficacy:
                updates.append("efficacy = ?")
                params.append(efficacy)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(product_id)
            
            query = f"UPDATE products SET {', '.join(updates)} WHERE product_id = ?"
            cursor.execute(query, params)
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 제품 업데이트: product_id=%s", product_id)
            return updated


    def delete_product(self, product_id: str) -> bool:
        """제품 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM products WHERE product_id = ?
            """, (product_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 제품 삭제: product_id=%s", product_id)
            return deleted


    def list_products(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """제품 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT product_id, product_name, category, key_ingredients, efficacy,
                       target_skin_types, target_concerns, created_at, updated_at
                FROM products
                WHERE 1=1
            """
            params = []
            if category:
                query += " AND category = ?"
                params.append(category)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "product_id": row[0],
                    "product_name": row[1],
                    "category": row[2],
                    "key_ingredients": json.loads(row[3]) if row[3] else [],
                    "efficacy": row[4],
                    "target_skin_types": json.loads(row[5]) if row[5] else [],
                    "target_concerns": json.loads(row[6]) if row[6] else [],
                    "created_at": row[7],
                    "updated_at": row[8],
                }
                for row in rows
            ]

    # ── 사용자 세션 관련 메서드 ─────────────────────────────────────────────


    def get_ready_made_products(self) -> List[Dict[str, Any]]:
        """기성품 목록 조회 (is_ready_made=1)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT product_id, product_name, category, price, stock_quantity, description
                FROM products 
                WHERE is_ready_made = 1 AND is_active = 1
                ORDER BY product_id
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "product_id": row[0],
                    "product_name": row[1],
                    "category": row[2],
                    "price": row[3],
                    "stock_quantity": row[4],
                    "description": row[5] if len(row) > 5 else None,
                }
                for row in rows
            ]

    # ── 주문 통계/분석 ─────────────────────────────────────────────────────

