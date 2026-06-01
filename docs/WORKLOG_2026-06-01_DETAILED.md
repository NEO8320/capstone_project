# News Curator — 2026-06-01 상세 기술 작업보고서 (코드 diff 포함)

> 조원 공유·PPT 제작·기술 리뷰용. 오늘 진행한 모든 작업을
> **문제 → 원인 → 해결 → 코드 diff → 결과 → 관련 파일** 구조로 정리했다.
> 코드 diff는 실제 커밋(`git show`)에서 발췌했으며, 방대한 CSS 등 일부는 핵심만 발췌하고
> 전체는 커밋 해시로 참조한다.
> 브랜치: `chore/docs-and-scripts` · 커밋: 3b4062d, 4851dea, 95c0515, 0f61cf5, 4bb2048, 6e61964

---

## 0. 개요

| # | 분류 | 작업 | 핵심 파일 | 커밋 |
|---|------|------|-----------|------|
| 1 | 인프라 | Windows 한글 깨짐 근본 해결(PowerShell shim) | `*.bat`, `scripts/*.ps1` | 3b4062d |
| 2 | 버그 | `.env` 로드 실패(NAVER 키 미인식) | `config.py` | 3b4062d |
| 3 | 개선 | 부족 우선 크롤링 배분 | `pipeline.py` | 3b4062d |
| 4 | 버그 | 카테고리 오분류(정치→생활·문화) | `pipeline.py` | 4851dea |
| 5 | 기능 | 게스트 모드 | `auth.py`, `Login.jsx` | 4851dea |
| 6 | 확인 | 라이트테마/계정관리 이미 구현 | `ThemeContext.jsx`, `Settings.jsx` | 4851dea |
| 7 | 개선 | 반응형/모바일 | `index.css`, `Feed.css` | 4851dea |
| 8 | 버그 | AI 요약 깨짐(`\n`·영어 머리말) | `llm_processor.py` | 95c0515 |
| 9 | 버그 | 기자명 추출+구독 버튼 | `pipeline.py`, `ArticleDetail.jsx` | 95c0515 |
| 10 | 기능 | 페이지네이션+읽음 숨김 | `recommendation.py`, `Feed.jsx`, `Pagination.jsx` | 0f61cf5 |
| 11 | 운영 | DB 백업/복원 스크립트 | `backup_db.*`, `restore_db.*` | 3b4062d |
| 12 | 문서 | README 전면 재작성 | `README.md` | 3b4062d |
| 13 | 문서 | 신뢰도 가중치 학술 근거 | `CREDIBILITY_RATIONALE.md` | 4bb2048, 6e61964 |
| 14 | 문서 | 크롤링 1시간 주기 근거 | `CRAWL_INTERVAL_RATIONALE.md` | 4bb2048 |
| 15 | 데이터 | 깨진 요약 334건 정리+재크롤 | (DB 작업) | — |

---

## 1. Windows 한글 깨짐 근본 해결 (PowerShell shim 아키텍처)

**문제**: 한국어 Windows에서 `.bat` 실행 시 한글 깨짐 + `'enAI'은(는) 내부 또는 외부 명령…`
오류. 수동 `$env:PYTHONIOENCODING="utf-8"` 없이는 백엔드 기동 실패.

**원인**: cmd.exe가 `.bat`를 cp949로 미리 버퍼링한 뒤 파싱 → `chcp 65001`이 적용되기 전에
한글 UTF-8 바이트가 깨진 명령으로 해석됨. 순수 `.bat`로는 회피 불가.

**해결**: `.bat`는 ASCII 전용 shim으로 축소, 로직·한글은 PowerShell `.ps1`(UTF-8 BOM)로 분리.

```bat
@echo off
REM  run_all.bat — ASCII-only shim. 실제 로직은 scripts\run_all.ps1
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\run_all.ps1"
set "PS_EXIT=%ERRORLEVEL%"
echo.
pause
endlocal & exit /b %PS_EXIT%
```

```powershell
# scripts/run_all.ps1 (UTF-8 BOM) — 콘솔 UTF-8 강제
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8       = '1'
try { chcp 65001 > $null } catch {}
# ... (Docker/Ollama/venv 검증 후 백엔드·프론트 새 창 기동)
```

