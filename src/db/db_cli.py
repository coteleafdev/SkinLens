"""
DB 관리 CLI 명령줄 도구.

데이터베이스 백업, 정리, 마이그레이션 등 DB 관리 작업을 수행합니다.
"""
import click
import shutil
from datetime import datetime
from pathlib import Path
import os
import sys

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.cli.execution_history import (
    ExecutionHistoryDB,
    archive_old_data,
    DBMigrationManager,
    create_readonly_replica,
)
from src.utils.config import get_db_path_from_env


@click.group()
def db_cli():
    """DB 관리 CLI"""
    pass


@db_cli.command()
@click.option("--days", default=90, help="보관 기간 (일)")
def cleanup(days: int):
    """오래된 데이터 정리"""
    db_path = get_db_path_from_env()
    archive_old_data(db_path, days)
    click.echo(f"Data older than {days} days archived")


@db_cli.command()
def backup():
    """DB 백업"""
    from src.server.deps import BACKUP_DIR
    
    db_path = get_db_path_from_env()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"execution_history_{timestamp}.db")
    
    shutil.copy(db_path, backup_path)
    click.echo(f"Backup created: {backup_path}")


@db_cli.command()
def status():
    """DB 상태 확인"""
    db_path = get_db_path_from_env()
    db = ExecutionHistoryDB(db_path)
    
    health = db.check_health()
    
    if health["healthy"]:
        click.echo(f"DB Status: Healthy")
        click.echo(f"File Size: {health['file_size_mb']} MB")
        click.echo(f"Row Counts:")
        for table, count in health["row_counts"].items():
            click.echo(f"  {table}: {count}")
    else:
        click.echo(f"DB Status: Unhealthy - {health.get('error', 'Unknown error')}")


@db_cli.command()
def migrate():
    """DB 마이그레이션 실행"""
    db_path = get_db_path_from_env()
    manager = DBMigrationManager(db_path)
    
    current_version = manager.get_current_version()
    click.echo(f"Current DB version: {current_version}")
    
    manager.migrate()
    
    new_version = manager.get_current_version()
    click.echo(f"DB version after migration: {new_version}")


@db_cli.command()
@click.option("--days", default=90, help="보관 기간 (일)")
def archive(days: int):
    """오래된 데이터 아카이빙"""
    db_path = get_db_path_from_env()
    archive_old_data(db_path, days)
    click.echo(f"Data older than {days} days archived")


@db_cli.command()
def restore():
    """백업 파일로 DB 복구 (구현 필요)"""
    click.echo("Restore functionality not implemented yet")


@db_cli.command()
@click.option("--output", default="execution_history_readonly.db", help="복제본 파일 경로")
def replica(output: str):
    """읽기 전용 복제본 생성"""
    db_path = get_db_path_from_env()
    create_readonly_replica(db_path, output)
    click.echo(f"Read-only replica created: {output}")


if __name__ == "__main__":
    db_cli()
