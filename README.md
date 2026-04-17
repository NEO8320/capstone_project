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

## 📣 최근 업데이트 (2026-04-17)

### 🛠 신뢰도 점수 "50점 고착" 버그 수정
기존에는 대부분의 기사가 **신뢰도 45~55점 구간**에 몰려 있었습니다. 원인과 해결 내용:

| 항목 | 이전 | 수정 후 |
|------|------|--------|
| **계산 방식** | Llama 3 LLM이 JSON 스키마로 RB-01~04 점수 직접 생성 | **규칙 기반 결정론적 계산** (`backend/app/services/credibility.py`) |
| **실패 시 동작** | `cred.get(field, 50)` + `_clamp` fallback 50으로 수렴 | 항상 본문을 직접 분석 → 기본값 없음 |
| **재현성** | 같은 기사도 호출마다 점수 다름 | 같은 기사 → **항상 같은 점수** |
| **실측 분포 (DB 73건 기준)** | 45~55 구간 집중 | **평균 72 / 중앙값 71**, 25~95점에 고르게 분포 |

#### 무엇이 바뀌었나
- **RB-01 (문체 중립성 30%)** : `충격`·`역대급`·`미친` 등 선정적 어휘 사전을 본문·제목에서 정규식 매칭 → 적을수록 고득점
- **RB-02 (정보 밀도 25%)** : 본문 내 숫자·날짜·단위(`%`, `원`, `명`, `km` 등) 밀도(1000자당 출현빈도)를 계측
- **RB-03 (인용구 25%)** : `"…"`·`「…」`·`'라고 말했다` 패턴의 직접·간접 인용 개수로 산출
- **RB-04 (기자 실명 20%)** : 바이라인 존재 여부 (기존과 동일)

#### 기존 DB 재계산
한 번만 실행하면 DB의 기존 기사들도 새로운 점수로 갱신됩니다.

```bash
cd backend
python -m scripts.recalculate_credibility
```

실행 결과 (점수 분포)가 다음과 같이 출력됩니다:
```
[Recalc] 신뢰도 점수 분포
     0-39 :     2건 (  2.7%)
    40-59 :    16건 ( 21.9%)
    60-79 :    35건 ( 47.9%)
   80-100 :    20건 ( 27.4%)
  평균      : 72.2
  중앙값    : 71.2
```

