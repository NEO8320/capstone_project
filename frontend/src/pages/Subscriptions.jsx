/**
 * Subscriptions — 구독 설정 페이지
 * ====================================
 *
 * 현재 구독 중인 언론사/기자 목록을 표시하고 개별 해제 가능.
 * 구독 추가는 기사 상세 페이지에서 할 수 있다.
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchSubscriptions, removeSubscription } from '../api/subscriptions';
import './Subscriptions.css';

export default function Subscriptions() {
  const [subs, setSubs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadSubs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const { data } = await fetchSubscriptions();
      setSubs(data);
    } catch {
      setError('구독 목록을 불러오는 데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubs();
  }, [loadSubs]);

  const handleUnsubscribe = useCallback(async (subId) => {
    // 낙관적 UI: 즉시 제거
    setSubs((prev) => prev.filter((s) => s.id !== subId));
    try {
      await removeSubscription(subId);
    } catch {
      // 실패 시 목록 다시 로드
      loadSubs();
    }
  }, [loadSubs]);

  if (loading) {
    return <div className="subs-loading" aria-live="polite">구독 목록을 불러오는 중...</div>;
  }

  if (error) {
    return (
      <div className="subs-error" role="alert">
        <p>{error}</p>
        <button onClick={loadSubs} className="btn-retry">다시 시도</button>
      </div>
    );
  }

  const pressList = (subs || []).filter((s) => s.target_type === 'press');
  const journalistList = (subs || []).filter((s) => s.target_type === 'journalist');

  return (
    <div className="subscriptions" role="region" aria-label="구독 설정">
      <h2 className="section-title">구독 설정</h2>
      <p className="subs__hint">
        기사 상세 페이지에서 언론사와 기자를 구독할 수 있습니다.
      </p>

      {/* ── 언론사 구독 목록 ── */}
      <section className="subs__section">
        <h3 className="subs__section-title">구독 언론사</h3>
        {pressList.length === 0 ? (
          <p className="subs__empty">구독 중인 언론사가 없습니다.</p>
        ) : (
          <ul className="subs__list">
            {pressList.map((sub) => (
              <li key={sub.id} className="subs__item">
                <span className="subs__item-name">{sub.target_name}</span>
                <button
                  className="btn-unsub"
                  onClick={() => handleUnsubscribe(sub.id)}
                  aria-label={`${sub.target_name} 구독 해제`}
                >
                  해제
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── 기자 구독 목록 ── */}
      <section className="subs__section">
        <h3 className="subs__section-title">구독 기자</h3>
        {journalistList.length === 0 ? (
          <p className="subs__empty">구독 중인 기자가 없습니다.</p>
        ) : (
          <ul className="subs__list">
            {journalistList.map((sub) => (
              <li key={sub.id} className="subs__item">
                <span className="subs__item-name">{sub.target_name} 기자</span>
                <button
                  className="btn-unsub"
                  onClick={() => handleUnsubscribe(sub.id)}
                  aria-label={`${sub.target_name} 기자 구독 해제`}
                >
                  해제
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
