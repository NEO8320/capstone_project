/**
 * Toast — Undo 토스트 메시지 컴포넌트
 * =====================================
 *
 * 관심없음 클릭 시 하단에 5초간 표시되며,
 * '실행취소' 버튼 클릭 시 관심없음을 즉시 취소한다.
 *
 * Props:
 *   message   : 토스트에 표시할 메시지
 *   onUndo    : 실행취소 버튼 클릭 콜백
 *   duration  : 표시 시간 (ms, 기본 5000)
 *   onClose   : 토스트 닫힘 콜백 (타이머 만료 또는 Undo 후)
 */

import { useEffect, useState } from 'react';
import './Toast.css';

export default function Toast({ message, onUndo, duration = 5000, onClose }) {
  const [visible, setVisible] = useState(true);
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    // 프로그레스 바 애니메이션 (5초 동안 100→0)
    const startTime = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, 100 - (elapsed / duration) * 100);
      setProgress(remaining);
    }, 50);

    // 5초 후 자동 닫힘
    const timer = setTimeout(() => {
      setVisible(false);
      onClose?.();
    }, duration);

    return () => {
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, [duration, onClose]);

  const handleUndo = () => {
    setVisible(false);
    onUndo?.();
    onClose?.();
  };

  if (!visible) return null;

  return (
    <div className="toast" role="alert" aria-live="assertive">
      <span className="toast__message">{message}</span>
      <button
        className="toast__undo"
        onClick={handleUndo}
        aria-label="실행취소"
      >
        실행취소
      </button>
      {/* 남은 시간 프로그레스 바 */}
      <div
        className="toast__progress"
        style={{ width: `${progress}%` }}
        aria-hidden="true"
      />
    </div>
  );
}
