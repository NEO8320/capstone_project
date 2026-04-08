/**
 * Settings — 접근성 설정 컴포넌트 (글자 크기 4단계)
 * ==================================================
 *
 * 노년층 배려를 위해 CSS 커스텀 속성(--font-size-multiplier)을
 * 활용한 전체 UI 글자 크기 조정 기능.
 *
 * 4단계:
 *   0 = 소   (×0.85) — 컴팩트한 표시
 *   1 = 중   (×1.00) — 기본값
 *   2 = 대   (×1.20) — 넓은 가독성
 *   3 = 특대 (×1.45) — 노년층/저시력자 배려
 *
 * localStorage에 'fontSizeLevel' 키로 저장하여
 * 브라우저 재방문 시에도 설정이 유지된다.
 */

import { useEffect, useState } from 'react';
import './Settings.css';

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
  const [fontLevel, setFontLevel] = useState(getStoredFontLevel);

  // 컴포넌트 마운트 시 저장된 설정 적용
  useEffect(() => {
    applyFontLevel(fontLevel);
  }, [fontLevel]);

  const handleChange = (level) => {
    setFontLevel(level);
    applyFontLevel(level);
  };

  return (
    <div className="settings" role="region" aria-label="접근성 설정">
      <h2 className="section-title">접근성 설정</h2>

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
              onClick={() => handleChange(config.level)}
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

        {/* 현재 선택 안내 */}
        <p className="settings__current" aria-live="polite">
          현재: <strong>{FONT_SIZE_LEVELS[fontLevel].label}</strong> (
          {FONT_SIZE_LEVELS[fontLevel].description})
        </p>
      </div>
    </div>
  );
}
