"""
SQLAlchemy ORM 모델 정의 (PostgreSQL + pgvector)
=================================================

테이블 구조:
  - Article   : 뉴스 기사 (URL이 PK, 768차원 임베딩 벡터 포함)
  - User      : 사용자 (이메일이 PK, 관심/비관심 벡터 포함)
  - Subscription : 사용자의 언론사/기자 구독 정보
  - ReadLog   : 기사 읽음 로그 (피드백 벡터 업데이트 추적용)
  - DislikeLog : 관심없음 로그 (Undo 기능 지원을 위해 별도 관리)

pgvector 인덱스:
  - Article.embedding, User.interest_vector, User.disinterest_vector에
    HNSW 인덱스를 적용하여 코사인 유사도 검색 성능을 확보한다.
"""

from datetime import datetime
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.database import Base

# ── 벡터 차원 상수 ──
DIM = settings.EMBEDDING_DIM  # 768


# ============================================================
# Enum: 기사 카테고리 (6개)
# ============================================================
class CategoryEnum(str, PyEnum):
    """네이버 뉴스 6대 카테고리"""
    POLITICS = "정치"
    ECONOMY = "경제"
    SOCIETY = "사회"
    CULTURE = "생활/문화"
    TECH = "IT/과학"
    WORLD = "세계"


