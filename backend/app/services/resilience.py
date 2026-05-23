"""
가용성 제어 모듈 (Resilience)
==============================

외부 API 호출의 안정성을 보장하는 세 가지 핵심 패턴을 구현한다:

1. CircuitBreaker (서킷 브레이커)
   - 외부 API(LLM, 네이버 뉴스) 호출이 5회 연속 실패하면 30초간 호출을 차단한다.
   - 상태: CLOSED(정상) → OPEN(차단) → HALF_OPEN(시험 호출)
   - OPEN 상태에서 30초 경과 후 HALF_OPEN으로 전환, 1회 성공 시 CLOSED로 복귀.

2. BackPressureController (백프레셔)
   - 처리 대기 큐 크기를 모니터링하여 크롤링 속도를 자동 제어한다.
   - 큐 100건 초과 → 크롤링 일시 중지 (is_paused=True)
   - 큐 50건 이하 → 크롤링 재개 (is_paused=False)

3. AdaptiveRateController (적응형 수집량 조절)
   - 서버 CPU 사용률에 따라 카테고리당 수집 건수를 동적으로 결정한다.
   - CPU < 50%  → 카테고리당 20건
   - CPU 50~70% → 카테고리당 15건
   - CPU > 70%  → 카테고리당 10건
"""

import asyncio
import time
from enum import Enum

import psutil


# ============================================================
# 서킷 브레이커
# ============================================================
class CircuitState(str, Enum):
    """서킷 브레이커 상태"""
    CLOSED = "closed"        # 정상 — 모든 호출 허용
    OPEN = "open"            # 차단 — 모든 호출 거부 (쿨다운 대기)
    HALF_OPEN = "half_open"  # 시험 — 1회 호출 허용, 성공 시 CLOSED로 복귀


class CircuitBreaker:
    """
    서킷 브레이커 패턴 구현.

    사용법:
        breaker = CircuitBreaker(name="llm_api")

        if not breaker.can_call():
            return  # 서킷 열림, 호출 건너뜀

        try:
            result = await call_external_api()
            breaker.record_success()
        except Exception:
            breaker.record_failure()

    매개변수:
        name             : 서킷 브레이커 식별 이름 (로깅용)
        failure_threshold: 연속 실패 허용 횟수 (기본 5회)
        recovery_timeout : OPEN 상태 유지 시간 (기본 30초)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """현재 서킷 상태를 반환 (OPEN → HALF_OPEN 자동 전환 포함)"""
        if self._state == CircuitState.OPEN:
            # 쿨다운 시간이 지났으면 HALF_OPEN으로 전환
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                print(f"[CircuitBreaker:{self.name}] OPEN -> HALF_OPEN (시험 호출 허용)")
        return self._state

    def can_call(self) -> bool:
        """
        호출 가능 여부를 판단한다.
        - CLOSED / HALF_OPEN: True (호출 허용)
        - OPEN: False (호출 차단)
        """
        current = self.state
        if current == CircuitState.OPEN:
            print(f"[CircuitBreaker:{self.name}] 서킷 OPEN - 호출 차단됨")
            return False
        return True

    async def record_success(self):
        """호출 성공 시 호출. 실패 카운트를 초기화하고 CLOSED 상태로 전환."""
        async with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                print(f"[CircuitBreaker:{self.name}] HALF_OPEN -> CLOSED (정상 복귀)")
            self._state = CircuitState.CLOSED

    async def record_failure(self):
        """
        호출 실패 시 호출.
        연속 실패 횟수가 threshold에 도달하면 OPEN 상태로 전환.
        """
        async with self._lock:
            self._failure_count += 1
            print(
                f"[CircuitBreaker:{self.name}] 실패 "
                f"{self._failure_count}/{self.failure_threshold}"
            )

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                print(
                    f"[CircuitBreaker:{self.name}] CLOSED -> OPEN "
                    f"({self.recovery_timeout}초간 호출 중단)"
                )

    def reset(self):
        """수동 리셋 (테스트/관리용)"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0


