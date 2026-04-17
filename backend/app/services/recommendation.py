# -*- coding: utf-8 -*-
"""
개인화 추천 엔진 — 구독 트랙 + 추천 트랙 (SC-02 / SC-03)
====================================================

■ 구독 트랙(SC-02):
  구독 언론사/기자의 최신 기사를 우선 노출.
  정렬: 최신성(0.50) + 신뢰도(0.50) — 벡터 연산 없이 경량 처리.
  최대 10건 반환. 구독이 없으면 빈 리스트.

■ 추천 트랙(SC-03):
  후보 선별: 최신순(published_at DESC) — 전체 카테고리 편향 없이 노출
  base_score = (임베딩 유사도 × 0.40) + (최신성 × 0.20)
             + (구독 가중치 × 0.20) + (신뢰도 × 0.20)
  final_score = base_score - (비관심 패널티 × 0.25)
  구독 기사: final_score × 1.3 (SC-04 구독 부스트)
  이미 읽은/관심없음 기사는 제외 (NO-03)

■ 콜드 스타트 방어 (Bug #1 fix):
  interest_vector가 None이거나 영벡터(norm ≈ 0)이면
  pgvector <=> 연산을 완전히 우회하고,
  credibility DESC + published_at DESC 기준 상위 20건을 반환한다.

■ 타임존 충돌 방어 (Bug #3 fix):
  _hours_since()에서 naive/aware datetime이 혼재해도
  양쪽 모두 UTC aware로 정규화하여 안전하게 연산한다.

■ Redis 캐싱:
  키: "user:{email}:feed", TTL: 5분
  피드백(읽음/관심없음) 발생 시 즉시 무효화.

■ 가중치 외부 설정: config.yaml (NFR-E03)
"""

import json
import math
from datetime import datetime, timezone

import numpy as np
import redis.asyncio as aioredis
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.yaml_config import get_yaml_config
from app.models import Article, DislikeLog, ReadLog, Subscription, User
from app.schemas import ArticleSummary, FeedItem, FeedResponse

# ── 상수 ──
LAMBDA_DECAY = 0.05               # 최신성 Exponential Decay 감쇠 계수
MAX_RECOMMENDATION_TRACK = 50      # 추천 트랙 최대 반환 건수
COLD_START_LIMIT = 20              # 콜드 스타트 시 반환 건수


# ============================================================
# 가중치 로드
# ============================================================
def _load_weights() -> dict:
    """config.yaml에서 추천 가중치를 로드한다. 없으면 기본값 사용 (NFR-E03)."""
    cfg = get_yaml_config().get("recommendation", {})
    return {
        "w_similarity": cfg.get("weight_embedding", 0.40),
        "w_freshness": cfg.get("weight_recency", 0.20),
        "w_subscription": cfg.get("weight_subscription", 0.20),
        "w_reliability": cfg.get("weight_reliability", 0.20),
        "w_dislike_penalty": cfg.get("weight_dislike_penalty", 0.25),
        "boost_multiplier": cfg.get("subscription_boost_multiplier", 1.3),
        "sub_track_limit": cfg.get("subscription_track_limit", 10),
    }


# ============================================================
# 콜드 스타트 판별 (Bug #1 핵심 방어)
# ============================================================
def _is_cold_start(vec) -> bool:
    """
    벡터가 None이거나 영벡터(all zeros)인지 판별한다.
    True이면 콜드 스타트 → pgvector 코사인 연산을 완전히 우회해야 한다.

    왜 필요한가:
      User.interest_vector 컬럼이 nullable=False라서 Python에서 None이 아닐 수 있다.
      하지만 신규 유저의 벡터가 [0,0,...,0] 영벡터이면
      pgvector의 <=> (코사인 거리) 연산이 0으로 나누기를 하여 NaN을 반환한다.
      이 NaN이 float()으로 변환되면 TypeError/ValueError가 터지고 500 에러.
    """
    if vec is None:
        return True
    try:
        norm = float(np.linalg.norm(vec))
        return norm < 1e-9
    except Exception:
        return True


