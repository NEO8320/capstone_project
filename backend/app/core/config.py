"""
애플리케이션 환경 설정 모듈
- pydantic-settings를 활용하여 .env 파일 또는 환경 변수에서 설정값을 로드
- 모든 민감 정보(DB 비밀번호, API 키 등)는 환경 변수로 관리
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── .env 의 절대 경로 ──
# pydantic-settings 는 env_file 을 cwd 기준 상대경로로 해석하기 때문에,
# start_backend.py 가 cwd 를 프로젝트 루트로 chdir 하면 backend/.env 를 못 찾는다.
# 이 모듈 자신의 위치(backend/app/core/config.py) 기준으로 절대경로를 계산하여
# cwd 와 무관하게 항상 backend/.env 를 로드하도록 한다.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
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
    # ★ 카테고리 이름은 config.yaml의 categories 섹션과 완전히 동일한 가운뎃점(·) 형식
    #   으로 유지해야 한다 (크롤러 → DB → 피드 필터 → 프론트엔드 전 구간 일관성 보장).
    CRAWL_CATEGORIES: list[str] = [
        "정치", "경제", "사회", "생활·문화", "IT·과학", "세계", "연예", "스포츠",
    ]

    # ── 서버 시작 시 즉시 크롤링 옵션 ──
    # 서버 가동과 동시에 1회 크롤링을 실행하여 빈 DB 문제를 방지한다.
    CRAWL_ON_STARTUP: bool = True                # True면 서버 시작 직후 1회 즉시 크롤링
    AUTO_SEED_ON_EMPTY_DB: bool = True           # 크롤링 전 DB가 비어 있으면 샘플 기사 자동 시드
    STARTUP_CRAWL_RETRY_ON_ZERO: int = 1         # 즉시 크롤링이 0건이면 60초 후 재시도 횟수
    DB_INIT_MAX_RETRIES: int = 5                 # init_db() 지수 백오프 최대 시도
    DB_INIT_INITIAL_DELAY: float = 2.0           # init_db() 첫 재시도 대기 시간 (초)

    # ── Rate Limiting 설정 ──
    RATE_LIMIT: str = "60/minute"  # 분당 60회 제한


settings = Settings()
