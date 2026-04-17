/**
 * Settings — 설정 컴포넌트
 * ==========================
 *
 * 섹션:
 *   1. 계정 정보 — 이메일(사용자 ID), 이름 표시
 *   2. 관심 카테고리 — 1개 이상 자유 선택, 저장 버튼으로 업데이트
 *   3. 글자 크기 조정 — 4단계 (0=소~3=특대)
 *   4. 테마 설정 — 다크/라이트 모드 전환
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { fetchMe, updateMe } from '../api/users';
import { useTheme } from '../contexts/ThemeContext';
import './Settings.css';

const CATEGORIES = [
  '정치', '경제', '사회', 'IT·과학', '생활·문화', '세계', '연예', '스포츠',
];

const FONT_SIZE_LEVELS = [
  { level: 0, label: '소', multiplier: 0.85, description: '작은 글자' },
  { level: 1, label: '중', multiplier: 1.0, description: '기본 크기' },
  { level: 2, label: '대', multiplier: 1.2, description: '큰 글자' },
  { level: 3, label: '특대', multiplier: 1.45, description: '매우 큰 글자' },
];

/** localStorage에서 글자 크기 레벨을 읽는다 (기본값: 1=중) */
export function getStoredFontLevel() {
  const stored = localStorage.getItem('fontSizeLevel');
  const level = stored !== null ? parseInt(stored, 10) : 1;
  return level >= 0 && level <= 3 ? level : 1;
}

/** 글자 크기 레벨을 CSS 변수와 localStorage에 적용한다 */
export function applyFontLevel(level) {
  const config = FONT_SIZE_LEVELS[level] || FONT_SIZE_LEVELS[1];
  document.documentElement.style.setProperty(
    '--font-size-multiplier',
    String(config.multiplier)
  );
  localStorage.setItem('fontSizeLevel', String(level));
}