# ============================================================
# 메인 진입점
# ============================================================
async def get_personalized_feed(
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis | None,
) -> FeedResponse:
    """
    사용자 맞춤형 개인화 뉴스 피드를 조합하여 반환한다 (API-04).

    1. Redis 캐시가 있으면 즉시 반환 (5분 TTL)
    2. 캐시 미스 → 구독 트랙 + 추천 트랙을 각각 구성
    3. 결과를 Redis에 캐싱 후 반환
    """
    cache_key = f"user:{user.email}:feed"

    # ── Redis 캐시 히트 ──
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return FeedResponse(**json.loads(cached))
        except Exception:
            pass  # Redis 장애 시 DB 직접 조회로 폴백

    # ── 제외 대상 수집 ──
    # (Bug fix) 읽은 기사는 숨기지 않고 is_read 플래그로 표시만 한다.
    #           피드에서 사라지는 현상(read_urls | disliked_urls)을 제거.
    disliked_urls = await _get_active_disliked_urls(user.email, db)
    read_urls = await _get_read_article_urls(user.email, db)
    excluded_urls = disliked_urls  # 관심없음만 실제 제외

    # ── 구독 정보 수집 ──
    subscriptions = await _get_user_subscriptions(user.email, db)
    subscribed_press = {s.target_name for s in subscriptions if s.target_type == "press"}
    subscribed_journalists = {
        s.target_name for s in subscriptions if s.target_type == "journalist"
    }

    # ── 트랙 구성 ──
    subscription_track = await _build_subscription_track(
        user, db, subscribed_press, subscribed_journalists, excluded_urls, read_urls,
    )
    recommendation_track = await _build_recommendation_track(
        user, db, subscribed_press, subscribed_journalists, excluded_urls, read_urls,
    )

    feed = FeedResponse(
        subscription_track=subscription_track,
        recommendation_track=recommendation_track,
    )

    # ── Redis 캐싱 ──
    if redis:
        try:
            await redis.setex(cache_key, settings.FEED_CACHE_TTL, feed.model_dump_json())
        except Exception:
            pass  # 캐싱 실패해도 응답은 정상 반환

    return feed


async def invalidate_feed_cache(user_email: str, redis: aioredis.Redis | None):
    """사용자의 피드 캐시를 즉시 무효화한다."""
    if redis:
        try:
            await redis.delete(f"user:{user_email}:feed")
        except Exception:
            pass


# ============================================================
# SC-02: 구독 트랙
# ============================================================
async def _build_subscription_track(
    user: User,
    db: AsyncSession,
    subscribed_press: set[str],
    subscribed_journalists: set[str],
    excluded_urls: set[str],
    read_urls: set[str] | None = None,
) -> list[FeedItem]:
    """
    SC-02: 구독 트랙 구성.

    구독 언론사/기자의 최신 기사를 최신성+신뢰도 점수로 정렬한다.
    벡터 연산을 사용하지 않으므로 콜드 스타트 유저에게도 안전하다.
    구독이 없으면 빈 리스트를 반환한다.
    최대 10건.

    read_urls: 이미 읽은 기사 URL 집합 — 노출은 유지하되 is_read=True 플래그를 부여한다.
    """
    if not subscribed_press and not subscribed_journalists:
        return []

    read_urls = read_urls or set()
    w = _load_weights()
    now = datetime.now(timezone.utc)

    # ── 구독 대상 기사만 ORM으로 조회 (pgvector 불필요) ──
    conditions = []
    if subscribed_press:
        conditions.append(Article.press.in_(subscribed_press))
    if subscribed_journalists:
        conditions.append(Article.journalist.in_(subscribed_journalists))

    result = await db.execute(
        select(Article)
        .where(or_(*conditions))
        .order_by(Article.published_at.desc())
        .limit(w["sub_track_limit"] * 3)  # 제외 대상 감안하여 여유분 확보
    )
    candidates = result.scalars().all()

    scored_items: list[FeedItem] = []
    for article in candidates:
        if article.url in excluded_urls:
            continue

        # 구독 트랙 점수: 최신성(0.50) + 신뢰도(0.50)
        hours = _hours_since(article.published_at, now)
        freshness = math.exp(-LAMBDA_DECAY * hours)
        credibility_norm = _safe_credibility(article.credibility)

        score = (freshness * 0.50) + (credibility_norm * 0.50)

        scored_items.append(
            _make_feed_item(
                article,
                is_subscribed=True,
                score=score,
                is_read=(article.url in read_urls),
            )
        )

    scored_items.sort(key=lambda x: x.score, reverse=True)
    return scored_items[: w["sub_track_limit"]]


