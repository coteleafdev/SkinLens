"""recommendations 도메인 저장소 Mixin."""
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


class RecommendationsMixin:
    """recommendations 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def save_product_recommendation(
        self,
        customer_id: str,
        analysis_id: int,
        product_id: str,
        match_score: float,
        recommendation_reason: str,
    ) -> bool:
        """제품 추천 저장"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO product_recommendations
                (customer_id, analysis_id, product_id, match_score, recommendation_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (customer_id, analysis_id, product_id, match_score, recommendation_reason))
            self._conn.commit()
            log.info("[DB] 제품 추천 저장: customer_id=%s, product_id=%s", customer_id, product_id)
            return True


    def get_product_recommendations(
        self,
        customer_id: str,
        analysis_id: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """고객의 제품 추천 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            
            if analysis_id:
                cursor.execute("""
                    SELECT pr.id, pr.analysis_id, pr.product_id, pr.match_score,
                           pr.recommendation_reason, pr.created_at,
                           p.product_name, p.category, p.key_ingredients, p.efficacy
                    FROM product_recommendations pr
                    JOIN products p ON pr.product_id = p.product_id
                    WHERE pr.customer_id = ? AND pr.analysis_id = ?
                    ORDER BY pr.match_score DESC
                    LIMIT ?
                """, (customer_id, analysis_id, limit))
            else:
                cursor.execute("""
                    SELECT pr.id, pr.analysis_id, pr.product_id, pr.match_score,
                           pr.recommendation_reason, pr.created_at,
                           p.product_name, p.category, p.key_ingredients, p.efficacy
                    FROM product_recommendations pr
                    JOIN products p ON pr.product_id = p.product_id
                    WHERE pr.customer_id = ?
                    ORDER BY pr.created_at DESC
                    LIMIT ?
                """, (customer_id, limit))
            
            rows = cursor.fetchall()
            return [
                {
                    "recommendation_id": row[0],
                    "analysis_id": row[1],
                    "product_id": row[2],
                    "match_score": row[3],
                    "recommendation_reason": row[4],
                    "recommended_at": row[5],
                    "product_name": row[6],
                    "category": row[7],
                    "key_ingredients": json.loads(row[8]) if row[8] else [],
                    "efficacy": row[9],
                }
                for row in rows
            ]


    def get_latest_recommendations(self, customer_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """최근 분석 기반 제품 추천 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT pr.id, pr.analysis_id, pr.product_id, pr.match_score,
                       pr.recommendation_reason, pr.created_at,
                       p.product_name, p.category, p.key_ingredients, p.efficacy,
                       a.overall_score_restored
                FROM product_recommendations pr
                JOIN products p ON pr.product_id = p.product_id
                JOIN analyses a ON pr.analysis_id = a.id
                WHERE pr.customer_id = ?
                ORDER BY pr.created_at DESC
                LIMIT ?
            """, (customer_id, limit))
            
            rows = cursor.fetchall()
            return [
                {
                    "recommendation_id": row[0],
                    "analysis_id": row[1],
                    "product_id": row[2],
                    "match_score": row[3],
                    "recommendation_reason": row[4],
                    "recommended_at": row[5],
                    "product_name": row[6],
                    "category": row[7],
                    "key_ingredients": json.loads(row[8]) if row[8] else [],
                    "efficacy": row[9],
                    "latest_score": row[10],
                }
                for row in rows
            ]

    # ── 고객 관리 관련 메서드 ─────────────────────────────────────────────────

