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
            logger.info(f"📄 Document Parse 시작: {url}")

            # URL에서 파일 다운로드 후 업로드
            try:
                # URL에서 파일 다운로드
                file_response = requests.get(url, timeout=30)
                if file_response.status_code != 200:
                    logger.error(f"파일 다운로드 실패: {url}")
                    return None

                # Content-Type과 Content-Disposition에서 파일 정보 추출
                content_type = file_response.headers.get('Content-Type', '').lower()
                content_disposition = file_response.headers.get('Content-Disposition', '')

                # 실제 파일명 추출 (Content-Disposition 헤더에서)
                filename = Path(url).name  # 기본값
                if 'filename=' in content_disposition:
                    import re
                    match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition)
                    if match:
                        filename = match.group(1).strip('"\'')

                # Content-Type으로 문서 타입 확인
                supported_types = [
                    'application/pdf',
                    'application/msword',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/vnd.ms-powerpoint',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'application/vnd.ms-excel',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/x-hwp',  # HWP
                    'application/haansofthwp',  # HWP
                ]

                # 파일 확장자로도 체크
                file_ext = Path(filename).suffix.lower()
                is_supported = (
                    any(t in content_type for t in supported_types) or
                    file_ext in self.SUPPORTED_DOCUMENT_TYPES
                )

                if not is_supported:
                    logger.warning(f"지원하지 않는 파일 타입: {content_type}, 확장자: {file_ext}")
                    logger.warning(f"URL: {url}")
                    logger.warning(f"파일명: {filename}")
                    return None

                logger.info(f"📄 파일 다운로드 성공: {filename} ({content_type})")

                # Upstage Document Parse API 호출 (파일 업로드 방식)
                files = {
                    "document": (filename, file_response.content)
                }
                data = {
                    "model": "document-parse",  # 필수!
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

                            # 디버깅: API 응답 구조 로깅
                            logger.info(f"📊 Document Parse API 응답 키: {list(result.keys())}")

                            # 텍스트 추출 (공식 문서 응답 구조 사용)
                            extracted_text = self._extract_text_from_response(result)

                            if extracted_text:
                                logger.info(f"✅ Document Parse 성공: {len(extracted_text)}자 추출")
                            else:
                                logger.warning(f"⚠️  텍스트 추출 실패. 응답 구조: {result}")

                            return {
                                "text": extracted_text,
                                "html": result.get("content", {}).get("html", ""),
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
            logger.info(f"🖼️  OCR 시작: {url}")

            # URL에서 이미지 다운로드
            try:
                file_response = requests.get(url, timeout=30)
                if file_response.status_code != 200:
                    logger.error(f"이미지 다운로드 실패: {url}")
                    return None

                # Content-Type 확인
                content_type = file_response.headers.get('Content-Type', '').lower()
                content_disposition = file_response.headers.get('Content-Disposition', '')

                # 실제 파일명 추출
                filename = Path(url).name
                if 'filename=' in content_disposition:
                    import re
                    match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition)
                    if match:
                        filename = match.group(1).strip('"\'')

                # 이미지 타입 확인
                supported_image_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']
                file_ext = Path(filename).suffix.lower()

                is_image = (
                    any(t in content_type for t in supported_image_types) or
                    file_ext in self.SUPPORTED_IMAGE_TYPES
                )

                if not is_image:
                    logger.warning(f"이미지가 아님: {content_type}, 확장자: {file_ext}, URL: {url}")
                    return None

                # 파일 크기 확인 (너무 작으면 손상되었을 가능성)
                content_length = len(file_response.content)
                if content_length < 100:
                    logger.warning(f"이미지 파일이 너무 작음 ({content_length} bytes): {url}")
                    return None

                logger.info(f"🖼️  이미지 다운로드 성공: {filename} ({content_type}, {content_length} bytes)")

                # Upstage OCR API 호출 (파일 업로드 방식)
                # 이미지도 document-parse 모델로 처리 (자동 OCR)
                files = {
                    "document": (filename, file_response.content)
                }
                data = {
                    "model": "document-parse",  # 필수! 이미지도 document-parse 사용
                    "ocr": "auto"
                }

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

                            # 디버깅: API 응답 구조 로깅
                            logger.info(f"📊 OCR API 응답 키: {list(result.keys())}")

                            # OCR 결과에서 텍스트 추출 (공식 문서 응답 구조 사용)
                            extracted_text = self._extract_text_from_response(result)

                            if extracted_text:
                                logger.info(f"✅ OCR 성공: {len(extracted_text)}자 추출")

                                return {
                                    "text": extracted_text,
                                    "html": result.get("content", {}).get("html", ""),
                                    "elements": result.get("elements", []),
                                    "source_url": url
                                }
                            else:
                                logger.warning("⚠️  OCR 결과가 비어있음")
                                logger.warning(f"응답 전체 구조: {result}")
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

    def _extract_text_from_response(self, result: Dict) -> str:
        """
        Upstage Document Parse API 응답에서 텍스트 추출

        공식 문서 응답 구조:
        {
            "content": {
                "html": "<h1>...</h1>",
                "markdown": "...",
                "text": "..."
            },
            "elements": [
                {
                    "category": "heading1",
                    "content": {
                        "html": "<h1>...</h1>",
                        "text": "..."
                    }
                }
            ]
        }
        """
        try:
            # 1. content.text 우선 (전체 텍스트)
            if "content" in result:
                content = result["content"]
                if isinstance(content, dict):
                    text = content.get("text", "")
                    if text:
                        return text

            # 2. elements에서 텍스트 추출
            if "elements" in result:
                texts = []
                for element in result.get("elements", []):
                    if isinstance(element, dict) and "content" in element:
                        elem_content = element["content"]
                        if isinstance(elem_content, dict):
                            elem_text = elem_content.get("text", "")
                            if elem_text:
                                texts.append(elem_text)

                if texts:
                    return "\n\n".join(texts)

            # 3. Fallback: 최상위 text 필드
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
