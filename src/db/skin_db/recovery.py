"""recovery 도메인 저장소 Mixin."""
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


class RecoveryMixin:
    """recovery 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_incident(
        self,
        incident_type: str,
        severity: str,
        resource_type: str,
        resource_id: str,
        description: Optional[str] = None,
    ) -> str:
        """장애 이벤트 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            incident_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO incident_events (
                    id, incident_type, severity, resource_type, resource_id, description
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (incident_id, incident_type, severity, resource_type, resource_id, description))
            self._conn.commit()
            log.info("[DB] 장애 이벤트 생성: ID=%s, Type=%s, Severity=%s", incident_id, incident_type, severity)
            return incident_id


    def update_incident_status(self, incident_id: str, status: str) -> bool:
        """장애 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            if status == "resolved":
                cursor.execute("""
                    UPDATE incident_events
                    SET status = ?, resolved_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, incident_id))
            else:
                cursor.execute("""
                    UPDATE incident_events
                    SET status = ?
                    WHERE id = ?
                """, (status, incident_id))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 장애 상태 업데이트: ID=%s, Status=%s", incident_id, status)
            return updated


    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """장애 이벤트 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, incident_type, severity, resource_type, resource_id,
                       detected_at, resolved_at, status, description
                FROM incident_events
                WHERE id = ?
            """, (incident_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "incident_type": row[1],
                    "severity": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "detected_at": row[5],
                    "resolved_at": row[6],
                    "status": row[7],
                    "description": row[8],
                }
            return None


    def get_incidents(
        self,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """장애 이벤트 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, incident_type, severity, resource_type, resource_id,
                       detected_at, resolved_at, status, description
                FROM incident_events
                WHERE 1=1
            """
            params = []
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY detected_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "incident_type": row[1],
                    "severity": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "detected_at": row[5],
                    "resolved_at": row[6],
                    "status": row[7],
                    "description": row[8],
                }
                for row in rows
            ]


    def create_recovery_action(
        self,
        incident_id: str,
        action_type: str,
    ) -> str:
        """복구 작업 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            action_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO recovery_actions (id, incident_id, action_type)
                VALUES (?, ?, ?)
            """, (action_id, incident_id, action_type))
            self._conn.commit()
            log.info("[DB] 복구 작업 생성: ID=%s, IncidentID=%s, Type=%s", action_id, incident_id, action_type)
            return action_id


    def update_recovery_action_status(
        self,
        action_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """복구 작업 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            if status == "in_progress":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, action_id))
            elif status == "completed":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, action_id))
            elif status == "failed":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, error_message = ?
                    WHERE id = ?
                """, (status, error_message, action_id))
            elif status == "rolled_back":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, rollback_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, action_id))
            else:
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?
                    WHERE id = ?
                """, (status, action_id))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 복구 작업 상태 업데이트: ID=%s, Status=%s", action_id, status)
            return updated


    def get_recovery_actions(self, incident_id: str) -> List[Dict[str, Any]]:
        """복구 작업 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, incident_id, action_type, action_status,
                       started_at, completed_at, rollback_at, error_message
                FROM recovery_actions
                WHERE incident_id = ?
                ORDER BY started_at DESC
            """, (incident_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "incident_id": row[1],
                    "action_type": row[2],
                    "action_status": row[3],
                    "started_at": row[4],
                    "completed_at": row[5],
                    "rollback_at": row[6],
                    "error_message": row[7],
                }
                for row in rows
            ]


    def add_recovery_log(
        self,
        recovery_action_id: str,
        log_level: str,
        message: str,
    ) -> str:
        """복구 로그 추가"""
        with self._lock:
            cursor = self._conn.cursor()
            log_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO recovery_logs (id, recovery_action_id, log_level, message)
                VALUES (?, ?, ?, ?)
            """, (log_id, recovery_action_id, log_level, message))
            self._conn.commit()
            return log_id


    def get_recovery_logs(self, recovery_action_id: str) -> List[Dict[str, Any]]:
        """복구 로그 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, recovery_action_id, log_level, message, created_at
                FROM recovery_logs
                WHERE recovery_action_id = ?
                ORDER BY created_at ASC
            """, (recovery_action_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "recovery_action_id": row[1],
                    "log_level": row[2],
                    "message": row[3],
                    "created_at": row[4],
                }
                for row in rows
            ]

    # ── API 키 관리 ─────────────────────────────────────────────────────────────


    def create_anomaly(
        self,
        anomaly_type: str,
        customer_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        description: Optional[str] = None,
        severity: str = "medium",
    ) -> str:
        """이상 활동 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            import uuid
            anomaly_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO security_anomalies
                (id, anomaly_type, customer_id, ip_address, description, severity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (anomaly_id, anomaly_type, customer_id, ip_address, description, severity))
            self._conn.commit()
            log.warning("[DB] 이상 활동 탐지: type=%s, customer_id=%s, ip=%s", 
                      anomaly_type, customer_id, ip_address)
            return anomaly_id


    def get_anomalies(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """이상 활동 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, anomaly_type, customer_id, ip_address, description,
                       severity, detected_at, resolved_at, status
                FROM security_anomalies
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            query += " ORDER BY detected_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "anomaly_type": row[1],
                    "customer_id": row[2],
                    "ip_address": row[3],
                    "description": row[4],
                    "severity": row[5],
                    "detected_at": row[6],
                    "resolved_at": row[7],
                    "status": row[8],
                }
                for row in rows
            ]


    def resolve_anomaly(self, anomaly_id: str) -> bool:
        """이상 활동 해결"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE security_anomalies
                SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (anomaly_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    # ── 사용자 역할 관련 메서드 ─────────────────────────────────────────────

