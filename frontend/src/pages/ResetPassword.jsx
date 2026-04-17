/**
 * ResetPassword — 비밀번호 재설정 페이지
 * ==========================================
 * URL: /reset-password?token=<JWT>
 * POST /api/auth/reset-password → 성공 시 /login으로 이동
 */

import axios from 'axios';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import './AuthExtra.css';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';

  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!token) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <h1 className="auth-title">News Curator</h1>
          <p className="auth-error">유효하지 않은 링크입니다.</p>
          <Link to="/forgot-password" className="auth-back-link">
            비밀번호 찾기로 이동
          </Link>
        </div>
      </div>
    );
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword !== confirm) {
      setError('비밀번호가 일치하지 않습니다.');
      return;
    }
    if (newPassword.length < 8) {
      setError('비밀번호는 최소 8자 이상이어야 합니다.');
      return;
    }

    setLoading(true);
    try {
      await axios.post(
        '/api/auth/reset-password',
        { token, new_password: newPassword },
        { timeout: 10000 },
      );
      navigate('/login', { state: { message: '비밀번호가 재설정되었습니다. 새 비밀번호로 로그인해 주세요.' } });
    } catch (err) {
      setError(err.response?.data?.detail || '재설정에 실패했습니다. 링크가 만료되었을 수 있습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h1 className="auth-title">News Curator</h1>
        <h2 className="auth-subtitle">새 비밀번호 설정</h2>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="new-password">새 비밀번호</label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="8자 이상"
              required
              autoFocus
            />
          </div>

          <div className="auth-field">
            <label htmlFor="confirm-password">새 비밀번호 확인</label>
            <input
              id="confirm-password"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="비밀번호 재입력"
              required
            />
          </div>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button type="submit" className="auth-btn" disabled={loading}>
            {loading ? '변경 중...' : '비밀번호 재설정'}
          </button>
        </form>

        <Link to="/login" className="auth-back-link">← 로그인으로 돌아가기</Link>
      </div>
    </div>
  );
}
