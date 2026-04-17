"""
기존 DB에 적재된 기사들의 신뢰도 점수를 규칙 기반 알고리즘으로 일괄 재계산한다.
=============================================================================

왜 필요한가
-----------
구 버전에서는 Llama 3 8B가 신뢰도 JSON 서브필드를 자주 누락하거나
placeholder 문자열을 반환해 _clamp fallback(50)으로 수렴 → 대부분의 기사가
신뢰도 45~55 구간으로 몰리는 버그가 있었다. 크롤링은 이미 수행됐기 때문에
기존 DB 레코드의 credibility / rb01_tone / rb02_density / rb03_quotes /
rb04_journalist 컬럼도 모두 업데이트해야 프론트 차트/배지가 올바르게 뜬다.

실행 방법
---------
    # (Windows)
    cd backend
    python -m scripts.recalculate_credibility

    # (Linux/Mac)
    cd backend
    python -m scripts.recalculate_credibility

안전성
------
* 트랜잭션 단위는 기사 1건. 중간 실패해도 이미 처리된 기사는 보존.
* credibility 외 컬럼(title/body/summary/embedding 등)은 전혀 건드리지 않는다.
* 배치 크기(500)마다 commit하여 장시간 락을 방지.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# backend/ 를 PYTHONPATH 에 추가 (스크립트 단독 실행용)
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, update  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.models import Article  # noqa: E402
from app.services.credibility import calculate_credibility  # noqa: E402


BATCH_SIZE = 500


async def recalculate_all() -> None:
    """모든 articles 레코드의 신뢰도 점수를 규칙 기반으로 재계산."""
    total = 0
    updated = 0

    async with async_session() as session:
        result = await session.execute(
            select(Article.url, Article.title, Article.body, Article.journalist)
        )
        rows = result.all()
        total = len(rows)
        print(f"[Recalc] 대상 기사 수: {total}건")

        for i, row in enumerate(rows, start=1):
            url, title, body, journalist = row
            cred = calculate_credibility(
                title=title or "",
                body=body or "",
                journalist=journalist,
            )

            await session.execute(
                update(Article)
                .where(Article.url == url)
                .values(
                    credibility=cred["credibility"],
                    rb01_tone=cred["rb01_tone"],
                    rb02_density=cred["rb02_density"],
                    rb03_quotes=cred["rb03_quotes"],
                    rb04_journalist=cred["rb04_journalist"],
                )
            )
            updated += 1

            if i % BATCH_SIZE == 0:
                await session.commit()
                print(f"[Recalc] 진행 {i}/{total}건 커밋 완료")

        await session.commit()

    print(f"[Recalc] 완료 — 갱신된 기사: {updated}/{total}")


async def summarize_distribution() -> None:
    """재계산 후 점수 분포를 출력해 효과를 확인."""
    async with async_session() as session:
        result = await session.execute(select(Article.credibility))
        scores = [r[0] for r in result.all() if r[0] is not None]

    if not scores:
        print("[Recalc] 분포 계산 대상 없음")
        return

    buckets = {"0-39": 0, "40-59": 0, "60-79": 0, "80-100": 0}
    for s in scores:
        if s < 40:
            buckets["0-39"] += 1
        elif s < 60:
            buckets["40-59"] += 1
        elif s < 80:
            buckets["60-79"] += 1
        else:
            buckets["80-100"] += 1

    print("\n[Recalc] 신뢰도 점수 분포")
    for label, count in buckets.items():
        pct = (count / len(scores)) * 100
        bar = "█" * int(pct / 2)
        print(f"  {label:>7} : {count:>5}건 ({pct:5.1f}%) {bar}")
    print(f"  평균      : {sum(scores)/len(scores):.1f}")
    print(f"  중앙값    : {sorted(scores)[len(scores)//2]:.1f}")


async def main() -> None:
    await recalculate_all()
    await summarize_distribution()


if __name__ == "__main__":
    asyncio.run(main())
