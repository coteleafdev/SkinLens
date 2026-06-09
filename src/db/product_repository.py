# -*- coding: utf-8 -*-
"""
맞춤형 화장품 성분 정보를 관리하는 Repository 모듈.

이 모듈은 ProductTable에서 제품 정보를 조회하고,
피부 고민사항, 피부 타입, 측정 점수를 기반으로
맞춤형 화장품을 추천하는 기능을 제공합니다.
"""
import logging
import sqlite3
import json
from typing import Optional, List, Dict, Any
from pathlib import Path

log = logging.getLogger(__name__)


class ProductRepository:
    """맞춤형 화장품 성분 정보를 관리하는 Repository 클래스"""

    def __init__(self, db_path: str = "results/skin_analysis.db"):
        """
        ProductRepository 초기화.

        Parameters
        ----------
        db_path : str
            DB 파일 경로 (기본값: results/skin_analysis.db)
        """
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_db()

    def close(self):
        """DB 연결 종료"""
        if self._conn:
            self._conn.close()

    def _init_db(self):
        """DB 테이블 생성 및 초기 데이터 로드"""
        cursor = self._conn.cursor()

        # products 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                key_ingredients TEXT NOT NULL,
                efficacy TEXT NOT NULL,
                target_skin_types TEXT,
                target_concerns TEXT,
                target_prescription_items TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 기존 테이블에 target_prescription_items 컬럼이 없으면 추가 (마이그레이션)
        try:
            cursor.execute("ALTER TABLE products ADD COLUMN target_prescription_items TEXT")
            self._conn.commit()
            log.info("[마이그레이션] target_prescription_items 컬럼 추가 완료")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                log.info("[마이그레이션] target_prescription_items 컬럼 이미 존재")
            else:
                log.warning(f"[마이그레이션] 컬럼 추가 실패: {e}")

        # 샘플 제품 데이터 로드 (테이블이 비어있는 경우만)
        cursor.execute("SELECT COUNT(*) FROM products")
        product_count = cursor.fetchone()[0]
        if product_count == 0:
            self._load_sample_products(cursor)
            self._conn.commit()

        self._conn.commit()

    # ── 제품 CRUD ─────────────────────────────────────────────────────────────

    def add_product(
        self,
        product_id: str,
        product_name: str,
        category: str,
        key_ingredients: List[str],
        efficacy: str,
        target_skin_types: Optional[List[str]] = None,
        target_concerns: Optional[List[str]] = None,
        target_prescription_items: Optional[List[str]] = None,
    ) -> int:
        """
        제품 정보 추가.

        Parameters
        ----------
        product_id : str
            제품 ID (고유 식별자)
        product_name : str
            제품명
        category : str
            제품 카테고리 (예: 트러블 케어, 홍조 케어)
        key_ingredients : List[str]
            주요 성분 목록
        efficacy : str
            효능 설명
        target_skin_types : List[str], optional
            적용 가능한 피부 타입 목록
        target_concerns : List[str], optional
            타겟 피부 고민사항 목록
        target_prescription_items : List[str], optional
            타겟 처방 항목 목록 (예: ["A01", "A06"])

        Returns
        -------
        int
            추가된 제품의 ID
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO products
            (product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns, target_prescription_items, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            product_id,
            product_name,
            category,
            json.dumps(key_ingredients, ensure_ascii=False),
            efficacy,
            json.dumps(target_skin_types or [], ensure_ascii=False),
            json.dumps(target_concerns or [], ensure_ascii=False),
            json.dumps(target_prescription_items or [], ensure_ascii=False),
        ))
        self._conn.commit()
        return cursor.lastrowid

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        제품 ID로 제품 정보 조회.

        Parameters
        ----------
        product_id : str
            제품 ID

        Returns
        -------
        Dict[str, Any] or None
            제품 정보 (존재하지 않으면 None)
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns, target_prescription_items
            FROM products WHERE product_id = ?
        """, (product_id,))
        row = cursor.fetchone()
        if row:
            return {
                "product_id": row[0],
                "product_name": row[1],
                "category": row[2],
                "key_ingredients": json.loads(row[3]),
                "efficacy": row[4],
                "target_skin_types": json.loads(row[5]),
                "target_concerns": json.loads(row[6]),
                "target_prescription_items": json.loads(row[7]) if row[7] else [],
            }
        return None

    def get_all_products(self) -> List[Dict[str, Any]]:
        """
        모든 제품 정보 조회.

        Returns
        -------
        List[Dict[str, Any]]
            제품 정보 목록
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns, target_prescription_items
            FROM products ORDER BY product_name
        """)
        rows = cursor.fetchall()
        return [
            {
                "product_id": row[0],
                "product_name": row[1],
                "category": row[2],
                "key_ingredients": json.loads(row[3]),
                "efficacy": row[4],
                "target_skin_types": json.loads(row[5]),
                "target_concerns": json.loads(row[6]),
                "target_prescription_items": json.loads(row[7]) if row[7] else [],
            }
            for row in rows
        ]

    # ── 제품 매칭 ─────────────────────────────────────────────────────────────

    def get_products_by_concerns(self, concerns: List[str]) -> List[Dict[str, Any]]:
        """
        피부 고민사항 기반 제품 조회.

        Parameters
        ----------
        concerns : List[str]
            피부 고민사항 목록 (예: ["트러블", "홍조"])

        Returns
        -------
        List[Dict[str, Any]]
            매칭된 제품 목록
        """
        cursor = self._conn.cursor()
        matched_products = []
        
        for concern in concerns:
            cursor.execute("""
                SELECT product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns
                FROM products WHERE target_concerns LIKE ?
            """, (f"%{concern}%",))
            rows = cursor.fetchall()
            for row in rows:
                product = {
                    "product_id": row[0],
                    "product_name": row[1],
                    "category": row[2],
                    "key_ingredients": json.loads(row[3]),
                    "efficacy": row[4],
                    "target_skin_types": json.loads(row[5]),
                    "target_concerns": json.loads(row[6]),
                }
                if product not in matched_products:
                    matched_products.append(product)
        
        return matched_products

    def get_products_by_skin_type(self, skin_type: str) -> List[Dict[str, Any]]:
        """
        피부 타입 기반 제품 조회.

        Parameters
        ----------
        skin_type : str
            피부 타입 (예: "combination", "sensitive")

        Returns
        -------
        List[Dict[str, Any]]
            매칭된 제품 목록
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns
            FROM products WHERE target_skin_types LIKE ?
        """, (f"%{skin_type}%",))
        rows = cursor.fetchall()
        return [
            {
                "product_id": row[0],
                "product_name": row[1],
                "category": row[2],
                "key_ingredients": json.loads(row[3]),
                "efficacy": row[4],
                "target_skin_types": json.loads(row[5]),
                "target_concerns": json.loads(row[6]),
            }
            for row in rows
        ]

    def match_products(
        self,
        concerns: List[str],
        skin_type: Optional[str] = None,
        scores: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        고민사항, 피부 타입, 점수 기반 제품 매칭.

        Parameters
        ----------
        concerns : List[str]
            피부 고민사항 목록
        skin_type : str, optional
            피부 타입
        scores : Dict[str, float], optional
            측정 점수 (예: {"acne_score": 50, "redness_score": 67})

        Returns
        -------
        List[Dict[str, Any]]
            매칭된 제품 목록 (match_score 포함)
        """
        all_products = self.get_all_products()
        matched_products = []
        
        for product in all_products:
            match_score = 0.0
            match_reasons = []
            
            # 고민사항 매칭
            product_concerns = product.get("target_concerns", [])
            for concern in concerns:
                if concern in product_concerns:
                    match_score += 0.5
                    match_reasons.append(f"고민사항 매칭: {concern}")
            
            # 피부 타입 매칭
            if skin_type:
                product_skin_types = product.get("target_skin_types", [])
                if skin_type in product_skin_types:
                    match_score += 0.3
                    match_reasons.append(f"피부 타입 매칭: {skin_type}")
            
            # 점수 기반 매칭
            if scores:
                for metric, value in scores.items():
                    # 점수가 낮을수록 문제가 심각하므로, 낮은 점수에 해당하는 고민사항과 매칭
                    if value < 60:
                        metric_concern_map = {
                            "acne_score": "트러블",
                            "redness_score": "홍조",
                            "melasma_score": "색소침착",
                            "pore_size_score": "모공",
                            "wrinkle_score": "주름",
                        }
                        concern = metric_concern_map.get(metric)
                        if concern and concern in product_concerns:
                            match_score += 0.2
                            match_reasons.append(f"점수 기반 매칭: {metric}={value}")
            
            if match_score > 0:
                product["match_score"] = min(match_score, 1.0)
                product["match_reason"] = ", ".join(match_reasons)
                matched_products.append(product)
        
        # match_score 기반 정렬
        matched_products.sort(key=lambda x: x["match_score"], reverse=True)

        return matched_products

    def match_products_by_prescription(
        self,
        prescription_recipe: Dict[str, float],
        max_products: int = 5,
        concerns: Optional[List[str]] = None,
        skin_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        처방전 기반 제품 매칭 (설문 응답도 참조).

        Parameters
        ----------
        prescription_recipe : Dict[str, Any]
            처방전. 신 형식 {"M01": {"percentage": 2.5, "name": "톤&밝기"}} 또는
            구 형식 {"M01": 2.5} 모두 지원.
        max_products : int, optional
            최대 반환 제품 수 (기본값: 5)
        concerns : List[str], optional
            피부 고민사항 목록 (설문 응답)
        skin_type : str, optional
            피부 타입 (설문 응답)

        Returns
        -------
        List[Dict[str, Any]]
            매칭된 제품 목록 (match_score 포함)
        """
        # config.json에서 가중치 로드
        try:
            from src.scoring.skin_scoring import _load_scoring_config
            config = _load_scoring_config()
            product_config = config.get("product_recommendation", {})
            matching_weights = product_config.get("matching_weights", {})
            weights_with_concerns = matching_weights.get("with_concerns", {"prescription": 0.5, "concerns": 0.3, "skin_type": 0.2})
            weights_without_concerns = matching_weights.get("without_concerns", {"prescription": 0.7, "skin_type": 0.3})
        except Exception as e:
            log.warning(f"[경고] config.json 로드 실패, 기본 가중치 사용: {e}")
            weights_with_concerns = {"prescription": 0.5, "concerns": 0.3, "skin_type": 0.2}
            weights_without_concerns = {"prescription": 0.7, "skin_type": 0.3}
        
        all_products = self.get_all_products()
        matched_products = []
        
        for product in all_products:
            match_score = 0.0
            match_reasons = []
            
            # 설문 응답 여부에 따른 가중치 선택
            if concerns:
                weights = weights_with_concerns
            else:
                weights = weights_without_concerns
            
            # 처방 항목 매칭
            product_prescription_items = product.get("target_prescription_items", [])
            for mix_code, mix_data in prescription_recipe.items():
                if mix_code in product_prescription_items:
                    # [REFACTOR 2026-06-08] 처방전 신 형식 {"percentage":.., "name":..} 와
                    # 구 형식(숫자) 모두 지원. 숫자 비율만 추출.
                    percentage = mix_data.get("percentage", 0) if isinstance(mix_data, dict) else mix_data
                    # 처방 비율이 높을수록 매칭 점수 증가
                    match_score += (percentage / 3.0) * weights["prescription"]
                    match_reasons.append(f"처방 항목 매칭: {mix_code} ({percentage}%)")
            
            # 설문 응답: 고민사항 매칭
            if concerns and "concerns" in weights:
                product_concerns = product.get("target_concerns", [])
                for concern in concerns:
                    if concern in product_concerns:
                        match_score += weights["concerns"]
                        match_reasons.append(f"고민사항 매칭: {concern}")
            
            # 설문 응답: 피부 타입 매칭
            if skin_type and "skin_type" in weights:
                product_skin_types = product.get("target_skin_types", [])
                if skin_type in product_skin_types:
                    match_score += weights["skin_type"]
                    match_reasons.append(f"피부 타입 매칭: {skin_type}")
            
            if match_score > 0:
                product["match_score"] = min(match_score, 1.0)
                product["match_reason"] = ", ".join(match_reasons)
                matched_products.append(product)
        
        # match_score 기반 정렬
        matched_products.sort(key=lambda x: x["match_score"], reverse=True)
        
        # 최대 제품 수 제한
        return matched_products[:max_products]

    def _load_sample_products(self, cursor) -> None:
        """샘플 제품 데이터 로드"""
        sample_products = [
            {
                "product_id": "P001",
                "product_name": "꼬드리브 트러블 케어 세럼",
                "category": "트러블 케어",
                "key_ingredients": ["나이아신아마이드", "살리실산", "티트리 오일"],
                "efficacy": "트러블 억제, 모공 관리, 피부 진정",
                "target_skin_types": ["oily", "combination", "acne_prone"],
                "target_concerns": ["트러블", "모공"],
                "target_prescription_items": ["M10"],  # 트러블
            },
            {
                "product_id": "P002",
                "product_name": "꼬드리브 레드니스 케어 크림",
                "category": "홍조 케어",
                "key_ingredients": ["병풀 추출물", "판테놀", "알로에 베라"],
                "efficacy": "홍조 완화, 피부 진정, 장벽 강화",
                "target_skin_types": ["sensitive", "combination", "dry"],
                "target_concerns": ["홍조", "민감성", "붉은기"],
                "target_prescription_items": ["M06"],  # 홍조
            },
            {
                "product_id": "P003",
                "product_name": "꼬드리브 브라이트닝 앰플",
                "category": "색소 케어",
                "key_ingredients": ["비타민 C", "글루타치온", "나이아신아마이드"],
                "efficacy": "색소 침착 개선, 피부 톤 밝기",
                "target_skin_types": ["all", "combination", "dry"],
                "target_concerns": ["색소침착", "기미", "주근깨", "칙칙함"],
                "target_prescription_items": ["M01", "M05"],  # 광채, 색소침착
            },
            {
                "product_id": "P004",
                "product_name": "꼬드리브 안티에이징 크림",
                "category": "주름 케어",
                "key_ingredients": ["레티놀", "펩타이드", "히알루론산"],
                "efficacy": "주름 개선, 탄력 증진, 보습",
                "target_skin_types": ["mature", "dry", "combination"],
                "target_concerns": ["주름", "탄력", "건조"],
                "target_prescription_items": ["M02"],  # 주름
            },
            {
                "product_id": "P005",
                "product_name": "꼬드리브 모공 토너",
                "category": "모공 케어",
                "key_ingredients": ["BHA", "AHA", "하이드로진산"],
                "efficacy": "모공 축소, 각질 제거, 피부결 개선",
                "target_skin_types": ["oily", "combination"],
                "target_concerns": ["모공", "거칠기", "블랙헤드"],
                "target_prescription_items": ["M07"],  # 모공
            },
        ]

        for product_data in sample_products:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO products
                    (product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns, target_prescription_items)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_data["product_id"],
                    product_data["product_name"],
                    product_data["category"],
                    json.dumps(product_data["key_ingredients"], ensure_ascii=False),
                    product_data["efficacy"],
                    json.dumps(product_data["target_skin_types"], ensure_ascii=False),
                    json.dumps(product_data["target_concerns"], ensure_ascii=False),
                    json.dumps(product_data["target_prescription_items"], ensure_ascii=False),
                ))
                log.info(f"샘플 제품 로드 완료: {product_data['product_name']}")
            except Exception as e:
                log.warning(f"샘플 제품 로드 실패: {product_data['product_name']} - {e}")


