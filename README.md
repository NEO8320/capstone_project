# News Curator — AI 기반 개인화 뉴스 큐레이팅 서비스

> 사용자의 관심사를 실시간으로 학습하여, AI가 맞춤형 뉴스 피드를 구성해 주는 풀스택 웹 서비스

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5.4-646CFF?logo=vite)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-0.3-green)](https://github.com/pgvector/pgvector)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis)](https://redis.io/)
[![Ollama](https://img.shields.io/badge/Ollama-Llama3-black)](https://ollama.com/)

---

## 📑 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [최근 업데이트 (2026-04-19)](#2-최근-업데이트-2026-04-19)
3. [시스템 아키텍처](#3-시스템-아키텍처)
4. [사전 설치 요구사항](#4-사전-설치-요구사항)
5. [빠른 시작 (Quick Start)](#5-빠른-시작-quick-start)
6. [환경 변수 상세](#6-환경-변수-상세)
7. [실행 방법](#7-실행-방법)
8. [AI 모델 상세](#8-ai-모델-상세)
9. [알고리즘 상세](#9-알고리즘-상세)
10. [데이터 수집 파이프라인](#10-데이터-수집-파이프라인)
11. [가용성 제어](#11-가용성-제어)
12. [API 레퍼런스](#12-api-레퍼런스)
13. [프론트엔드 구성](#13-프론트엔드-구성)
14. [파일 구조](#14-파일-구조)
15. [운영 스크립트](#15-운영-스크립트)
16. [트러블슈팅](#16-트러블슈팅)

---

## 1. 프로젝트 개요

**News Curator** 는 네이버 뉴스 검색 API 로 수집한 한국어 기사를 다음 4단계로 처리하여 사용자에게 **개인 맞춤 피드** 로 제공하는 서비스다.

```
[1] 수집 (Crawler)          네이버 뉴스 API → HTML 스크래핑
[2] AI 처리 (LLM + 규칙)     Llama 3 요약 → GPT 카테고리 분류 → 규칙 기반 신뢰도 점수
[3] 임베딩 (Ko-SBERT)        제목+요약 → 768차원 의미 벡터 → pgvector HNSW 인덱스
[4] 추천 (Weighted Score)   유사도×40% + 최신성×20% + 구독×20% + 신뢰도×20% − 비관심 패널티×25%
```

### 핵심 차별화 포인트

| 기능 | 설명 |
|------|------|
| **투 트랙 피드** | '추천 트랙' (개인화 점수) + '구독 트랙' (구독 카테고리 최신순) 이원 구성 |
| **EMA 관심 벡터** | 읽기·좋아요·싫어요에 따라 사용자 관심 벡터가 **지수 이동 평균**으로 실시간 갱신 |
| **Undo 지원** | 싫어요 눌렀다가 취소 시 **EMA 역산**으로 벡터 원상복구 |
| **결정론적 신뢰도** | LLM 편차 없이 규칙 기반(RB-01~04) 으로 **같은 입력 → 같은 점수** 보장 |
| **콜드 스타트** | 신규 가입자는 관심 카테고리 벡터들의 평균으로 초기 피드 구성 |
| **3중 가용성 제어** | 서킷 브레이커 + 백프레셔 + 적응형 수집량 조절 |

### 8개 카테고리

`정치` · `경제` · `사회` · `생활·문화` · `IT·과학` · `세계` · `연예` · `스포츠`

> ⚠ 카테고리 이름은 반드시 **가운뎃점 `·`** 사용 (슬래시 `/` 아님).
> 크롤러 → DB → 피드 → 프론트엔드 전 구간에서 정확히 동일해야 한다.

---

## 2. 최근 업데이트 (2026-04-19)

### 🎯 신뢰도 점수 "50점 수렴" 완전 해소 (v2)

v1 에서는 규칙 기반 도입에도 불구하고 **평균 72, 50~59 구간 20%, 85+ 거의 없음** 이라는 2차 편향이 남아 있었다.
원인은 계단식(step-function) 점수 테이블 + 짧은 본문 고정 페널티 + 이진(0/100) RB-04. v2 는 4개 서브스코어를 모두 **연속 스케일** 로 재설계했다.

| 서브스코어 | v1 (계단) | v2 (연속) |
|------------|-----------|-----------|
| **RB-01 문체 중립성** (30%) | 5단계 `100/85/65/45/25` 계단 | `max(25, 100 − hits·7)` 선형 감점 |
| **RB-02 정보 밀도** (25%) | 짧은 본문 고정 30, 기본 20 바닥 | 짧은 본문 **55** , `35 + density·13` 선형 |
| **RB-03 인용구** (25%) | 0건 → 0점 (과도) | 0건 → **30점** , 1~4 스무스 |
| **RB-04 출처 명시** (20%) | 기자 유무 이진 `0 / 100` | **3-tier** `25 / 60 / 100` (기자+언론사 조합) |

**실측 결과 (DB 73건)**
```
                   v1 (before)     v2 (after)
─────────────────────────────────────────────
평균                72.2            79.2
50~59 구간          20.0%           1.4%   ← 해소
80+ 구간            극소수           50.7%
활용 구간 수        2~3             7 (고르게 분포)
```

구버전 기사를 새 점수로 재계산:
```bash
cd backend
python -m scripts.recalculate_credibility
```

### 🌍 세계·연예·스포츠 기사 공백 해결

네이버 뉴스 검색 API 는 공백으로 구분된 쿼리를 **AND 매칭** 으로 처리한다. 이전에 `"연예 아이돌 드라마"` 같은 3단어 쿼리로 검색 결과 집합이 너무 좁아져 세계/연예/스포츠 카테고리가 DB 에 **각 1건** 만 존재하는 문제가 있었다.

**수정**:
- `crawler.py` 의 `CATEGORY_KEYWORDS` 를 1~2 단어 핵심어로 축소 (예: `"세계" → "국제"`)
- `llm_processor.py` 의 GPT 분류 실패 시 고정 '사회' 폴백을 **크롤러 섹션 카테고리로 폴백** 으로 교체
- GPT 프롬프트에 섹션 힌트를 포함 (분류 정확도 향상)

### ⏱ 서버 기동 시 자동 크롤링 + 1시간 간격 스케줄

- `CRAWL_ON_STARTUP=True` (기본) 로 **서버 구동 직후 1회 즉시 크롤링**
- APScheduler `interval=1h` 로 **1시간 간격 자동 수집**
- 최초 크롤링이 0건이면 60초 후 1회 재시도 (`STARTUP_CRAWL_RETRY_ON_ZERO`)
- DB 비어 있으면 샘플 기사 자동 시드 (`AUTO_SEED_ON_EMPTY_DB`)

---

## 3. 시스템 아키텍처

```
┌────────────────┐      HTTP          ┌────────────────────┐
│   React 18     │ ─────────────────▶ │  FastAPI 0.115     │
│   + Vite 5     │ ◀───── JSON ────── │  (async/await)     │
│   + axios      │                    │                    │
└────────────────┘                    └──┬─────────────┬───┘
                                         │             │
                              ┌──────────▼───┐  ┌──────▼──────┐
                              │ PostgreSQL 16│  │  Redis 7    │
                              │ + pgvector   │  │  (feed cache)│
                              │   HNSW 768d  │  │   5-min TTL │
                              └──────────────┘  └─────────────┘
                                         ▲
                ┌────────────────────────┼─────────────────┐
                │                        │                 │
        ┌───────▼────────┐   ┌──────────▼──────┐   ┌──────▼──────┐
        │  Naver News    │   │  Ollama (local) │   │  OpenAI     │
        │  Search API    │   │  Llama 3 8B     │   │  GPT-4o-mini│
        │  (8 categories)│   │  (CT-01 요약)    │   │ (CT-02 분류)│
        └────────────────┘   └─────────────────┘   └─────────────┘

         ┌──────────────────────────────────────────┐
         │  APScheduler — 1h interval + startup run │
         └──────────────────────────────────────────┘
```

### 데이터 흐름

```
[Naver API] ─► [scrape body] ─► [Llama: summary] ─► [GPT: category]
                                                           │
                            [규칙: credibility v2] ◀───────┘
                                       │
                          [Ko-SBERT: 768d embedding]
                                       │
                       [PostgreSQL: articles + pgvector HNSW]
                                       │
          ┌────────────────────────────┴────────────────────────┐
          │                                                     │
   [Redis: user:{id}:feed (5min TTL)] ─────────▶ [Frontend feed]
                                       ▲
                         [Recommendation: weighted score]
                                       ▲
                     [사용자 피드백 → EMA 관심벡터 갱신]
```

---

## 4. 사전 설치 요구사항

### 필수 소프트웨어

| 항목 | 버전 | 용도 | 다운로드 |
|------|------|------|---------|
| **Python** | 3.12+ | 백엔드 런타임 | https://python.org |
| **Node.js** | 18+ (권장 20+) | 프론트엔드 빌드/개발 | https://nodejs.org |
| **Docker Desktop** | 최신 | PostgreSQL+pgvector, Redis 컨테이너 | https://www.docker.com/products/docker-desktop |
| **Ollama** | 최신 | 로컬 Llama 3 추론 | https://ollama.com |
| **Git** | 2.30+ | 소스 관리 | https://git-scm.com |

### 선택 사항

- **Redis Desktop Manager** (또는 RedisInsight) — Redis 캐시 키 확인용
- **pgAdmin 4** 또는 DBeaver — PostgreSQL GUI
- **Postman** / **Insomnia** — API 테스트
- **Visual Studio Code** — `.vscode/launch.json` 이 포함되어 있어 디버깅 즉시 가능

### 외부 API 키 (선택)

로컬 Llama 3 만으로도 정상 동작하지만, 아래 키가 있으면 품질이 향상된다.

| 키 | 필수 여부 | 발급처 | 용도 |
|----|----------|--------|------|
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | **필수** | https://developers.naver.com | 뉴스 검색 API |
| `OPENAI_API_KEY` | 선택 | https://platform.openai.com | CT-02 카테고리 분류 (GPT-4o-mini) |
| `ANTHROPIC_API_KEY` | 선택 | https://console.anthropic.com | Claude 폴백 (현재 미사용) |

---

## 5. 빠른 시작 (Quick Start)

```bash
# 1) 저장소 클론
git clone https://github.com/NEO8320/capstone_project.git news-curator
cd news-curator

# 2) 인프라 컨테이너 기동 (PostgreSQL + Redis)
docker compose up -d

# 3) 로컬 LLM 다운로드 (약 4.7GB)
ollama pull llama3

# 4) 환경 변수 파일 생성
cp backend/.env.example backend/.env   # 없으면 아래 예시대로 직접 작성
# backend/.env 를 열어서 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 입력

# 5) Python 가상환경 + 의존성
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r backend/requirements.txt

# 6) 프론트엔드 의존성
cd frontend && npm install && cd ..

# 7) 서버 기동 (개발 모드)
#    — 백엔드와 프론트엔드를 동시에 띄우는 통합 스크립트
./run_all.bat      # Windows
```

기동 후:
- API: http://localhost:8000/docs (Swagger UI)
- Web: http://localhost:5173

---

## 6. 환경 변수 상세

`backend/.env` 파일을 만들어 다음 값들을 설정한다. `backend/app/core/config.py` 의 `Settings` 가 자동으로 로드한다.

```ini
# ─── 필수 ─────────────────────────────────────
NAVER_CLIENT_ID=네이버_검색_API_클라이언트_ID
NAVER_CLIENT_SECRET=네이버_검색_API_비밀키
SECRET_KEY=32바이트_이상의_랜덤_문자열_예: openssl rand -hex 32

# ─── DB / Redis (기본값 그대로 쓰면 docker-compose와 맞음) ─────
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/news_curator
REDIS_URL=redis://localhost:6379/0

# ─── LLM (있으면 품질 향상, 없어도 동작) ──────────
OPENAI_API_KEY=sk-...           # 있으면 CT-02 GPT 분류 활성화
ANTHROPIC_API_KEY=              # 선택 (현재 미사용)

# ─── JWT ───────────────────────────────────────
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ─── LLM 엔드포인트 (로컬 Ollama 기본) ─────────
LLM_PRIMARY_MODEL=llama3
LLM_PRIMARY_BASE_URL=http://localhost:11434/v1

# ─── 임베딩 모델 ───────────────────────────────
EMBEDDING_MODEL_NAME=snunlp/KR-SBERT-V40K-klueNLI-augSTS
EMBEDDING_DIM=768

# ─── 크롤링 스케줄 ─────────────────────────────
CRAWL_INTERVAL_HOURS=1          # 자동 크롤링 주기
CRAWL_ON_STARTUP=True           # 서버 기동 시 즉시 크롤링
AUTO_SEED_ON_EMPTY_DB=True      # DB 비어 있으면 샘플 기사 시드
STARTUP_CRAWL_RETRY_ON_ZERO=1   # 0건일 때 60초 후 재시도 횟수

# ─── 기타 ──────────────────────────────────────
RATE_LIMIT=60/minute
FEED_CACHE_TTL=300              # 피드 Redis 캐시 TTL (초)
```

### 가중치/모델 튜닝 — `backend/config.yaml`

코드 수정 없이 동작을 조정할 수 있는 YAML 설정 파일 (NFR-E03).

```yaml
llm:
  summarizer:
    model: "llama3"
    base_url: "http://localhost:11434/v1"
    max_tokens: 1024
    temperature: 0.3
  classifier:
    model: "gpt-4o-mini"
    base_url: "https://api.openai.com/v1"
    max_tokens: 512
    temperature: 0.1

recommendation:
  weight_embedding: 0.40          # 의미 유사도
  weight_recency: 0.20            # 최신성
  weight_subscription: 0.20       # 구독 가중
  weight_reliability: 0.20        # 신뢰도
  weight_dislike_penalty: 0.25    # 비관심 패널티
  subscription_boost_multiplier: 1.3
  subscription_track_limit: 10

categories:
  - "정치"
  - "경제"
  - "사회"
  - "IT·과학"
  - "생활·문화"
  - "세계"
  - "연예"
  - "스포츠"
```

---

## 7. 실행 방법

### 통합 스크립트 (권장)

```bash
./run_all.bat
```
내부에서 아래를 순차 실행:
1. Docker 인프라 기동 확인
2. Ollama 서비스 헬스 체크
3. FastAPI 서버 (Uvicorn) 기동 — 포트 8000
4. Vite 개발 서버 기동 — 포트 5173

### 개별 실행

**DB / Redis**
```bash
docker compose up -d
```

**Ollama (별도 터미널)**
```bash
ollama serve
ollama run llama3       # 최초 1회 모델 다운로드
```

**백엔드**
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**프론트엔드**
```bash
cd frontend
npm run dev             # 개발 모드 (HMR)
npm run build           # 프로덕션 빌드
npm run preview         # 빌드 산출물 미리보기
```

### 서버 기동 로그 읽기

```
[Startup] DB 연결 확인 중...
[Startup] DB 연결 성공 (attempt 1)
[Startup] KoBERT 모델 로딩 중...
[Startup] KoBERT 로드 완료 (768-dim)
[Startup] 샘플 기사 시드 건너뜀 (기존 73건 존재)
[Startup] 즉시 크롤링 시작...
[Crawler] 정치: 50건 수집
[Crawler] 경제: 50건 수집
...
[Pipeline] 150건 처리 완료 (스킵: 23건, 실패: 2건)
[Scheduler] 다음 크롤링 예정: 2026-04-19 01:25:00
```

---

## 8. AI 모델 상세

### 8-1. Ko-SBERT 임베딩 모델

| 항목 | 값 |
|------|-----|
| 모델 | `snunlp/KR-SBERT-V40K-klueNLI-augSTS` |
| 출처 | 서울대 자연언어처리 연구실 |
| 차원 | **768** |
| 정규화 | L2 (cosine 유사도용) |
| 입력 제한 | 512 토큰 (이를 초과하지 않도록 **제목 + 요약**만 임베딩) |
| 로딩 시점 | 서버 기동 시 1회 (startup hook) |

**왜 Ko-SBERT 인가**
- 한국어 NLI + STS 증강 학습 → 문장 수준 의미 유사도에 최적화
- Multilingual SBERT 대비 한국어 뉴스 도메인에서 유사도 계산 정확도 10-15%p 높음 (내부 벤치)

**사용처**
- 기사 저장 시 `articles.embedding` 컬럼에 저장 (pgvector `vector(768)`)
- 사용자 관심 벡터 `users.interest_vector` / 비관심 벡터 `users.disinterest_vector`
- 콜드 스타트 시 관심 카테고리들의 대표 벡터 평균

### 8-2. Llama 3 8B — CT-01 요약 (로컬)

| 항목 | 값 |
|------|-----|
| 모델 | `llama3` (Ollama 기본 8B Instruct) |
| 엔드포인트 | `http://localhost:11434/v1` (OpenAI 호환 API) |
| max_tokens | 1024 |
| temperature | 0.3 (낮은 무작위성 — 재현성 중시) |
| 프롬프트 | `CT01_SUMMARIZE_PROMPT` — "3줄로 핵심만 요약하라" |

**왜 로컬 Llama 3 인가**
- CT-01 요약은 **매 기사마다 호출** → API 비용 부담 큼
- 로컬 Ollama 로 비용 0, 프라이버시 확보
- 요약 품질은 8B 로도 충분 (3문장 추출 작업)

### 8-3. GPT-4o-mini — CT-02 카테고리 분류

| 항목 | 값 |
|------|-----|
| 모델 | `gpt-4o-mini` |
| 엔드포인트 | `https://api.openai.com/v1` |
| max_tokens | 512 |
| temperature | 0.1 (거의 결정론적) |
| 입력 | `"{제목} [SEP] {요약}"` + 크롤러 섹션 힌트 |
| 출력 | 8개 카테고리 중 하나 |

**신뢰성 강화**
- **3회 재시도** + 지수 백오프 (0.5s → 1.0s → 2.0s 또는 1.0s → 2.0s → 3.0s)
- **퍼지 매칭**: `"IT"`, `"IT/과학"` → `IT·과학` 으로 자동 정규화
- **실패 시 폴백**: 크롤러 섹션 카테고리를 그대로 사용 (사회 쏠림 방지)

---

## 9. 알고리즘 상세

### 9-1. 신뢰도 점수 v2 (규칙 기반 결정론적 계산)

**파일**: `backend/app/services/credibility.py`

```
Final = RB01×0.30 + RB02×0.25 + RB03×0.25 + RB04×0.20
```

#### RB-01 문체 중립성 (30%)

감정·선정·과장 어휘 사전 매칭 후 선형 감점:

```python
SENSATIONAL_WORDS = ("충격", "경악", "최악", "역대급", "미친", "분노",
                    "대란", "참사", "폭락", "폭등", "단독", "속보", ...)

title_hits = sum(2 for w in SENSATIONAL_WORDS if w in title)  # 제목 2배
body_hits  = sum(1 for w in SENSATIONAL_WORDS if w in body)
score = max(25, 100 - (title_hits + body_hits) * 7)           # 연속 선형
```

#### RB-02 정보 밀도 (25%)

숫자·날짜·단위의 **1000자당 출현 빈도**:

```python
if len(body) < 80: return 55     # 짧은 본문은 중립적 기본점
entities = count(숫자) + count(날짜) + count(단위)
density = entities / len(body) * 1000
score = clamp(35, 100, 35 + density * 13)
```

#### RB-03 인용구 존재 (25%)

직접 인용 `"..."` + 간접 인용 `'...라고 말했다'` 개수:

```
0건 → 30    1건 → 60    2건 → 78    3건 → 90    4건 → 96    5+건 → 100
```

#### RB-04 출처 명시 (20%, **3-tier**)

```python
기자 실명 + 언론사 매칭   → 100  (완전 출처)
기자 또는 언론사 중 하나  →  60  (부분 출처)
둘 다 없음                →  25  (익명 게시 수준)
```

#### 분포 비교

```
            v1 (계단)          v2 (연속)
평균        72.2               79.2
표준편차    ~5                 ~9
구간        2~3개에 집중        7개에 고르게 분포
50~59       20%                1.4%  ← 해소
```

---

### 9-2. 추천 알고리즘 (투 트랙 가중합)

**파일**: `backend/app/services/recommendation.py`

#### 추천 트랙 (Recommendation Track)

개인화 점수로 정렬된 20건. 수식:

```
base_score = (similarity    × 0.40)
           + (freshness     × 0.20)
           + (subscription  × 0.20)
           + (credibility/100 × 0.20)

if dislike_similarity > threshold:
    base_score -= dislike_similarity × 0.25

if category in 구독:
    base_score *= 1.3      # 구독 부스트

최종 정렬: base_score DESC
```

**컴포넌트**:
- `similarity`: 사용자 `interest_vector` vs 기사 `embedding` 의 코사인 유사도
- `freshness`: `exp(-Δhours / 24)` — 24시간 반감기
- `subscription`: 구독 카테고리면 1.0, 아니면 0.0
- `credibility`: 위 v2 신뢰도 (0~100 → 0~1)
- `dislike_penalty`: `disinterest_vector` 와의 유사도 × 0.25

**SQL 후보 선별 (2026-04-17 수정)**:

이전 버전은 `ORDER BY embedding <=> interest_vec LIMIT 200` 로 KNN 사전필터링 → 관심 벡터에 가까운 기사만 후보 → '전체' 탭에 관심 카테고리 외 기사 미노출.

**현재**: `ORDER BY published_at DESC LIMIT 200` 으로 최신순 후보 선별 후 Python 에서 가중 스코어링.

#### 구독 트랙 (Subscription Track)

구독 카테고리 안에서 **최신성 + 신뢰도** 만으로 정렬한 10건:

```
subscription_score = freshness × 0.50 + (credibility/100) × 0.50
```

---

### 9-3. EMA 관심 벡터 (피드백 학습)

**파일**: `backend/app/api/feedback.py`

#### 좋아요 / 읽기 피드백

```
V_new = α × V_article + (1 - α) × V_old      # α = 0.15
V_new ← L2_normalize(V_new)
```

#### 싫어요 피드백

```
D_new = β × V_article + (1 - β) × D_old      # β = 0.10
D_new ← L2_normalize(D_new)
```

#### Undo (EMA 역산)

```
V_old = (V_new - α × V_article) / (1 - α)
V_old ← L2_normalize(V_old)
```

이 역산 공식 덕분에 싫어요 취소가 **정확히 이전 벡터 상태** 로 복귀한다.

---

### 9-4. 콜드 스타트 (신규 가입자)

`interest_vector` 가 없는 사용자는 관심 카테고리들의 대표 벡터 평균을 임시 벡터로 사용:

```python
cold_start_vec = L2_normalize(
    Σ category_embedding(c) for c in user.interest_categories
) / len(user.interest_categories)
```

첫 피드백이 들어오면 이 임시 벡터가 EMA 갱신을 통해 실제 `interest_vector` 로 승격된다.

---

## 10. 데이터 수집 파이프라인

**파일**: `backend/app/services/pipeline.py`, `crawler.py`, `llm_processor.py`

### 파이프라인 단계

```
1. APScheduler 트리거 (1시간 간격 또는 서버 기동 시)
        │
        ▼
2. 카테고리별 네이버 뉴스 API 호출
   - CATEGORY_KEYWORDS 매핑 (1-2 단어 쿼리로 AND 매칭 넓게)
   - 적응형 수집량 (CPU 부하에 따라 15/30/50건)
        │
        ▼
3. URL 중복 검사 (DB IN 쿼리 1회로 bulk)
        │
        ▼
4. 병렬 처리 (asyncio.gather, 백프레셔 적용)
   ┌─ 본문 스크래핑 (BeautifulSoup)
   ├─ 기자명/언론사 추출
   ├─ LLM 요약 (Llama 3)
   ├─ LLM 분류 (GPT-4o-mini)
   ├─ 신뢰도 계산 (규칙 기반 v2)
   └─ Ko-SBERT 임베딩
        │
        ▼
5. DB upsert (ON CONFLICT (url) DO UPDATE)
        │
        ▼
6. Redis 피드 캐시 무효화 (user:*:feed 패턴)
        │
        ▼
7. 완료 로그 (처리/스킵/실패 건수)
```

### 카테고리 키워드 매핑

```python
CATEGORY_KEYWORDS = {
    "정치": "정치",
    "경제": "경제",
    "사회": "사회 사건",     # 단독 '사회'는 과도하게 범용적
    "생활·문화": "문화",
    "IT·과학": "IT",
    "세계": "국제",          # '세계'는 노이즈 多 → '국제'
    "연예": "연예",
    "스포츠": "스포츠",
}
```

### 적응형 수집량 조절

| CPU 사용률 | 카테고리당 수집 |
|-----------|-----------------|
| < 50% | 50건 |
| 50~70% | 30건 |
| > 70% | 15건 |

### 본문 스크래핑 전략 (우선순위)

1. 네이버 뉴스 본문 (`<article id="dic_area">`)
2. 일반 기사 패턴 (`class=article_body|news_body|content`)
3. `<article>` 태그
4. 폴백: `<body>` 전체
5. 스크래핑 실패 시 API `description` 필드 폴백

---

## 11. 가용성 제어

**파일**: `backend/app/services/resilience.py`

### 11-1. 서킷 브레이커

외부 API 연속 실패 차단. 3개의 상태 머신:

```
CLOSED  ──(5회 연속 실패)──▶  OPEN  ──(30초 경과)──▶  HALF_OPEN  ──(1회 성공)──▶  CLOSED
                                                           │
                                                           └──(실패)──▶  OPEN
```

적용 대상:
- 네이버 뉴스 API (`naver_news_api`)
- LLM API (`llm_api`)

### 11-2. 백프레셔

처리 대기 큐 100건 초과 시 크롤링 일시 중지, 50건 이하로 내려가면 재개. 히스테리시스(pause=100, resume=50) 로 chattering 방지.

### 11-3. 적응형 수집량 조절

9-4 참고. CPU 부하에 따라 수집 건수를 15/30/50 세 단계로 자동 조절.

---

## 12. API 레퍼런스

모든 응답은 JSON. JWT Bearer 인증 필요 (일부 admin 제외).

### 인증

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/signup` | 회원가입 (이메일+패스워드+관심 카테고리 최소 1개) |
| POST | `/api/auth/login` | 로그인 → access_token + refresh_token 발급 |
| POST | `/api/auth/refresh` | refresh_token 으로 access_token 재발급 |
| GET | `/api/auth/me` | 현재 사용자 정보 |

### 피드

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/feed` | 투 트랙 피드 (recommendation + subscription) |
| GET | `/api/feed?category=정치` | 카테고리 필터 |
| GET | `/api/feed?sort=latest` | 정렬 변경 (latest/credibility) |

### 기사

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/articles/{id}` | 기사 상세 (RB-01~04 서브스코어 포함) |

### 피드백

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/feedback/read/{article_id}` | 읽기 피드백 (EMA α=0.15) |
| POST | `/api/feedback/like/{article_id}` | 좋아요 |
| POST | `/api/feedback/dislike/{article_id}` | 싫어요 (β=0.10) |
| DELETE | `/api/feedback/dislike/{article_id}` | 싫어요 취소 (EMA 역산 Undo) |

### 구독

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/subscriptions` | 내 구독 목록 |
| POST | `/api/subscriptions` | 카테고리 구독 추가 |
| DELETE | `/api/subscriptions/{category}` | 구독 해제 |

### 관리자

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/admin/crawl` | 수동 크롤링 트리거 |
| POST | `/api/admin/seed` | 샘플 기사 시드 |

Swagger UI 에서 전체 스키마 확인: http://localhost:8000/docs

---

## 13. 프론트엔드 구성

### 주요 컴포넌트

```
src/
├─ App.jsx                   라우터 / 인증 가드
├─ pages/
│  ├─ Login.jsx              로그인
│  ├─ Signup.jsx             회원가입 (관심 카테고리 최소 1개)
│  └─ Home.jsx               피드 홈
├─ components/
│  ├─ Feed.jsx               투 트랙 피드 렌더링
│  ├─ ArticleCard.jsx        기사 카드 (배지 + 좋아요/싫어요)
│  ├─ CategoryFilter.jsx     8개 카테고리 탭
│  ├─ SortFilter.jsx         최신순 / 신뢰도순
│  ├─ Toast.jsx              Undo 포함 스낵바
│  └─ CredibilityChart.jsx   RB-01~04 방사형 차트
└─ utils/
   ├─ api.js                 axios 인스턴스 + 401 인터셉터
   └─ credibility.js         배지 색상 매핑 (90+ green / 70-89 yellow / <70 red)
```

### 신뢰도 배지 색상

```javascript
function getBadgeColor(score) {
  if (score >= 90) return 'green';    // 최상
  if (score >= 70) return 'yellow';   // 양호
  return 'red';                       // 주의
}
```

### Optimistic UI

- 싫어요 클릭 시 **즉시** 카드 제거 + Undo Toast 표시 (5초)
- 5초 내 Undo 클릭하면 EMA 역산 API 호출 → 벡터 + 카드 복구
- 미클릭 시 서버 피드백 유지

---

## 14. 파일 구조

```
news-curator/
├─ README.md                      (이 문서)
├─ docker-compose.yml             PostgreSQL+pgvector, Redis
├─ run_all.bat                    통합 기동 스크립트 (Windows)
├─ start_backend.py               백엔드 단독 실행
├─ start_frontend.js              프론트엔드 단독 실행
│
├─ backend/
│  ├─ requirements.txt            Python 의존성
│  ├─ config.yaml                 LLM/가중치/카테고리 설정
│  ├─ app/
│  │  ├─ main.py                  FastAPI 엔트리포인트, lifespan 훅
│  │  ├─ models.py                SQLAlchemy 모델 (User, Article, Feedback…)
│  │  ├─ schemas.py               Pydantic 스키마 (요청/응답)
│  │  ├─ core/
│  │  │  ├─ config.py             환경변수/설정 (pydantic-settings)
│  │  │  ├─ database.py           async_session, init_db 재시도
│  │  │  └─ yaml_config.py        config.yaml 로더 + 캐시
│  │  ├─ api/
│  │  │  ├─ auth.py               회원가입/로그인/토큰
│  │  │  ├─ feed.py               투 트랙 피드
│  │  │  ├─ feedback.py           EMA 벡터 갱신
│  │  │  ├─ articles.py           기사 상세
│  │  │  ├─ subscriptions.py      카테고리 구독
│  │  │  ├─ users.py              프로필
│  │  │  └─ admin.py              수동 크롤링/시드
│  │  └─ services/
│  │     ├─ crawler.py            네이버 API + 스크래핑
│  │     ├─ llm_processor.py      CT-01/CT-02 LLM 호출
│  │     ├─ credibility.py        규칙 기반 신뢰도 v2
│  │     ├─ embedding.py          Ko-SBERT 768d
│  │     ├─ pipeline.py           전체 파이프라인 오케스트레이션
│  │     ├─ recommendation.py     투 트랙 가중합
│  │     └─ resilience.py         서킷 브레이커/백프레셔/적응형
│  └─ scripts/
│     ├─ recalculate_credibility.py   기존 DB 일괄 재계산
│     └─ sample_articles.py            샘플 시드 데이터
│
└─ frontend/
   ├─ package.json               npm 의존성 (React 18 + Vite 5)
   ├─ vite.config.js
   ├─ index.html
   └─ src/
      ├─ App.jsx                 라우터
      ├─ main.jsx                ReactDOM 엔트리
      ├─ pages/                  Login, Signup, Home
      ├─ components/             Feed, ArticleCard, CategoryFilter, …
      └─ utils/                  api, credibility
```

---

## 15. 운영 스크립트

### 기존 DB 신뢰도 재계산

```bash
cd backend
python -m scripts.recalculate_credibility
```
- 모든 `articles` 의 `credibility`, `rb01_tone`~`rb04_journalist` 컬럼을 **현재 코드 기준**으로 재계산
- 배치 크기 500건마다 commit
- 실행 후 10단위 점수 분포를 출력 (재현성 검증용)

### 수동 크롤링

```bash
# REST API 로
curl -X POST http://localhost:8000/api/admin/crawl \
     -H "Authorization: Bearer $TOKEN"

# 또는 Python 스크립트로
cd backend
python -c "import asyncio; from app.services.pipeline import run_crawl_pipeline; asyncio.run(run_crawl_pipeline())"
```

### 샘플 기사 시드 (DB 비어있을 때)

```bash
curl -X POST http://localhost:8000/api/admin/seed
```
또는 `CRAWL_ON_STARTUP=True` + `AUTO_SEED_ON_EMPTY_DB=True` (기본) 로 서버 기동 시 자동 처리.

### DB 초기화

```bash
docker compose down -v      # 볼륨까지 삭제 (주의: 모든 데이터 영구 삭제)
docker compose up -d
```
서버 재기동 시 `init_db()` 가 스키마를 재생성한다.

---

## 16. 트러블슈팅

### Q1. 서버 기동 시 "connection refused" 또는 "role postgres does not exist"
- Docker 컨테이너가 아직 준비되지 않았거나 초기화가 끝나지 않았다.
- `docker compose ps` 로 상태 확인
- `init_db()` 에는 5회 지수 백오프 재시도가 내장돼 있으므로 보통 자동 복구된다.

### Q2. Llama 3 호출이 계속 실패한다
```bash
# Ollama 서비스 확인
ollama list                 # llama3 모델이 보여야 함
curl http://localhost:11434/api/tags  # 응답 200 OK

# 모델 재다운로드
ollama pull llama3
```

### Q3. 피드에 기사가 너무 적다
- DB 상태 확인: `SELECT category, count(*) FROM articles GROUP BY category;`
- 세계/연예/스포츠가 각 1건이면 **v1 버그**. 크롤러 키워드 수정 + 재크롤링 필요.
- 수동 크롤링: `curl -X POST http://localhost:8000/api/admin/crawl`

### Q4. 신뢰도 점수가 여전히 50점 근처에 몰린다
- 구 DB 기사들이 v1 점수로 남아있음. 재계산 실행:
  ```bash
  cd backend && python -m scripts.recalculate_credibility
  ```
- 재계산 후에도 50 수렴이면 이슈 리포트 요망 (`backend/app/services/credibility.py` 디버그 모드)

### Q5. 프론트엔드가 401 Unauthorized 를 반복한다
- `localStorage` 의 access_token 만료. 브라우저 콘솔:
  ```javascript
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  ```
- 또는 axios 인터셉터 (`src/utils/api.js`) 가 refresh 를 시도하게 되어 있음 — 네트워크 탭에서 `/auth/refresh` 호출 확인

### Q6. Windows 에서 `UnicodeEncodeError: cp949` 가 난다
- Python stdout 이 cp949 로 설정돼 있음. 스크립트 출력에 em-dash(—) 나 가운뎃점(·)이 있으면 크래시.
- `chcp 65001` 로 콘솔을 UTF-8 로 전환하거나 환경변수 설정:
  ```
  set PYTHONIOENCODING=utf-8
  ```

### Q7. pgvector HNSW 인덱스 생성이 느리다
- 기사 1만건 이상이면 HNSW 빌드에 수분 걸릴 수 있음. `CREATE INDEX CONCURRENTLY` 를 수동 실행하거나 배치를 나눠서 처리.

### Q8. 프론트엔드 빌드 경고 "Browserslist is outdated"
```bash
cd frontend
npx update-browserslist-db@latest
```

---

## 라이선스 / 크레딧

- **백엔드 프레임워크**: FastAPI (MIT)
- **프론트엔드**: React (MIT) + Vite (MIT)
- **임베딩 모델**: [snunlp/KR-SBERT](https://github.com/snunlp/KR-SBERT) (Apache 2.0)
- **LLM**: Llama 3 (Meta Llama 3 Community License), GPT-4o-mini (OpenAI 상용)
- **DB**: PostgreSQL (PostgreSQL License) + pgvector (PostgreSQL License)

**데이터 출처**: [네이버 뉴스 검색 API](https://developers.naver.com/docs/serviceapi/search/news/news.md) — 제공된 링크/요약/메타데이터만 사용하며, 원문 저작권은 각 언론사에 귀속된다.

---

**문의 / 기여**: GitHub Issues / Pull Requests 환영합니다.
