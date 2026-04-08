"""
개인화 추천 엔진 (Recommendation Engine)
==========================================

사용자별 개인화 피드를 생성하는 핵심 추천 알고리즘.

■ 추천 스코어 공식:
  Score = (임베딩_유사도 × 0.40)
        + (기사_최신성 × 0.15)
        + (구독_부스트 × 0.20)
        + (신뢰도_점수 × 0.15)
        - (비관심_패널티 × 0.25)

  각 항목 상세:
    ┌─────────────────┬──────────────────────────────────────────────────────┐
    │ 임베딩 유사도    │ pgvector <=> 연산자 (코사인 거리)                     │
    │                 │ cosine_similarity = 1 - cosine_distance              │
    │                 │ 사용자 interest_vector ↔ 기사 embedding              │
    ├─────────────────┼──────────────────────────────────────────────────────┤
    │ 기사 최신성      │ Exponential Decay: exp(-λ × hours_since_published)   │
    │                 │ λ = 0.05, 시간이 지날수록 기하급수적으로 감소          │
    │                 │ 예: 1시간 → 0.951, 12시간 → 0.549, 24시간 → 0.301   │
    ├─────────────────┼──────────────────────────────────────────────────────┤
    │ 구독 부스트      │ 사용자가 구독한 언론사/기자의 기사이면 ×1.3           │
    │                 │ 미구독이면 ×1.0 (기본값)                              │
    ├─────────────────┼──────────────────────────────────────────────────────┤
    │ 신뢰도 점수      │ 기사의 credibility / 100 (0~1 정규화)                │
    ├─────────────────┼──────────────────────────────────────────────────────┤
    │ 비관심 패널티    │ pgvector <=> 연산자 (코사인 거리)                     │
    │                 │ 사용자 disinterest_vector ↔ 기사 embedding           │
    │                 │ 유사할수록 높은 감점 → 피드 하단으로 밀려남            │
    └─────────────────┴──────────────────────────────────────────────────────┘

■ Redis 캐싱:
  - 키 형식: "user:{email}:feed"
  - TTL: 설정값 (기본 300초 = 5분)
  - 피드백(읽음/관심없음) 발생 시 즉시 무효화
"""

import json
import math
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import and_, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Article, DislikeLog, ReadLog, Subscription, User
from app.schemas import ArticleSummary, FeedItem, FeedResponse

# ── 추천 공식 가중치 상수 ──
W_SIMILARITY = 0.40    # 임베딩 유사도 가중치
W_FRESHNESS = 0.15     # 기사 최신성 가중치
W_SUBSCRIPTION = 0.20  # 구독 부스트 가중치
W_CREDIBILITY = 0.15   # 신뢰도 점수 가중치
W_DISINTEREST = 0.25   # 비관심 패널티 가중치

# ── Exponential Decay 파라미터 ──
LAMBDA_DECAY = 0.05  # 시간 감쇠 계수 (λ)

# ── 구독 부스트 배율 ──
SUBSCRIPTION_BOOST = 1.3  # 구독 기사 부스트 multiplier

# ── 피드 제한 ──
MAX_SUBSCRIPTION_TRACK = 10   # 구독 트랙 최대 기사 수
MAX_RECOMMENDATION_TRACK = 50  # 추천 트랙 최대 기사 수


async def get_personalized_feed(
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis | None,
) -> FeedResponse:
    """
    사용자 맞춤형 개인화 피드를 생성한다.

    1. Redis 캐시 확인 → 히트 시 즉시 반환
    2. 캐시 미스 → DB에서 추천 점수 계산 → 피드 생성 → 캐시 저장

    Args:
        user: 현재 로그인된 사용자 (interest_vector, disinterest_vector 포함)
        db: 비동기 DB 세션
        redis: Redis 클라이언트 (None이면 캐싱 비활성)

    Returns:
        FeedResponse: 구독 트랙 (최대 10건) + 추천 트랙 (점수 내림차순)
    """
    cache_key = f"user:{user.email}:feed"

    # ── Redis 캐시 확인 ──
    if redis:
        cached = await redis.get(cache_key)
        if cached:
            return FeedResponse(**json.loads(cached))

    # ── 사용자의 읽음/관심없음 기사 목록 조회 (피드 제외용) ──
    read_urls = await _get_read_article_urls(user.email, db)
    disliked_urls = await _get_active_disliked_urls(user.email, db)
    excluded_urls = read_urls | disliked_urls

    # ── 사용자의 구독 정보 조회 ──
    subscriptions = await _get_user_subscriptions(user.email, db)
    subscribed_press = {s.target_name for s in subscriptions if s.target_type == "press"}
    subscribed_journalists = {s.target_name for s in subscriptions if s.target_type == "journalist"}

    # ── 구독 트랙: 구독 언론사/기자의 최신 기사 (최대 10건) ──
    subscription_track = await _build_subscription_track(
        user, db, subscribed_press, subscribed_journalists, excluded_urls,
    )

    # ── 추천 트랙: 개인화 점수 기반 추천 ──
    recommendation_track = await _build_recommendation_track(
        user, db, subscribed_press, subscribed_journalists, excluded_urls,
    )

    feed = FeedResponse(
        subscription_track=subscription_track,
        recommendation_track=recommendation_track,
    )

    # ── Redis에 캐시 저장 (TTL: FEED_CACHE_TTL초) ──
    if redis:
        await redis.setex(
            cache_key,
            settings.FEED_CACHE_TTL,
            feed.model_dump_json(),
        )

    return feed


