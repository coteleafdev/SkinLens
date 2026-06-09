"""gamification 도메인 저장소 Mixin."""
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


class GamificationMixin:
    """gamification 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def create_skin_diary_entry(
        self,
        entry_id: str,
        customer_id: str,
        analysis_id: Optional[int] = None,
        image_url: Optional[str] = None,
        overall_score: Optional[float] = None,
        measurement_scores: Optional[Dict] = None,
        notes: Optional[str] = None,
        mood: Optional[str] = None,
        weather: Optional[str] = None,
    ) -> bool:
        """피부 일기 엔트리 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO skin_diary 
                (entry_id, customer_id, analysis_id, image_url, overall_score, measurement_scores, notes, mood, weather)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entry_id, customer_id, analysis_id, image_url, overall_score, json.dumps(measurement_scores) if measurement_scores else None, notes, mood, weather),
            )
            self._conn.commit()
            log.info("[DB] 피부 일기 엔트리 생성: entry_id=%s, customer_id=%s", entry_id, customer_id)
            return True


    def get_skin_diary_entries(self, customer_id: str, limit: int = 30) -> List[Dict]:
        """고객 피부 일기 엔트리 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT entry_id, customer_id, analysis_id, image_url, overall_score, measurement_scores, notes, mood, weather, created_at
                FROM skin_diary
                WHERE customer_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 고객 목표 ─────────────────────────────────────────────────────────────


    def create_customer_goal(
        self,
        goal_id: str,
        customer_id: str,
        goal_type: str,
        target_value: float,
        start_date: str,
        end_date: str,
    ) -> bool:
        """고객 목표 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_goals 
                (goal_id, customer_id, goal_type, target_value, current_value, start_date, end_date)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (goal_id, customer_id, goal_type, target_value, start_date, end_date),
            )
            self._conn.commit()
            log.info("[DB] 고객 목표 생성: goal_id=%s, customer_id=%s, type=%s", goal_id, customer_id, goal_type)
            return True


    def update_customer_goal_progress(self, goal_id: str, current_value: float) -> bool:
        """고객 목표 진행률 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE customer_goals
                SET current_value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE goal_id = ?
                """,
                (current_value, goal_id),
            )
            self._conn.commit()
            log.info("[DB] 고객 목표 진행률 업데이트: goal_id=%s, value=%s", goal_id, current_value)
            return True


    def get_customer_goals(self, customer_id: str) -> List[Dict]:
        """고객 목표 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT goal_id, customer_id, goal_type, target_value, current_value, start_date, end_date, status, created_at
                FROM customer_goals
                WHERE customer_id = ?
                ORDER BY created_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 업적 ─────────────────────────────────────────────────────────────────


    def create_achievement(
        self,
        achievement_id: str,
        name: str,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        requirement_type: Optional[str] = None,
        requirement_value: Optional[float] = None,
        reward_points: int = 0,
    ) -> bool:
        """업적 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO achievements 
                (achievement_id, name, description, icon, requirement_type, requirement_value, reward_points)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (achievement_id, name, description, icon, requirement_type, requirement_value, reward_points),
            )
            self._conn.commit()
            log.info("[DB] 업적 생성: achievement_id=%s, name=%s", achievement_id, name)
            return True


    def earn_achievement(self, customer_id: str, achievement_id: str) -> bool:
        """고객 업적 획득"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_achievements (customer_id, achievement_id)
                VALUES (?, ?)
                """,
                (customer_id, achievement_id),
            )
            self._conn.commit()
            log.info("[DB] 고객 업적 획득: customer_id=%s, achievement_id=%s", customer_id, achievement_id)
            return True


    def get_customer_achievements(self, customer_id: str) -> List[Dict]:
        """고객 업적 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT ca.customer_id, ca.achievement_id, ca.earned_at, a.name, a.description, a.icon, a.reward_points
                FROM customer_achievements ca
                JOIN achievements a ON ca.achievement_id = a.achievement_id
                WHERE ca.customer_id = ?
                ORDER BY ca.earned_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 제품 구독 ─────────────────────────────────────────────────────────────


    def create_product_subscription(
        self,
        subscription_id: str,
        customer_id: str,
        product_id: str,
        frequency: str,
        next_delivery_date: str,
    ) -> bool:
        """제품 구독 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO product_subscriptions 
                (subscription_id, customer_id, product_id, frequency, next_delivery_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (subscription_id, customer_id, product_id, frequency, next_delivery_date),
            )
            self._conn.commit()
            log.info("[DB] 제품 구독 생성: subscription_id=%s, customer_id=%s, product_id=%s", subscription_id, customer_id, product_id)
            return True


    def get_customer_subscriptions(self, customer_id: str) -> List[Dict]:
        """고객 구독 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT subscription_id, customer_id, product_id, frequency, next_delivery_date, status, created_at
                FROM product_subscriptions
                WHERE customer_id = ? AND status = 'active'
                ORDER BY created_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 챌린지 ───────────────────────────────────────────────────────────────


    def create_challenge(
        self,
        challenge_id: str,
        name: str,
        description: Optional[str] = None,
        duration_days: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        reward_points: int = 0,
    ) -> bool:
        """챌린지 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO challenges 
                (challenge_id, name, description, duration_days, start_date, end_date, reward_points)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (challenge_id, name, description, duration_days, start_date, end_date, reward_points),
            )
            self._conn.commit()
            log.info("[DB] 챌린지 생성: challenge_id=%s, name=%s", challenge_id, name)
            return True


    def join_challenge(self, customer_id: str, challenge_id: str, start_date: str, end_date: str) -> bool:
        """챌린지 참여"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_challenges (customer_id, challenge_id, start_date, end_date)
                VALUES (?, ?, ?, ?)
                """,
                (customer_id, challenge_id, start_date, end_date),
            )
            self._conn.commit()
            log.info("[DB] 챌린지 참여: customer_id=%s, challenge_id=%s", customer_id, challenge_id)
            return True


    def update_challenge_progress(self, customer_id: str, challenge_id: str, progress: float) -> bool:
        """챌린지 진행률 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE customer_challenges
                SET progress = ?
                WHERE customer_id = ? AND challenge_id = ?
                """,
                (progress, customer_id, challenge_id),
            )
            self._conn.commit()
            log.info("[DB] 챌린지 진행률 업데이트: customer_id=%s, challenge_id=%s, progress=%s", customer_id, challenge_id, progress)
            return True


    def get_customer_challenges(self, customer_id: str) -> List[Dict]:
        """고객 챌린지 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT cc.customer_id, cc.challenge_id, cc.start_date, cc.end_date, cc.progress, cc.status, cc.created_at,
                       c.name, c.description, c.reward_points
                FROM customer_challenges cc
                JOIN challenges c ON cc.challenge_id = c.challenge_id
                WHERE cc.customer_id = ?
                ORDER BY cc.created_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 웹훅 관련 메서드 ───────────────────────────────────────────────────────

