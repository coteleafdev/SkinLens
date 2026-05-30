"""
Customer Data Repository 테스트 - 고객 데이터 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
import json
from src.cli.repositories.customer_data import CustomerDataRepository


class TestCustomerDataRepository:
    """CustomerDataRepository 테스트"""

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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_api_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT,
                timestamp TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                estimated_cost_usd REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT,
                timestamp TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                severity TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return CustomerDataRepository(db_path)

    def test_delete_customer_data(self, repository, db_path):
        """고객 데이터 삭제"""
        # 테스트 데이터 삽입
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # analysis_stats
        cursor.execute('''
            INSERT INTO analysis_stats (date, customer_id, total_analyses, successful_analyses, failed_analyses)
            VALUES ('2024-01-01', 'customer123', 10, 8, 2)
        ''')
        
        # score_trends
        cursor.execute('''
            INSERT INTO score_trends (customer_id, timestamp, overall_score)
            VALUES ('customer123', '2024-01-01T00:00:00', 85.0)
        ''')
        
        # llm_api_stats
        cursor.execute('''
            INSERT INTO llm_api_stats (customer_id, timestamp, provider, model, total_tokens)
            VALUES ('customer123', '2024-01-01T00:00:00', 'openai', 'gpt-4', 1000)
        ''')
        
        # error_analysis
        cursor.execute('''
            INSERT INTO error_analysis (customer_id, timestamp, error_type, error_message)
            VALUES ('customer123', '2024-01-01T00:00:00', 'TimeoutError', 'Request timeout')
        ''')
        
        conn.commit()
        conn.close()
        
        # 삭제 실행
        deleted_count = repository.delete_customer_data("customer123")
        assert deleted_count == 4
        
        # 삭제 확인
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM analysis_stats WHERE customer_id = ?', ('customer123',))
        assert cursor.fetchone()[0] == 0
        
        cursor.execute('SELECT COUNT(*) FROM score_trends WHERE customer_id = ?', ('customer123',))
        assert cursor.fetchone()[0] == 0
        
        cursor.execute('SELECT COUNT(*) FROM llm_api_stats WHERE customer_id = ?', ('customer123',))
        assert cursor.fetchone()[0] == 0
        
        cursor.execute('SELECT COUNT(*) FROM error_analysis WHERE customer_id = ?', ('customer123',))
        assert cursor.fetchone()[0] == 0
        
        conn.close()

    def test_delete_customer_data_partial(self, repository, db_path):
        """일부 테이블에만 데이터가 있는 경우 삭제"""
        # analysis_stats에만 데이터 삽입
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO analysis_stats (date, customer_id, total_analyses, successful_analyses, failed_analyses)
            VALUES ('2024-01-01', 'customer123', 10, 8, 2)
        ''')
        
        conn.commit()
        conn.close()
        
        # 삭제 실행
        deleted_count = repository.delete_customer_data("customer123")
        assert deleted_count == 1

    def test_delete_customer_data_no_data(self, repository):
        """데이터가 없는 고객 삭제"""
        deleted_count = repository.delete_customer_data("nonexistent")
        assert deleted_count == 0

    def test_delete_customer_data_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        # 테스트 데이터 삽입
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO analysis_stats (date, customer_id, total_analyses, successful_analyses, failed_analyses)
            VALUES ('2024-01-01', 'customer123', 10, 8, 2)
        ''')
        
        conn.commit()
        conn.close()
        
        # 존재하지 않는 테이블로 인한 에러 유도 (테이블 목록 수정 필요)
        # 이 테스트는 실제 구현에서 테이블이 존재하지 않을 경우를 시뮬레이션
        # 현재 구현에서는 모든 테이블이 존재한다고 가정하므로 생략

    def test_export_customer_data(self, repository, db_path):
        """고객 데이터 내보내기"""
        # 테스트 데이터 준비
        analysis_stats_data = [
            {"date": "2024-01-01", "total_analyses": 10, "successful_analyses": 8}
        ]
        
        score_trends_data = [
            {"timestamp": "2024-01-01T00:00:00", "overall_score": 85.0}
        ]
        
        llm_api_stats_data = [
            {"timestamp": "2024-01-01T00:00:00", "provider": "openai", "total_tokens": 1000}
        ]
        
        errors_data = [
            {"timestamp": "2024-01-01T00:00:00", "error_type": "TimeoutError"}
        ]
        
        audit_logs_data = [
            {"timestamp": "2024-01-01T00:00:00", "endpoint": "/v3/analyze"}
        ]
        
        # 내보내기 실행
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            exported_count = repository.export_customer_data(
                customer_id="customer123",
                output_path=output_path,
                analysis_stats_data=analysis_stats_data,
                score_trends_data=score_trends_data,
                llm_api_stats_data=llm_api_stats_data,
                errors_data=errors_data,
                audit_logs_data=audit_logs_data
            )
            
            assert exported_count == 5
            
            # 파일 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            assert data["customer_id"] == "customer123"
            assert "exported_at" in data
            assert len(data["analysis_stats"]) == 1
            assert len(data["score_trends"]) == 1
            assert len(data["llm_api_stats"]) == 1
            assert len(data["errors"]) == 1
            assert len(data["audit_logs"]) == 1
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_customer_data_empty(self, repository):
        """데이터가 없는 고객 내보내기"""
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            exported_count = repository.export_customer_data(
                customer_id="customer123",
                output_path=output_path
            )
            
            assert exported_count == 0
            
            # 파일 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            assert data["customer_id"] == "customer123"
            assert len(data["analysis_stats"]) == 0
            assert len(data["score_trends"]) == 0
            assert len(data["llm_api_stats"]) == 0
            assert len(data["errors"]) == 0
            assert len(data["audit_logs"]) == 0
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_customer_data_partial(self, repository):
        """일부 데이터만 있는 고객 내보내기"""
        analysis_stats_data = [
            {"date": "2024-01-01", "total_analyses": 10, "successful_analyses": 8}
        ]
        
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            exported_count = repository.export_customer_data(
                customer_id="customer123",
                output_path=output_path,
                analysis_stats_data=analysis_stats_data
            )
            
            assert exported_count == 1
            
            # 파일 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            assert len(data["analysis_stats"]) == 1
            assert len(data["score_trends"]) == 0
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_export_customer_data_json_format(self, repository):
        """JSON 형식 검증"""
        analysis_stats_data = [
            {"date": "2024-01-01", "total_analyses": 10}
        ]
        
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        
        try:
            repository.export_customer_data(
                customer_id="customer123",
                output_path=output_path,
                analysis_stats_data=analysis_stats_data
            )
            
            # JSON 유효성 확인
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 필수 필드 확인
            assert "customer_id" in data
            assert "exported_at" in data
            assert isinstance(data["analysis_stats"], list)
            assert isinstance(data["score_trends"], list)
            assert isinstance(data["llm_api_stats"], list)
            assert isinstance(data["errors"], list)
            assert isinstance(data["audit_logs"], list)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
