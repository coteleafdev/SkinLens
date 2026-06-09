"""
향상된 기능 API 라우터

이미지 업로드 개선, 결과 시각화, 푸시 알림 개인화, A/B 테스트, 모니터링 기능을 제공합니다.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field

from src.db.skin_analysis_db import SkinAnalysisDB
from src.server.deps import get_current_customer
from src.utils.config import load_config

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/enhancements", tags=["enhancements"])

# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class PushPreferencesRequest(BaseModel):
    push_enabled: bool = True
    analysis_complete_enabled: bool = True
    promotion_enabled: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    device_token: Optional[str] = None
    platform: Optional[str] = None

class ABTestCreateRequest(BaseModel):
    test_name: str
    variant_a_name: str
    variant_b_name: str
    description: Optional[str] = None
    traffic_split: float = 0.5
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class ABTestResultRequest(BaseModel):
    test_id: int
    variant: str
    metric_name: str
    metric_value: Optional[float] = None
    event_count: int = 1

class MetricRecordRequest(BaseModel):
    metric_name: str
    metric_value: float
    metric_unit: Optional[str] = None
    tags: Optional[Dict[str, str]] = None

# ── 의존성 ───────────────────────────────────────────────────────────────────

def get_db():
    config = load_config()
    db_path = config.get("database", {}).get("sqlite_path", "results/skin_analysis.db")
    return SkinAnalysisDB(db_path=db_path)

# ── 이미지 업로드 ─────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_image(
    current_customer: dict = Depends(get_current_customer),
    file: UploadFile = File(...),
    rotation_angle: int = Form(0),
    db: SkinAnalysisDB = Depends(get_db),
):
    """
    이미지 업로드
    
    - 파일 크기 제한: 10MB
    - 지원 형식: jpg, jpeg, png
    - 자동 회전 지원
    """
    customer_id = current_customer.get("customer_id") if isinstance(current_customer, dict) else current_customer
    # 파일 크기 확인
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 10MB limit"
        )
    
    # 파일 형식 확인
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    file_ext = file.filename.lower().split(".")[-1] if "." in file.filename else ""
    if f".{file_ext}" not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only jpg, jpeg, png are allowed"
        )
    
    # 업로드 ID 생성
    upload_id = str(uuid.uuid4())
    
    # 파일 저장 (실제 구현에서는 S3 등 사용)
    import os
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{upload_id}_{file.filename}")
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    # 이미지 크기 확인
    from PIL import Image, UnidentifiedImageError
    try:
        img = Image.open(file_path)
        width, height = img.size
    except (UnidentifiedImageError, OSError, IOError) as e:  # [FIX P2] 구체적 예외
        log.error(f"이미지 열기 실패: {e}")
        width, height = None, None
    
    # DB에 기록
    db.create_image_upload(
        customer_id=customer_id,
        upload_id=upload_id,
        original_filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        width=width,
        height=height,
        rotation_angle=rotation_angle,
    )
    
    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "file_size": len(content),
        "width": width,
        "height": height,
        "rotation_angle": rotation_angle,
        "status": "pending"
    }

@router.get("/uploads")
async def get_uploads(
    current_customer: dict = Depends(get_current_customer),
    upload_status: Optional[str] = None,
    limit: int = 100,
    db: SkinAnalysisDB = Depends(get_db),
):
    """이미지 업로드 목록 조회"""
    customer_id = current_customer.get("customer_id") if isinstance(current_customer, dict) else current_customer
    uploads = db.get_image_uploads(
        customer_id=customer_id,
        upload_status=upload_status,
        limit=limit,
    )
    return {"uploads": uploads}

# ── 푸시 알림 선호도 ─────────────────────────────────────────────────────────

@router.post("/push/preferences")
async def set_push_preferences(
    preferences: PushPreferencesRequest,
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """푸시 알림 선호도 설정"""
    customer_id = current_customer.get("customer_id") if isinstance(current_customer, dict) else current_customer
    success = db.set_push_preferences(
        customer_id=customer_id,
        push_enabled=preferences.push_enabled,
        analysis_complete_enabled=preferences.analysis_complete_enabled,
        promotion_enabled=preferences.promotion_enabled,
        quiet_hours_start=preferences.quiet_hours_start,
        quiet_hours_end=preferences.quiet_hours_end,
        device_token=preferences.device_token,
        platform=preferences.platform,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set push preferences"
        )
    
    return {"message": "Push preferences updated successfully"}

@router.get("/push/preferences")
async def get_push_preferences(
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """푸시 알림 선호도 조회"""
    customer_id = current_customer.get("customer_id") if isinstance(current_customer, dict) else current_customer
    preferences = db.get_push_preferences(customer_id=customer_id)
    if not preferences:
        # 기본값 반환
        return {
            "push_enabled": True,
            "analysis_complete_enabled": True,
            "promotion_enabled": False,
            "quiet_hours_start": None,
            "quiet_hours_end": None,
        }
    return preferences

# ── A/B 테스트 ───────────────────────────────────────────────────────────────

@router.post("/ab/tests")
async def create_ab_test(
    request: ABTestCreateRequest,
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """A/B 테스트 생성 (관리자 전용)"""
    if current_customer.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    success = db.create_ab_test(
        test_name=request.test_name,
        variant_a_name=request.variant_a_name,
        variant_b_name=request.variant_b_name,
        description=request.description,
        traffic_split=request.traffic_split,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test name already exists"
        )
    
    return {"message": "A/B test created successfully", "test_name": request.test_name}

@router.post("/ab/assign")
async def assign_user_to_variant(
    test_id: int,
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """
    사용자를 A/B 테스트 변형에 할당
    
    트래픽 분할 비율에 따라 자동으로 변형 할당
    """
    customer_id = current_customer.get("customer_id") if isinstance(current_customer, dict) else current_customer
    # 테스트 정보 조회
    # (실제 구현에서는 테스트 정보를 DB에서 조회)
    import random
    variant = "A" if random.random() < 0.5 else "B"
    
    success = db.assign_user_to_variant(
        test_id=test_id,
        customer_id=customer_id,
        variant=variant,
    )
    
    if not success:
        # 이미 할당된 경우 기존 변형 반환
        existing_variant = db.get_user_variant(test_id, customer_id)
        return {"variant": existing_variant}
    
    return {"variant": variant}

@router.get("/ab/variant/{test_id}")
async def get_user_variant(
    test_id: int,
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """사용자의 A/B 테스트 변형 조회"""
    customer_id = current_customer.get("customer_id") if isinstance(current_customer, dict) else current_customer
    variant = db.get_user_variant(test_id, customer_id)
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not assigned to this test"
        )
    return {"variant": variant}

@router.post("/ab/results")
async def record_ab_test_result(
    request: ABTestResultRequest,
    db: SkinAnalysisDB = Depends(get_db),
):
    """A/B 테스트 결과 기록"""
    success = db.record_ab_test_result(
        test_id=request.test_id,
        variant=request.variant,
        metric_name=request.metric_name,
        metric_value=request.metric_value,
        event_count=request.event_count,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record test result"
        )
    
    return {"message": "Test result recorded successfully"}

@router.get("/ab/results/{test_id}")
async def get_ab_test_results(
    test_id: int,
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """A/B 테스트 결과 조회 (관리자 전용)"""
    if current_customer.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    results = db.get_ab_test_results(test_id=test_id)
    return {"results": results}

# ── 모니터링 메트릭 ─────────────────────────────────────────────────────────

@router.post("/metrics")
async def record_metric(
    request: MetricRecordRequest,
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """모니터링 메트릭 기록 (관리자 전용)"""
    if current_customer.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    success = db.record_metric(
        metric_name=request.metric_name,
        metric_value=request.metric_value,
        metric_unit=request.metric_unit,
        tags=request.tags,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record metric"
        )
    
    return {"message": "Metric recorded successfully"}

@router.get("/metrics")
async def get_metrics(
    metric_name: Optional[str] = None,
    limit: int = 1000,
    current_customer: dict = Depends(get_current_customer),
    db: SkinAnalysisDB = Depends(get_db),
):
    """모니터링 메트릭 조회 (관리자 전용)"""
    if current_customer.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    metrics = db.get_metrics(
        metric_name=metric_name,
        limit=limit,
    )
    return {"metrics": metrics}

# ── 분석 추이 ───────────────────────────────────────────────────────────────

@router.get("/trends")
async def get_analysis_trends(
    current_customer: dict = Depends(get_current_customer),
    limit: int = 50,
    db: SkinAnalysisDB = Depends(get_db),
):
    """분석 추이 조회 (시계열 데이터)"""
    customer_id = current_customer.get("customer_id") if isinstance(current_customer, dict) else current_customer
    trends = db.get_analysis_trends(
        customer_id=customer_id,
        limit=limit,
    )
    
    # 시계열 데이터 형식 변환
    formatted_trends = []
    for trend in trends:
        formatted_trends.append({
            "recorded_at": trend["recorded_at"],
            "overall_score_original": trend["overall_score_original"],
            "overall_score_restored": trend["overall_score_restored"],
            "measurement_scores": trend.get("measurement_scores"),
        })
    
    return {"trends": formatted_trends}
