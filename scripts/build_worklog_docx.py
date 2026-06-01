# -*- coding: utf-8 -*-
"""
2026-06-01 작업보고서 Word(.docx) 생성기.
docs/WORKLOG_2026-06-01_DETAILED.md 의 내용을 구조화된 Word 문서로 출력한다.
한글 폰트(맑은 고딕), 코드블록(Consolas + 회색 음영), 표지/목차/표 포함.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

KO_FONT = "맑은 고딕"
CODE_FONT = "Consolas"


def set_korean_font(run, font=KO_FONT, size=None, bold=None, color=None):
    run.font.name = font
    r = run._element
    rpr = r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def shade_paragraph(p, fill="F2F2F2"):
    """단락 배경 음영 (코드블록용)."""
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr.append(shd)


def add_body(doc, text, size=10.5, bold=False, color=None, align=None, space_after=6):
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    set_korean_font(run, size=size, bold=bold, color=color)
    return p


def add_heading_ko(doc, text, level=1):
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    sizes = {0: 22, 1: 16, 2: 13, 3: 11.5}
    set_korean_font(run, size=sizes.get(level, 11), bold=True,
                    color=RGBColor(0x1F, 0x38, 0x64))
    return h


def add_code_block(doc, code, lang=""):
    """코드블록: 회색 음영 + Consolas, 줄 단위 단락."""
    lines = code.rstrip("\n").split("\n")
    for i, line in enumerate(lines):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.left_indent = Inches(0.1)
        shade_paragraph(p, "F4F4F4")
        run = p.add_run(line if line else " ")
        run.font.name = CODE_FONT
        run.font.size = Pt(9)
        r = run._element
        rpr = r.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts"); rpr.append(rfonts)
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rfonts.set(qn(attr), CODE_FONT)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_overview_table(doc, rows, headers):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, htext in enumerate(headers):
        hdr[i].text = ""
        run = hdr[i].paragraphs[0].add_run(htext)
        set_korean_font(run, size=9.5, bold=True)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(val))
            set_korean_font(run, size=9)
    return table


# ============================================================
doc = Document()

# 기본 스타일 한글 폰트
style = doc.styles["Normal"]
style.font.name = KO_FONT
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), KO_FONT)

# ── 표지 ──
for _ in range(6):
    doc.add_paragraph()
add_body(doc, "News Curator", size=30, bold=True,
         color=RGBColor(0x1F, 0x38, 0x64), align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
add_body(doc, "2026-06-01 작업보고서 (상세 기술 버전)", size=16, bold=True,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=24)
add_body(doc, "AI 기반 개인화 뉴스 큐레이팅 서비스", size=12,
         align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x55,0x55,0x55), space_after=2)
add_body(doc, "신규 기능 2 · 버그 수정 5 · 피드백 반영 3 · 문서화 4", size=11,
         align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x55,0x55,0x55), space_after=2)
add_body(doc, "GitHub 브랜치: chore/docs-and-scripts", size=10,
         align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x88,0x88,0x88))
doc.add_page_break()

# ── 0. 개요 표 ──
add_heading_ko(doc, "0. 작업 개요", level=1)
add_body(doc, "오늘 진행한 전체 작업을 분류·핵심 파일·커밋과 함께 정리한다.", size=10.5)
overview = [
    ["1","인프라","Windows 한글 깨짐 근본 해결(PowerShell shim)","*.bat, scripts/*.ps1","3b4062d"],
    ["2","버그",".env 로드 실패(NAVER 키 미인식)","config.py","3b4062d"],
    ["3","개선","부족 우선 크롤링 배분","pipeline.py","3b4062d"],
    ["4","버그","카테고리 오분류(정치→생활·문화)","pipeline.py","4851dea"],
    ["5","기능","게스트 모드","auth.py, Login.jsx","4851dea"],
    ["6","확인","라이트테마/계정관리 이미 구현","ThemeContext, Settings","4851dea"],
    ["7","개선","반응형/모바일","index.css, Feed.css","4851dea"],
    ["8","버그","AI 요약 깨짐(\\n·영어 머리말)","llm_processor.py","95c0515"],
    ["9","버그","기자명 추출+구독 버튼","pipeline.py, ArticleDetail.jsx","95c0515"],
    ["10","기능","페이지네이션+읽음 숨김","recommendation.py, Feed.jsx, Pagination.jsx","0f61cf5"],
    ["11","운영","DB 백업/복원 스크립트","backup_db.*, restore_db.*","3b4062d"],
    ["12","문서","README 전면 재작성","README.md","3b4062d"],
    ["13","문서","신뢰도 가중치 학술 근거","CREDIBILITY_RATIONALE.md","4bb2048/6e61964"],
    ["14","문서","크롤링 1시간 주기 근거","CRAWL_INTERVAL_RATIONALE.md","4bb2048"],
    ["15","데이터","깨진 요약 334건 정리+재크롤","(DB 작업)","-"],
]
add_overview_table(doc, overview, ["#","분류","작업","핵심 파일","커밋"])
doc.add_page_break()

# ── 본문 항목들 ──
# (제목, [("body", 텍스트) | ("code", 코드) | ("sub", 소제목)] )
sections = [
    ("1. Windows 한글 깨짐 근본 해결 (PowerShell shim 아키텍처)", [
        ("b","[문제] 한국어 Windows에서 .bat 실행 시 한글 깨짐 + '내부 또는 외부 명령' 오류. "
             "수동 $env:PYTHONIOENCODING 없이는 백엔드 기동 실패."),
        ("b","[원인] cmd.exe가 .bat를 cp949로 미리 버퍼링한 뒤 파싱 → chcp 65001 적용 전에 "
             "한글 UTF-8 바이트가 깨진 명령으로 해석됨. 순수 .bat로는 회피 불가."),
        ("b","[해결] .bat는 ASCII 전용 shim으로 축소, 로직·한글은 PowerShell .ps1(UTF-8 BOM)로 분리."),
        ("code","@echo off\nREM run_all.bat — ASCII-only shim\nsetlocal\nset \"SCRIPT_DIR=%~dp0\"\n"
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%SCRIPT_DIR%scripts\\run_all.ps1\"\n"
                "set \"PS_EXIT=%ERRORLEVEL%\"\necho.\npause\nendlocal & exit /b %PS_EXIT%"),
        ("code","# scripts/run_all.ps1 (UTF-8 BOM)\n"
                "try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}\n"
                "$env:PYTHONIOENCODING = 'utf-8'\n$env:PYTHONUTF8 = '1'\ntry { chcp 65001 > $null } catch {}"),
        ("b","[추가 버그] 자식 cmd 창에 'set PYTHONUTF8=1' 인라인 시 값 끝 공백으로 "
             "Fatal Python error 발생 → 인라인 set 제거(환경변수는 PowerShell 부모 상속)."),
        ("b","[결과] 수동 환경변수 없이 더블클릭/실행 모두 한글 정상."),
        ("b","[파일] setup.bat, run_all.bat, scripts/setup.ps1, scripts/run_all.ps1, start_backend.py, main.py"),
    ]),
    ("2. 백엔드 .env 로드 실패 (NAVER 키 미인식)", [
        ("b","[문제] backend/.env에 NAVER 키를 넣어도 '미설정'으로 크롤링 거부."),
        ("b","[원인] pydantic-settings가 .env를 cwd 상대경로로 찾는데 start_backend.py가 cwd를 "
             "프로젝트 루트로 변경 → backend/.env 못 찾고 전 설정이 기본값 폴백."),
        ("b","[해결 diff]"),
        ("code","+from pathlib import Path\n"
                "+_ENV_FILE = Path(__file__).resolve().parent.parent.parent / \".env\"\n\n"
                " class Settings(BaseSettings):\n     model_config = SettingsConfigDict(\n"
                "-        env_file=\".env\",\n+        env_file=str(_ENV_FILE),\n"
                "         env_file_encoding=\"utf-8\", case_sensitive=False,\n     )"),
        ("b","[결과] NAVER 키·SECRET_KEY 정상 로드, 크롤링 작동. [파일] backend/app/core/config.py"),
    ]),
    ("3. 부족 우선 크롤링 배분", [
        ("b","[문제] 카테고리별 기사 수 불균형(정치 편중)."),
        ("b","[해결] DB에 적은 카테고리에 수집 예산 더 배분."),
        ("code","def _allocate_crawl_budget(categories, current_counts, base_per_category,\n"
                "                           min_per_category=5, max_per_category=100):\n"
                "    counts = {c: current_counts.get(c, 0) for c in categories}\n"
                "    max_count = max(counts.values()) if counts else 0\n"
                "    weights = {c: (max_count - counts[c]) + 1 for c in categories}\n"
                "    total_weight = sum(weights.values()) or 1\n"
                "    total_budget = base_per_category * len(categories)\n"
                "    return {c: max(min_per_category,\n"
                "                   min(max_per_category,\n"
                "                       int(round(total_budget*weights[c]/total_weight))))\n"
                "            for c in categories}"),
        ("b","[부가 버그] func.count(Article.id) → PK가 url이라 오류 → func.count()로 수정."),
        ("b","[결과] 시간이 지날수록 카테고리 분포 자동 균형. [파일] pipeline.py"),
    ]),
    ("4. 카테고리 오분류 (정치 기사가 생활·문화에 섞임)", [
        ("b","[문제] 정치 기사가 '생활·문화' 탭에 박힘."),
        ("b","[원인] IT·과학·생활·문화를 sticky(크롤러 분류 우선)에 넣었는데 키워드('문화','IT')가 "
             "넓어 타 카테고리 기사가 딸려옴 + GPT 정확분류를 sticky가 무시."),
        ("b","[해결 diff]"),
        ("code"," STICKY_CRAWLER_CATEGORIES = frozenset(\n"
                "-    {\"세계\", \"연예\", \"스포츠\", \"IT·과학\", \"생활·문화\"}\n"
                "+    {\"세계\", \"연예\", \"스포츠\"}\n )"),
        ("b","[결과] 정치는 정치 탭, 생활 기사만 생활 탭. (빈 탭은 서버사이드 필터링으로 이미 해결) "
             "[파일] pipeline.py"),
    ]),
    ("5. 게스트 모드 (계정 없이 둘러보기)", [
        ("b","[요구] 회원가입 없이 체험."),
        ("b","[구현 — 백엔드] POST /api/auth/guest: 공용 게스트 계정 멱등 생성 + 일반 로그인과 동일 토큰."),
        ("code","GUEST_EMAIL = \"guest@newscurator.demo\"\n\n"
                "@router.post(\"/guest\", response_model=TokenResponse)\n"
                "async def guest_login(db=Depends(get_db)):\n"
                "    user = await db.get(User, GUEST_EMAIL)\n"
                "    if not user:\n"
                "        # 콜드스타트 벡터 생성(실패 시 랜덤 폴백) 후 계정 생성\n"
                "        user = User(email=GUEST_EMAIL, name=\"게스트\", ...)\n"
                "        db.add(user)\n"
                "        try: await db.commit()\n"
                "        except IntegrityError:  # 동시요청 멱등\n"
                "            await db.rollback(); user = await db.get(User, GUEST_EMAIL)\n"
                "    return TokenResponse(access_token=..., refresh_token=...)"),
        ("b","[구현 — 프론트] 로그인 화면에 '계정 없이 둘러보기(게스트)' 버튼 → /api/auth/guest 호출 → 토큰 저장 → /feed."),
        ("b","[결과] 가입 없이 즉시 피드 체험(계정 1개만 멱등 유지). [파일] auth.py, Login.jsx, Register.css"),
    ]),
    ("6. 라이트 테마 / 계정 관리 — 이미 구현됨 확인", [
        ("b","[피드백] '화이트 테마?', '비밀번호 변경 등 계정 관리?'"),
        ("b","[확인] 둘 다 이미 구현됨. 라이트 테마: ThemeContext(다크↔라이트) + index.css "
             "[data-theme=light] 변수 + 헤더 ThemeToggle. 계정 관리: Settings.jsx 비밀번호 변경"
             "(PATCH /users/me/password)·탈퇴(DELETE /users/me)."),
        ("b","[결과] 추가 작업 없이 '구현 완료'로 정리(발표 답변 강화)."),
    ]),
    ("7. 반응형/모바일 대응 보강 (교수님 요청)", [
        ("b","[보강] 헤더 nav 줄바꿈, 480px 패딩/버튼 축소, 구독 카드 모바일 폭(85vw)."),
        ("code","@media (max-width: 767px) {\n"
                "  .header { flex-direction: column; align-items: stretch; }\n"
                "  .header__nav { flex-wrap: wrap; justify-content: center; }\n}\n"
                "@media (max-width: 480px) {\n  .card-scroll > * { flex: 0 0 85vw; }\n}"),
        ("b","[결과] 폰(375px)·태블릿(768px) 레이아웃 유지. [파일] index.css, Feed.css"),
    ]),
    ("8. AI 요약 깨짐 수정 (\\n 글자·영어 머리말)", [
        ("b","[문제] 요약에 \\n이 글자로 보이고 'Here is a 3-line summary:' 영어 머리말 섞임."),
        ("b","[원인] 프롬프트의 '줄바꿈(\\n)으로 구분' 지시 + 후처리 미흡."),
        ("b","[해결] 프롬프트 수정 + _clean_summary() 신설."),
        ("code","def _clean_summary(text):\n"
                "    text = text.replace('\\\\r\\\\n','\\n').replace('\\\\n','\\n')  # 리터럴→실제 줄바꿈\n"
                "    for _ in range(3):  # 영어/한국어 머리말 반복 제거\n"
                "        for pat in _SUMMARY_PREFIX_PATTERNS: text = pat.sub('', text, count=1)\n"
                "        text = text.strip()\n"
                "    # 줄별 마크다운/번호/불릿 제거 ...\n"
                "    if not re.search(r'[가-힣]', result): return None  # 완전 영어 → description 폴백\n"
                "    return result"),
        ("b","[검증] 실제 깨진 요약 입력 → 한국어 3줄만 남고 영어/리터럴 제거 확인. [파일] llm_processor.py"),
    ]),
    ("9. 기자명 추출 개선 + 기자 구독 버튼 항상 표시", [
        ("b","[문제] 외부 언론사 기사에서 기자 구독 버튼이 아예 안 보임."),
        ("b","[원인] 추출이 '본문 끝 200자 + 홍길동 기자'만 봐서 외부 언론사 실패 + 프론트가 "
             "기자명 없으면 버튼 숨김."),
        ("b","[해결 — 백엔드] 다단계 추출(본문 끝/앞 + 이메일 근접 + 역순 어순 + description 보조), "
             "'기자회견·기자단' 등 negative lookahead로 오매칭 차단."),
        ("b","[해결 — 프론트] 기자명 없으면 '기자 정보 없음' 비활성 버튼 표시."),
        ("code","{article.journalist ? (\n"
                "  <button className=\"btn-subscribe\">{article.journalist} 기자 구독</button>\n"
                ") : (\n"
                "  <button className=\"btn-subscribe btn-subscribe--disabled\" disabled>\n"
                "    기자 정보 없음\n  </button>\n)}"),
        ("b","[검증] 추출 단위테스트 8/8 통과. [파일] pipeline.py, ArticleDetail.jsx, ArticleDetail.css"),
    ]),
    ("10. 메인 피드 페이지네이션 + 읽은 기사 숨김 토글", [
        ("b","[요구] 기사 전부 노출(1 2 3 … N 탭) + 읽은 기사 제외."),
        ("b","[백엔드] 추천 트랙 반환 상한 50→300."),
        ("code","-MAX_RECOMMENDATION_TRACK = 50\n-COLD_START_LIMIT = 20\n"
                "+MAX_RECOMMENDATION_TRACK = 300\n+COLD_START_LIMIT = 300"),
        ("b","[프론트] 페이지당 15개, 읽음 숨김 토글(기본 노출), 카테고리/정렬/토글 변경 시 1페이지 리셋."),
        ("code","const PAGE_SIZE = 15;\n"
                "const filtered = hideRead ? items.filter(i => !i.is_read) : items;\n"
                "const sorted = applySortToItems(filtered, activeSort);\n"
                "const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));\n"
                "const paged = sorted.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE);"),
        ("b","[Pagination.jsx 압축 페이저] 1 … 4 5 [6] 7 8 … 22"),
        ("code","function buildPages(current, total) {\n"
                "  if (total <= 7) return [...Array(total)].map((_,i)=>i+1);\n"
                "  const p=[], L=Math.max(2,current-2), R=Math.min(total-1,current+2);\n"
                "  p.push(1); if(L>2) p.push('…');\n"
                "  for(let i=L;i<=R;i++) p.push(i);\n"
                "  if(R<total-1) p.push('…'); p.push(total); return p;\n}"),
        ("b","[결과] 모든 기사 페이지 탐색 + 읽은 기사 토글 제외. 모바일/테마 대응. "
             "[파일] recommendation.py, Feed.jsx, Pagination.jsx/css, Feed.css"),
    ]),
    ("11. DB 백업/복원 스크립트 (USB 이전용)", [
        ("b","pg_dump로 pgvector 임베딩까지 단일 .dump 백업, 다른 PC에서 복원. "
             "[파일] backup_db.bat, restore_db.bat, scripts/backup_db.ps1, scripts/restore_db.ps1"),
    ]),
    ("12. README 전면 재작성", [
        ("b","작동법·기술스택·아키텍처·동작원리·API·데이터모델·환경변수·운영·트러블슈팅·FAQ를 "
             "새로 정리. 게스트 모드·페이지네이션·근거 문서 링크 반영. [파일] README.md"),
    ]),
    ("13. 신뢰도 가중치 학술 근거 (CREDIBILITY_RATIONALE.md)", [
        ("b","논문 3편(최미연 2023 / 언론과학연구 2023 / 김미경 2019)을 직접 읽고(스캔본 OCR) 인용 정리."),
        ("b","[핵심] 논문은 가중치 서열(문체>정보밀도≈인용>출처)은 뒷받침하나 정확한 % 숫자는 "
             "도출 못 함 → '서열은 근거 있음 / 정밀값은 라벨 데이터 튜닝 영역'으로 정직하게 명시."),
        ("b","RB-01 문체30%: '자극적 뉴스 기피'(②)+Meyer/Gaziano '불편향 최대 요인'. "
             "RB-02 정보밀도25%·RB-03 인용25%: '정확성·전문성=전통 가치'(①③). "
             "RB-04 출처20%: '신뢰할 출처로 전환'(②) 보조 지표."),
    ]),
    ("14. 크롤링 1시간 주기 근거 (CRAWL_INTERVAL_RATIONALE.md)", [
        ("b","6가지 근거: ① API 한도 여유(일 25,000 중 1% 미만) ② 신선도 체감 차이 작음 "
             "③ LLM 처리비용 ④ Redis 5분 캐시 조화 ⑤ 정보 과부하 완화 ⑥ 업계 관행."),
        ("b","[메시지] '더 자주 못 해서가 아니라 할 필요가 없어서' 1시간, 설정으로 조정 가능."),
    ]),
    ("15. 데이터 정비", [
        ("b","깨진 요약 334건(전체 350건의 95%) → articles TRUNCATE(사용자·구독 유지) 후 재크롤. "
             "자동 시드 off + 코드의 임의 샘플 기사 11건 제거 → 실제 크롤링 기사만 노출."),
    ]),
]

for title, blocks in sections:
    add_heading_ko(doc, title, level=1)
    for kind, content in blocks:
        if kind == "b":
            add_body(doc, content, size=10.5)
        elif kind == "code":
            add_code_block(doc, content)
        elif kind == "sub":
            add_heading_ko(doc, content, level=2)
    doc.add_paragraph()

# ── 부록: 커밋 목록 ──
add_heading_ko(doc, "부록. 오늘 커밋 목록 (chore/docs-and-scripts)", level=1)
commit_rows = [
    ["3b4062d","(연속)","인코딩 해결 + 크롤러 개선 + README 재작성 + 백업 스크립트"],
    ["4851dea","15:00","게스트 모드 + 반응형 + 신뢰도 근거 초안 + sticky 수정"],
    ["95c0515","15:18","요약 깨짐 + 기자 구독 버튼"],
    ["0f61cf5","15:32","페이지네이션 + 읽은 기사 숨김"],
    ["4bb2048","15:52","신뢰도 학술 근거 + 크롤링 주기 근거"],
    ["6e61964","16:01","신뢰도 가중치 '비율의 근거와 한계'"],
]
add_overview_table(doc, commit_rows, ["커밋","시각","내용"])

out = sys.argv[1] if len(sys.argv) > 1 else "docs/News_Curator_작업보고서_2026-06-01.docx"
doc.save(out)
print("저장 완료:", out)
print("문단 수:", len(doc.paragraphs))
