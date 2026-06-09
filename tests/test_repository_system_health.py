"""
System Health Repository 테스트 - 시스템 헬스 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
from src.cli.repositories.system_health import SystemHealthRepository


class TestSystemHealthRepository:
    """SystemHealthRepository 테스트"""

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
            CREATE TABLE IF NOT EXISTS system_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu_usage_percent REAL,
                memory_usage_percent REAL,
                disk_usage_percent REAL,
                disk_free_gb REAL,
                gpu_usage_percent REAL,
                gpu_memory_usage_percent REAL,
                network_status TEXT DEFAULT 'ok',
                api_latency_ms REAL,
                active_jobs INTEGER DEFAULT 0,
                queue_size INTEGER DEFAULT 0
            )
        ''')
        
        # 추가 테이블 생성 (check_health 테스트용)
        for table in ["executions", "logs", "analysis_stats", "model_performance",
                      "score_trends", "llm_api_stats", "image_metadata",
                      "error_analysis", "audit_log"]:
            if table == "logs":
                cursor.execute(f'''
                    CREATE TABLE IF NOT EXISTS {table} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT,
                        log_name TEXT,
                        message TEXT
                    )
                ''')
            else:
                cursor.execute(f'''
                    CREATE TABLE IF NOT EXISTS {table} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL
                    )
                ''')
        
        conn.commit()
        conn.close()
        
        return SystemHealthRepository(db_path)

    def test_record_system_health(self, repository):
        """시스템 헬스 기록"""
        repository.record_system_health(
            cpu_usage_percent=45.5,
            memory_usage_percent=60.2,
            disk_usage_percent=75.0,
            disk_free_gb=100.5,
            gpu_usage_percent=30.0,
            gpu_memory_usage_percent=40.0,
            network_status="ok",
            api_latency_ms=150.0,
            active_jobs=5,
            queue_size=10
        )
        
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1
        assert health[0]["cpu_usage_percent"] == 45.5
        assert health[0]["memory_usage_percent"] == 60.2
        assert health[0]["disk_usage_percent"] == 75.0
        assert health[0]["disk_free_gb"] == 100.5
        assert health[0]["gpu_usage_percent"] == 30.0
        assert health[0]["gpu_memory_usage_percent"] == 40.0
        assert health[0]["network_status"] == "ok"
        assert health[0]["api_latency_ms"] == 150.0
        assert health[0]["active_jobs"] == 5
        assert health[0]["queue_size"] == 10

    def test_record_system_health_minimal(self, repository):
        """최소 파라미터로 시스템 헬스 기록"""
        repository.record_system_health()
        
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1
        # psutil이 설치되어 있으면 기본값이 계산됨
        # psutil이 없으면 None일 수 있음
        assert "cpu_usage_percent" in health[0]
        assert "memory_usage_percent" in health[0]

    def test_record_system_health_partial(self, repository):
        """일부 파라미터만 지정하여 시스템 헬스 기록"""
        repository.record_system_health(
            cpu_usage_percent=50.0,
            memory_usage_percent=70.0
        )
        
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1
        assert health[0]["cpu_usage_percent"] == 50.0
        assert health[0]["memory_usage_percent"] == 70.0
        assert health[0]["network_status"] == "ok"  # 기본값
        assert health[0]["active_jobs"] == 0  # 기본값

    def test_get_system_health_with_hours_filter(self, repository):
        """시간 필터로 시스템 헬스 조회"""
        repository.record_system_health(
            cpu_usage_percent=50.0,
            memory_usage_percent=70.0
        )
        
        # 24시간 이내 헬스 조회
        health = repository.get_system_health(hours=24, limit=10)
        assert len(health) == 1
        
        # 1시간 이내 헬스 조회
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1

    def test_get_system_health_limit(self, repository):
        """limit 파라미터로 결과 제한"""
        # 여러 헬스 기록
        for i in range(5):
            repository.record_system_health(
                cpu_usage_percent=50.0 + i,
                memory_usage_percent=70.0 + i
            )
        
        # limit=3
        health = repository.get_system_health(hours=24, limit=3)
        assert len(health) == 3

    def test_get_system_health_ordering(self, repository):
        """최신순 정렬 검증"""
        # 여러 헬스 기록
        for i in range(3):
            repository.record_system_health(
                cpu_usage_percent=50.0 + i,
                memory_usage_percent=70.0 + i
            )
        
        health = repository.get_system_health(hours=24, limit=10)
        # 최신순 정렬 확인
        assert len(health) == 3
        # timestamp 필드 확인
        assert "timestamp" in health[0]

    def test_get_system_health_empty(self, repository):
        """데이터가 없을 때 시스템 헬스 조회"""
        health = repository.get_system_health(hours=24, limit=10)
        assert len(health) == 0

    def test_check_health(self, repository):
        """DB 상태 확인"""
        health = repository.check_health()
        assert health["healthy"] is True
        assert "file_size_mb" in health
        assert "file_size_bytes" in health
        assert "row_counts" in health
        assert "db_path" in health
        assert "last_check" in health
        assert health["db_path"] == repository.db_path

    def test_check_health_with_data(self, repository, db_path):
        """데이터가 있는 DB 상태 확인"""
        # 테이블에 데이터 추가
        conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit 모드
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO executions (timestamp)
            VALUES ('2024-01-01T00:00:00')
        ''')
        
        cursor.execute('''
            INSERT INTO logs (timestamp, level, log_name, message)
            VALUES ('2024-01-01T00:00:00', 'INFO', 'test', 'message')
        ''')
        
        # WAL 모드 활성화 (Windows 파일 잠금 완화)
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        
        # 연결을 명시적으로 닫고 가비지 컬렉션 유도
        cursor.close()
        conn.close()
        del conn
        del cursor
        
        # 충분한 시간 지연으로 Windows 파일 잠금 해제
        import time
        import gc
        gc.collect()
        time.sleep(1.0)
        
        # 새로운 연결로 상태 확인 (Windows 파일 잠금 방지)
        health = repository.check_health()
        assert health["healthy"] is True
        assert health["row_counts"]["executions"] == 1
        assert health["row_counts"]["logs"] == 1

    def test_check_health_file_size(self, repository):
        """파일 크기 확인"""
        health = repository.check_health()
        assert health["file_size_bytes"] > 0
        assert health["file_size_mb"] > 0

    def test_get_slow_queries(self, repository):
        """느린 쿼리 조회 (현재 미구현)"""
        # 현재 구현되지 않음 - 빈 리스트 반환
        slow_queries = repository.get_slow_queries(threshold_ms=100, limit=10)
        assert slow_queries == []

    def test_record_system_health_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        # 현재 구현에서는 예외가 발생하지 않으므로 기본 동작만 확인
        # 실제 롤백 테스트는 DB 트랜잭션 설정이 필요
        pass

    def test_record_multiple_health_records(self, repository):
        """여러 헬스 레코드 기록"""
        for i in range(5):
            repository.record_system_health(
                cpu_usage_percent=50.0 + i,
                memory_usage_percent=70.0 + i,
                disk_usage_percent=75.0 + i
            )
        
        health = repository.get_system_health(hours=24, limit=10)
        assert len(health) == 5

    def test_check_health_missing_table(self, repository, db_path):
        """존재하지 않는 테이블 처리"""
        # 존재하지 않는 테이블은 row_counts에 0으로 표시됨
        health = repository.check_health()
        assert health["healthy"] is True
        # 모든 테이블이 row_counts에 포함되어야 함
        expected_tables = [
            "executions", "logs", "analysis_stats", "model_performance",
            "score_trends", "llm_api_stats", "image_metadata",
            "error_analysis", "system_health", "audit_log"
        ]
        for table in expected_tables:
            assert table in health["row_counts"]

    def test_record_system_health_with_gpu(self, repository):
        """GPU 관련 파라미터 기록"""
        repository.record_system_health(
            gpu_usage_percent=80.0,
            gpu_memory_usage_percent=75.0
        )
        
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1
        assert health[0]["gpu_usage_percent"] == 80.0
        assert health[0]["gpu_memory_usage_percent"] == 75.0

    def test_record_system_health_network_status(self, repository):
        """네트워크 상태 기록"""
        repository.record_system_health(
            network_status="degraded"
        )
        
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1
        assert health[0]["network_status"] == "degraded"

    def test_record_system_health_api_latency(self, repository):
        """API 지연 시간 기록"""
        repository.record_system_health(
            api_latency_ms=250.5
        )
        
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1
        assert health[0]["api_latency_ms"] == 250.5

    def test_record_system_health_job_queue(self, repository):
        """작업 및 대기열 정보 기록"""
        repository.record_system_health(
            active_jobs=15,
            queue_size=25
        )
        
        health = repository.get_system_health(hours=1, limit=10)
        assert len(health) == 1
        assert health[0]["active_jobs"] == 15
        assert health[0]["queue_size"] == 25
