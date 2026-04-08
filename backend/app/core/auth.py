"""
JWT 인증 의존성 모듈
=====================

FastAPI의 Depends()를 통해 현재 로그인된 사용자 정보를 주입한다.

흐름:
  1. Authorization 헤더에서 Bearer 토큰 추출
  2. JWT 디코딩 → 이메일(sub) 추출
  3. DB에서 User 객체 조회 → 반환

API 라우터에서 사용:
  @router.get("/feed")
  async def get_feed(user: User = Depends(get_current_user)):
      ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import User

# OAuth2 Bearer 토큰 추출기 (Authorization: Bearer <token>)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    JWT 토큰에서 현재 사용자를 추출하여 반환한다.

    Raises:
        HTTPException 401: 토큰이 유효하지 않거나 사용자가 존재하지 않을 때
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.get(User, email)
    if user is None:
        raise credentials_exception

    return user
