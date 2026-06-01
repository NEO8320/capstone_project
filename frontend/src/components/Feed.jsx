/**
 * Feed 메인 피드 컴포넌트 (구독 트랙 + 추천 트랙 분리)
 * =========================================================
 *
 * 레이아웃:
 *   [구독 트랙]  구독 언론사/기자 최신 기사 (구독이 없으면 숨김)
 *   (최대 10건, 점수 스코어 기반 정렬)
 *
 *   [추천 트랙]  AI 추천 알고리즘 기반 기사
 *   (반응형, 점수 3→2→1열)
 *
 * 관심없음 처리:
 *   1. 카드 즉시 숨김 (optimistic UI)
 *   2. API 호출 (POST /articles/{url}/dislike)
 *   3. 5초간 Undo 토스트 표시
 *   4. Undo 클릭 시 API 호출 (DELETE) + 카드 복원
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { dislikeArticle, fetchFeed, markRead, undoDislike } from '../api/feed';
import ArticleCard from './ArticleCard';
import CategoryFilter from './CategoryFilter';
import Pagination from './Pagination';
import SortFilter, { applySortToItems, weightedShuffle } from './SortFilter';
import Toast from './Toast';
import './Feed.css';

const PAGE_SIZE = 15;  // 추천 트랙 페이지당 기사 수

export default function Feed() {
  const [feed, setFeed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 관심없음 처리 상태 (Undo 토스트용)
  const [hiddenUrls, setHiddenUrls] = useState(new Set());
  const [toast, setToast] = useState(null); // { message, articleUrl }
  // 카테고리 필터
  const [activeCategory, setActiveCategory] = useState('전체');
  // 정렬 기준 (추천순 / 최신순 / 신뢰도순)
  const [activeSort, setActiveSort] = useState('recommended');
  // 페이지네이션 + 읽은 기사 숨김
  const [currentPage, setCurrentPage] = useState(1);
  const [hideRead, setHideRead] = useState(false);
  // 새로고침 시드 — 값이 바뀔 때마다 추천순 가중 셔플이 새 조합을 만든다
  const [refreshSeed, setRefreshSeed] = useState(0);

  // 피드 데이터 로드 (activeCategory 를 서버에 전달하여 카테고리별 DB 필터)
  const loadFeed = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetchFeed(activeCategory);
      const data = response?.data;
      if (data && typeof data === 'object') {
        setFeed(data);
      } else {
        setFeed({ subscription_track: [], recommendation_track: [] });
      }
    } catch (err) {
      // 에러 종류를 구분하여 진단 메시지 제공 (단순 "실패" 메시지로는 원인 파악 불가)
      const status = err?.response?.status;
      const code = err?.code;
      let diagnostic;
      if (code === 'ERR_NETWORK' || code === 'ECONNABORTED' || !err?.response) {
        diagnostic = {
          title: '백엔드 서버에 연결할 수 없습니다',
          detail: 'run_all.bat 가 정상 실행 중인지, 백엔드 cmd 창("News Curator - Backend")이 떠 있는지 확인하세요.',
          action: '.\\diagnose.bat 실행 → 권장 조치 확인',
        };
      } else if (status === 401) {
        // 인터셉터가 /login 으로 리다이렉트해야 정상. 여기 오면 토큰 만료
        diagnostic = {
          title: '인증이 만료되었습니다',
          detail: '다시 로그인이 필요합니다.',
          action: '잠시 후 로그인 페이지로 이동합니다',
        };
      } else if (status === 500) {
        diagnostic = {
          title: '서버 내부 오류 (500)',
          detail: 'DB 연결이 끊겼거나 백엔드가 비정상 상태일 수 있습니다. 백엔드 cmd 창의 "[Startup] DB 초기화" 로그를 확인하세요.',
          action: '.\\diagnose.bat 실행으로 어느 레이어가 깨졌는지 확인',
        };
      } else if (status === 503) {
        diagnostic = {
          title: '서비스를 일시적으로 사용할 수 없습니다 (503)',
          detail: '백엔드가 시작 중이거나 의존 서비스(DB/Redis)가 준비 중입니다.',
          action: '1~2분 후 다시 시도',
        };
      } else {
        diagnostic = {
          title: `피드를 불러오는 데 실패했습니다 ${status ? `(${status})` : ''}`,
          detail: err?.message || '알 수 없는 오류',
          action: '.\\diagnose.bat 로 진단',
        };
      }
      setError(diagnostic);
      console.error('[Feed] 로드 실패:', err);
    } finally {
      setLoading(false);
    }
  }, [activeCategory]);

  // activeCategory 가 바뀌면 loadFeed 가 갱신되어 서버에서 해당 카테고리를 재조회
  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  // 카테고리/정렬/읽음숨김이 바뀌면 1페이지로 리셋
  useEffect(() => {
    setCurrentPage(1);
  }, [activeCategory, activeSort, hideRead]);

  // 기사 읽음 처리 (제목 클릭 시)
  const handleRead = useCallback(async (articleUrl) => {
    try {
      await markRead(articleUrl);
    } catch {
      // 읽음 실패는 UX에 영향 없으므로 조용히 무시
    }
  }, []);

  // 관심없음 처리
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
    setToast({ message: '관심없음 처리했습니다.', articleUrl });
  }, []);

  // 관심없음 Undo
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

  // 로딩/에러 상태 처리
  if (loading) {
    return <div className="loading" aria-live="polite">피드를 불러오는 중...</div>;
  }

  if (error) {
    // error 는 객체 { title, detail, action } 형식이지만, 옛 코드 호환을 위해 문자열도 허용
    const e = typeof error === 'string' ? { title: error } : error;
    return (
      <div className="empty-state" role="alert">
        <p style={{ fontWeight: 600, fontSize: '1.1em' }}>{e.title}</p>
        {e.detail && <p style={{ marginTop: 8, color: '#666', whiteSpace: 'pre-line' }}>{e.detail}</p>}
        {e.action && (
          <p style={{ marginTop: 8, color: '#888', fontSize: '0.9em' }}>
            <strong>다음 단계:</strong> {e.action}
          </p>
        )}
        <button onClick={loadFeed} className="btn-retry" style={{ marginTop: 16 }}>다시 시도</button>
      </div>
    );
  }

  if (!feed) return null;

  // 응답 스키마가 흔들려도 렌더링이 죽지 않도록 안전 배열로 강제
  // (추천 트랙은 sortedRecommendation useMemo 안에서 feed로부터 직접 추출)
  const subscriptionTrack = Array.isArray(feed?.subscription_track)
    ? feed.subscription_track
    : [];

  // 구독 트랙 숨김 필터링 (추천 트랙은 아래 useMemo 파이프라인에서 처리)
  const visibleSubscription = subscriptionTrack.filter((item) => {
    const article = item?.article;
    const url = article?.url;
    return Boolean(article) && (!url || !hiddenUrls.has(url));
  });

  // 추천 트랙 파이프라인: 숨김 제외 → 카테고리 필터 → 읽음 숨김 → 정렬/셔플.
  // useMemo로 묶어 refreshSeed가 바뀔 때만(=새로고침 버튼) 가중 셔플이 새 조합을 만든다.
  // (Math.random 기반이라 매 렌더 재계산되면 스크롤·상태변경 때마다 순서가 바뀌어버림)
  const sortedRecommendation = useMemo(() => {
    const track = Array.isArray(feed?.recommendation_track)
      ? feed.recommendation_track
      : [];
    // 1) 관심없음(optimistic) 숨김 제외
    let items = track.filter((item) => {
      const url = item?.article?.url;
      return Boolean(item?.article) && (!url || !hiddenUrls.has(url));
    });
    // 2) 카테고리 필터 (서버가 이미 하지만 방어적으로 유지)
    if (activeCategory !== '전체') {
      items = items.filter((it) => it?.article?.category === activeCategory);
    }
    // 3) 읽은 기사 숨김 (토글 ON일 때만)
    if (hideRead) items = items.filter((it) => !it?.is_read);
    // 4) 정렬: '추천순'은 점수 가중 셔플(새로고침마다 다른 조합), 그 외는 결정적 정렬
    if (activeSort === 'recommended') {
      return weightedShuffle(applySortToItems(items, 'recommended'));
    }
    return applySortToItems(items, activeSort);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feed, hiddenUrls, activeCategory, hideRead, activeSort, refreshSeed]);

  // 페이지네이션: 전체 페이지 수 + 현재 페이지 슬라이스
  const totalPages = Math.max(1, Math.ceil(sortedRecommendation.length / PAGE_SIZE));
  const safePage = Math.min(currentPage, totalPages);  // 데이터 줄어들어 범위 초과 시 보정
  const pagedRecommendation = sortedRecommendation.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  // 페이지 변경 핸들러 (변경 후 추천 섹션 상단으로 스크롤)
  const handlePageChange = (page) => {
    setCurrentPage(page);
    const sec = document.getElementById('rec-section');
    if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // 새로고침: 서버 재요청 + (추천순이면) 가중 셔플 재계산 + 1페이지로
  const handleRefresh = () => {
    setRefreshSeed((s) => s + 1);   // sortedRecommendation useMemo 재계산 트리거
    setCurrentPage(1);
    loadFeed();                      // 캐시 만료 시 최신 데이터 반영
  };

  return (
    <div className="feed">
      {/* ── 카테고리 필터 탭 ── */}
      <CategoryFilter
        categories={['전체', '정치', '경제', '사회', 'IT·과학', '생활·문화', '세계', '연예', '스포츠']}
        active={activeCategory}
        onChange={setActiveCategory}
      />

      {/* ── 정렬 기준 + 새로고침 + 읽은 기사 숨김 토글 (한 줄) ── */}
      <div className="feed__controls">
        <SortFilter active={activeSort} onChange={setActiveSort} />
        <div className="feed__controls-right">
          <button
            type="button"
            className="feed__refresh"
            onClick={handleRefresh}
            title={activeSort === 'recommended'
              ? '새로고침 — 추천 상위 기사들을 다시 섞어 보여줍니다'
              : '새로고침 — 최신 기사를 다시 불러옵니다'}
            aria-label="피드 새로고침"
          >
            ↻ 새로고침
          </button>
          <button
            type="button"
            className={`feed__hide-read ${hideRead ? 'feed__hide-read--active' : ''}`}
            onClick={() => setHideRead((v) => !v)}
            aria-pressed={hideRead}
          >
            {hideRead ? '✓ 읽은 기사 숨김' : '읽은 기사 숨기기'}
          </button>
        </div>
      </div>

      {/* ── 구독 트랙 (상단) — 가로 스크롤 ── */}
      {visibleSubscription.length > 0 && (
        <section className="feed__section" aria-label="구독 기사">
          <h2 className="section-title">구독중인 언론사</h2>
          <div className="card-scroll">
            {visibleSubscription.map((item, index) => (
              <ArticleCard
                key={item?.article?.url || item?.article?.id || `sub-${index}`}
                item={item}
                onDislike={handleDislike}
                onRead={handleRead}
              />
            ))}
          </div>
        </section>
      )}

      {/* ── 추천 트랙 (하단) — 그리드 + 카테고리 필터 + 정렬 + 페이지네이션 ── */}
      <section className="feed__section" id="rec-section" aria-label="추천 기사">
        <h2 className="section-title">맞춤 추천 기사</h2>
        {sortedRecommendation.length > 0 ? (
          <>
            <div className="card-grid">
              {pagedRecommendation.map((item, index) => (
                <ArticleCard
                  key={item?.article?.url || item?.article?.id || `rec-${index}`}
                  item={item}
                  onDislike={handleDislike}
                  onRead={handleRead}
                />
              ))}
            </div>
            <Pagination
              currentPage={safePage}
              totalPages={totalPages}
              onChange={handlePageChange}
            />
          </>
        ) : (
          <div className="empty-state">
            {hideRead
              ? '표시할 기사가 없습니다. (읽은 기사 숨김이 켜져 있어요)'
              : activeCategory === '전체'
                ? '추천할 기사가 없습니다. 관심 카테고리를 설정해 보세요.'
                : `'${activeCategory}' 카테고리 기사가 없습니다.`}
          </div>
        )}
      </section>

      {/* ── Undo 토스트 (하단 고정, 5초) ── */}
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
