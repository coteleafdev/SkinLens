"""Execution Stats Repository.

실행 이력 관리를 담당합니다.
"""
from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from .base import BaseRepository


class ExecutionStatsRepository(BaseRepository):
    """실행 이력 Repository.

    executions 테이블의 CRUD 및 통계를 담당합니다.
    """

    def log_execution(
        self,
        input_path: str,
        output_dir: str,
        result: Dict[str, Any],
        execution_time: float,
        success: bool = True,
        resource_stats: Optional[Dict[str, float]] = None,
    ) -> int:
        """실행 이력 기록.

        Args:
            input_path: 입력 이미지 경로
            output_dir: 출력 디렉토리 경로
            result: 분석 결과 딕셔너리
            execution_time: 실행 시간 (초)
            success: 성공 여부
            resource_stats: 리소스 사용량 통계 (ResourceMonitor.stop() 반환값)

        Returns:
            삽입된 레코드 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 분석 결과 추출
            analysis_result = result.get("analysis_result", {})
            overall_score = analysis_result.get("overall_score")
            perceived_age = analysis_result.get("perceived_age")

            # base64 크기 계산
            input_b64_size = len(result.get("input_image_base64", "")) if result.get("input_image_base64") else None
            restored_b64_size = len(result.get("restored_image_base64", "")) if result.get("restored_image_base64") else None

            # 파이프라인 모드
            pipeline_mode = str(result.get("pipeline_mode", {}))

            # 리소스 통계 추출
            memory_peak = resource_stats.get("memory_peak_mb") if resource_stats else None
            memory_avg = resource_stats.get("memory_avg_mb") if resource_stats else None
            cpu_percent_avg = resource_stats.get("cpu_percent_avg") if resource_stats else None
            cpu_time_user = resource_stats.get("cpu_time_user_sec") if resource_stats else None
            cpu_time_system = resource_stats.get("cpu_time_system_sec") if resource_stats else None
            thread_count = resource_stats.get("thread_count") if resource_stats else None

            cursor.execute('''
                INSERT INTO executions
                (timestamp, input_path, output_dir, overall_score, perceived_age,
                 execution_time_sec, pipeline_mode, success, error_message,
                 input_image_base64_size, restored_image_base64_size,
                 memory_peak_mb, memory_avg_mb, cpu_percent_avg,
                 cpu_time_user_sec, cpu_time_system_sec, thread_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                input_path,
                output_dir,
                overall_score,
                perceived_age,
                execution_time,
                pipeline_mode,
                success,
                None if success else result.get("error_message"),
                input_b64_size,
                restored_b64_size,
                memory_peak,
                memory_avg,
                cpu_percent_avg,
                cpu_time_user,
                cpu_time_system,
                thread_count,
            ))

            record_id = cursor.lastrowid
            conn.commit()

            log.debug(f"실행 이력 기록: ID={record_id}, success={success}")
            return record_id
        except Exception as e:
            conn.rollback()
            log.error(f"실행 이력 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_recent_executions(
        self,
        limit: int = 100,
        success_only: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """최근 실행 이력 조회.

        Args:
            limit: 조회할 레코드 수 (기본: 100)
            success_only: 성공한 실행만 조회 (None: 전체, True: 성공만, False: 실패만)

        Returns:
            실행 이력 레코드 리스트 (dict 형태)
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM executions'
            params = []

            if success_only is not None:
                query += ' WHERE success = ?'
                params.append(success_only)

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]

            return rows
        finally:
            conn.close()

    def get_statistics(
        self,
        days: int = 7,
    ) -> Dict[str, Any]:
        """기간별 통계 조회.

        Args:
            days: 조회할 기간 (일)

        Returns:
            통계 딕셔너리
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 기간 계산
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            # 전체 실행 수
            cursor.execute('''
                SELECT COUNT(*) FROM executions
                WHERE timestamp >= ?
            ''', (cutoff_date,))
            total_count = cursor.fetchone()[0]

            # 성공/실패 수
            cursor.execute('''
                SELECT success, COUNT(*) FROM executions
                WHERE timestamp >= ?
                GROUP BY success
            ''', (cutoff_date,))
            success_counts = dict(cursor.fetchall())

            # 평균 점수 (성공한 경우만)
            cursor.execute('''
                SELECT AVG(overall_score) FROM executions
                WHERE timestamp >= ? AND success = 1 AND overall_score IS NOT NULL
            ''', (cutoff_date,))
            avg_score = cursor.fetchone()[0]

            # 평균 실행 시간
            cursor.execute('''
                SELECT AVG(execution_time_sec) FROM executions
                WHERE timestamp >= ? AND execution_time_sec IS NOT NULL
            ''', (cutoff_date,))
            avg_execution_time = cursor.fetchone()[0]

            # 평균 메모리 사용량
            cursor.execute('''
                SELECT AVG(memory_peak_mb) FROM executions
                WHERE timestamp >= ? AND memory_peak_mb IS NOT NULL
            ''', (cutoff_date,))
            avg_memory_peak = cursor.fetchone()[0]

            # 평균 CPU 사용률
            cursor.execute('''
                SELECT AVG(cpu_percent_avg) FROM executions
                WHERE timestamp >= ? AND cpu_percent_avg IS NOT NULL
            ''', (cutoff_date,))
            avg_cpu_percent = cursor.fetchone()[0]

            # 일별 실행 수
            cursor.execute('''
                SELECT DATE(timestamp) as date, COUNT(*) as count
                FROM executions
                WHERE timestamp >= ?
                GROUP BY date
                ORDER BY date DESC
            ''', (cutoff_date,))
            daily_counts = cursor.fetchall()

            return {
                "period_days": days,
                "total_executions": total_count,
                "successful_executions": success_counts.get(1, 0),
                "failed_executions": success_counts.get(0, 0),
                "success_rate": (success_counts.get(1, 0) / total_count * 100) if total_count > 0 else 0,
                "avg_score": round(avg_score, 2) if avg_score else None,
                "avg_execution_time_sec": round(avg_execution_time, 2) if avg_execution_time else None,
                "avg_memory_peak_mb": round(avg_memory_peak, 2) if avg_memory_peak else None,
                "avg_cpu_percent": round(avg_cpu_percent, 2) if avg_cpu_percent else None,
                "daily_counts": daily_counts,
            }
        finally:
            conn.close()

    def cleanup_old_records(
        self,
        days: int = 90,
    ) -> int:
        """오래된 레코드 삭제.

        Args:
            days: 보관할 기간 (일), 이전의 레코드 삭제

        Returns:
            삭제된 레코드 수
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM executions
                WHERE timestamp < ?
            ''', (cutoff_date,))

            deleted_count = cursor.rowcount
            conn.commit()

            log.info(f"오래된 실행 레코드 삭제 완료: {deleted_count}개 레코드 ({days}일 이전)")
            return deleted_count
        except Exception as e:
            conn.rollback()
            log.error(f"오래된 실행 레코드 삭제 실패: {e}")
            raise
        finally:
            conn.close()
