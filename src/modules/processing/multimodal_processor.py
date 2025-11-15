"""
멀티모달 콘텐츠 처리
이미지, 첨부파일 등 비텍스트 콘텐츠를 RAG에 활용 가능하도록 변환
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from typing import List, Tuple, Dict, Optional
from pymongo import MongoClient
from config import CrawlerConfig
from processing.upstage_client import UpstageClient

logger = logging.getLogger(__name__)


class MultimodalContent:
    """
    멀티모달 콘텐츠 데이터 클래스

    하나의 게시글에서 추출된 모든 콘텐츠를 담는 컨테이너
    """

    def __init__(self, title: str, url: str, date: str):
        self.title = title
        self.url = url
        self.date = date

        # 텍스트 콘텐츠
        self.text_chunks: List[str] = []

        # 이미지 콘텐츠
        self.image_contents: List[Dict] = []
        # [{"url": "...", "ocr_text": "...", "description": "..."}]

        # 첨부파일 콘텐츠
        self.attachment_contents: List[Dict] = []
        # [{"url": "...", "type": "pdf", "text": "..."}]

    def add_text_chunk(self, text: str):
        """텍스트 청크 추가"""
        if text and text.strip():
            self.text_chunks.append(text)

    def add_image_content(self, url: str, ocr_text: str = "", description: str = ""):
        """이미지 콘텐츠 추가"""
        self.image_contents.append({
            "url": url,
            "ocr_text": ocr_text,
            "description": description
        })

    def add_attachment_content(self, url: str, file_type: str, text: str):
        """첨부파일 콘텐츠 추가"""
        self.attachment_contents.append({
            "url": url,
            "type": file_type,
            "text": text
        })

    def to_embedding_items(self) -> List[Tuple[str, Dict]]:
        """
        임베딩할 항목들로 변환

        Returns:
            [(text, metadata), ...]
        """
        items = []

        # 1. 텍스트 청크
        for chunk in self.text_chunks:
            items.append((
                chunk,
                {
                    "title": self.title,
                    "url": self.url,
                    "date": self.date,
                    "content_type": "text",
                }
            ))

        # 2. 이미지 OCR 결과
        for img in self.image_contents:
            if img["ocr_text"]:
                # OCR 텍스트를 임베딩
                combined_text = f"[이미지 텍스트]\n{img['ocr_text']}"

                # 설명도 있으면 추가
                if img["description"]:
                    combined_text += f"\n\n[이미지 설명]\n{img['description']}"

                items.append((
                    combined_text,
                    {
                        "title": self.title,
                        "url": self.url,
                        "date": self.date,
                        "content_type": "image",
                        "image_url": img["url"]
                    }
                ))

        # 3. 첨부파일 내용
        for att in self.attachment_contents:
            if att["text"]:
                items.append((
                    f"[첨부파일: {att['type'].upper()}]\n{att['text']}",
                    {
                        "title": self.title,
                        "url": self.url,
                        "date": self.date,
                        "content_type": "attachment",
                        "attachment_url": att["url"],
                        "attachment_type": att["type"]
                    }
                ))

        return items


class MultimodalProcessor:
    """
    멀티모달 콘텐츠 프로세서

    역할:
    - 이미지에서 텍스트 추출 (OCR)
    - 첨부파일에서 텍스트 추출 (Document Parse)
    - 처리된 콘텐츠를 RAG용으로 변환
    """

    def __init__(
        self,
        upstage_api_key: Optional[str] = None,
        mongo_client: Optional[MongoClient] = None,
        enable_image_processing: bool = True,
        enable_attachment_processing: bool = True
    ):
        """
        Args:
            upstage_api_key: Upstage API 키
            mongo_client: MongoDB 클라이언트 (처리 이력 저장용)
            enable_image_processing: 이미지 처리 활성화
            enable_attachment_processing: 첨부파일 처리 활성화
        """
        self.upstage_client = UpstageClient(api_key=upstage_api_key)
        self.enable_image = enable_image_processing
        self.enable_attachment = enable_attachment_processing

        # MongoDB 연결 (처리 이력 캐시용)
        if mongo_client is None:
            mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)

        self.client = mongo_client
        self.db = self.client[CrawlerConfig.MONGODB_DATABASE]
        self.cache_collection = self.db["multimodal_cache"]

        # 캐시 인덱스 생성
        self.cache_collection.create_index("url", unique=True)

        logger.info(f"MultimodalProcessor 초기화 - 이미지: {self.enable_image}, 첨부파일: {self.enable_attachment}")

    def process_images(self, image_urls: List[str]) -> List[Dict]:
        """
        이미지 리스트 처리 (OCR)

        Args:
            image_urls: 이미지 URL 리스트

        Returns:
            [{"url": "...", "ocr_text": "...", "description": "..."}, ...]
        """
        if not self.enable_image or not image_urls:
            return []

        results = []

        for img_url in image_urls:
            try:
                # 캐시 확인
                cached = self._get_from_cache(img_url)
                if cached:
                    logger.info(f"✅ 캐시에서 이미지 로드: {img_url}")
                    results.append(cached)
                    continue

                # Upstage OCR API 호출
                logger.info(f"🖼️  이미지 처리 중: {img_url}")
                ocr_result = self.upstage_client.extract_text_from_image_url(img_url)

                if ocr_result and ocr_result["text"]:
                    content = {
                        "url": img_url,
                        "ocr_text": ocr_result["text"],
                        "description": ""  # 향후 Vision API 추가 가능
                    }

                    results.append(content)

                    # 캐시에 저장
                    self._save_to_cache(img_url, content)

                    logger.info(f"✅ 이미지 OCR 완료: {len(ocr_result['text'])}자")
                else:
                    logger.warning(f"⚠️  이미지에서 텍스트 추출 실패: {img_url}")

            except Exception as e:
                logger.error(f"❌ 이미지 처리 오류 ({img_url}): {e}")
                # 오류 발생해도 다음 이미지 계속 처리

        return results

    def process_attachments(self, attachment_urls: List[str]) -> List[Dict]:
        """
        첨부파일 리스트 처리 (Document Parse)

        Args:
            attachment_urls: 첨부파일 URL 리스트

        Returns:
            [{"url": "...", "type": "pdf", "text": "..."}, ...]
        """
        if not self.enable_attachment or not attachment_urls:
            return []

        results = []

        for att_url in attachment_urls:
            try:
                # 파일 타입 확인
                if not self.upstage_client.is_document_url(att_url):
                    logger.warning(f"지원하지 않는 파일 타입: {att_url}")
                    continue

                # 캐시 확인
                cached = self._get_from_cache(att_url)
                if cached:
                    logger.info(f"✅ 캐시에서 첨부파일 로드: {att_url}")
                    results.append(cached)
                    continue

                # Upstage Document Parse API 호출
                logger.info(f"📄 첨부파일 처리 중: {att_url}")
                parse_result = self.upstage_client.parse_document_from_url(att_url)

                if parse_result and parse_result["text"]:
                    file_type = Path(att_url).suffix.lower()[1:]  # .pdf -> pdf

                    content = {
                        "url": att_url,
                        "type": file_type,
                        "text": parse_result["text"]
                    }

                    results.append(content)

                    # 캐시에 저장
                    self._save_to_cache(att_url, content)

                    logger.info(f"✅ 첨부파일 파싱 완료: {len(parse_result['text'])}자")
                else:
                    logger.warning(f"⚠️  첨부파일 파싱 실패: {att_url}")

            except Exception as e:
                logger.error(f"❌ 첨부파일 처리 오류 ({att_url}): {e}")
                # 오류 발생해도 다음 파일 계속 처리

        return results

    def _get_from_cache(self, url: str) -> Optional[Dict]:
        """캐시에서 처리 결과 조회"""
        try:
            cached = self.cache_collection.find_one({"url": url})
            if cached:
                # MongoDB _id 제거
                cached.pop("_id", None)
                cached.pop("url", None)
                return cached
        except Exception as e:
            logger.warning(f"캐시 조회 오류: {e}")

        return None

    def _save_to_cache(self, url: str, content: Dict):
        """처리 결과를 캐시에 저장"""
        try:
            cache_data = {"url": url, **content}
            self.cache_collection.update_one(
                {"url": url},
                {"$set": cache_data},
                upsert=True
            )
        except Exception as e:
            logger.warning(f"캐시 저장 오류: {e}")

    def create_multimodal_content(
        self,
        title: str,
        url: str,
        date: str,
        text_chunks: List[str],
        image_urls: List[str],
        attachment_urls: List[str]
    ) -> MultimodalContent:
        """
        멀티모달 콘텐츠 생성 (통합 인터페이스)

        Args:
            title: 게시글 제목
            url: 게시글 URL
            date: 날짜
            text_chunks: 텍스트 청크 리스트
            image_urls: 이미지 URL 리스트
            attachment_urls: 첨부파일 URL 리스트

        Returns:
            MultimodalContent 객체
        """
        content = MultimodalContent(title, url, date)

        # 1. 텍스트 추가
        for chunk in text_chunks:
            content.add_text_chunk(chunk)

        # 2. 이미지 처리 및 추가
        if image_urls:
            logger.info(f"🖼️  이미지 {len(image_urls)}개 처리 시작")
            image_contents = self.process_images(image_urls)
            for img_content in image_contents:
                content.add_image_content(
                    url=img_content["url"],
                    ocr_text=img_content.get("ocr_text", ""),
                    description=img_content.get("description", "")
                )
            logger.info(f"✅ 이미지 처리 완료: {len(image_contents)}개")

        # 3. 첨부파일 처리 및 추가
        if attachment_urls:
            logger.info(f"📄 첨부파일 {len(attachment_urls)}개 처리 시작")
            attachment_contents = self.process_attachments(attachment_urls)
            for att_content in attachment_contents:
                content.add_attachment_content(
                    url=att_content["url"],
                    file_type=att_content["type"],
                    text=att_content["text"]
                )
            logger.info(f"✅ 첨부파일 처리 완료: {len(attachment_contents)}개")

        return content