# ============================================================
# SC-03: 추천 트랙 (핵심 개인화 알고리즘)
# ============================================================
async def _build_recommendation_track(
    user: User,
    db: AsyncSession,
    subscribed_press: set[str],
    subscribed_journalists: set[str],
    excluded_urls: set[str],
    read_urls: set[str] | None = None,
) -> list[FeedItem]:
    """
    SC-03: 추천 트랙 구성.

    ■ 정상 유저 (interest_vector가 유효한 벡터):
      최신순(published_at DESC)으로 후보군을 폭넓게 조회한 뒤,
      가중합 점수(base_score - 비관심 패널티)로 정렬하여 반환.
      → '전체' 탭에서 모든 카테고리가 편향 없이 노출됨 (Task 1).
      코사인 유사도는 SELECT절에서 계산하여 스코어링에 0.40 가중치로 활용.

    ■ 콜드 스타트 유저 (interest_vector가 None 또는 영벡터):
      벡터 연산을 완전히 건너뛰고,
      credibility DESC + published_at DESC 기준 상위 기사를 반환.
      유사도 점수는 중립값(0.5)으로 대체한다.
    """
    read_urls = read_urls or set()
    w = _load_weights()
    now = datetime.now(timezone.utc)
    cold_start = _is_cold_start(user.interest_vector)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 경로 A: 콜드 스타트 폴백
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if cold_start:
        result = await db.execute(
            select(Article)
            .order_by(Article.credibility.desc(), Article.published_at.desc())
            .limit(COLD_START_LIMIT * 2)  # 제외 대상 감안하여 여유분
        )
        candidates = result.scalars().all()

        scored_items: list[FeedItem] = []
        for article in candidates:
            if article.url in excluded_urls:
                continue

            hours = _hours_since(article.published_at, now)
            freshness = math.exp(-LAMBDA_DECAY * hours)
            credibility_norm = _safe_credibility(article.credibility)

            is_subscribed = _check_subscribed(
                article, subscribed_press, subscribed_journalists,
            )

            # 콜드 스타트: 유사도=0.5(중립), 비관심=0.0
            score = (
                (0.5 * w["w_similarity"])
                + (freshness * w["w_freshness"])
                + ((1.0 if is_subscribed else 0.0) * w["w_subscription"])
                + (credibility_norm * w["w_reliability"])
            )
            if is_subscribed:
                score *= w["boost_multiplier"]

            scored_items.append(
                _make_feed_item(
                    article,
                    is_subscribed=is_subscribed,
                    score=score,
                    is_read=(article.url in read_urls),
                )
            )

        scored_items.sort(key=lambda x: x.score, reverse=True)
        return scored_items[:COLD_START_LIMIT]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 경로 B: 정상 — 최신순 후보 선별 + 코사인 유사도 스코어링
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    interest_vec_literal = _vector_literal(user.interest_vector)
    disinterest_cold = _is_cold_start(user.disinterest_vector)

    if disinterest_cold:
        # 비관심 벡터가 영벡터 → 비관심 거리를 NULL로 우회
        # Task 1: ORDER BY published_at DESC — 전체 카테고리 편향 없이 후보 선별
        query = text("""
            SELECT
                url, title, summary, category, credibility,
                press, journalist, published_at,
                rb01_tone, rb02_density, rb03_quotes, rb04_journalist,
                (embedding <=> :interest_vec) AS interest_distance,
                NULL AS disinterest_distance
            FROM articles
            ORDER BY published_at DESC
            LIMIT :candidate_limit
        """)
        result = await db.execute(
            query,
            {
                "interest_vec": interest_vec_literal,
                "candidate_limit": MAX_RECOMMENDATION_TRACK * 4,
            },
        )
    else:
        disinterest_vec_literal = _vector_literal(user.disinterest_vector)
        # Task 1: ORDER BY published_at DESC — 전체 카테고리 편향 없이 후보 선별
        query = text("""
            SELECT
                url, title, summary, category, credibility,
                press, journalist, published_at,
                rb01_tone, rb02_density, rb03_quotes, rb04_journalist,
                (embedding <=> :interest_vec) AS interest_distance,
                (embedding <=> :disinterest_vec) AS disinterest_distance
            FROM articles
            ORDER BY published_at DESC
            LIMIT :candidate_limit
        """)
        result = await db.execute(
            query,
            {
                "interest_vec": interest_vec_literal,
                "disinterest_vec": disinterest_vec_literal,
                "candidate_limit": MAX_RECOMMENDATION_TRACK * 4,
            },
        )

    candidates = result.fetchall()
    scored_items: list[FeedItem] = []

    for row in candidates:
        url = row.url
        if url in excluded_urls:
            continue

        # (1) 임베딩 유사도 — NaN/None 방어
        cosine_similarity = _safe_cosine(row.interest_distance)

        # (2) 최신성 점수
        hours = _hours_since(row.published_at, now)
        freshness = math.exp(-LAMBDA_DECAY * hours)

        # (3) 구독 여부 가중치
        # ★ Python 단축평가 버그 방어: `x and ...` 표현은 x=None이면 None을 반환.
        #   is_subscribed가 None이 되어 Pydantic FeedItem 생성 시 ValidationError 발생.
        #   명시적으로 `is not None` 비교 + bool() 래핑으로 bool 타입 보장.
        is_subscribed = bool(
            row.press in subscribed_press
            or (
                row.journalist is not None
                and row.journalist in subscribed_journalists
            )
        )
        sub_weight = 1.0 if is_subscribed else 0.0

        # (4) 신뢰도 정규화
        credibility_norm = _safe_credibility(row.credibility)

        # (5) 비관심 패널티 — NaN/None 방어
        disinterest_similarity = _safe_disinterest(row.disinterest_distance)

        # ── 점수 합산 ──
        base_score = (
            (cosine_similarity * w["w_similarity"])
            + (freshness * w["w_freshness"])
            + (sub_weight * w["w_subscription"])
            + (credibility_norm * w["w_reliability"])
        )
        final_score = base_score - (disinterest_similarity * w["w_dislike_penalty"])

        if is_subscribed:
            final_score *= w["boost_multiplier"]

        article_summary = ArticleSummary(
            url=url,
            title=row.title,
            summary=row.summary or "",
            category=row.category or "",
            credibility=float(row.credibility or 0),
            rb01_tone=row.rb01_tone,
            rb02_density=row.rb02_density,
            rb03_quotes=row.rb03_quotes,
            rb04_journalist=row.rb04_journalist,
            press=row.press or "",
            journalist=row.journalist,
            published_at=row.published_at,
        )

        scored_items.append(FeedItem(
            article=article_summary,
            score=round(final_score, 4),
            is_subscribed=is_subscribed,
            is_read=(url in read_urls),
            credibility_badge=FeedItem.compute_badge(float(row.credibility or 0)),
        ))

    scored_items.sort(key=lambda x: x.score, reverse=True)
    return scored_items[:MAX_RECOMMENDATION_TRACK]


