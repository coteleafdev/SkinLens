"""Base Repository 추상 클래스.

모든 Repository의 기본 기능을 제공합니다.
"""
from __future__ import annotations

import logging
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class BaseRepository(ABC):
    """Repository 기본 클래스.

    DB 연결 관리, 기본 CRUD, 트랜잭션 관리를 제공합니다.
    """

    def __init__(self, db_path: str):
        """Repository 초기화.

        Args:
            db_path: SQLite DB 파일 경로
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """DB 연결 가져오기.

        Returns:
            SQLite 연결
        """
        return sqlite3.connect(self.db_path)

    def _execute_query(
        self,
        query: str,
        params: Tuple = (),
        fetch: bool = False,
        commit: bool = True,
    ) -> Optional[List[Tuple]]:
        """쿼리 실행 헬퍼.

        Args:
            query: SQL 쿼리
            params: 쿼리 파라미터
            fetch: 결과 반환 여부
            commit: 커밋 여부

        Returns:
            fetch=True인 경우 결과 리스트, 아니면 None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if commit:
                conn.commit()
            if fetch:
                return cursor.fetchall()
            return None
        except Exception as e:
            if commit:
                conn.rollback()
            log.error(f"쿼리 실행 실패: {e}")
            raise
        finally:
            conn.close()

    def _execute_many(
        self,
        query: str,
        params_list: List[Tuple],
        commit: bool = True,
    ) -> None:
        """다중 쿼리 실행 헬퍼.

        Args:
            query: SQL 쿼리
            params_list: 파라미터 리스트
            commit: 커밋 여부
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.executemany(query, params_list)
            if commit:
                conn.commit()
        except Exception as e:
            if commit:
                conn.rollback()
            log.error(f"다중 쿼리 실행 실패: {e}")
            raise
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """트랜잭션 컨텍스트 매니저.

        사용 예:
            with repo.transaction():
                repo.insert(data1)
                repo.insert(data2)

        Yields:
            커서 객체
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN")
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.error(f"트랜잭션 실패: {e}")
            raise
        finally:
            conn.close()

    def _dict_from_row(self, row: Tuple, columns: List[str]) -> Dict[str, Any]:
        """행 튜플을 딕셔너리로 변환.

        Args:
            row: 행 튜플
            columns: 컬럼 이름 리스트

        Returns:
            딕셔너리
        """
        return dict(zip(columns, row))
