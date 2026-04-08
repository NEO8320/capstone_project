/**
 * 피드 및 피드백 API 호출 모듈
 */

import api from './client';

/** GET /feed — 개인화 추천 피드 조회 */
export const fetchFeed = () => api.get('/feed');

/** POST /articles/{url}/read — 기사 읽음 처리 */
export const markRead = (articleUrl) =>
  api.post(`/articles/${encodeURIComponent(articleUrl)}/read`);

/** POST /articles/{url}/dislike — 관심없음 처리 */
export const dislikeArticle = (articleUrl) =>
  api.post(`/articles/${encodeURIComponent(articleUrl)}/dislike`);

/** DELETE /articles/{url}/dislike — 관심없음 Undo */
export const undoDislike = (articleUrl) =>
  api.delete(`/articles/${encodeURIComponent(articleUrl)}/dislike`);
