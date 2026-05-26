"""Error and Audit Repository.

에러 분석 및 감사 로그 관리를 담당합니다.
"""
from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from .base import BaseRepository


class ErrorAuditRepository(BaseRepository):
    """에러 및 감사 로그 Repository.

    에러 추적, 해결 관리, 감사 로그를 담당합니다.
    """

    # ── 에러 관리 메서드 ───────────────────────────────────────────────────

    def record_error(
        self,
        error_type: str,
        error_message: str,
        module: Optional[str] = None,
        function: Optional[str] = None,
        line_number: Optional[int] = None,
        stack_trace: Optional[str] = None,
        customer_id: Optional[str] = None,
        image_path: Optional[str] = None,
        pipeline_mode: Optional[str] = None,
        severity: str = "medium",
    ) -> None:
        """에러 기록.

        Args:
            error_type: 에러 유형
            error_message: 에러 메시지
            module: 모듈
            function: 함수
            line_number: 라인 번호
            stack_trace: 스택 트레이스
            customer_id: 고객 ID
            image_path: 이미지 경로
            pipeline_mode: 파이프라인 모드
            severity: 심각도
        """
        timestamp = datetime.now().isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO error_analysis (
                    timestamp, error_type, error_message, module, function, line_number,
                    stack_trace, customer_id, image_path, pipeline_mode, severity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, error_type, error_message, module, function, line_number,
                  stack_trace, customer_id, image_path, pipeline_mode, severity))

            conn.commit()
            log.debug(f"에러 기록: {error_type} - {error_message}")
        except Exception as e:
            conn.rollback()
            log.error(f"에러 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_errors(
        self,
        resolved: Optional[bool] = None,
        severity: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """에러 조회.

        Args:
            resolved: 해결 여부
            severity: 심각도
            days: 조회할 기간 (일)
            limit: 조회할 레코드 수

        Returns:
            에러 레코드 리스트
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM error_analysis WHERE timestamp > ?'
            params = [cutoff_date]

            if resolved is not None:
                query += ' AND resolved = ?'
                params.append(resolved)
            if severity:
                query += ' AND severity = ?'
                params.append(severity)

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute('PRAGMA table_info(error_analysis)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def resolve_error(self, error_id: int, resolution_note: str) -> None:
        """에러 해결 표시.

        Args:
            error_id: 에러 ID
            resolution_note: 해결 노트
        """
        resolved_at = datetime.now().isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE error_analysis
                SET resolved = 1, resolved_at = ?, resolution_note = ?
                WHERE id = ?
            ''', (resolved_at, resolution_note, error_id))

            conn.commit()
            log.info(f"에러 해결 표시: ID={error_id}")
        except Exception as e:
            conn.rollback()
            log.error(f"에러 해결 표시 실패: {e}")
            raise
        finally:
            conn.close()

    def get_error_summary(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """최근 에러 이력 조회 (executions 테이블).

        Args:
            limit: 조회할 레코드 수

        Returns:
            에러 레코드 리스트 (dict 형태)
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT * FROM executions
                WHERE success = 0
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

            rows = [dict(row) for row in cursor.fetchall()]
            return rows
        finally:
            conn.close()

    # ── 감사 로그 메서드 ───────────────────────────────────────────────────

    def record_audit_log(
        self,
        actor_customer_id: Optional[str],
        target_customer_id: Optional[str],
        endpoint: str,
        method: str,
        user_role: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """감사 로그 기록.

        Args:
            actor_customer_id: 수행자 고객 ID
            target_customer_id: 대상 고객 ID
            endpoint: API 엔드포인트
            method: HTTP 메서드
            user_role: 사용자 역할
            ip_address: IP 주소
            user_agent: 사용자 에이전트
            success: 성공 여부
            error_message: 에러 메시지
        """
        timestamp = datetime.now().isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO audit_log (
                    timestamp, actor_customer_id, target_customer_id, endpoint, method,
                    user_role, ip_address, user_agent, success, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, actor_customer_id, target_customer_id, endpoint, method,
                  user_role, ip_address, user_agent, success, error_message))

            conn.commit()
            log.debug(f"감사 로그 기록: {endpoint} {method} by {actor_customer_id}")
        except Exception as e:
            conn.rollback()
            log.error(f"감사 로그 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_audit_logs(
        self,
        actor_customer_id: Optional[str] = None,
        target_customer_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """감사 로그 조회.

        Args:
            actor_customer_id: 수행자 고객 ID
            target_customer_id: 대상 고객 ID
            days: 조회할 기간 (일)
            limit: 조회할 레코드 수

        Returns:
            감사 로그 리스트
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM audit_log WHERE timestamp > ?'
            params = [cutoff_date]

            if actor_customer_id:
                query += ' AND actor_customer_id = ?'
                params.append(actor_customer_id)
            if target_customer_id:
                query += ' AND target_customer_id = ?'
                params.append(target_customer_id)

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute('PRAGMA table_info(audit_log)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
