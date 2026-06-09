"""notifications 도메인 저장소 Mixin."""
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


class NotificationsMixin:
    """notifications 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def get_notification_settings(self, customer_id: str) -> Dict[str, Any]:
        """알림 설정 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT analysis_complete, score_improvement, care_reminder,
                       marketing, reminder_hours, created_at, updated_at
                FROM notification_settings WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": customer_id,
                    "analysis_complete": bool(row[0]),
                    "score_improvement": bool(row[1]),
                    "care_reminder": bool(row[2]),
                    "marketing": bool(row[3]),
                    "reminder_hours": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                }
            # 기본 설정 반환
            return {
                "customer_id": customer_id,
                "analysis_complete": True,
                "score_improvement": True,
                "care_reminder": False,
                "marketing": False,
                "reminder_hours": 168,
            }


    def update_notification_settings(
        self,
        customer_id: str,
        analysis_complete: Optional[bool] = None,
        score_improvement: Optional[bool] = None,
        care_reminder: Optional[bool] = None,
        marketing: Optional[bool] = None,
        reminder_hours: Optional[int] = None,
    ) -> bool:
        """알림 설정 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            
            # 업데이트할 필드만 동적으로 구성
            updates = []
            params = []
            
            if analysis_complete is not None:
                updates.append("analysis_complete = ?")
                params.append(1 if analysis_complete else 0)
            if score_improvement is not None:
                updates.append("score_improvement = ?")
                params.append(1 if score_improvement else 0)
            if care_reminder is not None:
                updates.append("care_reminder = ?")
                params.append(1 if care_reminder else 0)
            if marketing is not None:
                updates.append("marketing = ?")
                params.append(1 if marketing else 0)
            if reminder_hours is not None:
                updates.append("reminder_hours = ?")
                params.append(reminder_hours)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(customer_id)
            
            query = f"""
                INSERT INTO notification_settings (customer_id)
                VALUES (?)
                ON CONFLICT(customer_id) DO UPDATE SET {', '.join(updates)}
            """
            
            cursor.execute(query, params)
            self._conn.commit()
            log.info("[DB] 알림 설정 업데이트: customer_id=%s", customer_id)
            return True

    # ── 제품 추천 관련 메서드 ─────────────────────────────────────────────────


    def send_notification(
        self,
        customer_id: str,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """알림 전송"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                # 알림 설정 확인
                cursor.execute(
                    """
                    SELECT analysis_complete_enabled FROM notification_settings 
                    WHERE customer_id = ?
                    """,
                    (customer_id,),
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    return False  # 알림 비활성화
                
                # 알림 기록 (실제 구현 시 푸시 알림 서비스 연동)
                notification_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO notification_settings (customer_id, analysis_complete_enabled)
                    VALUES (?, 1)
                    ON CONFLICT(customer_id) DO UPDATE SET analysis_complete_enabled = 1
                    """,
                    (customer_id,),
                )
                self._conn.commit()
                log.info("[DB] 알림 전송: customer_id=%s, type=%s, title=%s", customer_id, notification_type, title)
                return True
            except Exception as e:
                log.error("[DB] 알림 전송 실패: customer_id=%s, error=%s", customer_id, e)
                return False


    def get_notification_settings(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """알림 설정 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT customer_id, analysis_complete_enabled, device_token, platform
                FROM notification_settings WHERE customer_id = ?
                """,
                (customer_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": row[0],
                    "analysis_complete_enabled": bool(row[1]),
                    "device_token": row[2],
                    "platform": row[3],
                }
            return None


    def update_notification_settings(
        self,
        customer_id: str,
        analysis_complete_enabled: bool,
        device_token: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> bool:
        """알림 설정 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO notification_settings 
                (customer_id, analysis_complete_enabled, device_token, platform)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    analysis_complete_enabled = excluded.analysis_complete_enabled,
                    device_token = excluded.device_token,
                    platform = excluded.platform
                """,
                (customer_id, analysis_complete_enabled, device_token, platform),
            )
            self._conn.commit()
            log.info("[DB] 알림 설정 업데이트: customer_id=%s", customer_id)
            return True

    # ── 보안/암호화 ─────────────────────────────────────────────────────


    def set_push_preferences(
        self,
        customer_id: str,
        push_enabled: bool = True,
        analysis_complete_enabled: bool = True,
        promotion_enabled: bool = False,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
        device_token: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> bool:
        """푸시 알림 선호도 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO push_preferences 
                    (customer_id, push_enabled, analysis_complete_enabled, promotion_enabled, quiet_hours_start, quiet_hours_end, device_token, platform)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(customer_id) DO UPDATE SET
                        push_enabled = excluded.push_enabled,
                        analysis_complete_enabled = excluded.analysis_complete_enabled,
                        promotion_enabled = excluded.promotion_enabled,
                        quiet_hours_start = excluded.quiet_hours_start,
                        quiet_hours_end = excluded.quiet_hours_end,
                        device_token = excluded.device_token,
                        platform = excluded.platform,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (customer_id, push_enabled, analysis_complete_enabled, promotion_enabled, quiet_hours_start, quiet_hours_end, device_token, platform),
                )
                self._conn.commit()
                log.info("[DB] 푸시 알림 선호도 설정: customer_id=%s", customer_id)
                return True
            except Exception as e:
                log.error("[DB] 푸시 알림 선호도 설정 실패: %s", e)
                return False


    def get_push_preferences(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """푸시 알림 선호도 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM push_preferences WHERE customer_id = ?",
                (customer_id,),
            )
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

    # ── A/B 테스트 관리 ───────────────────────────────────────────────────────

