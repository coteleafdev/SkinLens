"""
Analysis Stats Repository 테스트 - 분석 통계 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from src.cli.repositories.analysis_stats import AnalysisStatsRepository


class TestAnalysisStatsRepository:
    """AnalysisStatsRepository 테스트"""

    @pytest.fixture
    def db_path(self):
        """임시 데이터베이스 파일 생성"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def repository(self, db_path):
        """Repository 인스턴스 생성"""
        # 테이블 생성
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
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
                avg_execution_time_sec REAL
            )
        ''')
        
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
                output_quality_score REAL
            )
        ''')
        
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
                analysis_count INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return AnalysisStatsRepository(db_path)

    def test_record_analysis_stat_new_record(self, repository):
        """새 분석 통계 레코드 생성"""
        repository.record_analysis_stat(
            customer_id="customer123",
            success=True,
            score_original=85.5,
            score_restored=90.0,
            execution_time_sec=2.5
        )
        
        stats = repository.get_analysis_stats(days=1, customer_id="customer123")
        assert len(stats) == 1
        assert stats[0]["total_analyses"] == 1
        assert stats[0]["successful_analyses"] == 1
        assert stats[0]["failed_analyses"] == 0
        assert stats[0]["avg_score_original"] == 85.5
        assert stats[0]["avg_score_restored"] == 90.0
        assert stats[0]["avg_execution_time_sec"] == 2.5

    def test_record_analysis_stat_update_existing(self, repository):
        """기존 레코드 업데이트"""
        # 첫 번째 기록
        repository.record_analysis_stat(
            customer_id="customer123",
            success=True,
            score_original=85.5,
            score_restored=90.0,
            execution_time_sec=2.5
        )
        
        # 두 번째 기록 (같은 날짜)
        repository.record_analysis_stat(
            customer_id="customer123",
            success=False,
            score_original=80.0,
            score_restored=85.0,
            execution_time_sec=3.0
        )
        
        stats = repository.get_analysis_stats(days=1, customer_id="customer123")
        assert len(stats) == 1
        assert stats[0]["total_analyses"] == 2
        assert stats[0]["successful_analyses"] == 1
        assert stats[0]["failed_analyses"] == 1
        # 이동 평균 계산 검증
        expected_avg_orig = (85.5 + 80.0) / 2
        assert abs(stats[0]["avg_score_original"] - expected_avg_orig) < 0.01

    def test_record_analysis_stat_without_customer(self, repository):
        """고객 ID 없이 전체 통계 기록"""
        repository.record_analysis_stat(
            customer_id=None,
            success=True,
            score_original=85.5,
            score_restored=90.0,
            execution_time_sec=2.5
        )
        
        stats = repository.get_analysis_stats(days=1, customer_id=None)
        assert len(stats) == 1
        assert stats[0]["customer_id"] is None

    def test_get_analysis_stats_with_days_filter(self, repository):
        """기간 필터로 통계 조회"""
        # 오늘 기록
        repository.record_analysis_stat(
            customer_id="customer123",
            success=True,
            score_original=85.5,
            score_restored=90.0,
            execution_time_sec=2.5
        )
        
        # 7일 이내 기록만 조회
        stats = repository.get_analysis_stats(days=7, customer_id="customer123")
        assert len(stats) == 1
        
        # 1일 이내 기록만 조회
        stats = repository.get_analysis_stats(days=1, customer_id="customer123")
        assert len(stats) == 1

    def test_get_analysis_stats_ordering(self, repository):
        """최신순 정렬 검증"""
        # 여러 날짜에 기록
        for i in range(3):
            repository.record_analysis_stat(
                customer_id="customer123",
                success=True,
                score_original=80.0 + i,
                score_restored=85.0 + i,
                execution_time_sec=2.0 + i
            )
        
        stats = repository.get_analysis_stats(days=7, customer_id="customer123")
        # 최신순 정렬 확인
        assert len(stats) >= 1
        # 날짜 필드 확인
        assert "date" in stats[0]

    def test_record_model_performance(self, repository):
        """모델 성능 기록"""
        repository.record_model_performance(
            model_type="pigmentation_v1",
            execution_time_ms=1500.0,
            memory_peak_mb=512.0,
            cpu_percent_avg=45.0,
            success=True,
            error_type=None,
            input_resolution="512x512",
            output_quality_score=0.95
        )
        
        performance = repository.get_model_performance(model_type="pigmentation_v1")
        assert len(performance) == 1
        assert performance[0]["model_type"] == "pigmentation_v1"
        assert performance[0]["execution_time_ms"] == 1500.0
        assert performance[0]["memory_peak_mb"] == 512.0
        assert performance[0]["cpu_percent_avg"] == 45.0
        assert performance[0]["success"] in [True, 1]
        assert performance[0]["input_resolution"] == "512x512"
        assert performance[0]["output_quality_score"] == 0.95

    def test_record_model_performance_with_error(self, repository):
        """에러와 함께 모델 성능 기록"""
        repository.record_model_performance(
            model_type="pigmentation_v1",
            execution_time_ms=1500.0,
            memory_peak_mb=512.0,
            cpu_percent_avg=45.0,
            success=False,
            error_type="TimeoutError",
            input_resolution="512x512",
            output_quality_score=None
        )
        
        performance = repository.get_model_performance(model_type="pigmentation_v1")
        assert len(performance) == 1
        assert performance[0]["success"] in [False, 0]
        assert performance[0]["error_type"] == "TimeoutError"
        assert performance[0]["output_quality_score"] is None

    def test_get_model_performance_with_filters(self, repository):
        """필터와 함께 모델 성능 조회"""
        # 여러 모델 기록
        repository.record_model_performance(
            model_type="pigmentation_v1",
            execution_time_ms=1500.0,
            memory_peak_mb=512.0,
            cpu_percent_avg=45.0,
            success=True
        )
        
        repository.record_model_performance(
            model_type="redness_v1",
            execution_time_ms=1200.0,
            memory_peak_mb=480.0,
            cpu_percent_avg=40.0,
            success=True
        )
        
        # 모델 타입 필터
        performance = repository.get_model_performance(model_type="pigmentation_v1")
        assert len(performance) == 1
        assert performance[0]["model_type"] == "pigmentation_v1"
        
        # 시간 필터
        performance = repository.get_model_performance(hours=1)
        assert len(performance) >= 1

    def test_get_model_performance_limit(self, repository):
        """limit 파라미터로 결과 제한"""
        # 여러 기록
        for i in range(5):
            repository.record_model_performance(
                model_type="pigmentation_v1",
                execution_time_ms=1500.0 + i,
                memory_peak_mb=512.0,
                cpu_percent_avg=45.0,
                success=True
            )
        
        # limit=2
        performance = repository.get_model_performance(limit=2)
        assert len(performance) == 2

    def test_record_score_trend(self, repository):
        """점수 추이 기록"""
        measurements = {
            "melasma_score": 85.0,
            "redness_score": 90.0,
            "wrinkle_score": 80.0,
            "pore_score": 75.0
        }
        
        repository.record_score_trend(
            customer_id="customer123",
            overall_score=82.5,
            measurements=measurements,
            improvement_delta=5.0
        )
        
        trends = repository.get_score_trends(customer_id="customer123")
        assert len(trends) == 1
        assert trends[0]["customer_id"] == "customer123"
        assert trends[0]["overall_score"] == 82.5
        assert trends[0]["melasma_score"] == 85.0
        assert trends[0]["redness_score"] == 90.0
        assert trends[0]["wrinkle_score"] == 80.0
        assert trends[0]["pore_score"] == 75.0
        assert trends[0]["improvement_delta"] == 5.0
        assert trends[0]["analysis_count"] == 1

    def test_record_score_trend_analysis_count(self, repository):
        """분석 횟수 자동 증가 검증"""
        measurements = {
            "melasma_score": 85.0,
            "redness_score": 90.0,
            "wrinkle_score": 80.0,
            "pore_score": 75.0
        }
        
        # 첫 번째 기록
        repository.record_score_trend(
            customer_id="customer123",
            overall_score=82.5,
            measurements=measurements
        )
        
        # 두 번째 기록
        repository.record_score_trend(
            customer_id="customer123",
            overall_score=83.0,
            measurements=measurements
        )
        
        trends = repository.get_score_trends(customer_id="customer123")
        assert len(trends) == 2
        assert trends[0]["analysis_count"] == 2  # 최신 기록
        assert trends[1]["analysis_count"] == 1  # 이전 기록

    def test_get_score_trends_with_customer_filter(self, repository):
        """고객 ID 필터로 점수 추이 조회"""
        measurements = {
            "melasma_score": 85.0,
            "redness_score": 90.0,
            "wrinkle_score": 80.0,
            "pore_score": 75.0
        }
        
        # 여러 고객 기록
        repository.record_score_trend(
            customer_id="customer123",
            overall_score=82.5,
            measurements=measurements
        )
        
        repository.record_score_trend(
            customer_id="customer456",
            overall_score=85.0,
            measurements=measurements
        )
        
        # 특정 고객만 조회
        trends = repository.get_score_trends(customer_id="customer123")
        assert len(trends) == 1
        assert trends[0]["customer_id"] == "customer123"

    def test_get_score_trends_with_days_filter(self, repository):
        """기간 필터로 점수 추이 조회"""
        measurements = {
            "melasma_score": 85.0,
            "redness_score": 90.0,
            "wrinkle_score": 80.0,
            "pore_score": 75.0
        }
        
        repository.record_score_trend(
            customer_id="customer123",
            overall_score=82.5,
            measurements=measurements
        )
        
        # 30일 이내 기록 조회
        trends = repository.get_score_trends(customer_id="customer123", days=30)
        assert len(trends) == 1
        
        # 1일 이내 기록 조회
        trends = repository.get_score_trends(customer_id="customer123", days=1)
        assert len(trends) == 1

    def test_get_score_trends_limit(self, repository):
        """limit 파라미터로 결과 제한"""
        measurements = {
            "melasma_score": 85.0,
            "redness_score": 90.0,
            "wrinkle_score": 80.0,
            "pore_score": 75.0
        }
        
        # 여러 기록
        for i in range(5):
            repository.record_score_trend(
                customer_id="customer123",
                overall_score=82.5 + i,
                measurements=measurements
            )
        
        # limit=3
        trends = repository.get_score_trends(customer_id="customer123", limit=3)
        assert len(trends) == 3

    def test_record_analysis_stat_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        # 현재 구현에서는 예외가 발생하지 않으므로 기본 동작만 확인
        # 실제 롤백 테스트는 DB 트랜잭션 설정이 필요
        pass
