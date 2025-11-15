"""
Upstage API 클라이언트
Document Parse, OCR 등 Upstage 서비스 통합
"""
import os
import requests
import logging
from typing import Optional, Dict, List
from pathlib import Path
import time

logger = logging.getLogger(__name__)


class UpstageClient:
    """
    Upstage API 통합 클라이언트

    지원 기능:
    - Document Parse: PDF, DOCX, HWP, PPTX 등
    - OCR: 이미지에서 텍스트 추출
    - Vision: 이미지 설명 생성 (향후 추가 가능)
    """

    # Upstage Document Digitization API (통합 엔드포인트)
    # Document Parse와 OCR 모두 이 엔드포인트 사용, model 파라미터로 구분
    API_URL = "https://api.upstage.ai/v1/document-digitization"

    # 지원 파일 타입
    SUPPORTED_DOCUMENT_TYPES = {
        '.pdf', '.docx', '.doc', '.pptx', '.ppt',
        '.hwp', '.xlsx', '.xls'
    }

    SUPPORTED_IMAGE_TYPES = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'
    }

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3):
        """
        Args:
            api_key: Upstage API 키 (없으면 환경변수에서 로드)
            max_retries: API 실패 시 재시도 횟수
        """
        self.api_key = api_key or os.getenv('UPSTAGE_API_KEY')
        if not self.api_key:
            raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다")

        self.max_retries = max_retries
        self.headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

    def parse_document_from_url(self, url: str) -> Optional[Dict]:
        """
        URL에서 문서를 다운로드하고 Document Parse API로 처리

        Args:
            url: 문서 URL

        Returns:
            {
                "text": "추출된 텍스트",
                "html": "HTML 형식",
                "elements": [...],  # 구조화된 요소들
                "source_url": "..."
            }
            실패 시 None
        """
        try:
            # URL 파일 타입 확인
            file_ext = Path(url).suffix.lower()
            if file_ext not in self.SUPPORTED_DOCUMENT_TYPES:
                logger.warning(f"지원하지 않는 문서 타입: {file_ext}")
                return None

            logger.info(f"📄 Document Parse 시작: {url}")

            # URL에서 파일 다운로드 후 업로드
            try:
                # URL에서 파일 다운로드
                file_response = requests.get(url, timeout=30)
                if file_response.status_code != 200:
                    logger.error(f"파일 다운로드 실패: {url}")
                    return None

                # Upstage Document Parse API 호출 (파일 업로드 방식)
                files = {
                    "document": (Path(url).name, file_response.content)
                }
                data = {
                    "ocr": "auto"  # OCR 자동 활성화 (PDF 내장 텍스트 우선, 필요시 OCR)
                }

                for attempt in range(self.max_retries):
                    try:
                        response = requests.post(
                            self.API_URL,
                            headers=self.headers,
                            files=files,
                            data=data,
                            timeout=60
                        )

                        if response.status_code == 200:
                            result = response.json()

                            # 텍스트 추출 (pages 구조 사용)
                            extracted_text = self._extract_text_from_pages(result)

                            logger.info(f"✅ Document Parse 성공: {len(extracted_text)}자 추출")

                            return {
                                "text": extracted_text,
                                "pages": result.get("pages", []),
                                "elements": result.get("elements", []),
                                "source_url": url
                            }
                        else:
                            logger.warning(f"Document Parse API 오류: {response.status_code} - {response.text[:200]}")

                    except Exception as e:
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"재시도 {attempt + 1}/{self.max_retries} (대기: {wait_time}초)")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"Document Parse 실패: {e}")
                            raise

            except Exception as download_error:
                logger.error(f"파일 다운로드 오류: {download_error}")
                return None

            return None

        except Exception as e:
            logger.error(f"문서 파싱 중 오류: {url} - {e}")
            return None

    def extract_text_from_image_url(self, url: str) -> Optional[Dict]:
        """
        이미지 URL에서 OCR로 텍스트 추출

        Args:
            url: 이미지 URL

        Returns:
            {
                "text": "추출된 텍스트",
                "confidence": 0.95,
                "words": [...]
            }
            실패 시 None
        """
        try:
            # URL 파일 타입 확인
            file_ext = Path(url).suffix.lower()
            if file_ext not in self.SUPPORTED_IMAGE_TYPES:
                logger.warning(f"지원하지 않는 이미지 타입: {file_ext}")
                return None

            logger.info(f"🖼️  OCR 시작: {url}")

            # URL에서 이미지 다운로드
            try:
                file_response = requests.get(url, timeout=30)
                if file_response.status_code != 200:
                    logger.error(f"이미지 다운로드 실패: {url}")
                    return None

                # Upstage OCR API 호출 (파일 업로드 방식)
                # 이미지 파일은 document-digitization API로 자동 OCR 처리
                files = {
                    "document": (Path(url).name, file_response.content)
                }
                # 이미지 파일을 보내면 자동으로 OCR 처리됨 (별도 파라미터 불필요)
                data = {}

                for attempt in range(self.max_retries):
                    try:
                        response = requests.post(
                            self.API_URL,
                            headers=self.headers,
                            files=files,
                            data=data if data else None,
                            timeout=30
                        )

                        if response.status_code == 200:
                            result = response.json()

                            # OCR 결과에서 텍스트 추출 (pages 구조 사용)
                            extracted_text = self._extract_text_from_pages(result)

                            if extracted_text:
                                logger.info(f"✅ OCR 성공: {len(extracted_text)}자 추출")

                                return {
                                    "text": extracted_text,
                                    "confidence": result.get("confidence", 1.0),
                                    "pages": result.get("pages", []),
                                    "source_url": url
                                }
                            else:
                                logger.warning("OCR 결과가 비어있음")
                                return None
                        else:
                            logger.warning(f"OCR API 오류: {response.status_code} - {response.text[:200]}")

                    except Exception as e:
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"재시도 {attempt + 1}/{self.max_retries} (대기: {wait_time}초)")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"OCR 실패: {e}")
                            raise

            except Exception as download_error:
                logger.error(f"이미지 다운로드 오류: {download_error}")
                return None

            return None

        except Exception as e:
            logger.error(f"이미지 OCR 중 오류: {url} - {e}")
            return None

    def _extract_text_from_pages(self, result: Dict) -> str:
        """
        Upstage API 응답에서 텍스트 추출 (pages 구조 사용)

        응답 구조:
        {
            "pages": [
                {
                    "id": 1,
                    "text": "페이지 텍스트...",
                    ...
                }
            ]
        }
        """
        try:
            texts = []

            # pages 배열에서 텍스트 추출
            for page in result.get("pages", []):
                if isinstance(page, dict):
                    page_text = page.get("text", "")
                    if page_text:
                        texts.append(page_text)

            if texts:
                return "\n\n".join(texts)

            # Fallback: content.text 시도
            if "content" in result:
                content = result["content"]
                if isinstance(content, dict):
                    return content.get("text", "")
                elif isinstance(content, str):
                    return content

            # Fallback: text 필드 직접 시도
            if "text" in result:
                return result["text"]

            logger.warning("응답에서 텍스트를 찾을 수 없음")
            return ""

        except Exception as e:
            logger.error(f"텍스트 추출 오류: {e}")
            return ""

    def is_document_url(self, url: str) -> bool:
        """URL이 지원되는 문서 타입인지 확인"""
        file_ext = Path(url).suffix.lower()
        return file_ext in self.SUPPORTED_DOCUMENT_TYPES

    def is_image_url(self, url: str) -> bool:
        """URL이 지원되는 이미지 타입인지 확인"""
        file_ext = Path(url).suffix.lower()
        return file_ext in self.SUPPORTED_IMAGE_TYPES