async def invalidate_feed_cache(user_email: str, redis: aioredis.Redis | None):
    """
    사용자의 피드 캐시를 무효화한다.
    피드백(읽음, 관심없음, Undo) 발생 시 즉시 호출되어
    다음 피드 요청에서 최신 추천 결과를 반영한다.

    Args:
        user_email: 캐시를 무효화할 사용자 이메일
        redis: Redis 클라이언트 (None이면 아무 작업 없음)
    """
    if redis:
        cache_key = f"user:{user_email}:feed"
        await redis.delete(cache_key)


# ============================================================
# 구독 트랙 생성
# ============================================================
async def _build_subscription_track(
    user: User,
    db: AsyncSession,
    subscribed_press: set[str],
    subscribed_journalists: set[str],
    excluded_urls: set[str],
) -> list[FeedItem]:
    """
    구독 트랙: 사용자가 구독한 언론사/기자의 최신 기사를 최대 10건 반환.
    피드 상단에 분리 노출되므로 추천 점수와 무관하게 최신순 정렬.
    """
    if not subscribed_press and not subscribed_journalists:
        return []

    # 구독 언론사 OR 구독 기자 조건
    conditions = []
    if subscribed_press:
        conditions.append(Article.press.in_(subscribed_press))
    if subscribed_journalists:
        conditions.append(Article.journalist.in_(subscribed_journalists))

    from sqlalchemy import or_
    query = (
        select(Article)
        .where(or_(*conditions))
        .order_by(Article.published_at.desc())
        .limit(MAX_SUBSCRIPTION_TRACK + len(excluded_urls))  # 제외분 여유 확보
    )

    result = await db.execute(query)
    articles = result.scalars().all()

    items = []
    for article in articles:
        if article.url in excluded_urls:
            continue
        if len(items) >= MAX_SUBSCRIPTION_TRACK:
            break

        items.append(_make_feed_item(article, is_subscribed=True, score=1.0))

    return items


