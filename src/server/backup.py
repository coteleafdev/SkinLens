"""
backup.py — 데이터 백업 및 복구 시스템

기능:
- 자동 백업 스케줄링
- 백업 파일 관리
- 복구 기능
"""
import logging
import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List
import asyncio
import json

log = logging.getLogger(__name__)


class BackupManager:
    """백업 관리자"""

    def __init__(
        self,
        backup_dir: Path,
        db_path: Path,
        results_dir: Path,
        max_backups: int = 7,
        backup_interval_hours: int = 24,
    ):
        """
        Args:
            backup_dir: 백업 디렉토리
            db_path: 데이터베이스 파일 경로
            results_dir: 결과 파일 디렉토리
            max_backups: 최대 백업 개수
            backup_interval_hours: 백업 간격 (시간)
        """
        self.backup_dir = backup_dir
        self.db_path = db_path
        self.results_dir = results_dir
        self.max_backups = max_backups
        self.backup_interval_hours = backup_interval_hours
        self._backup_task: Optional[asyncio.Task] = None
        self._running = False

        # 백업 디렉토리 생성
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """백업 스케줄러 시작"""
        if self._running:
            return

        self._running = True
        log.info("백업 스케줄러 시작 (간격: %d시간)", self.backup_interval_hours)

        # 백업 태스크 생성
        self._backup_task = asyncio.create_task(self._backup_loop())

    async def stop(self) -> None:
        """백업 스케줄러 중지"""
        self._running = False

        if self._backup_task:
            self._backup_task.cancel()
            try:
                await self._backup_task
            except asyncio.CancelledError:
                pass

        log.info("백업 스케줄러 중지")

    async def _backup_loop(self) -> None:
        """백업 루프"""
        while self._running:
            try:
                # 백업 수행
                await self.create_backup()

                # 다음 백업까지 대기
                await asyncio.sleep(self.backup_interval_hours * 3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("백업 루프 오류: %s", e)
                await asyncio.sleep(300)  # 5분 후 재시도

    async def create_backup(self) -> Path:
        """백업 생성.

        Returns:
            백업 파일 경로
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.zip"
        backup_path = self.backup_dir / backup_name

        log.info("백업 생성 시작: %s", backup_name)

        try:
            # 임시 디렉토리 생성
            temp_dir = self.backup_dir / f"temp_{timestamp}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # 데이터베이스 백업
            if self.db_path.exists():
                db_backup = temp_dir / self.db_path.name
                shutil.copy2(self.db_path, db_backup)
                log.info("데이터베이스 백업 완료: %s", self.db_path.name)

            # 결과 파일 백업
            if self.results_dir.exists():
                results_backup = temp_dir / "results"
                shutil.copytree(self.results_dir, results_backup, ignore=shutil.ignore_patterns("temp_*"))
                log.info("결과 파일 백업 완료")

            # 백업 메타데이터 생성
            metadata = {
                "timestamp": timestamp,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "db_path": str(self.db_path),
                "results_dir": str(self.results_dir),
                "files": [f.name for f in temp_dir.rglob("*") if f.is_file()],
            }
            metadata_path = temp_dir / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # ZIP 파일 생성
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in temp_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(temp_dir)
                        zipf.write(file_path, arcname)

            # 임시 디렉토리 삭제
            shutil.rmtree(temp_dir, ignore_errors=True)

            log.info("백업 생성 완료: %s (크기: %.2f MB)", backup_name, backup_path.stat().st_size / (1024 * 1024))

            # 오래된 백업 정리
            await self.cleanup_old_backups()

            return backup_path

        except Exception as e:
            log.error("백업 생성 실패: %s", e)
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    async def cleanup_old_backups(self) -> None:
        """오래된 백업 정리"""
        try:
            backups = sorted(self.backup_dir.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)

            # 최대 백업 개수 초과 시 정리
            if len(backups) > self.max_backups:
                for old_backup in backups[self.max_backups:]:
                    old_backup.unlink()
                    log.info("오래된 백업 삭제: %s", old_backup.name)

        except Exception as e:
            log.error("백업 정리 실패: %s", e)

    def list_backups(self) -> List[dict]:
        """백업 목록 조회.

        Returns:
            백업 정보 목록
        """
        backups = []
        for backup_path in sorted(self.backup_dir.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                # 메타데이터 읽기
                with zipfile.ZipFile(backup_path, "r") as zipf:
                    if "metadata.json" in zipf.namelist():
                        with zipf.open("metadata.json") as f:
                            metadata = json.load(f)
                    else:
                        metadata = {}

                backups.append({
                    "name": backup_path.name,
                    "path": str(backup_path),
                    "size_mb": round(backup_path.stat().st_size / (1024 * 1024), 2),
                    "created_at": metadata.get("created_at", datetime.fromtimestamp(backup_path.stat().st_mtime).isoformat()),
                    "files": metadata.get("files", []),
                })
            except Exception as e:
                log.warning("백업 메타데이터 읽기 실패: %s, error=%s", backup_path.name, e)

        return backups

    async def restore_backup(self, backup_name: str) -> bool:
        """백업 복구.

        Args:
            backup_name: 백업 파일 이름

        Returns:
            복구 성공 여부
        """
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            log.error("백업 파일 없음: %s", backup_name)
            return False

        log.info("백업 복구 시작: %s", backup_name)

        try:
            # 임시 디렉토리 생성
            temp_dir = self.backup_dir / f"restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # 백업 압축 해제
            with zipfile.ZipFile(backup_path, "r") as zipf:
                zipf.extractall(temp_dir)

            # 데이터베이스 복구
            db_backup = temp_dir / self.db_path.name
            if db_backup.exists():
                # 기존 데이터베이스 백업
                if self.db_path.exists():
                    db_backup_path = self.db_path.with_suffix(f".backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
                    shutil.copy2(self.db_path, db_backup_path)
                    log.info("기존 데이터베이스 백업: %s", db_backup_path.name)

                # 데이터베이스 복구
                shutil.copy2(db_backup, self.db_path)
                log.info("데이터베이스 복구 완료")

            # 결과 파일 복구
            results_backup = temp_dir / "results"
            if results_backup.exists():
                # 기존 결과 파일 백업
                if self.results_dir.exists():
                    results_backup_path = self.results_dir.parent / f"results_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                    shutil.copytree(self.results_dir, results_backup_path)
                    log.info("기존 결과 파일 백업: %s", results_backup_path.name)

                # 결과 파일 복구
                if self.results_dir.exists():
                    shutil.rmtree(self.results_dir, ignore_errors=True)
                shutil.copytree(results_backup, self.results_dir)
                log.info("결과 파일 복구 완료")

            # 임시 디렉토리 삭제
            shutil.rmtree(temp_dir, ignore_errors=True)

            log.info("백업 복구 완료: %s", backup_name)
            return True

        except Exception as e:
            log.error("백업 복구 실패: %s, error=%s", backup_name, e)
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    def delete_backup(self, backup_name: str) -> bool:
        """백업 삭제.

        Args:
            backup_name: 백업 파일 이름

        Returns:
            삭제 성공 여부
        """
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            log.error("백업 파일 없음: %s", backup_name)
            return False

        try:
            backup_path.unlink()
            log.info("백업 삭제 완료: %s", backup_name)
            return True
        except Exception as e:
            log.error("백업 삭제 실패: %s, error=%s", backup_name, e)
            return False


# 전역 백업 관리자
_global_backup_manager: Optional[BackupManager] = None


def get_backup_manager() -> BackupManager:
    """전역 백업 관리자 반환"""
    global _global_backup_manager
    if _global_backup_manager is None:
        from src.utils.config import load_config
        from src.server.deps import jobs_root

        config = load_config()
        server_config = config.get("server", {})
        backup_config = server_config.get("backup", {})

        backup_dir = Path(backup_config.get("backup_dir", "backups"))
        db_path = Path(backup_config.get("db_path", "execution_history.db"))
        results_dir = jobs_root()
        max_backups = backup_config.get("max_backups", 7)
        backup_interval_hours = backup_config.get("backup_interval_hours", 24)

        _global_backup_manager = BackupManager(
            backup_dir=backup_dir,
            db_path=db_path,
            results_dir=results_dir,
            max_backups=max_backups,
            backup_interval_hours=backup_interval_hours,
        )
    return _global_backup_manager