**추가 버그**: 자식 cmd 창에 `set PYTHONUTF8=1`을 인라인으로 넣으면 값 끝에 공백이 붙어
`Fatal Python error: invalid PYTHONUTF8` 로 죽음 → 인라인 set 제거, 환경변수는 PowerShell
부모에서 상속.

**결과**: 수동 환경변수 없이 더블클릭/실행 모두 한글 정상.
**관련 파일**: `setup.bat`, `run_all.bat`, `scripts/setup.ps1`, `scripts/run_all.ps1`, `start_backend.py`, `backend/app/main.py`

---

## 2. 백엔드 `.env` 로드 실패 (NAVER 키 미인식)

**문제**: `backend/.env`에 NAVER 키를 넣어도 "NAVER_CLIENT_ID/SECRET 미설정"으로 크롤링 거부.

**원인**: pydantic-settings가 `.env`를 cwd 상대경로로 찾는데 `start_backend.py`가 cwd를
프로젝트 루트로 변경 → `backend/.env`를 못 찾고 전 설정이 기본값(빈 문자열)으로 폴백.

**해결 (diff)**:
```diff
+from pathlib import Path
+
+# pydantic-settings 는 env_file 을 cwd 기준 상대경로로 해석하기 때문에,
+# start_backend.py 가 cwd 를 프로젝트 루트로 chdir 하면 backend/.env 를 못 찾는다.
+# 이 모듈 자신의 위치 기준으로 절대경로를 계산하여 cwd 와 무관하게 로드한다.
+_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

 class Settings(BaseSettings):
     model_config = SettingsConfigDict(
-        env_file=".env",
+        env_file=str(_ENV_FILE),
         env_file_encoding="utf-8",
         case_sensitive=False,
     )
```

**결과**: NAVER 키·SECRET_KEY 정상 로드, 크롤링 작동.
**관련 파일**: `backend/app/core/config.py`

---

## 3. 부족 우선 크롤링 배분

**문제**: 카테고리별 기사 수 불균형(정치 편중).

**해결**: DB에 적은 카테고리에 수집 예산을 더 배분.
```python
def _allocate_crawl_budget(categories, current_counts, base_per_category,
                           min_per_category=5, max_per_category=100):
    counts = {c: current_counts.get(c, 0) for c in categories}
    max_count = max(counts.values()) if counts else 0
    # 가중치: 부족분(max - count) + 1 평탄화로 모든 카테고리에 양수 보장
    weights = {c: (max_count - counts[c]) + 1 for c in categories}
    total_weight = sum(weights.values()) or 1
    total_budget = base_per_category * len(categories)
    allocation = {}
    for c in categories:
        raw = int(round(total_budget * weights[c] / total_weight))
        allocation[c] = max(min_per_category, min(max_per_category, raw))
    return allocation
```
**부가 버그**: `func.count(Article.id)` → PK가 `url`이라 오류 → `func.count()`로 수정.
**결과**: 시간이 지날수록 카테고리 분포 자동 균형.
**관련 파일**: `backend/app/services/pipeline.py`

---

## 4. 카테고리 오분류 (정치 기사가 생활·문화에 섞임)

**문제**: 정치 기사가 '생활·문화' 탭에 박힘.
**원인**: IT·과학·생활·문화를 sticky(크롤러 분류 우선)에 넣었는데 키워드("문화","IT")가
넓어 타 카테고리 기사가 딸려옴 + GPT 정확분류를 sticky가 무시.

**해결 (diff)**:
```diff
 STICKY_CRAWLER_CATEGORIES = frozenset(
-    {"세계", "연예", "스포츠", "IT·과학", "생활·문화"}
+    {"세계", "연예", "스포츠"}
 )
```
**결과**: 정치는 정치 탭, 생활 기사만 생활 탭. (빈 탭 문제는 서버사이드 필터링으로 이미 해결)
**관련 파일**: `backend/app/services/pipeline.py`

---

## 5. 게스트 모드 ("계정 없이 둘러보기")

