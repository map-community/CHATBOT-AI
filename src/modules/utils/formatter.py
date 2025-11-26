"""
문서 및 데이터 포매팅 유틸리티

LLM이 이해하기 쉬운 형식으로 데이터를 변환하는 함수들
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def format_temporal_intent(temporal_filter: Optional[Dict[str, Any]]) -> str:
    """
    시간 의도를 LLM이 이해하기 쉬운 문자열로 변환

    Args:
        temporal_filter: parse_temporal_intent()의 반환값
            예: {'is_ongoing': True} 또는 {'year': 2024, 'semester': 1}

    Returns:
        str: 시간 의도 설명 (이모지 포함)

    Examples:
        >>> format_temporal_intent({'is_ongoing': True})
        '🎯 현재 진행중인 것을 묻고 있습니다 (마감일이 지나지 않은 항목, 현재 신청/참여 가능한 것)'

        >>> format_temporal_intent({'year': 2024, 'semester': 1})
        '📅 2024학년도 1학기 정보를 묻고 있습니다'

        >>> format_temporal_intent(None)
        '시간 의도 없음 (일반 검색)'
    """
    if not temporal_filter:
        return "시간 의도 없음 (일반 검색)"

    if temporal_filter.get('is_ongoing'):
        return "🎯 현재 진행중인 것을 묻고 있습니다 (마감일이 지나지 않은 항목, 현재 신청/참여 가능한 것)"

    elif temporal_filter.get('is_policy'):
        return "📜 정책/규정 질문 (시간 무관, 최신 정보 제공)"

    elif temporal_filter.get('year') and temporal_filter.get('semester'):
        year = temporal_filter['year']
        semester = temporal_filter['semester']
        return f"📅 {year}학년도 {semester}학기 정보를 묻고 있습니다"

    elif temporal_filter.get('year'):
        year = temporal_filter['year']
        return f"📅 {year}년도 정보를 묻고 있습니다"

    elif temporal_filter.get('year_from'):
        year_from = temporal_filter['year_from']
        return f"📅 {year_from}년 이후 최근 정보를 묻고 있습니다"

    else:
        return "시간 의도 없음"


def format_docs(docs: List[Any]) -> str:
    """
    문서 리스트를 LLM이 이해하기 쉬운 형식으로 포맷팅

    출처(원본/이미지OCR/첨부파일)를 라벨로 표시하여 맥락 제공
    각 청크에 제목 정보를 명시하여 문맥 단절(Context Fragmentation) 문제 해결

    Args:
        docs: Document 객체 리스트 (LangChain Document)
            각 Document는 page_content와 metadata를 가짐

    Returns:
        str: 포맷팅된 컨텍스트 문자열

    Format:
        ```
        문서 제목: [제목]
        [라벨]
        [내용]

        문서 제목: [제목]
        [라벨]
        [내용]
        ```

    Examples:
        >>> from langchain.schema import Document
        >>> docs = [
        ...     Document(
        ...         page_content="공지사항 내용...",
        ...         metadata={"title": "2024학년도 1학기 수강신청", "source": "original_post"}
        ...     )
        ... ]
        >>> result = format_docs(docs)
        >>> "문서 제목: 2024학년도 1학기 수강신청" in result
        True
    """
    formatted = []

    for doc in docs:
        # 메타데이터에서 제목 추출
        title = doc.metadata.get('title', '제목 없음')

        # 출처에 따라 라벨 생성
        source = doc.metadata.get('source', 'original_post')
        content_type = doc.metadata.get('content_type', 'text')

        if source == "image_ocr":
            label = "[이미지 OCR 텍스트]"
        elif source == "document_parse":
            # 첨부파일 타입 표시
            attachment_type = doc.metadata.get('attachment_type', 'document')
            label = f"[첨부파일: {attachment_type.upper()}]"
        else:
            # 원본 게시글
            label = "[본문]"

        # 제목 + 라벨 + 내용 (제목을 명시하여 청크의 문맥 제공)
        formatted.append(f"문서 제목: {title}\n{label}\n{doc.page_content}")

    return "\n\n".join(formatted)


def format_search_results(results: List[tuple], include_scores: bool = False) -> str:
    """
    검색 결과를 사람이 읽기 쉬운 형식으로 포맷팅

    Args:
        results: (score, title, date, text, url) 형식의 튜플 리스트
        include_scores: True이면 유사도 점수 포함

    Returns:
        str: 포맷팅된 검색 결과

    Examples:
        >>> results = [(0.95, "공지사항", "2024-01-01", "내용", "http://...")]
        >>> formatted = format_search_results(results, include_scores=True)
        >>> "0.95" in formatted
        True
    """
    lines = []

    for i, result in enumerate(results, 1):
        if len(result) >= 5:
            score, title, date, text, url = result[:5]

            if include_scores:
                lines.append(f"{i}. [{score:.4f}] {title}")
            else:
                lines.append(f"{i}. {title}")

            lines.append(f"   날짜: {date}")
            lines.append(f"   URL: {url}")
            lines.append(f"   내용: {text[:100]}..." if len(text) > 100 else f"   내용: {text}")
            lines.append("")

    return "\n".join(lines)
