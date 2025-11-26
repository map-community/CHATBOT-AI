"""
재시도 로직 유틸리티

API 호출 실패 시 exponential backoff 전략으로 재시도하는 데코레이터 및 헬퍼 함수
"""
import time
import logging
from typing import Callable, TypeVar, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential: bool = True,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[int, int, Exception], None]] = None,
    on_final_failure: Optional[Callable[[Exception], None]] = None
):
    """
    Exponential backoff 전략으로 함수 재시도 데코레이터

    Args:
        max_retries: 최대 재시도 횟수 (기본값: 3)
        base_delay: 기본 대기 시간 (초, 기본값: 1.0)
        exponential: True이면 지수 백오프(2^attempt), False이면 고정 대기
        exceptions: 재시도할 예외 타입 튜플 (기본값: 모든 Exception)
        on_retry: 재시도 시 호출할 콜백 함수 (attempt, max_retries, exception)
        on_final_failure: 최종 실패 시 호출할 콜백 함수 (exception)

    Returns:
        데코레이터 함수

    Examples:
        >>> @retry_with_backoff(max_retries=3)
        ... def api_call():
        ...     response = requests.get("https://api.example.com")
        ...     return response.json()

        >>> @retry_with_backoff(
        ...     max_retries=5,
        ...     base_delay=2.0,
        ...     exceptions=(requests.RequestException,)
        ... )
        ... def unstable_api():
        ...     return requests.post("https://api.example.com")

    Notes:
        - exponential=True일 때 대기 시간: base_delay * (2 ^ attempt)
          (예: 1초, 2초, 4초, 8초, ...)
        - exponential=False일 때 대기 시간: base_delay (고정)
        - 마지막 시도에서도 실패하면 예외를 re-raise
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt < max_retries - 1:
                        # 재시도 전 대기
                        if exponential:
                            wait_time = base_delay * (2 ** attempt)
                        else:
                            wait_time = base_delay

                        # 커스텀 재시도 콜백 실행
                        if on_retry:
                            on_retry(attempt + 1, max_retries, e)
                        else:
                            logger.warning(
                                f"재시도 {attempt + 1}/{max_retries} "
                                f"(대기: {wait_time:.1f}초) - {func.__name__}: {e}"
                            )

                        time.sleep(wait_time)
                    else:
                        # 최종 실패
                        if on_final_failure:
                            on_final_failure(e)
                        else:
                            logger.error(f"최종 실패 ({max_retries}회 시도) - {func.__name__}: {e}")
                        raise
            # 여기 도달하면 안 되지만 타입 체커를 위해
            raise RuntimeError("Unexpected state in retry_with_backoff")
        return wrapper
    return decorator


class RetryContext:
    """
    재시도 로직을 컨텍스트 매니저로 제공하는 클래스

    데코레이터 사용이 불가능한 경우 (인라인 재시도 로직) 활용

    Examples:
        >>> retry_ctx = RetryContext(max_retries=3)
        >>> for attempt in retry_ctx:
        ...     try:
        ...         result = api_call()
        ...         break  # 성공 시 탈출
        ...     except Exception as e:
        ...         retry_ctx.handle_exception(e, attempt)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        exponential: bool = True,
        exceptions: tuple = (Exception,)
    ):
        """
        Args:
            max_retries: 최대 재시도 횟수
            base_delay: 기본 대기 시간 (초)
            exponential: True이면 지수 백오프, False이면 고정 대기
            exceptions: 재시도할 예외 타입 튜플
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.exponential = exponential
        self.exceptions = exceptions
        self.current_attempt = 0

    def __iter__(self):
        """range(max_retries)처럼 사용"""
        return iter(range(self.max_retries))

    def handle_exception(self, exception: Exception, attempt: int):
        """
        예외 처리 및 재시도 대기

        Args:
            exception: 발생한 예외
            attempt: 현재 시도 횟수 (0부터 시작)

        Raises:
            Exception: 마지막 시도에서 발생한 예외를 re-raise
        """
        if not isinstance(exception, self.exceptions):
            # 재시도 대상이 아닌 예외는 즉시 raise
            raise exception

        if attempt < self.max_retries - 1:
            # 재시도 전 대기
            if self.exponential:
                wait_time = self.base_delay * (2 ** attempt)
            else:
                wait_time = self.base_delay

            logger.warning(
                f"재시도 {attempt + 1}/{self.max_retries} "
                f"(대기: {wait_time:.1f}초): {exception}"
            )
            time.sleep(wait_time)
        else:
            # 최종 실패
            logger.error(f"최종 실패 ({self.max_retries}회 시도): {exception}")
            raise exception


# ============================================================
# 편의 함수
# ============================================================

def retry_on_exception(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
    *args,
    **kwargs
) -> T:
    """
    함수를 재시도 로직과 함께 실행 (데코레이터 없이 사용)

    Args:
        func: 실행할 함수
        max_retries: 최대 재시도 횟수
        base_delay: 기본 대기 시간 (초)
        exceptions: 재시도할 예외 타입 튜플
        *args, **kwargs: func에 전달할 인자

    Returns:
        func의 반환값

    Raises:
        Exception: 최종 실패 시 마지막 예외

    Examples:
        >>> result = retry_on_exception(
        ...     requests.get,
        ...     max_retries=5,
        ...     base_delay=2.0,
        ...     exceptions=(requests.RequestException,),
        ...     "https://api.example.com"
        ... )
    """
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)
                logger.warning(
                    f"재시도 {attempt + 1}/{max_retries} "
                    f"(대기: {wait_time:.1f}초) - {func.__name__}: {e}"
                )
                time.sleep(wait_time)
            else:
                logger.error(f"최종 실패 ({max_retries}회 시도) - {func.__name__}: {e}")
                raise
    raise RuntimeError("Unexpected state in retry_on_exception")
