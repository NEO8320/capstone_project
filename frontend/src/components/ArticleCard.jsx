/**
 * ArticleCard — 기사 카드 컴포넌트
 * ==================================
 *
 * 표시 항목:
 *   - 기사 제목, 3줄 요약, 언론사, 기자명, 발행시간
 *   - 신뢰도 3단계 배지 (우측 상단): 초록(90+), 노랑(70~89), 빨강(~69)
 *   - 관심없음 버튼 (하단)
 *
 * 동작:
 *   - 제목 클릭 → 원문 언론사 페이지가 새 탭으로 열림 (저작권 보호)
 *   - 관심없음 클릭 → 카드 즉시 숨김 + onDislike 콜백 호출
 */

import './ArticleCard.css';

/** 발행 시간을 '~분 전', '~시간 전' 등으로 변환 */
function formatTimeAgo(dateString) {
  const now = new Date();
  const published = new Date(dateString);
  const diffMs = now - published;
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return '방금 전';
  if (diffMin < 60) return `${diffMin}분 전`;

  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;

  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}일 전`;

  return published.toLocaleDateString('ko-KR');
}

/** 신뢰도 점수 → 배지 정보 매핑 */
function getBadgeInfo(credibility) {
  if (credibility >= 90) return { label: '높음', className: 'badge--green' };
  if (credibility >= 70) return { label: '보통', className: 'badge--yellow' };
  return { label: '낮음', className: 'badge--red' };
}

export default function ArticleCard({ item, onDislike }) {
  const { article, is_subscribed } = item;
  const badge = getBadgeInfo(article.credibility);

  return (
    <article className="article-card" role="article">
      {/* ── 신뢰도 배지 (우측 상단) ── */}
      <span
        className={`article-card__badge ${badge.className}`}
        title={`신뢰도 ${Math.round(article.credibility)}점`}
        aria-label={`신뢰도 ${badge.label}`}
      >
        {badge.label}
      </span>

      {/* ── 구독 표시 ── */}
      {is_subscribed && (
        <span className="article-card__subscribed" aria-label="구독 중">
          구독
        </span>
      )}

      {/* ── 카테고리 태그 ── */}
      <span className="article-card__category">{article.category}</span>

      {/* ── 제목: 클릭 시 원문 새 탭 열기 (저작권 보호) ── */}
      <h3 className="article-card__title">
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`${article.title} — 원문 보기 (새 탭)`}
        >
          {article.title}
        </a>
      </h3>

      {/* ── 3줄 요약 ── */}
      <p className="article-card__summary">{article.summary}</p>

      {/* ── 메타 정보: 언론사, 기자명, 발행시간 ── */}
      <div className="article-card__meta">
        <span className="article-card__press">{article.press}</span>
        {article.journalist && (
          <span className="article-card__journalist">
            {article.journalist} 기자
          </span>
        )}
        <time
          className="article-card__time"
          dateTime={article.published_at}
        >
          {formatTimeAgo(article.published_at)}
        </time>
      </div>

      {/* ── 관심없음 버튼 ── */}
      <div className="article-card__actions">
        <button
          className="btn-dislike"
          onClick={() => onDislike(article.url)}
          aria-label={`${article.title} 관심없음`}
        >
          관심없음
        </button>
      </div>
    </article>
  );
}
