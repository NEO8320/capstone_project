/**
 * ArticleDetail — 기사 상세 페이지
 * ===================================
 *
 * URL: /article?url=<encodedArticleUrl>
 *
 * 표시 항목:
 *   - 카테고리 + 언론사
 *   - 발행 시간 + 제목
 *   - 3줄 요약
 *   - 기사 본문 (단락 분리 렌더링)
 *   - 신뢰도 점수 시각화 (점수 + 컬러 바)
 *   - 언론사/기자 구독·해제 버튼
 *   - 관심없음 버튼
 *   - 원문 보기 버튼 (새 탭)
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchArticleDetail } from '../api/articles';
import { dislikeArticle, markRead } from '../api/feed';
import { addSubscription, removeSubscription } from '../api/subscriptions';
import CredibilityChart from '../components/CredibilityChart';
import './ArticleDetail.css';

/** 발행 시간 포맷 */
function formatDate(dateString) {
  return new Date(dateString).toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function ArticleDetail() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const articleUrl = searchParams.get('url') || '';

  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 구독 상태 (낙관적 UI)
  const [pressSubscribed, setPressSubscribed] = useState(false);
  const [pressSubId, setPressSubId] = useState(null);
  const [journalistSubscribed, setJournalistSubscribed] = useState(false);
  const [journalistSubId, setJournalistSubId] = useState(null);

  const [disliked, setDisliked] = useState(false);

  // ── 기사 로드 ──
  useEffect(() => {
    if (!articleUrl) {
      navigate('/feed', { replace: true });
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const { data } = await fetchArticleDetail(articleUrl);
        if (cancelled) return;
        setArticle(data);
        setPressSubscribed(data.press_subscribed);
        setPressSubId(data.press_sub_id);
        setJournalistSubscribed(data.journalist_subscribed);
        setJournalistSubId(data.journalist_sub_id);
        // 읽음 처리
        await markRead(articleUrl).catch(() => {});
      } catch {
        if (!cancelled) setError('기사를 불러오는 데 실패했습니다.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [articleUrl, navigate]);

  // ── 언론사 구독 토글 ──
  const handlePressSubscribe = useCallback(async () => {
    if (!article) return;
    if (pressSubscribed && pressSubId) {
      await removeSubscription(pressSubId);
      setPressSubscribed(false);
      setPressSubId(null);
    } else {
      const { data } = await addSubscription('press', article.press);
      setPressSubscribed(true);
      setPressSubId(data.id);
    }
  }, [article, pressSubscribed, pressSubId]);

  // ── 기자 구독 토글 ──
  const handleJournalistSubscribe = useCallback(async () => {
    if (!article?.journalist) return;
    if (journalistSubscribed && journalistSubId) {
      await removeSubscription(journalistSubId);
      setJournalistSubscribed(false);
      setJournalistSubId(null);
    } else {
      const { data } = await addSubscription('journalist', article.journalist);
      setJournalistSubscribed(true);
      setJournalistSubId(data.id);
    }
  }, [article, journalistSubscribed, journalistSubId]);

  // ── 관심없음 ──
  const handleDislike = useCallback(async () => {
    if (!article) return;
    await dislikeArticle(article.url).catch(() => {});
    setDisliked(true);
  }, [article]);

  // ── 상태별 렌더링 ──
  if (loading) {
    return <div className="detail-loading" aria-live="polite">기사를 불러오는 중...</div>;
  }

  if (error || !article) {
    return (
      <div className="detail-error" role="alert">
        <p>{error || '기사를 찾을 수 없습니다.'}</p>
        <button className="btn-back" onClick={() => navigate(-1)}>← 뒤로가기</button>
      </div>
    );
  }

  return (
    <div className="article-detail">
      {/* ── 뒤로가기 ── */}
      <button className="btn-back" onClick={() => navigate(-1)}>
        ← 뒤로가기
      </button>

      {/* ── 카테고리 + 언론사 ── */}
      <div className="detail__meta-top">
        <span className="detail__category">{article.category}</span>
        <span className="detail__press">{article.press}</span>
        {article.journalist && (
          <span className="detail__journalist">{article.journalist} 기자</span>
        )}
      </div>

      {/* ── 발행 시간 ── */}
      <time className="detail__date" dateTime={article.published_at}>
        {formatDate(article.published_at)}
      </time>

      {/* ── 제목 ── */}
      <h1 className="detail__title">{article.title}</h1>

      {/* ── 3줄 요약 ── */}
      <section className="detail__summary-box" aria-label="AI 요약">
        <h2 className="detail__summary-label">AI 3줄 요약</h2>
        <p className="detail__summary">{article.summary}</p>
      </section>

      {/* ── 기사 본문 (단락 분리 렌더링) ── */}
      {article.body && (
        <section className="detail__body-box" aria-label="기사 본문">
          <h2 className="detail__body-label">기사 본문</h2>
          <div className="detail__body">
            {article.body
              .split(/\n+/)
              .map((para) => para.trim())
              .filter((para) => para.length > 0)
              .map((para, idx) => (
                <p key={idx} className="detail__body-paragraph">
                  {para}
                </p>
              ))}
          </div>
        </section>
      )}

      {/* ── 신뢰도 4-지표 분석 차트 ── */}
      <CredibilityChart article={article} />

      {/* ── 구독 버튼 ── */}
      <section className="detail__subscribe-box" aria-label="구독 설정">
        <button
          className={`btn-subscribe ${pressSubscribed ? 'btn-subscribe--active' : ''}`}
          onClick={handlePressSubscribe}
        >
          {pressSubscribed ? `✓ ${article.press} 구독 중` : `${article.press} 구독`}
        </button>
        {article.journalist && (
          <button
            className={`btn-subscribe ${journalistSubscribed ? 'btn-subscribe--active' : ''}`}
            onClick={handleJournalistSubscribe}
          >
            {journalistSubscribed
              ? `✓ ${article.journalist} 기자 구독 중`
              : `${article.journalist} 기자 구독`}
          </button>
        )}
      </section>

      {/* ── 하단 액션 버튼 ── */}
      <div className="detail__actions">
        {!disliked ? (
          <button className="btn-dislike" onClick={handleDislike}>
            관심없음
          </button>
        ) : (
          <span className="detail__disliked-msg">관심없음 처리되었습니다.</span>
        )}
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-original"
        >
          원문 보기 →
        </a>
      </div>
    </div>
  );
}
