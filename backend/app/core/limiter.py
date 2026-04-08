"""
Rate Limiter 싱글턴 모듈
=========================

순환 임포트를 방지하기 위해 main.py에서 분리.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# 클라이언트 IP 기반 분당 60회 제한
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT])
