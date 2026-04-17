/**
 * Axios 인스턴스 및 JWT 인터셉터 설정
 * =====================================
 *
 * - baseURL: Vite proxy를 통해 /api → localhost:8000/api로 전달
 * - 요청 인터셉터: localStorage의 access_token을 Authorization 헤더에 자동 첨부
 * - 응답 인터셉터: 401 응답 시 refresh_token으로 access_token 갱신 시도
 *   단, PUBLIC_PATHS에 해당하는 요청은 갱신 시도 없이 즉시 에러 반환
 */

import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,   // 30초 — Ko-SBERT 첫 로딩 시간 고려
  headers: { 'Content-Type': 'application/json' },
});

/* ── 인증 불필요 공개 경로 화이트리스트 (IFR-I01) ── */
const PUBLIC_PATHS = [
  '/auth/login',
  '/auth/register',
  '/auth/refresh',
  '/auth/forgot-password',
  '/auth/reset-password',
  '/v1/auth/login',
  '/v1/auth/register',
  '/v1/auth/refresh',
];

/* ──────────────────────────────────────────
 * 요청 인터셉터: Access Token 자동 첨부
 * ────────────────────────────────────────── */
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

/* ──────────────────────────────────────────
 * 응답 인터셉터: 401 시 토큰 갱신 (Refresh)
 * 공개 경로는 갱신 시도 없이 즉시 에러 반환
 * ────────────────────────────────────────── */

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // 401이 아니면 그대로 반환
    if (error.response?.status !== 401) {
      return Promise.reject(error);
    }

    // 공개 경로 요청은 토큰 갱신 시도 없이 즉시 에러 반환 (무한 루프 방지)
    const requestUrl = originalRequest.url || '';
    const isPublicPath = PUBLIC_PATHS.some((path) => requestUrl.includes(path));
    if (isPublicPath) {
      return Promise.reject(error);
    }

    // _retry 플래그로 무한 재시도 방지
    if (originalRequest._retry) {
      return Promise.reject(error);
    }

    // 이미 갱신 중이면 큐에 대기
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return api(originalRequest);
      });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    const refreshToken = localStorage.getItem('refresh_token');

    if (!refreshToken) {
      processQueue(error);
      isRefreshing = false;
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      return Promise.reject(error);
    }

    try {
      const { data } = await axios.post('/api/auth/refresh', {
        refresh_token: refreshToken,
      });

      const newAccessToken = data.access_token;
      localStorage.setItem('access_token', newAccessToken);

      if (data.refresh_token) {
        localStorage.setItem('refresh_token', data.refresh_token);
      }

      processQueue(null, newAccessToken);

      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
      return api(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError);
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default api;
