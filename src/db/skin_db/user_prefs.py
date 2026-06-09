"""user_prefs 도메인 저장소 Mixin."""
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


class UserPrefsMixin:
    """user_prefs 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def set_user_language(self, customer_id: str, language: str) -> bool:
        """사용자 언어 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_preferences (customer_id, language)
                VALUES (?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET language = ?, updated_at = CURRENT_TIMESTAMP
            """, (customer_id, language, language))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 사용자 언어 설정: customer_id=%s, language=%s", customer_id, language)
            return updated


    def get_user_language(self, customer_id: str) -> str:
        """사용자 언어 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT language FROM user_preferences WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            return row[0] if row else "ko"


    def set_user_timezone(self, customer_id: str, timezone: str) -> bool:
        """사용자 시간대 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_preferences (customer_id, timezone)
                VALUES (?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET timezone = ?, updated_at = CURRENT_TIMESTAMP
            """, (customer_id, timezone, timezone))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 사용자 시간대 설정: customer_id=%s, timezone=%s", customer_id, timezone)
            return updated


    def get_user_timezone(self, customer_id: str) -> str:
        """사용자 시간대 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT timezone FROM user_preferences WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            return row[0] if row else "Asia/Seoul"


    def get_user_preferences(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """사용자 설정 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT customer_id, language, timezone, created_at, updated_at
                FROM user_preferences WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": row[0],
                    "language": row[1],
                    "timezone": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                }
            return None

    # ── 북마크 관련 메서드 ─────────────────────────────────────────────────────


    def add_bookmark(self, customer_id: str, analysis_id: int, notes: Optional[str] = None) -> bool:
        """분석 결과 북마크 추가"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO analysis_bookmarks (customer_id, analysis_id, notes)
                    VALUES (?, ?, ?)
                """, (customer_id, analysis_id, notes))
                self._conn.commit()
                log.info("[DB] 북마크 추가: customer_id=%s, analysis_id=%d", customer_id, analysis_id)
                return True
            except sqlite3.IntegrityError:
                # 이미 북마크된 경우
                return False


    def remove_bookmark(self, customer_id: str, analysis_id: int) -> bool:
        """분석 결과 북마크 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM analysis_bookmarks
                WHERE customer_id = ? AND analysis_id = ?
            """, (customer_id, analysis_id))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 북마크 삭제: customer_id=%s, analysis_id=%d", customer_id, analysis_id)
            return deleted


    def get_bookmarks(self, customer_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """고객의 북마크 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT b.id, b.analysis_id, b.notes, b.created_at,
                       a.original_filename, a.created_at as analysis_date,
                       a.overall_score_original, a.overall_score_restored
                FROM analysis_bookmarks b
                JOIN analyses a ON b.analysis_id = a.id
                WHERE b.customer_id = ?
                ORDER BY b.created_at DESC
                LIMIT ? OFFSET ?
            """, (customer_id, limit, offset))
            rows = cursor.fetchall()
            return [
                {
                    "bookmark_id": row[0],
                    "analysis_id": row[1],
                    "notes": row[2],
                    "bookmarked_at": row[3],
                    "original_filename": row[4],
                    "analysis_date": row[5],
                    "overall_score_original": row[6],
                    "overall_score_restored": row[7],
                }
                for row in rows
            ]


    def is_bookmarked(self, customer_id: str, analysis_id: int) -> bool:
        """분석 결과 북마크 여부 확인"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM analysis_bookmarks
                WHERE customer_id = ? AND analysis_id = ?
            """, (customer_id, analysis_id))
            return cursor.fetchone()[0] > 0

    # ── 알림 설정 관련 메서드 ─────────────────────────────────────────────────

