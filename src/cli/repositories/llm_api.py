"""LLM API Repository.

LLM API 호출 통계 관리를 담당합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from .base import BaseRepository


class LLMAPIRepository(BaseRepository):
    """LLM API 사용 통계 Repository.

    LLM API 통계 테이블을 담당합니다.
    """

    TABLE_NAME = "llm_api_stats"  # 테이블명 일반화

    def record_llm_api_call(
        self,
        customer_id: Optional[str],
        request_type: str,
        input_tokens: int,
        output_tokens: int,
        execution_time_sec: float,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """LLM API 호출 기록.

        Args:
            customer_id: 고객 ID
            request_type: 요청 유형
            input_tokens: 입력 토큰 수
            output_tokens: 출력 토큰 수
            execution_time_sec: 실행 시간
            success: 성공 여부
            error_message: 에러 메시지
        """
        timestamp = datetime.now().isoformat()
        total_tokens = input_tokens + output_tokens
        # Gemini 가격: $0.00025/1K input tokens, $0.0005/1K output tokens
        estimated_cost = (input_tokens / 1000 * 0.00025) + (output_tokens / 1000 * 0.0005)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(f'''
                INSERT INTO {self.TABLE_NAME} (
                    timestamp, customer_id, request_type, input_tokens, output_tokens,
                    total_tokens, execution_time_sec, success, error_message, estimated_cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, customer_id, request_type, input_tokens, output_tokens,
                  total_tokens, execution_time_sec, success, error_message, estimated_cost))

            conn.commit()
            log.debug(f"LLM API 호출 기록: request_type={request_type}, success={success}")
        except Exception as e:
            conn.rollback()
            log.error(f"LLM API 호출 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_llm_api_stats(
        self,
        customer_id: Optional[str] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """LLM API 통계 조회.

        Args:
            customer_id: 고객 ID
            days: 조회할 기간 (일)

        Returns:
            통계 레코드 리스트
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = f'SELECT * FROM {self.TABLE_NAME} WHERE timestamp > ?'
            params = [cutoff_date]

            if customer_id:
                query += ' AND customer_id = ?'
                params.append(customer_id)

            query += ' ORDER BY timestamp DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute(f'PRAGMA table_info({self.TABLE_NAME})')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