# ============================================================
# 백프레셔 컨트롤러
# ============================================================
class BackPressureController:
    """
    백프레셔 패턴 구현.

    처리 대기 큐의 크기를 추적하여 크롤링 속도를 자동 제어한다.
    - 큐 크기 > pause_threshold (100건) → 일시 중지
    - 큐 크기 ≤ resume_threshold (50건) → 재개

    히스테리시스(hysteresis) 설계:
      pause와 resume의 임계값을 다르게 설정하여
      경계값 근처에서 빈번한 on/off 전환(chattering)을 방지한다.

    사용법:
        bp = BackPressureController()

        bp.increment()  # 큐에 작업 추가
        if bp.is_paused:
            await asyncio.sleep(1)  # 중지 상태에서 대기
        bp.decrement()  # 작업 처리 완료
    """

    def __init__(
        self,
        pause_threshold: int = 100,
        resume_threshold: int = 50,
    ):
        self.pause_threshold = pause_threshold
        self.resume_threshold = resume_threshold

        self._queue_size = 0
        self._is_paused = False
        self._lock = asyncio.Lock()

    @property
    def is_paused(self) -> bool:
        """현재 일시 중지 상태인지 반환"""
        return self._is_paused

    @property
    def queue_size(self) -> int:
        """현재 대기 큐 크기"""
        return self._queue_size

    async def increment(self, count: int = 1):
        """
        큐에 작업이 추가될 때 호출.
        큐 크기가 pause_threshold를 초과하면 일시 중지 상태로 전환.
        """
        async with self._lock:
            self._queue_size += count
            if not self._is_paused and self._queue_size > self.pause_threshold:
                self._is_paused = True
                print(
                    f"[BackPressure] 큐 {self._queue_size}건 > "
                    f"{self.pause_threshold}건 -> 크롤링 일시 중지"
                )

    async def decrement(self, count: int = 1):
        """
        작업 처리 완료 시 호출.
        큐 크기가 resume_threshold 이하로 내려가면 재개.
        """
        async with self._lock:
            self._queue_size = max(0, self._queue_size - count)
            if self._is_paused and self._queue_size <= self.resume_threshold:
                self._is_paused = False
                print(
                    f"[BackPressure] 큐 {self._queue_size}건 <= "
                    f"{self.resume_threshold}건 -> 크롤링 재개"
                )

    async def wait_if_paused(self, check_interval: float = 1.0):
        """
        백프레셔로 일시 중지된 경우, 재개될 때까지 대기한다.
        check_interval(초) 간격으로 상태를 확인한다.
        """
        while self._is_paused:
            await asyncio.sleep(check_interval)


# ============================================================
# 적응형 수집량 조절기
# ============================================================
class AdaptiveRateController:
    """
    서버 CPU 부하에 따라 카테고리당 수집 건수를 동적으로 결정한다.

    CPU 사용률 구간별 수집량:
      - CPU < 50%  → 카테고리당 20건 (여유 상태)
      - CPU 50~70% → 카테고리당 15건 (보통 부하)
      - CPU > 70%  → 카테고리당 10건 (고부하 상태)

    psutil.cpu_percent()를 사용하며, interval=1로 1초간 샘플링한다.
    """

    # CPU 구간별 수집 건수 매핑
    TIERS = [
        (50.0, 20),   # CPU < 50%  → 20건 (여유 상태)
        (70.0, 15),   # CPU < 70%  → 15건 (보통 부하)
        (100.0, 10),  # CPU ≤ 100% → 10건 (고부하 상태)
    ]

    @staticmethod
    def get_articles_per_category() -> int:
        """
        현재 CPU 사용률을 측정하고, 적정 수집 건수를 반환한다.

        Returns:
            int: 카테고리당 수집할 기사 수 (50, 30, 또는 15)
        """
        # interval=1: 1초간 CPU 사용률 측정 (non-blocking 아님, 스케줄러 스레드에서 호출)
        cpu_percent = psutil.cpu_percent(interval=1)

        for threshold, count in AdaptiveRateController.TIERS:
            if cpu_percent < threshold:
                print(
                    f"[AdaptiveRate] CPU {cpu_percent:.1f}% "
                    f"-> 카테고리당 {count}건 수집"
                )
                return count

        # fallback (CPU 100%)
        return 15

    @staticmethod
    async def get_articles_per_category_async() -> int:
        """
        비동기 버전: CPU 측정을 별도 스레드에서 실행하여 이벤트 루프를 블로킹하지 않는다.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, AdaptiveRateController.get_articles_per_category
        )
