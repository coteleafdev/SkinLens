"""Image Metadata Repository.

이미지 메타데이터 관리를 담당합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from .base import BaseRepository


class ImageMetadataRepository(BaseRepository):
    """이미지 메타데이터 Repository.

    image_metadata 테이블을 담당합니다.
    """

    def record_image_metadata(
        self,
        analysis_id: int,
        image_type: str,
        file_size_bytes: int,
        width: int,
        height: int,
        format: str,
        exif_date_taken: Optional[str] = None,
        exif_device: Optional[str] = None,
        exif_location: Optional[str] = None,
    ) -> None:
        """이미지 메타데이터 기록.

        Args:
            analysis_id: 분석 ID
            image_type: 이미지 유형
            file_size_bytes: 파일 크기
            width: 너비
            height: 높이
            format: 포맷
            exif_date_taken: EXIF 촬영일
            exif_device: EXIF 기기
            exif_location: EXIF 위치
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO image_metadata (
                    analysis_id, image_type, file_size_bytes, width, height, format,
                    exif_date_taken, exif_device, exif_location
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (analysis_id, image_type, file_size_bytes, width, height, format,
                  exif_date_taken, exif_device, exif_location))

            conn.commit()
            log.debug(f"이미지 메타데이터 기록: analysis_id={analysis_id}, image_type={image_type}")
        except Exception as e:
            conn.rollback()
            log.error(f"이미지 메타데이터 기록 실패: {e}")
            raise
        finally:
            conn.close()

    def get_image_metadata(
        self,
        analysis_id: Optional[int] = None,
        image_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """이미지 메타데이터 조회.

        Args:
            analysis_id: 분석 ID
            image_type: 이미지 유형

        Returns:
            메타데이터 레코드 리스트
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = 'SELECT * FROM image_metadata'
            params = []
            conditions = []

            if analysis_id:
                conditions.append('analysis_id = ?')
                params.append(analysis_id)
            if image_type:
                conditions.append('image_type = ?')
                params.append(image_type)

            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)

            query += ' ORDER BY created_at DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute('PRAGMA table_info(image_metadata)')
            columns = [col[1] for col in cursor.fetchall()]

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
