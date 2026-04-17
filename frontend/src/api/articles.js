/**
 * 기사 상세 API 호출 모듈
 */

import api from './client';

/** GET /articles/{url} — 기사 상세 조회 (구독 여부 포함) */
export const fetchArticleDetail = (articleUrl) =>
  api.get(`/articles/${encodeURIComponent(articleUrl)}`);
