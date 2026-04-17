"""
사용자 프로필 API
=================
■ GET   /api/users/me — 내 프로필 조회 (이메일, 이름, 관심 카테고리)
■ PATCH /api/users/me — 내 프로필 업데이트 (관심 카테고리, 글자 크기)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _hash_password, _verify_password
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models import User
from app.schemas import ChangePasswordRequest, UserProfileUpdate, UserResponse

router = APIRouter()


@router.get(
    "/me",
    response_model=UserResponse,
    summary="내 프로필 조회",
)
@limiter.limit(settings.RATE_LIMIT)
async def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 로그인된 사용자의 프로필 정보를 반환한다."""
    return user


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="내 프로필 업데이트",
)
@limiter.limit(settings.RATE_LIMIT)
async def update_me(
    request: Request,
    body: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    관심 카테고리와 글자 크기 단계를 업데이트한다.
    None 값은 변경하지 않는다 (PATCH 의미론).
    """
    if body.interest_categories is not None:
        user.interest_categories = [c.value for c in body.interest_categories]
    if body.font_size_level is not None:
        user.font_size_level = body.font_size_level
    await db.commit()
    await db.refresh(user)
    return user


@router.patch(
    "/me/password",
    summary="비밀번호 변경",
)
@limiter.limit(settings.RATE_LIMIT)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    현재 비밀번호를 확인한 뒤 새 비밀번호로 변경한다.
    현재 비밀번호와 동일한 새 비밀번호는 거부한다.
    """
    if not _verify_password(body.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호는 현재 비밀번호와 달라야 합니다.",
        )
    user.hashed_password = _hash_password(body.new_password)
    await db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="계정 탈퇴",
)
@limiter.limit(settings.RATE_LIMIT)
async def delete_account(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    사용자 계정과 관련 데이터(구독, 읽음 로그, 관심없음 로그)를 모두 삭제한다.
    FK CASCADE 설정에 의해 연관 레코드가 자동 삭제된다.
    """
    await db.delete(user)
    await db.commit()
