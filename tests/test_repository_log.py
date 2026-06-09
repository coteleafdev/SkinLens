"""
Log Repository 테스트 - 로그 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
import csv
import json
from src.cli.repositories.log import LogRepository


class TestLogRepository:
    """LogRepository 테스트"""

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
        
        conn.commit()
        conn.close()
        
        return LogRepository(db_path)

    def test_insert_log(self, repository):
        """로그 삽입"""
        repository.insert_log(
            level="INFO",
            log_name="test_logger",
            message="Test log message",
            module="test_module",
            function="test_function",
            line_number=42
        )
        
        logs = repository.get_logs(limit=10)
        assert len(logs) == 1
        assert logs[0]["level"] == "INFO"
        assert logs[0]["log_name"] == "test_logger"
        assert logs[0]["message"] == "Test log message"
        assert logs[0]["module"] == "test_module"
        assert logs[0]["function"] == "test_function"
        assert logs[0]["line_number"] == 42

    def test_insert_log_minimal(self, repository):
        """최소 파라미터로 로그 삽입"""
        repository.insert_log(
            level="ERROR",
            log_name="test_logger",
            message="Error occurred"
        )
        
        logs = repository.get_logs(limit=10)
        assert len(logs) == 1
        assert logs[0]["level"] == "ERROR"
        assert logs[0]["module"] is None
        assert logs[0]["function"] is None
        assert logs[0]["line_number"] is None

    def test_insert_log_with_retention(self, repository):
        """보관 기간 설정과 함께 로그 삽입"""
        # 오래된 로그 삽입 (수동으로)
        conn = sqlite3.connect(repository.db_path)
        cursor = conn.cursor()
        
        old_timestamp = "2020-01-01T00:00:00"
        cursor.execute('''
            INSERT INTO logs (timestamp, level, log_name, message)
            VALUES (?, ?, ?, ?)
        ''', (old_timestamp, "INFO", "test_logger", "Old log"))
        
        conn.commit()
        conn.close()
        
        # 보관 기간 1일로 새 로그 삽입 (오래된 로그 자동 삭제)
        repository.insert_log(
            level="INFO",
            log_name="test_logger",
            message="New log",
            retention_days=1
        )
        
        logs = repository.get_logs(limit=10)
        # 오래된 로그는 삭제되어야 함
        assert all(log["timestamp"] > "2024-01-01" for log in logs)

    def test_get_logs_with_level_filter(self, repository):
        """레벨 필터로 로그 조회"""
        # 여러 레벨 로그 삽입
        repository.insert_log(level="INFO", log_name="test_logger", message="Info message")
        repository.insert_log(level="ERROR", log_name="test_logger", message="Error message")
        repository.insert_log(level="WARNING", log_name="test_logger", message="Warning message")
        
        # ERROR 레벨만 조회
        logs = repository.get_logs(level="ERROR", limit=10)
        assert len(logs) == 1
        assert logs[0]["level"] == "ERROR"

    def test_get_logs_with_hours_filter(self, repository):
        """시간 필터로 로그 조회"""
        repository.insert_log(level="INFO", log_name="test_logger", message="Recent log")
        
        # 1시간 이내 로그 조회
        logs = repository.get_logs(hours=1, limit=10)
        assert len(logs) == 1

    def test_get_logs_with_both_filters(self, repository):
        """레벨과 시간 필터 함께 사용"""
        repository.insert_log(level="INFO", log_name="test_logger", message="Info message")
        repository.insert_log(level="ERROR", log_name="test_logger", message="Error message")
        
        # ERROR 레벨, 1시간 이내
        logs = repository.get_logs(level="ERROR", hours=1, limit=10)
        assert len(logs) == 1
        assert logs[0]["level"] == "ERROR"

    def test_get_logs_limit(self, repository):
        """limit 파라미터로 결과 제한"""
        # 여러 로그 삽입
        for i in range(10):
            repository.insert_log(
                level="INFO",
                log_name="test_logger",
                message=f"Log message {i}"
            )
        
        # limit=5
        logs = repository.get_logs(limit=5)
        assert len(logs) == 5

    def test_get_logs_ordering(self, repository):
        """최신순 정렬 검증"""
        # 여러 로그 삽입
        for i in range(3):
            repository.insert_log(
                level="INFO",
                log_name="test_logger",
                message=f"Log message {i}"
            )
        
        logs = repository.get_logs(limit=10)
        # 최신순 정렬 확인
        assert len(logs) == 3
        # timestamp 필드 확인
        assert "timestamp" in logs[0]

    def test_get_logs_empty(self, repository):
        """데이터가 없을 때 로그 조회"""
        logs = repository.get_logs(limit=10)
        assert len(logs) == 0

    def test_export_logs_to_csv(self, repository):
        """로그를 CSV로 내보내기"""
        # 로그 삽입
        repository.insert_log(level="INFO", log_name="test_logger", message="Info message")
        repository.insert_log(level="ERROR", log_name="test_logger", message="Error message")
        
        # CSV 내보내기
        fd, output_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        
        try:
            exported_count = repository.export_logs_to_csv(output_path)
            assert exported_count == 2
            
            # 파일 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 2
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_logs_to_csv_with_filter(self, repository):
        """필터와 함께 CSV 내보내기"""
        repository.insert_log(level="INFO", log_name="test_logger", message="Info message")
        repository.insert_log(level="ERROR", log_name="test_logger", message="Error message")
        
        fd, output_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        
        try:
            # ERROR 레벨만 내보내기
            exported_count = repository.export_logs_to_csv(output_path, level="ERROR")
            assert exported_count == 1
            
            # 파일 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 1
                assert rows[0]["level"] == "ERROR"
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_logs_to_csv_empty(self, repository):
        """데이터가 없을 때 CSV 내보내기"""
        fd, output_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        
        try:
            exported_count = repository.export_logs_to_csv(output_path)
            assert exported_count == 0
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_logs_to_json(self, repository):
        """로그를 JSON으로 내보내기"""
        # 로그 삽입
        repository.insert_log(level="INFO", log_name="test_logger", message="Info message")
        repository.insert_log(level="ERROR", log_name="test_logger", message="Error message")
        
        # JSON 내보내기
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            exported_count = repository.export_logs_to_json(output_path)
            assert exported_count == 2
            
            # 파일 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert len(data) == 2
                assert isinstance(data, list)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_logs_to_json_with_filter(self, repository):
        """필터와 함께 JSON 내보내기"""
        repository.insert_log(level="INFO", log_name="test_logger", message="Info message")
        repository.insert_log(level="ERROR", log_name="test_logger", message="Error message")
        
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            # ERROR 레벨만 내보내기
            exported_count = repository.export_logs_to_json(output_path, level="ERROR")
            assert exported_count == 1
            
            # 파일 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert len(data) == 1
                assert data[0]["level"] == "ERROR"
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_logs_to_json_empty(self, repository):
        """데이터가 없을 때 JSON 내보내기"""
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            exported_count = repository.export_logs_to_json(output_path)
            assert exported_count == 0
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_cleanup_old_logs(self, repository):
        """오래된 로그 삭제"""
        # 최근 로그 삽입
        repository.insert_log(level="INFO", log_name="test_logger", message="Recent log")
        
        # 7일 이전 로그 삭제 (최근 로그는 유지됨)
        deleted_count = repository.cleanup_old_logs(days=7)
        assert deleted_count == 0  # 최근 로그는 삭제되지 않음
        
        # 여전히 레코드가 존재해야 함
        logs = repository.get_logs(limit=10)
        assert len(logs) == 1

    def test_cleanup_old_logs_with_old_data(self, repository, db_path):
        """오래된 데이터 삭제"""
        # 오래된 로그 삽입 (수동으로)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        old_timestamp = "2020-01-01T00:00:00"
        cursor.execute('''
            INSERT INTO logs (timestamp, level, log_name, message)
            VALUES (?, ?, ?, ?)
        ''', (old_timestamp, "INFO", "test_logger", "Old log"))
        
        conn.commit()
        conn.close()
        
        # 7일 이전 로그 삭제
        deleted_count = repository.cleanup_old_logs(days=7)
        assert deleted_count == 1
        
        # 오래된 로그가 삭제되었는지 확인
        logs = repository.get_logs(limit=10)
        assert len(logs) == 0

    def test_insert_log_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        # 잘못된 데이터로 에러 유도
        with pytest.raises(Exception):
            repository.insert_log(
                level="INFO",
                log_name="test_logger",
                message=None  # 잘못된 데이터
            )
        
        # 롤백되어 레코드가 없어야 함
        logs = repository.get_logs(limit=10)
        assert len(logs) == 0

    def test_get_logs_different_levels(self, repository):
        """다양한 로그 레벨 조회"""
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        
        for level in levels:
            repository.insert_log(
                level=level,
                log_name="test_logger",
                message=f"{level} message"
            )
        
        # 각 레벨별 조회
        for level in levels:
            logs = repository.get_logs(level=level, limit=10)
            assert len(logs) == 1
            assert logs[0]["level"] == level

    def test_insert_log_zero_retention(self, repository):
        """보관 기간 0으로 설정 (자동 삭제 비활성화)"""
        repository.insert_log(
            level="INFO",
            log_name="test_logger",
            message="Test log",
            retention_days=0
        )
        
        logs = repository.get_logs(limit=10)
        assert len(logs) == 1
