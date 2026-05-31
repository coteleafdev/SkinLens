"""
app_features.py — 앱 기능 관련 API 라우터

피부 일기, 고객 목표, 업적, 제품 구독, 챌린지 기능 제공
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.server.deps import log, get_db
from src.db.skin_analysis_db import SkinAnalysisDB

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/app", tags=["app-features"])


# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class SkinDiaryEntryRequest(BaseModel):
    customer_id: str = Field(..., description="고객 ID")
    analysis_id: Optional[int] = Field(None, description="분석 ID")
    image_url: Optional[str] = Field(None, description="이미지 URL")
    overall_score: Optional[float] = Field(None, description="전체 점수")
    measurement_scores: Optional[dict] = Field(None, description="측정 점수")
    notes: Optional[str] = Field(None, description="메모")
    mood: Optional[str] = Field(None, description="기분")
    weather: Optional[str] = Field(None, description="날씨")


class SkinDiaryEntryResponse(BaseModel):
    entry_id: str
    customer_id: str
    created_at: str
    message: str


class SkinDiaryListResponse(BaseModel):
    customer_id: str
    total_entries: int
    entries: List[dict]


class CustomerGoalRequest(BaseModel):
    customer_id: str = Field(..., description="고객 ID")
    goal_type: str = Field(..., description="목표 유형 (skin_score, analysis_count, etc.)")
    target_value: float = Field(..., description="목표 값")
    start_date: str = Field(..., description="시작 날짜")
    end_date: str = Field(..., description="종료 날짜")


class CustomerGoalResponse(BaseModel):
    goal_id: str
    customer_id: str
    goal_type: str
    target_value: float
    current_value: float
    start_date: str
    end_date: str
    status: str
    message: str


class CustomerGoalListResponse(BaseModel):
    customer_id: str
    total_goals: int
    goals: List[dict]


class AchievementRequest(BaseModel):
    achievement_id: str = Field(..., description="업적 ID")
    name: str = Field(..., description="업적 이름")
    description: Optional[str] = Field(None, description="업적 설명")
    icon: Optional[str] = Field(None, description="업적 아이콘")
    requirement_type: Optional[str] = Field(None, description="요구 유형")
    requirement_value: Optional[float] = Field(None, description="요구 값")
    reward_points: int = Field(0, description="보상 포인트")


class AchievementResponse(BaseModel):
    achievement_id: str
    name: str
    message: str


class EarnAchievementRequest(BaseModel):
    customer_id: str = Field(..., description="고객 ID")
    achievement_id: str = Field(..., description="업적 ID")


class EarnAchievementResponse(BaseModel):
    customer_id: str
    achievement_id: str
    earned_at: str
    message: str


class CustomerAchievementListResponse(BaseModel):
    customer_id: str
    total_achievements: int
    achievements: List[dict]


class ProductSubscriptionRequest(BaseModel):
    customer_id: str = Field(..., description="고객 ID")
    product_id: str = Field(..., description="제품 ID")
    frequency: str = Field(..., description="배송 주기 (weekly, monthly)")
    next_delivery_date: str = Field(..., description="다음 배송 날짜")


class ProductSubscriptionResponse(BaseModel):
    subscription_id: str
    customer_id: str
    product_id: str
    frequency: str
    next_delivery_date: str
    message: str


class SubscriptionListResponse(BaseModel):
    customer_id: str
    total_subscriptions: int
    subscriptions: List[dict]


class ChallengeRequest(BaseModel):
    challenge_id: str = Field(..., description="챌린지 ID")
    name: str = Field(..., description="챌린지 이름")
    description: Optional[str] = Field(None, description="챌린지 설명")
    duration_days: int = Field(30, description="지속 일수")
    start_date: Optional[str] = Field(None, description="시작 날짜")
    end_date: Optional[str] = Field(None, description="종료 날짜")
    reward_points: int = Field(0, description="보상 포인트")


class ChallengeResponse(BaseModel):
    challenge_id: str
    name: str
    message: str


class JoinChallengeRequest(BaseModel):
    customer_id: str = Field(..., description="고객 ID")
    challenge_id: str = Field(..., description="챌린지 ID")
    start_date: str = Field(..., description="시작 날짜")
    end_date: str = Field(..., description="종료 날짜")


class JoinChallengeResponse(BaseModel):
    customer_id: str
    challenge_id: str
    start_date: str
    end_date: str
    message: str


class UpdateChallengeProgressRequest(BaseModel):
    customer_id: str = Field(..., description="고객 ID")
    challenge_id: str = Field(..., description="챌린지 ID")
    progress: float = Field(..., ge=0, le=100, description="진행률 (0-100)")


class UpdateChallengeProgressResponse(BaseModel):
    customer_id: str
    challenge_id: str
    progress: float
    message: str


class CustomerChallengeListResponse(BaseModel):
    customer_id: str
    total_challenges: int
    challenges: List[dict]


# ── 피부 일기 API ─────────────────────────────────────────────────────────────

@router.post("/diary", response_model=SkinDiaryEntryResponse)
async def create_diary_entry(request: SkinDiaryEntryRequest, db: SkinAnalysisDB = Depends(get_db)):
    """피부 일기 엔트리 생성"""
    entry_id = f"DIARY-{uuid.uuid4().hex[:8]}"
    
    db.create_skin_diary_entry(
        entry_id=entry_id,
        customer_id=request.customer_id,
        analysis_id=request.analysis_id,
        image_url=request.image_url,
        overall_score=request.overall_score,
        measurement_scores=request.measurement_scores,
        notes=request.notes,
        mood=request.mood,
        weather=request.weather,
    )
    
    return SkinDiaryEntryResponse(
        entry_id=entry_id,
        customer_id=request.customer_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        message="피부 일기 엔트리가 생성되었습니다."
    )


@router.get("/diary/{customer_id}", response_model=SkinDiaryListResponse)
async def get_diary_entries(customer_id: str, limit: int = 30, db: SkinAnalysisDB = Depends(get_db)):
    """고객 피부 일기 엔트리 조회"""
    entries = db.get_skin_diary_entries(customer_id, limit)
    
    return SkinDiaryListResponse(
        customer_id=customer_id,
        total_entries=len(entries),
        entries=entries,
    )


# ── 고객 목표 API ─────────────────────────────────────────────────────────────

@router.post("/goals", response_model=CustomerGoalResponse)
async def create_customer_goal(request: CustomerGoalRequest, db: SkinAnalysisDB = Depends(get_db)):
    """고객 목표 생성"""
    goal_id = f"GOAL-{uuid.uuid4().hex[:8]}"
    
    db.create_customer_goal(
        goal_id=goal_id,
        customer_id=request.customer_id,
        goal_type=request.goal_type,
        target_value=request.target_value,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    
    return CustomerGoalResponse(
        goal_id=goal_id,
        customer_id=request.customer_id,
        goal_type=request.goal_type,
        target_value=request.target_value,
        current_value=0.0,
        start_date=request.start_date,
        end_date=request.end_date,
        status="active",
        message="고객 목표가 생성되었습니다."
    )


@router.put("/goals/{goal_id}/progress")
async def update_goal_progress(goal_id: str, current_value: float, db: SkinAnalysisDB = Depends(get_db)):
    """고객 목표 진행률 업데이트"""
    db.update_customer_goal_progress(goal_id, current_value)
    
    return {"goal_id": goal_id, "current_value": current_value, "message": "목표 진행률이 업데이트되었습니다."}


@router.get("/goals/{customer_id}", response_model=CustomerGoalListResponse)
async def get_customer_goals(customer_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """고객 목표 조회"""
    goals = db.get_customer_goals(customer_id)
    
    return CustomerGoalListResponse(
        customer_id=customer_id,
        total_goals=len(goals),
        goals=goals,
    )


# ── 업적 API ─────────────────────────────────────────────────────────────────

@router.post("/achievements", response_model=AchievementResponse)
async def create_achievement(request: AchievementRequest, db: SkinAnalysisDB = Depends(get_db)):
    """업적 생성 (관리자용)"""
    db.create_achievement(
        achievement_id=request.achievement_id,
        name=request.name,
        description=request.description,
        icon=request.icon,
        requirement_type=request.requirement_type,
        requirement_value=request.requirement_value,
        reward_points=request.reward_points,
    )
    
    return AchievementResponse(
        achievement_id=request.achievement_id,
        name=request.name,
        message="업적이 생성되었습니다."
    )


@router.post("/achievements/earn", response_model=EarnAchievementResponse)
async def earn_achievement(request: EarnAchievementRequest, db: SkinAnalysisDB = Depends(get_db)):
    """고객 업적 획득"""
    db.earn_achievement(request.customer_id, request.achievement_id)
    
    return EarnAchievementResponse(
        customer_id=request.customer_id,
        achievement_id=request.achievement_id,
        earned_at=datetime.now(timezone.utc).isoformat(),
        message="업적을 획득했습니다."
    )


@router.get("/achievements/{customer_id}", response_model=CustomerAchievementListResponse)
async def get_customer_achievements(customer_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """고객 업적 조회"""
    achievements = db.get_customer_achievements(customer_id)
    
    return CustomerAchievementListResponse(
        customer_id=customer_id,
        total_achievements=len(achievements),
        achievements=achievements,
    )


# ── 제품 구독 API ─────────────────────────────────────────────────────────────

@router.post("/subscriptions", response_model=ProductSubscriptionResponse)
async def create_subscription(request: ProductSubscriptionRequest, db: SkinAnalysisDB = Depends(get_db)):
    """제품 구독 생성"""
    subscription_id = f"SUB-{uuid.uuid4().hex[:8]}"
    
    db.create_product_subscription(
        subscription_id=subscription_id,
        customer_id=request.customer_id,
        product_id=request.product_id,
        frequency=request.frequency,
        next_delivery_date=request.next_delivery_date,
    )
    
    return ProductSubscriptionResponse(
        subscription_id=subscription_id,
        customer_id=request.customer_id,
        product_id=request.product_id,
        frequency=request.frequency,
        next_delivery_date=request.next_delivery_date,
        message="제품 구독이 생성되었습니다."
    )


@router.get("/subscriptions/{customer_id}", response_model=SubscriptionListResponse)
async def get_customer_subscriptions(customer_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """고객 구독 조회"""
    subscriptions = db.get_customer_subscriptions(customer_id)
    
    return SubscriptionListResponse(
        customer_id=customer_id,
        total_subscriptions=len(subscriptions),
        subscriptions=subscriptions,
    )


# ── 챌린지 API ───────────────────────────────────────────────────────────────

@router.post("/challenges", response_model=ChallengeResponse)
async def create_challenge(request: ChallengeRequest, db: SkinAnalysisDB = Depends(get_db)):
    """챌린지 생성 (관리자용)"""
    db.create_challenge(
        challenge_id=request.challenge_id,
        name=request.name,
        description=request.description,
        duration_days=request.duration_days,
        start_date=request.start_date,
        end_date=request.end_date,
        reward_points=request.reward_points,
    )
    
    return ChallengeResponse(
        challenge_id=request.challenge_id,
        name=request.name,
        message="챌린지가 생성되었습니다."
    )


@router.post("/challenges/join", response_model=JoinChallengeResponse)
async def join_challenge(request: JoinChallengeRequest, db: SkinAnalysisDB = Depends(get_db)):
    """챌린지 참여"""
    db.join_challenge(
        customer_id=request.customer_id,
        challenge_id=request.challenge_id,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    
    return JoinChallengeResponse(
        customer_id=request.customer_id,
        challenge_id=request.challenge_id,
        start_date=request.start_date,
        end_date=request.end_date,
        message="챌린지에 참여했습니다."
    )


@router.put("/challenges/progress", response_model=UpdateChallengeProgressResponse)
async def update_challenge_progress(request: UpdateChallengeProgressRequest, db: SkinAnalysisDB = Depends(get_db)):
    """챌린지 진행률 업데이트"""
    db.update_challenge_progress(
        customer_id=request.customer_id,
        challenge_id=request.challenge_id,
        progress=request.progress,
    )
    
    return UpdateChallengeProgressResponse(
        customer_id=request.customer_id,
        challenge_id=request.challenge_id,
        progress=request.progress,
        message="챌린지 진행률이 업데이트되었습니다."
    )


@router.get("/challenges/{customer_id}", response_model=CustomerChallengeListResponse)
async def get_customer_challenges(customer_id: str, db: SkinAnalysisDB = Depends(get_db)):
    """고객 챌린지 조회"""
    challenges = db.get_customer_challenges(customer_id)
    
    return CustomerChallengeListResponse(
        customer_id=customer_id,
        total_challenges=len(challenges),
        challenges=challenges,
    )
