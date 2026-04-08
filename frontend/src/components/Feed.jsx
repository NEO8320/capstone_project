/**
 * Feed — 메인 피드 컴포넌트 (구독 트랙 + 추천 트랙 분리)
 * =========================================================
 *
 * 레이아웃:
 *   ┌─────────────────────────────────────────┐
 *   │  [구독 트랙]  구독 언론사/기자 최신 기사  │ ← 구독이 없으면 숨김
 *   │  (최대 10건, 수평 스크롤 가능)            │
 *   ├─────────────────────────────────────────┤
 *   │  [추천 트랙]  AI 추천 스코어 순서         │
 *   │  (반응형 그리드: 3열/2열/1열)             │
 *   └─────────────────────────────────────────┘
 *
 * 관심없음 처리:
 *   1. 카드 즉시 숨김 (optimistic UI)
 *   2. API 호출 (POST /articles/{url}/dislike)
 *   3. 5초간 Undo 토스트 표시
 *   4. Undo 클릭 시 API 호출 (DELETE) + 카드 복원
 */

import { useCallback, useEffect, useState } from 'react';
import { dislikeArticle, fetchFeed, markRead, undoDislike } from '../api/feed';
import ArticleCard from './ArticleCard';
import Toast from './Toast';
import './Feed.css';

export default function Feed() {
  const [feed, setFeed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 관심없음 처리 상태 (Undo 토스트용)
  const [hiddenUrls, setHiddenUrls] = useState(new Set());
  const [toast, setToast] = useState(null); // { message, articleUrl }

  // ── 피드 데이터 로드 ──
  const loadFeed = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const { data } = await fetchFeed();
      setFeed(data);
    } catch (err) {
      setError('피드를 불러오는 데 실패했습니다.');
      console.error('[Feed] 로드 실패:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  // ── 기사 읽음 처리 (제목 클릭 시) ──
  const handleRead = useCallback(async (articleUrl) => {
    try {
      await markRead(articleUrl);
    } catch {
      // 읽음 실패는 UX에 영향 없으므로 조용히 무시
    }
  }, []);

  // ── 관심없음 처리 ──
  const handleDislike = useCallback(async (articleUrl) => {
    // 1) Optimistic UI: 즉시 카드 숨김
    setHiddenUrls((prev) => new Set(prev).add(articleUrl));

    // 2) API 호출
    try {
      await dislikeArticle(articleUrl);
    } catch (err) {
      console.error('[Feed] 관심없음 실패:', err);
      // API 실패 시 카드 복원
      setHiddenUrls((prev) => {
        const next = new Set(prev);
        next.delete(articleUrl);
        return next;
      });
      return;
    }

    // 3) 5초 Undo 토스트 표시
    setToast({ message: '관심없음 처리되었습니다.', articleUrl });
  }, []);

  // ── 관심없음 Undo ──
  const handleUndo = useCallback(async (articleUrl) => {
    try {
      await undoDislike(articleUrl);
      // 카드 복원
      setHiddenUrls((prev) => {
        const next = new Set(prev);
        next.delete(articleUrl);
        return next;
      });
    } catch (err) {
      console.error('[Feed] Undo 실패:', err);
    }
  }, []);

  // ── 로딩/에러 상태 ──
  if (loading) {
    return <div className="loading" aria-live="polite">피드를 불러오는 중...</div>;
  }

  if (error) {
    return (
      <div className="empty-state" role="alert">
        <p>{error}</p>
        <button onClick={loadFeed} className="btn-retry">다시 시도</button>
      </div>
    );
  }

  if (!feed) return null;

  // 숨겨진 기사 필터링
  const visibleSubscription = feed.subscription_track.filter(
    (item) => !hiddenUrls.has(item.article.url)
  );
  const visibleRecommendation = feed.recommendation_track.filter(
    (item) => !hiddenUrls.has(item.article.url)
  );

  return (
    <div className="feed">
      {/* ════════════════════════════════════
       * 구독 트랙 (상단) — 구독이 있을 때만 표시
       * ════════════════════════════════════ */}
      {visibleSubscription.length > 0 && (
        <section className="feed__section" aria-label="구독 기사">
          <h2 className="section-title">구독 트랙</h2>
          <div className="card-grid">
            {visibleSubscription.map((item) => (
              <ArticleCard
                key={item.article.url}
                item={item}
                onDislike={handleDislike}
                onRead={handleRead}
              />
            ))}
          </div>
        </section>
      )}

      {/* ════════════════════════════════════
       * 추천 트랙 (하단) — AI 추천 스코어 순서
       * ════════════════════════════════════ */}
      <section className="feed__section" aria-label="추천 기사">
        <h2 className="section-title">추천 트랙</h2>
        {visibleRecommendation.length > 0 ? (
          <div className="card-grid">
            {visibleRecommendation.map((item) => (
              <ArticleCard
                key={item.article.url}
                item={item}
                onDislike={handleDislike}
                onRead={handleRead}
              />
            ))}
          </div>
        ) : (
          <div className="empty-state">
            추천할 기사가 없습니다. 관심 카테고리를 설정해 보세요.
          </div>
        )}
      </section>

      {/* ════════════════════════════════════
       * Undo 토스트 (하단 고정, 5초)
       * ════════════════════════════════════ */}
      {toast && (
        <Toast
          message={toast.message}
          onUndo={() => handleUndo(toast.articleUrl)}
          duration={5000}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}
