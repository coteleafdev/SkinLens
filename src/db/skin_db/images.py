"""images 도메인 저장소 Mixin."""
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


class ImagesMixin:
    """images 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_image_upload(
        self,
        customer_id: str,
        upload_id: str,
        original_filename: str,
        file_path: str,
        file_size: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        rotation_angle: int = 0,
    ) -> bool:
        """이미지 업로드 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO image_uploads 
                    (customer_id, upload_id, original_filename, file_path, file_size, width, height, rotation_angle)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (customer_id, upload_id, original_filename, file_path, file_size, width, height, rotation_angle),
                )
                self._conn.commit()
                log.info("[DB] 이미지 업로드 생성: upload_id=%s", upload_id)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] 이미지 업로드 중복: upload_id=%s", upload_id)
                return False


    def update_image_upload_status(
        self,
        upload_id: str,
        upload_status: str,
        processed_at: Optional[datetime] = None,
    ) -> bool:
        """이미지 업로드 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE image_uploads 
                SET upload_status = ?, processed_at = COALESCE(?, processed_at)
                WHERE upload_id = ?
                """,
                (upload_status, processed_at, upload_id),
            )
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 이미지 업로드 상태 업데이트: upload_id=%s, status=%s", upload_id, upload_status)
            return updated


    def get_image_uploads(
        self,
        customer_id: Optional[str] = None,
        upload_status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """이미지 업로드 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = "SELECT * FROM image_uploads WHERE 1=1"
            params = []
            
            if customer_id:
                query += " AND customer_id = ?"
                params.append(customer_id)
            if upload_status:
                query += " AND upload_status = ?"
                params.append(upload_status)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 푸시 알림 선호도 ───────────────────────────────────────────────────────

