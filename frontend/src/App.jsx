/**
 * App — 루트 컴포넌트 (SPA 네비게이션)
 * =======================================
 *
 * 간단한 탭 기반 네비게이션:
 *   - 피드 (기본 화면)
 *   - 설정 (접근성 글자 크기 조정)
 *
 * 추후 React Router 도입 시 교체 예정.
 */

import { useEffect, useState } from 'react';
import Feed from './components/Feed';
import Settings, { applyFontLevel, getStoredFontLevel } from './components/Settings';

export default function App() {
  const [currentPage, setCurrentPage] = useState('feed');

  // 앱 시작 시 저장된 글자 크기 설정 적용
  useEffect(() => {
    applyFontLevel(getStoredFontLevel());
  }, []);

  return (
    <div className="container">
      {/* ── 헤더 ── */}
      <header className="header">
        <h1 className="header__title">
          News Curator
        </h1>
        <nav className="header__nav" aria-label="메인 내비게이션">
          <button
            className={`nav-btn ${currentPage === 'feed' ? 'nav-btn--active' : ''}`}
            onClick={() => setCurrentPage('feed')}
            aria-current={currentPage === 'feed' ? 'page' : undefined}
          >
            피드
          </button>
          <button
            className={`nav-btn ${currentPage === 'settings' ? 'nav-btn--active' : ''}`}
            onClick={() => setCurrentPage('settings')}
            aria-current={currentPage === 'settings' ? 'page' : undefined}
          >
            설정
          </button>
        </nav>
      </header>

      {/* ── 페이지 콘텐츠 ── */}
      <main>
        {currentPage === 'feed' && <Feed />}
        {currentPage === 'settings' && <Settings />}
      </main>
    </div>
  );
}
