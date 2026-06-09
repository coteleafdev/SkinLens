"""sessions 도메인 저장소 Mixin."""
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


class SessionsMixin:
    """sessions 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_session(
        self,
        session_id: str,
        customer_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """사용자 세션 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_sessions (id, customer_id, ip_address, user_agent)
                VALUES (?, ?, ?, ?)
            """, (session_id, customer_id, ip_address, user_agent))
            self._conn.commit()
            return True


    def update_session_activity(self, session_id: str) -> bool:
        """세션 활동 시간 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE user_sessions
                SET last_activity_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (session_id,))
            self._conn.commit()
            return cursor.rowcount > 0


    def end_session(self, session_id: str) -> bool:
        """세션 종료"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE user_sessions
                SET is_active = 0
                WHERE id = ?
            """, (session_id,))
            self._conn.commit()
            return cursor.rowcount > 0


    def get_active_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """활성 세션 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, ip_address, user_agent, started_at, last_activity_at
                FROM user_sessions
                WHERE is_active = 1
                ORDER BY last_activity_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "session_id": row[0],
                    "customer_id": row[1],
                    "ip_address": row[2],
                    "user_agent": row[3],
                    "started_at": row[4],
                    "last_activity_at": row[5],
                }
                for row in rows
            ]

    # ── 이상 활동 관련 메서드 ─────────────────────────────────────────────────

