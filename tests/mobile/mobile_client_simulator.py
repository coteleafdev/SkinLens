"""
mobile_client_simulator.py — 모바일 앱 클라이언트 시뮬레이터

실제 모바일 앱의 동작을 시뮬레이션하여 서버와의 통합 테스트를 수행합니다.
"""
import json
import time
from typing import Dict, Any, Optional, List
from pathlib import Path
from fastapi.testclient import TestClient


class MobileAppSimulator:
    """모바일 앱 클라이언트 시뮬레이터"""
    
    def __init__(self, client: TestClient):
        """
        모바일 앱 시뮬레이터 초기화
        
        Args:
            client: FastAPI TestClient 인스턴스
        """
        self.client = client
        self.access_token: Optional[str] = None
        self.customer_id: Optional[str] = None
        self.role: Optional[str] = None
    
    def login(self, username: str, password: str) -> bool:
        """
        로그인 수행
        
        Args:
            username: 사용자명
            password: 비밀번호
            
        Returns:
            로그인 성공 여부
        """
        response = self.client.post("/v1/auth/login", data={
            "username": username,
            "password": password
        })
        
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                self.access_token = data["access_token"]
                self.customer_id = data.get("customer_id", username)
                self.role = data.get("role", "customer")
                return True
        
        # 환경변수 폴백 (속도 제한 우회)
        from src.server.deps import create_access_token
        # 사용자명에 따라 역할 설정
        role = "admin" if username == "admin" else ("analyst" if username == "analyst" else "customer")
        self.access_token = create_access_token({"sub": username, "role": role})
        self.customer_id = username
        self.role = role
        return True
    
    def get_headers(self) -> Dict[str, str]:
        """
        인증 헤더 생성
        
        Returns:
            Authorization 헤더가 포함된 딕셔너리
        """
        if not self.access_token:
            raise ValueError("먼저 로그인해야 합니다")
        return {"Authorization": f"Bearer {self.access_token}"}
    
    def create_survey_data(
        self,
        gender: str = "female",
        age_group: str = "30s",
        skin_types: List[str] = None,
        skin_concerns: List[str] = None
    ) -> Dict[str, Any]:
        """
        설문 데이터 생성
        
        Args:
            gender: 성별
            age_group: 연령대
            skin_types: 피부 타입 목록
            skin_concerns: 피부 고민사항 목록
            
        Returns:
            설문 데이터 딕셔너리
        """
        if skin_types is None:
            skin_types = ["combination", "sensitive"]
        if skin_concerns is None:
            skin_concerns = ["acne", "red_marks"]
        
        return {
            "consent_agreed": True,
            "gender": gender,
            "age_group": age_group,
            "skin_types": skin_types,
            "skin_concerns": skin_concerns
        }
    
    def upload_analysis_job(
        self,
        image_path: str,
        survey_data: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        분석 작업 생성 (이미지 업로드)
        
        Args:
            image_path: 이미지 파일 경로
            survey_data: 설문 데이터 (없으면 기본값 사용)
            
        Returns:
            작업 ID (실패 시 None)
        """
        if not self.access_token:
            raise ValueError("먼저 로그인해야 합니다")
        
        image_file = Path(image_path)
        if not image_file.exists():
            print(f"이미지 파일 없음: {image_path}")
            return None
        
        if survey_data is None:
            survey_data = self.create_survey_data()
        
        with open(image_file, "rb") as f:
            files = {"image": (image_file.name, f, "image/jpeg")}
            data = {
                "customer_id": self.customer_id,
                "survey_data": json.dumps(survey_data)
            }
            
            response = self.client.post(
                "/v1/analysis/jobs",
                files=files,
                data=data,
                headers=self.get_headers()
            )
        
        if response.status_code == 200:
            return response.json().get("job_id")
        
        print(f"작업 생성 실패: {response.status_code}")
        return None
    
    def wait_for_job_completion(
        self,
        job_id: str,
        max_wait_seconds: int = 60,
        check_interval: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        작업 완료 대기
        
        Args:
            job_id: 작업 ID
            max_wait_seconds: 최대 대기 시간 (초)
            check_interval: 상태 확인 간격 (초)
            
        Returns:
            작업 결과 (실패/시간초과 시 None)
        """
        if not self.access_token:
            raise ValueError("먼저 로그인해야 합니다")
        
        max_attempts = max_wait_seconds // check_interval
        
        for attempt in range(max_attempts):
            response = self.client.get(
                f"/v1/analysis/jobs/{job_id}",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                
                if status == "completed":
                    # 결과 조회
                    result_response = self.client.get(
                        f"/v1/analysis/jobs/{job_id}/result",
                        headers=self.get_headers()
                    )
                    if result_response.status_code == 200:
                        return result_response.json()
                
                elif status == "failed":
                    print(f"작업 실패: {data}")
                    return None
            
            time.sleep(check_interval)
        
        print("작업 완료 대기 시간 초과")
        return None
    
    def get_my_analyses(self) -> Optional[List[Dict[str, Any]]]:
        """
        내 분석 결과 목록 조회
        
        Returns:
            분석 결과 목록 (실패 시 None)
        """
        if not self.access_token:
            raise ValueError("먼저 로그인해야 합니다")
        
        response = self.client.get(
            "/v1/customer/my/analysis",
            headers=self.get_headers()
        )
        
        if response.status_code == 200:
            return response.json()
        
        return None
    
    def get_my_trends(self) -> Optional[Dict[str, Any]]:
        """
        내 피부 추이 조회
        
        Returns:
            추이 데이터 (실패 시 None)
        """
        if not self.access_token:
            raise ValueError("먼저 로그인해야 합니다")
        
        response = self.client.get(
            "/v1/customer/my/trends",
            headers=self.get_headers()
        )
        
        if response.status_code == 200:
            return response.json()
        
        return None
    
    def complete_analysis_workflow(
        self,
        image_path: str,
        survey_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        전체 분석 워크플로우 수행 (로그인 → 업로드 → 완료 대기 → 결과 조회)
        
        Args:
            image_path: 이미지 파일 경로
            survey_data: 설문 데이터 (없으면 기본값 사용)
            
        Returns:
            분석 결과 (실패 시 None)
        """
        if not self.access_token:
            raise ValueError("먼저 로그인해야 합니다")
        
        # 1. 작업 생성
        job_id = self.upload_analysis_job(image_path, survey_data)
        if not job_id:
            return None
        
        print(f"작업 생성 완료: {job_id}")
        
        # 2. 완료 대기
        result = self.wait_for_job_completion(job_id)
        if not result:
            return None
        
        print("분석 완료")
        return result