**요구**: 회원가입 없이 체험.
**구현 (백엔드)**:
```python
GUEST_EMAIL = "guest@newscurator.demo"
GUEST_CATEGORIES = ["정치", "경제", "IT·과학"]

@router.post("/guest", response_model=TokenResponse, summary="게스트 로그인")
async def guest_login(db: AsyncSession = Depends(get_db)):
    user = await db.get(User, GUEST_EMAIL)
    if not user:
        # 콜드스타트 벡터(실패 시 랜덤 정규화 폴백)
        try:
            interest_vector = await asyncio.wait_for(
                compute_cold_start_vector(GUEST_CATEGORIES), timeout=60.0)
        except (asyncio.TimeoutError, Exception):
            v = np.random.default_rng().standard_normal(settings.EMBEDDING_DIM)
            interest_vector = (v / np.linalg.norm(v)).tolist()
        user = User(email=GUEST_EMAIL, hashed_password=_hash_password(secrets.token_hex(16)),
                    name="게스트", interest_categories=GUEST_CATEGORIES,
                    interest_vector=interest_vector, disinterest_vector=get_zero_vector())
        db.add(user)
        try: await db.commit()
        except IntegrityError:  # 동시요청 멱등 처리
            await db.rollback(); user = await db.get(User, GUEST_EMAIL)
    # 일반 로그인과 동일 토큰 발급
    return TokenResponse(access_token=..., refresh_token=...)
```
**구현 (프론트)**:
```jsx
const handleGuest = async () => {
  const { data } = await axios.post('/api/auth/guest');
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  navigate('/feed');
};
// 로그인 폼 아래: <button onClick={handleGuest}>계정 없이 둘러보기 (게스트)</button>
```
**결과**: 가입 없이 즉시 피드 체험(멱등 — 계정 1개만).
**관련 파일**: `backend/app/api/auth.py`, `frontend/src/components/Login.jsx`, `Register.css`

---

## 6. 라이트 테마 / 계정 관리 — 이미 구현됨 확인

**피드백**: "화이트 테마?", "비밀번호 변경 등 계정 관리?"
**확인**: 둘 다 이미 구현됨.
- 라이트 테마: `ThemeContext`(다크↔라이트) + `index.css`의 `[data-theme="light"]` 변수 +
  헤더 `ThemeToggle`.
- 계정 관리: `Settings.jsx`에 비밀번호 변경(`PATCH /users/me/password`)·탈퇴(`DELETE /users/me`).

**결과**: 추가 작업 없이 "구현 완료"로 정리(발표 답변 강화).

---

## 7. 반응형/모바일 대응 보강 (교수님 요청)

**보강 (diff 발췌)**:
```css
@media (max-width: 767px) {
  .header { flex-direction: column; align-items: stretch; text-align: center; }
  .header__nav { flex-wrap: wrap; justify-content: center; }
}
@media (max-width: 480px) {
  .nav-btn { padding: 6px 10px; font-size: 0.85rem; }
}
/* 구독 트랙 카드 모바일 폭: 다음 카드가 살짝 보여 스와이프 유도 */
@media (max-width: 480px) { .card-scroll > * { flex: 0 0 85vw; } }
```
**결과**: 폰(375px)·태블릿(768px)에서 레이아웃 유지.
**관련 파일**: `frontend/src/index.css`, `Feed.css`

---

## 8. AI 요약 깨짐 수정 (`\n` 글자·영어 머리말)

**문제**: 요약에 `\n`이 글자로 보이고 "Here is a 3-line summary:" 영어 머리말 섞임.
**원인**: 프롬프트의 "줄바꿈(`\n`)으로 구분" 지시 + 후처리 미흡.

