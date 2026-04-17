/**
 * SortFilter — 피드 정렬 옵션 선택 UI
 * ======================================
 * 추천 트랙을 3가지 기준으로 즉시 재정렬한다.
 *
 *   - 추천순 (기본) : item.score DESC        — 개인화 알고리즘 스코어
 *   - 최신순        : published_at DESC       — 발행 시간 역순
 *   - 신뢰도순      : credibility DESC        — 신뢰도 점수 내림차순
 *
 * 카테고리 필터와 독립적으로 동작하며, 조합이 가능하다.
 * (예: "IT·과학" + "신뢰도순" = IT·과학 카테고리만 신뢰도순 정렬)
 */

import './SortFilter.css';

export const SORT_OPTIONS = [
  { key: 'recommended', label: '추천순' },
  { key: 'latest', label: '최신순' },
  { key: 'credibility', label: '신뢰도순' },
];

export default function SortFilter({ active, onChange }) {
  return (
    <nav className="sort-filter" aria-label="정렬 기준">
      <span className="sort-filter__label" aria-hidden="true">정렬</span>
      {SORT_OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          className={`sort-filter__tab ${
            active === opt.key ? 'sort-filter__tab--active' : ''
          }`}
          onClick={() => onChange(opt.key)}
          aria-pressed={active === opt.key}
        >
          {opt.label}
        </button>
      ))}
    </nav>
  );
}

/**
 * 선택된 정렬 기준에 따라 FeedItem 배열을 정렬한다.
 * 원본 배열을 변경하지 않고 새 배열을 반환한다 (React state immutability).
 *
 * @param {Array} items - FeedItem 배열 (article + score + is_subscribed + is_read)
 * @param {string} sortKey - 'recommended' | 'latest' | 'credibility'
 * @returns {Array} 정렬된 새 배열
 */
export function applySortToItems(items, sortKey) {
  if (!Array.isArray(items) || items.length === 0) return items;

  const copy = [...items];

  switch (sortKey) {
    case 'latest':
      return copy.sort((a, b) => {
        const da = new Date(a?.article?.published_at || 0).getTime();
        const db = new Date(b?.article?.published_at || 0).getTime();
        return db - da; // 최신순
      });

    case 'credibility':
      return copy.sort((a, b) => {
        const ca = Number(a?.article?.credibility ?? 0);
        const cb = Number(b?.article?.credibility ?? 0);
        // 신뢰도 동점이면 최신순 tiebreaker
        if (cb !== ca) return cb - ca;
        const da = new Date(a?.article?.published_at || 0).getTime();
        const db = new Date(b?.article?.published_at || 0).getTime();
        return db - da;
      });

    case 'recommended':
    default:
      return copy.sort((a, b) => {
        const sa = Number(a?.score ?? 0);
        const sb = Number(b?.score ?? 0);
        return sb - sa; // 스코어 내림차순
      });
  }
}
