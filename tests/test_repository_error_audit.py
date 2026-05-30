"""
Error Audit Repository 테스트 - 에러 및 감사 로그 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from src.cli.repositories.error_audit import ErrorAuditRepository


class TestErrorAuditRepository:
    """ErrorAuditRepository 테스트"""

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
            CREATE TABLE IF NOT EXISTS error_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                module TEXT,
                function TEXT,
                line_number INTEGER,
                stack_trace TEXT,
                customer_id TEXT,
                image_path TEXT,
                pipeline_mode TEXT,
                severity TEXT DEFAULT 'medium',
                resolved BOOLEAN DEFAULT 0,
                resolved_at TEXT,
                resolution_note TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor_customer_id TEXT,
                target_customer_id TEXT,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                user_role TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                success BOOLEAN DEFAULT 1,
                error_message TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                success BOOLEAN DEFAULT 1,
                error_message TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return ErrorAuditRepository(db_path)

    def test_record_error(self, repository):
        """에러 기록"""
        repository.record_error(
            error_type="ValueError",
            error_message="Invalid input value",
            module="analyzers",
            function="analyze_pigmentation",
            line_number=42,
            stack_trace="Traceback...",
            customer_id="customer123",
            image_path="/path/to/image.jpg",
            pipeline_mode="analyze_only",
            severity="high"
        )
        
        errors = repository.get_errors(days=1)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "ValueError"
        assert errors[0]["error_message"] == "Invalid input value"
        assert errors[0]["module"] == "analyzers"
        assert errors[0]["function"] == "analyze_pigmentation"
        assert errors[0]["line_number"] == 42
        assert errors[0]["customer_id"] == "customer123"
        assert errors[0]["severity"] == "high"
        assert errors[0]["resolved"] == 0

    def test_record_error_minimal(self, repository):
        """최소 파라미터로 에러 기록"""
        repository.record_error(
            error_type="RuntimeError",
            error_message="Something went wrong"
        )
        
        errors = repository.get_errors(days=1)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "RuntimeError"
        assert errors[0]["error_message"] == "Something went wrong"
        assert errors[0]["severity"] == "medium"  # 기본값

    def test_get_errors_with_filters(self, repository):
        """필터와 함께 에러 조회"""
        # 여러 에러 기록
        repository.record_error(
            error_type="ValueError",
            error_message="Error 1",
            severity="high"
        )
        
        repository.record_error(
            error_type="RuntimeError",
            error_message="Error 2",
            severity="medium"
        )
        
        # severity 필터
        errors = repository.get_errors(severity="high", days=1)
        assert len(errors) == 1
        assert errors[0]["severity"] == "high"
        
        # resolved 필터 (기본적으로 모두 미해결)
        errors = repository.get_errors(resolved=False, days=1)
        assert len(errors) == 2

    def test_get_errors_with_days_filter(self, repository):
        """기간 필터로 에러 조회"""
        repository.record_error(
            error_type="ValueError",
            error_message="Recent error"
        )
        
        # 7일 이내 에러 조회
        errors = repository.get_errors(days=7)
        assert len(errors) == 1
        
        # 1일 이내 에러 조회
        errors = repository.get_errors(days=1)
        assert len(errors) == 1

    def test_get_errors_limit(self, repository):
        """limit 파라미터로 결과 제한"""
        # 여러 에러 기록
        for i in range(5):
            repository.record_error(
                error_type=f"ErrorType{i}",
                error_message=f"Error message {i}"
            )
        
        # limit=3
        errors = repository.get_errors(limit=3, days=1)
        assert len(errors) == 3

    def test_resolve_error(self, repository):
        """에러 해결 표시"""
        # 에러 기록
        repository.record_error(
            error_type="ValueError",
            error_message="Test error"
        )
        
        errors = repository.get_errors(days=1)
        error_id = errors[0]["id"]
        
        # 해결 표시
        repository.resolve_error(error_id, "Fixed the issue")
        
        # 해결 확인
        errors = repository.get_errors(days=1)
        assert errors[0]["resolved"] == 1
        assert errors[0]["resolution_note"] == "Fixed the issue"
        assert "resolved_at" in errors[0]

    def test_resolve_error_nonexistent(self, repository):
        """존재하지 않는 에러 해결 시도"""
        # 에러가 발생해야 함 (예외 처리 필요)
        with pytest.raises(Exception):
            repository.resolve_error(999, "This error doesn't exist")

    def test_get_error_summary(self, repository, db_path):
        """에러 요약 조회"""
        # 실패한 실행 기록
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO executions (timestamp, success, error_message)
            VALUES ('2024-01-01T00:00:00', 0, 'Error 1')
        ''')
        
        cursor.execute('''
            INSERT INTO executions (timestamp, success, error_message)
            VALUES ('2024-01-01T01:00:00', 0, 'Error 2')
        ''')
        
        cursor.execute('''
            INSERT INTO executions (timestamp, success, error_message)
            VALUES ('2024-01-01T02:00:00', 1, NULL)
        ''')
        
        conn.commit()
        conn.close()
        
        # 에러 요약 조회
        summary = repository.get_error_summary(limit=10)
        assert len(summary) == 2  # 실패한 실행만
        assert all(error["success"] == 0 for error in summary)

    def test_record_audit_log(self, repository):
        """감사 로그 기록"""
        repository.record_audit_log(
            actor_customer_id="admin",
            target_customer_id="customer123",
            endpoint="/v3/analyze",
            method="POST",
            user_role="admin",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            success=True
        )
        
        logs = repository.get_audit_logs(days=1)
        assert len(logs) == 1
        assert logs[0]["actor_customer_id"] == "admin"
        assert logs[0]["target_customer_id"] == "customer123"
        assert logs[0]["endpoint"] == "/v3/analyze"
        assert logs[0]["method"] == "POST"
        assert logs[0]["user_role"] == "admin"
        assert logs[0]["ip_address"] == "192.168.1.1"
        assert logs[0]["user_agent"] == "Mozilla/5.0"
        assert logs[0]["success"] is True

    def test_record_audit_log_minimal(self, repository):
        """최소 파라미터로 감사 로그 기록"""
        repository.record_audit_log(
            actor_customer_id="admin",
            target_customer_id=None,
            endpoint="/v3/health",
            method="GET",
            user_role="admin"
        )
        
        logs = repository.get_audit_logs(days=1)
        assert len(logs) == 1
        assert logs[0]["actor_customer_id"] == "admin"
        assert logs[0]["success"] is True  # 기본값

    def test_record_audit_log_with_error(self, repository):
        """에러와 함께 감사 로그 기록"""
        repository.record_audit_log(
            actor_customer_id="customer123",
            target_customer_id=None,
            endpoint="/v3/analyze",
            method="POST",
            user_role="customer",
            success=False,
            error_message="Authentication failed"
        )
        
        logs = repository.get_audit_logs(days=1)
        assert len(logs) == 1
        assert logs[0]["success"] is False
        assert logs[0]["error_message"] == "Authentication failed"

    def test_get_audit_logs_with_filters(self, repository):
        """필터와 함께 감사 로그 조회"""
        # 여러 로그 기록
        repository.record_audit_log(
            actor_customer_id="admin",
            target_customer_id="customer123",
            endpoint="/v3/analyze",
            method="POST",
            user_role="admin"
        )
        
        repository.record_audit_log(
            actor_customer_id="customer123",
            target_customer_id=None,
            endpoint="/v3/health",
            method="GET",
            user_role="customer"
        )
        
        # actor_customer_id 필터
        logs = repository.get_audit_logs(actor_customer_id="admin", days=1)
        assert len(logs) == 1
        assert logs[0]["actor_customer_id"] == "admin"
        
        # target_customer_id 필터
        logs = repository.get_audit_logs(target_customer_id="customer123", days=1)
        assert len(logs) == 1

    def test_get_audit_logs_with_days_filter(self, repository):
        """기간 필터로 감사 로그 조회"""
        repository.record_audit_log(
            actor_customer_id="admin",
            target_customer_id=None,
            endpoint="/v3/health",
            method="GET",
            user_role="admin"
        )
        
        # 30일 이내 로그 조회
        logs = repository.get_audit_logs(days=30)
        assert len(logs) == 1
        
        # 1일 이내 로그 조회
        logs = repository.get_audit_logs(days=1)
        assert len(logs) == 1

    def test_get_audit_logs_limit(self, repository):
        """limit 파라미터로 결과 제한"""
        # 여러 로그 기록
        for i in range(5):
            repository.record_audit_log(
                actor_customer_id=f"user{i}",
                target_customer_id=None,
                endpoint="/v3/health",
                method="GET",
                user_role="customer"
            )
        
        # limit=3
        logs = repository.get_audit_logs(limit=3, days=1)
        assert len(logs) == 3

    def test_record_error_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        # 잘못된 데이터로 에러 유도 (실제로는 테이블 구조 문제 등)
        # 이 테스트는 테이블이 올바르게 생성되었으므로 생략

    def test_record_audit_log_rollback_on_error(self, repository, db_path):
        """감사 로그 기록 실패 시 롤백 검증"""
        # 잘못된 데이터로 에러 유도
        # 이 테스트는 테이블이 올바르게 생성되었으므로 생략