**해결 — 프롬프트 수정 + `_clean_summary()` 신설**:
```python
# 프롬프트: "줄바꿈(\n)으로 구분" 제거 →
# "각 문장을 한 줄씩, 실제 줄바꿈으로 나눠 총 3줄로. 영어 안내문·머리말 절대 금지."

_SUMMARY_PREFIX_PATTERNS = [
    re.compile(r"^\s*here\s+(is|are)\b.*?:\s*", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*(the\s+)?(3[\s-]?line\s+)?summary\b[^\n]*?:\s*", re.IGNORECASE),
    re.compile(r"^\s*#*\s*(3줄\s*)?요약\s*[:：\-–—]?\s*"),
    re.compile(r"^\s*(다음은|아래는)\b[^\n]*?요약(문)?\s*(입니다|이에요|예요)?\s*[.:：]?\s*"),
    # ...
]

def _clean_summary(text):
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n")   # 리터럴 \n → 실제 줄바꿈
    for _ in range(3):                                          # 머리말 반복 제거
        for pat in _SUMMARY_PREFIX_PATTERNS: text = pat.sub("", text, count=1)
        text = text.strip()
    # 줄별 마크다운/번호/불릿 제거 ...
    result = "\n".join(cleaned_lines).strip()
    if not re.search(r"[가-힣]", result): return None  # 완전 영어 응답 → description 폴백
    return result
```
**검증**: 실제 깨진 요약 입력 → 한국어 3줄만 남고 영어/리터럴 제거 확인.
**관련 파일**: `backend/app/services/llm_processor.py`

---

## 9. 기자명 추출 개선 + 기자 구독 버튼 항상 표시

**문제**: 외부 언론사 기사에서 기자 구독 버튼이 아예 안 보임.
**원인**: 추출이 "본문 끝 200자 + `홍길동 기자`"만 봐서 외부 언론사에서 자주 실패 + 프론트가
기자명 없으면 버튼을 숨김.

**해결 (백엔드, 다단계 추출)**:
```python
def _extract_journalist(body, extra=None):
    forward = re.compile(r"([가-힣]{2,4})\s*(?:기자|특파원|통신원|논설위원)"
                         r"(?!회견|단|실|협회|상|회|증|클럽|단실)(?=\s|$|[.,·\)\]】」』])")
    backward = re.compile(r"기자(?!회견|단|실|협회|상|회|증|클럽)\s+([가-힣]{2,4})")
    # 1) 본문 끝 → 2) 이메일 근접 → 3) 본문 앞 → 4) 역순 어순 → 5) description 보조
    # ('기자회견·기자단' 등은 negative lookahead로 오매칭 차단)
```
**해결 (프론트, 버튼 항상 표시)**:
```jsx
{article.journalist ? (
  <button className="btn-subscribe" onClick={handleJournalistSubscribe}>
    {article.journalist} 기자 구독
  </button>
) : (
  <button className="btn-subscribe btn-subscribe--disabled" disabled
          title="이 기사는 기자 정보가 확인되지 않아 구독할 수 없습니다.">
    기자 정보 없음
  </button>
)}
```
**검증**: 추출 단위테스트 8/8 통과(정방향/이메일/역순/앞부분/description + 오매칭 차단).
**관련 파일**: `backend/app/services/pipeline.py`, `frontend/src/pages/ArticleDetail.jsx`, `ArticleDetail.css`

---

## 10. 메인 피드 페이지네이션 + 읽은 기사 숨김 토글

**요구**: 기사 전부 노출(`1 2 3 … N` 탭) + 읽은 기사 제외.

**백엔드 (반환 상한 ↑)**:
```diff
-MAX_RECOMMENDATION_TRACK = 50      # 추천 트랙 최대 반환 건수
-COLD_START_LIMIT = 20              # 콜드 스타트 시 반환 건수
+MAX_RECOMMENDATION_TRACK = 300     # 추천 트랙 최대 반환 건수
+COLD_START_LIMIT = 300             # 콜드 스타트 시 반환 건수 (게스트/신규도 페이지네이션)
```

**프론트 (Feed.jsx 파이프라인)**:
```jsx
const PAGE_SIZE = 15;
// 읽은 기사 숨김
const filteredRecommendation = hideRead
  ? categoryFiltered.filter((item) => !item?.is_read)
  : categoryFiltered;
const sortedRecommendation = applySortToItems(filteredRecommendation, activeSort);
// 페이지 슬라이스
const totalPages = Math.max(1, Math.ceil(sortedRecommendation.length / PAGE_SIZE));
const safePage = Math.min(currentPage, totalPages);
const pagedRecommendation = sortedRecommendation.slice(
  (safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
// 카테고리/정렬/hideRead 변경 시 1페이지 리셋
useEffect(() => { setCurrentPage(1); }, [activeCategory, activeSort, hideRead]);
```