# ── 초기 데이터 로드 ───────────────────────────────────────────────────────────

def load_sample_products(repo: ProductRepository) -> None:
    """
    샘플 제품 데이터 로드.

    Parameters
    ----------
    repo : ProductRepository
        ProductRepository 인스턴스
    """
    sample_products = [
        {
            "product_id": "P001",
            "product_name": "CÔTELEAF 트러블 케어 세럼",
            "category": "트러블 케어",
            "key_ingredients": ["나이아신아마이드", "살리실산", "티트리 오일"],
            "efficacy": "트러블 억제, 모공 관리, 피부 진정",
            "target_skin_types": ["oily", "combination", "acne_prone"],
            "target_concerns": ["트러블", "모공"],
            "target_prescription_items": ["M10"],  # 트러블
        },
        {
            "product_id": "P002",
            "product_name": "CÔTELEAF 레드니스 케어 크림",
            "category": "홍조 케어",
            "key_ingredients": ["병풀 추출물", "판테놀", "알로에 베라"],
            "efficacy": "홍조 완화, 피부 진정, 장벽 강화",
            "target_skin_types": ["sensitive", "combination", "dry"],
            "target_concerns": ["홍조", "민감성", "붉은기"],
            "target_prescription_items": ["M07"],  # 홍조
        },
        {
            "product_id": "P003",
            "product_name": "CÔTELEAF 브라이트닝 앰플",
            "category": "색소 케어",
            "key_ingredients": ["비타민 C", "글루타치온", "나이아신아마이드"],
            "efficacy": "색소 침착 개선, 피부 톤 밝기",
            "target_skin_types": ["all", "combination", "dry"],
            "target_concerns": ["색소침착", "기미", "주근깨", "칙칙함"],
            "target_prescription_items": ["M01", "M06"],  # 광채, 색소침착
        },
        {
            "product_id": "P004",
            "product_name": "CÔTELEAF 안티에이징 크림",
            "category": "주름 케어",
            "key_ingredients": ["레티놀", "펩타이드", "히알루론산"],
            "efficacy": "주름 개선, 탄력 증진, 보습",
            "target_skin_types": ["mature", "dry", "combination"],
            "target_concerns": ["주름", "탄력", "건조"],
            "target_prescription_items": ["M02", "M05"],  # 주름, 탄력
        },
        {
            "product_id": "P005",
            "product_name": "CÔTELEAF 모공 토너",
            "category": "모공 케어",
            "key_ingredients": ["BHA", "AHA", "하이드로진산"],
            "efficacy": "모공 축소, 각질 제거, 피부결 개선",
            "target_skin_types": ["oily", "combination"],
            "target_concerns": ["모공", "거칠기", "블랙헤드"],
            "target_prescription_items": ["M07"],  # 모공
        },
    ]
    
    for product_data in sample_products:
        try:
            repo.add_product(**product_data)
            log.info(f"제품 로드 완료: {product_data['product_name']}")
        except Exception as e:
            log.warning(f"제품 로드 실패: {product_data['product_name']} - {e}")


if __name__ == "__main__":
    # 테스트용: 샘플 데이터 로드
    repo = ProductRepository()
    load_sample_products(repo)
    
    # 테스트: 제품 매칭
    matched = repo.match_products(
        concerns=["트러블", "홍조"],
        skin_type="combination",
        scores={"acne_score": 50, "redness_score": 67}
    )
    
    log.info("=== 매칭된 제품 ===")
    for product in matched:
        log.info("%s (매칭 점수: %.1f)", product['product_name'], product['match_score'])
        log.info("  카테고리: %s", product['category'])
        log.info("  주요 성분: %s", ', '.join(product['key_ingredients']))
        log.info("  효능: %s", product['efficacy'])
        log.info("  매칭 사유: %s", product['match_reason'])
    
    repo.close()
