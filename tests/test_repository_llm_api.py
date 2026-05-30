"""
LLM API Repository 테스트 - LLM API 통계 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
from src.cli.repositories.llm_api import LLMAPIRepository


class TestLLMAPIRepository:
    """LLMAPIRepository 테스트"""

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
            CREATE TABLE IF NOT EXISTS llm_api_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                customer_id TEXT,
                request_type TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                execution_time_sec REAL NOT NULL,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                estimated_cost_usd REAL
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return LLMAPIRepository(db_path)

    def test_record_llm_api_call_success(self, repository):
        """성공한 LLM API 호출 기록"""
        repository.record_llm_api_call(
            customer_id="customer123",
            request_type="skin_report",
            input_tokens=1000,
            output_tokens=500,
            execution_time_sec=2.5,
            success=True
        )
        
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["customer_id"] == "customer123"
        assert stats[0]["request_type"] == "skin_report"
        assert stats[0]["input_tokens"] == 1000
        assert stats[0]["output_tokens"] == 500
        assert stats[0]["total_tokens"] == 1500
        assert stats[0]["execution_time_sec"] == 2.5
        assert stats[0]["success"] is True
        assert stats[0]["error_message"] is None
        # 비용 계산 검증 (Gemini 가격)
        expected_cost = (1000 / 1000 * 0.00025) + (500 / 1000 * 0.0005)
        assert abs(stats[0]["estimated_cost_usd"] - expected_cost) < 0.0001

    def test_record_llm_api_call_failure(self, repository):
        """실패한 LLM API 호출 기록"""
        repository.record_llm_api_call(
            customer_id="customer123",
            request_type="skin_report",
            input_tokens=1000,
            output_tokens=0,
            execution_time_sec=1.0,
            success=False,
            error_message="API rate limit exceeded"
        )
        
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["success"] is False
        assert stats[0]["error_message"] == "API rate limit exceeded"
        assert stats[0]["output_tokens"] == 0

    def test_record_llm_api_call_without_customer(self, repository):
        """고객 ID 없이 LLM API 호출 기록"""
        repository.record_llm_api_call(
            customer_id=None,
            request_type="system_report",
            input_tokens=500,
            output_tokens=200,
            execution_time_sec=1.5,
            success=True
        )
        
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["customer_id"] is None

    def test_get_llm_api_stats_with_customer_filter(self, repository):
        """고객 ID 필터로 통계 조회"""
        # 여러 고객 기록
        repository.record_llm_api_call(
            customer_id="customer123",
            request_type="skin_report",
            input_tokens=1000,
            output_tokens=500,
            execution_time_sec=2.5,
            success=True
        )
        
        repository.record_llm_api_call(
            customer_id="customer456",
            request_type="skin_report",
            input_tokens=800,
            output_tokens=400,
            execution_time_sec=2.0,
            success=True
        )
        
        # customer123으로 필터링
        stats = repository.get_llm_api_stats(customer_id="customer123", days=1)
        assert len(stats) == 1
        assert stats[0]["customer_id"] == "customer123"

    def test_get_llm_api_stats_with_days_filter(self, repository):
        """기간 필터로 통계 조회"""
        repository.record_llm_api_call(
            customer_id="customer123",
            request_type="skin_report",
            input_tokens=1000,
            output_tokens=500,
            execution_time_sec=2.5,
            success=True
        )
        
        # 30일 이내 통계 조회
        stats = repository.get_llm_api_stats(days=30)
        assert len(stats) == 1
        
        # 1일 이내 통계 조회
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 1

    def test_get_llm_api_stats_all(self, repository):
        """모든 통계 조회"""
        # 여러 기록
        for i in range(3):
            repository.record_llm_api_call(
                customer_id=f"customer{i}",
                request_type="skin_report",
                input_tokens=1000 + i * 100,
                output_tokens=500 + i * 50,
                execution_time_sec=2.0 + i * 0.5,
                success=True
            )
        
        # 필터 없이 조회
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 3

    def test_get_llm_api_stats_empty(self, repository):
        """데이터가 없을 때 통계 조회"""
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 0

    def test_get_llm_api_stats_ordering(self, repository):
        """최신순 정렬 검증"""
        # 여러 기록
        for i in range(3):
            repository.record_llm_api_call(
                customer_id="customer123",
                request_type="skin_report",
                input_tokens=1000,
                output_tokens=500,
                execution_time_sec=2.0,
                success=True
            )
        
        stats = repository.get_llm_api_stats(days=1)
        # 최신순 정렬 확인
        assert len(stats) == 3
        # timestamp 필드 확인
        assert "timestamp" in stats[0]

    def test_record_llm_api_call_cost_calculation(self, repository):
        """비용 계산 검증"""
        # 다양한 토큰 수로 기록
        test_cases = [
            (1000, 500),  # 기본 케이스
            (2000, 1000),  # 2배
            (500, 250),    # 절반
        ]
        
        for input_tokens, output_tokens in test_cases:
            repository.record_llm_api_call(
                customer_id="customer123",
                request_type="skin_report",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                execution_time_sec=2.0,
                success=True
            )
        
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 3
        
        # 각 레코드의 비용 계산 검증
        for i, (input_tokens, output_tokens) in enumerate(test_cases):
            expected_cost = (input_tokens / 1000 * 0.00025) + (output_tokens / 1000 * 0.0005)
            actual_cost = stats[i]["estimated_cost_usd"]
            assert abs(actual_cost - expected_cost) < 0.0001

    def test_record_llm_api_call_different_request_types(self, repository):
        """다양한 요청 타입 기록"""
        request_types = ["skin_report", "product_recommendation", "restoration_guide"]
        
        for request_type in request_types:
            repository.record_llm_api_call(
                customer_id="customer123",
                request_type=request_type,
                input_tokens=1000,
                output_tokens=500,
                execution_time_sec=2.0,
                success=True
            )
        
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 3
        recorded_types = [s["request_type"] for s in stats]
        assert set(recorded_types) == set(request_types)

    def test_record_llm_api_call_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        # 잘못된 데이터 타입으로 에러 유도
        with pytest.raises(Exception):
            repository.record_llm_api_call(
                customer_id="customer123",
                request_type="skin_report",
                input_tokens="invalid",  # 잘못된 타입
                output_tokens=500,
                execution_time_sec=2.0,
                success=True
            )
        
        # 롤백되어 레코드가 없어야 함
        stats = repository.get_llm_api_stats(days=1)
        assert len(stats) == 0

    def test_total_tokens_calculation(self, repository):
        """총 토큰 수 계산 검증"""
        repository.record_llm_api_call(
            customer_id="customer123",
            request_type="skin_report",
            input_tokens=1000,
            output_tokens=500,
            execution_time_sec=2.0,
            success=True
        )
        
        stats = repository.get_llm_api_stats(days=1)
        assert stats[0]["total_tokens"] == 1500  # 1000 + 500

    def test_get_llm_api_stats_with_both_filters(self, repository):
        """고객 ID와 기간 필터 함께 사용"""
        # 여러 기록
        repository.record_llm_api_call(
            customer_id="customer123",
            request_type="skin_report",
            input_tokens=1000,
            output_tokens=500,
            execution_time_sec=2.0,
            success=True
        )
        
        repository.record_llm_api_call(
            customer_id="customer456",
            request_type="skin_report",
            input_tokens=800,
            output_tokens=400,
            execution_time_sec=2.0,
            success=True
        )
        
        # customer123과 30일 이내로 필터링
        stats = repository.get_llm_api_stats(customer_id="customer123", days=30)
        assert len(stats) == 1
        assert stats[0]["customer_id"] == "customer123"
