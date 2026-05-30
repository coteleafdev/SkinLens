"""
test_backup.py — 백업 및 복구 테스트
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from src.server.backup import BackupManager
import asyncio


class TestBackupManager:
    """백업 관리자 테스트"""

    @pytest.fixture
    def temp_dirs(self):
        """임시 디렉토리 fixture"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            backup_dir = tmpdir_path / "backups"
            db_path = tmpdir_path / "test.db"
            results_dir = tmpdir_path / "results"

            # 테스트용 파일 생성
            db_path.write_text("test db content")
            results_dir.mkdir(parents=True, exist_ok=True)
            (results_dir / "test.txt").write_text("test result")

            yield {
                "backup_dir": backup_dir,
                "db_path": db_path,
                "results_dir": results_dir,
            }

            # 정리
            shutil.rmtree(tmpdir_path, ignore_errors=True)

    def test_backup_manager_initialization(self, temp_dirs):
        """백업 관리자 초기화 테스트"""
        manager = BackupManager(
            backup_dir=temp_dirs["backup_dir"],
            db_path=temp_dirs["db_path"],
            results_dir=temp_dirs["results_dir"],
            max_backups=3,
            backup_interval_hours=1,
        )

        assert manager.backup_dir == temp_dirs["backup_dir"]
        assert manager.db_path == temp_dirs["db_path"]
        assert manager.results_dir == temp_dirs["results_dir"]
        assert manager.max_backups == 3
        assert manager.backup_interval_hours == 1

    def test_create_backup(self, temp_dirs):
        """백업 생성 테스트"""
        manager = BackupManager(
            backup_dir=temp_dirs["backup_dir"],
            db_path=temp_dirs["db_path"],
            results_dir=temp_dirs["results_dir"],
            max_backups=3,
            backup_interval_hours=1,
        )

        backup_path = asyncio.run(manager.create_backup())

        assert backup_path.exists()
        assert backup_path.suffix == ".zip"
        assert backup_path.name.startswith("backup_")

    def test_cleanup_old_backups(self, temp_dirs):
        """오래된 백업 정리 테스트"""
        manager = BackupManager(
            backup_dir=temp_dirs["backup_dir"],
            db_path=temp_dirs["db_path"],
            results_dir=temp_dirs["results_dir"],
            max_backups=2,
            backup_interval_hours=1,
        )

        # 3개 백업 생성 (각 생성 후 정리가 발생하므로 최종적으로 2개만 남음)
        asyncio.run(manager.create_backup())
        asyncio.run(manager.create_backup())
        asyncio.run(manager.create_backup())

        # 정리 후 최대 2개만 남아야 함
        backups = list(temp_dirs["backup_dir"].glob("backup_*.zip"))
        assert len(backups) <= 2

    def test_list_backups(self, temp_dirs):
        """백업 목록 조회 테스트"""
        manager = BackupManager(
            backup_dir=temp_dirs["backup_dir"],
            db_path=temp_dirs["db_path"],
            results_dir=temp_dirs["results_dir"],
            max_backups=3,
            backup_interval_hours=1,
        )

        # 백업 없음
        backups = manager.list_backups()
        assert len(backups) == 0

    def test_delete_backup(self, temp_dirs):
        """백업 삭제 테스트"""
        manager = BackupManager(
            backup_dir=temp_dirs["backup_dir"],
            db_path=temp_dirs["db_path"],
            results_dir=temp_dirs["results_dir"],
            max_backups=3,
            backup_interval_hours=1,
        )

        # 존재하지 않는 백업 삭제
        result = manager.delete_backup("nonexistent.zip")
        assert result is False

    def test_backup_config_from_json(self):
        """config.json에서 백업 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        backup_config = server_config.get("backup", {})

        assert "backup_dir" in backup_config
        assert "db_path" in backup_config
        assert "max_backups" in backup_config
        assert "backup_interval_hours" in backup_config
