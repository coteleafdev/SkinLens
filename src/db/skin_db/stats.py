"""stats 도메인 저장소 Mixin."""
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


class StatsMixin:
    """stats 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def record_daily_stats(
        self,
        date: str,
        total_analyses: int,
        unique_customers: int,
        successful_analyses: int,
        failed_analyses: int,
        avg_score: Optional[float] = None,
        total_revenue: float = 0.0,
    ) -> bool:
        """일일 통계 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO daily_stats
                (date, total_analyses, unique_customers, successful_analyses,
                 failed_analyses, avg_score, total_revenue)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_analyses = ?, unique_customers = ?,
                    successful_analyses = ?, failed_analyses = ?,
                    avg_score = ?, total_revenue = ?
            """, (
                date, total_analyses, unique_customers, successful_analyses,
                failed_analyses, avg_score, total_revenue,
                total_analyses, unique_customers, successful_analyses,
                failed_analyses, avg_score, total_revenue,
            ))
            self._conn.commit()
            return True


    def get_daily_stats(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """일일 통계 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT date, total_analyses, unique_customers, successful_analyses,
                       failed_analyses, avg_score, total_revenue
                FROM daily_stats
                WHERE 1=1
            """
            params = []
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            query += " ORDER BY date DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "date": row[0],
                    "total_analyses": row[1],
                    "unique_customers": row[2],
                    "successful_analyses": row[3],
                    "failed_analyses": row[4],
                    "avg_score": row[5],
                    "total_revenue": row[6],
                }
                for row in rows
            ]

    # ── 제품 피드백 ───────────────────────────────────────────────────────────


    def record_metric(
        self,
        metric_name: str,
        metric_value: float,
        metric_unit: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        """모니터링 메트릭 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO monitoring_metrics (metric_name, metric_value, metric_unit, tags)
                VALUES (?, ?, ?, ?)
                """,
                (metric_name, metric_value, metric_unit, json.dumps(tags) if tags else None),
            )
            self._conn.commit()
            return True


    def get_metrics(
        self,
        metric_name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """모니터링 메트릭 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = "SELECT * FROM monitoring_metrics WHERE 1=1"
            params = []
            
            if metric_name:
                query += " AND metric_name = ?"
                params.append(metric_name)
            if since:
                query += " AND recorded_at >= ?"
                params.append(since)
            
            query += " ORDER BY recorded_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 분석 추이 ───────────────────────────────────────────────────────────


    def record_analysis_trend(
        self,
        customer_id: str,
        analysis_id: int,
        overall_score_original: float,
        overall_score_restored: float,
        measurement_scores: Dict[str, float],
    ) -> bool:
        """분석 추이 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO analysis_trends 
                (customer_id, analysis_id, overall_score_original, overall_score_restored, measurement_scores)
                VALUES (?, ?, ?, ?, ?)
                """,
                (customer_id, analysis_id, overall_score_original, overall_score_restored, json.dumps(measurement_scores)),
            )
            self._conn.commit()
            log.info("[DB] 분석 추이 기록: customer_id=%s, analysis_id=%s", customer_id, analysis_id)
            return True


    def get_analysis_trends(
        self,
        customer_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """분석 추이 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT * FROM analysis_trends
                WHERE customer_id = ?
                ORDER BY recorded_at ASC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