export default function Settings() {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const [fontLevel, setFontLevel] = useState(getStoredFontLevel);

  // 계정 정보
  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(true);

  // 관심 카테고리 편집
  const [selectedCats, setSelectedCats] = useState([]);
  const [catSaving, setCatSaving] = useState(false);
  const [catSaved, setCatSaved] = useState(false);

  // 비밀번호 변경
  const [pwForm, setPwForm] = useState({ current: '', next: '', confirm: '' });
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState(false);
  const [pwSaving, setPwSaving] = useState(false);

  // 계정 탈퇴
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);

  // 컴포넌트 마운트 시 저장된 글자 크기 + 프로필 로드
  useEffect(() => {
    applyFontLevel(fontLevel);
  }, [fontLevel]);

  useEffect(() => {
    fetchMe()
      .then(({ data }) => {
        setProfile(data);
        setSelectedCats(data.interest_categories || []);
      })
      .catch(() => {})
      .finally(() => setProfileLoading(false));
  }, []);

  const handleFontChange = (level) => {
    setFontLevel(level);
    applyFontLevel(level);
  };

  // ── 카테고리 토글 (자유 선택, 1개 이상 필수) ──
  const handleCatToggle = (cat) => {
    setCatSaved(false);
    setSelectedCats((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  // ── 관심 카테고리 저장 ──
  // ── 비밀번호 변경 ──
  const handlePwChange = async (e) => {
    e.preventDefault();
    setPwError('');
    setPwSuccess(false);
    if (pwForm.next !== pwForm.confirm) {
      setPwError('새 비밀번호가 일치하지 않습니다.');
      return;
    }
    if (pwForm.next.length < 8) {
      setPwError('새 비밀번호는 최소 8자 이상이어야 합니다.');
      return;
    }
    setPwSaving(true);
    try {
      await api.patch('/users/me/password', {
        current_password: pwForm.current,
        new_password: pwForm.next,
      });
      setPwSuccess(true);
      setPwForm({ current: '', next: '', confirm: '' });
    } catch (err) {
      setPwError(err.response?.data?.detail || '비밀번호 변경에 실패했습니다.');
    } finally {
      setPwSaving(false);
    }
  };

  // ── 계정 탈퇴 ──
  const handleDeleteAccount = async () => {
    setDeleteError('');
    if (!profile || deleteConfirm !== profile.email) {
      setDeleteError('이메일을 정확히 입력해 주세요.');
      return;
    }
    setDeleteLoading(true);
    try {
      await api.delete('/users/me');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      navigate('/register');
    } catch (err) {
      setDeleteError(err.response?.data?.detail || '탈퇴 처리에 실패했습니다.');
      setDeleteLoading(false);
    }
  };

  const handleSaveCats = async () => {
    if (selectedCats.length < 1) return;
    setCatSaving(true);
    try {
      const { data } = await updateMe({ interest_categories: selectedCats });
      setProfile(data);
      setCatSaved(true);
    } catch {
      // 저장 실패 — 사용자에게 표시 없이 조용히 처리
    } finally {
      setCatSaving(false);
    }
  };

  return (
    <div className="settings" role="region" aria-label="설정">
      <h2 className="section-title">설정</h2>

      {/* ════════════════════════════════
       * 계정 정보
       * ════════════════════════════════ */}
      <div className="settings__group">
        <h3 className="settings__label">계정 정보</h3>
        {profileLoading ? (
          <p className="settings__description">불러오는 중...</p>
        ) : profile ? (
          <dl className="settings__profile">
            <div className="settings__profile-row">
              <dt>이메일 (사용자 ID)</dt>
              <dd>{profile.email}</dd>
            </div>
            <div className="settings__profile-row">
              <dt>이름</dt>
              <dd>{profile.name}</dd>
            </div>
          </dl>
        ) : (
          <p className="settings__description">프로필을 불러올 수 없습니다.</p>
        )}
      </div>

      {/* ════════════════════════════════
       * 관심 카테고리
       * ════════════════════════════════ */}
      <div className="settings__group">
        <h3 className="settings__label" id="cat-label">관심 카테고리</h3>
        <p className="settings__description">
          1개 이상 자유롭게 선택하세요. 많이 선택할수록 더 정확한 추천을 받을 수 있습니다.
        </p>
        <div className="cat-selector" role="group" aria-labelledby="cat-label">
          {CATEGORIES.map((cat) => {
            const active = selectedCats.includes(cat);
            return (
              <button
                key={cat}
                className={`cat-btn ${active ? 'cat-btn--active' : ''}`}
                onClick={() => handleCatToggle(cat)}
                aria-pressed={active}
              >
                {cat}
              </button>
            );
          })}
        </div>
        <div className="settings__cat-footer">
          <span className="settings__cat-count">
            {selectedCats.length}개 선택됨
          </span>
          <button
            className="btn-save-cats"
            onClick={handleSaveCats}
            disabled={selectedCats.length < 1 || catSaving}
          >
            {catSaving ? '저장 중...' : catSaved ? '저장됨 ✓' : '저장'}
          </button>
        </div>
      </div>

      {/* ════════════════════════════════
       * 글자 크기
       * ════════════════════════════════ */}
      <div className="settings__group">
        <h3 className="settings__label" id="font-size-label">
          글자 크기 조정
        </h3>
        <p className="settings__description">
          화면의 모든 텍스트 크기를 한 번에 조정합니다.
          설정은 자동으로 저장됩니다.
        </p>

        <div
          className="font-size-selector"
          role="radiogroup"
          aria-labelledby="font-size-label"
        >
          {FONT_SIZE_LEVELS.map((config) => (
            <button
              key={config.level}
              className={`font-size-btn ${
                fontLevel === config.level ? 'font-size-btn--active' : ''
              }`}
              onClick={() => handleFontChange(config.level)}
              role="radio"
              aria-checked={fontLevel === config.level}
              aria-label={`글자 크기 ${config.label} (${config.description})`}
            >
              <span
                className="font-size-btn__preview"
                style={{ fontSize: `${16 * config.multiplier}px` }}
              >
                가
              </span>
              <span className="font-size-btn__label">{config.label}</span>
            </button>
          ))}
        </div>

        <p className="settings__current" aria-live="polite">
          현재: <strong>{FONT_SIZE_LEVELS[fontLevel].label}</strong> (
          {FONT_SIZE_LEVELS[fontLevel].description})
        </p>
      </div>

      {/* ════════════════════════════════
       * 테마 설정
       * ════════════════════════════════ */}
      <div className="settings__group">
        <h3 className="settings__label">테마 설정</h3>
        <p className="settings__description">
          다크 모드와 라이트 모드를 전환합니다. 설정은 자동으로 저장됩니다.
        </p>
        <div className="settings__theme-row">
          <button
            className={`theme-btn ${theme === 'dark' ? 'theme-btn--active' : ''}`}
            onClick={() => theme !== 'dark' && toggleTheme()}
            aria-pressed={theme === 'dark'}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
            다크 모드
          </button>
          <button
            className={`theme-btn ${theme === 'light' ? 'theme-btn--active' : ''}`}
            onClick={() => theme !== 'light' && toggleTheme()}
            aria-pressed={theme === 'light'}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
            라이트 모드
          </button>
        </div>
      </div>

      {/* ════════════════════════════════
       * 비밀번호 변경
       * ════════════════════════════════ */}
      <div className="settings__group">
        <h3 className="settings__label">비밀번호 변경</h3>
        <form className="settings__pw-form" onSubmit={handlePwChange}>
          <input
            type="password"
            placeholder="현재 비밀번호"
            value={pwForm.current}
            onChange={(e) => setPwForm({ ...pwForm, current: e.target.value })}
            className="settings__pw-input"
            required
          />
          <input
            type="password"
            placeholder="새 비밀번호 (8자 이상)"
            value={pwForm.next}
            onChange={(e) => { setPwForm({ ...pwForm, next: e.target.value }); setPwSuccess(false); }}
            className="settings__pw-input"
            required
          />
          <input
            type="password"
            placeholder="새 비밀번호 확인"
            value={pwForm.confirm}
            onChange={(e) => { setPwForm({ ...pwForm, confirm: e.target.value }); setPwSuccess(false); }}
            className="settings__pw-input"
            required
          />
          {pwError && <p className="settings__error" role="alert">{pwError}</p>}
          {pwSuccess && <p className="settings__success" aria-live="polite">비밀번호가 변경되었습니다.</p>}
          <button
            type="submit"
            className="btn-save-cats"
            disabled={pwSaving}
            style={{ alignSelf: 'flex-start' }}
          >
            {pwSaving ? '변경 중...' : '비밀번호 변경'}
          </button>
        </form>
      </div>

      {/* ════════════════════════════════
       * 계정 탈퇴 (위험 구역)
       * ════════════════════════════════ */}
      <div className="settings__group settings__danger-zone">
        <h3 className="settings__label settings__danger-title">계정 탈퇴</h3>
        <p className="settings__description">
          탈퇴하면 모든 데이터(구독, 읽음 기록, 관심없음 기록)가 <strong>즉시 삭제</strong>되며
          복구할 수 없습니다.
          확인을 위해 이메일 주소를 입력해 주세요.
        </p>
        {profile && (
          <div className="settings__delete-row">
            <input
              type="email"
              placeholder={profile.email}
              value={deleteConfirm}
              onChange={(e) => { setDeleteConfirm(e.target.value); setDeleteError(''); }}
              className="settings__pw-input"
            />
            {deleteError && <p className="settings__error" role="alert">{deleteError}</p>}
            <button
              className="btn-delete-account"
              onClick={handleDeleteAccount}
              disabled={deleteLoading || deleteConfirm !== profile.email}
            >
              {deleteLoading ? '처리 중...' : '계정 탈퇴'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
