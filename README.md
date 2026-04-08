# News Curator - AI 기반 나만의 뉴스 큐레이팅 서비스

> 사용자의 관심사를 학습하여 맞춤형 뉴스를 추천하는 AI 뉴스 큐레이팅 플랫폼

---

## 프로젝트 개요

News Curator는 AI 기술을 활용하여 사용자별 개인화된 뉴스 피드를 제공하는 풀스택 웹 서비스입니다. 네이버 뉴스 API로 기사를 수집하고, 로컬 LLM(Llama 3)으로 기사를 요약/분류하며, Ko-SBERT 임베딩과 코사인 유사도 기반 추천 알고리즘으로 사용자의 관심사에 맞는 뉴스를 실시간으로 추천합니다.

### 핵심 차별점

- **완전 로컬 AI 파이프라인**: Ollama(Llama 3)를 활용한 기사 요약/분류로 외부 API 의존도를 최소화
- **실시간 관심사 학습**: EMA(지수이동평균) 알고리즘으로 사용자 피드백을 즉시 반영
- **뉴스 신뢰도 점수**: 문체 중립성, 정보 밀도, 인용구 존재, 기자 실명을 기반으로 0~100점 자동 산출
- **노년층 접근성**: WCAG AA 색상 대비 준수 및 4단계 글자 크기 조정

---

## 주요 기능

### 1. AI 기사 요약 및 카테고리 분류
- 로컬 Llama 3 모델(Ollama)로 기사 본문을 3줄 요약
- 6개 카테고리(정치/경제/사회/생활문화/IT과학/세계) 자동 분류
- LLM 3단계 폴백 체인: Ollama(1순위) -> Claude Haiku(2순위) -> GPT-4o-mini(3순위)

### 2. Ko-SBERT 벡터 임베딩 기반 추천
- `snunlp/KR-SBERT-V40K-klueNLI-augSTS` 모델로 기사를 768차원 벡터로 인코딩
- pgvector의 HNSW 인덱스를 활용한 코사인 유사도 검색
- **추천 스코어 공식**:
  ```
  Score = (임베딩_유사도 x 0.40) + (최신성 x 0.15) + (구독_부스트 x 0.20)
        + (신뢰도 x 0.15) - (비관심_패널티 x 0.25)
  ```
  - 기사 최신성: 시간 감쇠 함수 `exp(-0.05 x hours)`
  - 구독 부스트: 구독 언론사/기자 기사에 x1.3 배율 적용

### 3. EMA 피드백 벡터 업데이트
- 기사 읽음: `V_new = 0.15 x V_article + 0.85 x V_old` (관심 벡터)
- 관심없음: `V_new = 0.10 x V_article + 0.90 x V_old` (비관심 벡터)
- 콜드 스타트: 신규 사용자는 선택한 2개 카테고리의 평균 벡터로 초기화

### 4. 뉴스 신뢰도 점수 (0~100점)
| 항목 | 가중치 | 설명 |
|------|--------|------|
| 문체 중립성 | 30% | 감정적/선정적 표현 없을수록 고득점 |
| 정보 밀도 | 25% | 구체적 수치/데이터/팩트가 많을수록 고득점 |
| 인용구 존재 | 25% | 직접 인용구가 있으면 고득점 |
| 기자 실명 | 20% | 기자 실명 기재 시 100점 |

### 5. 가용성 제어 (비기능 요구사항)
- **서킷 브레이커**: 외부 API 5회 연속 실패 -> 30초간 호출 차단
- **백프레셔**: 대기큐 100건 초과 -> 일시 중지, 50건 이하 -> 재개
- **적응형 수집량**: CPU <50% -> 50건, 50~70% -> 30건, >70% -> 15건

### 6. 프론트엔드 접근성
- 구독 트랙(상단) / 추천 트랙(하단) 피드 분리
- 신뢰도 3단계 배지: 초록(90+) / 노랑(70~89) / 빨강(~69)
- 관심없음 5초 Undo 토스트
- WCAG AA 색상 대비 (15.4:1)
- 4단계 글자 크기 조정 (소/중/대/특대, localStorage 유지)
- 반응형 레이아웃: 데스크톱(1280px+) / 태블릿(768~1279px) / 모바일(~767px)

---

## 기술 스택