# ============================================================
# Article 테이블
# ============================================================
class Article(Base):
    """
    뉴스 기사 테이블.

    - url (PK)        : 기사 고유 URL. 중복 수집 방지용 자연키.
    - title           : 기사 제목
    - body            : 기사 본문 전체 텍스트
    - summary         : LLM이 생성한 3줄 요약
    - category        : 6개 카테고리 중 하나 (LLM 태깅)
    - embedding       : Ko-SBERT로 '제목 + 요약'을 인코딩한 768차원 벡터.
                        pgvector의 <=> 연산자로 코사인 유사도 검색에 사용.
    - credibility     : 신뢰도 점수 (0~100).
                        문체 중립성(30%) + 정보 밀도(25%) + 인용구(25%) + 기자 실명(20%)
    - press           : 언론사명
    - journalist      : 기자 실명 (없으면 NULL)
    - published_at    : 기사 발행 시간 (최신성 점수 산출에 사용)
    """
    __tablename__ = "articles"

    url: Mapped[str] = mapped_column(String(2048), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="CategoryEnum 값 중 하나",
    )

    # pgvector 768차원 벡터 컬럼
    # HNSW 인덱스: 코사인 거리(cosine) 기반 근사 최근접 이웃 검색
    embedding: Mapped[list] = mapped_column(
        Vector(DIM),
        nullable=False,
        comment="Ko-SBERT 768차원 임베딩",
    )

    # 신뢰도 점수: 0~100 범위 (Float로 소수점까지 보관)
    credibility: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="기사 신뢰도 점수 (0~100)",
    )
    press: Mapped[str] = mapped_column(String(100), nullable=False)
    journalist: Mapped[str | None] = mapped_column(String(100), nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    # 레코드 관리용 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # ── 인덱스 정의 ──
    __table_args__ = (
        # pgvector HNSW 인덱스 (코사인 거리)
        # m=16: 그래프 연결 수, ef_construction=200: 인덱스 빌드 정밀도
        Index(
            "ix_articles_embedding_hnsw",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # 카테고리 + 발행시간 복합 인덱스 (카테고리별 최신 기사 조회 최적화)
        Index("ix_articles_category_published", "category", "published_at"),
    )


# ============================================================
# User 테이블
# ============================================================
class User(Base):
    """
    사용자 테이블.

    - email (PK)          : 이메일 주소를 사용자 식별자로 사용
    - hashed_password     : bcrypt 해시 + salt 적용된 비밀번호
    - name                : 사용자 표시 이름
    - interest_categories : 가입 시 선택한 관심 카테고리 2개 (ARRAY)
    - interest_vector     : 관심 벡터 (768차원). 기사 읽음 시 EMA 업데이트.
                            V_new = 0.15 × V_article + 0.85 × V_old
    - disinterest_vector  : 비관심 벡터 (768차원). 관심없음 시 EMA 업데이트.
                            V_new = 0.10 × V_article + 0.90 × V_old
    - font_size_level     : 접근성 글자 크기 단계 (0=소, 1=중, 2=대, 3=특대)

    콜드 스타트 초기화:
      신규 가입 시 선택한 2개 카테고리의 평균 벡터를 interest_vector 초기값으로 설정.
      disinterest_vector는 영벡터로 초기화.
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    hashed_password: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="bcrypt 해시 (salt 포함)",
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    # 관심 카테고리 2개를 PostgreSQL ARRAY로 저장
    interest_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)),
        nullable=False,
        comment="가입 시 선택한 관심 카테고리 2개",
    )

    # 관심 벡터: 기사 읽음 피드백으로 점진적 업데이트 (EMA α=0.15)
    interest_vector: Mapped[list] = mapped_column(
        Vector(DIM),
        nullable=False,
        comment="사용자 관심 벡터 (768차원, EMA 업데이트)",
    )

    # 비관심 벡터: '관심없음' 피드백으로 점진적 업데이트 (EMA α=0.10)
    disinterest_vector: Mapped[list] = mapped_column(
        Vector(DIM),
        nullable=False,
        comment="사용자 비관심 벡터 (768차원, EMA 업데이트)",
    )

    # 접근성: 글자 크기 단계 (0=소, 1=중, 2=대, 3=특대)
    font_size_level: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
        comment="글자 크기 단계: 0=소, 1=중, 2=대, 3=특대",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # ── 관계(Relationships) ──
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )
    read_logs: Mapped[list["ReadLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )
    dislike_logs: Mapped[list["DislikeLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )

    # ── 인덱스 정의 ──
    __table_args__ = (
        # 관심 벡터 HNSW 인덱스 (추천 알고리즘에서 사용)
        Index(
            "ix_users_interest_hnsw",
            interest_vector,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"interest_vector": "vector_cosine_ops"},
        ),
    )


# ============================================================
# Subscription 테이블 (구독 정보)
# ============================================================
class Subscription(Base):
    """
    사용자의 언론사/기자 구독 테이블.
    추천 알고리즘에서 구독 부스트(×1.3) 적용 시 참조.
    """
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str] = mapped_column(
        ForeignKey("users.email", ondelete="CASCADE"), nullable=False,
    )
    # 구독 대상 유형: "press" (언론사) 또는 "journalist" (기자)
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="구독 유형: 'press' 또는 'journalist'",
    )
    # 구독 대상 이름 (언론사명 또는 기자명)
    target_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        # 동일 사용자가 같은 대상을 중복 구독하지 못하도록 유니크 제약
        Index(
            "uq_subscription_user_target",
            "user_email", "target_type", "target_name",
            unique=True,
        ),
    )


# ============================================================
# ReadLog 테이블 (기사 읽음 로그)
# ============================================================
class ReadLog(Base):
    """
    기사 읽음 기록.
    - 관심 벡터 EMA 업데이트 이력 추적
    - 이미 읽은 기사를 피드에서 중복 노출하지 않기 위한 필터링 용도
    """
    __tablename__ = "read_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str] = mapped_column(
        ForeignKey("users.email", ondelete="CASCADE"), nullable=False,
    )
    article_url: Mapped[str] = mapped_column(
        ForeignKey("articles.url", ondelete="CASCADE"), nullable=False,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="read_logs")
    article: Mapped["Article"] = relationship()

    __table_args__ = (
        Index("ix_readlog_user_article", "user_email", "article_url"),
    )


# ============================================================
# DislikeLog 테이블 (관심없음 로그)
# ============================================================
class DislikeLog(Base):
    """
    관심없음 기록.
    - is_active=True: 현재 관심없음 상태 (피드에서 제외)
    - is_active=False: Undo로 취소됨
    - 비관심 벡터 EMA 업데이트 이력 추적
    """
    __tablename__ = "dislike_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str] = mapped_column(
        ForeignKey("users.email", ondelete="CASCADE"), nullable=False,
    )
    article_url: Mapped[str] = mapped_column(
        ForeignKey("articles.url", ondelete="CASCADE"), nullable=False,
    )
    # Undo 기능 지원: is_active=False면 Undo된 상태
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="dislike_logs")
    article: Mapped["Article"] = relationship()

    __table_args__ = (
        Index("ix_dislikelog_user_active", "user_email", "is_active"),
    )
