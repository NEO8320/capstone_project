"""
피드 API 라우터 (GET /feed)
============================

사용자 맞춤형 개인화 뉴스 피드를 반환한다.

응답 구조:
  - subscription_track: 구독 언론사/기자의 최신 기사 (최대 10건, 피드 상단)
  - recommendation_track: 추천 점수 기반 기사 (점수 내림차순, 피드 하단)

추천 스코어 공식:
  Score = (임베딩 유사도 × 0.40) + (최신성 × 0.15) + (구독 부스트 × 0.20)
        + (신뢰도 × 0.15) - (비관심 패널티 × 0.25)

캐싱:
  Redis에 "user:{email}:feed" 키로 5분간 캐싱.
  피드백(읽음/관심없음) 발생 시 즉시 무효화.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.redis import get_redis
from app.models import User
from app.schemas import FeedResponse
from app.services.recommendation import get_personalized_feed

router = APIRouter()


@router.get("/feed", response_model=FeedResponse, summary="개인화 추천 피드 조회")
@limiter.limit(settings.RATE_LIMIT)
async def get_feed(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    현재 로그인된 사용자의 개인화 뉴스 피드를 반환한다.

    ■ 구독 트랙 (상단, 최대 10건):
      사용자가 구독한 언론사/기자의 최신 기사를 최신순으로 표시.

    ■ 추천 트랙 (하단, 최대 50건):
      추천 스코어 공식에 따라 계산된 점수 내림차순 정렬.
      이미 읽은 기사와 '관심없음' 처리된 기사는 제외.

    ■ 캐싱:
      Redis에 5분간 캐싱하여 동일 요청 시 DB 부하를 줄인다.
      피드백 발생 시 캐시가 즉시 무효화되어 최신 상태를 반영.
    """
    # Redis 연결 시도 (연결 실패 시 None → 캐싱 없이 동작)
    try:
        redis = get_redis()
    except RuntimeError:
        redis = None

    return await get_personalized_feed(user=user, db=db, redis=redis)
