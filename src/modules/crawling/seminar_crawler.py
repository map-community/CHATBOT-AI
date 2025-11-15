"""
세미나 크롤러
"""
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from .base_crawler import BaseCrawler
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CrawlerConfig


class SeminarCrawler(BaseCrawler):
    """세미나 크롤러"""

    def __init__(self):
        super().__init__(
            board_type='seminar',
            base_url=CrawlerConfig.BASE_URLS['seminar']
        )

    def extract_from_url(self, url: str) -> Optional[Tuple[str, str, any, any, str, str]]:
        """
        세미나 URL에서 데이터 추출

        Args:
            url: 크롤링할 URL

        Returns:
            (title, text, image_list, attachment_list, date, url) 튜플
        """
        try:
            response = self.fetch_with_retry(url)
            if response is None:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # 제목 추출
            title_element = soup.find('span', class_='bo_v_tit')
            title = title_element.get_text(strip=True) if title_element else "Unknown Title"

            # 제목이 Unknown이면 건너뜀
            if title == "Unknown Title":
                return None

            # 본문 텍스트 추출
            text_content = ""
            image_content = []
            attachment_content = []

            paragraphs = soup.find('div', id='bo_v_con')
            if paragraphs:
                # 텍스트 추출 (get_text()로 모든 텍스트 추출)
                text_content = paragraphs.get_text(separator='\n', strip=True)

                if text_content.strip() == "":
                    text_content = ""

                # 이미지 URL 추출
                for img in paragraphs.find_all('img'):
                    img_src = img.get('src')
                    if img_src:
                        # 상대 경로를 절대 경로로 변환
                        if img_src.startswith('/'):
                            img_src = f"https://cse.knu.ac.kr{img_src}"
                        elif not img_src.startswith('http'):
                            img_src = f"https://cse.knu.ac.kr/{img_src}"
                        image_content.append(img_src)

            # 첨부파일 URL 추출
            attachment_section = soup.find('section', id='bo_v_file') or soup.find('div', class_='bo_v_file')
            if attachment_section:
                for link in attachment_section.find_all('a', href=True, class_='view_file_download'):
                    href = link['href']
                    # 다운로드 링크만 추출 (download.php 또는 파일 확장자 포함)
                    if 'download.php' in href or any(ext in href.lower() for ext in ['.pdf', '.docx', '.hwp', '.pptx', '.xlsx', '.doc', '.ppt', '.xls']):
                        # 상대 경로를 절대 경로로 변환
                        if href.startswith('/'):
                            href = f"https://cse.knu.ac.kr{href}"
                        elif not href.startswith('http'):
                            href = f"https://cse.knu.ac.kr/{href}"
                        attachment_content.append(href)

            # 날짜 추출
            date_element = soup.select_one("strong.if_date")
            date = date_element.get_text(strip=True) if date_element else "Unknown Date"

            return title, text_content, image_content, attachment_content, date, url

        except Exception as e:
            print(f"❌ 오류 발생 ({url}): {e}")
            return None
