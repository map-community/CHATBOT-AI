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
                # download.php의 경우 세션 유지가 필요 (봇 차단 우회)
                if 'download.php' in url:
                    from urllib.parse import urlparse, parse_qs

                    # URL 파싱
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)

                    # 세션 생성
                    session = requests.Session()
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })

                    # 베이스 URL
                    base_url = f"{parsed.scheme}://{parsed.netloc}"

                    # 1단계: 게시판 방문 (bo_table만)
                    if 'bo_table' in params:
                        bo_table = params['bo_table'][0]
                        board_url = f"{base_url}/bbs/board.php?bo_table={bo_table}"
                        logger.info(f"🔗 1단계: 게시판 방문 - {board_url}")
                        session.get(board_url, timeout=30)

                    # 2단계: 글 방문 (bo_table + wr_id)
                    if 'bo_table' in params and 'wr_id' in params:
                        bo_table = params['bo_table'][0]
                        wr_id = params['wr_id'][0]
                        post_url = f"{base_url}/bbs/board.php?bo_table={bo_table}&wr_id={wr_id}"
                        logger.info(f"🔗 2단계: 글 방문 - {post_url}")
                        session.get(post_url, timeout=30)

                    # 3단계: 다운로드 (세션 유지 상태)
                    logger.info(f"🔗 3단계: 파일 다운로드 - {url}")
                    file_response = session.get(url, timeout=30, allow_redirects=True)
                else:
                    # 일반 URL은 직접 다운로드
                    file_response = requests.get(url, timeout=30, allow_redirects=True)

                if file_response.status_code != 200:
                    logger.error(f"파일 다운로드 실패: {url}")
                    return None

                # Content-Type과 Content-Disposition에서 파일 정보 추출
                content_type = file_response.headers.get('Content-Type', '').lower()
                content_disposition = file_response.headers.get('Content-Disposition', '')

                logger.info(f"📊 응답 정보: Content-Type={content_type}, Content-Disposition={content_disposition}")

                # 실제 파일명 추출 (우선순위: Content-Disposition > URL 경로)
                filename = None

                # 1. Content-Disposition 헤더에서 파일명 추출 (가장 신뢰성 높음)
                if 'filename=' in content_disposition:
                    import re
                    # RFC 5987: filename*=UTF-8''encoded_filename 또는 filename="regular_filename"
                    match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)|filename=([^;]+)", content_disposition)
                    if match:
                        encoded_filename = match.group(1)
                        regular_filename = match.group(2)

                        if encoded_filename:
                            # URL 디코딩
                            from urllib.parse import unquote
                            filename = unquote(encoded_filename).strip('"\'')
                        elif regular_filename:
                            filename = regular_filename.strip('"\'')

                # 2. URL 경로에서 추출 (쿼리 파라미터 제거!)
                if not filename:
                    filename = Path(url).name
                    # 쿼리 파라미터 제거 (download.php?... → download.php)
                    if '?' in filename:
                        filename = filename.split('?')[0]

                # 3. Content-Type에서 확장자 유추 (최후의 수단)
                if not filename or filename == 'download.php' or not Path(filename).suffix:
                    type_to_ext = {
                        'application/pdf': '.pdf',
                        'application/msword': '.doc',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                        'application/x-hwp': '.hwp',
                        'application/haansofthwp': '.hwp',
                        'application/vnd.ms-powerpoint': '.ppt',
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx'
                    }
                    for mime_type, ext in type_to_ext.items():
                        if mime_type in content_type:
                            filename = f"document{ext}"
                            break

                logger.info(f"📄 최종 파일명: {filename}")

                # 파일 확장자 확인
                file_ext = Path(filename).suffix.lower()

                # 이미지 파일인지 확인
                supported_image_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']
                is_image = (
                    any(t in content_type for t in supported_image_types) or
                    file_ext in self.SUPPORTED_IMAGE_TYPES
                )

                # 이미지 파일이면 OCR로 자동 전환
                if is_image:
                    logger.info(f"📊 이미지 파일 감지 ({file_ext}) - OCR로 전환")

                    # OCR API 호출 (이미 다운로드한 파일 사용)
                    files = {
                        "document": (filename, file_response.content)
                    }
                    data_param = {
                        "model": "document-parse",
                        "ocr": "auto"
                    }

                    for attempt in range(self.max_retries):
                        try:
                            response = requests.post(
                                self.API_URL,
                                headers=self.headers,
                                files=files,
                                data=data_param,
                                timeout=30
                            )

                            if response.status_code == 200:
                                result = response.json()
                                logger.info(f"📊 OCR API 응답 키: {list(result.keys())}")

                                extracted_text = self._extract_text_from_response(result)

                                if extracted_text:
                                    logger.info(f"✅ OCR 성공 (이미지 첨부파일): {len(extracted_text)}자 추출")
                                    return {
                                        "text": extracted_text,
                                        "html": result.get("content", {}).get("html", ""),
                                        "full_html": result.get("content", {}).get("html", ""),
                                        "elements": result.get("elements", []),
                                        "source_url": url
                                    }
                                else:
                                    logger.warning("⚠️  OCR 결과가 비어있음 (이미지 첨부파일)")
                                    return None
                            else:
                                logger.warning(f"OCR API 오류: {response.status_code} - {response.text[:200]}")

                        except Exception as e:
                            if attempt < self.max_retries - 1:
                                wait_time = 2 ** attempt
                                logger.warning(f"재시도 {attempt + 1}/{self.max_retries} (대기: {wait_time}초)")
                                time.sleep(wait_time)
                            else:
                                logger.error(f"OCR 실패 (이미지 첨부파일): {e}")
                                raise

                    return None

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

                # 문서 타입 확인
                is_supported = (
                    any(t in content_type for t in supported_types) or
                    file_ext in self.SUPPORTED_DOCUMENT_TYPES
                )

                if not is_supported:
                    logger.warning(f"지원하지 않는 파일 타입: {content_type}, 확장자: {file_ext}")
                    logger.warning(f"URL: {url}")
                    logger.warning(f"파일명: {filename}")
                    return None

                # 파일명이 길면 줄임
                display_name = filename if len(filename) <= 30 else f"{filename[:27]}..."
                logger.info(f"📄 다운로드 성공: {display_name}")

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

                            # RAG용으로 텍스트와 HTML 둘 다 반환
                            return {
                                "text": extracted_text,  # 검색용 순수 텍스트
                                "html": result.get("content", {}).get("html", ""),  # 구조 보존용 HTML
                                "full_html": result.get("content", {}).get("html", ""),  # 원본 HTML (별칭)
                                "markdown": result.get("content", {}).get("markdown", ""),  # Markdown (있으면)
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
            # Data URI는 짧게 로깅
            if url.startswith('data:'):
                log_url = "Data URI (Base64 이미지)"
            else:
                log_url = url[:100] + "..." if len(url) > 100 else url
            logger.info(f"🖼️  OCR 시작: {log_url}")

            # Data URI Scheme 처리 (data:image/png;base64,...)
            if url.startswith('data:'):
                try:
                    import base64
                    import re

                    logger.info("📊 Data URI 감지 - Base64 디코딩 시작")

                    # Data URI 파싱: data:[<mediatype>][;base64],<data>
                    match = re.match(r'data:([^;]+);base64,(.+)', url)
                    if not match:
                        logger.error("Data URI 형식이 올바르지 않음 (base64 인코딩 필요)")
                        return None

                    mime_type = match.group(1)  # image/png, image/jpeg 등
                    base64_data = match.group(2)

                    # MIME 타입 확인
                    supported_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']
                    if mime_type not in supported_types:
                        logger.warning(f"지원하지 않는 이미지 타입: {mime_type}")
                        return None

                    # Base64 디코딩
                    image_data = base64.b64decode(base64_data)
                    data_length = len(image_data)

                    # 파일 크기 확인
                    if data_length < 100:
                        logger.warning(f"이미지 데이터가 너무 작음 ({data_length} bytes)")
                        return None

                    # 확장자 결정
                    ext_map = {
                        'image/jpeg': '.jpg',
                        'image/jpg': '.jpg',
                        'image/png': '.png',
                        'image/gif': '.gif',
                        'image/bmp': '.bmp',
                        'image/webp': '.webp'
                    }
                    extension = ext_map.get(mime_type, '.jpg')
                    filename = f"data_uri_image{extension}"

                    logger.info(f"📊 디코딩 성공: {mime_type}, {data_length} bytes")

                    # Upstage OCR API 호출
                    files = {
                        "document": (filename, image_data)
                    }
                    data_param = {
                        "model": "document-parse",
                        "ocr": "auto"
                    }

                    for attempt in range(self.max_retries):
                        try:
                            response = requests.post(
                                self.API_URL,
                                headers=self.headers,
                                files=files,
                                data=data_param,
                                timeout=30
                            )

                            if response.status_code == 200:
                                result = response.json()

                                # 디버깅: API 응답 구조 로깅
                                logger.info(f"📊 OCR API 응답 키: {list(result.keys())}")

                                # OCR 결과에서 텍스트 추출
                                extracted_text = self._extract_text_from_response(result)

                                if extracted_text:
                                    logger.info(f"✅ OCR 성공 (Data URI): {len(extracted_text)}자 추출")

                                    # RAG용으로 텍스트와 HTML 둘 다 반환
                                    return {
                                        "text": extracted_text,
                                        "html": result.get("content", {}).get("html", ""),
                                        "full_html": result.get("content", {}).get("html", ""),
                                        "elements": result.get("elements", []),
                                        "source_url": "data_uri"  # Data URI는 너무 길어서 "data_uri"로 표시
                                    }
                                else:
                                    logger.warning("⚠️  OCR 결과가 비어있음 (Data URI)")
                                    return None
                            else:
                                logger.warning(f"OCR API 오류: {response.status_code} - {response.text[:200]}")

                        except Exception as e:
                            if attempt < self.max_retries - 1:
                                wait_time = 2 ** attempt
                                logger.warning(f"재시도 {attempt + 1}/{self.max_retries} (대기: {wait_time}초)")
                                time.sleep(wait_time)
                            else:
                                logger.error(f"OCR 실패 (Data URI): {e}")
                                raise

                    return None

                except Exception as data_uri_error:
                    logger.error(f"Data URI 처리 오류: {data_uri_error}")
                    return None

            # 일반 HTTP/HTTPS URL 처리
            # URL에서 이미지 다운로드 (리다이렉트 따라가기!)
            try:
                file_response = requests.get(url, timeout=30, allow_redirects=True)
                if file_response.status_code != 200:
                    log_url = url[:100] + "..." if len(url) > 100 else url
                    logger.error(f"이미지 다운로드 실패: {log_url}")
                    return None

                # Content-Type 확인
                content_type = file_response.headers.get('Content-Type', '').lower()
                content_disposition = file_response.headers.get('Content-Disposition', '')

                # 실제 파일명 추출 (우선순위: Content-Disposition > URL 경로)
                filename = None

                # 1. Content-Disposition 헤더
                if 'filename=' in content_disposition:
                    import re
                    match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)|filename=([^;]+)", content_disposition)
                    if match:
                        encoded_filename = match.group(1)
                        regular_filename = match.group(2)

                        if encoded_filename:
                            from urllib.parse import unquote
                            filename = unquote(encoded_filename).strip('"\'')
                        elif regular_filename:
                            filename = regular_filename.strip('"\'')

                # 2. URL 경로 (쿼리 파라미터 제거)
                if not filename:
                    filename = Path(url).name
                    if '?' in filename:
                        filename = filename.split('?')[0]

                # 이미지 타입 확인
                supported_image_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']
                file_ext = Path(filename).suffix.lower()

                is_image = (
                    any(t in content_type for t in supported_image_types) or
                    file_ext in self.SUPPORTED_IMAGE_TYPES
                )

                if not is_image:
                    log_url = url[:100] + "..." if len(url) > 100 else url
                    logger.warning(f"이미지가 아님: {content_type}, 확장자: {file_ext}, URL: {log_url}")
                    return None

                # 파일 크기 확인 (너무 작으면 손상되었을 가능성)
                content_length = len(file_response.content)
                if content_length < 100:
                    log_url = url[:100] + "..." if len(url) > 100 else url
                    logger.warning(f"이미지 파일이 너무 작음 ({content_length} bytes): {log_url}")
                    return None

                # 파일명이 길면 줄임
                display_name = filename if len(filename) <= 30 else f"{filename[:27]}..."
                logger.info(f"📊 다운로드 성공: {display_name}, {content_length} bytes")

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

                                # RAG용으로 텍스트와 HTML 둘 다 반환
                                return {
                                    "text": extracted_text,  # 검색용 순수 텍스트
                                    "html": result.get("content", {}).get("html", ""),  # 구조 보존용 HTML
                                    "full_html": result.get("content", {}).get("html", ""),  # 원본 HTML (별칭)
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
            # Data URI는 짧게 로깅
            if url.startswith('data:'):
                log_url = "Data URI (Base64 이미지)"
            else:
                log_url = url[:100] + "..." if len(url) > 100 else url
            logger.error(f"이미지 OCR 중 오류: {log_url} - {e}")
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

            # 3. HTML에서 텍스트 추출 (text 필드가 비어있을 때)
            # content.text와 elements[].content.text가 비어있어도 HTML에 텍스트가 있을 수 있음
            html_texts = []

            # 3-1. content.html에서 추출
            if "content" in result:
                content = result["content"]
                if isinstance(content, dict):
                    html = content.get("html", "")
                    if html:
                        html_text = self._extract_text_from_html(html)
                        if html_text:
                            html_texts.append(html_text)

            # 3-2. elements[].content.html에서 추출
            if "elements" in result and not html_texts:
                for element in result.get("elements", []):
                    if isinstance(element, dict) and "content" in element:
                        elem_content = element["content"]
                        if isinstance(elem_content, dict):
                            elem_html = elem_content.get("html", "")
                            if elem_html:
                                elem_text = self._extract_text_from_html(elem_html)
                                if elem_text:
                                    html_texts.append(elem_text)

            if html_texts:
                return "\n\n".join(html_texts)

            # 4. Fallback: 최상위 text 필드
            if "text" in result:
                return result["text"]

            logger.warning("응답에서 텍스트를 찾을 수 없음")
            return ""

        except Exception as e:
            logger.error(f"텍스트 추출 오류: {e}")
            return ""

    def _extract_text_from_html(self, html: str) -> str:
        """
        HTML에서 텍스트 추출 (BeautifulSoup 사용)

        Upstage API가 text 필드를 비워두고 HTML만 제공하는 경우가 있음
        특히 이미지 OCR 결과의 경우 <img alt="..."> 속성에 텍스트가 들어있음

        Args:
            html: HTML 문자열

        Returns:
            추출된 텍스트
        """
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, 'html.parser')

            # 텍스트 추출 전략:
            # 1. img[alt] 속성 우선 (OCR 결과)
            # 2. 모든 텍스트 노드 추출 (구조 유지)

            texts = []

            # 1. img 태그의 alt 속성에서 추출 (OCR 결과가 여기 들어있을 수 있음)
            for img in soup.find_all('img'):
                alt_text = img.get('alt', '').strip()
                if alt_text and alt_text != 'x':  # 'x'는 의미없는 플레이스홀더
                    texts.append(alt_text)

            # 2. h1, h2, p, li 등 구조화된 텍스트 추출 (순서 유지)
            for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'td', 'th']):
                elem_text = elem.get_text(strip=True)
                if elem_text:
                    # 중복 방지: alt에서 이미 추출한 텍스트는 제외
                    if not any(elem_text in existing for existing in texts):
                        texts.append(elem_text)

            # 3. 위에서 추출 못했으면 전체 텍스트 추출
            if not texts:
                body_text = soup.get_text(separator='\n', strip=True)
                if body_text:
                    texts.append(body_text)

            return '\n\n'.join(texts)

        except Exception as e:
            logger.warning(f"HTML 텍스트 추출 오류: {e}")
            return ""

    def is_document_url(self, url: str) -> bool:
        """URL이 지원되는 문서 타입인지 확인"""
        file_ext = Path(url).suffix.lower()
        return file_ext in self.SUPPORTED_DOCUMENT_TYPES

    def is_image_url(self, url: str) -> bool:
        """URL이 지원되는 이미지 타입인지 확인"""
        file_ext = Path(url).suffix.lower()
        return file_ext in self.SUPPORTED_IMAGE_TYPES
