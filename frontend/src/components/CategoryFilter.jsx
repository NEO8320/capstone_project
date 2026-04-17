/**
 * CategoryFilter — 피드 카테고리 필터 탭
 * =========================================
 * 추천 트랙을 카테고리별로 즉시 필터링하는 가로 탭 UI.
 * '전체' 탭이 기본 선택 상태.
 */

import './CategoryFilter.css';

export default function CategoryFilter({ categories, active, onChange }) {
  return (
    <nav className="cat-filter" aria-label="카테고리 필터">
      {categories.map((cat) => (
        <button
          key={cat}
          className={`cat-filter__tab ${active === cat ? 'cat-filter__tab--active' : ''}`}
          onClick={() => onChange(cat)}
          aria-pressed={active === cat}
        >
          {cat}
        </button>
      ))}
    </nav>
  );
}