**Pagination.jsx (압축 페이저 — `1 … 4 5 [6] 7 8 … 22`)**:
```jsx
function buildPages(current, total) {
  if (total <= 7) return Array.from({length: total}, (_, i) => i + 1);
  const pages = [], left = Math.max(2, current-2), right = Math.min(total-1, current+2);
  pages.push(1);
  if (left > 2) pages.push('…');
  for (let p = left; p <= right; p++) pages.push(p);
  if (right < total-1) pages.push('…');
  pages.push(total);
  return pages;
}
```
**결과**: 모든 기사 페이지 탐색 + 읽은 기사 토글 제외. 모바일/테마 대응.
**관련 파일**: `recommendation.py`, `Feed.jsx`, `Pagination.jsx`, `Pagination.css`, `Feed.css`

---

## 11. DB 백업/복원 스크립트 (USB 이전용)

`pg_dump`로 pgvector 임베딩까지 단일 `.dump` 백업, 다른 PC에서 복원.
**관련 파일**: `backup_db.bat`, `restore_db.bat`, `scripts/backup_db.ps1`, `scripts/restore_db.ps1`

---

## 12. README 전면 재작성

작동법·기술스택·아키텍처·동작원리·API·데이터모델·환경변수·운영·트러블슈팅·FAQ를 새로 정리.
게스트 모드·페이지네이션·근거 문서 링크 반영. **관련 파일**: `README.md`

---

## 13. 신뢰도 가중치 학술 근거 (`CREDIBILITY_RATIONALE.md`)

논문 3편(최미연 2023 / 언론과학연구 2023 / 김미경 2019)을 직접 읽고(스캔본 OCR) 인용 정리.
**핵심**: 논문은 **가중치 서열**(문체>정보밀도≈인용>출처)은 뒷받침하나 **정확한 % 숫자**는
도출 못 함 → "서열은 근거 있음 / 정밀값은 라벨 데이터 튜닝 영역"으로 정직하게 명시.

| 지표 | 비율 | 근거 |
|------|------|------|
| RB-01 문체 중립성 | 30% | "자극적 뉴스 기피"(②) + Meyer/Gaziano "불편향이 최대 요인" |
| RB-02 정보 밀도 | 25% | "정확성=전통 가치"(①), "정확성 주목"(③) |
| RB-03 인용구 | 25% | "전문성·검증가능성"(①) |
| RB-04 출처 명시 | 20% | "신뢰할 출처로 전환"(②) — 보조 지표 |

---

## 14. 크롤링 1시간 주기 근거 (`CRAWL_INTERVAL_RATIONALE.md`)

6가지 근거: ① API 한도 여유(일 25,000 중 1% 미만) ② 신선도 체감 차이 작음 ③ LLM 처리비용
④ Redis 5분 캐시 조화 ⑤ 정보 과부하 완화 ⑥ 업계 관행. **메시지**: "더 자주 못 해서가 아니라
할 필요가 없어서" 1시간, 설정으로 조정 가능.

---

## 15. 데이터 정비

- 깨진 요약 334건(전체 350건의 95%) → `articles` TRUNCATE(사용자·구독 유지) 후 재크롤.
- 자동 시드 off + 코드의 임의 샘플 기사 11건 제거 → 실제 크롤링 기사만 노출.

---

## 부록: 오늘 커밋 목록

| 커밋 | 시각 | 내용 |
|------|------|------|
| `3b4062d` | (연속) | 인코딩 해결 + 크롤러 개선 + README 재작성 + 백업 스크립트 |
| `4851dea` | 15:00 | 게스트 모드 + 반응형 + 신뢰도 근거 초안 + sticky 수정 |
| `95c0515` | 15:18 | 요약 깨짐 + 기자 구독 버튼 |
| `0f61cf5` | 15:32 | 페이지네이션 + 읽은 기사 숨김 |
| `4bb2048` | 15:52 | 신뢰도 학술 근거 + 크롤링 주기 근거 |
| `6e61964` | 16:01 | 신뢰도 가중치 '비율의 근거와 한계' |
