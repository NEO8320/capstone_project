# News Curator — AI 기반 개인화 뉴스 큐레이팅 서비스

> 네이버 뉴스를 실시간으로 수집하고, AI가 요약·분류·신뢰도 평가를 거쳐
> 사용자 관심사에 맞춰 개인화 추천 피드를 구성해 주는 풀스택 웹 서비스.

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-0.3-green)](https://github.com/pgvector/pgvector)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis)](https://redis.io/)
[![Ollama](https://img.shields.io/badge/Ollama-Llama3-black)](https://ollama.com/)

---

## 목차

1. [한눈에 보기](#1-한눈에-보기)
2. [빠른 시작 (처음 실행하는 사람용)](#2-빠른-시작-처음-실행하는-사람용)
3. [매번 실행하기](#3-매번-실행하기)
4. [기술 스택](#4-기술-스택)
5. [시스템 아키텍처](#5-시스템-아키텍처)
6. [디렉터리 구조](#6-디렉터리-구조)
7. [핵심 동작 원리](#7-핵심-동작-원리)
8. [API 엔드포인트](#8-api-엔드포인트)
9. [데이터 모델](#9-데이터-모델)
10. [환경변수 레퍼런스](#10-환경변수-레퍼런스)
11. [운영 · 데이터 백업/이전](#11-운영--데이터-백업이전)
12. [트러블슈팅](#12-트러블슈팅)
13. [자주 묻는 질문 (FAQ)](#13-자주-묻는-질문-faq)

---

## 1. 한눈에 보기

**News Curator** 는 다음 흐름으로 동작합니다.

```
네이버 뉴스 API ──▶ 본문 크롤링 ──▶ AI 요약·분류·신뢰도 ──▶ 벡터 임베딩 ──▶ DB 저장
                                                                          │
사용자 ◀── 개인화 추천 피드 ◀── 추천 점수 계산 (관심 벡터 × 코사인 유사도) ◀──┘
```

### 주요 기능

| 기능 | 설명 |
|------|------|
| **자동 뉴스 수집** | 8개 카테고리(정치/경제/사회/IT·과학/생활·문화/세계/연예/스포츠)를 1시간마다 자동 크롤링 |
| **AI 3줄 요약** | 로컬 Llama 3 가 기사 본문을 3줄로 요약 (CT-01) |
| **AI 카테고리 분류** | GPT-4o-mini 가 본문 기반으로 카테고리 재분류 (CT-02) |
| **신뢰도 점수** | 규칙 기반으로 문체·정보밀도·인용·출처를 평가해 0~100점 산출 |
| **개인화 추천** | Ko-SBERT 임베딩 + 사용자 관심 벡터의 코사인 유사도로 맞춤 정렬 |
| **관심사 학습** | 읽음/관심없음 피드백으로 관심·비관심 벡터를 EMA 업데이트 |
| **구독** | 언론사/기자 구독 시 해당 기사를 별도 트랙으로 우선 노출 |

---

## 2. 빠른 시작 (처음 실행하는 사람용)

> **이 프로젝트는 Windows 기준으로 작성되었습니다.**
> `.bat` 스크립트가 모든 과정을 자동화합니다. 명령어를 외울 필요 없이 순서만 따라오세요.

### 2-1. 사전 준비물 (4가지 설치)

아래 4개를 먼저 설치해야 합니다. 이미 있으면 건너뛰세요.

| 프로그램 | 버전 | 다운로드 | 설치 시 주의 |
|----------|------|----------|--------------|
| **Python** | 3.12 이상 | https://www.python.org/downloads/ | 설치 화면에서 **"Add Python to PATH" 체크 필수** |
| **Node.js** | 20 LTS | https://nodejs.org/ | LTS 버전 선택 |
| **Docker Desktop** | 최신 | https://www.docker.com/products/docker-desktop/ | 설치 후 **실행해서 켜 둘 것** |
| **Ollama** | 최신 | https://ollama.com/download | 설치 후 아래 2-4 단계에서 모델 다운로드 |

### 2-2. 프로젝트 내려받기 + 최초 1회 설치

PowerShell 또는 파일 탐색기에서 프로젝트 폴더로 이동한 뒤:

```powershell
cd C:\capstone_project-chore-docs-and-scripts

# 최초 1회만 실행 — 가상환경 생성 + 라이브러리 설치 + .env 준비를 전부 자동 처리
.\setup.bat
```

`setup.bat` 이 자동으로 수행하는 작업:

| 단계 | 내용 |
|------|------|
| [1/5] | Python 3.12+ 설치 확인 |
| [2/5] | `backend\.venv` 가상환경 생성 + `pip install -r requirements.txt` |
| [3/5] | `frontend\node_modules` 설치 (`npm install`) |
| [4/5] | `backend\.env.example` → `backend\.env` 복사 |
| [5/5] | 다음 단계(API 키 입력 등) 안내 출력 |

> 라이브러리 설치에 수 분 걸립니다. 특히 `sentence-transformers`(Ko-SBERT)가 큽니다.

### 2-3. API 키 입력 (`backend\.env` 편집)

메모장 등으로 `backend\.env` 파일을 열고 아래 값을 채웁니다.

```ini
# 필수 — 빈 값이면 서버가 뜨지 않거나 크롤링이 안 됩니다
SECRET_KEY=                  # 임의의 32바이트 이상 문자열 (아래 생성기 사용)
NAVER_CLIENT_ID=             # 네이버 검색 API 클라이언트 ID
NAVER_CLIENT_SECRET=         # 네이버 검색 API 시크릿

# 선택 — 있으면 GPT 카테고리 분류(CT-02) 활성화, 없으면 크롤러 분류로 폴백
OPENAI_API_KEY=
```

**SECRET_KEY 생성기** (PowerShell 에 그대로 붙여넣기):

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

**네이버 API 키 발급** (무료, 1분): https://developers.naver.com/apps/
→ 애플리케이션 등록 → "검색" API 추가 → Client ID / Secret 복사

### 2-4. Ollama 모델 다운로드 (필수)

별도 PowerShell 창에서:

```powershell
ollama pull llama3      # 약 4.7GB, 최초 1회만 다운로드
ollama serve            # LLM 서버 상주 (이 창은 닫지 말고 켜 둘 것)
```

> `ollama serve` 가 켜져 있어야 AI 요약(CT-01)이 동작합니다.
> 없으면 요약이 비고, 신뢰도/추천은 규칙 기반으로 폴백되어 서비스 자체는 동작합니다.

### 2-5. Docker Desktop 실행 확인

작업표시줄에서 Docker Desktop 아이콘이 켜져 있는지(고래 아이콘) 확인합니다.
PostgreSQL + Redis 컨테이너가 여기서 실행됩니다.

### 2-6. 실행

```powershell
.\run_all.bat
```

`run_all.bat` 이 자동으로:
1. Docker 컨테이너(PostgreSQL + Redis) 기동
2. Ollama 연결 확인
3. 가상환경 + `.env` 검증
4. **백엔드 서버**(FastAPI :8000)를 새 창에서 기동
5. **프론트엔드 서버**(Vite :5173)를 새 창에서 기동

### 2-7. 접속 + 회원가입

브라우저에서 **http://localhost:5173** 접속

1. `/login` 페이지로 자동 이동됨 → **"회원가입"** 클릭
2. 이메일·이름·비밀번호(8자 이상) 입력 + **관심 카테고리 1개 이상 선택**
3. 가입 즉시 자동 로그인되어 피드로 이동
4. 서버 기동 직후 자동 크롤링이 돌아 1~2분 내 실제 뉴스가 채워집니다

> **계정 없이 둘러보기**: 로그인 페이지의 **"계정 없이 둘러보기 (게스트)"** 버튼을 누르면
> 가입 없이 즉시 피드를 체험할 수 있습니다. (게스트는 공용 둘러보기 계정으로,
> 개인화 추천을 받으려면 가입이 필요합니다.)

| 주소 | 용도 |
|------|------|
| http://localhost:5173 | 프론트엔드 (사용자 화면) |
| http://localhost:8000 | 백엔드 API |
| http://localhost:8000/docs | API 문서 (Swagger UI) |

---

## 3. 매번 실행하기

최초 설치(2번)를 마쳤다면, 이후에는 다음만 하면 됩니다.

```powershell
# 1. Docker Desktop 켜기 (작업표시줄 확인)
# 2. Ollama 서버 켜기 (별도 창)
ollama serve
# 3. 통합 실행
.\run_all.bat
```

종료할 때는 열린 두 개의 cmd 창(Backend / Frontend)을 닫으면 됩니다.

---

## 4. 기술 스택

### 백엔드

| 분류 | 기술 | 용도 |
|------|------|------|
| 웹 프레임워크 | FastAPI 0.115 + Uvicorn | 비동기 REST API |
| ORM | SQLAlchemy 2.0 (async) + asyncpg | 비동기 DB 접근 |
| 데이터베이스 | PostgreSQL 16 + **pgvector** | 기사 저장 + 벡터 유사도 검색 |
| 캐시 | Redis 7 | 피드 캐싱(5분 TTL) |
| 스케줄러 | APScheduler | 1시간 주기 크롤링 |
| 인증 | python-jose(JWT) + passlib·bcrypt | 회원/로그인/토큰 |
| 크롤링 | httpx + BeautifulSoup4 + **trafilatura** | 기사 수집·본문 추출 |

### AI / ML

| 모델 | 역할 |
|------|------|
| **Ko-SBERT** (`snunlp/KR-SBERT-V40K-klueNLI-augSTS`) | 한국어 문장 임베딩(768차원). 추천 유사도 계산 |
| **Llama 3** (Ollama 로컬) | CT-01: 기사 본문 3줄 요약 |
| **GPT-4o-mini** (OpenAI, 선택) | CT-02: 카테고리 분류 |
| 규칙 기반 계산기 | 신뢰도 점수(RB-01~04). LLM 비의존, 결정론적 |

### 프론트엔드

| 기술 | 용도 |
|------|------|
| React 18 + Vite 5 | SPA 프레임워크 + 개발 서버 |
| React Router 6 | 클라이언트 라우팅 |
| axios | API 호출 + JWT 인터셉터(자동 토큰 갱신) |

---

## 5. 시스템 아키텍처

```
┌───────────────────────────────────────────────────────────────────┐
│                          사용자 브라우저                            │
│                     React SPA (Vite :5173)                          │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ /api/* (Vite 프록시)
                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                      FastAPI 백엔드 (:8000)                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │  인증/유저   │  │  피드/추천   │  │  APScheduler (1시간 주기)  │ │
│  │  (JWT)       │  │  엔진        │  │  → 크롤링 파이프라인       │ │
│  └─────────────┘  └──────────────┘  └────────────┬───────────────┘ │
└──────────┬────────────────┬──────────────────────┼─────────────────┘
           │                │                       │
           ▼                ▼                       ▼
   ┌──────────────┐  ┌────────────┐    ┌─────────────────────────────┐
   │  PostgreSQL  │  │   Redis    │    │  외부 서비스                │
   │  + pgvector  │  │  (캐시)    │    │  • 네이버 뉴스 검색 API     │
   │  (Docker)    │  │  (Docker)  │    │  • Ollama (Llama3, 로컬)    │
   └──────────────┘  └────────────┘    │  • OpenAI (GPT, 선택)       │
                                        └─────────────────────────────┘
```

### `.bat` → PowerShell shim 구조 (한글 깨짐 방지)

한국어 Windows 의 `cmd.exe` 는 UTF-8 `.bat` 파일의 한글을 cp949 로 잘못 읽어
깨뜨립니다. 이를 근본 차단하기 위해 **`.bat` 는 ASCII 전용 얇은 shim** 으로 두고,
실제 로직과 한국어 출력은 **PowerShell `.ps1`** 가 담당합니다.

```
setup.bat   (ASCII shim) ──▶ scripts\setup.ps1   (UTF-8 BOM, 한글 로직)
run_all.bat (ASCII shim) ──▶ scripts\run_all.ps1 (UTF-8 BOM, 한글 로직)
```

PowerShell 5.1 은 Windows 10+ 에 기본 탑재되어 추가 설치가 필요 없습니다.

---

## 6. 디렉터리 구조

```
capstone_project-chore-docs-and-scripts/
├─ README.md                      이 문서
├─ docker-compose.yml             PostgreSQL+pgvector, Redis 정의
│
├─ setup.bat                      최초 1회 환경 구축 (ASCII shim)
├─ run_all.bat                    통합 실행 (ASCII shim)
├─ backup_db.bat / restore_db.bat DB 백업/복원 (ASCII shim)
├─ start_backend.py               백엔드 단독 실행 래퍼 (venv 검증 포함)
├─ start_frontend.js              프론트엔드 단독 실행 래퍼
│
├─ scripts/                       PowerShell 워커 (실제 로직, UTF-8 BOM)
│  ├─ setup.ps1
│  ├─ run_all.ps1
│  ├─ backup_db.ps1
│  └─ restore_db.ps1
│
├─ backend/
│  ├─ requirements.txt            Python 의존성
│  ├─ config.yaml                 LLM/추천가중치/카테고리 설정 (코드 수정 없이 조정)
│  ├─ .env.example                환경변수 템플릿 (.env 로 복사해 사용)
│  └─ app/
│     ├─ main.py                  FastAPI 엔트리포인트 + lifespan(시작/종료 훅)
│     ├─ models.py                SQLAlchemy 모델 (Article, User, Subscription…)
│     ├─ schemas.py               Pydantic 요청/응답 스키마
│     ├─ api/                     라우터 (HTTP 엔드포인트)
│     │  ├─ auth.py               회원가입/로그인/토큰
│     │  ├─ users.py              프로필/관심사/비밀번호/탈퇴
│     │  ├─ feed.py               개인화 피드 (카테고리 필터 지원)
│     │  ├─ articles.py           기사 상세 조회
│     │  ├─ feedback.py           읽음/관심없음 피드백
│     │  ├─ subscriptions.py      언론사/기자 구독
│     │  └─ admin.py              샘플 시드 / 수동 크롤 트리거
│     ├─ core/                    인프라 (config, DB, Redis, JWT, rate limit)
│     └─ services/                비즈니스 로직
│        ├─ crawler.py            네이버 수집 + 본문 추출(trafilatura)
│        ├─ pipeline.py           크롤링 오케스트레이터 + 스케줄러
│        ├─ llm_processor.py      CT-01 요약 + CT-02 분류
│        ├─ embedding.py          Ko-SBERT 임베딩
│        ├─ credibility.py        신뢰도 규칙 계산기 (RB-01~04)
│        ├─ recommendation.py     추천 엔진 (구독/추천 트랙)
│        └─ resilience.py         서킷브레이커/백프레셔/적응형 수집량
│
└─ frontend/
   ├─ package.json
   ├─ vite.config.js              /api → localhost:8000 프록시 설정
   └─ src/
      ├─ main.jsx                 진입점
      ├─ App.jsx                  라우팅 + 인증 가드
      ├─ api/                     axios 클라이언트 + 엔드포인트 래퍼
      ├─ components/              Feed, Login, Register, Settings, ArticleCard…
      ├─ pages/                   ArticleDetail, Subscriptions…
      └─ contexts/                ThemeContext (다크/라이트)
```

---

## 7. 핵심 동작 원리

### 7-1. 크롤링 파이프라인 (`pipeline.py`)

1시간마다(그리고 서버 시작 직후 1회) 다음 순서로 실행됩니다.

```
[1] 적응형 수집량 결정    CPU 부하에 따라 카테고리당 10~20건 (resilience.py)
        ↓
[2] 부족 우선 배분        DB에 적은 카테고리에 더 많은 예산 배분
        ↓
[3] 8개 카테고리 병렬 수집  네이버 뉴스 검색 API
        ↓
[4] 배치 내 URL 중복 제거  같은 기사가 여러 카테고리에 걸리는 것 방지
        ↓
[5] DB 중복 제거          이미 저장된 URL 제외
        ↓
[6] 기사별 처리 (순차):
      a. 본문 추출        trafilatura(1순위) → BS4(2순위) → 한국어 후처리
      b. CT-01 요약       Llama 3 로 3줄 요약
      c. CT-02 분류       GPT 로 카테고리 재분류 (sticky 카테고리는 크롤러 분류 유지)
      d. 신뢰도 계산      규칙 기반 RB-01~04
      e. 임베딩 생성      Ko-SBERT 768차원
      f. DB upsert
```

**부족 우선 배분**: 카테고리별 기사 수를 조회해, 적은 카테고리에 더 많은 수집
예산을 할당합니다. `weight[c] = (max_count − count[c]) + 1` 공식으로 비례 배분하여
시간이 지날수록 카테고리 분포가 균형을 맞춥니다.

**Sticky 카테고리** (`세계·연예·스포츠·IT·과학·생활·문화`): 네이버 검색 키워드
기반 분류가 정확하므로, GPT 가 본문 근거로 다른 카테고리(주로 정치)로 옮기려 해도
크롤러 분류를 유지합니다. GPT 재분류는 정치/경제/사회 사이에서만 적용됩니다.
→ 특정 카테고리가 비어버리는 현상을 방지.

### 7-2. 본문 추출 (`crawler.py`)

뉴스 사이트마다 HTML 구조가 달라 본문만 정확히 뽑기 어렵습니다.
3단계 방어로 댓글·광고·관련기사·네비게이션 등 잡음을 제거합니다.

```
1순위: trafilatura       콘텐츠 밀도 분석으로 사이트 무관하게 본문만 추출
   ↓ 실패 시
2순위: BeautifulSoup4    네이버 article#dic_area 등 + 86개 잡음 패턴 제거
   ↓
공통: 한국어 후처리       "이전 기사보기", 키워드 해시태그, 저작권 고지,
                          기자 이메일, 관련기사 카루셀 등 23개 패턴 제거
   ↓
품질 검사 (_is_valid_body) 200자 미만/약관/방송대본/헤드라인목록 거부
```

### 7-3. 신뢰도 점수 (`credibility.py`)

LLM 없이 **동일 입력 → 동일 출력**을 보장하는 규칙 기반 계산기. 0~100점.

| 지표 | 가중치 | 평가 내용 |
|------|--------|-----------|
| RB-01 문체 중립성 | 30% | 감정·선정·과장 어휘 빈도 (적을수록 높음) |
| RB-02 정보 밀도 | 25% | 숫자·날짜·단위·고유명사 등 객관 정보량 |
| RB-03 인용구 | 25% | 직접/간접 인용 존재 |
| RB-04 출처 명시 | 20% | 기자 실명 + 언론사 매칭 (3-tier) |

`최종 = RB01×0.30 + RB02×0.25 + RB03×0.25 + RB04×0.20`
프론트엔드에서 90+ 초록 / 70~89 노랑 / 69↓ 빨강 배지로 표시.

> 가중치 배분의 학술적 근거와 선행연구 매핑은 [`docs/CREDIBILITY_RATIONALE.md`](docs/CREDIBILITY_RATIONALE.md) 참고.

### 7-4. 추천 알고리즘 (`recommendation.py`)

피드는 두 트랙으로 구성됩니다.

**구독 트랙** (상단, 최대 10건): 구독한 언론사/기자의 최신 기사.
`최신성 0.5 + 신뢰도 0.5` 로 정렬 (벡터 연산 없음).

**추천 트랙** (하단, 최대 50건): 개인화 점수 정렬.

```
base = (코사인유사도 × 0.40) + (최신성 × 0.20)
     + (구독가중치 × 0.20) + (신뢰도 × 0.20)
final = base − (비관심유사도 × 0.25)
구독 기사면 × 1.3 부스트
```

- **코사인 유사도**: 사용자 `interest_vector` 와 기사 임베딩 간 거리 (pgvector `<=>`)
- **콜드 스타트**: 신규 유저(관심 벡터 미형성)는 벡터 연산을 우회하고
  `신뢰도 + 최신성` 상위 기사를 보여줍니다.
- **관심사 학습**: 읽음/관심없음 피드백 시 관심·비관심 벡터를 EMA 로 갱신.

### 7-5. 카테고리 필터링 (서버사이드)

피드 상단 카테고리 탭을 누르면 **서버가 DB에서 해당 카테고리만 직접 조회**합니다
(`GET /api/feed?category=스포츠`). 정치 기사가 전체의 다수를 차지해도
모든 카테고리 탭이 정상적으로 자기 기사를 보여줍니다. 캐시 키도
`user:{email}:feed:{category}` 로 카테고리별 분리됩니다.

> **왜 이렇게 했나**: 과거에는 추천 상위 50건만 받아 프론트에서 클라이언트
> 필터링을 했는데, 정치 기사가 그 50건을 독점하면 소수 카테고리 탭이 비어 보이는
> 버그가 있었습니다. 서버사이드 필터링으로 근본 해결했습니다.

---

## 8. API 엔드포인트

베이스 경로: `http://localhost:8000`. 전체 문서는 `/docs` (Swagger UI).

### 인증 (`/api/auth`)
| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/register` | 회원가입 (관심 카테고리 포함) | — |
| POST | `/login` | 로그인 (access/refresh 토큰 발급) | — |
| POST | `/guest` | 게스트 로그인 (계정 없이 둘러보기) | — |
| POST | `/refresh` | access 토큰 갱신 | — |
| POST | `/forgot-password` | 비밀번호 재설정 요청 | — |
| POST | `/reset-password` | 비밀번호 재설정 | — |

### 사용자 (`/api/users`)
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/me` | 내 프로필 조회 |
| PATCH | `/me` | 관심 카테고리 등 수정 |
| PATCH | `/me/password` | 비밀번호 변경 |
| DELETE | `/me` | 회원 탈퇴 |

### 피드 · 기사 · 피드백
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/feed?category=` | 개인화 피드 (카테고리 필터 선택) |
| GET | `/api/articles/{url}` | 기사 상세 |
| POST | `/api/articles/{url}/read` | 읽음 처리 |
| POST | `/api/articles/{url}/dislike` | 관심없음 처리 |
| POST | `/api/v1/feed/dislike/undo` | 관심없음 취소 |

### 구독 (`/api/subscriptions`)
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 구독 목록 |
| POST | `/` | 언론사/기자 구독 |
| DELETE | `/{id}` | 구독 해지 |

### 관리자 (`/api/admin`, 개발·데모용)
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/seed` | 샘플 기사 DB 삽입 |
| POST | `/crawl` | 크롤링 수동 트리거 |

---

## 9. 데이터 모델

| 테이블 | PK | 핵심 컬럼 |
|--------|-----|-----------|
| **articles** | `url` | title, body, summary, category, **embedding(768d)**, credibility, rb01~04, press, journalist, published_at |
| **users** | `email` | name, password_hash, interest_categories, **interest_vector(768d)**, **disinterest_vector(768d)** |
| **subscriptions** | `id` | user_email, target_type(press/journalist), target_name |
| **read_logs** | `id` | user_email, article_url (읽음 기록) |
| **dislike_logs** | `id` | user_email, article_url, is_active (관심없음, Undo 가능) |

- `articles.embedding` 에는 pgvector **HNSW 코사인 인덱스**가 걸려 빠른 유사도 검색.
- `articles(category, published_at)` 복합 인덱스로 카테고리별 최신 조회 최적화.
- 기사 카테고리·사용자 관심사 모두 **가운뎃점(·, U+00B7)** 표기로 통일
  (예: `IT·과학`, `생활·문화`). 슬래시 표기와 혼용하면 필터가 깨지므로 주의.

---

## 10. 환경변수 레퍼런스

`backend/.env` 파일에서 관리합니다. (`backend/.env.example` 을 복사해 사용)

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `SECRET_KEY` | ✅ | (없음) | JWT 서명 키. 32바이트 이상 임의 문자열 |
| `NAVER_CLIENT_ID` | ✅ | (없음) | 네이버 검색 API ID |
| `NAVER_CLIENT_SECRET` | ✅ | (없음) | 네이버 검색 API 시크릿 |
| `OPENAI_API_KEY` | 선택 | (없음) | 있으면 CT-02 GPT 분류 활성화 |
| `DATABASE_URL` | — | `...localhost:5432/news_curator` | docker-compose 기본값과 일치 |
| `REDIS_URL` | — | `redis://localhost:6379/0` | 캐시 |
| `LLM_PRIMARY_MODEL` | — | `llama3` | CT-01 요약 모델 |
| `LLM_PRIMARY_BASE_URL` | — | `http://localhost:11434/v1` | Ollama 엔드포인트 |
| `EMBEDDING_MODEL_NAME` | — | `snunlp/KR-SBERT-V40K-klueNLI-augSTS` | Ko-SBERT |
| `CRAWL_INTERVAL_HOURS` | — | `1` | 크롤링 주기 |
| `CRAWL_ON_STARTUP` | — | `True` | 서버 시작 시 즉시 1회 크롤 |
| `AUTO_SEED_ON_EMPTY_DB` | — | `True` | DB 비었으면 샘플 기사 자동 시드 |
| `RATE_LIMIT` | — | `60/minute` | 분당 요청 제한 |
| `FEED_CACHE_TTL` | — | `300` | 피드 캐시 TTL(초) |

> 추천 가중치·LLM 모델·카테고리 목록 등은 `backend/config.yaml` 에서
> 코드 수정 없이 조정할 수 있습니다.

---

## 11. 운영 · 데이터 백업/이전

다른 컴퓨터에서 시연하거나 데이터를 옮길 때 사용합니다.

### 백업 (현재 PC)

```powershell
.\backup_db.bat
```

`backups\news_curator_<날짜>.dump` 파일이 생성됩니다. pgvector 임베딩까지 전부 포함됩니다.
USB 로 옮길 때는 이 `.dump` 파일과 `backend\.env`(API 키·SECRET_KEY) 를 함께 복사하세요.

### 복원 (다른 PC)

대상 PC에서 `setup.bat` → `run_all.bat`(컨테이너 기동)까지 마친 뒤:

```powershell
# backups\ 폴더에 .dump 파일을 둔 상태에서
.\restore_db.bat                          # 최신 백업 자동 선택
.\restore_db.bat C:\경로\foo.dump          # 특정 파일 지정
```

> `backend\.env` 의 `SECRET_KEY` 가 두 PC에서 같아야 기존 사용자 JWT 토큰이
> 그대로 유효합니다. 다르면 사용자가 재로그인하면 됩니다.

---

## 12. 트러블슈팅

### `.bat` 실행 시 한글이 깨지고 "내부 또는 외부 명령이 아닙니다" 오류
한국어 Windows 의 cmd.exe + UTF-8 `.bat` 충돌 문제입니다. **이미 해결되어 있습니다**
(`.bat` 은 ASCII shim, 로직은 `scripts\*.ps1`). 만약 그래도 발생하면
`scripts\*.ps1` 파일이 **UTF-8 BOM** 으로 저장됐는지 확인하세요.

```powershell
[System.IO.File]::ReadAllBytes('scripts\run_all.ps1')[0..2] -join ' '
# 출력이 239 187 191 (EF BB BF) 여야 정상
```

### `cannot be loaded because running scripts is disabled` (PowerShell 정책)
학교/회사 PC의 그룹 정책이 스크립트를 막는 경우입니다. 직접 호출하세요.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1
```

### 백엔드가 `Fatal Python error: invalid PYTHONUTF8` 로 죽음
이미 해결됨. 자식 cmd 창에 `set PYTHONUTF8=1` 을 인라인으로 넣으면 cmd 가
값 끝에 공백을 붙여 발생하던 버그였습니다. 환경변수는 PowerShell 부모에서 상속됩니다.

### 크롤링이 `NAVER_CLIENT_ID/SECRET 미설정` 으로 안 됨
`backend\.env` 에 네이버 키를 채웠는지 확인하세요. 채웠는데도 안 되면
백엔드를 재시작하세요. (config 가 `.env` 절대경로를 읽도록 되어 있어
실행 위치와 무관하게 로드됩니다.)

### 특정 카테고리 탭이 비어 보임
정상입니다. 갓 크롤링된 카테고리는 기사가 적을 수 있습니다.
1~2 크롤링 사이클(시간당 1회) 후 부족 우선 배분으로 채워집니다.
즉시 채우려면 백엔드를 재시작하면 startup 크롤이 한 번 더 돕니다.

### 피드가 401 Unauthorized
로그인이 안 됐거나 토큰이 만료된 상태입니다. 브라우저 `F12` → Application →
Local Storage 에서 토큰 삭제 후 새로고침 → 로그인 페이지에서 다시 로그인하세요.

### `(trapped) error reading bcrypt version` 경고
무해한 경고입니다. 제거하려면 `bcrypt==3.2.2` 가 설치돼 있는지 확인하세요
(`requirements.txt` 에 고정됨).

---

## 13. 자주 묻는 질문 (FAQ)

**Q. OpenAI 키 없이도 동작하나요?**
네. `OPENAI_API_KEY` 가 비어 있으면 CT-02(GPT 분류)를 건너뛰고 크롤러 키워드
기반 카테고리로 폴백합니다. 요약(Llama)·신뢰도·추천은 정상 동작합니다.

**Q. Ollama 없이 동작하나요?**
서비스는 뜨지만 AI 요약(CT-01)이 비게 됩니다. 신뢰도·추천은 규칙 기반이라
영향받지 않습니다. 시연 품질을 위해 `ollama serve` 를 권장합니다.

**Q. 다른 사람이 내 컴퓨터에 접속하려면?**
같은 WiFi 라면 `http://<내-IP>:5173` 으로 접속 가능합니다(`run_all` 이 `--host`
로 띄움). 외부 공개·24시간 운영이 필요하면 클라우드 배포가 필요합니다.

**Q. macOS / Linux 에서 실행되나요?**
백엔드/프론트엔드 코드 자체는 OS 무관입니다. 다만 `.bat`/`.ps1` 런처는 Windows
전용이라, 다른 OS 에서는 `docker-compose up -d` 후 `uvicorn`/`npm run dev` 를
수동 실행해야 합니다.

**Q. 데이터를 초기화하려면?**
`docker-compose down -v` 로 볼륨까지 삭제하면 DB 가 비워집니다. 다음 실행 시
샘플 시드 + 크롤링으로 다시 채워집니다.

---

<div align="center">

**News Curator** · 졸업과제 프로젝트
FastAPI · React · PostgreSQL+pgvector · Ko-SBERT · Llama 3

</div>
