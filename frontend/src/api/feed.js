/**
 * 피드 및 피드백 API 호출 모듈
 */

import api from './client';

/** GET /feed — 개인화 추천 피드 조회
 *  @param {string|null} category - 특정 카테고리 탭 선택 시 해당 카테고리만 서버에서 필터.
 *                                  '전체'(null/undefined)이면 전체 카테고리 추천. */
export const fetchFeed = (category) => {
  const params = category && category !== '전체' ? { category } : {};
  return api.get('/feed', { params });
};

/** POST /articles/{url}/read — 기사 읽음 처리 */
export const markRead = (articleUrl) =>
  api.post(`/articles/${encodeURIComponent(articleUrl)}/read`);

/** POST /articles/{url}/dislike — 관심없음 처리 */
export const dislikeArticle = (articleUrl) =>
  api.post(`/articles/${encodeURIComponent(articleUrl)}/dislike`);

/** POST /v1/feed/dislike/undo — 관심없음 Undo (API-07) */
export const undoDislike = (articleUrl) =>
  api.post('/v1/feed/dislike/undo', { article_id: articleUrl });
