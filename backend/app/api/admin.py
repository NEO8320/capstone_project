# -*- coding: utf-8 -*-
"""
관리자/개발용 API (인증 필수)
====================================
POST /api/admin/seed   — 샘플 기사를 DB에 삽입 (개발·데모용)
POST /api/admin/crawl  — 크롤링 파이프라인 수동 트리거

보안: 두 엔드포인트 모두 Depends(get_current_user)를 통해
JWT 인증을 요구한다. 토큰 없이 호출하면 401 Unauthorized.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models import Article, User
from app.services.embedding import get_embedding

router = APIRouter()

# 샘플 기사 데이터 (8개 카테고리, 각 2~3건)
SAMPLE_ARTICLES = [
    {
        "url": "https://sample.news/politics/001",
        "title": "여야, 예산안 협상 본격화…복지·국방 예산 줄다리기",
        "body": "여야가 예산안 협상에 본격 돌입했다. 여당은 국방비 증액을, 야당은 복지 예산 확대를 주장하며 팽팽한 줄다리기가 이어지고 있다. 국회 예산결산특별위원회는 오늘 전체회의를 열고 세부 항목별 조율에 나선다.",
        "summary": "여야가 예산안 협상에 본격 돌입했다.\n여당은 국방비 증액, 야당은 복지 예산 확대를 주장 중이다.\n예산결산특별위원회가 세부 항목별 조율에 나선다.",
        "category": "정치",
        "credibility": 82.5,
        "rb01_tone": 78.0, "rb02_density": 85.0, "rb03_quotes": 75.0, "rb04_journalist": 100.0,
        "press": "한국일보",
        "journalist": "김정수",
        "hours_ago": 1,
    },
    {
        "url": "https://sample.news/politics/002",
        "title": "대통령실, 한미 정상회담 의제 조율…경제·안보 동시 논의 전망",
        "body": "대통령실이 한미 정상회담 의제를 조율 중이라고 밝혔다. 경제 협력과 안보 현안을 동시에 논의할 전망이다. 양국 간 반도체 공급망 협력이 핵심 의제로 떠오르고 있다.",
        "summary": "대통령실이 한미 정상회담 의제를 조율 중이다.\n경제 협력과 안보 현안을 동시에 논의할 전망이다.\n반도체 공급망 협력이 핵심 의제로 부상했다.",
        "category": "정치",
        "credibility": 88.0,
        "rb01_tone": 90.0, "rb02_density": 82.0, "rb03_quotes": 85.0, "rb04_journalist": 100.0,
        "press": "KBS",
        "journalist": "이서진",
        "hours_ago": 3,
    },
    {
        "url": "https://sample.news/economy/001",
        "title": "코스피 2,600선 회복…반도체·2차전지 동반 상승",
        "body": "코스피가 반도체 업종 강세에 힘입어 2,600선을 회복했다. 삼성전자와 SK하이닉스 등 반도체주가 2% 이상 오르며 지수 상승을 이끌었다.",
        "summary": "코스피가 2,600선을 회복하며 반도체주가 강세를 보였다.\n삼성전자와 반도체주가 2% 이상 올라 지수 상승을 이끌었다.\n전문가들은 글로벌 수요 회복 가능성을 긍정적으로 평가했다.",
        "category": "경제",
        "credibility": 79.0,
        "rb01_tone": 72.0, "rb02_density": 88.0, "rb03_quotes": 65.0, "rb04_journalist": 100.0,
        "press": "매일경제",
        "journalist": "박현우",
        "hours_ago": 2,
    },
    {
        "url": "https://sample.news/economy/002",
        "title": "한국은행 기준금리 3.00% 동결…'상반기 인하 가능성 열어둔다'",
        "body": "한국은행 금융통화위원회가 기준금리를 3.00%로 동결했다. 총재는 상반기 인하 가능성을 열어두겠다고 밝히며 향후 경제 상황을 주시하겠다고 전했다.",
        "summary": "한국은행이 기준금리를 3.00%로 동결했다.\n총재는 상반기 인하 가능성을 열어두겠다고 밝혔다.\n시장은 하반기 금리 인하 가능성에 주목하고 있다.",
        "category": "경제",
        "credibility": 91.5,
        "rb01_tone": 95.0, "rb02_density": 92.0, "rb03_quotes": 88.0, "rb04_journalist": 100.0,
        "press": "연합뉴스",
        "journalist": "최민호",
        "hours_ago": 5,
    },
    {
        "url": "https://sample.news/society/001",
        "title": "서울 지하철 2호선 출근길 고장…시민 불편 극심",
        "body": "서울 지하철 2호선이 출근 시간대에 고장을 일으켜 시민들이 큰 불편을 겪었다. 서울교통공사는 오전 7시 30분경 신호 장애가 발생했다고 밝혔다.",
        "summary": "서울 지하철 2호선이 출근 시간대에 고장을 일으켜 시민 불편이 극심했다.\n서울교통공사는 오전 7시 30분 신호 장애가 발생했다고 밝혔다.\n지하철은 약 40분간 지연 운행된 후 오전 9시경 정상화됐다.",
        "category": "사회",
        "credibility": 75.0,
        "rb01_tone": 65.0, "rb02_density": 80.0, "rb03_quotes": 70.0, "rb04_journalist": 100.0,
        "press": "SBS",
        "journalist": "이하늘",
        "hours_ago": 4,
    },
    {
        "url": "https://sample.news/tech/001",
        "title": "삼성전자, 차세대 AI 칩 '엑시노스 2500' 공개…성능 40% 향상",
        "body": "삼성전자가 차세대 AI 모바일 칩 '엑시노스 2500'을 공개했다. 전작 대비 AI 추론 성능이 40% 향상됐으며 갤럭시 S25에 탑재될 전망이다.",
        "summary": "삼성전자가 AI 칩 엑시노스 2500을 공개했다.\n전작 대비 AI 성능이 40% 향상되어 큰 주목을 받았다.\n올해 갤럭시 S25 시리즈에 탑재될 전망이다.",
        "category": "IT·과학",
        "credibility": 87.0,
        "rb01_tone": 85.0, "rb02_density": 90.0, "rb03_quotes": 78.0, "rb04_journalist": 100.0,
        "press": "ZDNet Korea",
        "journalist": "정우진",
        "hours_ago": 2,
    },
    {
        "url": "https://sample.news/tech/002",
        "title": "오픈AI, GPT-5 개발 공식 발표…'인간 수준 추론 가능' 주장",
        "body": "오픈AI가 GPT-5 개발을 공식 발표했다. 샘 올트먼 CEO는 인간 수준의 추론이 가능할 것이라 주장하며 올해 하반기 출시를 목표로 하고 있다고 밝혔다.",
        "summary": "오픈AI가 GPT-5 개발을 공식 발표했다.\n샘 올트먼은 인간 수준 추론이 가능하다며 GPT-4 대비 대폭 향상됐다고 밝혔다.\n개발 일정과 세부 사양은 추가 공개 예정이다.",
        "category": "IT·과학",
        "credibility": 83.5,
        "rb01_tone": 75.0, "rb02_density": 82.0, "rb03_quotes": 88.0, "rb04_journalist": 100.0,
        "press": "전자신문",
        "journalist": "이준혁",
        "hours_ago": 6,
    },
    {
        "url": "https://sample.news/culture/001",
        "title": "부산 영화제 올해 역대 최다 관객…글로벌 작품 경쟁 치열",
        "body": "올해 부산 영화제가 역대 최다 관객을 동원했다. 국내외 작품 간 경쟁이 치열했으며 한국 독립 영화 3편이 수상 후보에 올랐다. 관객 만족도도 98%를 기록했다.",
        "summary": "올해 부산 영화제가 역대 최다 관객을 동원했다.\n글로벌 작품 경쟁이 치열했으며 관객 만족도 98%를 기록했다.\n한국 독립 영화 3편이 수상 후보에 올라 큰 관심을 받았다.",
        "category": "생활·문화",
        "credibility": 72.0,
        "rb01_tone": 68.0, "rb02_density": 70.0, "rb03_quotes": 60.0, "rb04_journalist": 100.0,
        "press": "문화일보",
        "journalist": "김소연",
        "hours_ago": 8,
    },
    {
        "url": "https://sample.news/world/001",
        "title": "미중 무역 분쟁 재점화…추가 관세 부과 가능성 시사",
        "body": "미중 간 무역 분쟁이 다시 격화되고 있다. 미국 측이 추가 관세 부과 가능성을 시사하면서 양국 간 긴장이 고조되고 있다. 글로벌 공급망에 미칠 영향이 주목된다.",
        "summary": "미중 무역 분쟁이 다시 격화되며 추가 관세 부과 가능성이 시사됐다.\n양국 간 긴장이 고조되면서 글로벌 경제에 미칠 영향이 주목된다.\n국제 경제 기관들은 시장 불확실성 확대를 경고했다.",
        "category": "세계",
        "credibility": 90.0,
        "rb01_tone": 88.0, "rb02_density": 92.0, "rb03_quotes": 85.0, "rb04_journalist": 100.0,
        "press": "연합뉴스",
        "journalist": "박지훈",
        "hours_ago": 3,
    },
    {
        "url": "https://sample.news/entertainment/001",
        "title": "BTS 정국, 솔로 월드투어 전석 매진 기록 화제",
        "body": "BTS 정국이 전역 후 시작한 솔로 월드투어가 전석 매진 기록을 세웠다. 소속사 측은 추가 공연 일정을 검토 중이라고 밝혔다.",
        "summary": "BTS 정국이 솔로 월드투어 전석 매진 기록을 세웠다.\n소속사 측은 추가 공연 일정을 검토 중이라고 밝혔다.\n팬들의 SNS에서 뜨거운 반응이 이어지고 있다.",
        "category": "연예",
        "credibility": 68.0,
        "rb01_tone": 55.0, "rb02_density": 60.0, "rb03_quotes": 70.0, "rb04_journalist": 100.0,
        "press": "OSEN",
        "journalist": "최영희",
        "hours_ago": 5,
    },
    {
        "url": "https://sample.news/sports/001",
        "title": "손흥민, 프리미어리그 시즌 10호 골 달성",
        "body": "손흥민이 프리미어리그 경기에서 시즌 10번째 골을 터뜨렸다. 경기 후 인터뷰에서 '팀의 승리가 가장 중요하다'고 소감을 밝혔다.",
        "summary": "손흥민이 프리미어리그에서 시즌 10호 골을 달성했다.\n경기에서 1-0 승리를 이끌며 팀 공헌도가 높았다.\n이번 시즌 손흥민은 꾸준한 활약으로 프리미어리그 최고 공격수로 평가받고 있다.",
        "category": "스포츠",
        "credibility": 85.0,
        "rb01_tone": 82.0, "rb02_density": 78.0, "rb03_quotes": 90.0, "rb04_journalist": 100.0,
        "press": "스포츠조선",
        "journalist": "이태호",
        "hours_ago": 7,
    },
]


# ============================================================
# 빈 DB 자동 시드 헬퍼 (서버 시작 시 호출, JWT 불필요)
# ============================================================
async def seed_sample_articles_if_empty(db: AsyncSession) -> int:
    """
    articles 테이블이 비어 있으면 SAMPLE_ARTICLES를 일괄 삽입한다.

    ■ 용도:
      main.py의 _startup_crawl() 태스크에서 호출되어
      실제 크롤링 전에 콜드 스타트 사용자에게 즉각적인 피드 컨텐츠를 제공한다.

    ■ 기존 seed_articles 엔드포인트와의 차이:
      1. JWT 인증 없음 (내부 호출 전용)
      2. 빈 DB일 때만 동작 (SELECT COUNT(*) 사전 검사)
      3. on_conflict_do_nothing — 이미 있으면 건드리지 않음

    Args:
        db: 활성 AsyncSession (호출자가 commit 관리)

    Returns:
        삽입된 샘플 기사 건수. DB가 비어있지 않으면 0.
    """
    # 선 검사: 기사가 이미 있으면 시드하지 않음
    count_result = await db.execute(select(func.count()).select_from(Article))
    existing_count = count_result.scalar_one()
    if existing_count and existing_count > 0:
        return 0

    print(f"[Seed] DB가 비어있음 - {len(SAMPLE_ARTICLES)}개 샘플 기사 삽입 시작")
    now = datetime.now(timezone.utc)
    inserted = 0

    for article in SAMPLE_ARTICLES:
        try:
            published_at = now - timedelta(hours=article["hours_ago"])
            embed_text = f"{article['title']} {article['summary']}"

            # 임베딩 생성 (Ko-SBERT — 호출자가 미리 프리로드 완료 가정)
            embedding = await get_embedding(embed_text)

            stmt = pg_insert(Article).values(
                url=article["url"],
                title=article["title"],
                body=article["body"],
                summary=article["summary"],
                category=article["category"],
                embedding=embedding,
                credibility=article["credibility"],
                rb01_tone=article.get("rb01_tone"),
                rb02_density=article.get("rb02_density"),
                rb03_quotes=article.get("rb03_quotes"),
                rb04_journalist=article.get("rb04_journalist"),
                press=article["press"],
                journalist=article.get("journalist"),
                published_at=published_at,
            ).on_conflict_do_nothing(index_elements=["url"])
            await db.execute(stmt)
            inserted += 1
        except Exception as e:
            print(f"[Seed] 샘플 기사 삽입 실패 ({article['url']}): {e}")

    await db.commit()
    print(f"[Seed] 샘플 기사 {inserted}건 삽입 완료")
    return inserted


@router.post("/seed", summary="샘플 기사 DB 삽입 (개발·데모용)")
async def seed_articles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    개발·데모용 샘플 기사를 DB에 삽입한다.
    Ko-SBERT 임베딩을 실시간 생성하므로 최초 실행 시 시간이 걸릴 수 있다.
    """
    now = datetime.now(timezone.utc)
    inserted = 0
    skipped = 0
    errors = []

    for article in SAMPLE_ARTICLES:
        try:
            published_at = now - timedelta(hours=article["hours_ago"])
            embed_text = f"{article['title']} {article['summary']}"

            # 임베딩 생성 (Ko-SBERT)
            embedding = await get_embedding(embed_text)

            stmt = pg_insert(Article).values(
                url=article["url"],
                title=article["title"],
                body=article["body"],
                summary=article["summary"],
                category=article["category"],
                embedding=embedding,
                credibility=article["credibility"],
                rb01_tone=article.get("rb01_tone"),
                rb02_density=article.get("rb02_density"),
                rb03_quotes=article.get("rb03_quotes"),
                rb04_journalist=article.get("rb04_journalist"),
                press=article["press"],
                journalist=article.get("journalist"),
                published_at=published_at,
            ).on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "summary": article["summary"],
                    "embedding": embedding,
                    "credibility": article["credibility"],
                    "rb01_tone": article.get("rb01_tone"),
                    "rb02_density": article.get("rb02_density"),
                    "rb03_quotes": article.get("rb03_quotes"),
                    "rb04_journalist": article.get("rb04_journalist"),
                },
            )
            await db.execute(stmt)
            inserted += 1
        except Exception as e:
            errors.append(f"{article['url']}: {str(e)}")
            skipped += 1

    await db.commit()

    return JSONResponse({
        "message": f"샘플 기사 삽입 완료: {inserted}건 성공, {skipped}건 실패",
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    })


@router.post("/crawl", summary="크롤링 파이프라인 수동 트리거 (개발용)")
async def trigger_crawl(user: User = Depends(get_current_user)):
    """크롤링 파이프라인을 백그라운드에서 즉시 실행한다."""
    try:
        from app.services.pipeline import run_crawl_pipeline
        asyncio.ensure_future(run_crawl_pipeline())
        return {
            "message": "크롤링 파이프라인이 백그라운드에서 시작됐습니다. 완료까지 수 분이 걸릴 수 있습니다.",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
