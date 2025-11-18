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
import zipfile
import io

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

    # 지원 파일 타입 (Upstage 공식 문서 기준)
    # Supported file formats: JPEG, PNG, BMP, PDF, TIFF, HEIC, DOCX, PPTX, XLSX, HWP, HWPX
    SUPPORTED_DOCUMENT_TYPES = {
        '.pdf', '.docx', '.doc', '.pptx', '.ppt',
        '.hwp', '.hwpx',  # ✅ HWPX 추가 (한컴오피스 2014+)
        '.xlsx', '.xls'
    }

    SUPPORTED_IMAGE_TYPES = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
        '.tiff', '.tif',  # ✅ TIFF 추가
        '.heic'  # ✅ HEIC 추가 (Apple 이미지 포맷)
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

                # 2. URL 경로에서 추출 (쿼리 파라미터에서 실제 파일명 추출)
                if not filename:
                    from urllib.parse import urlparse, parse_qs, unquote

                    parsed_url = urlparse(url)
                    query_params = parse_qs(parsed_url.query)

                    # download.php?..., view_image.php?fn=... 같은 프록시 URL 처리
                    # 우선순위: fn > file > 경로
                    actual_filename = None

                    if 'fn' in query_params:
                        # fn 파라미터에서 실제 파일명 추출 (view_image.php)
                        fn_value = query_params['fn'][0]
                        decoded_fn = unquote(fn_value)
                        actual_filename = Path(decoded_fn).name
                        logger.info(f"🔍 프록시 URL 감지 (fn) - 실제 파일명: {actual_filename}")
                    elif 'file' in query_params:
                        # file 파라미터에서 추출 (일부 다운로드 스크립트)
                        file_value = query_params['file'][0]
                        decoded_file = unquote(file_value)
                        actual_filename = Path(decoded_file).name
                        logger.info(f"🔍 프록시 URL 감지 (file) - 실제 파일명: {actual_filename}")

                    if actual_filename:
                        filename = actual_filename
                    else:
                        # 일반 URL: 경로에서 파일명 추출
                        filename = Path(parsed_url.path).name
                        # 쿼리 파라미터 제거
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
                        'application/vnd.hancom.hwp': '.hwp',
                        'application/vnd.hancom.hwpx': '.hwpx',  # ✅ HWPX 추가
                        'application/vnd.ms-powerpoint': '.ppt',
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
                        'application/vnd.ms-excel': '.xls',
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
                    }
                    for mime_type, ext in type_to_ext.items():
                        if mime_type in content_type:
                            filename = f"document{ext}"
                            break

                logger.info(f"📄 최종 파일명: {filename}")

                # 파일 확장자 확인
                file_ext = Path(filename).suffix.lower()

                # 이미지 파일인지 확인
                supported_image_types = [
                    'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
                    'image/bmp', 'image/webp',
                    'image/tiff', 'image/tif',  # ✅ TIFF 추가
                    'image/heic', 'image/heif'  # ✅ HEIC 추가
                ]
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
                # ✅ 100페이지 제한: Synchronous API는 자동으로 첫 100페이지만 처리
                # (공식 문서: For files exceeding 100 pages, the first 100 pages are processed)
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
            # view_image.php 같은 프록시 URL을 실제 이미지 URL로 변환
            actual_url = url
            from urllib.parse import urlparse, parse_qs, unquote

            parsed = urlparse(url)

            # view_image.php?fn=... 처리
            if 'view_image.php' in parsed.path and 'fn' in parse_qs(parsed.query):
                fn_value = parse_qs(parsed.query)['fn'][0]
                decoded_path = unquote(fn_value)  # /data/editor/2511/...png

                # 절대 URL로 변환
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                actual_url = f"{base_url}{decoded_path}"
                logger.info(f"🔍 프록시 URL 변환: view_image.php → {decoded_path}")

            # URL에서 이미지 다운로드 (리다이렉트 따라가기!)
            try:
                file_response = requests.get(actual_url, timeout=30, allow_redirects=True)
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

                # 2. URL 경로 (쿼리 파라미터에서 실제 파일명 추출)
                if not filename:
                    from urllib.parse import urlparse, parse_qs, unquote

                    parsed_url = urlparse(url)
                    query_params = parse_qs(parsed_url.query)

                    # view_image.php?fn=... 같은 프록시 URL 처리
                    if 'fn' in query_params:
                        # fn 파라미터에서 실제 파일명 추출
                        fn_value = query_params['fn'][0]
                        # URL 디코딩 (%2F → /)
                        decoded_fn = unquote(fn_value)
                        # 경로에서 파일명만 추출
                        filename = Path(decoded_fn).name
                        logger.info(f"🔍 프록시 URL 감지 - 실제 파일명: {filename}")
                    else:
                        # 일반 URL: 경로에서 파일명 추출
                        filename = Path(parsed_url.path).name
                        # 쿼리 파라미터 제거
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
                "markdown": "...",  # 표 구조 보존!
                "text": "..."
            },
            "elements": [
                {
                    "category": "heading1",
                    "content": {
                        "html": "<h1>...</h1>",
                        "markdown": "...",
                        "text": "..."
                    }
                }
            ]
        }
        """
        try:
            # 1. content.markdown 우선 (표 구조 보존!)
            if "content" in result:
                content = result["content"]
                if isinstance(content, dict):
                    markdown = content.get("markdown", "")
                    if markdown:
                        logger.info(f"✅ Markdown 사용 (표 구조 보존): {len(markdown)}자")
                        return markdown

            # 2. content.text (markdown 없으면)
            if "content" in result:
                content = result["content"]
                if isinstance(content, dict):
                    text = content.get("text", "")
                    if text:
                        return text

            # 3. elements에서 markdown 우선 추출 (표 구조 보존!)
            if "elements" in result:
                texts = []
                for element in result.get("elements", []):
                    if isinstance(element, dict) and "content" in element:
                        elem_content = element["content"]
                        if isinstance(elem_content, dict):
                            # markdown 우선
                            elem_markdown = elem_content.get("markdown", "")
                            if elem_markdown:
                                texts.append(elem_markdown)
                            else:
                                # markdown 없으면 text 사용
                                elem_text = elem_content.get("text", "")
                                if elem_text:
                                    texts.append(elem_text)

                if texts:
                    logger.info(f"✅ Elements에서 추출 (표 구조 보존 가능): {len(texts)}개 요소")
                    return "\n\n".join(texts)

            # 4. HTML에서 텍스트 추출 (markdown/text 필드가 비어있을 때)
            # Fallback: content.markdown, content.text, elements가 모두 비어있을 때만 사용
            html_texts = []

            # 4-1. content.html에서 추출
            if "content" in result:
                content = result["content"]
                if isinstance(content, dict):
                    html = content.get("html", "")
                    if html:
                        html_text = self._extract_text_from_html(html)
                        if html_text:
                            html_texts.append(html_text)

            # 4-2. elements[].content.html에서 추출
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

            # 5. Fallback: 최상위 text 필드
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
    def process_zip_from_url(self, zip_url: str) -> Dict:
        """
        ZIP 파일 처리 (압축 해제 후 개별 파일 파싱)

        Args:
            zip_url: ZIP 파일 URL

        Returns:
            {
                "successful": [{"filename": "...", "type": "pdf", "text": "..."}],
                "failed": [{"filename": "...", "reason": "..."}],
                "total_files": N
            }
        """
        MAX_ZIP_SIZE = 100 * 1024 * 1024  # 100MB
        MAX_TOTAL_FILES = 50  # ZIP 내 최대 파일 수
        MAX_EXTRACTION_SIZE = 500 * 1024 * 1024  # 압축 해제 후 최대 크기 (500MB, Zip Bomb 방지)

        successful = []
        failed = []

        try:
            logger.info(f"📦 ZIP 파일 다운로드 시작: {zip_url}")

            # 1. ZIP 파일 다운로드
            response = requests.get(zip_url, timeout=30, stream=True)

            if response.status_code != 200:
                logger.error(f"ZIP 다운로드 실패: {response.status_code}")
                return {
                    "successful": [],
                    "failed": [{"filename": zip_url, "reason": f"다운로드 실패: {response.status_code}"}],
                    "total_files": 0
                }

            # 2. 파일 크기 체크
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_ZIP_SIZE:
                logger.warning(f"ZIP 파일이 너무 큼: {content_length} bytes (최대: {MAX_ZIP_SIZE})")
                return {
                    "successful": [],
                    "failed": [{"filename": zip_url, "reason": f"파일 크기 초과: {content_length} bytes"}],
                    "total_files": 0
                }

            # 3. 메모리에 로드
            zip_data = response.content
            logger.info(f"📦 ZIP 파일 다운로드 완료: {len(zip_data)} bytes")

            # 4. ZIP 압축 해제 및 개별 파일 처리
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                file_list = zf.namelist()

                # 파일 개수 체크
                if len(file_list) > MAX_TOTAL_FILES:
                    logger.warning(f"ZIP 내 파일 개수 초과: {len(file_list)} (최대: {MAX_TOTAL_FILES})")
                    return {
                        "successful": [],
                        "failed": [{"filename": zip_url, "reason": f"파일 개수 초과: {len(file_list)}"}],
                        "total_files": len(file_list)
                    }

                logger.info(f"📦 ZIP 내 파일 개수: {len(file_list)}")

                total_extraction_size = 0

                for file_info in zf.infolist():
                    # 디렉토리 스킵
                    if file_info.is_dir():
                        continue

                    filename = file_info.filename
                    file_size = file_info.file_size

                    # 압축 해제 크기 누적 체크 (Zip Bomb 방지)
                    total_extraction_size += file_size
                    if total_extraction_size > MAX_EXTRACTION_SIZE:
                        logger.warning(f"ZIP 압축 해제 크기 초과 (Zip Bomb 의심): {total_extraction_size}")
                        failed.append({
                            "filename": filename,
                            "reason": "ZIP 압축 해제 크기 초과 (Zip Bomb 의심)"
                        })
                        continue

                    try:
                        # 파일 데이터 추출
                        file_data = zf.read(file_info)
                        file_ext = Path(filename).suffix.lower()

                        logger.info(f"  📄 처리 중: {filename} ({file_ext}, {file_size} bytes)")

                        # 지원 형식 확인
                        if file_ext in self.SUPPORTED_DOCUMENT_TYPES:
                            # 문서 파일 처리
                            result = self._process_document_from_bytes(file_data, filename)
                            if result:
                                successful.append(result)
                                logger.info(f"  ✅ 성공: {filename} ({len(result['text'])}자)")
                            else:
                                failed.append({
                                    "filename": filename,
                                    "reason": "문서 파싱 실패 (텍스트 없음)"
                                })
                                logger.warning(f"  ❌ 실패: {filename} (텍스트 없음)")

                        elif file_ext in self.SUPPORTED_IMAGE_TYPES:
                            # 이미지 파일 처리
                            result = self._process_image_from_bytes(file_data, filename)
                            if result:
                                successful.append(result)
                                logger.info(f"  ✅ 성공: {filename} ({len(result['text'])}자)")
                            else:
                                failed.append({
                                    "filename": filename,
                                    "reason": "이미지 OCR 실패 (텍스트 없음)"
                                })
                                logger.warning(f"  ❌ 실패: {filename} (텍스트 없음)")

                        else:
                            # 지원하지 않는 형식
                            failed.append({
                                "filename": filename,
                                "reason": f"지원하지 않는 형식: {file_ext}"
                            })
                            logger.warning(f"  ⏭️  스킵: {filename} (지원하지 않는 형식)")

                    except Exception as e:
                        failed.append({
                            "filename": filename,
                            "reason": str(e)
                        })
                        logger.error(f"  ❌ 에러: {filename} - {e}")

            logger.info(f"📦 ZIP 처리 완료: 성공 {len(successful)}개, 실패 {len(failed)}개")

            return {
                "successful": successful,
                "failed": failed,
                "total_files": len(file_list)
            }

        except zipfile.BadZipFile:
            logger.error(f"손상된 ZIP 파일: {zip_url}")
            return {
                "successful": [],
                "failed": [{"filename": zip_url, "reason": "손상된 ZIP 파일"}],
                "total_files": 0
            }
        except Exception as e:
            logger.error(f"ZIP 처리 에러: {e}")
            return {
                "successful": [],
                "failed": [{"filename": zip_url, "reason": str(e)}],
                "total_files": 0
            }

    def _process_document_from_bytes(self, file_data: bytes, filename: str) -> Optional[Dict]:
        """바이너리 데이터로부터 문서 파싱"""
        try:
            files = {"document": (filename, file_data)}
            data = {
                "model": "document-parse",
                "ocr": "auto"
            }

            response = requests.post(
                self.API_URL,
                headers=self.headers,
                files=files,
                data=data,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                extracted_text = self._extract_text_from_response(result)

                if extracted_text:
                    return {
                        "filename": filename,
                        "type": Path(filename).suffix.lower()[1:],
                        "text": extracted_text,
                        "html": result.get("content", {}).get("html", ""),
                        "from_zip": True
                    }

            return None

        except Exception as e:
            logger.error(f"문서 파싱 실패: {filename} - {e}")
            return None

    def _process_image_from_bytes(self, file_data: bytes, filename: str) -> Optional[Dict]:
        """바이너리 데이터로부터 이미지 OCR"""
        try:
            files = {"document": (filename, file_data)}
            data = {
                "model": "document-parse",
                "ocr": "auto"
            }

            response = requests.post(
                self.API_URL,
                headers=self.headers,
                files=files,
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                extracted_text = self._extract_text_from_response(result)

                if extracted_text:
                    return {
                        "filename": filename,
                        "type": "image",
                        "text": extracted_text,
                        "html": result.get("content", {}).get("html", ""),
                        "from_zip": True
                    }

            return None

        except Exception as e:
            logger.error(f"이미지 OCR 실패: {filename} - {e}")
            return None
