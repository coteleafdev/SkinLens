"""surveys 도메인 저장소 Mixin."""
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


class SurveysMixin:
    """surveys 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_survey(
        self,
        survey_id: str,
        customer_id: str,
        survey_data: str
    ) -> bool:
        """설문 데이터 생성"""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT INTO surveys (survey_id, customer_id, survey_data)
                    VALUES (?, ?, ?)
                """, (survey_id, customer_id, survey_data))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    

    def get_survey(self, survey_id: str) -> Optional[Dict]:
        """설문 데이터 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, survey_id, customer_id, survey_data, is_active, created_at, updated_at
                FROM surveys
                WHERE survey_id = ? AND is_active = 1
            """, (survey_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "survey_id": row[1],
                    "customer_id": row[2],
                    "survey_data": row[3],
                    "is_active": bool(row[4]),
                    "created_at": row[5],
                    "updated_at": row[6],
                }
            return None
    

    def get_surveys(self, customer_id: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """사용자의 설문 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, survey_id, customer_id, survey_data, is_active, created_at, updated_at
                FROM surveys
                WHERE customer_id = ? AND is_active = 1
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (customer_id, limit, offset))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "survey_id": row[1],
                    "customer_id": row[2],
                    "survey_data": row[3],
                    "is_active": bool(row[4]),
                    "created_at": row[5],
                    "updated_at": row[6],
                }
                for row in rows
            ]
    

    def update_survey(self, survey_id: str, survey_data: str) -> bool:
        """설문 데이터 수정"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE surveys
                SET survey_data = ?, updated_at = ?
                WHERE survey_id = ?
            """, (survey_data, datetime.now(timezone.utc), survey_id))
            self._conn.commit()
            return cursor.rowcount > 0
    

    def delete_survey(self, survey_id: str) -> bool:
        """설문 데이터 삭제 (비활성화)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE surveys
                SET is_active = 0
                WHERE survey_id = ?
            """, (survey_id,))
            self._conn.commit()
            return cursor.rowcount > 0
    
    # ── 비밀번호 리셋 토큰 관련 메서드 ───────────────────────────────────────────
    
