"""
피드백 API 라우터 (읽음, 관심없음, Undo)
==========================================

사용자의 기사 피드백을 처리하고 개인화 벡터를 EMA 방식으로 업데이트한다.

■ POST /articles/{url}/read — 기사 읽음
  관심 벡터 EMA 업데이트: V_new = 0.15 × V_article + 0.85 × V_old
  → 사용자가 읽은 기사 방향으로 관심 벡터가 서서히 이동

■ POST /articles/{url}/dislike — 관심없음
  비관심 벡터 EMA 업데이트: V_new = 0.10 × V_article + 0.90 × V_old
  → 피드에서 즉시 제거 (is_active=True)
  → 5초 내 Undo 가능 (프론트엔드에서 토스트 UI 제공)

■ DELETE /articles/{url}/dislike — 관심없음 취소 (Undo)
  DislikeLog.is_active → False로 전환
  → 기사가 다시 피드에 노출됨

[중요] 모든 피드백 처리 후 Redis 피드 캐시 즉시 무효화
"""

from urllib.parse import unquote

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.redis import get_redis
from app.models import Article, DislikeLog, ReadLog, User
from app.schemas import DislikeResponse, ReadResponse, UndoDislikeResponse
from app.services.recommendation import invalidate_feed_cache

router = APIRouter()

# ── EMA(지수이동평균) 학습률 ──
ALPHA_READ = 0.15     # 읽음 피드백: 새 기사에 15% 가중치
ALPHA_DISLIKE = 0.10  # 관심없음 피드백: 새 기사에 10% 가중치


@router.post(
    "/{article_url:path}/read",
    response_model=ReadResponse,
    summary="기사 읽음 처리",
)
@limiter.limit(settings.RATE_LIMIT)
async def mark_article_read(
    request: Request,
    article_url: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    기사를 읽음 처리하고 사용자의 관심 벡터를 EMA 업데이트한다.

    ■ EMA 공식: V_new = α × V_article + (1 - α) × V_old
      - α = 0.15 (읽음)
      - V_article: 기사의 768차원 임베딩 벡터
      - V_old: 사용자의 현재 관심 벡터

    ■ 효과:
      사용자가 기사를 읽을 때마다 관심 벡터가 해당 기사 방향으로
      서서히 이동하여 추천 정확도가 점진적으로 개선된다.
    """
    article_url = unquote(article_url)

    # ── 기사 존재 확인 ──
    article = await db.get(Article, article_url)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기사를 찾을 수 없습니다.",
        )

    # ── 중복 읽음 방지: 이미 읽은 기사는 벡터 업데이트 건너뜀 ──
    existing = await db.execute(
        select(ReadLog).where(
            and_(
                ReadLog.user_email == user.email,
                ReadLog.article_url == article_url,
            )
        )
    )
    if existing.scalar_one_or_none():
        return ReadResponse(article_url=article_url, message="이미 읽은 기사입니다.")

    # ── 읽음 로그 기록 ──
    read_log = ReadLog(user_email=user.email, article_url=article_url)
    db.add(read_log)

    # ── 관심 벡터 EMA 업데이트 ──
    # V_new = 0.15 × V_article + 0.85 × V_old
    updated_vector = _ema_update(
        old_vector=user.interest_vector,
        article_vector=article.embedding,
        alpha=ALPHA_READ,
    )
    user.interest_vector = updated_vector

    await db.commit()

    # ── Redis 피드 캐시 무효화 ──
    await _invalidate_cache(user.email)

    return ReadResponse(article_url=article_url)


@router.post(
    "/{article_url:path}/dislike",
    response_model=DislikeResponse,
    summary="관심없음 처리",
)
@limiter.limit(settings.RATE_LIMIT)
async def dislike_article(
    request: Request,
    article_url: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    기사를 관심없음 처리하고 비관심 벡터를 EMA 업데이트한다.

    ■ EMA 공식: V_new = α × V_article + (1 - α) × V_old
      - α = 0.10 (관심없음)
      - V_article: 기사의 768차원 임베딩 벡터
      - V_old: 사용자의 현재 비관심 벡터

    ■ 즉시 효과:
      - 피드에서 해당 기사 즉시 제거 (DislikeLog.is_active=True)
      - 비관심 벡터가 해당 기사 방향으로 이동 → 유사 기사도 향후 감점

    ■ Undo 지원:
      프론트엔드에서 5초간 Undo 토스트를 표시하고,
      사용자가 Undo 클릭 시 DELETE 엔드포인트를 호출.
    """
    article_url = unquote(article_url)

    # ── 기사 존재 확인 ──
    article = await db.get(Article, article_url)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기사를 찾을 수 없습니다.",
        )

    # ── 이미 관심없음 처리된 기사 확인 ──
    existing = await db.execute(
        select(DislikeLog).where(
            and_(
                DislikeLog.user_email == user.email,
                DislikeLog.article_url == article_url,
                DislikeLog.is_active.is_(True),
            )
        )
    )
    existing_log = existing.scalar_one_or_none()
    if existing_log:
        return DislikeResponse(
            article_url=article_url,
            dislike_id=existing_log.id,
            message="이미 관심없음 처리된 기사입니다.",
        )

    # ── 관심없음 로그 기록 (is_active=True: 피드에서 제거) ──
    dislike_log = DislikeLog(
        user_email=user.email,
        article_url=article_url,
        is_active=True,
    )
    db.add(dislike_log)

    # ── 비관심 벡터 EMA 업데이트 ──
    # V_new = 0.10 × V_article + 0.90 × V_old
    updated_vector = _ema_update(
        old_vector=user.disinterest_vector,
        article_vector=article.embedding,
        alpha=ALPHA_DISLIKE,
    )
    user.disinterest_vector = updated_vector

    await db.flush()  # dislike_log.id를 얻기 위해 flush
    await db.commit()

    # ── Redis 피드 캐시 무효화 ──
    await _invalidate_cache(user.email)

    return DislikeResponse(article_url=article_url, dislike_id=dislike_log.id)