| 계층 | 기술 | 역할 |
|------|------|------|
| **프론트엔드** | React 18 + Vite | SPA, 반응형 UI |
| **HTTP 클라이언트** | Axios | JWT 인터셉터, Refresh Token 갱신 |
| **백엔드** | FastAPI (Python) | 비동기 REST API, 분당 60회 Rate Limiting |
| **ORM** | SQLAlchemy 2.0 (asyncpg) | 비동기 PostgreSQL 연결 |
| **데이터베이스** | PostgreSQL 16 + pgvector | 벡터 유사도 검색 (HNSW 인덱스) |
| **캐시** | Redis 7 | 피드 캐싱 (TTL 5분), 피드백 시 즉시 무효화 |
| **LLM (1순위)** | Llama 3 8B (Ollama) | 로컬 기사 요약, 카테고리 분류, 신뢰도 분석 |
| **LLM (폴백)** | Claude Haiku / GPT-4o-mini | 원격 API 폴백 |
| **임베딩** | Ko-SBERT (768차원) | 한국어 문장 임베딩 (코사인 유사도) |
| **스케줄러** | APScheduler | 1시간 주기 기사 수집 파이프라인 |
| **컨테이너** | Docker Compose | PostgreSQL + Redis 인프라 |

---

## 프로젝트 구조

```
news-curator/
├── run_all.bat              # Windows 통합 실행 스크립트
├── docker-compose.yml       # PostgreSQL(pgvector) + Redis
├── start_backend.py         # 백엔드 실행 래퍼
├── start_frontend.js        # 프론트엔드 실행 래퍼
│
├── backend/
│   ├── .env                 # 환경변수 (Git 제외)
│   ├── .env.example         # 환경변수 템플릿
│   ├── requirements.txt     # Python 의존성
│   └── app/
│       ├── main.py          # FastAPI 엔트리포인트
│       ├── models.py        # SQLAlchemy ORM (pgvector)
│       ├── schemas.py       # Pydantic v2 스키마
│       ├── core/
│       │   ├── config.py    # 환경 설정 (NFR-E03)
│       │   ├── database.py  # 비동기 DB 세션
│       │   ├── auth.py      # JWT 인증
│       │   ├── redis.py     # Redis 싱글턴
│       │   └── limiter.py   # Rate Limiter
│       ├── api/
│       │   ├── feed.py      # GET /api/feed
│       │   └── feedback.py  # POST read, POST/DELETE dislike
│       └── services/
│           ├── resilience.py      # 서킷브레이커, 백프레셔, 적응형수집
│           ├── crawler.py         # 네이버 뉴스 수집 + BeautifulSoup
│           ├── llm_processor.py   # LLM 3단계 폴백 체인
│           ├── embedding.py       # Ko-SBERT 768차원 임베딩
│           ├── recommendation.py  # 추천 스코어 엔진
│           └── pipeline.py        # APScheduler 파이프라인
│
└── frontend/
    ├── package.json
    ├── vite.config.js       # /api -> localhost:8000 프록시
    └── src/
        ├── main.jsx
        ├── App.jsx          # 루트 (피드/설정 탭)
        ├── index.css        # 글로벌 CSS (WCAG AA, 반응형)
        ├── api/
        │   ├── client.js    # Axios + JWT 인터셉터
        │   └── feed.js      # API 호출 함수
        └── components/
            ├── Feed.jsx           # 구독 트랙 + 추천 트랙
            ├── ArticleCard.jsx    # 기사 카드 (신뢰도 배지)
            ├── Toast.jsx          # Undo 토스트 (5초)
            └── Settings.jsx       # 글자 크기 4단계
```

---

## 시작하기 (Getting Started)

### 사전 설치 프로그램

시작하기 전에 아래 프로그램을 설치해 주세요:

| 프로그램 | 버전 | 용도 | 다운로드 |
|----------|------|------|----------|
| **Docker Desktop** | 최신 | PostgreSQL + Redis 컨테이너 | [docker.com](https://www.docker.com/products/docker-desktop/) |
| **Python** | 3.12+ | FastAPI 백엔드 | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 20+ | React 프론트엔드 | [nodejs.org](https://nodejs.org/) |
| **Ollama** | 최신 | 로컬 Llama 3 LLM | [ollama.com](https://ollama.com/download) |
| **Git** | 최신 | 소스 코드 관리 | [git-scm.com](https://git-scm.com/) |

### 설치 및 실행 순서

#### Step 1: 저장소 클론
```bash
git clone https://github.com/NEO8320/capstone_project.git
cd capstone_project
```

#### Step 2: Ollama에 Llama 3 모델 다운로드
```bash
ollama pull llama3
```
> 약 4.7GB 다운로드가 진행됩니다. 완료 후 `ollama run llama3`로 동작을 확인하세요.

#### Step 3: Docker 컨테이너 시작
```bash
# Docker Desktop이 실행 중인지 확인한 후:
docker-compose up -d
```
> PostgreSQL(pgvector) + Redis가 백그라운드에서 시작됩니다.

#### Step 4: 백엔드 환경 설정
```bash
cd backend

# 환경변수 파일 생성
cp .env.example .env

# Python 의존성 설치
pip install -r requirements.txt
```
> `.env` 파일을 열어 필요한 API 키를 입력하세요. 로컬 Ollama만 사용하면 LLM 관련 API 키는 비워둬도 됩니다.

#### Step 5: 프론트엔드 의존성 설치
```bash
cd ../frontend
npm install
```

#### Step 6: 서버 실행

**방법 A: 통합 실행 스크립트 (Windows, 권장)**
```bash
# 프로젝트 최상위 폴더에서:
run_all.bat
```

**방법 B: 수동 실행**
```bash
# 터미널 1 — 백엔드
cd capstone_project
python start_backend.py

# 터미널 2 — 프론트엔드
cd capstone_project/frontend
npx vite --host
```

#### Step 7: 브라우저에서 확인

| 서비스 | URL |
|--------|-----|
| 프론트엔드 | http://localhost:5173 |
| 백엔드 API | http://localhost:8000 |
| API 문서 (Swagger) | http://localhost:8000/docs |

---

## API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/feed` | 개인화 추천 피드 (구독 트랙 + 추천 트랙) |
| `POST` | `/api/articles/{url}/read` | 기사 읽음 + 관심 벡터 EMA 업데이트 |
| `POST` | `/api/articles/{url}/dislike` | 관심없음 + 비관심 벡터 EMA 업데이트 |
| `DELETE` | `/api/articles/{url}/dislike` | 관심없음 Undo |
| `GET` | `/health` | 서버 상태 확인 |

---

## 환경 변수 (.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/news_curator` | PostgreSQL 연결 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 연결 |
| `LLM_PRIMARY_MODEL` | `llama3` | 1순위 LLM 모델명 |
| `LLM_PRIMARY_BASE_URL` | `http://localhost:11434/v1` | 1순위 LLM API 주소 |
| `ANTHROPIC_API_KEY` | (빈 문자열) | Claude API 키 (선택) |
| `OPENAI_API_KEY` | (빈 문자열) | OpenAI API 키 (선택) |
| `EMBEDDING_MODEL_NAME` | `snunlp/KR-SBERT-V40K-klueNLI-augSTS` | Ko-SBERT 모델 |

---

## 데이터베이스 스키마 (ERD 요약)

```
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│   articles   │     │    users     │     │ subscriptions │
├──────────────┤     ├──────────────┤     ├───────────────┤
│ url (PK)     │     │ email (PK)   │◄────│ user_email FK │
│ title        │     │ hashed_pw    │     │ target_type   │
│ body         │     │ name         │     │ target_name   │
│ summary      │     │ interest_cat │     └───────────────┘
│ category     │     │ interest_vec │
│ embedding    │     │ disint_vec   │     ┌───────────────┐
│  (768 dim)   │     │ font_size    │     │  read_logs    │
│ credibility  │     └──────────────┘     ├───────────────┤
│ press        │            │             │ user_email FK │
│ journalist   │            ├─────────────│ article_url FK│
│ published_at │            │             └───────────────┘
└──────────────┘            │
        │                   │             ┌───────────────┐
        │                   │             │ dislike_logs  │
        └───────────────────┴─────────────│ user_email FK │
                                          │ article_url FK│
                                          │ is_active     │
                                          └───────────────┘
```

---

## 팀 정보

캡스톤 디자인 프로젝트

---

## 라이선스

이 프로젝트는 학술 목적으로 개발되었습니다.
