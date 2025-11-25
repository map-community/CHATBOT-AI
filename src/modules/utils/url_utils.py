"""
URL 처리 유틸리티

URL 매칭, 필터링 등의 유틸리티 기능 제공
"""
from typing import List, Tuple


def find_documents_by_url_prefix(
    url_prefix: str,
    titles: List[str],
    dates: List[str],
    texts: List[str],
    urls: List[str],
    max_count: int
) -> List[Tuple[str, str, str, str]]:
    """
    URL 접두사로 문서를 검색하고 고유한 문서를 반환

    Args:
        url_prefix: 검색할 URL 접두사
        titles: 제목 리스트
        dates: 날짜 리스트
        texts: 텍스트 리스트
        urls: URL 리스트
        max_count: 최대 반환 문서 수

    Returns:
        [(title, date, text, url), ...] 형식의 문서 리스트
        URL 숫자 기준으로 고유한 문서만 반환

    Examples:
        >>> find_documents_by_url_prefix(
        ...     url_prefix="https://example.com/post",
        ...     titles=["제목1", "제목2"],
        ...     dates=["2025-01-01", "2025-01-02"],
        ...     texts=["본문1", "본문2"],
        ...     urls=["https://example.com/post123", "https://example.com/post456"],
        ...     max_count=2
        ... )
        [("제목1", "2025-01-01", "본문1", "https://example.com/post123"),
         ("제목2", "2025-01-02", "본문2", "https://example.com/post456")]
    """
    # 1. URL 접두사로 매칭되는 문서 수집
    matched_docs = []
    for i, doc_url in enumerate(urls):
        if doc_url.startswith(url_prefix):
            matched_docs.append((titles[i], dates[i], texts[i], urls[i]))

    # 2. URL 기준 역순 정렬 (최신 문서 우선)
    matched_docs.sort(key=lambda x: x[3], reverse=True)

    # 3. 고유 숫자를 추적하며 max_count개의 문서 선택
    unique_numbers = set()
    filtered_docs = []

    for doc in matched_docs:
        # 고유 숫자가 max_count개 모이면 종료
        if len(unique_numbers) >= max_count:
            break

        # URL에서 숫자 추출 (예: "post123" → "123")
        url_number = ''.join(filter(str.isdigit, doc[3]))
        if not url_number:
            # 숫자가 없는 URL은 그대로 추가
            filtered_docs.append(doc)
        elif url_number not in unique_numbers:
            unique_numbers.add(url_number)
            filtered_docs.append(doc)

    return filtered_docs


# 하위 호환성을 위한 함수 (기존 코드와의 호환)
def find_url(url: str, title: List[str], doc_date: List[str],
             text: List[str], doc_url: List[str], number: int) -> List[Tuple]:
    """
    레거시 함수: 기존 코드와의 호환성 유지

    Args:
        url: 검색할 URL 접두사
        title: 제목 리스트
        doc_date: 날짜 리스트
        text: 텍스트 리스트
        doc_url: URL 리스트
        number: 최대 반환 문서 수

    Returns:
        [(title, date, text, url), ...] 형식의 문서 리스트
    """
    return find_documents_by_url_prefix(
        url_prefix=url,
        titles=title,
        dates=doc_date,
        texts=text,
        urls=doc_url,
        max_count=number
    )
