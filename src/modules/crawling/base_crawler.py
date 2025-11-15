"""
기본 크롤러 추상 클래스
모든 크롤러의 공통 기능 제공
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import re
import time
from ..config import CrawlerConfig


class BaseCrawler(ABC):
    """
    추상 기본 크롤러 클래스

    역할:
    - 모든 크롤러의 공통 기능 제공
    - 템플릿 메서드 패턴 적용
    - 재시도 로직 포함
    """

    def __init__(self, board_type: str, base_url: str):
        """
        Args:
            board_type: 게시판 타입 ('notice', 'job', 'seminar' 등)
            base_url: 게시판 기본 URL
        """
        self.board_type = board_type
        self.base_url = base_url
        self.max_workers = CrawlerConfig.MAX_WORKERS
        self.max_retries = CrawlerConfig.MAX_RETRIES
        self.retry_delay = CrawlerConfig.RETRY_DELAY

    def fetch_with_retry(self, url: str) -> Optional[requests.Response]:
        """
        재시도 로직이 포함된 HTTP 요청

        Args:
            url: 요청할 URL

        Returns:
            Response 객체 (실패 시 None)
        """
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    return response
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"⚠️  재시도 {attempt + 1}/{self.max_retries}: {url}")
                    time.sleep(self.retry_delay)
                else:
                    print(f"❌ 요청 실패: {url} - {e}")

        return None

    def get_latest_id(self) -> Optional[int]:
        """
        게시판의 최신 게시글 ID 조회

        Returns:
            최신 ID (조회 실패 시 None)
        """
        response = self.fetch_with_retry(self.base_url)

        if response is None:
            return None

        # URL에서 wr_id 추출
        matches = re.findall(r'wr_id=(\d+)', response.text)

        if matches:
            return max(int(wr_id) for wr_id in matches)

        return None

    @abstractmethod
    def extract_from_url(self, url: str) -> Optional[Tuple[str, str, any, str, str]]:
        """
        URL에서 데이터 추출 (각 크롤러에서 구현)

        Args:
            url: 크롤링할 URL

        Returns:
            (title, text, image, date, url) 튜플 (실패 시 None)
        """
        pass

    def crawl_urls(self, urls: List[str]) -> List[Tuple[str, str, any, str, str]]:
        """
        여러 URL을 병렬로 크롤링

        Args:
            urls: 크롤링할 URL 리스트

        Returns:
            [(title, text, image, date, url), ...] 리스트
        """
        all_data = []

        print(f"\n{'='*80}")
        print(f"🌐 {self.board_type.upper()} 크롤링 시작")
        print(f"📋 크롤링할 URL 개수: {len(urls)}개")
        print(f"{'='*80}\n")

        if not urls:
            print("⚠️  크롤링할 URL이 없습니다.")
            return all_data

        print("🔄 웹 크롤링 중...\n")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = executor.map(self.extract_from_url, urls)

        # 유효한 데이터만 추가
        for result in results:
            if result is not None:
                title, text, image, date, url = result
                if title is not None and title != "Unknown Title":
                    all_data.append((title, text, image, date, url))

        print(f"\n{'='*80}")
        print(f"✅ {self.board_type.upper()} 크롤링 완료! {len(all_data)}개 수집됨")
        print(f"{'='*80}\n")

        return all_data

    def generate_urls(self, id_range: range) -> List[str]:
        """
        ID 범위로부터 URL 리스트 생성

        Args:
            id_range: ID range 객체

        Returns:
            URL 리스트
        """
        urls = []
        for wr_id in id_range:
            url = f"{self.base_url}&wr_id={wr_id}"
            urls.append(url)

        return urls
