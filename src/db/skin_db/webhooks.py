"""webhooks 도메인 저장소 Mixin."""
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


class WebhooksMixin:
    """webhooks 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_webhook(
        self,
        webhook_id: str,
        customer_id: str,
        url: str,
        events: List[str],
        secret_key: Optional[str] = None,
    ) -> bool:
        """웹훅 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO webhooks (id, customer_id, url, events, secret_key)
                    VALUES (?, ?, ?, ?, ?)
                """, (webhook_id, customer_id, url, json.dumps(events, ensure_ascii=False), secret_key))
                self._conn.commit()
                log.info("[DB] 웹훅 생성: webhook_id=%s, customer_id=%s", webhook_id, customer_id)
                return True
            except sqlite3.IntegrityError:
                return False


    def get_webhooks(self, customer_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """웹훅 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, customer_id, url, events, secret_key, is_active, created_at, updated_at
                FROM webhooks
                WHERE customer_id = ?
            """
            params = [customer_id]
            if active_only:
                query += " AND is_active = 1"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "customer_id": row[1],
                    "url": row[2],
                    "events": json.loads(row[3]) if row[3] else [],
                    "secret_key": row[4],
                    "is_active": bool(row[5]),
                    "created_at": row[6],
                    "updated_at": row[7],
                }
                for row in rows
            ]


    def update_webhook(
        self,
        webhook_id: str,
        url: Optional[str] = None,
        events: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """웹훅 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            updates = []
            params = []
            
            if url:
                updates.append("url = ?")
                params.append(url)
            if events:
                updates.append("events = ?")
                params.append(json.dumps(events, ensure_ascii=False))
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(1 if is_active else 0)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(webhook_id)
            
            query = f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 웹훅 업데이트: webhook_id=%s", webhook_id)
            return updated

    # ── 이미지 업로드 관리 ───────────────────────────────────────────────────────


    def delete_webhook(self, webhook_id: str) -> bool:
        """웹훅 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM webhooks WHERE id = ?
            """, (webhook_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 웹훅 삭제: webhook_id=%s", webhook_id)
            return deleted

    # ── 외부 동기화 로그 관련 메서드 ───────────────────────────────────────────

