/**
 * Axios 인스턴스 및 JWT 인터셉터 설정
 * =====================================
 *
 * - baseURL: Vite proxy를 통해 /api → localhost:8000/api로 전달
 * - 요청 인터셉터: localStorage의 access_token을 Authorization 헤더에 자동 첨부
 * - 응답 인터셉터: 401 응답 시 refresh_token으로 access_token 갱신 시도
 *   갱신 성공 → 원래 요청 재시도
 *   갱신 실패 → 로그인 페이지로 리다이렉트
 */

import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

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
 * ────────────────────────────────────────── */

// 토큰 갱신 중복 방지 플래그
let isRefreshing = false;
// 갱신 대기 중인 요청 큐 (갱신 완료 후 일괄 재시도)
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

    // 401 응답이고, 아직 재시도하지 않은 요청인 경우
    if (error.response?.status === 401 && !originalRequest._retry) {
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
        // Refresh Token 없음 → 로그인 페이지로
        processQueue(error);
        isRefreshing = false;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        // Refresh Token으로 새 Access Token 요청
        const { data } = await axios.post('/api/auth/refresh', {
          refresh_token: refreshToken,
        });

        const newAccessToken = data.access_token;
        localStorage.setItem('access_token', newAccessToken);

        if (data.refresh_token) {
          localStorage.setItem('refresh_token', data.refresh_token);
        }

        // 대기 중인 요청들에 새 토큰 전달
        processQueue(null, newAccessToken);

        // 원래 요청 재시도
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        // 갱신 실패 → 모든 대기 요청 거부 + 로그아웃
        processQueue(refreshError);
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
