"""
구독 API (언론사 / 기자 구독 관리)
=====================================
■ GET  /api/subscriptions        — 내 구독 목록 조회
■ POST /api/subscriptions        — 구독 추가
■ DELETE /api/subscriptions/{id} — 구독 해제
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models import Subscription, User
from app.schemas import SubscriptionCreate, SubscriptionResponse

router = APIRouter()


@router.get(
    "",
    response_model=list[SubscriptionResponse],
    summary="내 구독 목록 조회",
)
@limiter.limit(settings.RATE_LIMIT)
async def list_subscriptions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 모든 구독(언론사/기자)을 반환한다."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_email == user.email)
        .order_by(Subscription.created_at.desc())
    )
    return result.scalars().all()


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="구독 추가",
)
@limiter.limit(settings.RATE_LIMIT)
async def add_subscription(
    request: Request,
    body: SubscriptionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """언론사 또는 기자를 구독한다. 이미 구독 중이면 409 반환."""
    existing = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.user_email == user.email,
                Subscription.target_type == body.target_type.value,
                Subscription.target_name == body.target_name,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 구독 중입니다.",
        )

    sub = Subscription(
        user_email=user.email,
        target_type=body.target_type.value,
        target_name=body.target_name,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


@router.delete(
    "/{sub_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="구독 해제",
)
@limiter.limit(settings.RATE_LIMIT)
async def remove_subscription(
    request: Request,
    sub_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """구독을 해제한다. 본인의 구독이 아니면 404 반환."""
    sub = await db.get(Subscription, sub_id)
    if not sub or sub.user_email != user.email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="구독을 찾을 수 없습니다.",
        )
    await db.delete(sub)
    await db.commit()