# ============================================================
# DB 조회 헬퍼
# ============================================================
async def _get_read_article_urls(user_email: str, db: AsyncSession) -> set[str]:
    """사용자가 읽은 기사 URL 집합을 반환한다."""
    result = await db.execute(
        select(ReadLog.article_url).where(ReadLog.user_email == user_email)
    )
    return {row[0] for row in result.fetchall()}


async def _get_active_disliked_urls(user_email: str, db: AsyncSession) -> set[str]:
    """사용자가 관심없음(is_active=True) 처리한 기사 URL 집합을 반환한다."""
    result = await db.execute(
        select(DislikeLog.article_url).where(
            and_(DislikeLog.user_email == user_email, DislikeLog.is_active.is_(True))
        )
    )
    return {row[0] for row in result.fetchall()}


async def _get_user_subscriptions(user_email: str, db: AsyncSession) -> list[Subscription]:
    """사용자의 구독 목록을 반환한다."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_email == user_email)
    )
    return list(result.scalars().all())


# ============================================================
# 연산 헬퍼 — 타입 안전 + NaN 방어
# ============================================================
def _hours_since(published_at, now: datetime | None = None) -> float:
    """
    기사 발행 후 경과 시간(시간 단위)을 안전하게 계산한다.

    ■ Bug #3 타임존 충돌 방어:
      - published_at이 None이거나 datetime이 아니면 0.0 반환 (최신 기사로 간주)
      - tz-aware와 tz-naive가 혼재해도 양쪽 모두 UTC aware로 정규화
      - 어떤 예외가 발생해도 0.0 반환 (방어적 폴백)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(published_at, datetime):
        return 0.0

    try:
        # 양쪽 모두 UTC aware로 통일
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        delta = now - published_at
        return max(0.0, delta.total_seconds() / 3600.0)
    except Exception:
        return 0.0


