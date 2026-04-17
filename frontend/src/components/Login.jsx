/**
 * Login — 로그인 페이지 (공개 라우트)
 * =====================================
 *
 * - 이메일, 비밀번호 입력
 * - POST /api/auth/login
 * - 인증 헤더 미포함 (공개 엔드포인트)
 * - 이미 로그인된 상태면 /feed로 리다이렉트 (App.jsx PublicOnlyRoute)
 */

import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import './Register.css'; // 공통 auth 스타일 공유

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const justRegistered = location.state?.registered;
  const successMessage = location.state?.message;

  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // 인증 헤더 미포함: axios 직접 사용 (인터셉터 우회)
      const { data } = await axios.post('/api/auth/login', {
        email: form.email,
        password: form.password,
      });

      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      navigate('/feed');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || '로그인에 실패했습니다. 이메일과 비밀번호를 확인해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">News Curator</h1>
        <h2 className="auth-card__subtitle">로그인</h2>

        {(justRegistered || successMessage) && (
          <p style={{
            background: '#f0fdf4', color: '#16a34a', padding: '0.75rem 1rem',
            borderRadius: '8px', fontSize: '0.9rem', marginBottom: '1rem',
            border: '1px solid #bbf7d0',
          }}>
            {successMessage || '회원가입이 완료되었습니다. 로그인해 주세요.'}
          </p>
        )}

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
            비밀번호
            <input
              type="password"
              name="password"
              value={form.password}
              onChange={handleChange}
              required
              className="auth-form__input"
              autoComplete="current-password"
            />
          </label>

          <button
            type="submit"
            className="auth-form__submit"
            disabled={loading}
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        <p className="auth-card__link" style={{ textAlign: 'right', marginTop: '-0.5rem' }}>
          <Link to="/forgot-password" style={{ fontSize: '0.875rem', color: '#6b7280' }}>
            비밀번호를 잊으셨나요?
          </Link>
        </p>

        <p className="auth-card__link">
          계정이 없으신가요? <Link to="/register">회원가입</Link>
        </p>
      </div>
    </div>
  );
}
