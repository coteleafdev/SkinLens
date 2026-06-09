"""apikeys 도메인 저장소 Mixin."""
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


class ApiKeysMixin:
    """apikeys 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_api_key(
        self,
        name: str,
        owner_id: str,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """API 키 생성.

        Args:
            name: API 키 이름
            owner_id: 소유자 ID
            description: 설명
            scopes: 권한 범위 (예: ["read", "write"])
            expires_in_days: 만료일수 (None이면 만료 없음)

        Returns:
            생성된 API 키 정보 (실제 키는 한 번만 반환됨)
        """
        import hashlib

        # 실제 API 키 생성 (32 bytes = 64 hex chars)
        api_key = secrets.token_hex(32)

        # 키 해시 생성 (SHA-256)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # 만료일 계산
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now() + timedelta(days=expires_in_days)

        # JSON으로 scopes 저장
        scopes_json = json.dumps(scopes) if scopes else None

        with self._lock:
            cursor = self._conn.cursor()
            key_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO api_keys (id, key_hash, name, description, owner_id, scopes, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (key_id, key_hash, name, description, owner_id, scopes_json, expires_at))
            self._conn.commit()

        return {
            "id": key_id,
            "api_key": api_key,  # 실제 키는 한 번만 반환
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "scopes": scopes,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "created_at": datetime.now().isoformat(),
        }


    def validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """API 키 검증.

        Args:
            api_key: 검증할 API 키

        Returns:
            유효한 키 정보, 유효하지 않으면 None
        """
        import hashlib

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, name, description, owner_id, scopes, is_active, expires_at
                FROM api_keys
                WHERE key_hash = ? AND is_active = 1
            """, (key_hash,))
            row = cursor.fetchone()

            if not row:
                return None

            # 만료 체크
            expires_at = row[6]
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at)
                if datetime.now() > expires_dt:
                    return None

            # 마지막 사용 시간 업데이트
            cursor.execute("""
                UPDATE api_keys
                SET last_used_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (row[0],))
            self._conn.commit()

            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "owner_id": row[3],
                "scopes": json.loads(row[4]) if row[4] else [],
                "expires_at": row[5],
            }


    def revoke_api_key(self, key_id: str, reason: Optional[str] = None) -> bool:
        """API 키 폐지.

        Args:
            key_id: 폐지할 API 키 ID
            reason: 폐지 사유

        Returns:
            성공 여부
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE api_keys
                SET is_active = 0, revoked_at = CURRENT_TIMESTAMP, revoke_reason = ?
                WHERE id = ?
            """, (reason, key_id))
            self._conn.commit()
            return cursor.rowcount > 0


    def list_api_keys(
        self,
        owner_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """API 키 목록 조회.

        Args:
            owner_id: 소유자 ID 필터
            is_active: 활성 상태 필터
            limit: 최대 반환 수

        Returns:
            API 키 목록
        """
        with self._lock:
            cursor = self._conn.cursor()

            query = """
                SELECT id, name, description, owner_id, scopes, is_active,
                       expires_at, last_used_at, created_at, revoked_at
                FROM api_keys
                WHERE 1=1
            """
            params = []

            if owner_id:
                query += " AND owner_id = ?"
                params.append(owner_id)

            if is_active is not None:
                query += " AND is_active = ?"
                params.append(1 if is_active else 0)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "owner_id": row[3],
                    "scopes": json.loads(row[4]) if row[4] else [],
                    "is_active": bool(row[5]),
                    "expires_at": row[6],
                    "last_used_at": row[7],
                    "created_at": row[8],
                    "revoked_at": row[9],
                }
                for row in rows
            ]


    def log_api_key_usage(
        self,
        api_key_id: str,
        endpoint: str,
        method: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> str:
        """API 키 사용 로그 기록.

        Args:
            api_key_id: API 키 ID
            endpoint: 엔드포인트
            method: HTTP 메서드
            ip_address: IP 주소
            user_agent: User-Agent
            success: 성공 여부
            error_message: 에러 메시지

        Returns:
            로그 ID
        """
        with self._lock:
            cursor = self._conn.cursor()
            log_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO api_key_usage_logs
                (id, api_key_id, endpoint, method, ip_address, user_agent, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, api_key_id, endpoint, method, ip_address, user_agent, success, error_message))
            self._conn.commit()
            return log_id

    # ── 사용자 설정 관련 메서드 ───────────────────────────────────────────────

