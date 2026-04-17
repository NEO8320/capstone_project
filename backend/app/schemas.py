"""
Pydantic v2 스키마 정의
========================

API 요청/응답의 데이터 검증 및 직렬화를 담당한다.
SQLAlchemy 모델과 1:1 대응하되, API 계층에서 필요한 필드만 노출한다.

구조:
  - Auth 관련: UserCreate, UserLogin, TokenResponse
  - Article 관련: ArticleResponse, ArticleSummary
  - Feed 관련: FeedResponse, FeedItem (추천 점수 포함)
  - Subscription 관련: SubscriptionCreate, SubscriptionResponse
  - 피드백 관련: ReadResponse, DislikeResponse
  - 설정 관련: UserSettingsUpdate
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator


# ============================================================
# Enum
# ============================================================
class CategoryEnum(str, Enum):
    """기사 카테고리 8종"""
    POLITICS = "정치"
    ECONOMY = "경제"
    SOCIETY = "사회"
    CULTURE = "생활·문화"
    TECH = "IT·과학"
    WORLD = "세계"
    ENTERTAINMENT = "연예"
    SPORTS = "스포츠"


class SubscriptionTargetType(str, Enum):
    """구독 대상 유형"""
    PRESS = "press"
    JOURNALIST = "journalist"


# ============================================================
# Auth (인증) 스키마
# ============================================================
class UserCreate(BaseModel):
    """
    회원가입 요청 스키마.
    - interest_categories: 1개 이상 자유 선택 (2개 이상 권장)
    - password: 최소 8자 이상
    """
    email: EmailStr
    password: str = Field(min_length=8, description="비밀번호 (최소 8자)")
    name: str = Field(min_length=1, max_length=50)
    interest_categories: list[CategoryEnum] = Field(
        min_length=1, max_length=8,
        description="관심 카테고리 1개 이상 선택 (콜드 스타트 초기화용, 2개 이상 권장)",
    )

    @field_validator("interest_categories")
    @classmethod
    def validate_unique_categories(cls, v: list[CategoryEnum]) -> list[CategoryEnum]:
        """중복 카테고리 선택 방지"""
        if len(set(v)) != len(v):
            raise ValueError("서로 다른 카테고리를 선택해 주세요.")
        return v


class UserLogin(BaseModel):
    """로그인 요청 스키마"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT 토큰 응답 스키마"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """POST /auth/refresh 요청 스키마"""
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """POST /auth/forgot-password 요청 스키마"""
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """POST /auth/forgot-password 응답 스키마"""
    message: str
    # 개발/데모 환경에서만 노출 — 실제 서비스에서는 이메일로만 전달
    reset_link: str | None = None


class ResetPasswordRequest(BaseModel):
    """POST /auth/reset-password 요청 스키마"""
    token: str
    new_password: str = Field(min_length=8, description="새 비밀번호 (최소 8자)")


class ChangePasswordRequest(BaseModel):
    """PATCH /users/me/password 요청 스키마"""
    current_password: str
    new_password: str = Field(min_length=8, description="새 비밀번호 (최소 8자)")


class UserResponse(BaseModel):
    """사용자 정보 응답 (비밀번호 제외)"""
    email: str
    name: str
    interest_categories: list[str]
    font_size_level: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Article (기사) 스키마
# ============================================================
class ArticleResponse(BaseModel):
    """
    기사 상세 응답 스키마.
    임베딩 벡터는 클라이언트에 노출하지 않는다.
    """
    url: str
    title: str
    summary: str
    category: str
    credibility: float = Field(ge=0, le=100, description="신뢰도 점수 (0~100)")
    press: str
    journalist: str | None
    published_at: datetime

    model_config = {"from_attributes": True}


class ArticleDetailResponse(BaseModel):
    """
    기사 상세 페이지 응답 (본문 + 구독 여부 + 신뢰도 sub-score 포함).
    GET /api/articles/{url} 에서 반환.
    """
    url: str
    title: str
    body: str
    summary: str
    category: str
    credibility: float = Field(ge=0, le=100, description="신뢰도 종합 점수 (0~100)")
    # ── 신뢰도 sub-score (RB-01~RB-04) ──
    # NULL이면 프론트엔드가 종합 점수에서 결정론적 합성 (기존 기사 호환)
    rb01_tone: float | None = Field(default=None, description="RB-01 문체 중립성 (0~100)")
    rb02_density: float | None = Field(default=None, description="RB-02 정보 밀도 (0~100)")
    rb03_quotes: float | None = Field(default=None, description="RB-03 인용구 존재 (0~100)")
    rb04_journalist: float | None = Field(default=None, description="RB-04 기자 실명 (0~100)")
    press: str
    journalist: str | None
    published_at: datetime
    # 구독 여부 및 구독 ID (구독 해제 시 사용)
    press_subscribed: bool = False
    press_sub_id: int | None = None
    journalist_subscribed: bool = False
    journalist_sub_id: int | None = None

    model_config = {"from_attributes": True}


