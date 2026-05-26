"""Customer Data Repository.

고객 데이터 관리 (GDPR 준수)를 담당합니다.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

log = logging.getLogger(__name__)

from .base import BaseRepository


class CustomerDataRepository(BaseRepository):
    """고객 데이터 Repository.

    GDPR 준수를 위한 고객 데이터 삭제/내보내기를 담당합니다.
    """

    def delete_customer_data(self, customer_id: str) -> int:
        """고객 데이터 삭제 (GDPR 준수).

        Args:
            customer_id: 고객 ID

        Returns:
            삭제된 총 레코드 수
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        total_deleted = 0

        # 각 테이블에서 고객 데이터 삭제
        tables = [
            ('analysis_stats', 'customer_id'),
            ('score_trends', 'customer_id'),
            ('llm_api_stats', 'customer_id'),
            ('error_analysis', 'customer_id'),
        ]

        try:
            for table, column in tables:
                cursor.execute(f'DELETE FROM {table} WHERE {column} = ?', (customer_id,))
                total_deleted += cursor.rowcount

            # executions 테이블에서는 직접 customer_id가 없으므로 건너뜀
            # 필요시 별도 매핑 테이블을 만들어야 함

            conn.commit()
            log.info(f"고객 데이터 삭제 완료: {customer_id}, {total_deleted}개 레코드")
            return total_deleted
        except Exception as e:
            conn.rollback()
            log.error(f"고객 데이터 삭제 실패: {customer_id}, {e}")
            raise
        finally:
            conn.close()

    def export_customer_data(
        self,
        customer_id: str,
        output_path: str,
        analysis_stats_data: Optional[list] = None,
        score_trends_data: Optional[list] = None,
        llm_api_stats_data: Optional[list] = None,
        errors_data: Optional[list] = None,
        audit_logs_data: Optional[list] = None,
    ) -> int:
        """고객 데이터 내보내기 (JSON).

        참고: 이 메서드는 다른 Repository의 데이터를 받아서 처리합니다.
        Repository 간 순환 의존을 피하기 위해 데이터를 파라미터로 받습니다.

        Args:
            customer_id: 고객 ID
            output_path: 출력 파일 경로
            analysis_stats_data: 분석 통계 데이터 (AnalysisStatsRepository에서 가져옴)
            score_trends_data: 점수 트렌드 데이터 (AnalysisStatsRepository에서 가져옴)
            llm_api_stats_data: LLM API 통계 데이터 (LLMAPIRepository에서 가져옴)
            errors_data: 에러 데이터 (ErrorAuditRepository에서 가져옴)
            audit_logs_data: 감사 로그 데이터 (ErrorAuditRepository에서 가져옴)

        Returns:
            내보낸 총 레코드 수
        """
        import json
        from datetime import datetime

        data = {
            "customer_id": customer_id,
            "exported_at": datetime.now().isoformat(),
            "analysis_stats": analysis_stats_data or [],
            "score_trends": score_trends_data or [],
            "llm_api_stats": llm_api_stats_data or [],
            "errors": errors_data or [],
            "audit_logs": audit_logs_data or [],
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        total_records = (
            len(data["analysis_stats"]) +
            len(data["score_trends"]) +
            len(data["llm_api_stats"]) +
            len(data["errors"]) +
            len(data["audit_logs"])
        )

        log.info(f"고객 데이터 내보내기 완료: {customer_id}, {total_records}개 레코드 -> {output_path}")
        return total_records
