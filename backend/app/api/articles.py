"""
기사 상세 API
=============
■ GET /api/articles/{article_url:path} — 기사 상세 조회 (구독 여부 포함)
"""

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models import Article, Subscription, User
from app.schemas import ArticleDetailResponse

router = APIRouter()


@router.get(
    "/{article_url:path}",
    response_model=ArticleDetailResponse,
    summary="기사 상세 조회",
)
@limiter.limit(settings.RATE_LIMIT)
async def get_article_detail(
    request: Request,
    article_url: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    기사 URL을 기반으로 기사 상세 정보를 반환한다.

    - 본문(body) 포함
    - 현재 사용자의 해당 언론사/기자 구독 여부 포함
    - 신뢰도 점수(0~100) 포함
    """
    article_url = unquote(article_url)

    article = await db.get(Article, article_url)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기사를 찾을 수 없습니다.",
        )

    # ── 언론사 구독 여부 확인 ──
    press_result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.user_email == user.email,
                Subscription.target_type == "press",
                Subscription.target_name == article.press,
            )
        )
    )
    press_sub = press_result.scalar_one_or_none()
    press_subscribed = press_sub is not None
    press_sub_id = press_sub.id if press_sub else None

    # ── 기자 구독 여부 확인 ──
    journalist_subscribed = False
    journalist_sub_id = None
    if article.journalist:
        j_result = await db.execute(
            select(Subscription).where(
                and_(
                    Subscription.user_email == user.email,
                    Subscription.target_type == "journalist",
                    Subscription.target_name == article.journalist,
                )
            )
        )
        j_sub = j_result.scalar_one_or_none()
        journalist_subscribed = j_sub is not None
        journalist_sub_id = j_sub.id if j_sub else None

    return ArticleDetailResponse(
        url=article.url,
        title=article.title,
        body=article.body,
        summary=article.summary,
        category=article.category,
        credibility=article.credibility,
        rb01_tone=article.rb01_tone,
        rb02_density=article.rb02_density,
        rb03_quotes=article.rb03_quotes,
        rb04_journalist=article.rb04_journalist,
        press=article.press,
        journalist=article.journalist,
        published_at=article.published_at,
        press_subscribed=press_subscribed,
        press_sub_id=press_sub_id,
        journalist_subscribed=journalist_subscribed,
        journalist_sub_id=journalist_sub_id,
    )
