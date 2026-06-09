"""Log Repository.

애플리케이션 로그 관리를 담당합니다.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from .base import BaseRepository


class LogRepository(BaseRepository):
    """로그 Repository.

    애플리케이션 로그의 저장, 조회, 내보내기를 담당합니다.
    """

    def insert_log(
        self,
        level: str,
        log_name: str,
        message: str,
        module: Optional[str] = None,
        function: Optional[str] = None,
        line_number: Optional[int] = None,
        retention_days: int = 7,
    ) -> None:
        """로그 레코드 삽입.

        Args:
            level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
            log_name: 로거 이름
            message: 로그 메시지
            module: 모듈 이름 (선택)
            function: 함수 이름 (선택)
            line_number: 라인 번호 (선택)
            retention_days: 보관 기간 (일). 이전의 로그 자동 삭제.
        """
        timestamp = datetime.now().isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 오래된 로그 자동 삭제 (롤링 방식)
            if retention_days > 0:
                cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
                cursor.execute('''
                    DELETE FROM logs
                    WHERE timestamp < ?
                ''', (cutoff_date,))

            # 새 로그 삽입
            cursor.execute('''
                INSERT INTO logs (timestamp, level, log_name, message, module, function, line_number)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, level, log_name, message, module, function, line_number))

            conn.commit()
            # log.debug(f"로그 삽입: {level} - {log_name}")  # 무한 루프 방지를 위해 주석 처리
        except Exception as e:
            conn.rollback()
            # log.error(f"로그 삽입 실패: {e}")  # 무한 루프 방지를 위해 주석 처리
            raise
        finally:
            conn.close()

    def get_logs(
        self,
        level: Optional[str] = None,
        limit: int = 100,
        hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """로그 레코드 조회.

        Args:
            level: 필터링할 로그 레벨 (선택)
            limit: 조회할 레코드 수
            hours: 최근 N시간 내의 로그만 조회 (선택)

        Returns:
            로그 레코드 리스트
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM logs'
            params = []

            conditions = []
            if level:
                conditions.append('level = ?')
                params.append(level)
            if hours:
                cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
                conditions.append('timestamp > ?')
                params.append(cutoff)

            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # 컬럼 이름 가져오기
            cursor.execute('PRAGMA table_info(logs)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def export_logs_to_csv(
        self,
        output_path: str,
        level: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> int:
        """로그를 CSV 파일로 내보내기.

        Args:
            output_path: 출력 CSV 파일 경로
            level: 필터링할 로그 레벨 (선택)
            hours: 최근 N시간 내의 로그만 내보내기 (선택)

        Returns:
            내보낸 레코드 수
        """
        logs = self.get_logs(level=level, limit=10000, hours=hours)

        if not logs:
            return 0

        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            if logs:
                writer = csv.DictWriter(f, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)

        log.info(f"로그 CSV 내보내기 완료: {len(logs)}개 레코드 -> {output_path}")
        return len(logs)

    def export_logs_to_json(
        self,
        output_path: str,
        level: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> int:
        """로그를 JSON 파일로 내보내기.

        Args:
            output_path: 출력 JSON 파일 경로
            level: 필터링할 로그 레벨 (선택)
            hours: 최근 N시간 내의 로그만 내보내기 (선택)

        Returns:
            내보낸 레코드 수
        """
        logs = self.get_logs(level=level, limit=10000, hours=hours)

        if not logs:
            return 0

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        log.info(f"로그 JSON 내보내기 완료: {len(logs)}개 레코드 -> {output_path}")
        return len(logs)

    def cleanup_old_logs(
        self,
        days: int = 7,
    ) -> int:
        """오래된 로그 삭제.

        Args:
            days: 보관할 기간 (일), 이전의 로그 삭제

        Returns:
            삭제된 레코드 수
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM logs
                WHERE timestamp < ?
            ''', (cutoff_date,))

            deleted_count = cursor.rowcount
            conn.commit()

            log.info(f"오래된 로그 삭제 완료: {deleted_count}개 레코드 ({days}일 이전)")
            return deleted_count
        except Exception as e:
            conn.rollback()
            log.error(f"오래된 로그 삭제 실패: {e}")
            raise
        finally:
            conn.close()
