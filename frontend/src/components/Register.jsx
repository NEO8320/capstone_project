/**
 * Register — 회원가입 페이지 (공개 라우트)
 * ==========================================
 *
 * - 이메일, 비밀번호, 이름, 관심 카테고리 1개 이상 선택
 * - API-01: POST /api/v1/auth/register
 * - 인증 헤더 미포함 (공개 엔드포인트)
 * - 이미 로그인된 상태면 /feed로 리다이렉트 (App.jsx PublicOnlyRoute)
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import './Register.css';

const CATEGORIES = [
  '정치', '경제', '사회', 'IT·과학', '생활·문화', '세계', '연예', '스포츠',
];

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: '',
    password: '',
    name: '',
  });
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const toggleCategory = (cat) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (selectedCategories.length < 1) {
      setError('관심 카테고리를 1개 이상 선택해 주세요. (2개 이상 권장)');
      return;
    }
    if (form.password.length < 8) {
      setError('비밀번호는 최소 8자 이상이어야 합니다.');
      return;
    }

    setLoading(true);
    try {
      // 인증 헤더 미포함: axios 직접 사용 (인터셉터 우회)
      await axios.post('/api/auth/register', {
        email: form.email,
        password: form.password,
        name: form.name,
        interest_categories: selectedCategories,
      }, { timeout: 60000 }); // 60초 — 첫 실행 시 모델 다운로드 시간 고려

      // ── 가입 성공 직후 자동 로그인 → /feed 직행 (UX 개선) ──
      // 이전엔 /login 으로 리다이렉트해 사용자가 이메일/비번을 다시 입력해야 했음.
      // 이제 동일한 자격증명으로 즉시 로그인 시도 후, 성공하면 토큰 저장 → /feed.
      // 자동 로그인 실패 시(드물) 안전망으로 /login 페이지에 성공 메시지 전달.
      try {
        const loginResp = await axios.post('/api/auth/login', {
          email: form.email,
          password: form.password,
        }, { timeout: 10000 });
        const { access_token, refresh_token } = loginResp.data || {};
        if (access_token) {
          localStorage.setItem('access_token', access_token);
          if (refresh_token) localStorage.setItem('refresh_token', refresh_token);
          navigate('/feed', { replace: true });
          return;
        }
        // 토큰 누락 시 안전 폴백
        navigate('/login', { state: { registered: true, email: form.email } });
      } catch (loginErr) {
        // 자동 로그인 실패는 치명적이지 않음. 사용자에게 명시적 로그인 유도.
        console.warn('[Register] 자동 로그인 실패:', loginErr);
        navigate('/login', { state: { registered: true, email: form.email } });
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || '회원가입에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">News Curator</h1>
        <h2 className="auth-card__subtitle">회원가입</h2>

        {error && <p className="auth-card__error" role="alert">{error}</p>}

        <form onSubmit={handleSubmit} className="auth-form">
          <label className="auth-form__label">
            이메일
            <input
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              required
              className="auth-form__input"
              autoComplete="email"
            />
          </label>

          <label className="auth-form__label">
            이름
            <input
              type="text"
              name="name"
              value={form.name}
              onChange={handleChange}
              required
              maxLength={50}
              className="auth-form__input"
              autoComplete="name"
            />
          </label>

          <label className="auth-form__label">
            비밀번호 (8자 이상)
            <input
              type="password"
              name="password"
              value={form.password}
              onChange={handleChange}
              required
              minLength={8}
              className="auth-form__input"
              autoComplete="new-password"
            />
          </label>

          <fieldset className="auth-form__fieldset">
            <legend className="auth-form__legend">
              관심 카테고리 선택 (1개 이상, 2개 이상 권장)
            </legend>
            <p className="auth-form__hint">
              많이 선택할수록 더 정확한 추천을 받을 수 있습니다.
            </p>
            <div className="category-grid">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  className={`category-btn ${selectedCategories.includes(cat) ? 'category-btn--selected' : ''}`}
                  onClick={() => toggleCategory(cat)}
                  aria-pressed={selectedCategories.includes(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
          </fieldset>

          <button
            type="submit"
            className="auth-form__submit"
            disabled={loading}
          >
            {loading ? 'AI 관심 벡터 생성 중... (최초 실행 시 1분 소요)' : '회원가입'}
          </button>
        </form>

        <p className="auth-card__link">
          이미 계정이 있으신가요? <Link to="/login">로그인</Link>
        </p>
      </div>
    </div>
  );
}