# ============================================================
# 추천 트랙 생성 (핵심 추천 알고리즘)
# ============================================================
async def _build_recommendation_track(
    user: User,
    db: AsyncSession,
    subscribed_press: set[str],
    subscribed_journalists: set[str],
    excluded_urls: set[str],
) -> list[FeedItem]:
    """
    추천 트랙: 개인화 추천 스코어 공식에 따라 점수를 계산하고
    상위 N건을 점수 내림차순으로 반환한다.

    ■ Score = (cosine_sim × 0.40) + (freshness × 0.15)
            + (sub_boost × 0.20) + (credibility × 0.15)
            - (disinterest_penalty × 0.25)

    pgvector의 <=> 연산자는 코사인 '거리'(0~2)를 반환하므로
    코사인 '유사도' = 1 - cosine_distance 로 변환한다.
    """
    now = datetime.now(timezone.utc)

    # ── pgvector 코사인 거리 기반 후보 기사 조회 ──
    # interest_vector와 가까운 순으로 상위 200건 후보 추출 (pre-filter)
    # <=> 연산자: 코사인 거리 (0 = 동일, 2 = 반대)
    interest_vec_literal = _vector_literal(user.interest_vector)
    disinterest_vec_literal = _vector_literal(user.disinterest_vector)

    # SQL 직접 작성 (pgvector 연산자는 SQLAlchemy ORM으로 표현이 제한적)
    query = text("""
        SELECT
            url, title, summary, category, credibility,
            press, journalist, published_at,
            (embedding <=> :interest_vec) AS interest_distance,
            (embedding <=> :disinterest_vec) AS disinterest_distance
        FROM articles
        ORDER BY embedding <=> :interest_vec
        LIMIT :candidate_limit
    """)

    result = await db.execute(
        query,
        {
            "interest_vec": interest_vec_literal,
            "disinterest_vec": disinterest_vec_literal,
            "candidate_limit": MAX_RECOMMENDATION_TRACK * 4,  # 제외분 여유 확보
        },
    )
    candidates = result.fetchall()

    # ── 각 후보 기사에 추천 스코어 계산 ──
    scored_items: list[FeedItem] = []

    for row in candidates:
        url = row.url
        if url in excluded_urls:
            continue

        # ── (1) 임베딩 유사도: 코사인 유사도 = 1 - 코사인 거리 ──
        cosine_similarity = 1.0 - float(row.interest_distance)

        # ── (2) 기사 최신성: exp(-λ × hours) ──
        hours_since = _hours_since(row.published_at, now)
        freshness = math.exp(-LAMBDA_DECAY * hours_since)

        # ── (3) 구독 부스트: 구독 언론사/기자이면 ×1.3 ──
        is_subscribed = (
            row.press in subscribed_press
            or (row.journalist and row.journalist in subscribed_journalists)
        )
        sub_boost = SUBSCRIPTION_BOOST if is_subscribed else 1.0

        # ── (4) 신뢰도 점수: 0~100을 0~1로 정규화 ──
        credibility_norm = float(row.credibility) / 100.0

        # ── (5) 비관심 패널티: 코사인 유사도 = 1 - 코사인 거리 ──
        # 비관심 벡터가 영벡터이면 거리가 매우 크므로 패널티 ≈ 0
        disinterest_similarity = max(0.0, 1.0 - float(row.disinterest_distance))

        # ── 최종 스코어 계산 ──
        score = (
            (cosine_similarity * W_SIMILARITY)
            + (freshness * W_FRESHNESS)
            + (sub_boost * W_SUBSCRIPTION)
            + (credibility_norm * W_CREDIBILITY)
            - (disinterest_similarity * W_DISINTEREST)
        )

        article_summary = ArticleSummary(
            url=url,
            title=row.title,
            summary=row.summary,
            category=row.category,
            credibility=float(row.credibility),
            press=row.press,
            journalist=row.journalist,
            published_at=row.published_at,
        )

        scored_items.append(FeedItem(
            article=article_summary,
            score=round(score, 4),
            is_subscribed=is_subscribed,
            credibility_badge=FeedItem.compute_badge(float(row.credibility)),
        ))

    # ── 점수 내림차순 정렬 후 상위 N건 반환 ──
    scored_items.sort(key=lambda x: x.score, reverse=True)
    return scored_items[:MAX_RECOMMENDATION_TRACK]


# ============================================================
# 헬퍼 함수
# ============================================================

async def _get_read_article_urls(user_email: str, db: AsyncSession) -> set[str]:
    """사용자가 읽은 기사 URL 집합을 반환한다."""
    result = await db.execute(
        select(ReadLog.article_url).where(ReadLog.user_email == user_email)
    )
    return {row[0] for row in result.fetchall()}


async def _get_active_disliked_urls(user_email: str, db: AsyncSession) -> set[str]:
    """사용자가 관심없음 처리한 (is_active=True) 기사 URL 집합을 반환한다."""
    result = await db.execute(
        select(DislikeLog.article_url).where(
            and_(
                DislikeLog.user_email == user_email,
                DislikeLog.is_active.is_(True),
            )
        )
    )
    return {row[0] for row in result.fetchall()}


async def _get_user_subscriptions(
    user_email: str, db: AsyncSession
) -> list[Subscription]:
    """사용자의 구독 목록을 반환한다."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_email == user_email)
    )
    return list(result.scalars().all())


def _hours_since(published_at: datetime, now: datetime) -> float:
    """
    기사 발행 후 경과 시간(시간 단위)을 계산한다.
    Exponential Decay 함수 exp(-0.05 × hours)에 입력된다.
    """
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    delta = now - published_at
    return max(0.0, delta.total_seconds() / 3600.0)


def _vector_literal(vector) -> str:
    """
    pgvector용 벡터 리터럴 문자열을 생성한다.
    예: [0.1, 0.2, ...] → '[0.1,0.2,...]'
    SQLAlchemy text() 바인드 파라미터에서 사용.
    """
    if vector is None:
        # 영벡터 (비관심 벡터 미초기화 시)
        return "[" + ",".join(["0.0"] * settings.EMBEDDING_DIM) + "]"
    if isinstance(vector, str):
        return vector
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


def _make_feed_item(article: Article, is_subscribed: bool, score: float) -> FeedItem:
    """Article ORM 객체를 FeedItem 스키마로 변환한다."""
    return FeedItem(
        article=ArticleSummary(
            url=article.url,
            title=article.title,
            summary=article.summary,
            category=article.category,
            credibility=article.credibility,
            press=article.press,
            journalist=article.journalist,
            published_at=article.published_at,
        ),
        score=round(score, 4),
        is_subscribed=is_subscribed,
        credibility_badge=FeedItem.compute_badge(article.credibility),
    )
