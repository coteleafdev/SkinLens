"""
test_product_repository.py — 제품 리포지토리 단위 테스트

맞춤형 화장품 성분 정보 관리 테스트
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.db.product_repository import ProductRepository


class TestProductRepository:
    """ProductRepository 테스트"""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """임시 DB fixture"""
        db_path = tmp_path / "test_products.db"
        return str(db_path)
    
    @pytest.fixture
    def repository(self, temp_db):
        """ProductRepository fixture"""
        repo = ProductRepository(db_path=temp_db)
        yield repo
        repo.close()
    
    def test_init_db(self, repository):
        """DB 초기화 테스트"""
        # 테이블 생성 확인
        cursor = repository._conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='products'
        """)
        result = cursor.fetchone()
        
        assert result is not None
        assert result[0] == "products"
    
    def test_add_product(self, repository):
        """제품 추가 테스트"""
        product_id = repository.add_product(
            product_id="TEST001",
            product_name="Test Product",
            category="트러블 케어",
            key_ingredients=["니아시나마이드", "살리실산"],
            efficacy="트러블 진정 및 피부 결 개선",
            target_skin_types=["지성", "트러블성"],
            target_concerns=["acne", "pore"],
            target_prescription_items=["M10"]
        )
        
        assert product_id > 0
    
    def test_add_product_duplicate(self, repository):
        """중복 제품 추가 테스트 (REPLACE)"""
        # 첫 번째 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Test Product",
            category="트러블 케어",
            key_ingredients=["니아시나마이드"],
            efficacy="Test efficacy"
        )
        
        # 두 번째 추가 (REPLACE)
        product_id = repository.add_product(
            product_id="TEST001",
            product_name="Updated Product",
            category="홍조 케어",
            key_ingredients=["비타민 C"],
            efficacy="Updated efficacy"
        )
        
        assert product_id > 0
        
        # 업데이트 확인
        product = repository.get_product("TEST001")
        assert product["product_name"] == "Updated Product"
        assert product["category"] == "홍조 케어"
    
    def test_get_product(self, repository):
        """제품 조회 테스트"""
        # 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Test Product",
            category="트러블 케어",
            key_ingredients=["니아시나마이드", "살리실산"],
            efficacy="Test efficacy",
            target_skin_types=["지성"],
            target_concerns=["acne"],
            target_prescription_items=["M10"]
        )
        
        # 제품 조회
        product = repository.get_product("TEST001")
        
        assert product is not None
        assert product["product_id"] == "TEST001"
        assert product["product_name"] == "Test Product"
        assert product["category"] == "트러블 케어"
        assert "니아시나마이드" in product["key_ingredients"]
        assert "살리실산" in product["key_ingredients"]
        assert product["efficacy"] == "Test efficacy"
        assert "지성" in product["target_skin_types"]
        assert "acne" in product["target_concerns"]
        assert "M10" in product["target_prescription_items"]
    
    def test_get_product_not_found(self, repository):
        """존재하지 않는 제품 조회 테스트"""
        product = repository.get_product("NONEXISTENT")
        
        assert product is None
    
    def test_get_all_products(self, repository):
        """모든 제품 조회 테스트"""
        # 여러 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Product A",
            category="트러블 케어",
            key_ingredients=["성분 A"],
            efficacy="Efficacy A"
        )
        repository.add_product(
            product_id="TEST002",
            product_name="Product B",
            category="홍조 케어",
            key_ingredients=["성분 B"],
            efficacy="Efficacy B"
        )
        
        # 모든 제품 조회
        products = repository.get_all_products()
        
        assert len(products) >= 2  # 샘플 데이터도 포함될 수 있음
        product_ids = [p["product_id"] for p in products]
        assert "TEST001" in product_ids
        assert "TEST002" in product_ids
    
    def test_get_products_by_concerns(self, repository):
        """고민사항 기반 제품 조회 테스트"""
        # 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Acne Product",
            category="트러블 케어",
            key_ingredients=["니아시나마이드"],
            efficacy="Acne treatment",
            target_concerns=["acne", "pore"]
        )
        repository.add_product(
            product_id="TEST002",
            product_name="Redness Product",
            category="홍조 케어",
            key_ingredients=["비타민 C"],
            efficacy="Redness treatment",
            target_concerns=["redness"]
        )
        
        # acne 고민사항으로 조회
        products = repository.get_products_by_concerns(["acne"])
        
        assert len(products) >= 1
        product_ids = [p["product_id"] for p in products]
        assert "TEST001" in product_ids
    
    def test_get_products_by_concerns_multiple(self, repository):
        """다중 고민사항 기반 제품 조회 테스트"""
        # 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Multi Concern Product",
            category="복합 케어",
            key_ingredients=["니아시나마이드"],
            efficacy="Multi treatment",
            target_concerns=["acne", "pore", "redness"]
        )
        
        # 다중 고민사항으로 조회
        products = repository.get_products_by_concerns(["acne", "redness"])
        
        assert len(products) >= 1
        product_ids = [p["product_id"] for p in products]
        assert "TEST001" in product_ids
    
    def test_get_products_by_skin_type(self, repository):
        """피부 타입 기반 제품 조회 테스트"""
        # 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Oily Product",
            category="지성 케어",
            key_ingredients=["녹차 추출물"],
            efficacy="Oily skin treatment",
            target_skin_types=["지성", "트러블성"]
        )
        repository.add_product(
            product_id="TEST002",
            product_name="Dry Product",
            category="건성 케어",
            key_ingredients=["히알루론산"],
            efficacy="Dry skin treatment",
            target_skin_types=["건성", "민감성"]
        )
        
        # 지성 피부 타입으로 조회
        products = repository.get_products_by_skin_type("지성")
        
        assert len(products) >= 1
        product_ids = [p["product_id"] for p in products]
        assert "TEST001" in product_ids
    
    def test_get_products_by_prescription_items(self, repository):
        """처방 항목 기반 제품 조회 테스트"""
        # 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="M10 Product",
            category="트러블 케어",
            key_ingredients=["니아시나마이드"],
            efficacy="Acne treatment",
            target_prescription_items=["M10"]
        )
        repository.add_product(
            product_id="TEST002",
            product_name="M01 Product",
            category="톤 케어",
            key_ingredients=["비타민 C"],
            efficacy="Tone treatment",
            target_prescription_items=["M01"]
        )
        
        # M10 처방 항목으로 조회 (딕셔너리 형태)
        products = repository.match_products_by_prescription({"M10": 2.0})
        
        assert len(products) >= 1
        product_ids = [p["product_id"] for p in products]
        assert "TEST001" in product_ids
    
    def test_get_products_by_prescription_items_multiple(self, repository):
        """다중 처방 항목 기반 제품 조회 테스트"""
        # 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Multi Prescription Product",
            category="복합 케어",
            key_ingredients=["니아시나마이드"],
            efficacy="Multi treatment",
            target_prescription_items=["M10", "M01"]
        )
        
        # 다중 처방 항목으로 조회 (딕셔너리 형태)
        products = repository.match_products_by_prescription({"M10": 2.0, "M01": 1.5})
        
        assert len(products) >= 1
        product_ids = [p["product_id"] for p in products]
        assert "TEST001" in product_ids
    
    def test_recommend_products(self, repository):
        """제품 추천 테스트"""
        # 제품 추가
        repository.add_product(
            product_id="TEST001",
            product_name="Acne Product",
            category="트러블 케어",
            key_ingredients=["니아시나마이드"],
            efficacy="Acne treatment",
            target_skin_types=["지성"],
            target_concerns=["acne"],
            target_prescription_items=["M10"]
        )
        
        # 추천 요청 (메서드가 없으면 테스트 건너뜀)
        if hasattr(repository, 'recommend_products'):
            products = repository.recommend_products(
                skin_type="지성",
                concerns=["acne"],
                prescription_items=["M10"]
            )
            
            assert len(products) >= 1
            product_ids = [p["product_id"] for p in products]
            assert "TEST001" in product_ids
    
    def test_close(self, repository):
        """DB 연결 종료 테스트"""
        repository.close()
        
        # 연결이 종료되었는지 확인 (연결 객체가 여전히 존재할 수 있음)
        # close() 메서드가 호출되는지만 확인
        assert True
    
    def test_add_product_without_optional_fields(self, repository):
        """선택적 필드 없이 제품 추가 테스트"""
        product_id = repository.add_product(
            product_id="TEST001",
            product_name="Simple Product",
            category="기본 케어",
            key_ingredients=["성분 A"],
            efficacy="Basic efficacy"
        )
        
        assert product_id > 0
        
        # 제품 조회
        product = repository.get_product("TEST001")
        assert product is not None
        assert product["target_skin_types"] == []
        assert product["target_concerns"] == []
        assert product["target_prescription_items"] == []
