"""
test_mobile_integration.py — 모바일 앱 통합 테스트

모바일 앱 클라이언트 시뮬레이터를 사용하여 실제 모바일 앱 워크플로우를 테스트합니다.
"""
import pytest
from pathlib import Path
from tests.mobile.mobile_client_simulator import MobileAppSimulator


class TestMobileIntegration:
    """모바일 앱 통합 테스트"""
    
    @pytest.fixture
    def mobile_app(self, auth_client):
        """모바일 앱 시뮬레이터 fixture"""
        return MobileAppSimulator(auth_client)
    
    @pytest.fixture
    def logged_in_mobile_app(self, mobile_app):
        """로그인된 모바일 앱 fixture"""
        mobile_app.login("admin", "a")
        return mobile_app
    
    def test_mobile_login(self, mobile_app):
        """모바일 앱 로그인 테스트"""
        success = mobile_app.login("admin", "a")
        assert success, "로그인 실패"
        assert mobile_app.access_token is not None, "토큰 없음"
        assert mobile_app.customer_id == "admin", "고객 ID 불일치"
    
    def test_survey_data_creation(self, mobile_app):
        """설문 데이터 생성 테스트"""
        survey_data = mobile_app.create_survey_data(
            gender="female",
            age_group="30s",
            skin_types=["oily", "sensitive"],
            skin_concerns=["acne", "pores"]
        )
        
        assert survey_data["consent_agreed"] is True
        assert survey_data["gender"] == "female"
        assert survey_data["age_group"] == "30s"
        assert "oily" in survey_data["skin_types"]
        assert "acne" in survey_data["skin_concerns"]
    
    def test_mobile_analysis_workflow_without_image(self, logged_in_mobile_app):
        """이미지 없는 분석 워크플로우 테스트 (이미지 파일이 없으면 스킵)"""
        # 테스트 이미지 파일 확인
        test_image = Path("tests/fixtures/test_image.jpg")
        if not test_image.exists():
            pytest.skip("테스트 이미지 파일 없음")
        
        result = logged_in_mobile_app.complete_analysis_workflow(str(test_image))
        assert result is not None, "분석 실패"
    
    def test_get_my_analyses(self, logged_in_mobile_app):
        """내 분석 결과 목록 조회 테스트"""
        analyses = logged_in_mobile_app.get_my_analyses()
        # 분석 결과가 없어도 테스트 통과 (빈 리스트 또는 딕셔너리 반환)
        assert analyses is not None, "분석 목록 조회 실패"
        # 응답 형식이 리스트 또는 딕셔너리일 수 있음
        assert isinstance(analyses, (list, dict)), "분석 목록 형식 오류"
    
    def test_get_my_trends(self, logged_in_mobile_app):
        """내 피부 추이 조회 테스트"""
        trends = logged_in_mobile_app.get_my_trends()
        # 추이 데이터가 없어도 테스트 통과
        assert trends is not None, "추이 조회 실패"
    
    def test_mobile_app_full_workflow_simulation(self, logged_in_mobile_app):
        """모바일 앱 전체 워크플로우 시뮬레이션 테스트"""
        # 1. 로그인 확인
        assert logged_in_mobile_app.access_token is not None
        
        # 2. 설문 데이터 생성
        survey_data = logged_in_mobile_app.create_survey_data()
        assert survey_data is not None
        
        # 3. 내 분석 결과 조회 (빈 상태)
        analyses = logged_in_mobile_app.get_my_analyses()
        assert analyses is not None
        
        # 4. 내 추이 조회
        trends = logged_in_mobile_app.get_my_trends()
        assert trends is not None
        
        print("모바일 앱 워크플로우 시뮬레이션 완료")
    
    def test_mobile_app_different_user_scenarios(self, mobile_app):
        """다양한 사용자 시나리오 테스트"""
        # 관리자 로그인
        mobile_app.login("admin", "a")
        assert mobile_app.access_token is not None
        assert mobile_app.role == "admin"
        
        # 분석가 로그인
        mobile_app.login("analyst", "a")
        assert mobile_app.access_token is not None
        assert mobile_app.role == "analyst"
        
        # 고객 로그인
        mobile_app.login("customer", "c")
        assert mobile_app.access_token is not None
        assert mobile_app.role == "customer"
    
    def test_mobile_app_survey_variations(self, logged_in_mobile_app):
        """다양한 설문 데이터 조합 테스트"""
        # 20대 여성, 지성, 여드름
        survey1 = logged_in_mobile_app.create_survey_data(
            gender="female",
            age_group="20s",
            skin_types=["oily"],
            skin_concerns=["acne"]
        )
        assert survey1["age_group"] == "20s"
        
        # 40대 남성, 건성, 주름
        survey2 = logged_in_mobile_app.create_survey_data(
            gender="male",
            age_group="40s",
            skin_types=["dry"],
            skin_concerns=["wrinkles", "elasticity"]
        )
        assert survey2["gender"] == "male"
        assert "wrinkles" in survey2["skin_concerns"]
        
        # 30대, 복합성, 색소침착
        survey3 = logged_in_mobile_app.create_survey_data(
            gender="female",
            age_group="30s",
            skin_types=["combination"],
            skin_concerns=["pigmentation", "dullness"]
        )
        assert "pigmentation" in survey3["skin_concerns"]
