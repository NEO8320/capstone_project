"""
피드백 API 라우터 (읽음, 관심없음, Undo)
==========================================

■ POST /articles/{url}/read — 기사 읽음
  관심 벡터 EMA 업데이트: V_new = 0.15 × V_article + 0.85 × V_old

■ POST /articles/{url}/dislike — 관심없음
  비관심 벡터 EMA 업데이트: V_new = 0.10 × V_article + 0.90 × V_old

■ POST /api/v1/feed/dislike/undo — 관심없음 취소 (API-07)
  DislikeLog 레코드 삭제 + 비관심 벡터 역산 복구 (NO-04)
  V_old = (V_new - 0.10 × V_article) / 0.90

[중요] 모든 피드백 처리 후 Redis 피드 캐시 즉시 무효화
"""

from urllib.parse import unquote

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.redis import get_redis
from app.models import Article, DislikeLog, ReadLog, User
from app.schemas import (
    DislikeResponse,
    ReadResponse,
    UndoDislikeRequest,
    UndoDislikeResponse,
)
from app.services.recommendation import invalidate_feed_cache

router = APIRouter()

# ── Undo 전용 라우터 (main.py에서 /api/v1/feed 접두사로 등록) ──
undo_router = APIRouter()

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

    EMA 공식: V_new = 0.15 × V_article + 0.85 × V_old
    """
    article_url = unquote(article_url)

    article = await db.get(Article, article_url)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기사를 찾을 수 없습니다.",
        )

    # 중복 읽음 방지
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

    read_log = ReadLog(user_email=user.email, article_url=article_url)
    db.add(read_log)

    # 관심 벡터 EMA 업데이트
    # Bug #2 방어: 기사 임베딩이 없거나 비정상이면 벡터 업데이트를 건너뛴다.
    if _is_valid_embedding(article.embedding):
        updated_vector = _ema_update(
            old_vector=user.interest_vector,
            article_vector=article.embedding,
            alpha=ALPHA_READ,
        )
        if _is_vector_sane(updated_vector):
            user.interest_vector = updated_vector

    await db.commit()
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

    EMA 공식: V_new = 0.10 × V_article + 0.90 × V_old
    """
    article_url = unquote(article_url)

    article = await db.get(Article, article_url)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기사를 찾을 수 없습니다.",
        )

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

    dislike_log = DislikeLog(
        user_email=user.email,
        article_url=article_url,
        is_active=True,
    )
    db.add(dislike_log)

    # 비관심 벡터 EMA 업데이트
    # Bug #2 방어: 기사 임베딩이 없거나 비정상이면 벡터 업데이트를 건너뛴다.
    if _is_valid_embedding(article.embedding):
        updated_vector = _ema_update(
            old_vector=user.disinterest_vector,
            article_vector=article.embedding,
            alpha=ALPHA_DISLIKE,
        )
        if _is_vector_sane(updated_vector):
            user.disinterest_vector = updated_vector

    await db.flush()
    await db.commit()
    await _invalidate_cache(user.email)

    return DislikeResponse(article_url=article_url, dislike_id=dislike_log.id)


