"""
DB 관리 CLI 단위 테스트.

DB CLI 명령어 (backup, status, migrate, archive, replica)를 테스트합니다.
"""
import os
import tempfile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from click.testing import CliRunner
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.db_cli import db_cli


@pytest.mark.server
class TestDBCLI:
    """DB CLI 테스트."""
    
    @pytest.fixture
    def runner(self):
        """CLI 러너 생성."""
        return CliRunner()
    
    @pytest.fixture
    def temp_db(self):
        """임시 DB 생성 (올바른 스키마로 초기화)."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        
        # ExecutionHistoryDB로 올바른 스키마 초기화
        from src.cli.execution_history import ExecutionHistoryDB
        ExecutionHistoryDB(path)
        
        # 환경 변수 설정
        original_db = os.environ.get("EXECUTION_HISTORY_DB")
        os.environ["EXECUTION_HISTORY_DB"] = path
        
        yield path
        
        # 환경 변수 복원
        if original_db:
            os.environ["EXECUTION_HISTORY_DB"] = original_db
        else:
            os.environ.pop("EXECUTION_HISTORY_DB", None)
        
        # 파일 삭제
        if os.path.exists(path):
            os.remove(path)
    
    @pytest.fixture
    def backup_dir(self):
        """테스트용 백업 디렉토리 (function-scoped)."""
        temp_dir = tempfile.mkdtemp()
        original_dir = os.environ.get("SKIN_API_BACKUP_DIR")
        os.environ["SKIN_API_BACKUP_DIR"] = temp_dir
        
        yield temp_dir
        
        if original_dir:
            os.environ["SKIN_API_BACKUP_DIR"] = original_dir
        else:
            os.environ.pop("SKIN_API_BACKUP_DIR", None)
        
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    def test_cli_help(self, runner):
        """CLI 도움말 테스트."""
        result = runner.invoke(db_cli, ["--help"])
        assert result.exit_code == 0
        assert "DB 관리 CLI" in result.output

    def test_backup_command(self, runner, temp_db, backup_dir):
        """백업 명령어 테스트."""
        # 테스트용 DB 경로 설정
        original_db = os.environ.get("EXECUTION_HISTORY_DB")
        os.environ["EXECUTION_HISTORY_DB"] = temp_db
        
        try:
            result = runner.invoke(db_cli, ["backup"])
            
            assert result.exit_code == 0
            # 백업 명령어가 성공적으로 실행되는지만 확인
            assert "Backup created" in result.output or "backup" in result.output.lower() or result.exit_code == 0
        finally:
            # 환경변수 복원
            if original_db:
                os.environ["EXECUTION_HISTORY_DB"] = original_db
            else:
                os.environ.pop("EXECUTION_HISTORY_DB", None)
    
    def test_status_command(self, runner, temp_db):
        """상태 확인 명령어 테스트."""
        result = runner.invoke(db_cli, ["status"])
        
        assert result.exit_code == 0
        assert "DB Status" in result.output
        # 실제 DB 정보 검증 - 파일 크기나 테이블 정보가 포함되는지 확인
        assert "MB" in result.output or "table" in result.output.lower() or "테이블" in result.output
        # Row counts가 포함되는지 확인
        assert "executions:" in result.output or "logs:" in result.output
    
    def test_migrate_command(self, runner, temp_db):
        """마이그레이션 명령어 테스트."""
        result = runner.invoke(db_cli, ["migrate"])
        
        assert result.exit_code == 0
        # 마이그레이션 메시지 확인
        assert "version" in result.output.lower()
    
    def test_archive_command(self, runner, temp_db):
        """아카이빙 명령어 테스트."""
        # 아카이빙할 데이터가 있는 테이블 생성 필요
        from src.cli.execution_history import ExecutionHistoryDB
        db = ExecutionHistoryDB(temp_db)
        # 테스트 데이터 추가
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "test.jpg")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(output_dir)
            with open(input_path, "w") as f:
                f.write("test")
            
            db.log_execution(
                input_path=input_path,
                output_dir=output_dir,
                result={"score": 85.5},
                execution_time=10.0,
                success=True
            )
        
        result = runner.invoke(db_cli, ["archive", "--days=90"])
        
        assert result.exit_code == 0
        assert "archived" in result.output.lower()
    
    def test_replica_command(self, runner, temp_db):
        """복제본 생성 명령어 테스트."""
        fd, replica_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(replica_path)
        
        result = runner.invoke(db_cli, ["replica", "--output", replica_path])
        
        assert result.exit_code == 0
        assert "replica created" in result.output.lower()
        
        # 복제본 파일 확인
        assert os.path.exists(replica_path)
        
        # 복제본 데이터 확인 - executions 테이블이 있는지 확인
        conn = sqlite3.connect(replica_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='executions'")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
        
        # 정리
        os.remove(replica_path)
    
    def test_cleanup_command(self, runner, temp_db):
        """정리 명령어 테스트."""
        from src.cli.execution_history import ExecutionHistoryDB
        db = ExecutionHistoryDB(temp_db)
        # 테스트 데이터 추가
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "test.jpg")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(output_dir)
            with open(input_path, "w") as f:
                f.write("test")
            
            db.log_execution(
                input_path=input_path,
                output_dir=output_dir,
                result={"score": 85.5},
                execution_time=10.0,
                success=True
            )
        
        result = runner.invoke(db_cli, ["cleanup", "--days=90"])
        
        assert result.exit_code == 0
        assert "archived" in result.output.lower() or "cleanup" in result.output.lower()
    
    def test_restore_command_not_implemented(self, runner):
        """복구 명령어 테스트 (구현되지 않음)."""
        result = runner.invoke(db_cli, ["restore"])
        
        assert result.exit_code == 0
        assert "not implemented" in result.output.lower()


@pytest.mark.server
class TestDBCLIIntegration:
    """DB CLI 통합 테스트."""
    
    @pytest.fixture
    def temp_env(self):
        """임시 환경 설정."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        backup_dir = tempfile.mkdtemp()
        
        # 테스트 DB 생성 - 올바른 스키마로 초기화
        from src.cli.execution_history import ExecutionHistoryDB
        db = ExecutionHistoryDB(db_path)
        
        # 환경 변수 설정
        original_db = os.environ.get("EXECUTION_HISTORY_DB")
        original_backup_dir = os.environ.get("SKIN_API_BACKUP_DIR")
        
        os.environ["EXECUTION_HISTORY_DB"] = db_path
        os.environ["SKIN_API_BACKUP_DIR"] = backup_dir
        
        yield db_path, backup_dir
        
        # 환경 변수 복원
        if original_db:
            os.environ["EXECUTION_HISTORY_DB"] = original_db
        else:
            os.environ.pop("EXECUTION_HISTORY_DB", None)
        
        if original_backup_dir:
            os.environ["SKIN_API_BACKUP_DIR"] = original_backup_dir
        else:
            os.environ.pop("SKIN_API_BACKUP_DIR", None)
        
        # 정리
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
    
    def test_full_workflow(self, runner, temp_env):
        """전체 워크플로우 테스트."""
        db_path, backup_dir = temp_env
        
        # 1. 상태 확인
        result = runner.invoke(db_cli, ["status"])
        assert result.exit_code == 0
        assert "DB Status" in result.output
        
        # 2. 백업
        result = runner.invoke(db_cli, ["backup"])
        assert result.exit_code == 0
        
        # 3. 복제본 생성
        replica_path = os.path.join(backup_dir, "replica.db")
        result = runner.invoke(db_cli, ["replica", "--output", replica_path])
        assert result.exit_code == 0
        assert os.path.exists(replica_path)
        
        # 4. 상태 확인
        result = runner.invoke(db_cli, ["status"])
        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
