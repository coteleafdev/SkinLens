"""sync 도메인 저장소 Mixin."""
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


class SyncMixin:
    """sync 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_sync_log(
        self,
        sync_type: str,
        direction: str,
        source_system: Optional[str] = None,
        target_system: Optional[str] = None,
    ) -> str:
        """동기화 로그 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            import uuid
            log_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO external_sync_logs (id, sync_type, direction, source_system, target_system)
                VALUES (?, ?, ?, ?, ?)
            """, (log_id, sync_type, direction, source_system, target_system))
            self._conn.commit()
            log.info("[DB] 동기화 로그 생성: log_id=%s, type=%s", log_id, sync_type)
            return log_id


    def update_sync_log(
        self,
        log_id: str,
        status: str,
        records_count: int = 0,
        error_message: Optional[str] = None,
    ) -> bool:
        """동기화 로그 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE external_sync_logs
                SET status = ?, records_count = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, records_count, error_message, log_id))
            self._conn.commit()
            return cursor.rowcount > 0


    def get_sync_logs(
        self,
        sync_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """동기화 로그 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, sync_type, direction, status, source_system, target_system,
                       records_count, error_message, started_at, completed_at
                FROM external_sync_logs
                WHERE 1=1
            """
            params = []
            if sync_type:
                query += " AND sync_type = ?"
                params.append(sync_type)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "sync_type": row[1],
                    "direction": row[2],
                    "status": row[3],
                    "source_system": row[4],
                    "target_system": row[5],
                    "records_count": row[6],
                    "error_message": row[7],
                    "started_at": row[8],
                    "completed_at": row[9],
                }
                for row in rows
            ]

    # ── OAuth 관련 메서드 ─────────────────────────────────────────────────────

