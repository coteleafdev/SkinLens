"""customers 도메인 저장소 Mixin."""
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


class CustomersMixin:
    """customers 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_customer_profile(
        self,
        customer_id: str,
        email: Optional[str] = None,
        name: str = None,
        contact: str = None,
        address: str = None,
    ) -> bool:
        """고객 프로필 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO customer_profiles (customer_id, email, name, contact, address)
                    VALUES (?, ?, ?, ?, ?)
                """, (customer_id, email, name, contact, address))
                self._conn.commit()
                log.info("[DB] 고객 프로필 생성: customer_id=%s", customer_id)
                return True
            except sqlite3.IntegrityError:
                return False


    def get_customer_profile(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """고객 프로필 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT customer_id, email, name, contact, address, status, created_at, updated_at,
                       last_login_at, total_analyses
                FROM customer_profiles WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": row[0],
                    "email": row[1],
                    "name": row[2],
                    "contact": row[3],
                    "address": row[4],
                    "status": row[5],
                    "created_at": row[6],
                    "updated_at": row[7],
                    "last_login_at": row[8],
                    "total_analyses": row[9],
                }
            return None


    def update_customer_status(self, customer_id: str, status: str) -> bool:
        """고객 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE customer_profiles
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE customer_id = ?
            """, (status, customer_id))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 고객 상태 업데이트: customer_id=%s, status=%s", customer_id, status)
            return updated


    def list_customers(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """고객 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT customer_id, email, name, status, created_at, updated_at,
                       last_login_at, total_analyses
                FROM customer_profiles
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "customer_id": row[0],
                    "email": row[1],
                    "name": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                    "last_login_at": row[6],
                    "total_analyses": row[7],
                }
                for row in rows
            ]


    def delete_customer_profile(self, customer_id: str) -> bool:
        """고객 프로필 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM customer_profiles WHERE customer_id = ?
            """, (customer_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 고객 프로필 삭제: customer_id=%s", customer_id)
            return deleted

    # ── 제품 관리 관련 메서드 ─────────────────────────────────────────────────

