"""
파일 다운로드 유틸리티

HTTP, Data URI 등 다양한 소스에서 파일을 다운로드하는 통합 모듈
"""
import logging
import base64
import re
import requests
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path

logger = logging.getLogger(__name__)


class FileDownloadResult:
    """파일 다운로드 결과"""

    def __init__(
        self,
        content: Optional[bytes],
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        url: Optional[str] = None
    ):
        self.content = content
        self.filename = filename
        self.content_type = content_type
        self.url = url
        self.success = content is not None

    def get_extension(self) -> str:
        """파일 확장자 추출"""
        if self.filename:
            return Path(self.filename).suffix.lstrip('.')
        if self.content_type:
            # MIME type에서 확장자 추정
            mime_to_ext = {
                'image/jpeg': 'jpg',
                'image/png': 'png',
                'image/gif': 'gif',
                'application/pdf': 'pdf',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
                'application/vnd.ms-excel': 'xls',
                'application/zip': 'zip'
            }
            return mime_to_ext.get(self.content_type.split(';')[0].strip(), '')
        return ''


class FileDownloader:
    """
    파일 다운로드 통합 클래스

    지원 기능:
    - HTTP/HTTPS 다운로드
    - Data URI (base64) 디코딩
    - 프록시 URL 변환 (view_image.php, download.php)
    - 세션 기반 다운로드 (인증 우회)
    - Content-Type, Content-Disposition 파싱
    """

    def __init__(self, timeout: int = 30):
        """
        Args:
            timeout: HTTP 요청 타임아웃 (초)
        """
        self.timeout = timeout

    def download(
        self,
        url: str,
        extract_metadata: bool = True
    ) -> FileDownloadResult:
        """
        URL에서 파일 다운로드 (통합 인터페이스)

        Args:
            url: 다운로드할 URL (HTTP, HTTPS, Data URI 지원)
            extract_metadata: 파일명, Content-Type 추출 여부

        Returns:
            FileDownloadResult 객체

        Examples:
            >>> downloader = FileDownloader()
            >>> result = downloader.download("https://example.com/file.pdf")
            >>> if result.success:
            ...     with open(result.filename, 'wb') as f:
            ...         f.write(result.content)
        """
        try:
            # Data URI 처리
            if url.startswith('data:'):
                return self._download_data_uri(url)

            # HTTP/HTTPS 처리
            return self._download_http(url, extract_metadata)

        except Exception as e:
            logger.warning(f"파일 다운로드 실패 ({url[:50]}...): {e}")
            return FileDownloadResult(content=None, url=url)

    def _download_data_uri(self, data_uri: str) -> FileDownloadResult:
        """
        Data URI를 base64 디코딩

        Args:
            data_uri: data:image/png;base64,iVBORw0KGgo... 형식

        Returns:
            FileDownloadResult
        """
        try:
            # data:image/png;base64,<base64_data> 파싱
            if ';base64,' not in data_uri:
                return FileDownloadResult(content=None, url=data_uri)

            parts = data_uri.split(';base64,')
            if len(parts) != 2:
                return FileDownloadResult(content=None, url=data_uri)

            # Content-Type 추출
            content_type = parts[0].replace('data:', '').strip()

            # Base64 디코딩
            base64_data = parts[1]
            content = base64.b64decode(base64_data)

            return FileDownloadResult(
                content=content,
                content_type=content_type,
                url=data_uri
            )

        except Exception as e:
            logger.warning(f"Data URI 디코딩 실패: {e}")
            return FileDownloadResult(content=None, url=data_uri)

    def _download_http(
        self,
        url: str,
        extract_metadata: bool
    ) -> FileDownloadResult:
        """
        HTTP/HTTPS URL에서 파일 다운로드

        Args:
            url: HTTP/HTTPS URL
            extract_metadata: 메타데이터 추출 여부

        Returns:
            FileDownloadResult
        """
        # 프록시 URL 변환
        actual_url = self._resolve_proxy_url(url)

        # 세션 기반 다운로드 필요 여부 확인
        if 'download.php' in url:
            response = self._download_with_session(actual_url)
        else:
            response = requests.get(actual_url, timeout=self.timeout, allow_redirects=True)

        # 응답 검증
        if response.status_code != 200:
            logger.error(f"파일 다운로드 실패 (HTTP {response.status_code}): {url}")
            return FileDownloadResult(content=None, url=url)

        # 메타데이터 추출
        content_type = None
        filename = None

        if extract_metadata:
            content_type = response.headers.get('Content-Type', '').lower()
            filename = self._extract_filename(response, url)

        return FileDownloadResult(
            content=response.content,
            filename=filename,
            content_type=content_type,
            url=url
        )

    def _resolve_proxy_url(self, url: str) -> str:
        """
        프록시 URL을 실제 파일 URL로 변환

        - view_image.php?fn=/data/editor/... → https://site.com/data/editor/...

        Args:
            url: 원본 URL

        Returns:
            변환된 URL
        """
        parsed = urlparse(url)

        # view_image.php?fn=... 처리
        if 'view_image.php' in parsed.path:
            query_params = parse_qs(parsed.query)
            if 'fn' in query_params:
                fn_value = query_params['fn'][0]
                decoded_path = unquote(fn_value)  # /data/editor/2511/...png

                # 절대 URL로 변환
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                actual_url = f"{base_url}{decoded_path}"
                logger.info(f"🔍 프록시 URL 변환: view_image.php → {decoded_path}")
                return actual_url

        return url

    def _download_with_session(self, url: str) -> requests.Response:
        """
        세션 기반 다운로드 (download.php 우회)

        download.php는 세션이 있어야만 다운로드 가능한 경우가 있음.
        게시글을 먼저 방문하여 세션을 생성한 후 다운로드.

        Args:
            url: download.php URL

        Returns:
            requests.Response
        """
        session = requests.Session()
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        try:
            # 1단계: 게시판 메인 페이지 방문
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            if 'bo_table' in params:
                bo_table = params['bo_table'][0]
                board_url = f"{base_url}/bbs/board.php?bo_table={bo_table}"
                logger.info(f"🔗 1단계: 게시판 방문 - {board_url}")
                session.get(board_url, timeout=self.timeout)

            # 2단계: 게시글 방문 (세션 생성)
            if 'bo_table' in params and 'wr_id' in params:
                bo_table = params['bo_table'][0]
                wr_id = params['wr_id'][0]
                post_url = f"{base_url}/bbs/board.php?bo_table={bo_table}&wr_id={wr_id}"
                logger.info(f"🔗 2단계: 글 방문 - {post_url}")
                session.get(post_url, timeout=self.timeout)

            # 3단계: 다운로드 (세션 유지 상태)
            logger.info(f"🔗 3단계: 파일 다운로드 - {url}")
            return session.get(url, timeout=self.timeout, allow_redirects=True)

        finally:
            session.close()

    def _extract_filename(
        self,
        response: requests.Response,
        url: str
    ) -> Optional[str]:
        """
        HTTP 응답에서 파일명 추출

        우선순위:
        1. Content-Disposition 헤더
        2. URL 쿼리 파라미터 (fn, file 등)
        3. URL 경로

        Args:
            response: HTTP 응답
            url: 요청 URL

        Returns:
            파일명 또는 None
        """
        # 1. Content-Disposition 헤더
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            # RFC 5987: filename*=UTF-8''encoded_filename 또는 filename="regular_filename"
            match = re.search(
                r"filename\*=(?:UTF-8'')?([^;]+)|filename=([^;]+)",
                content_disposition
            )
            if match:
                encoded_filename = match.group(1)
                regular_filename = match.group(2)

                if encoded_filename:
                    return unquote(encoded_filename).strip('"\'')
                elif regular_filename:
                    return regular_filename.strip('"\'')

        # 2. URL 쿼리 파라미터
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        # 우선순위: fn > file > 경로
        for param_name in ['fn', 'file', 'filename']:
            if param_name in query_params:
                fn_value = query_params[param_name][0]
                decoded_fn = unquote(fn_value)
                # 경로에서 파일명만 추출
                return Path(decoded_fn).name

        # 3. URL 경로
        path = Path(parsed_url.path)
        if path.name and '.' in path.name:
            return path.name

        return None


# 전역 인스턴스 (편의성)
_default_downloader = None


def get_downloader(timeout: int = 30) -> FileDownloader:
    """
    FileDownloader 인스턴스 반환 (싱글톤)

    Args:
        timeout: HTTP 타임아웃 (초)

    Returns:
        FileDownloader 인스턴스
    """
    global _default_downloader
    if _default_downloader is None:
        _default_downloader = FileDownloader(timeout=timeout)
    return _default_downloader


def download_file(url: str, extract_metadata: bool = True) -> FileDownloadResult:
    """
    파일 다운로드 (편의 함수)

    Args:
        url: 다운로드할 URL
        extract_metadata: 메타데이터 추출 여부

    Returns:
        FileDownloadResult
    """
    return get_downloader().download(url, extract_metadata)
