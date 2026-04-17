/**
 * 사용자 프로필 API 호출 모듈
 */

import api from './client';

/** GET /users/me — 내 프로필 조회 */
export const fetchMe = () => api.get('/users/me');

/** PATCH /users/me — 프로필 업데이트 (관심 카테고리, 글자 크기) */
export const updateMe = (data) => api.patch('/users/me', data);
