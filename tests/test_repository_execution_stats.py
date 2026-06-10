"""
Execution Stats Repository 테스트 - 실행 이력 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from src.cli.repositories.execution_stats import ExecutionStatsRepository


class TestExecutionStatsRepository:
    """ExecutionStatsRepository 테스트"""

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
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                input_path TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                overall_score REAL,
                perceived_age INTEGER,
                execution_time_sec REAL,
                pipeline_mode TEXT,
                success BOOLEAN DEFAULT 1,
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
        ''')
        
        conn.commit()
        conn.close()
        
        return ExecutionStatsRepository(db_path)

    def test_log_execution_success(self, repository):
        """성공한 실행 이력 기록"""
        result = {
            "analysis_result": {
                "overall_score": 85.5,
                "perceived_age": 30
            },
            "input_image_base64": "base64data",
            "restored_image_base64": "restoreddata",
            "pipeline_mode": "analyze_only"
        }
        
        resource_stats = {
            "memory_peak_mb": 512.0,
            "memory_avg_mb": 480.0,
            "cpu_percent_avg": 45.0,
            "cpu_time_user_sec": 2.5,
            "cpu_time_system_sec": 0.5,
            "thread_count": 4
        }
        
        record_id = repository.log_execution(
            input_path="/path/to/image.jpg",
            output_dir="/path/to/output",
            result=result,
            execution_time=3.0,
            success=True,
            resource_stats=resource_stats
        )
        
        assert record_id > 0
        
        # 기록 확인
        executions = repository.get_recent_executions(limit=1)
        assert len(executions) == 1
        assert executions[0]["input_path"] == "/path/to/image.jpg"
        assert executions[0]["overall_score"] == 85.5
        assert executions[0]["perceived_age"] == 30
        assert executions[0]["execution_time_sec"] == 3.0
        assert executions[0]["success"] in [True, 1]
        assert executions[0]["memory_peak_mb"] == 512.0
        assert executions[0]["cpu_percent_avg"] == 45.0

    def test_log_execution_failure(self, repository):
        """실패한 실행 이력 기록"""
        result = {
            "error_message": "Analysis failed",
            "pipeline_mode": "analyze_only"
        }
        
        record_id = repository.log_execution(
            input_path="/path/to/image.jpg",
            output_dir="/path/to/output",
            result=result,
            execution_time=1.5,
            success=False
        )
        
        assert record_id > 0
        
        # 기록 확인
        executions = repository.get_recent_executions(limit=1)
        assert len(executions) == 1
        assert executions[0]["success"] in [False, 0]
        assert executions[0]["error_message"] == "Analysis failed"

    def test_log_execution_minimal(self, repository):
        """최소 파라미터로 실행 이력 기록"""
        result = {
            "analysis_result": {},
            "pipeline_mode": "analyze_only"
        }
        
        record_id = repository.log_execution(
            input_path="/path/to/image.jpg",
            output_dir="/path/to/output",
            result=result,
            execution_time=2.0
        )
        
        assert record_id > 0

    def test_get_recent_executions_all(self, repository):
        """모든 최근 실행 이력 조회"""
        # 여러 실행 기록
        for i in range(5):
            result = {
                "analysis_result": {"overall_score": 80.0 + i},
                "pipeline_mode": "analyze_only"
            }
            repository.log_execution(
                input_path=f"/path/to/image{i}.jpg",
                output_dir="/path/to/output",
                result=result,
                execution_time=2.0 + i
            )
        
        executions = repository.get_recent_executions(limit=10)
        assert len(executions) == 5

    def test_get_recent_executions_success_only(self, repository):
        """성공한 실행만 조회"""
        # 성공한 실행
        result_success = {
            "analysis_result": {"overall_score": 85.0},
            "pipeline_mode": "analyze_only"
        }
        repository.log_execution(
            input_path="/path/to/image1.jpg",
            output_dir="/path/to/output",
            result=result_success,
            execution_time=2.0,
            success=True
        )
        
        # 실패한 실행
        result_failure = {
            "error_message": "Failed",
            "pipeline_mode": "analyze_only"
        }
        repository.log_execution(
            input_path="/path/to/image2.jpg",
            output_dir="/path/to/output",
            result=result_failure,
            execution_time=1.0,
            success=False
        )
        
        # 성공한 실행만 조회
        executions = repository.get_recent_executions(limit=10, success_only=True)
        assert len(executions) == 1
        assert executions[0]["success"] in [True, 1]

    def test_get_recent_executions_failure_only(self, repository):
        """실패한 실행만 조회"""
        # 성공한 실행
        result_success = {
            "analysis_result": {"overall_score": 85.0},
            "pipeline_mode": "analyze_only"
        }
        repository.log_execution(
            input_path="/path/to/image1.jpg",
            output_dir="/path/to/output",
            result=result_success,
            execution_time=2.0,
            success=True
        )
        
        # 실패한 실행
        result_failure = {
            "error_message": "Failed",
            "pipeline_mode": "analyze_only"
        }
        repository.log_execution(
            input_path="/path/to/image2.jpg",
            output_dir="/path/to/output",
            result=result_failure,
            execution_time=1.0,
            success=False
        )
        
        # 실패한 실행만 조회
        executions = repository.get_recent_executions(limit=10, success_only=False)
        assert len(executions) == 1
        assert executions[0]["success"] in [False, 0]

    def test_get_recent_executions_limit(self, repository):
        """limit 파라미터로 결과 제한"""
        # 여러 실행 기록
        for i in range(10):
            result = {
                "analysis_result": {},
                "pipeline_mode": "analyze_only"
            }
            repository.log_execution(
                input_path=f"/path/to/image{i}.jpg",
                output_dir="/path/to/output",
                result=result,
                execution_time=2.0
            )
        
        # limit=5
        executions = repository.get_recent_executions(limit=5)
        assert len(executions) == 5

    def test_get_statistics(self, repository):
        """기간별 통계 조회"""
        # 여러 실행 기록
        for i in range(5):
            result = {
                "analysis_result": {"overall_score": 80.0 + i},
                "pipeline_mode": "analyze_only"
            }
            resource_stats = {
                "memory_peak_mb": 500.0 + i,
                "cpu_percent_avg": 40.0 + i
            }
            repository.log_execution(
                input_path=f"/path/to/image{i}.jpg",
                output_dir="/path/to/output",
                result=result,
                execution_time=2.0 + i,
                success=True,
                resource_stats=resource_stats
            )
        
        # 통계 조회
        stats = repository.get_statistics(days=7)
        assert stats["period_days"] == 7
        assert stats["total_executions"] == 5
        assert stats["successful_executions"] == 5
        assert stats["failed_executions"] == 0
        assert stats["success_rate"] == 100.0
        assert stats["avg_score"] is not None
        assert stats["avg_execution_time_sec"] is not None
        assert stats["avg_memory_peak_mb"] is not None
        assert stats["avg_cpu_percent"] is not None
        assert "daily_counts" in stats

    def test_get_statistics_with_failures(self, repository):
        """실패 포함 통계 조회"""
        # 성공한 실행
        result_success = {
            "analysis_result": {"overall_score": 85.0},
            "pipeline_mode": "analyze_only"
        }
        repository.log_execution(
            input_path="/path/to/image1.jpg",
            output_dir="/path/to/output",
            result=result_success,
            execution_time=2.0,
            success=True
        )
        
        # 실패한 실행
        result_failure = {
            "error_message": "Failed",
            "pipeline_mode": "analyze_only"
        }
        repository.log_execution(
            input_path="/path/to/image2.jpg",
            output_dir="/path/to/output",
            result=result_failure,
            execution_time=1.0,
            success=False
        )
        
        # 통계 조회
        stats = repository.get_statistics(days=7)
        assert stats["total_executions"] == 2
        assert stats["successful_executions"] == 1
        assert stats["failed_executions"] == 1
        assert stats["success_rate"] == 50.0

    def test_get_statistics_empty(self, repository):
        """데이터가 없을 때 통계 조회"""
        stats = repository.get_statistics(days=7)
        assert stats["total_executions"] == 0
        assert stats["successful_executions"] == 0
        assert stats["failed_executions"] == 0
        assert stats["success_rate"] == 0
        assert stats["avg_score"] is None
        assert stats["avg_execution_time_sec"] is None

    def test_cleanup_old_records(self, repository):
        """오래된 레코드 삭제"""
        # 최근 실행 기록
        result = {
            "analysis_result": {},
            "pipeline_mode": "analyze_only"
        }
        repository.log_execution(
            input_path="/path/to/image.jpg",
            output_dir="/path/to/output",
            result=result,
            execution_time=2.0
        )
        
        # 90일 이전 레코드 삭제 (최근 기록은 유지됨)
        deleted_count = repository.cleanup_old_records(days=90)
        assert deleted_count == 0  # 최근 기록은 삭제되지 않음
        
        # 여전히 레코드가 존재해야 함
        executions = repository.get_recent_executions(limit=10)
        assert len(executions) == 1

    def test_log_execution_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        import sqlite3
        from unittest.mock import patch
        
        original_get_connection = repository._get_connection
        
        def mock_get_connection_with_error():
            """실행 이력 기록 시 에러 발생 시뮬레이션"""
            if not hasattr(mock_get_connection_with_error, 'call_count'):
                mock_get_connection_with_error.call_count = 0
            mock_get_connection_with_error.call_count += 1
            
            if mock_get_connection_with_error.call_count == 1:
                return original_get_connection()
            else:
                raise sqlite3.OperationalError("Simulated execution stats error")
        
        # 기록 전후의 레코드 수 확인
        initial_executions = repository.get_recent_executions(limit=100)
        initial_count = len(initial_executions)
        
        # 모킹 적용
        with patch.object(repository, '_get_connection', side_effect=mock_get_connection_with_error):
            try:
                repository.log_execution(
                    input_path="/path/to/test.jpg",
                    output_dir="/path/to/output",
                    result={"analysis_result": {}, "pipeline_mode": "analyze_only"},
                    execution_time=2.0
                )
                assert False, "Expected an error to be raised"
            except sqlite3.OperationalError as e:
                assert "Simulated execution stats error" in str(e)
        
        # 롤백 확인
        final_executions = repository.get_recent_executions(limit=100)
        final_count = len(final_executions)
        
        assert final_count == initial_count, "Rollback failed: execution record was inserted despite error"

    def test_get_statistics_ordering(self, repository):
        """일별 실행 수 정렬 검증"""
        # 여러 실행 기록
        for i in range(3):
            result = {
                "analysis_result": {},
                "pipeline_mode": "analyze_only"
            }
            repository.log_execution(
                input_path=f"/path/to/image{i}.jpg",
                output_dir="/path/to/output",
                result=result,
                execution_time=2.0
            )
        
        stats = repository.get_statistics(days=7)
        daily_counts = stats["daily_counts"]
        
        # 최신순 정렬 확인
        if len(daily_counts) > 1:
            # 날짜가 내림차순인지 확인
            dates = [row[0] for row in daily_counts]
            assert dates == sorted(dates, reverse=True)
