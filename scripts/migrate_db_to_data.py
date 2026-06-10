#!/usr/bin/env python3
"""
DB 마이그레이션 스크립트 - results/ → data/

기존 results/ 폴더의 DB 파일을 data/ 폴더로 안전하게 이동합니다.

사용법:
    python scripts/migrate_db_to_data.py
"""
import shutil
from pathlib import Path
from datetime import datetime
import sqlite3
import sys


def backup_file(src: Path, backup_dir: Path) -> Path:
    """파일 백업"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{src.name}.{timestamp}.bak"
    backup_path = backup_dir / backup_name
    shutil.copy2(src, backup_path)
    print(f"✓ 백업 생성: {backup_path}")
    return backup_path


def migrate_db(src: Path, dst: Path, backup_dir: Path) -> bool:
    """DB 파일 이동"""
    if not src.exists():
        print(f"  건너뜀: {src} (존재하지 않음)")
        return True
    
    if dst.exists():
        print(f"  경고: {dst} 이미 존재함")
        # 기존 파일 백업
        backup_file(dst, backup_dir)
        print(f"  기존 파일 덮어쓰기: {dst}")
    
    # 소스 파일 백업
    backup_file(src, backup_dir)
    
    # 파일 이동
    shutil.move(src, dst)
    print(f"✓ 이동 완료: {src} → {dst}")
    return True


def verify_db(db_path: Path) -> bool:
    """DB 파일 검증"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()
        print(f"  검증 완료: {len(tables)}개 테이블 발견")
        return True
    except Exception as e:
        print(f"  ✗ 검증 실패: {e}")
        return False


def main():
    """메인 함수"""
    project_root = Path(__file__).parent.parent
    results_dir = project_root / "results"
    data_dir = project_root / "data"
    backup_dir = data_dir / "backups"
    
    # 백업 디렉토리 생성
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # data 디렉토리 생성
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("DB 마이그레이션: results/ → data/")
    print("=" * 60)
    print(f"프로젝트 루트: {project_root}")
    print(f"백업 디렉토리: {backup_dir}")
    print()
    
    # 마이그레이션할 DB 파일 목록
    db_files = [
        ("execution_history.db", "execution_history.db"),
        ("skin_analysis.db", "skin_analysis.db"),
        ("images.db", "images.db"),
    ]
    
    success_count = 0
    total_count = len(db_files)
    
    for src_name, dst_name in db_files:
        src_path = results_dir / src_name
        dst_path = data_dir / dst_name
        
        print(f"처리 중: {src_name}")
        
        if migrate_db(src_path, dst_path, backup_dir):
            if verify_db(dst_path):
                success_count += 1
            else:
                print(f"  ✗ 검증 실패로 복원 필요")
                sys.exit(1)
        else:
            print(f"  ✗ 마이그레이션 실패")
            sys.exit(1)
        
        print()
    
    print("=" * 60)
    print(f"마이그레이션 완료: {success_count}/{total_count} 파일")
    print("=" * 60)
    print()
    print("다음 단계:")
    print("1. data/ 폴더의 DB 파일 확인")
    print("2. results/ 폴더의 기존 DB 파일 삭제 (백업 후)")
    print("3. 애플리케이션 재시작")


if __name__ == "__main__":
    main()
