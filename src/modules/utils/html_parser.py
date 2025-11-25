"""
HTML/Markdown 파싱 유틸리티

다양한 HTML 변환 로직을 통합하여 중복 제거 및 일관성 확보
"""
import logging
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class HTMLParser:
    """
    HTML/Markdown 파싱 통합 클래스

    지원 기능:
    - HTML 테이블 → Markdown 테이블 변환 (상세/간단 모드)
    - HTML → 평문 텍스트 변환
    - Markdown 형식 감지
    - 복합 변환 (테이블 Markdown + 평문 텍스트)
    """

    @staticmethod
    def is_markdown(text: str) -> bool:
        """
        텍스트가 Markdown 형식인지 감지

        Args:
            text: 검사할 텍스트

        Returns:
            Markdown 테이블 형식이면 True

        Examples:
            >>> HTMLParser.is_markdown("| col1 | col2 |\\n| --- | --- |")
            True
            >>> HTMLParser.is_markdown("<table><tr><td>data</td></tr></table>")
            False
        """
        if not text:
            return False
        # Markdown 표 형식: '|' 구분자와 '---' 또는 개행 포함
        return '|' in text and ('---' in text or '\n' in text)

    @staticmethod
    def html_to_text(html: str) -> str:
        """
        HTML을 평문 텍스트로 변환

        Args:
            html: HTML 문자열

        Returns:
            평문 텍스트 (태그 제거됨)

        Note:
            BeautifulSoup을 사용하여 모든 HTML 태그를 제거하고 텍스트만 추출
        """
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, 'html.parser')
            return soup.get_text(separator=' ', strip=True)
        except Exception as e:
            logger.warning(f"HTML 텍스트 변환 실패: {e}")
            return html

    @staticmethod
    def table_to_markdown_detailed(html: str) -> str:
        """
        HTML 테이블을 상세 Markdown 테이블로 변환

        Args:
            html: HTML 문자열 (테이블 포함)

        Returns:
            Markdown 테이블 문자열 (테이블 없으면 빈 문자열)

        Features:
            - 첫 행을 헤더로 인식
            - 셀 개수 불일치 시 자동 패딩
            - 여러 테이블 지원 (구분하여 반환)

        Note:
            multimodal_processor.py의 _html_table_to_markdown() 로직 기반
        """
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')

            if not tables:
                return ""

            markdown_tables = []
            for table in tables:
                rows = table.find_all('tr')
                if not rows:
                    continue

                # 첫 행을 헤더로 사용
                first_row = rows[0]
                headers = [cell.get_text(strip=True) for cell in first_row.find_all(['th', 'td'])]

                if not headers:
                    continue

                # Markdown 테이블 생성
                md_table = "| " + " | ".join(headers) + " |\n"
                md_table += "|" + "|".join([" --- " for _ in headers]) + "|\n"

                # 데이터 행 (첫 행이 헤더가 아닌 경우도 고려)
                data_rows = rows[1:] if len(rows) > 1 else []
                for row in data_rows:
                    cells = [cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]
                    # 셀 개수가 헤더와 다르면 패딩
                    while len(cells) < len(headers):
                        cells.append("")
                    md_table += "| " + " | ".join(cells[:len(headers)]) + " |\n"

                markdown_tables.append(md_table)

            return "\n\n".join(markdown_tables)
        except Exception as e:
            logger.warning(f"HTML 테이블 변환 실패: {e}")
            return ""

    @staticmethod
    def table_to_markdown_simple(html: str) -> str:
        """
        HTML 테이블을 간단한 Markdown 테이블로 변환

        Args:
            html: HTML 문자열 (테이블 포함)

        Returns:
            Markdown 테이블 문자열

        Features:
            - 모든 행을 동일하게 처리
            - 첫 행 다음에 구분선 자동 추가
            - **[표 데이터]** 헤더 포함

        Note:
            ai_modules.py의 get_ai_message() 로직 기반
        """
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')

            if not tables:
                return ""

            markdown_content = ""
            for table in tables:
                markdown_content += "\n\n**[표 데이터]**\n"
                rows = table.find_all('tr')
                for row_idx, row in enumerate(rows):
                    cells = row.find_all(['th', 'td'])
                    row_text = " | ".join([cell.get_text(strip=True) for cell in cells])
                    markdown_content += f"| {row_text} |\n"
                    # 헤더 행 다음에 구분선 추가
                    if row_idx == 0 and cells:
                        markdown_content += "| " + " | ".join(["---"] * len(cells)) + " |\n"
                markdown_content += "\n"

            return markdown_content
        except Exception as e:
            logger.warning(f"HTML 테이블 간단 변환 실패: {e}")
            return ""

    @staticmethod
    def html_to_markdown_with_text(html: str) -> str:
        """
        HTML을 Markdown 테이블 + 평문 텍스트로 변환

        Args:
            html: HTML 문자열

        Returns:
            Markdown 테이블 + 평문 텍스트 결합 문자열

        Process:
            1. HTML 테이블을 Markdown으로 변환
            2. 테이블을 제거한 후 나머지 텍스트 추출
            3. 두 내용을 결합하여 반환

        Note:
            ai_modules.py의 get_ai_message() 로직 기반
            LLM 입력용 최적화된 형식
        """
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 1단계: 테이블 → Markdown 변환
            markdown_content = HTMLParser.table_to_markdown_simple(html)

            # 2단계: 테이블 제거 후 평문 텍스트 추출
            for table in soup.find_all('table'):
                table.decompose()  # 테이블 제거 (중복 방지)

            plain_text = soup.get_text(separator='\n', strip=True)

            # 3단계: 결합
            result = (markdown_content + "\n" + plain_text).strip()
            return result if result else ""

        except Exception as e:
            logger.warning(f"HTML 복합 변환 실패: {e}")
            return ""

    @staticmethod
    def parse_html_or_markdown(content: str) -> str:
        """
        HTML 또는 Markdown을 자동 감지하여 텍스트로 변환

        Args:
            content: HTML 또는 Markdown 문자열

        Returns:
            파싱된 텍스트

        Logic:
            - Markdown 감지 → 그대로 반환 (이미 LLM 최적화 형식)
            - HTML 감지 → 평문 텍스트로 변환

        Note:
            bm25_retriever.py의 _parse_html_to_text() 로직 기반
        """
        if not content:
            return ""

        # Markdown 형식이면 그대로 반환
        if HTMLParser.is_markdown(content):
            return content

        # HTML이면 평문 변환
        return HTMLParser.html_to_text(content)


# ============================================================
# 편의 함수 (Backward Compatibility)
# ============================================================

def is_markdown(text: str) -> bool:
    """Markdown 형식 감지 (편의 함수)"""
    return HTMLParser.is_markdown(text)


def html_to_text(html: str) -> str:
    """HTML → 평문 텍스트 변환 (편의 함수)"""
    return HTMLParser.html_to_text(html)


def html_to_markdown(html: str, detailed: bool = False) -> str:
    """
    HTML 테이블 → Markdown 변환 (편의 함수)

    Args:
        html: HTML 문자열
        detailed: True이면 상세 모드, False이면 간단 모드

    Returns:
        Markdown 테이블 문자열
    """
    if detailed:
        return HTMLParser.table_to_markdown_detailed(html)
    return HTMLParser.table_to_markdown_simple(html)


def parse_html_or_markdown(content: str) -> str:
    """HTML/Markdown 자동 감지 파싱 (편의 함수)"""
    return HTMLParser.parse_html_or_markdown(content)
