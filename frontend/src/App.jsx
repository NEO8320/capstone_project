/**
 * App — 루트 컴포넌트 (React Router SPA)
 * =========================================
 *
 * 라우팅 구조:
 *   /login         → 로그인 (공개)
 *   /register      → 회원가입 (공개)
 *   /              → 피드로 리다이렉트
 *   /feed          → 피드 (인증 필요)
 *   /article       → 기사 상세 (?url=...) (인증 필요)
 *   /subscriptions → 구독 설정 (인증 필요)
 *   /settings      → 설정 (인증 필요)
 */

import { useEffect } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import Feed from './components/Feed';
import Login from './components/Login';
import Register from './components/Register';
import Settings, { applyFontLevel, getStoredFontLevel } from './components/Settings';
import ThemeToggle from './components/ThemeToggle';
import ArticleDetail from './pages/ArticleDetail';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Subscriptions from './pages/Subscriptions';

/** 로그인 상태 확인 */
function isAuthenticated() {
  return !!localStorage.getItem('access_token');
}

/** 인증 필요 라우트 가드 */
function PrivateRoute({ children }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

/** 이미 로그인된 사용자를 피드로 리다이렉트 */
function PublicOnlyRoute({ children }) {
  if (isAuthenticated()) {
    return <Navigate to="/feed" replace />;
  }
  return children;
}

/** 네비게이션 헤더 (인증 상태에서만 표시) */
function AppHeader() {
  const location = useLocation();
  const navigate = useNavigate();

  if (!isAuthenticated()) return null;

  const p = location.pathname;

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    navigate('/login');
  };

  return (
    <header className="header">
      <h1 className="header__title">
        <Link to="/feed" className="header__title-link">
          News Curator
        </Link>
      </h1>
      <nav className="header__nav" aria-label="메인 내비게이션">
        <Link
          to="/feed"
          className={`nav-btn ${p === '/feed' || p === '/' ? 'nav-btn--active' : ''}`}
          aria-current={p === '/feed' || p === '/' ? 'page' : undefined}
        >
          피드
        </Link>
        <Link
          to="/subscriptions"
          className={`nav-btn ${p === '/subscriptions' ? 'nav-btn--active' : ''}`}
          aria-current={p === '/subscriptions' ? 'page' : undefined}
        >
          구독
        </Link>
        <Link
          to="/settings"
          className={`nav-btn ${p === '/settings' ? 'nav-btn--active' : ''}`}
          aria-current={p === '/settings' ? 'page' : undefined}
        >
          설정
        </Link>
        <button className="nav-btn" onClick={handleLogout}>
          로그아웃
        </button>
        <ThemeToggle />
      </nav>
    </header>
  );
}

export default function App() {
  useEffect(() => {
    applyFontLevel(getStoredFontLevel());
  }, []);

  return (
    <div className="container">
      <AppHeader />
      <main>
        <Routes>
          {/* 공개 라우트 */}
          <Route path="/login"            element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
          <Route path="/register"         element={<PublicOnlyRoute><Register /></PublicOnlyRoute>} />
          <Route path="/forgot-password"  element={<ForgotPassword />} />
          <Route path="/reset-password"   element={<ResetPassword />} />

          {/* 인증 필요 라우트 */}
          <Route path="/feed"          element={<PrivateRoute><Feed /></PrivateRoute>} />
          <Route path="/article"       element={<PrivateRoute><ArticleDetail /></PrivateRoute>} />
          <Route path="/subscriptions" element={<PrivateRoute><Subscriptions /></PrivateRoute>} />
          <Route path="/settings"      element={<PrivateRoute><Settings /></PrivateRoute>} />

          {/* 기본 리다이렉트 */}
          <Route path="/"  element={<Navigate to="/feed" replace />} />
          <Route path="*"  element={<Navigate to="/feed" replace />} />
        </Routes>
      </main>
    </div>
  );
}