#### 상세 문서
- **규칙 상세** : [`backend/app/services/credibility.py`](backend/app/services/credibility.py) 상단 docstring
- **아키텍처 변경** : 아래 [3.3 뉴스 신뢰도 점수](#33-뉴스-신뢰도-점수-0100점)
- **LLM 역할 변경** : Llama 3는 **요약 전용**으로 변경. 이전에는 요약 + 신뢰도를 동시에 생성했으나, JSON 스키마의 일부 서브필드를 안정적으로 반환하지 못해 버그의 원인이 됨.

### ✨ 정렬 필터 추가
피드 상단에 **추천순 / 최신순 / 신뢰도순** 3가지 정렬 탭이 추가되었습니다. 카테고리 필터와 조합 가능 (예: `IT·과학 + 신뢰도순`).

---

## 🌱 처음 오신 분께 (GitHub/터미널이 처음이어도 OK)

이 프로젝트를 내 컴퓨터에서 돌려보는 **가장 짧은 경로**입니다.

1. **이 페이지 우측 상단의 초록색 `Code` 버튼** → `Download ZIP` 으로 받거나,
   터미널에서 아래 명령으로 클론하세요.
   ```bash
   git clone https://github.com/NEO8320/capstone_project.git
   ```
2. **Docker Desktop**을 설치하고 실행한 뒤, 프로젝트 폴더에서
   ```bash
   docker-compose up -d
   ```
   한 줄로 PostgreSQL + Redis가 시작됩니다.
3. **Ollama**를 설치하고 `ollama pull llama3` 로 Llama 3 모델을 받습니다. (로컬 AI 엔진)
4. **Python 3.12+** 와 **Node.js 20+**을 설치한 뒤 각각
   ```bash
   cd backend && pip install -r requirements.txt
   cd ../frontend && npm install
   ```
5. 프로젝트 루트에서 `run_all.bat` (Windows) 또는 수동으로 백엔드·프론트엔드를 실행합니다.
6. 브라우저에서 <http://localhost:5173> 열기. 끝!

> **Tip** — 아래 [§7 단계별 설치 가이드](#7-단계별-설치-가이드)에 스크린샷 없이도 그대로 따라 할 수 있는 명령어가 전부 있습니다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [아키텍처 한눈에 보기](#2-아키텍처-한눈에-보기)
3. [핵심 알고리즘](#3-핵심-알고리즘)
4. [기술 스택](#4-기술-스택)
5. [디렉터리 구조 및 파일별 상세 설명](#5-디렉터리-구조-및-파일별-상세-설명)
6. [빠른 시작(Quick Start)](#6-빠른-시작-quick-start)
7. [단계별 설치 가이드](#7-단계별-설치-가이드)
8. [사용 방법(User Guide)](#8-사용-방법-user-guide)
9. [API 레퍼런스](#9-api-레퍼런스)
10. [환경 변수 레퍼런스](#10-환경-변수-레퍼런스)
11. [데이터베이스 스키마](#11-데이터베이스-스키마)
12. [데이터 플로우](#12-데이터-플로우)
13. [운영·디버깅 가이드](#13-운영디버깅-가이드)
14. [FAQ & 트러블슈팅](#14-faq--트러블슈팅)

---

## 1. 프로젝트 개요

**News Curator**는 네이버 뉴스 API에서 실시간으로 기사를 수집하고, 로컬 LLM으로 요약·분류하고, 벡터 임베딩 기반 추천 알고리즘으로 개인화 피드를 제공하는 **완전 로컬형 AI 뉴스 서비스**입니다.

### 이런 분들에게 유용합니다
- 알고리즘 편향 없이 **모든 카테고리 기사를 골고루** 보고 싶은 사용자
- 관심없는 기사를 한 번 클릭으로 제외하고, **학습 결과를 즉시** 피드에 반영하고 싶은 사용자
- **뉴스 신뢰도 점수**(감정·인용·팩트 기반)를 보고 기사를 선택하고 싶은 사용자
- 노년층 등 **접근성이 중요한** 사용자 (WCAG AA, 4단계 글자 크기)

### 핵심 차별점
| 차별점 | 설명 |
|--------|------|
| **완전 로컬 AI** | Llama 3(Ollama)로 요약/분류 — 외부 API 없이도 동작, API 키는 선택 폴백 |
| **실시간 개인화** | EMA(지수이동평균) 알고리즘으로 읽음/관심없음 즉시 반영 |
| **신뢰도 점수** | 문체 중립성·정보 밀도·인용구·기자실명 4지표로 0~100점 자동 산출 |
| **투 트랙 피드** | 구독 트랙(언론사/기자) + 추천 트랙(개인화 알고리즘) 분리 |
| **편향 없는 '전체' 탭** | 최신순 후보 선별 → 관심 카테고리 외 기사도 노출 |
| **접근성 1등급** | WCAG AA 색상 대비(15.4:1), 4단계 글자 크기, 다크 모드 |

---

## 2. 아키텍처 한눈에 보기

```
┌──────────────────────────────────────────────────────────────────────┐
│                         브라우저 (사용자)                             │
└───────────────┬──────────────────────────────────────────────────────┘
                │ HTTPS / JWT (Access + Refresh)
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│     React 18 SPA  (Vite 5)                                          │
│     ├─ 피드 / 기사 상세 / 구독 / 설정                                │
│     ├─ Axios 클라이언트 (토큰 자동 갱신 인터셉터)                     │
│     └─ localStorage: 토큰, 글자 크기, 다크 모드                       │
└───────────────┬──────────────────────────────────────────────────────┘
                │  /api/*  (Vite proxy → :8000)
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│     FastAPI 0.115  (비동기, Rate-Limit 60/min)                       │
│     ├─ 인증 (JWT)                                                   │
│     ├─ 피드  (GET /api/feed)                                         │
│     ├─ 피드백 (read / dislike / undo)                                │
│     ├─ 구독 (언론사·기자)                                             │
│     ├─ 사용자 (관심 카테고리·글자크기·비번)                            │
│     ├─ 기사 (상세 조회)                                              │
│     └─ 관리자 (수동 크롤링, 시드)                                     │
└───────┬──────────────────────┬───────────────────────┬────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌──────────────┐         ┌────────────┐          ┌──────────────────┐
│ PostgreSQL16 │         │  Redis 7   │          │  APScheduler     │
│ + pgvector   │◄───────►│  Feed 캐시 │          │  1시간 주기 크롤 │
│ HNSW 인덱스  │         │  TTL 5분   │          │  startup 크롤 1회│
└──────────────┘         └────────────┘          └────┬─────────────┘
                                                      │
                                                      ▼
                           ┌──────────────────────────────────┐
                           │ Crawl Pipeline                   │
                           │  1) 네이버 뉴스 API (BS4 파싱)    │
                           │  2) Ko-SBERT 임베딩 (768d)        │
                           │  3) LLM 요약(CT-01 Llama3)        │
                           │  4) LLM 분류(CT-02 GPT/Fuzzy)    │
                           │  5) 신뢰도 점수(RB01~RB04)        │
                           │  6) DB 저장 + Redis 캐시 무효화   │
                           └──────────────────────────────────┘
```

---

## 3. 핵심 알고리즘

### 3.1 추천 스코어 공식 (투 트랙)

**추천 트랙** (AI 맞춤 추천, 최대 50건)
```
Score = (코사인유사도 × 0.40)          # 관심 벡터와 유사도
      + (최신성       × 0.20)          # exp(-0.05 × 경과시간h)
      + (구독 부스트  × 0.20)          # 구독 언론사/기자면 +1
      + (신뢰도       × 0.20)          # credibility / 100
      - (비관심 패널티 × 0.25)          # 싫어요 벡터와 유사도
    × 1.3  (if 구독된 언론사/기자)      # 구독 부스트 배수
```

**구독 트랙** (구독 언론사/기자, 최대 10건)
```
Score = (최신성 × 0.50) + (신뢰도 × 0.50)
```

### 3.2 EMA 피드백 벡터 업데이트 (관심사 실시간 학습)

```
■ 기사 읽음 →  V_interest = 0.15 × V_article + 0.85 × V_interest_old
■ 관심없음 →  V_dislike  = 0.10 × V_article + 0.90 × V_dislike_old
■ Undo      →  V_old     = (V_new − 0.10 × V_article) / 0.90   (역산)
■ L2 정규화  →  최종 벡터는 단위벡터로 유지 → 코사인 유사도 안정성 보장
```

### 3.3 뉴스 신뢰도 점수 (0~100점)

**산출 방식: 규칙 기반 결정론적 계산** (`backend/app/services/credibility.py`).
LLM에 의존하지 않으므로 같은 기사는 항상 같은 점수로 평가됩니다.

| 코드 | 항목 | 가중치 | 구체적 계산 규칙 |
|------|------|--------|------------------|
| **RB-01** | 문체 중립성 | 30% | 제목·본문에서 `충격`, `역대급`, `미친`, `참사` 등 선정적 어휘 40여 개를 정규식 매칭. 제목 출현은 2배 가중. 0개→100 / 1~2→85 / 3~5→65 / 6~10→45 / 11+→25 |
| **RB-02** | 정보 밀도 | 25% | 본문 내 숫자(`\d+`), 날짜(`2025년`, `3월 15일`), 단위(`%`, `원`, `명`, `km`) 매칭 합계를 본문 길이로 나눠 1000자당 밀도 산출. 밀도 5 이상 → 100점 |
| **RB-03** | 인용구 존재 | 25% | 직접 인용(`"…"`, `「…」`, `『…』`) + 간접 인용(`…라고 말했다/밝혔다/전했다`) 개수. 0→0 / 1→55 / 2→75 / 3→90 / 4+→100 |
| **RB-04** | 기자 실명 | 20% | `_extract_journalist()`가 본문 끝 200자에서 `XXX 기자/특파원/통신원` 패턴 매칭. 있으면 100, 없으면 0 |

**최종 신뢰도 = RB-01×0.30 + RB-02×0.25 + RB-03×0.25 + RB-04×0.20**

프론트엔드에서 3단계 배지로 시각화:
- 🟢 초록 (90+)  /  🟡 노랑 (70~89)  /  🔴 빨강 (~69)

> **참고**: 이전 버전에서는 Llama 3에게 JSON 스키마로 RB-01~04 점수를 직접 생성시켰으나, 8B 모델이 숫자 서브필드를 빈번히 누락해 `_clamp` fallback(50)으로 수렴 → **대부분의 기사가 50점 고착** 버그를 유발했습니다. 규칙 기반 전환으로 해결됨. 자세한 내용은 문서 최상단 [최근 업데이트](#-최근-업데이트-2026-04-17) 섹션 참조.

### 3.4 LLM 3단계 폴백 체인

```
1순위: Llama 3 (Ollama, 로컬)         — 무료·무제한·오프라인
    ↓ 실패 시
2순위: Claude Haiku 4.5  (Anthropic)   — API 키 있을 때만
    ↓ 실패 시
3순위: GPT-4o-mini        (OpenAI)     — API 키 있을 때만
    ↓ 실패 시 (3회 재시도 후)
Fallback: "사회" 카테고리 + 원문 앞 3문장 요약
```

### 3.5 가용성 제어 (NFR)

| 메커니즘 | 설명 |
|---------|------|
| **서킷 브레이커** | 외부 API 5회 연속 실패 → 30초간 호출 차단 |
| **백프레셔** | 큐 >100 → 일시 중지 / <50 → 재개 |
| **적응형 수집량** | CPU<50%: 50건 / 50~70%: 30건 / >70%: 15건 |
| **DB 지수 백오프** | 초기 2초 → 2·4·8·16·32초 최대 5회 재시도 |
| **Redis 캐시 무효화** | 크롤링 성공 시 `user:*:feed` 일괄 삭제 |

---

## 4. 기술 스택

### 4.1 백엔드

| 계층 | 기술 | 버전 | 역할 |
|------|------|------|------|
| 웹 프레임워크 | FastAPI | 0.115 | 비동기 REST API |
| ASGI 서버 | Uvicorn | 0.30 | 프로덕션 서버 |
| ORM | SQLAlchemy[asyncio] | 2.0 | 비동기 ORM |
| DB 드라이버 | asyncpg | 0.30 | 비동기 PostgreSQL |
| DB | PostgreSQL + pgvector | 16 + 0.3 | 벡터 DB (HNSW) |
| 캐시 | Redis | 7 | 피드 캐싱 |
| 인증 | python-jose + bcrypt | 3.3 + 4.2 | JWT, 비밀번호 해시 |
| 임베딩 | sentence-transformers (Ko-SBERT) | 3.1 | 한국어 768d 벡터 |
| LLM | Anthropic + OpenAI SDK | 0.39 / 1.51 | 폴백 클라이언트 |
| 스케줄러 | APScheduler | 3.10 | 1시간 주기 크롤 |
| Rate-limit | SlowAPI | 0.1.9 | 분당 60회 제한 |
| 크롤링 | httpx + aiohttp + BS4 | 0.27 / 3.10 / 4.12 | 네이버 뉴스 파싱 |
| 검증 | Pydantic v2 + pydantic-settings | 2.9 / 2.5 | 스키마·환경설정 |

### 4.2 프론트엔드

| 계층 | 기술 | 버전 | 역할 |
|------|------|------|------|
| UI | React | 18.3 | SPA |
| 빌드 도구 | Vite | 5.4 | 개발 서버·프로덕션 빌드 |
| 라우팅 | react-router-dom | 6.30 | SPA 라우팅 |
| HTTP | Axios | 1.7 | JWT 인터셉터·리프레시 |
| 상태 | React Context + useState | — | 테마 컨텍스트 |
| 영속화 | localStorage | — | 토큰·테마·글자 크기 |
| 스타일 | Plain CSS + 변수 | — | 다크 모드, WCAG AA |

### 4.3 인프라

| 계층 | 기술 |
|------|------|
| 컨테이너 | Docker Compose (PostgreSQL + Redis) |
| 로컬 LLM | Ollama (Llama 3 8B) |
| 개발 환경 | Windows/Mac/Linux (크로스 플랫폼) |

---

## 5. 디렉터리 구조 및 파일별 상세 설명

```
news-curator/
├── README.md                        # ← 본 문서
├── docker-compose.yml               # PostgreSQL + Redis 컨테이너
├── run_all.bat                      # Windows 원클릭 실행 스크립트
├── start_backend.py                 # 백엔드 실행 래퍼 (uvicorn)
├── start_frontend.js                # 프론트엔드 실행 래퍼 (npm run dev)
├── .gitignore
│
├── backend/
│   ├── .env.example                 # 환경변수 템플릿
│   ├── config.yaml                  # 알고리즘 가중치·LLM 설정 (외부 설정)
│   ├── requirements.txt             # Python 의존성
│   ├── scripts/
│   │   └── recalculate_credibility.py  # 기존 기사 신뢰도 백필 스크립트
│   └── app/
│       ├── main.py                  # FastAPI 엔트리포인트 (lifespan)
│       ├── models.py                # SQLAlchemy ORM 모델
│       ├── schemas.py               # Pydantic v2 DTO
│       │
│       ├── core/
│       │   ├── config.py            # Pydantic Settings (env 로드)
│       │   ├── yaml_config.py       # config.yaml 로더
│       │   ├── database.py          # 비동기 엔진·세션, init_db()
│       │   ├── auth.py              # JWT 발급·검증, bcrypt 해시
│       │   ├── redis.py             # Redis 싱글턴
│       │   └── limiter.py           # SlowAPI 레이트리미터
│       │
│       ├── api/
│       │   ├── auth.py              # /api/auth  회원가입·로그인·리프레시·비번재설정
│       │   ├── users.py             # /api/users  내 정보·관심카테고리·글자크기
│       │   ├── feed.py              # /api/feed   개인화 피드
│       │   ├── feedback.py          # /api/articles/{url}/read|dislike + Undo
│       │   ├── subscriptions.py     # /api/subscriptions  언론사·기자 구독
│       │   ├── articles.py          # /api/articles/{url}  기사 단건 조회
│       │   └── admin.py             # /api/admin  수동 크롤링·샘플 시드
│       │
│       └── services/
│           ├── crawler.py           # 네이버 뉴스 API + BS4 본문 추출
│           ├── credibility.py       # ★ 규칙 기반 신뢰도 계산기 (신규)
│           ├── embedding.py         # Ko-SBERT 768d 임베딩 (싱글턴 모델)
│           ├── llm_processor.py     # Llama(요약) + GPT(분류) 폴백 체인
│           ├── recommendation.py    # 추천 트랙·구독 트랙 스코어링
│           ├── pipeline.py          # APScheduler 수집 파이프라인
│           └── resilience.py        # 서킷브레이커·백프레셔·적응형 수집
│
└── frontend/
    ├── package.json                 # React·Axios·Vite 의존성
    ├── vite.config.js               # /api → :8000 프록시
    ├── index.html
    └── src/
        ├── main.jsx                 # React 18 createRoot
        ├── App.jsx                  # Router + 헤더 + PrivateRoute 가드
        ├── App.css                  # 헤더·네비 스타일
        ├── index.css                # 글로벌 변수 (light/dark), WCAG
        │
        ├── api/
        │   ├── client.js            # Axios + JWT 자동 리프레시 인터셉터
        │   ├── feed.js              # GET /api/feed, read, dislike, undo
        │   ├── articles.js          # 기사 단건
        │   ├── subscriptions.js     # 구독 CRUD
        │   └── users.js             # 관심 카테고리·글자 크기 저장
        │
        ├── contexts/
        │   └── ThemeContext.jsx     # 다크 모드 Context + localStorage
        │
        ├── components/
        │   ├── Feed.jsx             # 메인 피드 (구독 + 추천 + 필터 + 정렬)
        │   ├── Feed.css
        │   ├── ArticleCard.jsx      # 기사 카드 (신뢰도 배지·읽음 표시)
        │   ├── ArticleCard.css
        │   ├── CategoryFilter.jsx   # 카테고리 탭 (전체/정치/IT/...)
        │   ├── CategoryFilter.css
        │   ├── SortFilter.jsx       # ★ 정렬 필터 (추천순/최신순/신뢰도순)
        │   ├── SortFilter.css
        │   ├── CredibilityChart.jsx # 신뢰도 4지표 바 차트 (상세페이지용)
        │   ├── CredibilityChart.css
        │   ├── Login.jsx            # 로그인 폼
        │   ├── Register.jsx         # 회원가입 (관심 카테고리 선택 포함)
        │   ├── Register.css
        │   ├── Settings.jsx         # 글자 크기 4단계 + 비번 변경
        │   ├── Settings.css
        │   ├── ThemeToggle.jsx      # 다크/라이트 모드 스위치
        │   ├── ThemeToggle.css
        │   ├── Toast.jsx            # 5초 Undo 토스트
        │   └── Toast.css
        │
        ├── pages/
        │   ├── ArticleDetail.jsx    # 기사 상세 페이지 (CredibilityChart 포함)
        │   ├── ArticleDetail.css
        │   ├── Subscriptions.jsx    # 구독 관리 페이지
        │   ├── Subscriptions.css
        │   ├── ForgotPassword.jsx   # 비밀번호 찾기
        │   ├── ResetPassword.jsx    # 비밀번호 재설정
        │   └── AuthExtra.css
        │
        └── utils/
            └── credibility.js       # 신뢰도 색상 라벨 유틸
```

### 5.1 백엔드 파일 상세

#### `backend/app/main.py`
FastAPI 앱의 **엔트리포인트**. 비동기 `lifespan` 컨텍스트로 다음을 수행:
1. PostgreSQL + pgvector 초기화 (지수 백오프 재시도)
2. Redis 연결 풀 생성
3. APScheduler 1시간 주기 등록
4. **서버 시작 직후 백그라운드 태스크**:
   - Ko-SBERT 프리로드 → 샘플 시드 → 즉시 크롤링 1회
   - 결과 0건이면 60초 후 재시도
5. Rate-limit, CORS, 전체 라우터 등록

#### `backend/app/models.py`
SQLAlchemy ORM 모델 정의:
- **`User`**: 이메일/비번/이름/관심카테고리/interest_vector(768)/disinterest_vector(768)/글자크기
- **`Article`**: URL(PK)/제목/본문/요약/카테고리/embedding(768, HNSW)/credibility/rb01~rb04/press/journalist/published_at
- **`Subscription`**: user_email FK + target_type (press|journalist) + target_name
- **`ReadLog`**: user_email + article_url + read_at (복합 PK)
- **`DislikeLog`**: user_email + article_url + is_active + created_at
- **`PasswordReset`**: token + user_email + expires_at

#### `backend/app/schemas.py`
Pydantic v2 DTO:
- 요청: `UserCreate`, `UserLogin`, `PasswordChange`, `SubscriptionCreate`, …
- 응답: `ArticleSummary` (recommendation_score 포함), `FeedResponse` (subscription_track + recommendation_track), `UserOut`, …

#### `backend/app/core/config.py`
Pydantic `BaseSettings`로 `.env` + OS 환경변수 로드:
- DB/Redis URL, JWT 비밀키, Ollama·Claude·OpenAI 설정
- 크롤 카테고리 8종, 즉시 크롤 옵션, 자동 시드 옵션
- 분당 60회 Rate-limit

#### `backend/app/core/yaml_config.py`
`config.yaml` 로더 — LLM 모델, 추천 가중치, 카테고리 리스트를 **코드 수정 없이** 조정 가능 (NFR-E03).

#### `backend/app/core/database.py`
- `create_async_engine` (echo=False, pool_pre_ping=True)
- `init_db()`: pgvector 확장 → 테이블 생성 → HNSW 인덱스 (articles.embedding)
- 지수 백오프 5회 재시도로 Docker 재기동 레이스 대응

#### `backend/app/core/auth.py`
- `hash_password()` (bcrypt 12 라운드)
- `verify_password()`
- `create_access_token()` / `create_refresh_token()` (HS256, iss/exp/type claim)
- `decode_token()` (만료·서명 검증)

#### `backend/app/api/feed.py`
**`GET /api/feed`** — 사용자 인증 → Redis 캐시 조회 → 미스 시 `build_feed()` 호출 → 투 트랙 반환. TTL 300초.

#### `backend/app/api/feedback.py`
- **`POST /api/articles/{url}/read`**: `ReadLog` 저장 + 관심 벡터 EMA 업데이트
- **`POST /api/articles/{url}/dislike`**: `DislikeLog` 저장 + 비관심 벡터 EMA 업데이트 + `user:{email}:feed` 캐시 무효화
- **`DELETE /api/v1/feed/{url}/dislike`**: is_active=False로 변경 + 비관심 벡터 역산 복원

#### `backend/app/services/crawler.py`
- `fetch_articles()`: 카테고리별 네이버 뉴스 API 호출 (쿼리 키워드 `CATEGORY_KEYWORDS` 매핑)
- `extract_body()`: BS4로 `#dic_area` / `.newsct_article` 등 다양한 셀렉터 시도
- `CATEGORY_KEYWORDS` 8개 카테고리: 정치/경제/사회/생활·문화/IT·과학/세계/연예/스포츠

#### `backend/app/services/embedding.py`
- 모듈 레벨 싱글턴으로 Ko-SBERT 모델 1회만 로드
- `get_embedding(text)` → `np.ndarray(768)` 반환
- asyncio Thread Pool로 호출 (`torch`는 동기)

#### `backend/app/services/llm_processor.py`
- **CT-01 (요약)**: `LlamaService.summarize()` — 3줄 한국어 요약만 반환 (이제 신뢰도 계산은 하지 않음)
- **CT-02 (분류)**: `GPTService.classify()` → 3회 재시도 + 0.5 × n 지수 백오프
- **퍼지 카테고리 매칭**: `IT/과학` → `IT·과학`, `생활/문화` → `생활·문화` 자동 정규화
- **process_article_with_llm()**: CT-01 → CT-02 → `credibility.calculate_credibility()` 순서로 호출

#### `backend/app/services/credibility.py`  ★ 신규
규칙 기반 결정론적 신뢰도 계산기. LLM에 의존하지 않으므로 **같은 입력 → 항상 같은 출력**을 보장합니다. 과거에는 Llama 3가 JSON 서브필드를 자주 누락해 모든 기사 신뢰도가 50점으로 수렴하던 버그의 해결책.
- `calculate_rb01_tone(title, body)` — 선정적 어휘 사전 매칭 (제목 2× 가중)
- `calculate_rb02_density(body)` — 숫자·날짜·단위 밀도 (1000자당)
- `calculate_rb03_quotes(body)` — 직접/간접 인용 개수
- `calculate_rb04_journalist(journalist)` — 바이라인 존재 여부
- `calculate_credibility(...)` — 4지표 + 가중합 최종 점수 dict 반환

#### `backend/app/services/recommendation.py`
- `build_feed(user)`: 구독 트랙 + 추천 트랙 병합
- `_build_recommendation_track()`: 경로 A(콜드스타트 카테고리 평균벡터) / 경로 B(정상 유저 **최신순 후보 200건 + 가중합 스코어링**)
- 구독 부스트 × 1.3, dislike 패널티 × 0.25
- is_subscribed `bool()` 래핑 (Pydantic None 방지)

#### `backend/app/services/pipeline.py`
- `start_scheduler()`: APScheduler 1시간 간격 크롤링 등록
- `run_crawl_pipeline()`: 수집 → LLM 처리 → 임베딩 → DB 저장 → **Redis 캐시 일괄 무효화**
- `_process_single_article()`: 임베딩 실패 시 명시적 롤백

#### `backend/app/services/resilience.py`
- `CircuitBreaker`: 5회 실패 → open → 30초 후 half-open
- `backpressure_gate()`: 큐 길이 모니터링
- `adaptive_collect_count()`: psutil CPU로 수집량 동적 조정

### 5.2 프론트엔드 파일 상세

#### `src/api/client.js`
Axios 인스턴스 + **JWT 인터셉터**:
- 요청: `Authorization: Bearer <access_token>` 자동 첨부
- 응답 401: refresh 토큰으로 재발급 → 원래 요청 재시도 → 실패 시 `/login` 이동
- `baseURL: '/api'` (Vite proxy → `:8000`)

#### `src/components/Feed.jsx`
메인 피드 컴포넌트. 렌더 파이프라인:
```
fetchFeed() → feed state
  ↓
visibleSubscription  = subscriptionTrack  − hiddenUrls
visibleRecommendation = recommendationTrack − hiddenUrls
  ↓
filteredRecommendation = visibleRecommendation − 카테고리 필터
  ↓
sortedRecommendation = applySortToItems(filteredRecommendation, activeSort)
  ↓
render: [CategoryFilter] [SortFilter] [구독 트랙 가로스크롤] [추천 그리드]
```

#### `src/components/SortFilter.jsx` ★ 최근 추가
정렬 옵션 3종:
- **추천순**: `item.score DESC` (기본)
- **최신순**: `published_at DESC`
- **신뢰도순**: `credibility DESC` (동점 → 최신순 tiebreaker)

`applySortToItems(items, sortKey)` 순수 함수 → 새 배열 반환 (React immutability).

#### `src/components/ArticleCard.jsx`
- 카드 상단: 카테고리 / 신뢰도 배지 (90+ 초록 / 70+ 노랑 / ~69 빨강)
- 본문: 제목 / 3줄 요약 / 언론사 · 기자 · 발행시각
- 우측 상단: 관심없음(×) 버튼 → optimistic 숨김 + 5초 Undo 토스트
- 클릭: `/article?url=...` 로 이동 + `markRead()` 호출
- 읽은 기사는 흐리게(dim) 표시

#### `src/components/CategoryFilter.jsx`
9개 탭 (전체 + 8 카테고리). 활성 탭 accent 색상.

#### `src/components/Register.jsx`
회원가입 시 **관심 카테고리 2개 이상 선택**을 강제 (콜드 스타트 벡터 초기화용).

#### `src/components/Settings.jsx`
- 글자 크기 4단계 (소/중/대/특대) → `--font-size-multiplier` CSS 변수 조정
- 현재 비번 + 새 비번 + 확인 → `PATCH /api/users/me/password`

#### `src/contexts/ThemeContext.jsx`
다크/라이트 Context. `localStorage.theme` 영속화.

#### `src/pages/ArticleDetail.jsx`
- 단건 기사 조회 (`GET /api/articles/{url}`)
- CredibilityChart로 RB-01~RB-04 4지표 바 차트 렌더링
- '관심없음' 처리 후 피드로 복귀

---

## 6. 빠른 시작 (Quick Start)

**최소 요구사항만 설치하면 5분 안에 실행 가능.**

```bash
# 1. 필수 패키지
#    - Docker Desktop
#    - Python 3.12+
#    - Node.js 20+
#    - Ollama  (https://ollama.com/download)

# 2. 저장소 클론
git clone https://github.com/NEO8320/capstone_project.git
cd capstone_project

# 3. Llama 3 모델 다운로드 (4.7GB)
ollama pull llama3

# 4. PostgreSQL + Redis 시작
docker-compose up -d

# 5. 백엔드 의존성 설치 + 환경변수
cd backend
pip install -r requirements.txt
copy .env.example .env     # Windows
# cp .env.example .env     # Mac/Linux

# 6. 프론트엔드 의존성 설치
cd ../frontend
npm install

# 7. 실행 (프로젝트 루트에서)
cd ..
run_all.bat                # Windows 원클릭
# 또는 수동: python start_backend.py  ·  npm --prefix frontend run dev

# 8. 브라우저 열기
#    http://localhost:5173
```

---

## 7. 단계별 설치 가이드

### 7.1 사전 설치 프로그램

| 프로그램 | 버전 | 용도 | 다운로드 |
|----------|------|------|----------|
| Docker Desktop | 최신 | PostgreSQL + Redis | <https://www.docker.com/products/docker-desktop/> |
| Python | 3.12+ | FastAPI 백엔드 | <https://www.python.org/downloads/> |
| Node.js | 20+ | React + Vite | <https://nodejs.org/> |
| Ollama | 최신 | 로컬 Llama 3 LLM | <https://ollama.com/download> |
| Git | 최신 | 소스 관리 | <https://git-scm.com/> |

### 7.2 Step-by-step

#### Step 1 — 저장소 클론
```bash
git clone https://github.com/NEO8320/capstone_project.git
cd capstone_project
```

#### Step 2 — Ollama에 Llama 3 다운로드
```bash
ollama pull llama3
ollama run llama3       # 'Hello' 입력해 동작 확인 → Ctrl+D로 종료
```

#### Step 3 — Docker 컨테이너 기동
```bash
docker-compose up -d
docker ps               # news_curator_db / news_curator_redis 확인
```

#### Step 4 — 백엔드 환경 설정
```bash
cd backend

# 가상환경 (선택 but 권장)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Mac/Linux

# 의존성 설치 (torch 포함으로 약 2GB)
pip install -r requirements.txt

# 환경변수 복사
copy .env.example .env        # Windows
# cp .env.example .env        # Mac/Linux
```

`.env`에서 반드시 수정할 값:
- `SECRET_KEY` → 랜덤 32바이트 이상 (예: `python -c "import secrets; print(secrets.token_hex(32))"`)
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` → [네이버 개발자센터](https://developers.naver.com/main/) 앱 등록 후 발급

선택 값:
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — 로컬 Llama만으로도 동작하므로 비워둬도 OK

#### Step 5 — 프론트엔드 의존성 설치
```bash
cd ../frontend
npm install
```

#### Step 6 — 서버 실행

**방법 A : 원클릭 (Windows 권장)**
```bash
cd ..
run_all.bat
```
세 개의 터미널이 자동으로 열립니다:
1. Docker(이미 기동 중이면 skip)
2. Uvicorn (`:8000`)
3. Vite Dev Server (`:5173`)

**방법 B : 수동 실행**

터미널 1 — 백엔드
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

터미널 2 — 프론트엔드
```bash
cd frontend
npm run dev
```

#### Step 7 — 브라우저 접속

| 서비스 | URL |
|--------|-----|
| 프론트엔드 | <http://localhost:5173> |
| 백엔드 API | <http://localhost:8000> |
| Swagger UI | <http://localhost:8000/docs> |
| ReDoc | <http://localhost:8000/redoc> |
| Health | <http://localhost:8000/health> |

#### Step 8 — 초기 데이터 확인

- 서버 시작 후 **최대 2분 내로** 60~100건 기사가 자동 수집됩니다 (Ko-SBERT 프리로드 포함)
- DB가 비어 있으면 `AUTO_SEED_ON_EMPTY_DB=True`로 11건의 샘플 기사가 먼저 시드됩니다
- APScheduler가 이후 **1시간마다 자동 재수집**

---

## 8. 사용 방법 (User Guide)

### 8.1 회원가입
1. `/register` 이동
2. 이메일 · 비밀번호(8자 이상) · 이름 입력
3. **관심 카테고리 2개 이상 선택** (콜드 스타트 벡터 초기화용)
4. 제출 → 자동 로그인 → `/feed`

### 8.2 피드 화면 (핵심)
- **상단 헤더**: 피드 / 구독 / 설정 / 로그아웃 / 테마 토글
- **카테고리 필터**: 전체 · 정치 · 경제 · 사회 · IT·과학 · 생활·문화 · 세계 · 연예 · 스포츠
- **정렬 필터** (★ 최근 추가):
  - **추천순** — 개인화 스코어 내림차순 (기본)
  - **최신순** — 발행일 내림차순
  - **신뢰도순** — credibility 내림차순 (동점 시 최신순)
- **구독 트랙** (구독 있을 때만): 가로 스크롤 카드
- **추천 트랙**: 반응형 그리드 (PC 3열 / 태블릿 2열 / 모바일 1열)

### 8.3 기사 카드 상호작용
| 액션 | 결과 |
|------|------|
| 제목 클릭 | 상세 페이지 이동 + `read` 피드백 (관심 벡터 EMA 업데이트) |
| × 버튼 | 즉시 숨김 + `dislike` 전송 + 5초 Undo 토스트 |
| Undo 버튼 | 복원 + 비관심 벡터 역산 복원 |
| 신뢰도 배지 | 클릭으로 상세 페이지 이동 + 4지표 바 차트 열람 |

### 8.4 구독 관리 (`/subscriptions`)
- 언론사(조선일보, 연합뉴스 등) 또는 기자 실명으로 구독 추가
- 구독한 source의 기사는 **구독 트랙에 우선 노출** + 추천 스코어 × 1.3 부스트

### 8.5 설정 (`/settings`)
- **글자 크기 4단계**: 소(0.875×) / 중(1.0×) / 대(1.125×) / 특대(1.25×)
- **비밀번호 변경**: 현재 비번 + 새 비번(8자 이상) + 확인
- **다크 모드**: 헤더 우측 토글 스위치

### 8.6 알아두면 좋은 동작
- **관심 학습은 즉시 반영**: 기사 1~2개 읽음/싫어요만으로 다음 피드 로드 시 변화 체감
- **캐시 TTL 5분**: 피드백 시 즉시 무효화되므로 새로고침하면 반영됨
- **크롤링은 1시간 주기**: 수동 재수집은 `POST /api/admin/crawl` (관리자 API)

---

## 9. API 레퍼런스

### 9.1 인증 — `/api/auth/*`

| Method | Path | Body | 설명 |
|--------|------|------|------|
| POST | `/register` | `UserCreate` (email, password, name, interest_categories[]) | 회원가입 + 콜드스타트 벡터 초기화 |
| POST | `/login` | `OAuth2PasswordRequestForm` | JWT Access + Refresh 발급 |
| POST | `/refresh` | `{refresh_token}` | Access 토큰 재발급 |
| POST | `/forgot-password` | `{email}` | 재설정 토큰 발급 |
| POST | `/reset-password` | `{token, new_password}` | 비번 재설정 |

### 9.2 사용자 — `/api/users/*`

| Method | Path | 설명 |
|--------|------|------|
| GET | `/me` | 내 정보 조회 |
| PATCH | `/me/interest-categories` | 관심 카테고리 수정 (벡터 재초기화) |
| PATCH | `/me/font-size` | 글자 크기 레벨 저장 (0~3) |
| PATCH | `/me/password` | 비밀번호 변경 |

### 9.3 피드 · 피드백 — `/api/*`

| Method | Path | 설명 |
|--------|------|------|
| GET | `/feed` | **투 트랙 피드** (구독 ≤10 + 추천 ≤50) |
| GET | `/articles/{url:path}` | 기사 단건 (신뢰도 4지표 포함) |
| POST | `/articles/{url}/read` | 읽음 + 관심 벡터 EMA 업데이트 |
| POST | `/articles/{url}/dislike` | 관심없음 + 비관심 벡터 EMA |
| DELETE | `/v1/feed/{url}/dislike` | Undo (벡터 역산 복원) |

### 9.4 구독 — `/api/subscriptions/*`

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 내 구독 목록 |
| POST | `/` | 구독 추가 `{target_type, target_name}` |
| DELETE | `/{subscription_id}` | 구독 해제 |

### 9.5 관리자 · 시스템

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/admin/crawl` | 수동 크롤링 실행 (dev 용) |
| POST | `/api/admin/seed` | 샘플 기사 강제 시드 |
| GET | `/health` | DB·Redis 상태 반환 |
| GET | `/docs` | Swagger UI |

---

## 10. 환경 변수 레퍼런스

`.env` 파일 (backend/.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/news_curator` | PostgreSQL + asyncpg 연결 문자열 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 연결 문자열 |
| `FEED_CACHE_TTL` | `300` | 피드 캐시 만료 시간(초) |
| `SECRET_KEY` | (빈값) | JWT 서명 비밀키 — **반드시 교체** |
| `ALGORITHM` | `HS256` | JWT 알고리즘 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access 토큰 수명 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh 토큰 수명 |
| `NAVER_CLIENT_ID` | (빈값) | 네이버 뉴스 API Client ID |
| `NAVER_CLIENT_SECRET` | (빈값) | 네이버 뉴스 API Client Secret |
| `LLM_PRIMARY_MODEL` | `llama3` | 1순위 LLM 모델명 |
| `LLM_PRIMARY_BASE_URL` | `http://localhost:11434/v1` | 1순위 LLM API (Ollama) |
| `LLM_FALLBACK_CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | 2순위 모델 |
| `ANTHROPIC_API_KEY` | (빈값) | Claude API 키 (선택) |
| `LLM_FALLBACK_OPENAI_MODEL` | `gpt-4o-mini` | 3순위 모델 |
| `LLM_FALLBACK_OPENAI_BASE_URL` | `https://api.openai.com/v1` | 3순위 API |
| `OPENAI_API_KEY` | (빈값) | OpenAI API 키 (선택) |
| `EMBEDDING_MODEL_NAME` | `snunlp/KR-SBERT-V40K-klueNLI-augSTS` | Ko-SBERT 모델 ID |
| `EMBEDDING_DIM` | `768` | 임베딩 차원 |
| `CRAWL_INTERVAL_HOURS` | `1` | APScheduler 주기 |
| `CRAWL_ON_STARTUP` | `True` | 서버 시작 직후 1회 크롤 |
| `AUTO_SEED_ON_EMPTY_DB` | `True` | 빈 DB에 샘플 자동 시드 |
| `STARTUP_CRAWL_RETRY_ON_ZERO` | `1` | 0건일 때 재시도 횟수 |
| `RATE_LIMIT` | `60/minute` | 분당 요청 제한 |
| `DEBUG` | `False` | 디버그 모드 |

`config.yaml` (backend/config.yaml) — 코드 수정 없이 조정

| 키 | 설명 |
|----|------|
| `llm.summarizer.*` | CT-01 요약 모델 설정 |
| `llm.classifier.*` | CT-02 분류 모델 설정 |
| `recommendation.weight_*` | 추천 가중치 (임베딩 0.40, 최신성 0.20, 구독 0.20, 신뢰도 0.20, dislike -0.25) |
| `recommendation.subscription_boost_multiplier` | 구독 부스트 (1.3) |
| `categories` | 8종 카테고리 리스트 (중앙점 `·` 유지 필수) |

---

## 11. 데이터베이스 스키마

```
┌─────────────────────────┐       ┌────────────────────────┐
│        articles         │       │         users          │
├─────────────────────────┤       ├────────────────────────┤
│ url            PK       │       │ email           PK     │
│ title                   │       │ hashed_password        │
│ body                    │       │ name                   │
│ summary                 │       │ interest_categories[]  │
│ category                │       │ interest_vector    (768)│
│ embedding       (768)   │       │ disinterest_vector (768)│
│ credibility  (0~100)    │       │ font_size_level  (0~3) │
│ rb01_tone      (0~100) │       │ created_at             │
│ rb02_density   (0~100) │       └────────────────────────┘
│ rb03_quotes    (0~100) │               │
│ rb04_journalist (0~100)│               │
│ press                   │               ├────────┐
│ journalist              │               │        │
│ published_at            │               │        │
│ created_at              │               │        │
│ INDEX embedding HNSW    │               │        │
│ INDEX published_at      │               │        │
└───┬─────────────────────┘               │        │
    │                                     │        │
    │  ┌──────────────────────┐           │        │
    │  │    subscriptions     │           │        │
    │  ├──────────────────────┤           │        │
    │  │ id             PK    │           │        │
    │  │ user_email    FK─────────────────┤        │
    │  │ target_type  (press/ │                    │
    │  │              journal)│                    │
    │  │ target_name          │                    │
    │  └──────────────────────┘                    │
    │                                              │
    │  ┌──────────────────────┐                    │
    ├──│    read_logs         │                    │
    │  ├──────────────────────┤                    │
    │  │ user_email    FK─────────────────────────┤
    │  │ article_url   FK     │
    │  │ read_at              │
    │  └──────────────────────┘
    │
    │  ┌──────────────────────┐
    └──│    dislike_logs      │
       ├──────────────────────┤
       │ user_email    FK─────────────────────────┤
       │ article_url   FK     │
       │ is_active            │
       │ created_at           │
       └──────────────────────┘

┌──────────────────────────┐
│     password_resets      │
├──────────────────────────┤
│ token             PK     │
│ user_email     FK────────────────────────────────┤
│ expires_at               │
└──────────────────────────┘
```

### 인덱스
- `articles.embedding` — pgvector **HNSW (cosine)** — 벡터 검색용
- `articles.published_at` — B-tree DESC — 최신순 조회용
- `articles.category` — B-tree — 카테고리 필터 최적화

---

## 12. 데이터 플로우

### 12.1 크롤링 → 저장
```
 APScheduler (매시)
    │
    ▼
 Naver API (카테고리별 10건 × 8 = 80건)
    │
    ▼
 URL 중복 확인 (DB SELECT)
    │
    ▼
 for each article:
   ├─ BS4 본문 추출
   ├─ Ko-SBERT 임베딩 (768d)
   ├─ CT-01 Llama 요약 (3회 재시도)
   ├─ CT-02 GPT 분류 + 퍼지 매칭 (3회 재시도)
   ├─ RB-01~RB-04 신뢰도 계산
   └─ INSERT articles
    │
    ▼
 Redis: DEL user:*:feed  ← 새 기사 즉시 반영
```

### 12.2 피드 조회 → 렌더
```
 GET /api/feed (JWT)
    │
    ▼
 Redis GET user:{email}:feed
    ├─ HIT → 즉시 반환
    └─ MISS
         │
         ▼
      recommendation.build_feed(user)
         ├─ 구독 트랙: subscription_track SQL (구독 언론사·기자 최신 10)
         └─ 추천 트랙:
              ├─ 경로 A (콜드스타트): 카테고리 평균벡터로 KNN
              └─ 경로 B (정상):
                    ├─ 최신순 200건 후보 조회 (published_at DESC)
                    ├─ 각 기사: 유사도 + 최신성 + 구독부스트 + 신뢰도 − dislike
                    └─ Top 50 정렬
         │
         ▼
      Redis SET user:{email}:feed TTL=300
         │
         ▼
      JSON 응답
         │
         ▼
 Axios → Feed.jsx state
         │
         ▼
 visible → filtered(카테고리) → sorted(추천/최신/신뢰도) → render
```

### 12.3 피드백 → 벡터 업데이트
```
 POST /articles/{url}/read
    │
    ▼
 INSERT read_logs (upsert)
    │
    ▼
 V_interest_new = 0.15 × V_article + 0.85 × V_interest_old  (EMA)
 L2 정규화
    │
    ▼
 UPDATE users.interest_vector
    │
    ▼
 다음 /feed 요청부터 추천 결과 변화
```

---

## 13. 운영·디버깅 가이드

### 13.1 수동 크롤링 강제 실행
```bash
curl -X POST http://localhost:8000/api/admin/crawl
```

### 13.1a 기존 DB 신뢰도 일괄 재계산
구 버전으로 수집된 기사들의 신뢰도 점수를 규칙 기반 알고리즘으로 다시 산정합니다. 새 버전 배포 후 **한 번만** 실행하면 됩니다.

```bash
cd backend
python -m scripts.recalculate_credibility
```

실행 후 stdout에 다음처럼 점수 분포가 출력됩니다:
```
[Recalc] 완료 — 갱신된 기사: 73/73
[Recalc] 신뢰도 점수 분포
     0-39 :     2건 (  2.7%)
    40-59 :    16건 ( 21.9%)
    60-79 :    35건 ( 47.9%)
   80-100 :    20건 ( 27.4%)
  평균      : 72.2
  중앙값    : 71.2
```

안전 속성:
- 500건마다 commit → 장시간 락 방지
- `credibility` / `rb01~04` 컬럼만 갱신. 본문·요약·임베딩은 건드리지 않음
- 중간 실패해도 이미 처리된 기사는 보존됨

### 13.2 Redis 캐시 전체 삭제
```bash
docker exec -it news_curator_redis redis-cli
> KEYS user:*:feed
> DEL <key>
```

### 13.3 DB 직접 조회 (pgAdmin 없이)
```bash
docker exec -it news_curator_db psql -U postgres -d news_curator

# 기사 수
SELECT category, COUNT(*) FROM articles GROUP BY category;

# 내 관심 벡터 확인
SELECT email, array_length(interest_vector::real[], 1) FROM users;

# 카테고리 정규화 불일치 점검 (있으면 UPDATE 필요)
SELECT DISTINCT category FROM articles;
```

### 13.4 로그 포인트
- `[Startup]` — lifespan 초기화
- `[Pipeline]` — 크롤 파이프라인 각 단계
- `[CT-01]` / `[CT-02]` — LLM 요약·분류
- `[Recommendation]` — 피드 빌드
- `[Feedback]` — read/dislike EMA

### 13.5 성능 튜닝
| 항목 | 조정 방법 |
|------|-----------|
| 피드 응답 느림 | `FEED_CACHE_TTL` 증가 or HNSW ef_search 튜닝 |
| 크롤링 실패 급증 | `resilience.py`의 서킷브레이커 임계값 조정 |
| 임베딩 메모리 과다 | Ko-SBERT를 경량 모델(`klue/bert-base`)로 교체 |
| GPT 분류 비용 | `config.yaml`의 classifier.model → `gpt-4o-mini` 고정 |

---

## 14. FAQ & 트러블슈팅

**Q. 서버는 떴는데 피드가 비어 있어요.**
A. Ko-SBERT 모델 최초 다운로드(약 400MB)에 1~2분 걸립니다. 서버 로그에 `[Startup] Ko-SBERT 모델 프리로드 완료` 가 뜰 때까지 기다려 주세요.

**Q. `psycopg2` / `asyncpg` 설치 오류가 납니다.**
A. asyncpg만 사용합니다. `pip install -r requirements.txt` 외에 추가 설치 불필요. Windows에서는 Visual C++ Build Tools가 필요할 수 있습니다.

**Q. Ollama 없이 사용할 수 있나요?**
A. 가능합니다. `ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY` 중 하나만 설정하면 자동 폴백합니다. 단, Llama가 1순위이므로 Ollama가 실행 중이면 그쪽이 먼저 호출됩니다. 로컬 API를 비우려면 `LLM_PRIMARY_BASE_URL=`로 두세요.

**Q. `생활/문화`와 `생활·문화`가 섞여 있어요.**
A. `pipeline.py`의 `_normalize_category()`가 자동 정규화합니다. 기존 DB에 누적된 데이터는 다음 SQL로 정리:
```sql
UPDATE articles SET category = 'IT·과학'   WHERE category = 'IT/과학';
UPDATE articles SET category = '생활·문화' WHERE category = '생활/문화';
```

**Q. 신뢰도 점수가 전부 50점 근처로만 나와요.**
A. 구 버전 버그입니다. 최신 코드로 업데이트 후 다음 명령을 한 번 실행하세요:
```bash
cd backend && python -m scripts.recalculate_credibility
```
자세한 내용은 문서 최상단 [📣 최근 업데이트](#-최근-업데이트-2026-04-17) 참조.

**Q. 로그인했는데 바로 `/login`으로 돌아가요.**
A. JWT `SECRET_KEY`가 기본값이거나, 서버를 재시작해 기존 토큰이 무효화된 경우. localStorage를 비우고 다시 로그인하세요.

**Q. 크롤링이 느린데 이유가 뭔가요?**
A. 카테고리 8개 × 10건 = 80건을 순차 처리하며, 각 기사당 Llama 요약(약 5초) + GPT 분류(약 2초)가 동기적으로 돕니다. `resilience.py`의 `adaptive_collect_count()`가 CPU에 따라 수집량을 낮추기도 합니다.

**Q. 프로덕션 배포는?**
A. 이 저장소는 개발/실습용입니다. 프로덕션 시 다음을 고려:
- HTTPS + 리버스 프록시 (nginx)
- Alembic 마이그레이션 도입
- JWT `SECRET_KEY`를 Secrets Manager로
- Redis + PostgreSQL 관리형 서비스 이관
- CORS 화이트리스트 축소

---

## 라이선스 & 팀 정보

본 프로젝트는 **캡스톤 디자인 학술 목적**으로 개발되었습니다.

기여: PR·Issue 모두 환영합니다. 질문은 GitHub Issues로 남겨 주세요.

---

> **Last Updated**: 2026-04-17
> **Version**: 1.0.0
