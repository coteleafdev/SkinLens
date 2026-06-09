"""pcr 도메인 저장소 Mixin."""
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


class PcrMixin:
    """pcr 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_pcr_test_request(
        self,
        request_id: str,
        customer_id: str,
        test_type: str,
        requested_at: str,
        status: str = "pending"
    ) -> bool:
        """PCR 검사 요청 생성"""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT INTO pcr_test_requests (request_id, customer_id, test_type, requested_at, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (request_id, customer_id, test_type, requested_at, status))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    

    def get_pcr_test_request(self, request_id: str) -> Optional[Dict]:
        """PCR 검사 요청 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, request_id, customer_id, test_type, requested_at, status, updated_at
                FROM pcr_test_requests
                WHERE request_id = ?
            """, (request_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "request_id": row[1],
                    "customer_id": row[2],
                    "test_type": row[3],
                    "requested_at": row[4],
                    "status": row[5],
                    "updated_at": row[6],
                }
            return None
    

    def update_pcr_test_status(self, request_id: str, status: str) -> bool:
        """PCR 검사 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE pcr_test_requests
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
            """, (status, request_id))
            self._conn.commit()
            return cursor.rowcount > 0
    

    def create_pcr_test_result(
        self,
        result_id: str,
        request_id: str,
        customer_id: str,
        test_data: dict,
        interpretation: str,
        completed_at: str
    ) -> bool:
        """PCR 검사 결과 생성"""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT INTO pcr_test_results (result_id, request_id, customer_id, test_data, interpretation, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (result_id, request_id, customer_id, json.dumps(test_data), interpretation, completed_at))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    

    def get_pcr_test_result(self, result_id: str) -> Optional[Dict]:
        """PCR 검사 결과 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, result_id, request_id, customer_id, test_data, interpretation, completed_at
                FROM pcr_test_results
                WHERE result_id = ?
            """, (result_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "result_id": row[1],
                    "request_id": row[2],
                    "customer_id": row[3],
                    "test_data": json.loads(row[4]) if row[4] else {},
                    "interpretation": row[5],
                    "completed_at": row[6],
                }
            return None
    

    def get_pcr_test_results_by_customer(self, customer_id: str, limit: int = 10) -> List[Dict]:
        """고객 PCR 검사 결과 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, result_id, request_id, customer_id, test_data, interpretation, completed_at
                FROM pcr_test_results
                WHERE customer_id = ?
                ORDER BY completed_at DESC
                LIMIT ?
            """, (customer_id, limit))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "result_id": row[1],
                    "request_id": row[2],
                    "customer_id": row[3],
                    "test_data": json.loads(row[4]) if row[4] else {},
                    "interpretation": row[5],
                    "completed_at": row[6],
                }
                for row in rows
            ]
    

    def get_pcr_test_history(self, customer_id: str, limit: int = 10) -> List[Dict]:
        """고객 PCR 검사 이력 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT r.id, r.request_id, r.customer_id, r.test_type, r.requested_at, r.status, r.updated_at,
                       res.result_id, res.interpretation, res.completed_at
                FROM pcr_test_requests r
                LEFT JOIN pcr_test_results res ON r.request_id = res.request_id
                WHERE r.customer_id = ?
                ORDER BY r.requested_at DESC
                LIMIT ?
            """, (customer_id, limit))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "request_id": row[1],
                    "customer_id": row[2],
                    "test_type": row[3],
                    "requested_at": row[4],
                    "status": row[5],
                    "updated_at": row[6],
                    "result_id": row[7],
                    "interpretation": row[8],
                    "completed_at": row[9],
                }
                for row in rows
            ]
    

    def create_pcr_consultation(
        self,
        consultation_id: str,
        customer_id: str,
        request_id: str,
        scheduled_at: str,
        notes: Optional[str] = None
    ) -> bool:
        """PCR 검사 전문가 상담 예약 생성"""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    INSERT INTO pcr_consultations (consultation_id, customer_id, request_id, scheduled_at, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (consultation_id, customer_id, request_id, scheduled_at, notes))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    

    def get_pcr_consultations(self, customer_id: str, limit: int = 10) -> List[Dict]:
        """고객 PCR 상담 예약 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, consultation_id, customer_id, request_id, scheduled_at, notes, status, created_at
                FROM pcr_consultations
                WHERE customer_id = ?
                ORDER BY scheduled_at DESC
                LIMIT ?
            """, (customer_id, limit))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "consultation_id": row[1],
                    "customer_id": row[2],
                    "request_id": row[3],
                    "scheduled_at": row[4],
                    "notes": row[5],
                    "status": row[6],
                    "created_at": row[7],
                }
                for row in rows
            ]
    
