"""System Health Repository.

시스템 건강 상태 모니터링을 담당합니다.
"""
from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from .base import BaseRepository

PSUTIL_AVAILABLE = False
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    pass


class SystemHealthRepository(BaseRepository):
    """시스템 건강 상태 Repository.

    시스템 리소스 사용량, DB 상태 등을 모니터링합니다.
    """

    def record_system_health(
        self,
        cpu_usage_percent: Optional[float] = None,
        memory_usage_percent: Optional[float] = None,
        disk_usage_percent: Optional[float] = None,
        disk_free_gb: Optional[float] = None,
        gpu_usage_percent: Optional[float] = None,
        gpu_memory_usage_percent: Optional[float] = None,
        network_status: str = "ok",
        api_latency_ms: Optional[float] = None,
        active_jobs: int = 0,
        queue_size: int = 0,
    ) -> None:
        """시스템 헬스 기록.

        Args:
            cpu_usage_percent: CPU 사용률
            memory_usage_percent: 메모리 사용률
            disk_usage_percent: 디스크 사용률
            disk_free_gb: 디스크 여유 공간
            gpu_usage_percent: GPU 사용률
            gpu_memory_usage_percent: GPU 메모리 사용률
            network_status: 네트워크 상태
            api_latency_ms: API 지연 시간
            active_jobs: 활성 작업 수
            queue_size: 대기열 크기
        """
        timestamp = datetime.now().isoformat()

        # 기본값 계산 (psutil 사용 가능한 경우)
        if PSUTIL_AVAILABLE:
            if cpu_usage_percent is None:
                cpu_usage_percent = psutil.cpu_percent()
            if memory_usage_percent is None:
                memory_usage_percent = psutil.virtual_memory().percent
            if disk_usage_percent is None:
                disk_usage_percent = psutil.disk_usage('/').percent
            if disk_free_gb is None:
                disk_free_gb = psutil.disk_usage('/').free / (1024**3)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO system_health (
                    timestamp, cpu_usage_percent, memory_usage_percent, disk_usage_percent,
                    disk_free_gb, gpu_usage_percent, gpu_memory_usage_percent, network_status,
                    api_latency_ms, active_jobs, queue_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, cpu_usage_percent, memory_usage_percent, disk_usage_percent,
                  disk_free_gb, gpu_usage_percent, gpu_memory_usage_percent, network_status,
                  api_latency_ms, active_jobs, queue_size))

            conn.commit()
            log.debug(f"시스템 헬스 기록: CPU={cpu_usage_percent}%, MEM={memory_usage_percent}%")
        except Exception as e:
            conn.rollback()
            log.error(f"시스템 헬스 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_system_health(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """시스템 헬스 조회.

        Args:
            hours: 조회할 기간 (시간)
            limit: 조회할 레코드 수

        Returns:
            헬스 레코드 리스트
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM system_health
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (cutoff, limit))

            rows = cursor.fetchall()

            cursor.execute('PRAGMA table_info(system_health)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def check_health(self) -> Dict[str, Any]:
        """DB 상태 확인.

        Returns:
            DB 상태 정보
        """
        try:
            # 파일 크기
            file_size_bytes = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            file_size_mb = file_size_bytes / (1024 * 1024)

            # 연결 테스트
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()

            # 테이블 행 수
            row_counts = {}
            tables = [
                "executions", "logs", "analysis_stats", "model_performance",
                "score_trends", "llm_api_stats", "image_metadata",
                "error_analysis", "system_health", "audit_log"
            ]

            conn = self._get_connection()
            cursor = conn.cursor()
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    row_counts[table] = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    row_counts[table] = 0
            conn.close()

            return {
                "healthy": True,
                "file_size_mb": round(file_size_mb, 2),
                "file_size_bytes": file_size_bytes,
                "row_counts": row_counts,
                "db_path": self.db_path,
                "last_check": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "db_path": self.db_path,
                "last_check": datetime.now().isoformat(),
            }

    def get_slow_queries(self, threshold_ms: int = 100, limit: int = 10) -> List[Dict[str, Any]]:
        """느린 쿼리 로그 조회 (구현 필요).

        Args:
            threshold_ms: 느린 쿼리 기준 (밀리초)
            limit: 조회할 레코드 수

        Returns:
            느린 쿼리 리스트
        """
        # SQLite에는 기본적으로 쿼리 시간 로깅이 없음
        # 추후 쿼리 래퍼 구현 시 추가 가능
        log.warning("get_slow_queries: 현재 구현되지 않음")
        return []
