/**
 * ForgotPassword — 비밀번호 찾기 페이지
 * ========================================
 * 이메일 입력 → POST /api/auth/forgot-password
 * 데모 환경: 응답의 reset_link를 화면에 표시
 */

import axios from 'axios';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import './AuthExtra.css';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [resetLink, setResetLink] = useState(null);
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const { data } = await axios.post(
        '/api/auth/forgot-password',
        { email },
        { timeout: 10000 },
      );
      setSubmitted(true);
      if (data.reset_link) setResetLink(data.reset_link);
    } catch (err) {
      setError(err.response?.data?.detail || '요청에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <h1 className="auth-title">News Curator</h1>
          <h2 className="auth-subtitle">이메일 발송 완료</h2>
          <p className="auth-info">
            입력하신 이메일로 재설정 링크를 발송했습니다.
            받은 편지함을 확인해 주세요.
          </p>

          {/* 데모 환경: 링크 직접 표시 */}
          {resetLink && (
            <div className="auth-dev-box">
              <p className="auth-dev-label">개발/데모 환경 — 재설정 링크</p>
              <a href={resetLink} className="auth-dev-link">
                비밀번호 재설정하기 →
              </a>
            </div>
          )}

          <Link to="/login" className="auth-back-link">← 로그인으로 돌아가기</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h1 className="auth-title">News Curator</h1>
        <h2 className="auth-subtitle">비밀번호 찾기</h2>
        <p className="auth-info">
          가입할 때 사용한 이메일을 입력하면 재설정 링크를 발송합니다.
        </p>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="email">이메일</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="example@email.com"
              required
              autoFocus
            />
          </div>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button type="submit" className="auth-btn" disabled={loading}>
            {loading ? '처리 중...' : '재설정 링크 받기'}
          </button>
        </form>

        <Link to="/login" className="auth-back-link">← 로그인으로 돌아가기</Link>
      </div>
    </div>
  );
}
