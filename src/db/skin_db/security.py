"""security 도메인 저장소 Mixin."""
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


class SecurityMixin:
    """security 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def set_user_role(
        self,
        customer_id: str,
        role: str,
        granted_by: Optional[str] = None,
    ) -> bool:
        """사용자 역할 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_roles (customer_id, role, granted_by)
                VALUES (?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    role = ?, granted_by = ?, granted_at = CURRENT_TIMESTAMP
            """, (customer_id, role, granted_by, role, granted_by))
            self._conn.commit()
            log.info("[DB] 사용자 역할 설정: customer_id=%s, role=%s", customer_id, role)
            return True


    def get_user_role(self, customer_id: str) -> Optional[str]:
        """사용자 역할 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT role FROM user_roles WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            return row[0] if row else "customer"


    def list_users_by_role(self, role: str, limit: int = 100) -> List[Dict[str, Any]]:
        """역할별 사용자 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT customer_id, role, granted_at, granted_by
                FROM user_roles
                WHERE role = ?
                ORDER BY granted_at DESC
                LIMIT ?
            """, (role, limit))
            rows = cursor.fetchall()
            return [
                {
                    "customer_id": row[0],
                    "role": row[1],
                    "granted_at": row[2],
                    "granted_by": row[3],
                }
                for row in rows
            ]

    # ── 차단된 IP 관련 메서드 ───────────────────────────────────────────────


    def block_ip(
        self,
        ip_address: str,
        reason: Optional[str] = None,
        blocked_by: Optional[str] = None,
        expires_in_hours: Optional[int] = None,
        is_permanent: bool = False,
    ) -> bool:
        """IP 차단"""
        with self._lock:
            cursor = self._conn.cursor()
            expires_at = None
            if expires_in_hours and not is_permanent:
                expires_at = (datetime.now() + timedelta(hours=expires_in_hours)).isoformat()
            
            cursor.execute("""
                INSERT INTO blocked_ips (ip_address, reason, blocked_by, expires_at, is_permanent)
                VALUES (?, ?, ?, ?, ?)
            """, (ip_address, reason, blocked_by, expires_at, 1 if is_permanent else 0))
            self._conn.commit()
            log.warning("[DB] IP 차단: ip=%s, reason=%s", ip_address, reason)
            return True


    def unblock_ip(self, ip_address: str) -> bool:
        """IP 차단 해제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM blocked_ips WHERE ip_address = ?
            """, (ip_address,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] IP 차단 해제: ip=%s", ip_address)
            return deleted


    def is_ip_blocked(self, ip_address: str) -> bool:
        """IP 차단 여부 확인"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM blocked_ips
                WHERE ip_address = ? AND (is_permanent = 1 OR expires_at > CURRENT_TIMESTAMP)
            """, (ip_address,))
            return cursor.fetchone()[0] > 0


    def get_blocked_ips(self, limit: int = 100) -> List[Dict[str, Any]]:
        """차단된 IP 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT ip_address, blocked_at, blocked_by, reason, expires_at, is_permanent
                FROM blocked_ips
                WHERE is_permanent = 1 OR expires_at > CURRENT_TIMESTAMP
                ORDER BY blocked_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "ip_address": row[0],
                    "blocked_at": row[1],
                    "blocked_by": row[2],
                    "reason": row[3],
                    "expires_at": row[4],
                    "is_permanent": bool(row[5]),
                }
                for row in rows
            ]

    # ── 일일 통계 관련 메서드 ───────────────────────────────────────────────

