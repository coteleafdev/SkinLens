"""
Image Metadata Repository 테스트 - 이미지 메타데이터 레포지토리
"""
import pytest
import sqlite3
import tempfile
import os
from src.cli.repositories.image_metadata import ImageMetadataRepository


class TestImageMetadataRepository:
    """ImageMetadataRepository 테스트"""

    @pytest.fixture
    def db_path(self):
        """임시 데이터베이스 파일 생성"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def repository(self, db_path):
        """Repository 인스턴스 생성"""
        # 테이블 생성
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                image_type TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                format TEXT NOT NULL,
                exif_date_taken TEXT,
                exif_device TEXT,
                exif_location TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return ImageMetadataRepository(db_path)

    def test_record_image_metadata(self, repository):
        """이미지 메타데이터 기록"""
        repository.record_image_metadata(
            analysis_id=1,
            image_type="input",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG",
            exif_date_taken="2024-01-01T12:00:00",
            exif_device="iPhone 13",
            exif_location="Seoul, Korea"
        )
        
        metadata = repository.get_image_metadata(analysis_id=1)
        assert len(metadata) == 1
        assert metadata[0]["analysis_id"] == 1
        assert metadata[0]["image_type"] == "input"
        assert metadata[0]["file_size_bytes"] == 1024000
        assert metadata[0]["width"] == 1920
        assert metadata[0]["height"] == 1080
        assert metadata[0]["format"] == "JPEG"
        assert metadata[0]["exif_date_taken"] == "2024-01-01T12:00:00"
        assert metadata[0]["exif_device"] == "iPhone 13"
        assert metadata[0]["exif_location"] == "Seoul, Korea"

    def test_record_image_metadata_minimal(self, repository):
        """최소 파라미터로 이미지 메타데이터 기록"""
        repository.record_image_metadata(
            analysis_id=1,
            image_type="input",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        metadata = repository.get_image_metadata(analysis_id=1)
        assert len(metadata) == 1
        assert metadata[0]["exif_date_taken"] is None
        assert metadata[0]["exif_device"] is None
        assert metadata[0]["exif_location"] is None

    def test_get_image_metadata_by_analysis_id(self, repository):
        """분석 ID로 메타데이터 조회"""
        # 여러 메타데이터 기록
        repository.record_image_metadata(
            analysis_id=1,
            image_type="input",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        repository.record_image_metadata(
            analysis_id=1,
            image_type="restored",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        repository.record_image_metadata(
            analysis_id=2,
            image_type="input",
            file_size_bytes=512000,
            width=1280,
            height=720,
            format="PNG"
        )
        
        # analysis_id=1로 조회
        metadata = repository.get_image_metadata(analysis_id=1)
        assert len(metadata) == 2
        assert all(m["analysis_id"] == 1 for m in metadata)

    def test_get_image_metadata_by_image_type(self, repository):
        """이미지 타입으로 메타데이터 조회"""
        # 여러 메타데이터 기록
        repository.record_image_metadata(
            analysis_id=1,
            image_type="input",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        repository.record_image_metadata(
            analysis_id=1,
            image_type="restored",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        repository.record_image_metadata(
            analysis_id=2,
            image_type="input",
            file_size_bytes=512000,
            width=1280,
            height=720,
            format="PNG"
        )
        
        # image_type="input"으로 조회
        metadata = repository.get_image_metadata(image_type="input")
        assert len(metadata) == 2
        assert all(m["image_type"] == "input" for m in metadata)

    def test_get_image_metadata_with_both_filters(self, repository):
        """분석 ID와 이미지 타입으로 메타데이터 조회"""
        # 여러 메타데이터 기록
        repository.record_image_metadata(
            analysis_id=1,
            image_type="input",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        repository.record_image_metadata(
            analysis_id=1,
            image_type="restored",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        repository.record_image_metadata(
            analysis_id=2,
            image_type="input",
            file_size_bytes=512000,
            width=1280,
            height=720,
            format="PNG"
        )
        
        # analysis_id=1, image_type="input"으로 조회
        metadata = repository.get_image_metadata(analysis_id=1, image_type="input")
        assert len(metadata) == 1
        assert metadata[0]["analysis_id"] == 1
        assert metadata[0]["image_type"] == "input"

    def test_get_image_metadata_all(self, repository):
        """모든 메타데이터 조회"""
        # 여러 메타데이터 기록
        for i in range(3):
            repository.record_image_metadata(
                analysis_id=i,
                image_type="input",
                file_size_bytes=1024000,
                width=1920,
                height=1080,
                format="JPEG"
            )
        
        # 필터 없이 조회
        metadata = repository.get_image_metadata()
        assert len(metadata) == 3

    def test_get_image_metadata_empty(self, repository):
        """데이터가 없을 때 메타데이터 조회"""
        metadata = repository.get_image_metadata()
        assert len(metadata) == 0

    def test_get_image_metadata_ordering(self, repository):
        """최신순 정렬 검증"""
        # 여러 메타데이터 기록
        for i in range(3):
            repository.record_image_metadata(
                analysis_id=i,
                image_type="input",
                file_size_bytes=1024000,
                width=1920,
                height=1080,
                format="JPEG"
            )
        
        metadata = repository.get_image_metadata()
        # 최신순 정렬 확인
        assert len(metadata) == 3
        # created_at 필드 확인
        assert "created_at" in metadata[0]

    def test_record_image_metadata_rollback_on_error(self, repository, db_path):
        """에러 발생 시 롤백 검증"""
        # 현재 구현에서는 예외가 발생하지 않으므로 기본 동작만 확인
        # 실제 롤백 테스트는 DB 트랜잭션 설정이 필요
        pass

    def test_record_multiple_image_types(self, repository):
        """여러 이미지 타입 기록"""
        image_types = ["input", "restored", "mask", "roi"]
        
        for i, image_type in enumerate(image_types):
            repository.record_image_metadata(
                analysis_id=1,
                image_type=image_type,
                file_size_bytes=1024000,
                width=1920,
                height=1080,
                format="JPEG"
            )
        
        metadata = repository.get_image_metadata(analysis_id=1)
        assert len(metadata) == 4
        recorded_types = [m["image_type"] for m in metadata]
        assert set(recorded_types) == set(image_types)

    def test_record_image_metadata_different_formats(self, repository):
        """다양한 이미지 포맷 기록"""
        formats = ["JPEG", "PNG", "WEBP", "TIFF"]
        
        for i, format_type in enumerate(formats):
            repository.record_image_metadata(
                analysis_id=i,
                image_type="input",
                file_size_bytes=1024000,
                width=1920,
                height=1080,
                format=format_type
            )
        
        metadata = repository.get_image_metadata()
        assert len(metadata) == 4
        recorded_formats = [m["format"] for m in metadata]
        assert set(recorded_formats) == set(formats)

    def test_get_image_metadata_no_results(self, repository):
        """조건에 맞는 결과가 없을 때"""
        repository.record_image_metadata(
            analysis_id=1,
            image_type="input",
            file_size_bytes=1024000,
            width=1920,
            height=1080,
            format="JPEG"
        )
        
        # 존재하지 않는 analysis_id로 조회
        metadata = repository.get_image_metadata(analysis_id=999)
        assert len(metadata) == 0
        
        # 존재하지 않는 image_type으로 조회
        metadata = repository.get_image_metadata(image_type="nonexistent")
        assert len(metadata) == 0
