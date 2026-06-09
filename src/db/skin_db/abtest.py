"""abtest 도메인 저장소 Mixin."""
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


class AbTestMixin:
    """abtest 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_ab_test(
        self,
        test_name: str,
        variant_a_name: str,
        variant_b_name: str,
        description: Optional[str] = None,
        traffic_split: float = 0.5,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> bool:
        """A/B 테스트 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO ab_tests 
                    (test_name, description, variant_a_name, variant_b_name, traffic_split, start_date, end_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (test_name, description, variant_a_name, variant_b_name, traffic_split, start_date, end_date),
                )
                self._conn.commit()
                log.info("[DB] A/B 테스트 생성: test_name=%s", test_name)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] A/B 테스트 중복: test_name=%s", test_name)
                return False


    def assign_user_to_variant(
        self,
        test_id: int,
        customer_id: str,
        variant: str,
    ) -> bool:
        """사용자를 A/B 테스트 변형에 할당"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO ab_test_assignments (test_id, customer_id, variant)
                    VALUES (?, ?, ?)
                    """,
                    (test_id, customer_id, variant),
                )
                self._conn.commit()
                log.info("[DB] A/B 테스트 할당: test_id=%s, customer_id=%s, variant=%s", test_id, customer_id, variant)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] A/B 테스트 할당 중복: test_id=%s, customer_id=%s", test_id, customer_id)
                return False


    def get_user_variant(self, test_id: int, customer_id: str) -> Optional[str]:
        """사용자의 A/B 테스트 변형 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT variant FROM ab_test_assignments WHERE test_id = ? AND customer_id = ?",
                (test_id, customer_id),
            )
            row = cursor.fetchone()
            return row[0] if row else None


    def record_ab_test_result(
        self,
        test_id: int,
        variant: str,
        metric_name: str,
        metric_value: Optional[float] = None,
        event_count: int = 1,
    ) -> bool:
        """A/B 테스트 결과 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO ab_test_results (test_id, variant, metric_name, metric_value, event_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (test_id, variant, metric_name, metric_value, event_count),
            )
            self._conn.commit()
            log.info("[DB] A/B 테스트 결과 기록: test_id=%s, variant=%s, metric=%s", test_id, variant, metric_name)
            return True


    def get_ab_test_results(self, test_id: int) -> List[Dict[str, Any]]:
        """A/B 테스트 결과 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT variant, metric_name, AVG(metric_value) as avg_value, SUM(event_count) as total_events
                FROM ab_test_results
                WHERE test_id = ?
                GROUP BY variant, metric_name
                """,
                (test_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 모니터링 메트릭 ───────────────────────────────────────────────────────

