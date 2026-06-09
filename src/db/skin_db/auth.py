"""auth 도메인 저장소 Mixin."""
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


class AuthMixin:
    """auth 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_oauth_provider(
        self,
        provider_id: str,
        provider_name: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: Optional[List[str]] = None,
    ) -> bool:
        """OAuth 제공자 등록"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO oauth_providers (id, provider_name, client_id, client_secret, redirect_uri, scopes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    provider_id,
                    provider_name,
                    client_id,
                    client_secret,
                    redirect_uri,
                    json.dumps(scopes, ensure_ascii=False) if scopes else None,
                ))
                self._conn.commit()
                log.info("[DB] OAuth 제공자 등록: provider_name=%s", provider_name)
                return True
            except sqlite3.IntegrityError:
                return False


    def get_oauth_provider(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """OAuth 제공자 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, provider_name, client_id, client_secret, redirect_uri, scopes, is_active, created_at
                FROM oauth_providers
                WHERE provider_name = ? AND is_active = 1
            """, (provider_name,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "provider_name": row[1],
                    "client_id": row[2],
                    "client_secret": row[3],
                    "redirect_uri": row[4],
                    "scopes": json.loads(row[5]) if row[5] else [],
                    "is_active": bool(row[6]),
                    "created_at": row[7],
                }
            return None


    def save_oauth_token(
        self,
        token_id: str,
        customer_id: str,
        provider_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> bool:
        """OAuth 토큰 저장"""
        with self._lock:
            cursor = self._conn.cursor()
            expires_at = None
            if expires_in:
                from datetime import datetime, timedelta
                expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            
            cursor.execute("""
                INSERT INTO oauth_tokens (id, customer_id, provider_id, access_token, refresh_token, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (token_id, customer_id, provider_id, access_token, refresh_token, expires_at))
            self._conn.commit()
            log.info("[DB] OAuth 토큰 저장: customer_id=%s, provider_id=%s", customer_id, provider_id)
            return True


    def get_oauth_token(self, customer_id: str, provider_id: str) -> Optional[Dict[str, Any]]:
        """OAuth 토큰 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, provider_id, access_token, refresh_token, expires_at, created_at
                FROM oauth_tokens
                WHERE customer_id = ? AND provider_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (customer_id, provider_id))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "customer_id": row[1],
                    "provider_id": row[2],
                    "access_token": row[3],
                    "refresh_token": row[4],
                    "expires_at": row[5],
                    "created_at": row[6],
                }
            return None

    # ── 사용자 관리 (FIX P1) ─────────────────────────────────────────────────────
    

    def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = "customer",
        customer_id: Optional[str] = None,
    ) -> bool:
        """사용자 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, role, customer_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, password_hash, role, customer_id, datetime.now(timezone.utc), datetime.now(timezone.utc)))
                self._conn.commit()
                log.info("[DB] 사용자 생성: username=%s, role=%s", username, role)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] 사용자 이미 존재: username=%s", username)
                return False
    

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """username으로 사용자 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, username, password_hash, role, customer_id, is_active, created_at, updated_at
                FROM users
                WHERE username = ? AND is_active = 1
            """, (username,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "username": row[1],
                    "password_hash": row[2],
                    "role": row[3],
                    "customer_id": row[4],
                    "is_active": bool(row[5]),
                    "created_at": row[6],
                    "updated_at": row[7],
                }
            return None
    

    def get_user_by_customer_id(self, customer_id: str) -> Optional[Dict]:
        """customer_id로 사용자 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, username, password_hash, role, customer_id, is_active, created_at, updated_at
                FROM users
                WHERE customer_id = ? AND is_active = 1
            """, (customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "username": row[1],
                    "password_hash": row[2],
                    "role": row[3],
                    "customer_id": row[4],
                    "is_active": bool(row[5]),
                    "created_at": row[6],
                    "updated_at": row[7],
                }
            return None
    
    # ── 리프레시 토큰 관련 메서드 ───────────────────────────────────────────────
    

    def create_refresh_token(
        self,
        token: str,
        customer_id: str,
        expires_at: str
    ) -> bool:
        """리프레시 토큰 생성"""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT INTO refresh_tokens (token, customer_id, expires_at)
                    VALUES (?, ?, ?)
                """, (token, customer_id, expires_at))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    

    def get_refresh_token(self, token: str) -> Optional[Dict]:
        """리프레시 토큰 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, token, customer_id, expires_at, created_at, is_revoked
                FROM refresh_tokens
                WHERE token = ? AND is_revoked = 0
            """, (token,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "token": row[1],
                    "customer_id": row[2],
                    "expires_at": row[3],
                    "created_at": row[4],
                    "is_revoked": bool(row[5]),
                }
            return None
    

    def revoke_refresh_token(self, token: str) -> bool:
        """리프레시 토큰 폐기"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE refresh_tokens
                SET is_revoked = 1
                WHERE token = ?
            """, (token,))
            self._conn.commit()
            return cursor.rowcount > 0
    

    def revoke_all_refresh_tokens(self, customer_id: str) -> int:
        """사용자의 모든 리프레시 토큰 폐기"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE refresh_tokens
                SET is_revoked = 1
                WHERE customer_id = ?
            """, (customer_id,))
            self._conn.commit()
            return cursor.rowcount
    

    def cleanup_expired_refresh_tokens(self) -> int:
        """만료된 리프레시 토큰 정리"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM refresh_tokens
                WHERE expires_at < datetime('now')
            """)
            deleted_count = cursor.rowcount
            self._conn.commit()
            return deleted_count
    
    # ── 장치 관련 메서드 ───────────────────────────────────────────────────────
    

    def register_device(
        self,
        customer_id: str,
        device_token: str,
        device_type: str,
        device_name: Optional[str] = None,
        os_version: Optional[str] = None,
        app_version: Optional[str] = None
    ) -> bool:
        """장치 등록"""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT INTO devices (customer_id, device_token, device_type, device_name, os_version, app_version)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (customer_id, device_token, device_type, device_name, os_version, app_version))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    

    def get_devices(self, customer_id: str) -> List[Dict]:
        """사용자의 장치 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, device_token, device_type, device_name, os_version, app_version, is_active, last_used_at, created_at
                FROM devices
                WHERE customer_id = ? AND is_active = 1
                ORDER BY last_used_at DESC
            """, (customer_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "customer_id": row[1],
                    "device_token": row[2],
                    "device_type": row[3],
                    "device_name": row[4],
                    "os_version": row[5],
                    "app_version": row[6],
                    "is_active": bool(row[7]),
                    "last_used_at": row[8],
                    "created_at": row[9],
                }
                for row in rows
            ]
    

    def update_device_last_used(self, device_token: str) -> bool:
        """장치 마지막 사용 시간 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE devices
                SET last_used_at = datetime('now')
                WHERE device_token = ?
            """, (device_token,))
            self._conn.commit()
            return cursor.rowcount > 0
    

    def revoke_device(self, device_id: int, customer_id: str) -> bool:
        """장치 폐기"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE devices
                SET is_active = 0
                WHERE id = ? AND customer_id = ?
            """, (device_id, customer_id))
            self._conn.commit()
            return cursor.rowcount > 0
    

    def update_user_username(self, old_username: str, new_username: str) -> bool:
        """사용자 username 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE users
                SET username = ?, updated_at = ?
                WHERE username = ?
            """, (new_username, datetime.now(timezone.utc), old_username))
            self._conn.commit()
            return cursor.rowcount > 0
    

    def deactivate_user(self, customer_id: str) -> bool:
        """사용자 비활성화"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE users
                SET is_active = 0, updated_at = ?
                WHERE customer_id = ?
            """, (datetime.now(timezone.utc), customer_id))
            self._conn.commit()
            return cursor.rowcount > 0
    
    # ── 설문 데이터 관련 메서드 ─────────────────────────────────────────────────
    

    def create_password_reset_token(
        self,
        token: str,
        customer_id: str,
        expires_at: str
    ) -> bool:
        """비밀번호 리셋 토큰 생성"""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT INTO password_reset_tokens (token, customer_id, expires_at)
                    VALUES (?, ?, ?)
                """, (token, customer_id, expires_at))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    

    def get_password_reset_token(self, token: str) -> Optional[Dict]:
        """비밀번호 리셋 토큰 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, token, customer_id, expires_at, created_at, is_used
                FROM password_reset_tokens
                WHERE token = ? AND is_used = 0
            """, (token,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "token": row[1],
                    "customer_id": row[2],
                    "expires_at": row[3],
                    "created_at": row[4],
                    "is_used": bool(row[5]),
                }
            return None
    

    def mark_password_reset_token_used(self, token: str) -> bool:
        """비밀번호 리셋 토큰 사용 표시"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE password_reset_tokens
                SET is_used = 1
                WHERE token = ?
            """, (token,))
            self._conn.commit()
            return cursor.rowcount > 0
    
    # ── PCR 검사 관련 메서드 ─────────────────────────────────────────────────────
    

    def cleanup_expired_password_reset_tokens(self) -> int:
        """만료된 비밀번호 리셋 토큰 정리"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM password_reset_tokens
                WHERE expires_at < datetime('now')
            """)
            deleted_count = cursor.rowcount
            self._conn.commit()
            return deleted_count
    

    def update_user_password(self, username: str, new_password_hash: str) -> bool:
        """사용자 비밀번호 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE users
                SET password_hash = ?, updated_at = ?
                WHERE username = ?
            """, (new_password_hash, datetime.now(timezone.utc), username))
            self._conn.commit()
            return cursor.rowcount > 0

