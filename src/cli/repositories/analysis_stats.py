"""Analysis Stats Repository.

분석 통계 관리를 담당합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from .base import BaseRepository


class AnalysisStatsRepository(BaseRepository):
    """분석 통계 Repository.

    analysis_stats, model_performance, score_trends 테이블을 담당합니다.
    """

    # ── 분석 통계 메서드 ───────────────────────────────────────────────────

    def record_analysis_stat(
        self,
        customer_id: Optional[str],
        success: bool,
        score_original: Optional[float],
        score_restored: Optional[float],
        execution_time_sec: float,
    ) -> None:
        """분석 통계 기록.

        Args:
            customer_id: 고객 ID
            success: 성공 여부
            score_original: 원본 점수
            score_restored: 복원 점수
            execution_time_sec: 실행 시간
        """
        today = datetime.now().strftime("%Y-%m-%d")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 기존 레코드 확인
            cursor.execute('''
                SELECT id, total_analyses, successful_analyses, failed_analyses,
                       avg_score_original, avg_score_restored, avg_execution_time_sec
                FROM analysis_stats
                WHERE date = ? AND (customer_id = ? OR customer_id IS NULL)
            ''', (today, customer_id))

            row = cursor.fetchone()

            if row:
                # 기존 레코드 업데이트
                (stat_id, total, success_count, failed_count,
                 avg_score_orig, avg_score_rest, avg_exec_time) = row

                new_total = total + 1
                new_success = success_count + (1 if success else 0)
                new_failed = failed_count + (0 if success else 1)

                # 이동 평균 계산
                if score_original is not None and avg_score_orig is not None:
                    new_avg_orig = (avg_score_orig * total + score_original) / new_total
                else:
                    new_avg_orig = avg_score_orig

                if score_restored is not None and avg_score_rest is not None:
                    new_avg_rest = (avg_score_rest * total + score_restored) / new_total
                else:
                    new_avg_rest = avg_score_rest

                if avg_exec_time is not None:
                    new_avg_exec = (avg_exec_time * total + execution_time_sec) / new_total
                else:
                    new_avg_exec = execution_time_sec

                cursor.execute('''
                    UPDATE analysis_stats
                    SET total_analyses = ?, successful_analyses = ?, failed_analyses = ?,
                        avg_score_original = ?, avg_score_restored = ?, avg_execution_time_sec = ?
                    WHERE id = ?
                ''', (new_total, new_success, new_failed, new_avg_orig, new_avg_rest, new_avg_exec, stat_id))
            else:
                # 새 레코드 삽입
                cursor.execute('''
                    INSERT INTO analysis_stats (
                        date, customer_id, total_analyses, successful_analyses, failed_analyses,
                        avg_score_original, avg_score_restored, avg_execution_time_sec
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (today, customer_id, 1, 1 if success else 0, 0 if success else 1,
                      score_original, score_restored, execution_time_sec))

            conn.commit()
            log.debug(f"분석 통계 기록: customer_id={customer_id}, success={success}")
        except Exception as e:
            conn.rollback()
            log.error(f"분석 통계 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_analysis_stats(
        self,
        days: int = 7,
        customer_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """분석 통계 조회.

        Args:
            days: 조회할 기간 (일)
            customer_id: 고객 ID (선택)

        Returns:
            통계 레코드 리스트
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = '''
                SELECT * FROM analysis_stats
                WHERE date >= ?
            '''
            params = [cutoff_date]

            if customer_id:
                query += ' AND customer_id = ?'
                params.append(customer_id)

            query += ' ORDER BY date DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute('PRAGMA table_info(analysis_stats)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    # ── 모델 성능 메서드 ───────────────────────────────────────────────────

    def record_model_performance(
        self,
        model_type: str,
        execution_time_ms: float,
        memory_peak_mb: Optional[float],
        cpu_percent_avg: Optional[float],
        success: bool,
        error_type: Optional[str] = None,
        input_resolution: Optional[str] = None,
        output_quality_score: Optional[float] = None,
    ) -> None:
        """모델 성능 기록.

        Args:
            model_type: 모델 유형
            execution_time_ms: 실행 시간 (ms)
            memory_peak_mb: 메모리 피크 (MB)
            cpu_percent_avg: CPU 사용률 평균
            success: 성공 여부
            error_type: 에러 유형
            input_resolution: 입력 해상도
            output_quality_score: 출력 품질 점수
        """
        timestamp = datetime.now().isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO model_performance (
                    timestamp, model_type, execution_time_ms, memory_peak_mb, cpu_percent_avg,
                    success, error_type, input_resolution, output_quality_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, model_type, execution_time_ms, memory_peak_mb, cpu_percent_avg,
                  success, error_type, input_resolution, output_quality_score))

            conn.commit()
            log.debug(f"모델 성능 기록: model_type={model_type}, success={success}")
        except Exception as e:
            conn.rollback()
            log.error(f"모델 성능 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_model_performance(
        self,
        model_type: Optional[str] = None,
        hours: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """모델 성능 조회.

        Args:
            model_type: 모델 유형 필터
            hours: 최근 N시간
            limit: 조회할 레코드 수

        Returns:
            성능 레코드 리스트
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM model_performance'
            params = []
            conditions = []

            if model_type:
                conditions.append('model_type = ?')
                params.append(model_type)
            if hours:
                cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
                conditions.append('timestamp > ?')
                params.append(cutoff)

            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute('PRAGMA table_info(model_performance)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    # ── 점수 추이 메서드 ───────────────────────────────────────────────────

    def record_score_trend(
        self,
        customer_id: Optional[str],
        overall_score: float,
        measurements: Dict[str, float],
        improvement_delta: Optional[float] = None,
    ) -> None:
        """점수 추이 기록.

        Args:
            customer_id: 고객 ID
            overall_score: 종합 점수
            measurements: 측정항목 점수 딕셔너리
            improvement_delta: 이전 대비 개선 정도
        """
        timestamp = datetime.now().isoformat()

        # 분석 횟수 계산
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT COUNT(*) FROM score_trends WHERE customer_id = ?
            ''', (customer_id,))
            analysis_count = cursor.fetchone()[0] + 1

            cursor.execute('''
                INSERT INTO score_trends (
                    customer_id, timestamp, overall_score, melasma_score, redness_score,
                    wrinkle_score, pore_score, improvement_delta, analysis_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (customer_id, timestamp, overall_score,
                  measurements.get('melasma_score'),
                  measurements.get('redness_score'),
                  measurements.get('wrinkle_score'),
                  measurements.get('pore_score'),
                  improvement_delta, analysis_count))

            conn.commit()
            log.debug(f"점수 추이 기록: customer_id={customer_id}, overall_score={overall_score}")
        except Exception as e:
            conn.rollback()
            log.error(f"점수 추이 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_score_trends(
        self,
        customer_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """점수 추이 조회.

        Args:
            customer_id: 고객 ID
            days: 조회할 기간 (일)
            limit: 조회할 레코드 수

        Returns:
            추이 레코드 리스트
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM score_trends WHERE timestamp > ?'
            params = [cutoff_date]

            if customer_id:
                query += ' AND customer_id = ?'
                params.append(customer_id)

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute('PRAGMA table_info(score_trends)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