def _safe_cosine(distance) -> float:
    """pgvector 코사인 거리를 유사도(0~1)로 변환한다. NaN/None 방어."""
    if distance is None:
        return 0.5  # 중립값
    try:
        val = 1.0 - float(distance)
        if math.isnan(val) or math.isinf(val):
            return 0.5
        return max(0.0, min(1.0, val))
    except (TypeError, ValueError):
        return 0.5


def _safe_disinterest(distance) -> float:
    """비관심 거리를 유사도(0~1)로 변환한다. NaN/None이면 패널티 없음(0.0)."""
    if distance is None:
        return 0.0
    try:
        val = 1.0 - float(distance)
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return max(0.0, min(1.0, val))
    except (TypeError, ValueError):
        return 0.0


def _safe_credibility(credibility) -> float:
    """신뢰도 점수를 0~1 범위로 정규화한다. None/비정상 방어."""
    try:
        val = float(credibility or 0) / 100.0
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return max(0.0, min(1.0, val))
    except (TypeError, ValueError):
        return 0.0


def _check_subscribed(
    article: Article,
    subscribed_press: set[str],
    subscribed_journalists: set[str],
) -> bool:
    """
    기사가 구독 대상인지 판별한다 (반드시 bool 반환).
    Python 단축평가 버그 방어: `x and ...`는 x=None이면 None 반환 → bool() 래핑.
    """
    return bool(
        article.press in subscribed_press
        or (
            article.journalist is not None
            and article.journalist in subscribed_journalists
        )
    )


def _vector_literal(vector) -> str:
    """파이썬 벡터를 pgvector 문자열 리터럴로 변환한다."""
    if vector is None:
        return "[" + ",".join(["0.0"] * settings.EMBEDDING_DIM) + "]"
    if isinstance(vector, str):
        return vector
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


def _make_feed_item(
    article: Article,
    is_subscribed: bool,
    score: float,
    is_read: bool = False,
) -> FeedItem:
    """Article ORM 객체를 FeedItem으로 변환한다."""
    return FeedItem(
        article=ArticleSummary(
            url=article.url,
            title=article.title or "",
            summary=article.summary or "",
            category=article.category or "",
            credibility=float(article.credibility or 0),
            rb01_tone=article.rb01_tone,
            rb02_density=article.rb02_density,
            rb03_quotes=article.rb03_quotes,
            rb04_journalist=article.rb04_journalist,
            press=article.press or "",
            journalist=article.journalist,
            published_at=article.published_at,
        ),
        score=round(score, 4),
        is_subscribed=is_subscribed,
        is_read=is_read,
        credibility_badge=FeedItem.compute_badge(float(article.credibility or 0)),
    )