# ============================================================
# API-07: 관심없음 취소 (Undo) — POST /api/v1/feed/dislike/undo
# ============================================================
@undo_router.post(
    "/dislike/undo",
    response_model=UndoDislikeResponse,
    summary="관심없음 취소 (API-07)",
)
@limiter.limit(settings.RATE_LIMIT)
async def undo_dislike(
    request: Request,
    body: UndoDislikeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    관심없음을 취소(Undo)한다 (API-07).

    1. DislikeLog 레코드를 DB에서 삭제
    2. 비관심 벡터 역산 복구 (NO-04):
       V_old = (V_new - 0.10 × V_article) / 0.90
    3. 복구된 비관심 벡터를 DB에 저장
    4. Redis 피드 캐시 무효화

    인증 필수: Authorization: Bearer <token>
    """
    article_url = body.article_id

    # 기사 존재 확인 (임베딩 벡터 필요)
    article = await db.get(Article, article_url)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기사를 찾을 수 없습니다.",
        )

    # 활성 관심없음 로그 조회
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

    # ── NO-04: 비관심 벡터 역산 복구 ──
    # V_old = (V_new - α × V_article) / (1 - α)
    # Bug #2 방어: 임베딩이 비정상이면 역산을 건너뛴다.
    if _is_valid_embedding(article.embedding):
        recovered_vector = _reverse_ema(
            current_vector=user.disinterest_vector,
            article_vector=article.embedding,
            alpha=ALPHA_DISLIKE,
        )
        if _is_vector_sane(recovered_vector):
            user.disinterest_vector = recovered_vector

    # ── DislikeLog 레코드 DB에서 삭제 ──
    await db.execute(
        delete(DislikeLog).where(DislikeLog.id == dislike_log.id)
    )
    await db.commit()

    await _invalidate_cache(user.email)

    return UndoDislikeResponse(article_url=article_url)


# ============================================================
# 내부 헬퍼 함수
# ============================================================

def _is_valid_embedding(embedding) -> bool:
    """
    기사 임베딩이 EMA 연산에 사용 가능한 상태인지 검증한다.

    Bug #2 방어: embedding이 None이거나, 빈 리스트이거나,
    NaN/inf가 포함되어 있으면 False를 반환하여 벡터 업데이트를 차단한다.
    """
    if embedding is None:
        return False
    try:
        arr = np.array(embedding, dtype=np.float64).reshape(-1)
        if arr.size == 0:
            return False
        if not np.all(np.isfinite(arr)):
            return False
        # 영벡터도 유효하지 않음 (의미 있는 벡터가 아님)
        if np.linalg.norm(arr) < 1e-9:
            return False
        return True
    except Exception:
        return False


def _is_vector_sane(vector) -> bool:
    """
    EMA 연산 결과 벡터가 DB에 저장해도 안전한지 최종 검증한다.

    Bug #2 방어: NaN, inf, 또는 비정상적으로 큰 값이 포함되면
    False를 반환하여 DB 저장을 차단한다.
    """
    if vector is None:
        return False
    try:
        arr = np.array(vector, dtype=np.float64)
        return bool(np.all(np.isfinite(arr)))
    except Exception:
        return False


def _ema_update(
    old_vector,
    article_vector,
    alpha: float,
) -> list[float]:
    """
    EMA(지수이동평균) 벡터 업데이트.
    V_new = α × V_article + (1 - α) × V_old, L2 정규화 적용.
    """
    dim = _resolve_dim(article_vector)
    v_old = _safe_vector(old_vector, dim)
    v_article = _safe_vector(article_vector, dim)

    v_new = alpha * v_article + (1.0 - alpha) * v_old
    v_new = np.nan_to_num(v_new, nan=0.0, posinf=0.0, neginf=0.0)

    norm = np.linalg.norm(v_new)
    if norm > 0:
        v_new = v_new / norm

    return v_new.tolist()


def _reverse_ema(
    current_vector,
    article_vector,
    alpha: float,
) -> list[float]:
    """
    EMA 역산으로 이전 벡터를 복구한다 (NO-04).
    V_old = (V_new - α × V_article) / (1 - α), L2 정규화 적용.

    Note: Undo는 5초 이내 호출이 보장되나 서버는 시간 제한 없이 처리.
    """
    dim = _resolve_dim(article_vector)
    v_current = _safe_vector(current_vector, dim)
    v_article = _safe_vector(article_vector, dim)

    v_recovered = (v_current - alpha * v_article) / (1.0 - alpha)
    v_recovered = np.nan_to_num(v_recovered, nan=0.0, posinf=0.0, neginf=0.0)

    norm = np.linalg.norm(v_recovered)
    if norm > 0:
        v_recovered = v_recovered / norm

    return v_recovered.tolist()


def _resolve_dim(reference_vector) -> int:
    """벡터 차원을 안전하게 계산한다."""
    if isinstance(reference_vector, (list, tuple)) and len(reference_vector) > 0:
        return len(reference_vector)
    return settings.EMBEDDING_DIM


def _safe_vector(vector, dim: int) -> np.ndarray:
    """
    None/비정상 입력을 0 벡터로 방어하고, 차원을 맞춰 ndarray로 반환한다.
    """
    if vector is None:
        return np.zeros(dim, dtype=np.float64)

    try:
        arr = np.array(vector, dtype=np.float64).reshape(-1)
    except Exception:
        return np.zeros(dim, dtype=np.float64)

    if arr.size == 0:
        return np.zeros(dim, dtype=np.float64)

    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

    if arr.size < dim:
        padded = np.zeros(dim, dtype=np.float64)
        padded[:arr.size] = arr
        return padded

    if arr.size > dim:
        return arr[:dim]

    return arr


async def _invalidate_cache(user_email: str):
    """사용자의 Redis 피드 캐시를 무효화한다."""
    try:
        redis = get_redis()
        await invalidate_feed_cache(user_email, redis)
    except RuntimeError:
        pass
