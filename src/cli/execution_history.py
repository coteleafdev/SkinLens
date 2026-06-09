"""
execution_history.py — CLI 실행 이력 추적을 위한 SQLite 데이터베이스

서버 환경에서 피부 분석 실행 이력을 구조화하여 저장하고 조회합니다.
메모리, CPU 사용량 등 리소스 모니터링 기능을 포함합니다.
로그 DB 저장 기능을 포함합니다.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

import queue
import threading

log = logging.getLogger(__name__)


class ConnectionPool:
    """SQLite 연결 풀 클래스.

    SQLite 연결을 풀링하여 성능을 향상시킵니다.
    """

    def __init__(self, db_path: str, max_connections: int = 10):
        """연결 풀 초기화.

        Args:
            db_path: DB 파일 경로
            max_connections: 최대 연결 수
        """
        self.db_path = db_path
        self.max_connections = max_connections
        self.pool = queue.Queue(max_connections)
        self.lock = threading.Lock()
        self._created = 0

    def get_connection(self) -> sqlite3.Connection:
        """연결 풀에서 연결 가져오기.

        Returns:
            SQLite 연결
        """
        with self.lock:
            try:
                conn = self.pool.get_nowait()
            except queue.Empty:
                # 지연 생성: 연결이 없으면 새로 생성
                if self._created < self.max_connections:
                    conn = sqlite3.connect(self.db_path, check_same_thread=False)
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    self._created += 1
                else:
                    # 최대 연결 수에 도달하면 대기
                    conn = self.pool.get()
        return conn

    def return_connection(self, conn: sqlite3.Connection):
        """연결을 풀에 반환.

        Args:
            conn: 반환할 연결
        """
        self.pool.put(conn)

    def close_all(self):
        """모든 연결 닫기."""
        with self.lock:
            while not self.pool.empty():
                try:
                    conn = self.pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
            self._created = 0


class ResourceMonitor:
    """리소스 사용량 모니터링 클래스.
    
    psutil을 사용하여 메모리, CPU 사용량을 측정합니다.
    """
    
    def __init__(self):
        """모니터 초기화."""
        if not PSUTIL_AVAILABLE:
            raise ImportError("psutil 패키지가 필요합니다. pip install psutil")
        
        self.process = psutil.Process()
        self._start_time = time.time()
        self._start_cpu_times = self.process.cpu_times()
        self._start_memory_info = self.process.memory_info()
        self._cpu_samples = []
        self._memory_samples = []
        self._monitoring = False
    
    def start(self) -> None:
        """모니터링 시작."""
        self._start_time = time.time()
        self._start_cpu_times = self.process.cpu_times()
        self._start_memory_info = self.process.memory_info()
        self._cpu_samples = []
        self._memory_samples = []
        self._monitoring = True
    
    def sample(self) -> None:
        """현재 리소스 사용량 샘플링."""
        if not self._monitoring:
            return
        
        try:
            # CPU 사용량 샘플
            cpu_percent = self.process.cpu_percent(interval=0.1)
            self._cpu_samples.append(cpu_percent)
            
            # 메모리 사용량 샘플 (MB)
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            self._memory_samples.append(memory_mb)
        except Exception as e:
            log.debug("메모리 샘플링 실패: %s", e)
    
    def stop(self) -> Dict[str, float]:
        """모니터링 종료 및 통계 계산.
        
        Returns:
            리소스 사용량 통계 딕셔너리
        """
        self._monitoring = False
        
        end_time = time.time()
        end_cpu_times = self.process.cpu_times()
        end_memory_info = self.process.memory_info()
        
        # 실행 시간
        execution_time = end_time - self._start_time
        
        # CPU 시간
        cpu_time_user = end_cpu_times.user - self._start_cpu_times.user
        cpu_time_system = end_cpu_times.system - self._start_cpu_times.system
        
        # CPU 사용률 평균
        cpu_percent_avg = sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else 0
        
        # 메모리 사용량
        memory_peak_mb = end_memory_info.rss / 1024 / 1024
        memory_avg_mb = sum(self._memory_samples) / len(self._memory_samples) if self._memory_samples else memory_peak_mb
        
        # 스레드 수
        thread_count = self.process.num_threads()
        
        return {
            "memory_peak_mb": round(memory_peak_mb, 2),
            "memory_avg_mb": round(memory_avg_mb, 2),
            "cpu_percent_avg": round(cpu_percent_avg, 2),
            "cpu_time_user_sec": round(cpu_time_user, 2),
            "cpu_time_system_sec": round(cpu_time_system, 2),
            "thread_count": thread_count,
        }


class ExecutionHistoryDB:
    """실행 이력 데이터베이스 관리 클래스.

    SQLite를 사용하여 다음 정보를 저장합니다:
        - 타임스탬프
        - 입력/출력 경로
        - 분석 결과 (종합 점수, 인지 나이)
        - 실행 시간
        - 파이프라인 모드
        - 성공/실패 여부
        - 에러 메시지
        - 리소스 사용량 (메모리, CPU)
    """

    def __init__(self, db_path: str = "results/execution_history.db", use_connection_pool: bool = False):
        """데이터베이스 초기화.

        Args:
            db_path: 데이터베이스 파일 경로 (기본: results/execution_history.db)
            use_connection_pool: 연결 풀 사용 여부 (기본: False)
        """
        self.db_path = db_path
        self.use_connection_pool = use_connection_pool
        self._connection_pool: Optional[ConnectionPool] = None
        if use_connection_pool:
            self._connection_pool = ConnectionPool(db_path)
        self._init_db()

        # Repository 초기화 (Repository 패턴 분리)
        from .repositories import (
            CustomerDataRepository,
            SystemHealthRepository,
            LogRepository,
            ErrorAuditRepository,
            ExecutionStatsRepository,
            AnalysisStatsRepository,
            LLMAPIRepository,
            ImageMetadataRepository,
        )

        self.customer_data = CustomerDataRepository(db_path)
        self.system_health = SystemHealthRepository(db_path)
        self.log = LogRepository(db_path)
        self.error_audit = ErrorAuditRepository(db_path)
        self.execution_stats = ExecutionStatsRepository(db_path)
        self.analysis_stats = AnalysisStatsRepository(db_path)
        self.llm_api = LLMAPIRepository(db_path)
        self.image_metadata = ImageMetadataRepository(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """연결 가져오기.

        Returns:
            SQLite 연결
        """
        if self.use_connection_pool and self._connection_pool:
            return self._connection_pool.get_connection()
        return sqlite3.connect(self.db_path)

    def _return_connection(self, conn: sqlite3.Connection) -> None:
        """연결 반환.

        Args:
            conn: 반환할 연결
        """
        if self.use_connection_pool and self._connection_pool:
            self._connection_pool.return_connection(conn)
        else:
            conn.close()

    def close(self) -> None:
        """리소스 정리."""
        if self._connection_pool:
            self._connection_pool.close_all()

    def _init_db(self) -> None:
        """데이터베이스 테이블 생성."""
        conn = sqlite3.connect(self.db_path)
        try:
            # 트랜잭션 시작
            conn.execute("BEGIN")
            
            # 코어 테이블 생성
            self._init_core_tables(conn)
            
            # 통계 테이블 생성
            self._init_stats_tables(conn)
            
            # 감사 테이블 생성
            self._init_audit_tables(conn)
            
            # 인덱스 생성
            self._init_indexes(conn)
            
            # 트랜잭션 커밋
            conn.commit()
        except Exception as e:
            # 에러 시 롤백
            conn.rollback()
            log.error(f"DB 초기화 실패: {e}")
            raise
        finally:
            conn.close()
    
    def _init_core_tables(self, conn: sqlite3.Connection) -> None:
        """코어 테이블 생성 (executions, logs)."""
        cursor = conn.cursor()
        
        # executions 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                input_path TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                overall_score REAL,
                perceived_age REAL,
                execution_time_sec REAL,
                pipeline_mode TEXT,
                success BOOLEAN,
                error_message TEXT,
                input_image_base64_size INTEGER,
                restored_image_base64_size INTEGER,
                -- 리소스 사용량
                memory_peak_mb REAL,
                memory_avg_mb REAL,
                cpu_percent_avg REAL,
                cpu_time_user_sec REAL,
                cpu_time_system_sec REAL,
                thread_count INTEGER
            )
        ''')
        
        # logs 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                log_name TEXT NOT NULL,
                message TEXT NOT NULL,
                module TEXT,
                function TEXT,
                line_number INTEGER
            )
        ''')
    
    def _init_stats_tables(self, conn: sqlite3.Connection) -> None:
        """통계 테이블 생성 (analysis_stats, model_performance, score_trends, llm_api_stats, image_metadata, error_analysis, system_health)."""
        cursor = conn.cursor()
        
        # analysis_stats 테이블 (1. 사용자 분석 통계)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                customer_id TEXT,
                total_analyses INTEGER DEFAULT 0,
                successful_analyses INTEGER DEFAULT 0,
                failed_analyses INTEGER DEFAULT 0,
                avg_score_original REAL,
                avg_score_restored REAL,
                avg_execution_time_sec REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # model_performance 테이블 (2. 모델 성능 메트릭)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model_type TEXT NOT NULL,
                execution_time_ms REAL,
                memory_peak_mb REAL,
                cpu_percent_avg REAL,
                success BOOLEAN,
                error_type TEXT,
                input_resolution TEXT,
                output_quality_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # score_trends 테이블 (3. 점수 변화 추이)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS score_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT,
                timestamp TEXT NOT NULL,
                overall_score REAL,
                melasma_score REAL,
                redness_score REAL,
                wrinkle_score REAL,
                pore_score REAL,
                improvement_delta REAL,
                analysis_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # llm_api_stats 테이블 (4. LLM API 사용 통계)
        # 기존 gemini_api_stats 테이블 삭제 (서비스 미운영으로 데이터 없음)
        cursor.execute('DROP TABLE IF EXISTS gemini_api_stats')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_api_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                customer_id TEXT,
                request_type TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                execution_time_sec REAL,
                success BOOLEAN,
                error_message TEXT,
                estimated_cost_usd REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # image_metadata 테이블 (5. 이미지 메타데이터)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER,
                image_type TEXT NOT NULL,
                file_size_bytes INTEGER,
                width INTEGER,
                height INTEGER,
                format TEXT,
                exif_date_taken TEXT,
                exif_device TEXT,
                exif_location TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # error_analysis 테이블 (6. 에러 분석)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT,
                module TEXT,
                function TEXT,
                line_number INTEGER,
                stack_trace TEXT,
                customer_id TEXT,
                image_path TEXT,
                pipeline_mode TEXT,
                severity TEXT,
                resolved BOOLEAN DEFAULT 0,
                resolved_at TIMESTAMP,
                resolution_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # system_health 테이블 (8. 시스템 헬스 체크)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu_usage_percent REAL,
                memory_usage_percent REAL,
                disk_usage_percent REAL,
                disk_free_gb REAL,
                gpu_usage_percent REAL,
                gpu_memory_usage_percent REAL,
                network_status TEXT,
                api_latency_ms REAL,
                active_jobs INTEGER,
                queue_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    def _init_audit_tables(self, conn: sqlite3.Connection) -> None:
        """감사 테이블 생성 (audit_log)."""
        cursor = conn.cursor()
        
        # audit_log 테이블 (감사 로그)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor_customer_id TEXT,
                target_customer_id TEXT,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                user_role TEXT,
                ip_address TEXT,
                user_agent TEXT,
                success BOOLEAN,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    def _init_indexes(self, conn: sqlite3.Connection) -> None:
        """인덱스 생성."""
        cursor = conn.cursor()
        
        # executions 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_executions_timestamp 
            ON executions(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_executions_success 
            ON executions(success)
        ''')
        
        # logs 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp 
            ON logs(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_logs_level 
            ON logs(level)
        ''')
        
        # analysis_stats 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_analysis_stats_date 
            ON analysis_stats(date DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_analysis_stats_customer 
            ON analysis_stats(customer_id)
        ''')
        
        # model_performance 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_model_performance_timestamp 
            ON model_performance(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_model_performance_type 
            ON model_performance(model_type)
        ''')
        
        # score_trends 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_score_trends_customer 
            ON score_trends(customer_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_score_trends_timestamp 
            ON score_trends(timestamp DESC)
        ''')
        
        # llm_api_stats 인덱스
        # 기존 인덱스 삭제
        cursor.execute('DROP INDEX IF EXISTS idx_gemini_api_stats_timestamp')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_llm_api_stats_timestamp 
            ON llm_api_stats(timestamp DESC)
        ''')
        
        # error_analysis 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_error_analysis_timestamp 
            ON error_analysis(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_error_analysis_resolved 
            ON error_analysis(resolved)
        ''')
        
        # system_health 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_system_health_timestamp 
            ON system_health(timestamp DESC)
        ''')
        
        # audit_log 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp 
            ON audit_log(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_log_actor 
            ON audit_log(actor_customer_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_log_target 
            ON audit_log(target_customer_id)
        ''')

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

        [위임] ExecutionStatsRepository.log_execution()로 위임합니다.

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
        return self.execution_stats.log_execution(
            input_path=input_path,
            output_dir=output_dir,
            result=result,
            execution_time=execution_time,
            success=success,
            resource_stats=resource_stats,
        )

    def get_recent_executions(
        self,
        limit: int = 100,
        success_only: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """최근 실행 이력 조회.

        [위임] ExecutionStatsRepository.get_recent_executions()로 위임합니다.

        Args:
            limit: 조회할 레코드 수 (기본: 100)
            success_only: 성공한 실행만 조회 (None: 전체, True: 성공만, False: 실패만)

        Returns:
            실행 이력 레코드 리스트 (dict 형태)
        """
        return self.execution_stats.get_recent_executions(
            limit=limit,
            success_only=success_only,
        )

    def get_statistics(
        self,
        days: int = 7,
    ) -> Dict[str, Any]:
        """기간별 통계 조회.

        [위임] ExecutionStatsRepository.get_statistics()로 위임합니다.

        Args:
            days: 조회할 기간 (일)

        Returns:
            통계 딕셔너리
        """
        return self.execution_stats.get_statistics(days=days)

    def get_error_summary(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """최근 에러 이력 조회.

        Args:
            limit: 조회할 레코드 수

        Returns:
            에러 레코드 리스트 (dict 형태)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM executions
            WHERE success = 0
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return rows

    def cleanup_old_records(
        self,
        days: int = 90,
    ) -> int:
        """오래된 레코드 삭제.

        [위임] ExecutionStatsRepository.cleanup_old_records()로 위임합니다.

        Args:
            days: 보관할 기간 (일), 이전의 레코드 삭제

        Returns:
            삭제된 레코드 수
        """
        return self.execution_stats.cleanup_old_records(days=days)

    # ── 로그 관련 메서드 ─────────────────────────────────────────────────────────

    def insert_log(
        self,
        level: str,
        log_name: str,
        message: str,
        module: Optional[str] = None,
        function: Optional[str] = None,
        line_number: Optional[int] = None,
        retention_days: int = 7,
    ) -> None:
        """로그 레코드 삽입.

        [위임] LogRepository.insert_log()로 위임합니다.

        Args:
            level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
            log_name: 로거 이름
            message: 로그 메시지
            module: 모듈 이름 (선택)
            function: 함수 이름 (선택)
            line_number: 라인 번호 (선택)
            retention_days: 보관 기간 (일). 이전의 로그 자동 삭제.
        """
        return self.log.insert_log(
            level=level,
            log_name=log_name,
            message=message,
            module=module,
            function=function,
            line_number=line_number,
            retention_days=retention_days,
        )

    def get_logs(
        self,
        level: Optional[str] = None,
        limit: int = 100,
        hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """로그 레코드 조회.

        [위임] LogRepository.get_logs()로 위임합니다.

        Args:
            level: 필터링할 로그 레벨 (선택)
            limit: 조회할 레코드 수
            hours: 최근 N시간 내의 로그만 조회 (선택)

        Returns:
            로그 레코드 리스트
        """
        return self.log.get_logs(level=level, limit=limit, hours=hours)

    def export_logs_to_csv(
        self,
        output_path: str,
        level: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> int:
        """로그를 CSV 파일로 내보내기.

        [위임] LogRepository.export_logs_to_csv()로 위임합니다.

        Args:
            output_path: 출력 CSV 파일 경로
            level: 필터링할 로그 레벨 (선택)
            hours: 최근 N시간 내의 로그만 내보내기 (선택)

        Returns:
            내보낸 레코드 수
        """
        return self.log.export_logs_to_csv(output_path=output_path, level=level, hours=hours)

    def export_logs_to_json(
        self,
        output_path: str,
        level: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> int:
        """로그를 JSON 파일로 내보내기.

        [위임] LogRepository.export_logs_to_json()로 위임합니다.

        Args:
            output_path: 출력 JSON 파일 경로
            level: 필터링할 로그 레벨 (선택)
            hours: 최근 N시간 내의 로그만 내보내기 (선택)

        Returns:
            내보낸 레코드 수
        """
        return self.log.export_logs_to_json(output_path=output_path, level=level, hours=hours)

    def cleanup_old_logs(
        self,
        days: int = 7,
    ) -> int:
        """오래된 로그 삭제.

        [위임] LogRepository.cleanup_old_logs()로 위임합니다.

        Args:
            days: 보관할 기간 (일), 이전의 로그 삭제

        Returns:
            삭제된 레코드 수
        """
        return self.log.cleanup_old_logs(days=days)

    # ── 분석 통계 메서드 (1. 사용자 분석 통계) ─────────────────────────────

    def record_analysis_stat(
        self,
        customer_id: Optional[str],
        success: bool,
        score_original: Optional[float],
        score_restored: Optional[float],
        execution_time_sec: float,
    ) -> None:
        """분석 통계 기록.

        [위임] AnalysisStatsRepository.record_analysis_stat()로 위임합니다.

        Args:
            customer_id: 고객 ID
            success: 성공 여부
            score_original: 원본 점수
            score_restored: 복원 점수
            execution_time_sec: 실행 시간
        """
        return self.analysis_stats.record_analysis_stat(
            customer_id=customer_id,
            success=success,
            score_original=score_original,
            score_restored=score_restored,
            execution_time_sec=execution_time_sec,
        )

    def get_analysis_stats(
        self,
        days: int = 7,
        customer_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """분석 통계 조회.

        [위임] AnalysisStatsRepository.get_analysis_stats()로 위임합니다.

        Args:
            days: 조회할 기간 (일)
            customer_id: 고객 ID (선택)

        Returns:
            통계 레코드 리스트
        """
        return self.analysis_stats.get_analysis_stats(days=days, customer_id=customer_id)

    # ── 모델 성능 메서드 (2. 모델 성능 메트릭) ─────────────────────────────

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

        [위임] AnalysisStatsRepository.record_model_performance()로 위임합니다.

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
        return self.analysis_stats.record_model_performance(
            model_type=model_type,
            execution_time_ms=execution_time_ms,
            memory_peak_mb=memory_peak_mb,
            cpu_percent_avg=cpu_percent_avg,
            success=success,
            error_type=error_type,
            input_resolution=input_resolution,
            output_quality_score=output_quality_score,
        )

    def get_model_performance(
        self,
        model_type: Optional[str] = None,
        hours: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """모델 성능 조회.

        [위임] AnalysisStatsRepository.get_model_performance()로 위임합니다.

        Args:
            model_type: 모델 유형 필터
            hours: 최근 N시간
            limit: 조회할 레코드 수

        Returns:
            성능 레코드 리스트
        """
        return self.analysis_stats.get_model_performance(
            model_type=model_type,
            hours=hours,
            limit=limit,
        )

    # ── 점수 추이 메서드 (3. 점수 변화 추이) ─────────────────────────────

    def record_score_trend(
        self,
        customer_id: Optional[str],
        overall_score: float,
        measurements: Dict[str, float],
        improvement_delta: Optional[float] = None,
    ) -> None:
        """점수 추이 기록.

        [위임] AnalysisStatsRepository.record_score_trend()로 위임합니다.

        Args:
            customer_id: 고객 ID
            overall_score: 종합 점수
            measurements: 측정항목 점수 딕셔너리
            improvement_delta: 이전 대비 개선 정도
        """
        return self.analysis_stats.record_score_trend(
            customer_id=customer_id,
            overall_score=overall_score,
            measurements=measurements,
            improvement_delta=improvement_delta,
        )

    def get_score_trends(
        self,
        customer_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """점수 추이 조회.

        [위임] AnalysisStatsRepository.get_score_trends()로 위임합니다.

        Args:
            customer_id: 고객 ID
            days: 조회할 기간 (일)
            limit: 조회할 레코드 수

        Returns:
            추이 레코드 리스트
        """
        return self.analysis_stats.get_score_trends(
            customer_id=customer_id,
            days=days,
            limit=limit,
        )

    # ── LLM API 통계 메서드 (4. LLM API 사용 통계) ───────────────────

    def record_llm_api_call(
        self,
        customer_id: Optional[str],
        request_type: str,
        input_tokens: int,
        output_tokens: int,
        execution_time_sec: float,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """LLM API 호출 기록.

        [위임] LLMAPIRepository.record_llm_api_call()로 위임합니다.

        Args:
            customer_id: 고객 ID
            request_type: 요청 유형
            input_tokens: 입력 토큰 수
            output_tokens: 출력 토큰 수
            execution_time_sec: 실행 시간
            success: 성공 여부
            error_message: 에러 메시지
        """
        return self.llm_api.record_llm_api_call(
            customer_id=customer_id,
            request_type=request_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            execution_time_sec=execution_time_sec,
            success=success,
            error_message=error_message,
        )

    def get_llm_api_stats(
        self,
        customer_id: Optional[str] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """LLM API 통계 조회.

        [위임] LLMAPIRepository.get_llm_api_stats()로 위임합니다.

        Args:
            customer_id: 고객 ID
            days: 조회할 기간 (일)

        Returns:
            통계 레코드 리스트
        """
        return self.llm_api.get_llm_api_stats(
            customer_id=customer_id,
            days=days,
        )

    # ── 이미지 메타데이터 메서드 (5. 이미지 메타데이터) ─────────────────────

    def record_image_metadata(
        self,
        analysis_id: int,
        image_type: str,
        file_size_bytes: int,
        width: int,
        height: int,
        format: str,
        exif_date_taken: Optional[str] = None,
        exif_device: Optional[str] = None,
        exif_location: Optional[str] = None,
    ) -> None:
        """이미지 메타데이터 기록.

        [위임] ImageMetadataRepository.record_image_metadata()로 위임합니다.

        Args:
            analysis_id: 분석 ID
            image_type: 이미지 유형
            file_size_bytes: 파일 크기
            width: 너비
            height: 높이
            format: 포맷
            exif_date_taken: EXIF 촬영일
            exif_device: EXIF 기기
            exif_location: EXIF 위치
        """
        return self.image_metadata.record_image_metadata(
            analysis_id=analysis_id,
            image_type=image_type,
            file_size_bytes=file_size_bytes,
            width=width,
            height=height,
            format=format,
            exif_date_taken=exif_date_taken,
            exif_device=exif_device,
            exif_location=exif_location,
        )

    def get_image_metadata(
        self,
        analysis_id: Optional[int] = None,
        image_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """이미지 메타데이터 조회.

        [위임] ImageMetadataRepository.get_image_metadata()로 위임합니다.

        Args:
            analysis_id: 분석 ID
            image_type: 이미지 유형

        Returns:
            메타데이터 레코드 리스트
        """
        return self.image_metadata.get_image_metadata(
            analysis_id=analysis_id,
            image_type=image_type,
        )

    # ── 에러 분석 메서드 (6. 에러 분석) ─────────────────────────────

    def record_error(
        self,
        error_type: str,
        error_message: str,
        module: Optional[str] = None,
        function: Optional[str] = None,
        line_number: Optional[int] = None,
        stack_trace: Optional[str] = None,
        customer_id: Optional[str] = None,
        image_path: Optional[str] = None,
        pipeline_mode: Optional[str] = None,
        severity: str = "medium",
    ) -> None:
        """에러 기록.

        [위임] ErrorAuditRepository.record_error()로 위임합니다.

        Args:
            error_type: 에러 유형
            error_message: 에러 메시지
            module: 모듈
            function: 함수
            line_number: 라인 번호
            stack_trace: 스택 트레이스
            customer_id: 고객 ID
            image_path: 이미지 경로
            pipeline_mode: 파이프라인 모드
            severity: 심각도
        """
        return self.error_audit.record_error(
            error_type=error_type,
            error_message=error_message,
            module=module,
            function=function,
            line_number=line_number,
            stack_trace=stack_trace,
            customer_id=customer_id,
            image_path=image_path,
            pipeline_mode=pipeline_mode,
            severity=severity,
        )

    def get_errors(
        self,
        resolved: Optional[bool] = None,
        severity: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
        customer_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """에러 조회.

        [위임] ErrorAuditRepository.get_errors()로 위임합니다.

        Args:
            resolved: 해결 여부
            severity: 심각도
            days: 조회할 기간 (일)
            limit: 조회할 레코드 수
            customer_id: 고객 ID 필터

        Returns:
            에러 레코드 리스트
        """
        return self.error_audit.get_errors(
            resolved=resolved,
            severity=severity,
            days=days,
            limit=limit,
            customer_id=customer_id,
        )

    def resolve_error(self, error_id: int, resolution_note: str) -> None:
        """에러 해결 표시.

        [위임] ErrorAuditRepository.resolve_error()로 위임합니다.

        Args:
            error_id: 에러 ID
            resolution_note: 해결 노트
        """
        return self.error_audit.resolve_error(error_id=error_id, resolution_note=resolution_note)

    def get_error_summary(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """최근 에러 이력 조회.

        [위임] ErrorAuditRepository.get_error_summary()로 위임합니다.

        Args:
            limit: 조회할 레코드 수

        Returns:
            에러 레코드 리스트 (dict 형태)
        """
        return self.error_audit.get_error_summary(limit=limit)

    # ── 시스템 헬스 메서드 (8. 시스템 헬스 체크) ─────────────────────────────

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

        [위임] SystemHealthRepository.record_system_health()로 위임합니다.

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
        return self.system_health.record_system_health(
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_percent=memory_usage_percent,
            disk_usage_percent=disk_usage_percent,
            disk_free_gb=disk_free_gb,
            gpu_usage_percent=gpu_usage_percent,
            gpu_memory_usage_percent=gpu_memory_usage_percent,
            network_status=network_status,
            api_latency_ms=api_latency_ms,
            active_jobs=active_jobs,
            queue_size=queue_size,
        )

    def get_system_health(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """시스템 헬스 조회.

        [위임] SystemHealthRepository.get_system_health()로 위임합니다.

        Args:
            hours: 조회할 기간 (시간)
            limit: 조회할 레코드 수

        Returns:
            헬스 레코드 리스트
        """
        return self.system_health.get_system_health(hours=hours, limit=limit)

    # ── 감사 로그 메서드 ───────────────────────────────────────────────────

    def record_audit_log(
        self,
        actor_customer_id: Optional[str],
        target_customer_id: Optional[str],
        endpoint: str,
        method: str,
        user_role: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """감사 로그 기록.

        [위임] ErrorAuditRepository.record_audit_log()로 위임합니다.

        Args:
            actor_customer_id: 수행자 고객 ID
            target_customer_id: 대상 고객 ID
            endpoint: API 엔드포인트
            method: HTTP 메서드
            user_role: 사용자 역할
            ip_address: IP 주소
            user_agent: 사용자 에이전트
            success: 성공 여부
            error_message: 에러 메시지
        """
        return self.error_audit.record_audit_log(
            actor_customer_id=actor_customer_id,
            target_customer_id=target_customer_id,
            endpoint=endpoint,
            method=method,
            user_role=user_role,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
        )

    def get_audit_logs(
        self,
        actor_customer_id: Optional[str] = None,
        target_customer_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """감사 로그 조회.

        [위임] ErrorAuditRepository.get_audit_logs()로 위임합니다.

        Args:
            actor_customer_id: 수행자 고객 ID
            target_customer_id: 대상 고객 ID
            days: 조회할 기간 (일)
            limit: 조회할 레코드 수

        Returns:
            감사 로그 리스트
        """
        return self.error_audit.get_audit_logs(
            actor_customer_id=actor_customer_id,
            target_customer_id=target_customer_id,
            days=days,
            limit=limit,
        )

    # ── 고객 데이터 관리 메서드 ───────────────────────────────────────────

    def delete_customer_data(self, customer_id: str) -> int:
        """고객 데이터 삭제 (GDPR 준수).

        [위임] CustomerDataRepository.delete_customer_data()로 위임합니다.

        Args:
            customer_id: 고객 ID

        Returns:
            삭제된 총 레코드 수
        """
        return self.customer_data.delete_customer_data(customer_id)

    def export_customer_data(self, customer_id: str, output_path: str) -> int:
        """고객 데이터 내보내기 (JSON).

        [위임] CustomerDataRepository.export_customer_data()로 위임합니다.

        Args:
            customer_id: 고객 ID
            output_path: 출력 파일 경로

        Returns:
            내보낸 총 레코드 수
        """
        # Repository에서 필요한 데이터 수집
        analysis_stats_data = self.get_analysis_stats(days=365, customer_id=customer_id)
        score_trends_data = self.get_score_trends(customer_id=customer_id, days=365)
        llm_api_stats_data = self.get_llm_api_stats(customer_id=customer_id, days=365)
        errors_data = self.get_errors(customer_id=customer_id, days=365)
        audit_logs_data = self.get_audit_logs(actor_customer_id=customer_id, days=365)

        return self.customer_data.export_customer_data(
            customer_id=customer_id,
            output_path=output_path,
            analysis_stats_data=analysis_stats_data,
            score_trends_data=score_trends_data,
            llm_api_stats_data=llm_api_stats_data,
            errors_data=errors_data,
            audit_logs_data=audit_logs_data,
        )

    def check_health(self) -> Dict[str, Any]:
        """DB 상태 확인.

        [위임] SystemHealthRepository.check_health()로 위임합니다.

        Returns:
            DB 상태 정보
        """
        return self.system_health.check_health()

    def get_slow_queries(self, threshold_ms: int = 100, limit: int = 10) -> List[Dict[str, Any]]:
        """느린 쿼리 로그 조회 (구현 필요).

        [위임] SystemHealthRepository.get_slow_queries()로 위임합니다.

        Args:
            threshold_ms: 느린 쿼리 기준 (밀리초)
            limit: 조회할 레코드 수

        Returns:
            느린 쿼리 리스트
        """
        return self.system_health.get_slow_queries(threshold_ms=threshold_ms, limit=limit)

    @contextmanager
    def transaction(self):
        """트랜잭션 컨텍스트 매니저.

        사용 예:
            with db.transaction():
                db.record_analysis_stat(...)
                db.record_model_performance(...)
        """
        conn = self._get_connection()
        try:
            conn.execute("BEGIN TRANSACTION")
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._return_connection(conn)

    def _execute_with_retry(self, query: str, params: tuple = (), fetch: bool = False):
        """재시도 메커니즘이 적용된 쿼리 실행.

        Args:
            query: SQL 쿼리
            params: 쿼리 파라미터
            fetch: 결과를 반환할지 여부

        Returns:
            쿼리 결과 (fetch=True인 경우)
        """
        if TENACITY_AVAILABLE:
            @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
            def _execute():
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                if fetch:
                    cursor.execute(query, params)
                    result = cursor.fetchall()
                    conn.close()
                    return result
                else:
                    cursor.execute(query, params)
                    conn.commit()
                    conn.close()
            return _execute()
        else:
            # tenacity가 없으면 일반 실행
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if fetch:
                cursor.execute(query, params)
                result = cursor.fetchall()
                conn.close()
                return result
            else:
                cursor.execute(query, params)
                conn.commit()
                conn.close()


# ── DB 마이그레이션 관리자 ─────────────────────────────────────────────

class DBMigrationManager:
    """DB 마이그레이션 관리자.
    
    버전 관리 기반 마이그레이션을 자동화합니다.
    """
    
    def __init__(self, db_path: str):
        """마이그레이션 관리자 초기화.

        Args:
            db_path: DB 파일 경로
        """
        self.db_path = db_path
        self.migrations = []
    
    def get_current_version(self) -> int:
        """현재 DB 버전 조회.

        Returns:
            현재 버전 (없으면 0)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # schema_version 테이블 확인
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='schema_version'
        """)
        
        if cursor.fetchone() is None:
            # 테이블 생성
            cursor.execute("""
                CREATE TABLE schema_version (version INTEGER)
            """)
            cursor.execute("INSERT INTO schema_version (version) VALUES (0)")
            conn.commit()
            conn.close()
            return 0
        
        cursor.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]
        conn.close()
        return version
    
    def migrate(self):
        """마이그레이션 실행."""
        current_version = self.get_current_version()
        
        for migration in self.migrations:
            if migration["version"] > current_version:
                self.apply_migration(migration)
    
    def apply_migration(self, migration: Dict[str, Any]):
        """마이그레이션 적용.

        Args:
            migration: 마이그레이션 정보
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(migration["sql"])
            cursor.execute("UPDATE schema_version SET version = ?", (migration['version'],))
            conn.commit()
            conn.close()
            log.info(f"Migration {migration['version']} applied successfully")
        except Exception as e:
            log.error(f"Migration {migration['version']} failed: {e}")
            raise


# ── 데이터 아카이빙 ─────────────────────────────────────────────────────

def archive_old_data(db_path: str, days: int = 90):
    """지정 기간보다 오래된 데이터 아카이빙.

    Args:
        db_path: DB 파일 경로
        days: 보관 기간 (일)
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 아카이브 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS executions_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            input_path TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            overall_score REAL,
            perceived_age REAL,
            execution_time_sec REAL,
            pipeline_mode TEXT,
            success BOOLEAN,
            error_message TEXT,
            input_image_base64_size INTEGER,
            restored_image_base64_size INTEGER,
            memory_peak_mb REAL,
            memory_avg_mb REAL,
            cpu_percent_avg REAL,
            cpu_time_user_sec REAL,
            cpu_time_system_sec REAL,
            thread_count INTEGER
        )
    """)
    
    # 아카이브 테이블로 이동
    cursor.execute('''
        INSERT INTO executions_archive
        SELECT * FROM executions
        WHERE timestamp < ?
    ''', (cutoff_date,))
    
    # 원본 테이블에서 삭제
    cursor.execute('''
        DELETE FROM executions
        WHERE timestamp < ?
    ''', (cutoff_date,))
    
    conn.commit()
    conn.close()
    
    log.info(f"Data older than {days} days archived")


# ── DB 암호화 및 읽기 전용 복제본 ─────────────────────────────────────

def create_readonly_replica(source_db: str, replica_db: str):
    """읽기 전용 복제본 생성.

    Args:
        source_db: 원본 DB 경로
        replica_db: 복제본 DB 경로
    """
    shutil.copy(source_db, replica_db)
    
    # 읽기 전용 모드 설정
    conn = sqlite3.connect(replica_db)
    conn.execute("PRAGMA query_only = 1")
    conn.close()
    
    log.info(f"Read-only replica created: {replica_db}")


class EncryptedExecutionHistoryDB:
    """암호화된 Execution History DB (SQLCipher).
    
    SQLCipher 패키지가 필요합니다: pip install pysqlcipher3
    
    참고: 이 클래스는 암호화된 연결만 제공합니다. 테이블 초기화는 
    ExecutionHistoryDB를 사용하여 수행한 후 이 클래스를 사용하여 연결하세요.
    """
    
    def __init__(self, db_path: str, encryption_key: str):
        """암호화 DB 초기화.

        Args:
            db_path: DB 파일 경로
            encryption_key: 암호화 키
        """
        try:
            import pysqlcipher3.dbapi2 as sqlite
        except ImportError:
            raise ImportError("pysqlcipher3 패키지가 필요합니다. pip install pysqlcipher3")
        
        self.db_path = db_path
        self.encryption_key = encryption_key
        self.sqlite = sqlite  # 모듈 저장
    
    def get_connection(self):
        """암호화된 연결 반환.
        
        Returns:
            sqlite3.Connection: 암호화된 연결
        """
        conn = self.sqlite.connect(self.db_path)
        conn.execute("PRAGMA key = ?", (self.encryption_key,))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn


# ── DBHandler: logging.Handler 서브클래스 ─────────────────────────────────────

class DBHandler(logging.Handler):
    """로그를 SQLite DB에 저장하는 Handler.

    config.json의 logging.db_logging 설정을 참조하여 동작합니다.
    """

    def __init__(self, db_path: str = "results/execution_history.db"):
        """DBHandler 초기화.

        Args:
            db_path: 데이터베이스 파일 경로
        """
        super().__init__()
        self.db_path = db_path
        self.db = ExecutionHistoryDB(db_path)
        self._load_config()

    def _load_config(self) -> None:
        """config.json에서 로그 DB 설정 로드."""
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "config.json"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                self.enabled = config.get("logging", {}).get("db_logging", {}).get("enabled", True)
                self.retention_days = config.get("logging", {}).get("db_logging", {}).get("retention_days", 7)
            else:
                self.enabled = True
                self.retention_days = 7
        except Exception as e:
            log.warning(f"Config load failed: {e}", exc_info=True)
            self.enabled = True
            self.retention_days = 7

    def emit(self, record: logging.LogRecord) -> None:
        """로그 레코드 emit.

        Args:
            record: logging.LogRecord
        """
        if not self.enabled:
            return

        try:
            self.db.insert_log(
                level=record.levelname,
                log_name=record.name,
                message=record.getMessage(),
                module=record.module,
                function=record.funcName,
                line_number=record.lineno,
                retention_days=self.retention_days,
            )
        except Exception as e:
            log.debug("로그 저장 실패: %s", e)

    def cleanup_old_logs(self) -> int:
        """오래된 로그 삭제.

        Returns:
            삭제된 레코드 수
        """
        if self.retention_days <= 0:
            return 0
        return self.db.cleanup_old_logs(days=self.retention_days)


# ── 유틸리티 함수 ─────────────────────────────────────────────────────────────

def setup_db_logging(db_path: str = "results/execution_history.db") -> Optional[DBHandler]:
    """DB 로깅 핸들러 설정.

    Args:
        db_path: 데이터베이스 파일 경로

    Returns:
        DBHandler 인스턴스 (설정 비활성화 시 None)
    """
    try:
        handler = DBHandler(db_path)
        if handler.enabled:
            logging.getLogger().addHandler(handler)
            return handler
    except Exception as e:
        log.debug("핸들러 추가 실패: %s", e)
    return None


def cleanup_logs_on_startup(db_path: str = "results/execution_history.db") -> int:
    """앱 시작 시 오래된 로그 정리.

    [참고] 현재는 사용하지 않습니다. 로그 저장 시 자동으로 롤링 방식으로 정리됩니다.
    나중에 수동 정리가 필요한 경우 사용할 수 있습니다.

    Args:
        db_path: 데이터베이스 파일 경로

    Returns:
        삭제된 레코드 수
    """
    try:
        db = ExecutionHistoryDB(db_path)
        # config.json에서 보관 기간 로드
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "config.json"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                retention_days = config.get("logging", {}).get("db_logging", {}).get("retention_days", 7)
            else:
                retention_days = 7
        except Exception:
            retention_days = 7

        if retention_days > 0:
            return db.cleanup_old_logs(days=retention_days)
    except Exception:
        log.debug("로그 정리 실패")
    return 0


# 팩토리 함수
def create_history_db(db_path: str = "results/execution_history.db") -> ExecutionHistoryDB:
    """실행 이력 데이터베이스 생성 팩토리 함수.

    Args:
        db_path: 데이터베이스 파일 경로

    Returns:
        ExecutionHistoryDB 인스턴스
    """
    return ExecutionHistoryDB(db_path)
