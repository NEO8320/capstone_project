"""
인증 API 라우터 (회원가입 / 로그인 / 토큰 갱신)
================================================

■ POST /auth/register  (API-01) — 회원가입
■ POST /auth/login     (API-02) — 로그인
■ POST /auth/refresh   (API-03) — Access Token 갱신
"""

import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
)
from app.services.embedding import compute_cold_start_vector, get_zero_vector

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ============================================================
# API-01: 회원가입
# ============================================================
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    신규 사용자 회원가입.
    - 이메일 중복 확인
    - 비밀번호 bcrypt 해시
    - 콜드 스타트: 선택한 2개 카테고리 평균 벡터로 interest_vector 초기화
    - 가입 즉시 JWT 토큰 발급
    """
    # 이메일 중복 확인
    existing = await db.get(User, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )

    # 콜드 스타트 벡터 초기화 (모델 로딩 실패/타임아웃 시 랜덤 정규화 벡터 사용)
    categories = [cat.value for cat in body.interest_categories]
    try:
        interest_vector = await asyncio.wait_for(
            compute_cold_start_vector(categories), timeout=60.0
        )
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[Register] 콜드 스타트 벡터 생성 실패, 폴백 사용: {e}")
        rng = np.random.default_rng()
        v = rng.standard_normal(settings.EMBEDDING_DIM).astype(np.float64)
        interest_vector = (v / np.linalg.norm(v)).tolist()
    disinterest_vector = get_zero_vector()

    user = User(
        email=body.email,
        hashed_password=_hash_password(body.password),
        name=body.name,
        interest_categories=categories,
        interest_vector=interest_vector,
        disinterest_vector=disinterest_vector,
        font_size_level=1,
    )
    db.add(user)
    await db.commit()

    access_token = _create_token(
        {"sub": user.email},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = _create_token(
        {"sub": user.email, "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ============================================================
# API-01b: 게스트 로그인 (계정 없이 둘러보기)
# ============================================================
# 공용 게스트 계정 1개를 멱등하게 보장 생성하고 토큰을 발급한다.
# 시연 시 평가자가 회원가입 없이 즉시 서비스를 체험할 수 있게 한다.
GUEST_EMAIL = "guest@newscurator.demo"
# 게스트 초기 관심 카테고리 (대표 3종) — 콜드 스타트 벡터 시드로 사용
GUEST_CATEGORIES = ["정치", "경제", "IT·과학"]


@router.post("/guest", response_model=TokenResponse, summary="게스트 로그인 (계정 없이 둘러보기)")
async def guest_login(db: AsyncSession = Depends(get_db)):
    """
    공용 게스트 계정으로 로그인한다.
    - 게스트 계정이 없으면 생성(멱등), 있으면 재사용
    - 일반 로그인과 동일한 JWT 토큰 발급 → 이후 흐름은 일반 회원과 동일

    참고: 게스트는 공용 계정이므로 읽음/관심없음 피드백이 공유된다.
          시연 후 데이터 초기화로 정리한다.
    """
    import secrets as _secrets

    from sqlalchemy.exc import IntegrityError

    user = await db.get(User, GUEST_EMAIL)
    if not user:
        # 콜드 스타트 벡터 (대표 카테고리 평균, 실패 시 랜덤 정규화 폴백)
        try:
            interest_vector = await asyncio.wait_for(
                compute_cold_start_vector(GUEST_CATEGORIES), timeout=60.0
            )
        except (asyncio.TimeoutError, Exception) as e:
            print(f"[Guest] 콜드 스타트 벡터 생성 실패, 폴백 사용: {e}")
            rng = np.random.default_rng()
            v = rng.standard_normal(settings.EMBEDDING_DIM).astype(np.float64)
            interest_vector = (v / np.linalg.norm(v)).tolist()

        user = User(
            email=GUEST_EMAIL,
            hashed_password=_hash_password(_secrets.token_hex(16)),  # 직접 로그인 불가
            name="게스트",
            interest_categories=GUEST_CATEGORIES,
            interest_vector=interest_vector,
            disinterest_vector=get_zero_vector(),
            font_size_level=1,
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:
            # 동시 요청으로 이미 생성된 경우 — 롤백 후 재조회
            await db.rollback()
            user = await db.get(User, GUEST_EMAIL)

    access_token = _create_token(
        {"sub": user.email},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = _create_token(
        {"sub": user.email, "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ============================================================
# API-02: 로그인
# ============================================================
@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """이메일 + 비밀번호로 로그인 후 JWT 토큰 발급."""
    user = await db.get(User, body.email)
    if not user or not _verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    access_token = _create_token(
        {"sub": user.email},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = _create_token(
        {"sub": user.email, "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ============================================================
# API-03: Access Token 갱신
# ============================================================
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh Token으로 새 Access Token 발급."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않은 리프레시 토큰입니다.",
    )
    try:
        payload = jwt.decode(
            body.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        if payload.get("type") != "refresh":
            raise credentials_exception
        email: str | None = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.get(User, email)
    if not user:
        raise credentials_exception

    access_token = _create_token(
        {"sub": user.email},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_refresh_token = _create_token(
        {"sub": user.email, "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


# ============================================================
# API-04: 비밀번호 찾기 — 재설정 토큰 발급
# ============================================================
@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="비밀번호 재설정 링크 발급",
)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    이메일로 비밀번호 재설정 링크를 발급한다.

    보안상 이유로 이메일 존재 여부와 관계없이 동일한 메시지를 반환한다.
    재설정 토큰은 JWT (type=password_reset, 15분 유효)로 발급된다.

    ※ 데모/개발 환경: reset_link를 응답에 직접 포함.
       실제 서비스에서는 이 필드를 제거하고 SMTP 이메일 발송으로 대체한다.
    """
    user = await db.get(User, body.email)

    reset_link = None
    if user:
        reset_token = _create_token(
            {"sub": user.email, "type": "password_reset"},
            timedelta(minutes=15),
        )
        reset_link = f"http://localhost:5173/reset-password?token={reset_token}"
        # TODO 실제 서비스: await send_reset_email(user.email, reset_link)
        print(f"[Auth] 비밀번호 재설정 링크: {reset_link}")

    return ForgotPasswordResponse(
        message="해당 이메일로 재설정 링크를 발송했습니다. 이메일을 확인해 주세요.",
        reset_link=reset_link,  # 데모용: 실제 서비스에서는 None으로 고정
    )


# ============================================================
# API-05: 비밀번호 재설정 — 토큰 검증 후 비밀번호 변경
# ============================================================
@router.post(
    "/reset-password",
    summary="비밀번호 재설정",
)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    재설정 토큰(JWT)을 검증하고 새 비밀번호로 변경한다.
    토큰은 15분간만 유효하다.
    """
    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="만료되었거나 유효하지 않은 토큰입니다.",
    )
    try:
        payload = jwt.decode(
            body.token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        if payload.get("type") != "password_reset":
            raise invalid_exc
        email: str | None = payload.get("sub")
        if not email:
            raise invalid_exc
    except JWTError:
        raise invalid_exc

    user = await db.get(User, email)
    if not user:
        raise invalid_exc  # 사용자 존재 여부 노출 방지

    user.hashed_password = _hash_password(body.new_password)
    await db.commit()

    return {"message": "비밀번호가 재설정되었습니다. 새 비밀번호로 로그인해 주세요."}
