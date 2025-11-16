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
        total_text_chunks = len(self.text_chunks)
        for idx, chunk in enumerate(self.text_chunks):
            items.append((
                chunk,
                {
                    "title": self.title,
                    "url": self.url,
                    "date": self.date,
                    "content_type": "text",
                    "chunk_index": idx,
                    "total_chunks": total_text_chunks,
                    "source": "original_post"  # 원본 게시글
                }
            ))

        # 2. 이미지 OCR 결과
        for idx, img in enumerate(self.image_contents):
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
                        "image_url": img["url"],
                        "image_index": idx,
                        "source": "image_ocr"  # OCR 결과
                    }
                ))

        # 3. 첨부파일 내용
        for idx, att in enumerate(self.attachment_contents):
            if att["text"]:
                items.append((
                    f"[첨부파일: {att['type'].upper()}]\n{att['text']}",
                    {
                        "title": self.title,
                        "url": self.url,
                        "date": self.date,
                        "content_type": "attachment",
                        "attachment_url": att["url"],
                        "attachment_type": att["type"],
                        "attachment_index": idx,
                        "source": "document_parse"  # Document Parse 결과
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

    def process_images(self, image_urls: List[str], logger=None, category: str = "notice") -> Dict:
        """
        이미지 리스트 처리 (OCR)

        Args:
            image_urls: 이미지 URL 리스트
            logger: 커스텀 로거
            category: 카테고리

        Returns:
            {
                "successful": [{"url": "...", "ocr_text": "..."}],
                "failed": [{"url": "...", "reason": "..."}],
                "unsupported": [{"url": "...", "reason": "..."}],
                "total": N
            }
        """
        if not self.enable_image or not image_urls:
            return {"successful": [], "failed": [], "unsupported": [], "total": 0}

        successful = []
        failed = []
        unsupported = []

        for img_url in image_urls:
            try:
                # 캐시 확인
                cached = self._get_from_cache(img_url)
                if cached:
                    # 캐시에서 가져온 데이터에 url 키 추가 (캐시 메서드에서 제거되므로)
                    cached["url"] = img_url

                    # 캐시된 데이터의 성공 여부 확인
                    if cached.get('ocr_text'):
                        successful.append(cached)
                        if logger:
                            logger.log_multimodal_detail(
                                "이미지 OCR (캐시)",
                                img_url[:50] + "..." if len(img_url) > 50 else img_url,
                                success=True,
                                detail=f"{len(cached.get('ocr_text', ''))}자"
                            )
                    continue

                # Upstage OCR API 호출
                ocr_result = self.upstage_client.extract_text_from_image_url(img_url)

                if ocr_result:
                    text_length = len(ocr_result.get("text", ""))

                    if text_length > 0:
                        # 성공: 텍스트 추출 완료
                        content = {
                            "url": img_url,
                            "ocr_text": ocr_result.get("text", ""),
                            "description": ""
                        }
                        successful.append(content)
                        self._save_to_cache(img_url, content)

                        if logger:
                            url_display = img_url[:50] + "..." if len(img_url) > 50 else img_url
                            logger.log_multimodal_detail(
                                "이미지 OCR",
                                url_display,
                                success=True,
                                detail=f"{text_length}자 추출"
                            )
                    else:
                        # 실패: API는 응답했지만 텍스트 없음
                        failed.append({
                            "url": img_url,
                            "reason": "빈 이미지 또는 텍스트 인식 실패"
                        })
                        if logger:
                            url_display = img_url[:50] + "..." if len(img_url) > 50 else img_url
                            logger.log_multimodal_detail(
                                "이미지 OCR",
                                url_display,
                                success=False,
                                detail="텍스트 없음 (인식 실패)"
                            )
                else:
                    # 실패: API 호출 자체가 실패
                    failed.append({
                        "url": img_url,
                        "reason": "API 호출 실패"
                    })
                    if logger:
                        url_display = img_url[:50] + "..." if len(img_url) > 50 else img_url
                        logger.log_multimodal_detail(
                            "이미지 OCR",
                            url_display,
                            success=False,
                            detail="API 호출 실패"
                        )

            except Exception as e:
                # 예외 발생: 실패로 분류
                error_msg = str(e)

                # 지원하지 않는 형식인지 확인
                if "지원하지 않는" in error_msg or "unsupported" in error_msg.lower():
                    unsupported.append({
                        "url": img_url,
                        "reason": error_msg
                    })
                else:
                    failed.append({
                        "url": img_url,
                        "reason": error_msg
                    })

                if logger:
                    url_display = img_url[:50] + "..." if len(img_url) > 50 else img_url
                    logger.log_multimodal_detail(
                        "이미지 OCR",
                        url_display,
                        success=False,
                        detail=error_msg[:100]
                    )

        return {
            "successful": successful,
            "failed": failed,
            "unsupported": unsupported,
            "total": len(image_urls)
        }

    def process_attachments(self, attachment_urls: List[str], logger=None, category: str = "notice") -> Dict:
        """
        첨부파일 리스트 처리 (Document Parse 또는 OCR)

        이미지 확장자 첨부파일은 OCR로 처리하고,
        문서 확장자는 Document Parse로 처리합니다.

        Args:
            attachment_urls: 첨부파일 URL 리스트
            logger: 커스텀 로거
            category: 카테고리

        Returns:
            {
                "successful": [{"url": "...", "type": "pdf", "text": "..."}],
                "failed": [{"url": "...", "reason": "..."}],
                "unsupported": [{"url": "...", "reason": "..."}],
                "total": N
            }
        """
        if not self.enable_attachment or not attachment_urls:
            return {"successful": [], "failed": [], "unsupported": [], "total": 0}

        successful = []
        failed = []
        unsupported = []

        for att_url in attachment_urls:
            # 이미지 확장자 확인 (대소문자 무관)
            is_image = self.upstage_client.is_image_url(att_url)

            # 이미지 첨부파일은 OCR로 처리
            if is_image:
                # 이미지로 처리 (process_images 로직과 동일)
                try:
                    # 캐시 확인
                    cached = self._get_from_cache(att_url)
                    if cached:
                        cached["url"] = att_url
                        if cached.get('text') or cached.get('ocr_text'):
                            # 이미지는 ocr_text 키 사용, 첨부파일은 text 키 사용
                            text = cached.get('text') or cached.get('ocr_text', '')
                            content = {
                                "url": att_url,
                                "type": "image",
                                "text": text
                            }
                            successful.append(content)
                            if logger:
                                url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                                logger.log_multimodal_detail(
                                    "이미지 첨부 OCR (캐시)",
                                    url_display,
                                    success=True,
                                    detail=f"이미지 - {len(text)}자"
                                )
                        continue

                    # OCR API 호출
                    ocr_result = self.upstage_client.extract_text_from_image_url(att_url)

                    if ocr_result and ocr_result.get("text"):
                        text = ocr_result.get("text", "")
                        content = {
                            "url": att_url,
                            "type": "image",
                            "text": text
                        }
                        successful.append(content)
                        self._save_to_cache(att_url, {"ocr_text": text, "type": "image"})

                        if logger:
                            url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                            logger.log_multimodal_detail(
                                "이미지 첨부 OCR",
                                url_display,
                                success=True,
                                detail=f"이미지 - {len(text)}자 추출"
                            )
                    else:
                        failed.append({
                            "url": att_url,
                            "reason": "OCR 텍스트 추출 실패"
                        })
                        if logger:
                            url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                            logger.log_multimodal_detail(
                                "이미지 첨부 OCR",
                                url_display,
                                success=False,
                                detail="텍스트 없음"
                            )

                except Exception as e:
                    error_msg = str(e)
                    if "지원하지 않는" in error_msg or "unsupported" in error_msg.lower():
                        unsupported.append({
                            "url": att_url,
                            "reason": error_msg
                        })
                    else:
                        failed.append({
                            "url": att_url,
                            "reason": error_msg
                        })

                    if logger:
                        url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                        logger.log_multimodal_detail(
                            "이미지 첨부 OCR",
                            url_display,
                            success=False,
                            detail=error_msg[:100]
                        )

                # 이미지 처리 완료, 다음 첨부파일로
                continue

            # 문서 파일 처리 (PDF, DOCX, HWP 등)
            try:
                # 파일 타입 확인 (download.php 같은 동적 URL은 Content-Type으로 확인)
                # is_document_url은 확장자 체크이므로 일단 시도
                # upstage_client에서 Content-Type 기반 체크함

                # 캐시 확인
                cached = self._get_from_cache(att_url)
                if cached:
                    # 캐시에서 가져온 데이터에 url 키 추가 (캐시 메서드에서 제거되므로)
                    cached["url"] = att_url

                    # 캐시된 데이터의 성공 여부 확인
                    if cached.get('text'):
                        successful.append(cached)
                        if logger:
                            url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                            logger.log_multimodal_detail(
                                "문서 파싱 (캐시)",
                                url_display,
                                success=True,
                                detail=f"{cached.get('type', 'unknown')} - {len(cached.get('text', ''))}자"
                            )
                    continue

                # Upstage Document Parse API 호출
                parse_result = self.upstage_client.parse_document_from_url(att_url)

                if parse_result:
                    text_length = len(parse_result.get("text", ""))
                    file_type = Path(att_url).suffix.lower()[1:] if Path(att_url).suffix else "unknown"

                    if text_length > 0:
                        # 성공: 텍스트 추출 완료
                        content = {
                            "url": att_url,
                            "type": file_type,
                            "text": parse_result.get("text", "")
                        }
                        successful.append(content)
                        self._save_to_cache(att_url, content)

                        if logger:
                            url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                            logger.log_multimodal_detail(
                                "문서 파싱",
                                url_display,
                                success=True,
                                detail=f"{file_type} - {text_length}자 추출"
                            )
                    else:
                        # 실패: API는 응답했지만 텍스트 없음
                        failed.append({
                            "url": att_url,
                            "reason": "빈 문서 또는 텍스트 추출 실패"
                        })
                        if logger:
                            url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                            logger.log_multimodal_detail(
                                "문서 파싱",
                                url_display,
                                success=False,
                                detail=f"{file_type} - 텍스트 없음"
                            )
                else:
                    # 실패: API 호출 자체가 실패
                    failed.append({
                        "url": att_url,
                        "reason": "API 호출 실패"
                    })
                    if logger:
                        url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                        logger.log_multimodal_detail(
                            "문서 파싱",
                            url_display,
                            success=False,
                            detail="API 호출 실패"
                        )

            except Exception as e:
                # 예외 발생: 실패로 분류
                error_msg = str(e)

                # 지원하지 않는 형식인지 확인
                if "지원하지 않는" in error_msg or "unsupported" in error_msg.lower():
                    unsupported.append({
                        "url": att_url,
                        "reason": error_msg
                    })
                else:
                    failed.append({
                        "url": att_url,
                        "reason": error_msg
                    })

                if logger:
                    url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                    logger.log_multimodal_detail(
                        "문서 파싱",
                        url_display,
                        success=False,
                        detail=error_msg[:100]
                    )

        return {
            "successful": successful,
            "failed": failed,
            "unsupported": unsupported,
            "total": len(attachment_urls)
        }

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
        attachment_urls: List[str],
        category: str = "notice",
        logger=None
    ) -> Tuple[MultimodalContent, Dict]:
        """
        멀티모달 콘텐츠 생성 (통합 인터페이스)

        Args:
            title: 게시글 제목
            url: 게시글 URL
            date: 날짜
            text_chunks: 텍스트 청크 리스트
            image_urls: 이미지 URL 리스트
            attachment_urls: 첨부파일 URL 리스트
            category: 카테고리
            logger: 커스텀 로거 (CrawlerLogger)

        Returns:
            (MultimodalContent, {"image_failures": [...], "attachment_failures": [...]})
        """
        content = MultimodalContent(title, url, date)

        # 실패 정보 수집
        failures = {
            "image_failed": [],
            "image_unsupported": [],
            "attachment_failed": [],
            "attachment_unsupported": []
        }

        # 1. 텍스트 추가
        for chunk in text_chunks:
            content.add_text_chunk(chunk)

        # 2. 이미지 처리 및 추가
        if image_urls:
            image_result = self.process_images(image_urls, logger=logger, category=category)
            # 성공한 이미지만 추가
            for img_content in image_result["successful"]:
                content.add_image_content(
                    url=img_content["url"],
                    ocr_text=img_content.get("ocr_text", ""),
                    description=img_content.get("description", "")
                )
            # 실패 정보 저장
            failures["image_failed"] = image_result["failed"]
            failures["image_unsupported"] = image_result["unsupported"]

        # 3. 첨부파일 처리 및 추가
        if attachment_urls:
            attachment_result = self.process_attachments(attachment_urls, logger=logger, category=category)
            # 성공한 첨부파일만 추가
            for att_content in attachment_result["successful"]:
                content.add_attachment_content(
                    url=att_content["url"],
                    file_type=att_content["type"],
                    text=att_content["text"]
                )
            # 실패 정보 저장
            failures["attachment_failed"] = attachment_result["failed"]
            failures["attachment_unsupported"] = attachment_result["unsupported"]

        return content, failures