class ArticleSummary(BaseModel):
    """피드에서 사용하는 기사 요약 정보 (본문 제외, sub-score 포함)"""
    url: str
    title: str
    summary: str
    category: str
    credibility: float
    # ── 신뢰도 sub-score (피드 카드 뱃지 + 상세 페이지 차트 겸용) ──
    rb01_tone: float | None = None
    rb02_density: float | None = None
    rb03_quotes: float | None = None
    rb04_journalist: float | None = None
    press: str
    journalist: str | None
    published_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Feed (추천 피드) 스키마
# ============================================================
class FeedItem(BaseModel):
    """
    추천 피드의 개별 기사 항목.
    추천 점수(score)를 포함하여 클라이언트에서 정렬/표시에 활용.

    점수 산출 공식:
      Score = (유사도 × 0.40) + (최신성 × 0.15) + (구독부스트 × 0.20)
              + (신뢰도 × 0.15) - (비관심 패널티 × 0.25)
    """
    article: ArticleSummary
    score: float = Field(description="개인화 추천 점수")
    is_subscribed: bool = Field(
        default=False,
        description="구독 언론사/기자의 기사인지 여부",
    )
    is_read: bool = Field(
        default=False,
        description="이미 읽은 기사 여부 (피드에서 시각적으로 흐리게 표시).",
    )

    # 신뢰도 배지 레벨: 프론트엔드에서 색상 매핑에 사용
    # "green" (90+), "yellow" (70~89), "red" (69 이하)
    credibility_badge: str = Field(description="신뢰도 배지: green/yellow/red")

    @staticmethod
    def compute_badge(credibility: float) -> str:
        """신뢰도 점수를 3단계 배지로 변환"""
        if credibility >= 90:
            return "green"
        elif credibility >= 70:
            return "yellow"
        return "red"


class FeedResponse(BaseModel):
    """
    GET /feed 응답 스키마.
    피드 상단 구독 트랙(최대 10건)과 하단 추천 트랙을 분리하여 전달.
    """
    subscription_track: list[FeedItem] = Field(
        max_length=10,
        description="구독 언론사/기자의 최신 기사 (최대 10건)",
    )
    recommendation_track: list[FeedItem] = Field(
        description="개인화 추천 기사 목록 (점수 내림차순)",
    )


# ============================================================
# Subscription (구독) 스키마
# ============================================================
class SubscriptionCreate(BaseModel):
    """구독 추가 요청"""
    target_type: SubscriptionTargetType
    target_name: str = Field(min_length=1, max_length=100)


class SubscriptionResponse(BaseModel):
    """구독 정보 응답"""
    id: int
    target_type: str
    target_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Feedback (피드백) 스키마
# ============================================================
class ReadResponse(BaseModel):
    """
    POST /articles/{url}/read 응답.
    관심 벡터 EMA 업데이트 완료를 알린다.
    V_new = 0.15 × V_article + 0.85 × V_old
    """
    message: str = "읽음 처리 완료. 관심 벡터가 업데이트되었습니다."
    article_url: str


class DislikeResponse(BaseModel):
    """
    POST /articles/{url}/dislike 응답.
    비관심 벡터 EMA 업데이트 및 피드 제거 완료를 알린다.
    V_new = 0.10 × V_article + 0.90 × V_old
    """
    message: str = "관심없음 처리 완료. 5초 내 Undo 가능합니다."
    article_url: str
    dislike_id: int = Field(description="Undo 시 사용할 DislikeLog ID")


class UndoDislikeRequest(BaseModel):
    """POST /api/v1/feed/dislike/undo 요청 (API-07)"""
    article_id: str = Field(description="관심없음 취소할 기사 URL (article PK)")


class UndoDislikeResponse(BaseModel):
    """POST /api/v1/feed/dislike/undo 응답 (API-07)"""
    message: str = "관심없음이 취소되었습니다. 비관심 벡터가 복구되었습니다."
    article_url: str


# ============================================================
# Settings (설정) 스키마
# ============================================================
class UserSettingsUpdate(BaseModel):
    """
    사용자 설정 업데이트 요청.
    현재는 글자 크기 단계만 지원. 추후 확장 가능.
    """
    font_size_level: int = Field(
        ge=0, le=3,
        description="글자 크기 단계: 0=소, 1=중, 2=대, 3=특대",
    )


class UserProfileUpdate(BaseModel):
    """
    PATCH /api/users/me 요청.
    None 값은 무시(변경 없음), 전달된 값만 업데이트.
    """
    interest_categories: list[CategoryEnum] | None = Field(
        default=None,
        min_length=1,
        max_length=8,
        description="관심 카테고리 1개 이상 (변경 시 필수, 2개 이상 권장)",
    )
    font_size_level: int | None = Field(
        default=None, ge=0, le=3,
        description="글자 크기 단계: 0=소, 1=중, 2=대, 3=특대",
    )
