"""
애플리케이션 환경 설정 모듈
- pydantic-settings를 활용하여 .env 파일 또는 환경 변수에서 설정값을 로드
- 모든 민감 정보(DB 비밀번호, API 키 등)는 환경 변수로 관리
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── 애플리케이션 기본 설정 ──
    APP_NAME: str = "News Curator"
    DEBUG: bool = False

    # ── PostgreSQL + pgvector 연결 설정 ──
    # asyncpg 드라이버를 사용한 비동기 연결 문자열
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/news_curator"

    # ── Redis 캐시 설정 ──
    REDIS_URL: str = "redis://localhost:6379/0"
    FEED_CACHE_TTL: int = 300  # 피드 캐시 만료 시간 (초), 기본 5분

    # ── JWT 인증 설정 ──
    SECRET_KEY: str = "change-this-to-a-secure-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 외부 API 키 (모두 Optional — 로컬 모델 사용 시 비워둬도 됨) ──
    NAVER_CLIENT_ID: str = ""
    NAVER_CLIENT_SECRET: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # ── LLM 엔진 설정 (NFR-E03: 환경변수로 유연하게 교체 가능) ──
    # 1순위: 로컬 Ollama (Llama 3)
    LLM_PRIMARY_MODEL: str = "llama3"
    LLM_PRIMARY_BASE_URL: str = "http://localhost:11434/v1"
    # 2순위: Claude Haiku (Anthropic API — API 키 있을 때만 활성)
    LLM_FALLBACK_CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"
    # 3순위: OpenAI 호환 원격 (API 키 있을 때만 활성)
    LLM_FALLBACK_OPENAI_MODEL: str = "gpt-4o-mini"
    LLM_FALLBACK_OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # ── Ko-SBERT 임베딩 모델 설정 ──
    EMBEDDING_MODEL_NAME: str = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
    EMBEDDING_DIM: int = 768  # Ko-SBERT 출력 벡터 차원

    # ── APScheduler 크롤링 설정 ──
    CRAWL_INTERVAL_HOURS: int = 1  # 크롤링 주기 (시간)
    CRAWL_CATEGORIES: list[str] = [
        "정치", "경제", "사회", "생활/문화", "IT/과학", "세계"
    ]

    # ── Rate Limiting 설정 ──
    RATE_LIMIT: str = "60/minute"  # 분당 60회 제한


settings = Settings()