@router.delete(
    "/{article_url:path}/dislike",
    response_model=UndoDislikeResponse,
    summary="관심없음 취소 (Undo)",
)
@limiter.limit(settings.RATE_LIMIT)
async def undo_dislike(
    request: Request,
    article_url: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    관심없음을 취소(Undo)하여 기사를 다시 피드에 노출한다.

    DislikeLog.is_active를 False로 전환하여
    향후 피드 생성 시 해당 기사가 제외 대상에서 빠진다.

    Note:
      비관심 벡터는 되돌리지 않는다 (EMA 특성상 역산이 부정확).
      대신 기사가 다시 피드에 노출되면서 자연스럽게 보정된다.
    """
    article_url = unquote(article_url)

    # ── 활성 관심없음 로그 조회 ──
    result = await db.execute(
        select(DislikeLog).where(
            and_(
                DislikeLog.user_email == user.email,
                DislikeLog.article_url == article_url,
                DislikeLog.is_active.is_(True),
            )
        )
    )
    dislike_log = result.scalar_one_or_none()

    if not dislike_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="관심없음 기록을 찾을 수 없습니다.",
        )

    # ── Undo: is_active → False ──
    dislike_log.is_active = False
    await db.commit()

    # ── Redis 피드 캐시 무효화 ──
    await _invalidate_cache(user.email)

    return UndoDislikeResponse(article_url=article_url)


# ============================================================
# 내부 헬퍼 함수
# ============================================================

def _ema_update(
    old_vector,
    article_vector,
    alpha: float,
) -> list[float]:
    """
    EMA(지수이동평균) 방식으로 벡터를 업데이트한다.

    공식: V_new = α × V_article + (1 - α) × V_old

    Args:
        old_vector: 기존 사용자 벡터 (768차원)
        article_vector: 기사 임베딩 벡터 (768차원)
        alpha: 학습률 (읽음: 0.15, 관심없음: 0.10)

    Returns:
        업데이트된 768차원 벡터 (L2 정규화 적용)
    """
    v_old = np.array(old_vector, dtype=np.float64)
    v_article = np.array(article_vector, dtype=np.float64)

    # EMA 계산
    v_new = alpha * v_article + (1.0 - alpha) * v_old

    # L2 정규화: 코사인 유사도 연산 시 단위 벡터를 유지해야 정확도 보장
    norm = np.linalg.norm(v_new)
    if norm > 0:
        v_new = v_new / norm

    return v_new.tolist()


async def _invalidate_cache(user_email: str):
    """
    사용자의 Redis 피드 캐시를 무효화한다.
    피드백 처리 후 즉시 호출되어 다음 /feed 요청에서
    최신 추천 결과가 반영되도록 보장한다.
    """
    try:
        redis = get_redis()
        await invalidate_feed_cache(user_email, redis)
    except RuntimeError:
        pass  # Redis 미연결 시 무시 (캐싱 비활성 상태)
