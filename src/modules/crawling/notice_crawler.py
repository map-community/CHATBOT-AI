"""
공지사항 크롤러
"""
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from .base_crawler import BaseCrawler
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CrawlerConfig
from utils import korean_to_iso8601
from constants import UNKNOWN_DATE


class NoticeCrawler(BaseCrawler):
    """공지사항 크롤러"""

    def __init__(self):
        super().__init__(
            board_type='notice',
            base_url=CrawlerConfig.BASE_URLS['notice']
        )

    def extract_from_url(self, url: str) -> Optional[Tuple[str, str, any, any, str, str]]:
        """
        공지사항 URL에서 데이터 추출

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

                # 이미지 URL 추출 (원본 이미지 우선)
                for img in paragraphs.find_all('img'):
                    img_url = None

                    # 1. 부모 <a> 태그에서 원본 이미지 링크 찾기
                    parent_link = img.find_parent('a')
                    if parent_link and parent_link.get('href'):
                        href = parent_link['href']
                        # 이미지 파일인지 확인
                        if any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                            img_url = href

                    # 2. data-original 속성 확인 (lazy loading)
                    if not img_url and img.get('data-original'):
                        img_url = img.get('data-original')

                    # 3. src 속성에서 썸네일 패턴 제거
                    if not img_url and img.get('src'):
                        src = img.get('src')
                        # thumb- 접두사 제거 시도
                        if '/thumb-' in src:
                            # thumb-파일명__크기정보.확장자 → 파일명.확장자 패턴 제거
                            # 예: thumb-abc__1234_1350x6875.png → abc.jpg로 추정하지 않고 건너뜀
                            # 대신 원본을 찾을 수 없으면 썸네일이라도 사용
                            img_url = src
                        else:
                            img_url = src

                    if img_url:
                        # 상대 경로를 절대 경로로 변환 (Data URI 제외)
                        if not img_url.startswith(('http', 'data:')):
                            if img_url.startswith('/'):
                                img_url = f"https://cse.knu.ac.kr{img_url}"
                            else:
                                img_url = f"https://cse.knu.ac.kr/{img_url}"

                        # thumb- URL은 원본을 못 찾은 경우만 추가 (일단 제외)
                        if '/thumb-' not in img_url:
                            image_content.append(img_url)

            # 첨부파일 URL 추출 (게시판 첨부파일 영역에서)
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

            # 중복 제거: 본문 이미지와 첨부파일에서 중복되는 URL 제거
            # (같은 이미지가 본문과 첨부파일에 모두 있는 경우)
            original_attachment_count = len(attachment_content)
            image_urls_set = set(image_content)
            attachment_content = [url for url in attachment_content if url not in image_urls_set]
            removed_count = original_attachment_count - len(attachment_content)

            if removed_count > 0:
                print(f"ℹ️  중복 제거: 본문과 중복되는 첨부파일 {removed_count}개 제거 (본문 이미지로 처리)")

            # 날짜 추출
            date_element = soup.select_one("strong.if_date")
            date_raw = date_element.get_text(strip=True) if date_element else ""

            # 한국어 날짜 형식을 ISO 8601로 변환
            date = korean_to_iso8601(date_raw) if date_raw else UNKNOWN_DATE

            return title, text_content, image_content, attachment_content, date, url

        except Exception as e:
            print(f"❌ 오류 발생 ({url}): {e}")
            return None
