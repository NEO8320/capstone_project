/**
 * ArticleCard — 기사 카드 컴포넌트
 * ==================================
 *
 * 표시 항목:
 *   - 기사 제목, 3줄 요약, 언론사, 기자명, 발행시간
 *   - 신뢰도 점수 배지 (우측 상단): 초록(90+), 노랑(70~89), 빨강(~69)
 *   - 관심없음 버튼 (하단)
 *
 * 동작:
 *   - 제목 클릭 → 앱 내 기사 상세 페이지(/article?url=...)로 이동 + onRead 호출
 *   - 관심없음 클릭 → 카드 즉시 숨김 + onDislike 콜백 호출
 */

import { useNavigate } from 'react-router-dom';
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

/** 신뢰도 점수 → 배지 색상 클래스 매핑 */
function getBadgeClass(credibility) {
  if (credibility >= 90) return 'badge--green';
  if (credibility >= 70) return 'badge--yellow';
  return 'badge--red';
}

export default function ArticleCard({ item, onDislike, onRead }) {
  const navigate = useNavigate();

  // Bug #4 방어: item 또는 item.article이 null/undefined면 렌더링하지 않는다.
  // Feed.jsx의 filter에서 걸러지지만, 만약의 경우를 위한 최종 방어선.
  if (!item || !item.article) {
    return null;
  }

  const { article, is_subscribed, is_read } = item;

  const handleTitleClick = () => {
    if (onRead && article.url) onRead(article.url);
    navigate(`/article?url=${encodeURIComponent(article.url || '')}`);
  };

  return (
    <article
      className={`article-card${is_read ? ' article-card--read' : ''}`}
      role="article"
    >
      {/* ── 신뢰도 점수 배지 (우측 상단) ── */}
      <span
        className={`article-card__badge ${getBadgeClass(article.credibility ?? 0)}`}
        aria-label={`신뢰도 ${Math.round(article.credibility ?? 0)}점`}
      >
        {Math.round(article.credibility ?? 0)}점
      </span>

      {/* ── 구독 표시 ── */}
      {is_subscribed && (
        <span className="article-card__subscribed" aria-label="구독 중">
          구독
        </span>
      )}

      {/* ── 읽음 표시 ── */}
      {is_read && (
        <span className="article-card__read-badge" aria-label="이미 읽은 기사">
          읽음
        </span>
      )}

      {/* ── 카테고리 태그 ── */}
      <span className="article-card__category">{article.category}</span>

      {/* ── 제목: 클릭 시 앱 내 상세 페이지로 이동 ── */}
      <h3 className="article-card__title">
        <button
          className="article-card__title-btn"
          onClick={handleTitleClick}
          aria-label={`${article.title} 상세 보기`}
        >
          {article.title}
        </button>
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
          onClick={() => onDislike && article.url && onDislike(article.url)}
          aria-label={`${article.title || '기사'} 관심없음`}
        >
          관심없음
        </button>
      </div>
    </article>
  );
}
