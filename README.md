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
17. [다른 데스크탑으로 이식하기 (VSCode 가이드)](#17-다른-데스크탑으로-이식하기-vscode-가이드)
18. [Claude Code 프롬프트 템플릿 (다른 데스크탑용)](#18-claude-code-프롬프트-템플릿-다른-데스크탑용)

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

### 🌍 세계·연예·스포츠 기사 공백 해결 (4-layer fix)

네이버 뉴스 검색 API 는 공백으로 구분된 쿼리를 **AND 매칭** 으로 처리한다. 이전에 `"연예 아이돌 드라마"` 같은 3단어 쿼리로 검색 결과 집합이 너무 좁아지고, 이어서 GPT 재분류가 세계/연예 섹션 기사를 '사회'/'경제' 로 흘려보내고, 마지막으로 파이프라인 교착 버그까지 겹쳐 해당 카테고리가 **DB 에 각 1건(시드)만** 존재하는 문제가 있었다.

**수정 (4층 방어)**:
1. **`crawler.py`** — `CATEGORY_KEYWORDS` 를 1~2 단어 핵심어로 축소하고 노이즈 키워드를 교체 (`"국제" → "해외"`, `"연예" → "연예인"`) — 네이버 API 의 AND 매칭에서 실제 해외/연예 기사가 잡히도록.
2. **`llm_processor.py`** — GPT 분류 프롬프트에 섹션 힌트를 강하게 편향 (`"기본 분류를 힌트 카테고리로 하되, 완전히 무관할 때만 재분류"`) + 실패 시 고정 '사회' 폴백을 **크롤러 섹션 카테고리 폴백** 으로 교체.
3. **`pipeline.py` (Sticky)** — 크롤러가 세계/연예/스포츠 섹션에서 가져온 기사는 GPT 재분류 결과를 무시하고 **크롤러 힌트 카테고리를 유지** (`STICKY_CRAWLER_CATEGORIES`). GPT 가 '연예인 골프 경기' 를 '스포츠' 로 바꿔서 연예 버킷이 비는 현상을 막는다.
4. **`pipeline.py` (Deadlock)** — 과거 `back_pressure.increment(len(new_articles))` 로 배치 전체(예: 239 건) 를 한꺼번에 큐에 등록한 뒤 `wait_if_paused()` 가 pause_threshold(100) 초과 상태에서 영원히 대기 → `decrement` 는 처리 완료 후 호출되므로 **서버 기동 직후 크롤링이 1 건도 진입하지 못하는 교착** 이 있었다. increment/decrement 를 per-item 으로 옮겨 큐를 1 이하로 유지하도록 수정.

**실측 결과** (단일 크롤링 회차, 239건 처리 완료):

| 카테고리 | Before | After | Δ |
|----------|--------|-------|---|
| 정치 | 16 | 77 | +61 |
| 사회 | 16 | 57 | +41 |
| 경제 | 16 | 53 | +37 |
| 생활·문화 | 16 | 53 | +37 |
| **세계** | **1 (시드)** | **35** | **+34** |
| **스포츠** | **1 (시드)** | **32** | **+31** |
| **연예** | **1 (시드)** | **31** | **+30** |
| IT·과학 | 6 | 15 | +9 |
| **TOTAL** | **73** | **353** | **+280** |

- 파이프라인 처리 성공률: **239/239 (100%)**, 소요 시간 1621.5초 (≈ 27분)
- `Sticky` 안전망 발동 횟수: **35회** (GPT 가 세계 기사를 경제/생활·문화/스포츠로 재분류하려 했으나 크롤러 힌트가 이를 덮어씀)

### 🧰 파이프라인 교착(Backpressure) 버그 수정

증상: "서버를 재시작해도 크롤링이 진행되지 않음". 원인은 위 §2 의 4번 항목과 동일.
`pipeline.py` 의 개별 기사 처리 루프에서 backpressure 를 **per-item increment** 로 바꿔 순차 처리 의미론을 지키도록 수정하였다 (순차 루프는 queue 크기 ≤ 1 을 보장하므로 `wait_if_paused` 는 사실상 no-op 이 된다).

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

### 5-A. Windows — 배치 스크립트 권장 경로 (3줄 요약)

```powershell
git clone https://github.com/NEO8320/capstone_project.git D:\news-curator
cd D:\news-curator
.\setup.bat         # 최초 1회: venv + pip + npm + .env 복사
# → setup.bat 안내에 따라 backend\.env 에 API 키 입력, ollama pull llama3, Docker Desktop 기동
.\run_all.bat       # 매번 기동
```

### 5-B. 수동 단계 (macOS/Linux 포함)

```bash
# 1) 저장소 클론
git clone https://github.com/NEO8320/capstone_project.git news-curator
cd news-curator

# 2) 인프라 컨테이너 기동 (PostgreSQL + Redis)
docker compose up -d

# 3) 로컬 LLM 다운로드 (약 4.7GB)
ollama pull llama3
ollama serve &      # 별도 터미널에 상주

# 4) 환경 변수 파일 생성 — API 키는 여기에 들어간다 (상세: §6 참고)
cp backend/.env.example backend/.env
# → backend/.env 를 열어서 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, SECRET_KEY 입력
#    (선택) OPENAI_API_KEY 있으면 함께 입력

# 5) Python 가상환경 + 의존성 (★ venv 경로는 반드시 backend/.venv)
python -m venv backend/.venv
# Windows
backend\.venv\Scripts\activate
# macOS/Linux
source backend/.venv/bin/activate

pip install -r backend/requirements.txt

# 6) 프론트엔드 의존성
cd frontend && npm install && cd ..

# 7) 서버 기동 (개발 모드)
# Windows — 통합 스크립트
./run_all.bat
# macOS/Linux — 개별 기동 (2개 터미널)
#   터미널 A: backend/.venv/bin/python start_backend.py
#   터미널 B: cd frontend && npm run dev -- --host
```

기동 후:
- API: http://localhost:8000/docs (Swagger UI)
- Web: http://localhost:5173

---

## 6. 환경 변수 상세

### 🔑 API 키 삽입 경로 — 이 한 파일만 수정하면 된다

> **파일 경로**: `backend/.env`
> (저장소에는 **존재하지 않는 파일**. `backend/.env.example` 을 복사해서 직접 만들어야 한다.)

```bash
# ① 템플릿 복사
cp backend/.env.example backend/.env         # macOS / Linux
copy backend\.env.example backend\.env       # Windows CMD
Copy-Item backend\.env.example backend\.env  # Windows PowerShell

# ② 생성된 backend/.env 파일을 에디터로 열어 값을 채운다
```

#### 어떤 키를 어디에 넣는가

생성된 `backend/.env` 파일에서 아래 줄들의 **등호(=) 오른쪽**에만 값을 입력한다. 키 이름(왼쪽)은 절대 바꾸지 말 것.

| 라인 | 키 이름 | 발급처 | 필수? |
|------|---------|--------|-------|
| **필수 1** | `NAVER_CLIENT_ID=` | https://developers.naver.com/apps/ (검색 API → 뉴스) | ✅ 필수 |
| **필수 2** | `NAVER_CLIENT_SECRET=` | 위와 동일 | ✅ 필수 |
| **필수 3** | `SECRET_KEY=` | `python -c "import secrets; print(secrets.token_hex(32))"` 로 직접 생성 | ✅ 필수 |
| 선택 4 | `OPENAI_API_KEY=` | https://platform.openai.com/api-keys | 🟡 선택 (있으면 GPT 분류 활성화) |
| 선택 5 | `ANTHROPIC_API_KEY=` | https://console.anthropic.com | ⚪ 미사용 (비워두기) |

#### 작성 예시

```ini
# backend/.env (직접 생성 후 값 채우기)

NAVER_CLIENT_ID=abcDefGhiJklMno12345        ← 네이버 개발자센터에서 복사
NAVER_CLIENT_SECRET=XYZqrs1234              ← 네이버 개발자센터에서 복사
SECRET_KEY=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
OPENAI_API_KEY=sk-proj-...                  ← 있으면 입력, 없으면 빈 줄로 두기
ANTHROPIC_API_KEY=                          ← 비워둠
```

#### ⚠ 절대 하지 말 것

- ❌ `backend/.env` 를 **git 에 커밋하지 말 것** (이미 `.gitignore` 에 등록됨 — 자동 차단)
- ❌ `backend/.env.example` 에 실제 키를 넣지 말 것 (이 파일은 공개 저장소에 올라감)
- ❌ 코드 파일(.py, .js) 에 API 키를 **하드코딩하지 말 것**
- ❌ Slack/채팅/이슈 등에 키를 붙여넣지 말 것

#### 키가 외부에 노출됐을 때의 처치

1. **즉시** 해당 키를 발급처에서 폐기(Revoke) 하고 새 키 재발급
2. `git log --all -p -- backend/.env` 로 과거 커밋 이력 확인
3. 만약 커밋된 적 있다면 `git filter-repo` 로 이력에서 삭제 후 force-push

---

### 전체 환경변수 레퍼런스

`backend/.env` 파일 전체 내용 (템플릿은 `backend/.env.example` 이며 모든 민감값은 공란으로 배포된다):

```ini
# ─── 필수 (공란일 때 서버 정상 기동 불가) ────────
NAVER_CLIENT_ID=                # ← 네이버 개발자센터에서 발급 후 여기에 입력
NAVER_CLIENT_SECRET=            # ← 네이버 개발자센터에서 발급 후 여기에 입력
SECRET_KEY=                     # ← 32바이트 랜덤 문자열 (secrets.token_hex(32))

# ─── DB / Redis (기본값 그대로 쓰면 docker-compose와 맞음) ─────
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/news_curator
REDIS_URL=redis://localhost:6379/0

# ─── LLM (공란이어도 서버 동작, 있으면 품질 향상) ──
OPENAI_API_KEY=                 # 있으면 CT-02 GPT 분류 활성화 (없으면 섹션 카테고리로 폴백)
ANTHROPIC_API_KEY=              # 선택 (현재 미사용 — 공란 유지)

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

### 통합 스크립트 (권장) — `setup.bat` 후 `run_all.bat`

**처음 이식한 환경이라면 반드시 순서대로 실행한다:**

```powershell
cd D:\news-curator

# ① 최초 1회 (venv 생성 + 의존성 설치 + .env 복사)
.\setup.bat

# ② 매번 서비스 기동
.\run_all.bat
```

`run_all.bat` 가 내부에서 수행하는 작업:
1. Docker 컨테이너 기동 확인 (`docker-compose up -d`)
2. Ollama 헬스 체크 (`curl http://localhost:11434/api/tags`)
3. **가상환경 자동 탐색** — `backend\.venv` 우선, 없으면 `.venv`
4. `.env` / `node_modules` / 필수 패키지 import 사전 검증
5. FastAPI 서버 기동 (**새 cmd 창**, 포트 8000, venv python 사용)
6. Vite 개발 서버 기동 (**새 cmd 창**, 포트 5173)

> 🚨 **중요**: 과거 `run_all.bat` 가 시스템 `python` 을 호출해 `sentence-transformers` 미존재로 인해 크롤링 0건 현상이 있었다. v2 부터는 venv python 을 명시적으로 사용하며, `start_backend.py` 가 가상환경이 아니면 즉시 오류와 함께 종료한다.

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

**백엔드** (반드시 venv python 으로)
```powershell
cd D:\news-curator
.\backend\.venv\Scripts\python.exe start_backend.py
# 또는 수동 uvicorn
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend
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

## 17. 다른 데스크탑으로 이식하기 (VSCode 가이드)

이 섹션은 **다른 데스크탑에서 이 프로젝트를 그대로 받아 VSCode 로 개발/실행**하려는 경우의 완전한 가이드다. 순서대로 따라가면 `run_all.bat` 한 번 실행만으로 전체 서비스가 기동된다.

### 17-1. 대상 환경 전제

| 항목 | 최소/권장 |
|------|-----------|
| OS | Windows 10/11 (64-bit). macOS/Linux 는 경로 구분만 바꾸면 동일 절차 |
| CPU/RAM | 4-core 이상, 16 GB RAM 이상 (Llama 3 로컬 실행 시 RAM 8 GB 여유 필요) |
| 디스크 | 15 GB 이상 여유 (Ollama 모델 4.7 GB + venv + 노드 모듈 + DB 볼륨) |
| 네트워크 | 네이버 뉴스 API + OpenAI API + Anthropic API (선택) 아웃바운드 허용 |

### 17-2. 사전 설치 (한 번만)

아래 5 종을 모두 설치한다. 모두 **공식 인스톨러** 사용 권장.

| 소프트웨어 | 설치 링크 | 확인 명령 |
|-----------|----------|-----------|
| **Git for Windows** | https://git-scm.com/download/win | `git --version` |
| **Python 3.12.x** | https://www.python.org/downloads/ (설치 시 *Add to PATH* 체크) | `python --version` |
| **Node.js 20 LTS** | https://nodejs.org/ | `node --version && npm --version` |
| **Docker Desktop** | https://www.docker.com/products/docker-desktop/ (WSL2 backend 권장) | `docker --version` |
| **Ollama** | https://ollama.com/download | `ollama --version` |
| **VSCode** | https://code.visualstudio.com/ | (GUI) |

**VSCode 권장 확장**:
- `ms-python.python` — Python 언어 서버
- `ms-python.vscode-pylance` — 타입 체크
- `dbaeumer.vscode-eslint` — 프런트엔드 린터
- `esbenp.prettier-vscode` — 코드 포맷
- `ms-azuretools.vscode-docker` — 컨테이너 관리
- `Anthropic.claude-code` — **Claude Code** (본 프로젝트 유지보수용)

### 17-3. 리포지토리 클론

```powershell
# PowerShell 또는 Git Bash
cd D:\          # 원하는 작업 폴더로
git clone https://github.com/NEO8320/capstone_project.git news-curator
cd news-curator
code .          # VSCode 로 열기
```

> ⚠️ 경로에 한글/공백이 있으면 일부 빌드 도구에서 실패한다. `D:\news-curator` 처럼 ASCII 단일 단어 경로 권장.

### 17-4. Python 가상환경 (backend)

VSCode 터미널(`Ctrl+` ` ` `)에서:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # PowerShell
# 또는  .\.venv\Scripts\activate.bat  (cmd.exe)

pip install --upgrade pip
pip install -r requirements.txt
```

VSCode 가 `.venv` 를 자동 감지하지 못하면:
1. `Ctrl+Shift+P` → `Python: Select Interpreter`
2. `./backend/.venv/Scripts/python.exe` 선택

**중요**: `sentence-transformers` 는 첫 실행 시 Ko-SBERT 모델(≈ 500 MB)을 Hugging Face 에서 다운로드한다. 방화벽이 차단하면 `HF_HUB_OFFLINE` 이슈가 날 수 있으므로 초회는 온라인 환경에서 실행하자.

### 17-5. 프런트엔드 의존성

```powershell
cd ..\frontend
npm install      # 2~3 분 소요
```

### 17-6. 환경 변수 파일 준비 — **API 키 여기에 입력**

```powershell
cd ..\backend
copy .env.example .env          # Windows
# cp .env.example .env           # macOS/Linux
```

그 뒤 VSCode 에서 `backend/.env` 를 열어 다음 4개 키의 **값 부분만** 채운다.

| 키 | 발급처 | 필수 여부 |
|----|--------|-----------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` 결과 붙여넣기 | ✅ 필수 (미설정 시 서버 기동 불가) |
| `NAVER_CLIENT_ID` | https://developers.naver.com/apps/ → 애플리케이션 등록 → 검색(뉴스) | ✅ 필수 |
| `NAVER_CLIENT_SECRET` | 위와 동일 | ✅ 필수 |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys | ⚠️ 선택 (없으면 CT-02 가 크롤러 섹션으로 자동 폴백) |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ | ❌ 현재 미사용 |

> 📌 **API 키는 `backend/.env` 외의 어떤 파일에도 쓰지 말 것.** `.env` 는 `.gitignore` 에 포함되어 커밋되지 않는다.

### 17-7. Ollama 로컬 LLM 준비

```powershell
ollama pull llama3          # 4.7 GB, 첫 실행 1회만
ollama serve                # 별도 터미널에서 상주 (기본: http://localhost:11434)
```

GPU 가 있으면 자동 활용된다. CPU-only 환경에서도 동작하지만 요약 1건당 4-8초 소요.

### 17-8. Docker (Postgres + Redis) 기동

```powershell
cd D:\news-curator
docker-compose up -d         # 2개 컨테이너 기동
docker ps                    # news_curator_db / news_curator_redis 상태 확인
```

**pgvector 확장**은 docker-compose 의 `pgvector/pgvector:pg16` 이미지에 포함되어 자동 활성화된다. 수동 `CREATE EXTENSION` 불필요.

### 17-9. 통합 실행 — `setup.bat` → `run_all.bat`

**처음 이식한 경우 반드시 아래 두 단계를 순서대로 실행한다.**

```powershell
cd D:\news-curator

# ① 최초 1회만: 가상환경 생성 + pip install + npm install + .env 복사
.\setup.bat

# (이때 출력되는 안내에 따라 backend\.env 에 API 키를 입력하고,
#  ollama pull llama3 및 ollama serve 를 실행한다)

# ② 매번 기동 시: 통합 실행
.\run_all.bat
```

#### `setup.bat` 가 하는 일 (첫 실행 전용)
| 단계 | 내용 |
|------|------|
| 1 | `python --version` 확인 (3.12+ 권장) |
| 2 | `backend\.venv` 생성 + `pip install -r backend\requirements.txt` |
| 3 | `frontend\node_modules` 설치 (`npm install`) |
| 4 | `backend\.env.example` → `backend\.env` 복사 (이미 있으면 스킵) |
| 5 | 다음 단계(API 키 입력 / Ollama 모델 / Docker 기동) 안내 |

#### `run_all.bat` 가 하는 일 (매번 기동)
| 단계 | 내용 | 실패 시 |
|------|------|---------|
| 0/5 | 사전 확인 체크리스트 출력 | 사용자가 수동 확인 |
| 1/5 | `docker-compose up -d` (Postgres + Redis) | 오류 메시지 후 종료 |
| 2/5 | `curl http://localhost:11434/api/tags` 로 Ollama 확인 | Y/N 확인 후 계속 가능 |
| 3/5 | `backend\.venv\Scripts\python.exe` 존재 확인 + 필수 패키지 import 테스트 + `backend\.env` 존재 확인 + `frontend\node_modules` 확인 | 명확한 복구 명령 출력 후 종료 |
| 4/5 | **새 cmd 창**에서 `venv python start_backend.py` (FastAPI :8000) | — |
| 5/5 | **새 cmd 창**에서 `npm run dev --prefix frontend -- --host` (Vite :5173) | — |

> ⚠️ **과거 버그**: 예전 `run_all.bat` 는 `cmd /k "python start_backend.py"` 로 **시스템 `python`** 을 호출했다. 시스템 `python` 에는 `sentence-transformers` 등이 없어서 서버는 뜨지만 **모든 기사 임베딩 생성이 실패해 DB 에 저장되지 않는** 문제가 있었다. v2 부터는 `backend\.venv\Scripts\python.exe` 를 명시적으로 사용하고, `start_backend.py` 내부에서도 가상환경이 아닐 경우 조기 종료한다.

#### 경로 정리

| 파일 | 위치 | 용도 |
|------|------|------|
| `run_all.bat` | `D:\news-curator\run_all.bat` | 통합 실행 (매번) |
| `setup.bat` | `D:\news-curator\setup.bat` | 최초 환경 구축 (1회) |
| `start_backend.py` | `D:\news-curator\start_backend.py` | 백엔드 래퍼 (venv 검증 포함) |
| 백엔드 venv python | `D:\news-curator\backend\.venv\Scripts\python.exe` | `run_all.bat` 가 자동 탐색 |
| 환경변수 파일 | `D:\news-curator\backend\.env` | **여기에만** API 키 입력 |
| docker-compose | `D:\news-curator\docker-compose.yml` | PG16+pgvector + Redis7 |

### 17-9-b. `run_all.bat` 가 안 될 때의 진단 순서

| 증상 | 원인 | 복구 |
|------|------|------|
| "docker 명령을 찾을 수 없습니다" | Docker Desktop 미설치 / PATH 누락 | Docker Desktop 설치 후 재부팅 |
| "가상환경을 찾을 수 없습니다" | `backend\.venv` 없음 | `.\setup.bat` 실행 |
| "가상환경에 필수 패키지가 설치되어 있지 않습니다" | `pip install` 생략 | `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt` |
| "backend\\.env 가 없습니다" | 복사 안 됨 | `copy backend\.env.example backend\.env` 후 API 키 입력 |
| "frontend\\node_modules 가 없거나 vite 가 설치되지 않았습니다" | `npm install` 생략 | `cd frontend && npm install` |
| Ollama 연결 실패 | `ollama serve` 미실행 | 별도 터미널에서 `ollama serve` 상주 |
| 새 창이 바로 닫힘 | `start_backend.py` 가 `sys.exit(1)` | 닫히기 전에 에러 메시지를 읽고 위 표에 대응 |

> 💡 **디버깅 팁**: 새 cmd 창이 순식간에 닫혀 에러 메시지를 읽을 수 없다면, `run_all.bat` 를 열지 말고 터미널에서 직접 아래 명령을 실행해 로그를 눈으로 확인한다:
> ```powershell
> cd D:\news-curator
> .\backend\.venv\Scripts\python.exe start_backend.py
> ```

### 17-10. VSCode 디버깅 설정 (선택)

`.vscode/launch.json` 에 다음을 추가하면 백엔드를 디버거로 기동할 수 있다:

```jsonc
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI (debug)",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8000"
      ],
      "cwd": "${workspaceFolder}/backend",
      "python": "${workspaceFolder}/backend/.venv/Scripts/python.exe",
      "env": { "PYTHONIOENCODING": "utf-8" },
      "justMyCode": false
    }
  ]
}
```

### 17-11. 흔히 겪는 이식 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError: No module named 'sentence_transformers'` | VSCode 터미널이 시스템 Python 을 사용 중 | `Ctrl+Shift+P` → Select Interpreter → `backend/.venv` |
| `ConnectionRefusedError (5432)` | Docker Desktop 미기동 또는 컨테이너 중단 | `docker-compose up -d` |
| `ollama: connection refused` | `ollama serve` 미실행 | 별도 터미널에서 `ollama serve` 상주 |
| 네이버 API 401 | `.env` 의 CLIENT_ID/SECRET 오타 또는 애플리케이션에서 **검색(뉴스)** 권한 누락 | https://developers.naver.com/apps/ 에서 "검색" API 추가 |
| 한글 콘솔 깨짐 (`cp949`) | Windows 기본 콘솔 인코딩 | 터미널에서 `$env:PYTHONIOENCODING="utf-8"` 또는 전역 시스템 변수 설정 |
| Vite `EADDRINUSE: 5173` | 이전 프런트엔드 프로세스가 살아 있음 | `netstat -ano \| findstr 5173` → `taskkill /F /PID <pid>` |

### 17-12. 이식 체크리스트 (5분 스모크 테스트)

1. ✅ `http://localhost:8000/docs` 열려서 FastAPI Swagger 가 뜬다
2. ✅ `http://localhost:5173` 에서 로그인 화면이 뜬다
3. ✅ 신규 가입 → 관심 카테고리 선택 → 피드에 기사가 나온다
4. ✅ `docker exec news_curator_db psql -U postgres -d news_curator -c "SELECT category, COUNT(*) FROM articles GROUP BY category;"` 에서 8개 카테고리 전부 0 보다 많다
5. ✅ 백엔드 로그에 `[Pipeline] 기사 수집 파이프라인 완료` 메시지가 기동 ~1분 내에 찍힌다

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

---

## 18. Claude Code 프롬프트 템플릿 (다른 데스크탑용)

다른 데스크탑에서 이 프로젝트를 `git clone` 한 뒤 **Claude Code (Anthropic)** 로 개발을 이어가려는 경우, 아래 프롬프트 3 종을 순서대로 던지면 Claude 가 프로젝트 구조를 자동으로 파악하고 작업할 수 있는 상태가 된다.

> 💡 **사용법**
> 1. VSCode 에서 `Claude Code` 확장을 설치하고 로그인한다.
> 2. 프로젝트 루트(`D:\news-curator`)에서 Claude Code 세션을 연다.
> 3. 아래 **① 부트스트랩 프롬프트**를 붙여넣어 환경을 일으킨다.
> 4. 필요에 따라 **② 점검 프롬프트** 또는 **③ 개발 작업 프롬프트**를 사용한다.

---

### ① 부트스트랩 프롬프트 — 새 데스크탑 최초 1회 실행

```text
이 리포지토리는 https://github.com/NEO8320/capstone_project 에서 clone 한
News Curator 프로젝트이다. 다른 데스크탑에서 개발을 이어가려 하니, 아래 작업을
순서대로 수행해 달라. 실패하는 단계는 원인을 설명하고 해결책을 제시하되,
내 확인 없이 .env 를 수정하거나 git 커밋을 만들지 말 것.

작업 순서:
1. README.md 의 §4 (사전 설치 요구사항) 과 §17 (이식 가이드) 을 읽고 현재
   호스트에 누락된 도구(Python 3.12, Node 20, Docker Desktop, Ollama) 가
   있는지 `git --version`, `python --version`, `node --version`,
   `docker --version`, `ollama --version` 로 확인만 해 달라. 없는 것은 목록으로
   보고.

2. backend/.venv 가 없으면 `python -m venv backend/.venv` 로 생성한 뒤
   `backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`
   로 의존성을 설치한다. 이미 있으면 그대로 두고 현재 설치 상태만 보고.

3. frontend/node_modules 가 없으면 `npm install --prefix frontend` 실행.

4. backend/.env 가 없으면 `.env.example` 을 복사만 하고, **키 값은 비워
   놓은 채 나에게 어떤 키를 어디서 발급받아 넣어야 하는지 표로 알려 줘라.**
   이미 .env 가 있으면 비어있는 필수 키만 목록화해서 보고.

5. Docker Desktop 이 실행 중이면 `docker-compose up -d` 를 제안(실제 실행
   여부는 내가 결정)하고, Postgres/Redis 컨테이너 상태를 docker ps 로 출력.

6. 마지막으로 "다음 할 일" 을 아래 기준으로 제안해 달라:
   - .env 값을 채워야 하면 § 6 표 기준으로 어떤 키가 비어 있는지
   - Ollama 에 llama3 가 pull 되어있지 않으면 `ollama pull llama3` 안내
   - 모든 준비가 끝났다면 `run_all.bat` 실행 안내

보고 형식: 체크리스트(✅/❌) + 누락된 항목만 짧게 이유 설명.
```

---

### ② 상태 점검 프롬프트 — 매일 작업 시작 전

```text
news-curator 프로젝트의 현재 상태를 아래 5가지 관점으로 점검하고 짧게 보고해 줘.
파일을 수정하거나 커밋하지는 말 것.

1. git status — 변경/미커밋 파일 목록 (있으면 summary)
2. docker ps — news_curator_db / news_curator_redis 기동 여부
3. backend/.venv/Scripts/python.exe -c "import sentence_transformers, openai, httpx, sqlalchemy; print('OK')"
   로 핵심 의존성 import 성공 여부
4. DB 카테고리 분포 — 아래 SQL 을 docker exec 로 실행한 결과:
   SELECT category, COUNT(*) FROM articles GROUP BY category ORDER BY category;
   (세계/연예/스포츠 가 각 5건 미만이면 경고)
5. 최근 크롤링 로그 (D:\news-curator\crawl_run.log 존재 시 마지막 20줄)

형식: 5개 섹션 bullet, 각 섹션 3줄 이내.
```

---

### ③ 개발 작업 프롬프트 — 기능 추가/버그 수정 요청할 때

```text
[작업 내용]
<여기에 구체적인 요구사항을 한국어로 작성>
(예: "추천 피드에서 최근 7일 이내 기사만 노출되도록 필터를 추가하고
싶다. backend/app/services/recommendation.py 에 조건을 넣고, 프런트엔드
필터 UI 는 건드리지 말 것.")

[작업 제약]
- 파일 변경 전 반드시 Read 로 현재 내용을 확인할 것
- 수정 후 `backend/.venv/Scripts/python.exe -m py_compile <변경파일>`
  으로 문법 검증할 것
- 프런트엔드를 수정했다면 `npm run build --prefix frontend` 로 빌드
  성공 확인할 것
- git 커밋은 내가 확인한 뒤 "커밋해" 라고 할 때만 할 것
- README.md 의 `## 2. 최근 업데이트` 섹션에 한 줄 추가할 것
- .env / settings.local.json / API 키 파일은 절대 건드리지 말 것

[완료 보고 형식]
1. 변경된 파일 목록 (경로 + 변경 요약)
2. 검증 결과 (py_compile / npm build 로그 요약)
3. 검토가 필요한 트레이드오프 (성능/보안/UX 측면)
```

---

### 참고: Claude Code CLI 단축 명령 예시

VSCode 외에 **CLI 로** Claude Code 를 실행하는 경우, 위 프롬프트를 파일로 저장해
두고 입력으로 넘기면 편하다:

```powershell
# PowerShell
claude-code --prompt-file .claude\prompts\bootstrap.md
claude-code --prompt-file .claude\prompts\daily-check.md
```

프롬프트를 수정/확장할 때마다 `.claude/prompts/` 에 커밋해 두면 팀 전원이 동일한
에이전트 컨텍스트로 작업할 수 있다.

---
