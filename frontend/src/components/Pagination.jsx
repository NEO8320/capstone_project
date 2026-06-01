/**
 * Pagination — 페이지 번호 네비게이션
 * =====================================
 * 추천 트랙을 페이지 단위로 나눠 보여줄 때 하단에 표시한다.
 *
 * 압축 표시: 페이지가 많으면 전부 나열하지 않고
 *   ‹  1 … 4 5 [6] 7 8 … 22  ›
 * 형태로 현재 페이지 주변(±2) + 양끝만 보여주고 나머지는 '…' 로 생략한다.
 *
 * props:
 *   - currentPage: 현재 페이지 (1-based)
 *   - totalPages : 전체 페이지 수
 *   - onChange(page): 페이지 클릭 시 호출
 */

import './Pagination.css';

const ELLIPSIS = '…';

/** 표시할 페이지 토큰 배열을 만든다. (숫자 또는 ELLIPSIS) */
function buildPages(current, total) {
  // 총 7칸 이하이면 전부 표시
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages = [];
  const left = Math.max(2, current - 2);
  const right = Math.min(total - 1, current + 2);

  pages.push(1); // 항상 첫 페이지
  if (left > 2) pages.push(ELLIPSIS);

  for (let p = left; p <= right; p += 1) pages.push(p);

  if (right < total - 1) pages.push(ELLIPSIS);
  pages.push(total); // 항상 마지막 페이지

  return pages;
}

export default function Pagination({ currentPage, totalPages, onChange }) {
  if (!totalPages || totalPages <= 1) return null;

  const pages = buildPages(currentPage, totalPages);
  const go = (p) => {
    if (p < 1 || p > totalPages || p === currentPage) return;
    onChange(p);
  };

  return (
    <nav className="pagination" aria-label="페이지 네비게이션">
      <button
        type="button"
        className="pagination__btn pagination__btn--arrow"
        onClick={() => go(currentPage - 1)}
        disabled={currentPage <= 1}
        aria-label="이전 페이지"
      >
        ‹
      </button>

      {pages.map((p, idx) =>
        p === ELLIPSIS ? (
          <span key={`e${idx}`} className="pagination__ellipsis" aria-hidden="true">
            {ELLIPSIS}
          </span>
        ) : (
          <button
            key={p}
            type="button"
            className={`pagination__btn ${p === currentPage ? 'pagination__btn--active' : ''}`}
            onClick={() => go(p)}
            aria-current={p === currentPage ? 'page' : undefined}
          >
            {p}
          </button>
        )
      )}

      <button
        type="button"
        className="pagination__btn pagination__btn--arrow"
        onClick={() => go(currentPage + 1)}
        disabled={currentPage >= totalPages}
        aria-label="다음 페이지"
      >
        ›
      </button>
    </nav>
  );
}
