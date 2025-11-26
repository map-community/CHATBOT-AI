"""
날짜 처리 유틸리티

날짜 형식 표준화 및 변환 기능 제공
"""
from datetime import datetime
import pytz
from typing import Optional


# 한국 시간대
KST = pytz.timezone('Asia/Seoul')


def parse_korean_date(date_str: str) -> Optional[datetime]:
    """
    한국어 날짜 문자열을 datetime 객체로 변환

    Args:
        date_str: "작성일25-10-17 15:48" 형식의 문자열

    Returns:
        datetime 객체 (한국 시간대) 또는 None (파싱 실패 시)
    """
    if not date_str or date_str == "Unknown Date":
        return None

    try:
        # "작성일" 제거
        clean_date_str = date_str.replace("작성일", "").strip()

        # 날짜 파싱 (2자리 연도)
        naive_date = datetime.strptime(clean_date_str, "%y-%m-%d %H:%M")

        # 한국 시간대 추가
        return KST.localize(naive_date)

    except Exception:
        # 파싱 실패 시 None 반환 (경고 제거 - 크롤러에서만 사용됨)
        return None


def to_iso8601(dt: Optional[datetime]) -> str:
    """
    datetime 객체를 ISO 8601 형식 문자열로 변환

    Args:
        dt: datetime 객체

    Returns:
        ISO 8601 형식 문자열 (예: "2025-10-17T15:48:00+09:00")
        파싱 실패 시 빈 문자열 반환
    """
    if dt is None:
        return ""

    try:
        # ISO 8601 형식으로 변환
        return dt.isoformat()
    except Exception:
        return ""


def korean_to_iso8601(date_str: str) -> str:
    """
    한국어 날짜 문자열을 ISO 8601 형식으로 직접 변환

    Args:
        date_str: "작성일25-10-17 15:48" 형식의 문자열

    Returns:
        ISO 8601 형식 문자열 (예: "2025-10-17T15:48:00+09:00")
        파싱 실패 시 빈 문자열 반환

    Examples:
        >>> korean_to_iso8601("작성일25-10-17 15:48")
        "2025-10-17T15:48:00+09:00"

        >>> korean_to_iso8601("작성일24-01-01 00:00")
        "2024-01-01T00:00:00+09:00"
    """
    dt = parse_korean_date(date_str)
    return to_iso8601(dt)


def get_current_kst() -> datetime:
    """
    현재 한국 시간 반환

    Returns:
        현재 한국 시간 (datetime 객체)
    """
    return datetime.now(KST)


def get_current_iso8601() -> str:
    """
    현재 한국 시간을 ISO 8601 형식으로 반환

    Returns:
        현재 시간의 ISO 8601 문자열
    """
    return get_current_kst().isoformat()


def calculate_days_diff(date_str: str) -> Optional[int]:
    """
    ISO 8601 날짜 문자열과 현재 시간의 일수 차이 계산

    Args:
        date_str: ISO 8601 형식 날짜 문자열

    Returns:
        일수 차이 (양수: 과거, 음수: 미래) 또는 None (파싱 실패 시)
    """
    if not date_str:
        return None

    try:
        # ISO 8601 파싱
        post_date = datetime.fromisoformat(date_str)
        current_time = get_current_kst()

        # 일수 차이 계산
        return (current_time - post_date).days

    except Exception as e:
        print(f"⚠️  날짜 차이 계산 실패: {date_str} - {e}")
        return None


# 하위 호환성을 위한 함수 (기존 코드와의 호환)
def parse_date_change_korea_time(date_str: str) -> Optional[datetime]:
    """
    ISO 8601 문자열을 datetime 객체로 변환

    [통일된 날짜 형식] 모든 날짜는 ISO 8601 형식으로 저장/처리됩니다.

    Args:
        date_str: ISO 8601 형식 (예: "2024-01-01T00:00:00+09:00")

    Returns:
        datetime 객체 (한국 시간대) 또는 None
    """
    if not date_str:
        return None

    try:
        # ISO 8601 형식 파싱
        dt = datetime.fromisoformat(date_str)
        # 시간대가 없으면 한국 시간대 추가
        if dt.tzinfo is None:
            return KST.localize(dt)
        return dt
    except Exception:
        # 파싱 실패 시 None 반환 (경고 제거)
        return None
