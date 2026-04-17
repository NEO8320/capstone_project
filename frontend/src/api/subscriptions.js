/**
 * 구독 API 호출 모듈
 */

import api from './client';

/** GET /subscriptions — 내 구독 목록 조회 */
export const fetchSubscriptions = () => api.get('/subscriptions');

/** POST /subscriptions — 구독 추가 */
export const addSubscription = (targetType, targetName) =>
  api.post('/subscriptions', { target_type: targetType, target_name: targetName });

/** DELETE /subscriptions/{id} — 구독 해제 */
export const removeSubscription = (subId) =>
  api.delete(`/subscriptions/${subId}`);
