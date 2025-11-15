"""
채용정보 크롤러
"""
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from .base_crawler import BaseCrawler
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CrawlerConfig


class JobCrawler(BaseCrawler):
    """채용정보 크롤러"""

    def __init__(self):
        super().__init__(
            board_type='job',
            base_url=CrawlerConfig.BASE_URLS['job']
        )

    def extract_from_url(self, url: str) -> Optional[Tuple[str, str, any, str, str]]:
        """
        채용정보 URL에서 데이터 추출

        Args:
            url: 크롤링할 URL

        Returns:
            (title, text, image_list, date, url) 튜플
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

            paragraphs = soup.find('div', id='bo_v_con')
            if paragraphs:
                # 텍스트 추출
                text_content = "\n".join([
                    element.get_text(strip=True)
                    for element in paragraphs.find_all(['p', 'div', 'li'])
                ])

                if text_content.strip() == "":
                    text_content = ""

                # 이미지 URL 추출
                for img in paragraphs.find_all('img'):
                    img_src = img.get('src')
                    if img_src:
                        image_content.append(img_src)

            # 날짜 추출
            date_element = soup.select_one("strong.if_date")
            date = date_element.get_text(strip=True) if date_element else "Unknown Date"

            return title, text_content, image_content, date, url

        except Exception as e:
            print(f"❌ 오류 발생 ({url}): {e}")
            return None
