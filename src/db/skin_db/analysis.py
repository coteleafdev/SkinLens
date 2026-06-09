"""analysis 도메인 저장소 Mixin."""
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


class AnalysisMixin:
    """analysis 관련 영속화 메서드. _BaseRepository 의 self._conn/_lock 사용."""

    def save_analysis(
        self,
        original_path: str,
        restored_path: str,
        json_result: Dict[str, Any],
        customer_id: Optional[str] = None,
        input_json: Optional[Dict[str, Any]] = None,
        supabase_async: bool = True,
    ) -> int:
        """
        분석 결과를 로컬 SQLite 에 저장하고, Supabase 에도 동기화.

        Parameters
        ----------
        original_path:
            원본 이미지 경로.
        restored_path:
            복원 이미지 경로.
        json_result:
            분석 결과 JSON 딕셔너리.
        customer_id:
            고객 식별자 (선택사항).
        input_json:
            스마트폰에서 보내온 입력 JSON (survey + client_meta).
        supabase_async:
            True(기본)이면 Supabase 업로드를 백그라운드 스레드로 실행.
            False 이면 현재 스레드에서 완료까지 대기 (테스트·배치 용).

        Returns
        -------
        int
            로컬 SQLite 에 저장된 레코드 ID.
        """
        # ── 1. 로컬 SQLite 저장 ───────────────────────────────────────────
        with self._lock:
            cursor = self._conn.cursor()

            original_filename = Path(original_path).stem if original_path else ""

            # 점수 추출: analysis_result 키에서 추출
            # [REFACTOR P0-8] 중복 로직을 result_parser.py로 통합
            from src.db.result_parser import extract_overall_scores
            overall_orig, overall_rest = extract_overall_scores(json_result)

            cursor.execute("""
                INSERT INTO analyses (
                    customer_id,
                    original_image_path,
                    restored_image_path,
                    json_result,
                    input_json,
                    original_filename,
                    overall_score_original,
                    overall_score_restored,
                    detected_skin_types,
                    skin_type_confidence,
                    skin_type_features,
                    skin_type_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                customer_id,
                str(original_path),
                str(restored_path),
                json.dumps(json_result, ensure_ascii=False, indent=2),
                json.dumps(input_json, ensure_ascii=False, indent=2) if input_json else None,
                original_filename,
                float(overall_orig),
                float(overall_rest),
                json.dumps(json_result.get("skin_type_detection", {}).get("skin_types"), ensure_ascii=False) if json_result.get("skin_type_detection") else None,
                json_result.get("skin_type_detection", {}).get("confidence") if json_result.get("skin_type_detection") else None,
                json.dumps(json_result.get("skin_type_detection", {}).get("features"), ensure_ascii=False) if json_result.get("skin_type_detection") else None,
                "auto" if json_result.get("skin_type_detection") else None,
            ))

            analysis_id = cursor.lastrowid
            self._conn.commit()

            log.info("[DB] 분석 결과 저장 완료: ID=%d, 파일명=%s", analysis_id, original_filename)

        # ── 2. Supabase 동기화 ────────────────────────────────────────────
        if self._supabase_sync_enabled:
            self._sync_to_supabase(
                local_id      = analysis_id,
                original_path = original_path,
                restored_path = restored_path,
                json_result   = json_result,
                customer_id   = customer_id,
                async_mode    = supabase_async,
                input_json    = input_json,
            )

        return analysis_id


    def get_analysis(self, analysis_id: int) -> Optional[Dict[str, Any]]:
        """ID로 분석 결과 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT json_result FROM analyses WHERE id = ?
            """, (analysis_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None


    def get_customer_analyses(self, customer_id: str) -> List[Dict[str, Any]]:
        """고객의 전체 분석 기록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                WHERE customer_id = ?
                ORDER BY created_at DESC
            """, (customer_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "original_filename": row[1],
                    "created_at": row[2],
                    "overall_score_original": row[3],
                    "overall_score_restored": row[4],
                }
                for row in rows
            ]


    def get_customer_analysis_detail(self, customer_id: str, analysis_id: int) -> Optional[Dict[str, Any]]:
        """고객의 특정 분석 상세 정보 조회 (이미지 경로 포함)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, original_image_path, restored_image_path,
                       json_result, input_json, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                WHERE customer_id = ? AND id = ?
            """, (customer_id, analysis_id))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "customer_id": row[1],
                    "original_image_path": row[2],
                    "restored_image_path": row[3],
                    "json_result": json.loads(row[4]) if row[4] else None,
                    "input_json": json.loads(row[5]) if row[5] else None,
                    "original_filename": row[6],
                    "created_at": row[7],
                    "overall_score_original": row[8],
                    "overall_score_restored": row[9],
                }
            return None


    def get_recent_analyses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """최근 분석 기록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                "id": row[0],
                "customer_id": row[1],
                "original_filename": row[2],
                "created_at": row[3],
                "overall_score_original": row[4],
                "overall_score_restored": row[5],
            }
            for row in rows
        ]


    def search_by_filename(self, filename: str) -> List[Dict[str, Any]]:
        """파일명으로 분석 기록 검색 (부분 일치)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                WHERE original_filename LIKE ?
                ORDER BY created_at DESC
            """, (f"%{filename}%",))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "customer_id": row[1],
                    "original_filename": row[2],
                    "created_at": row[3],
                    "overall_score_original": row[4],
                    "overall_score_restored": row[5],
                }
                for row in rows
            ]


    def delete_analysis(self, analysis_id: int) -> bool:
        """분석 기록 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM analyses WHERE id = ?
            """, (analysis_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 분석 기록 삭제 완료: ID=%d", analysis_id)
            return deleted


    def get_stats(self) -> Dict[str, Any]:
        """DB 통계 정보 조회"""
        with self._lock:
            cursor = self._conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM analyses")
            total_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT customer_id) FROM analyses WHERE customer_id IS NOT NULL")
            customer_count = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(created_at) FROM analyses")
            last_analysis = cursor.fetchone()[0]

            return {
                "total_analyses":   total_count,
                "total_customers": customer_count,
                "last_analysis":    last_analysis,
            }

