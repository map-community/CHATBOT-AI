"""
멀티모달 콘텐츠 처리
이미지, 첨부파일 등 비텍스트 콘텐츠를 RAG에 활용 가능하도록 변환
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import hashlib
from typing import List, Tuple, Dict, Optional
from pymongo import MongoClient
from config import CrawlerConfig
from processing.upstage_client import UpstageClient
from utils.file_downloader import download_file

logger = logging.getLogger(__name__)


class CharacterTextSplitter:
    """
    텍스트 분할기

    긴 텍스트를 chunk_size 단위로 분할하며,
    chunk_overlap 만큼 겹치도록 분할
    """

    def __init__(self, chunk_size: int = 850, chunk_overlap: int = 100):
        """
        Args:
            chunk_size: 청크 크기
            chunk_overlap: 청크 간 겹침 크기
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        """
        텍스트 분할

        Args:
            text: 분할할 텍스트

        Returns:
            분할된 텍스트 리스트
        """
        chunks = []

        if len(text) <= self.chunk_size:
            return [text]

        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunk = text[i:i + self.chunk_size]
            if chunk:
                chunks.append(chunk)

        return chunks


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

    @staticmethod
    def _html_table_to_markdown(html: str) -> str:
        """
        HTML 테이블을 Markdown 테이블로 변환 (캐시 데이터 활용용)

        Args:
            html: HTML 문자열 (테이블 포함)

        Returns:
            Markdown 테이블 문자열 (테이블 없으면 빈 문자열)
        """
        from bs4 import BeautifulSoup

        try:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')

            if not tables:
                return ""

            markdown_tables = []
            for table in tables:
                rows = table.find_all('tr')
                if not rows:
                    continue

                # 첫 행을 헤더로 사용
                first_row = rows[0]
                headers = [cell.get_text(strip=True) for cell in first_row.find_all(['th', 'td'])]

                if not headers:
                    continue

                # Markdown 테이블 생성
                md_table = "| " + " | ".join(headers) + " |\n"
                md_table += "|" + "|".join([" --- " for _ in headers]) + "|\n"

                # 데이터 행 (첫 행이 헤더가 아닌 경우도 고려)
                data_rows = rows[1:] if len(rows) > 1 else []
                for row in data_rows:
                    cells = [cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]
                    # 셀 개수가 헤더와 다르면 패딩
                    while len(cells) < len(headers):
                        cells.append("")
                    md_table += "| " + " | ".join(cells[:len(headers)]) + " |\n"

                markdown_tables.append(md_table)

            return "\n\n".join(markdown_tables)
        except Exception as e:
            # 변환 실패 시 빈 문자열 반환
            return ""

    def add_image_content(self, url: str, ocr_text: str = "", ocr_html: str = "", ocr_elements: List = None, description: str = ""):
        """이미지 콘텐츠 추가 (캐시 HTML → Markdown 변환)"""
        # HTML 테이블이 있으면 markdown으로 변환하여 텍스트 앞에 추가
        final_text = ocr_text
        if ocr_html and '<table' in ocr_html.lower():
            table_markdown = self._html_table_to_markdown(ocr_html)
            if table_markdown:
                # 테이블 markdown을 텍스트 앞에 추가 (구조 보존!)
                final_text = table_markdown + "\n\n" + ocr_text

        self.image_contents.append({
            "url": url,
            "ocr_text": final_text,  # markdown 테이블 포함!
            "ocr_html": ocr_html,  # 원본 HTML (참고용)
            "ocr_elements": ocr_elements or [],
            "description": description
        })

    def add_attachment_content(self, url: str, file_type: str, text: str, html: str = "", elements: List = None):
        """첨부파일 콘텐츠 추가 (캐시 HTML → Markdown 변환)"""
        # HTML 테이블이 있으면 markdown으로 변환하여 텍스트 앞에 추가
        final_text = text
        if html and '<table' in html.lower():
            table_markdown = self._html_table_to_markdown(html)
            if table_markdown:
                # 테이블 markdown을 텍스트 앞에 추가 (구조 보존!)
                final_text = table_markdown + "\n\n" + text

        self.attachment_contents.append({
            "url": url,
            "type": file_type,
            "text": final_text,  # markdown 테이블 포함!
            "html": html,  # 원본 HTML (참고용)
            "elements": elements or []
        })

    def to_embedding_items(self) -> List[Tuple[str, Dict]]:
        """
        임베딩할 항목들로 변환 (청킹 포함)

        Returns:
            [(text, metadata), ...]
        """
        items = []

        # 텍스트 분할기 초기화 (베스트 프랙티스: 850자 청킹)
        text_splitter = CharacterTextSplitter(
            chunk_size=CrawlerConfig.CHUNK_SIZE,
            chunk_overlap=CrawlerConfig.CHUNK_OVERLAP
        )

        # 1. 텍스트 청크 (이미 청킹되어 있음)
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

        # 2. 이미지 OCR 결과 (🔧 청킹 추가!)
        for idx, img in enumerate(self.image_contents):
            if img["ocr_text"]:
                # OCR 텍스트 준비
                combined_text = f"[이미지 텍스트]\n{img['ocr_text']}"

                # 설명도 있으면 추가
                if img["description"]:
                    combined_text += f"\n\n[이미지 설명]\n{img['description']}"

                # 🚨 Data URI 처리 (232KB 문자열을 메타데이터에 넣지 않음!)
                img_url = img["url"]
                is_data_uri = img_url.startswith('data:')

                # Pinecone 메타데이터용: Data URI면 플래그만, 일반 URL이면 전체 저장
                if is_data_uri:
                    # Data URI는 저장하지 않음 (MongoDB에만 보관)
                    image_metadata = {
                        "is_data_uri": True,
                        "image_index": idx  # MongoDB 조회용
                    }
                else:
                    # 일반 URL은 저장 (크기 작음)
                    image_metadata = {
                        "image_url": img_url,
                        "image_index": idx
                    }

                # ✅ 긴 텍스트는 청킹! (베스트 프랙티스)
                if len(combined_text) > CrawlerConfig.CHUNK_SIZE:
                    chunks = text_splitter.split_text(combined_text)
                    for chunk_idx, chunk in enumerate(chunks):
                        items.append((
                            chunk,
                            {
                                "title": self.title,
                                "url": self.url,
                                "date": self.date,
                                "content_type": "image",
                                **image_metadata,  # Data URI 처리된 메타데이터
                                "chunk_index": chunk_idx,
                                "total_chunks": len(chunks),
                                "source": "image_ocr",  # OCR 결과
                                "html_available": bool(img.get("ocr_html"))
                            }
                        ))
                else:
                    # 짧은 텍스트는 그대로
                    items.append((
                        combined_text,
                        {
                            "title": self.title,
                            "url": self.url,
                            "date": self.date,
                            "content_type": "image",
                            **image_metadata,  # Data URI 처리된 메타데이터
                            "source": "image_ocr",
                            "html_available": bool(img.get("ocr_html"))
                        }
                    ))

        # 3. 첨부파일 내용 (🔧 청킹 추가!)
        for idx, att in enumerate(self.attachment_contents):
            if att["text"]:
                full_text = f"[첨부파일: {att['type'].upper()}]\n{att['text']}"

                # 🚨 Data URI 처리 (첨부파일도 Data URI 가능)
                att_url = att["url"]
                is_data_uri = att_url.startswith('data:')

                # Pinecone 메타데이터용: Data URI면 플래그만, 일반 URL이면 전체 저장
                if is_data_uri:
                    # Data URI는 저장하지 않음 (MongoDB에만 보관)
                    attachment_metadata = {
                        "is_data_uri": True,
                        "attachment_type": att["type"],
                        "attachment_index": idx  # MongoDB 조회용
                    }
                else:
                    # 일반 URL은 저장 (크기 작음)
                    attachment_metadata = {
                        "attachment_url": att_url,
                        "attachment_type": att["type"],
                        "attachment_index": idx
                    }

                # ✅ 긴 텍스트는 청킹! (베스트 프랙티스)
                if len(full_text) > CrawlerConfig.CHUNK_SIZE:
                    chunks = text_splitter.split_text(full_text)
                    for chunk_idx, chunk in enumerate(chunks):
                        items.append((
                            chunk,
                            {
                                "title": self.title,
                                "url": self.url,
                                "date": self.date,
                                "content_type": "attachment",
                                **attachment_metadata,  # Data URI 처리된 메타데이터
                                "chunk_index": chunk_idx,
                                "total_chunks": len(chunks),
                                "source": "document_parse",  # Document Parse 결과
                                "html_available": bool(att.get("html"))
                            }
                        ))
                else:
                    # 짧은 텍스트는 그대로
                    items.append((
                        full_text,
                        {
                            "title": self.title,
                            "url": self.url,
                            "date": self.date,
                            "content_type": "attachment",
                            **attachment_metadata,  # Data URI 처리된 메타데이터
                            "source": "document_parse",
                            "html_available": bool(att.get("html"))
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
        self.cache_collection.create_index("file_hash")  # 파일 해시 인덱스 (중복 이미지 감지용)

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
                # 1. URL 기반 캐시 확인 (빠른 경로)
                cached = self._get_from_cache(img_url)
                if cached:
                    # 캐시에서 가져온 데이터에 url 키 추가 (캐시 메서드에서 제거되므로)
                    cached["url"] = img_url

                    # 캐시된 데이터의 성공 여부 확인
                    if cached.get('ocr_text'):
                        successful.append(cached)
                        if logger:
                            logger.log_multimodal_detail(
                                "이미지 OCR (URL 캐시)",
                                img_url[:50] + "..." if len(img_url) > 50 else img_url,
                                success=True,
                                detail=f"{len(cached.get('ocr_text', ''))}자"
                            )
                    continue

                # 2. 파일 다운로드 및 해시 계산
                download_result = download_file(img_url, extract_metadata=False)
                if not download_result.success:
                    failed.append({
                        "url": img_url,
                        "reason": "파일 다운로드 실패"
                    })
                    if logger:
                        url_display = img_url[:50] + "..." if len(img_url) > 50 else img_url
                        logger.log_multimodal_detail(
                            "이미지 OCR",
                            url_display,
                            success=False,
                            detail="다운로드 실패"
                        )
                    continue

                file_data = download_result.content
                file_hash = self._calculate_file_hash(file_data)

                # 3. 파일 해시 기반 캐시 확인 (중복 이미지 감지)
                cached_by_hash = self._get_from_cache_by_file_hash(file_hash)
                if cached_by_hash:
                    # 중복 이미지 발견! OCR 생략
                    content = {
                        "url": img_url,
                        "ocr_text": cached_by_hash.get("ocr_text", ""),
                        "description": cached_by_hash.get("description", "")
                    }
                    successful.append(content)
                    # 현재 URL도 캐시에 추가 (빠른 조회용)
                    self._save_to_cache(img_url, content, file_hash=file_hash)

                    if logger:
                        url_display = img_url[:50] + "..." if len(img_url) > 50 else img_url
                        logger.log_multimodal_detail(
                            "이미지 OCR (파일 해시 캐시)",
                            url_display,
                            success=True,
                            detail=f"중복 이미지 - {len(content['ocr_text'])}자"
                        )
                    else:
                        # 로거 없을 때 콘솔 출력
                        print(f"ℹ️  중복 이미지 감지 (파일 해시): OCR 생략 - {len(content['ocr_text'])}자")
                    continue

                # 4. 새 이미지 → Upstage OCR API 호출
                ocr_result = self.upstage_client.extract_text_from_image_url(img_url)

                if ocr_result:
                    text_length = len(ocr_result.get("text", ""))

                    if text_length > 0:
                        # 성공: 텍스트 추출 완료 (HTML, Markdown 구조 함께 저장)
                        content = {
                            "url": img_url,
                            "ocr_text": ocr_result.get("text", ""),
                            "ocr_html": ocr_result.get("html", ""),  # HTML 구조 보존 (표, 레이아웃 등)
                            "ocr_markdown": ocr_result.get("markdown", ""),  # Markdown (Upstage API 제공, 고품질!)
                            "ocr_elements": ocr_result.get("elements", []),  # 요소 정보
                            "description": ""
                        }
                        successful.append(content)
                        self._save_to_cache(img_url, content, file_hash=file_hash)

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

    def process_attachments(self, attachment_urls: List, logger=None, category: str = "notice") -> Dict:
        """
        첨부파일 리스트 처리 (Document Parse 또는 OCR)

        이미지 확장자 첨부파일은 OCR로 처리하고,
        문서 확장자는 Document Parse로 처리합니다.

        Args:
            attachment_urls: 첨부파일 리스트 (str 또는 {"url": str, "filename": str} 형식)
                           - HTML에서 filename 추출 시 딕셔너리로 전달 (HEAD 요청 생략)
                           - filename 없으면 str URL로 전달 (HEAD 요청으로 확인)
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

        for att in attachment_urls:
            # 🔧 하위 호환성: 딕셔너리 또는 문자열(URL) 처리
            if isinstance(att, dict):
                att_url = att["url"]
                filename = att.get("filename")  # HTML에서 추출된 파일명 (있으면)
            else:
                att_url = att  # 하위 호환 (문자열 URL)
                filename = None

            # 🔧 파일 확장자 추출 (우선순위: filename > URL > HEAD 요청)
            file_ext = None

            # 1. filename에서 확장자 추출 (HTML에서 얻은 경우)
            if filename:
                file_ext = Path(filename).suffix.lower()

            # 2. URL에서 확장자 추출 시도
            if not file_ext:
                url_ext = Path(att_url).suffix.lower()
                if url_ext:
                    file_ext = url_ext

            # 3. 확장자 없으면 HEAD 요청으로 Content-Disposition 확인 (fallback)
            if not file_ext:
                try:
                    import requests
                    from urllib.parse import unquote
                    head_response = requests.head(att_url, timeout=10, allow_redirects=True)
                    content_disp = head_response.headers.get('Content-Disposition', '')
                    if 'filename=' in content_disp:
                        # filename="파일.zip" 형식
                        parts = content_disp.split('filename=')
                        if len(parts) > 1:
                            filename = parts[1].strip('"').strip("'")
                            filename = unquote(filename)  # URL 디코딩
                            file_ext = Path(filename).suffix.lower()
                except:
                    pass  # HEAD 실패 시 계속 진행

            # 🔧 ZIP 파일 처리 (압축 해제 후 개별 파일 파싱)
            if file_ext == '.zip':
                try:
                    if logger:
                        url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                        logger.log_multimodal_detail(
                            "ZIP 파일 처리",
                            url_display,
                            success=True,
                            detail="압축 해제 중..."
                        )

                    # ZIP 파일 처리
                    zip_result = self.upstage_client.process_zip_from_url(att_url)

                    # 성공한 파일들 추가
                    for item in zip_result["successful"]:
                        # ZIP 내부 파일은 별도 URL로 구분
                        content = {
                            "url": f"{att_url}#{item['filename']}",  # ZIP#파일명
                            "type": item["type"],
                            "text": item["text"],
                            "html": item.get("html", ""),
                            "from_zip": True,
                            "zip_url": att_url
                        }
                        successful.append(content)

                        # 캐시 저장 (ZIP 내부 파일도 캐싱)
                        self._save_to_cache(
                            content["url"],
                            {
                                "text": item["text"],
                                "html": item.get("html", ""),
                                "type": item["type"],
                                "from_zip": True
                            }
                        )

                    # 실패한 파일들 기록
                    for item in zip_result["failed"]:
                        failed.append({
                            "url": f"{att_url}#{item['filename']}",
                            "reason": item["reason"]
                        })

                    if logger:
                        logger.log_multimodal_detail(
                            "ZIP 파일 처리",
                            url_display,
                            success=True,
                            detail=f"성공 {len(zip_result['successful'])}개, 실패 {len(zip_result['failed'])}개"
                        )

                except Exception as e:
                    error_msg = str(e)
                    failed.append({
                        "url": att_url,
                        "reason": error_msg
                    })

                    if logger:
                        url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                        logger.log_multimodal_detail(
                            "ZIP 파일 처리",
                            url_display,
                            success=False,
                            detail=error_msg[:100]
                        )

                # ZIP 파일 처리 완료, 다음 첨부파일로
                continue

            # 이미지 확장자 확인 (대소문자 무관)
            is_image = self.upstage_client.is_image_url(att_url)

            # 이미지 첨부파일은 OCR로 처리
            if is_image:
                # 이미지로 처리 (process_images 로직과 동일)
                try:
                    # 1. URL 기반 캐시 확인
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
                                    "이미지 첨부 OCR (URL 캐시)",
                                    url_display,
                                    success=True,
                                    detail=f"이미지 - {len(text)}자"
                                )
                        continue

                    # 2. 파일 다운로드 및 해시 계산
                    download_result = download_file(att_url, extract_metadata=False)
                    if not download_result.success:
                        failed.append({
                            "url": att_url,
                            "reason": "파일 다운로드 실패"
                        })
                        if logger:
                            url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                            logger.log_multimodal_detail(
                                "이미지 첨부 OCR",
                                url_display,
                                success=False,
                                detail="다운로드 실패"
                            )
                        continue

                    file_data = download_result.content
                    file_hash = self._calculate_file_hash(file_data)

                    # 3. 파일 해시 기반 캐시 확인 (중복 이미지 감지)
                    cached_by_hash = self._get_from_cache_by_file_hash(file_hash)
                    if cached_by_hash:
                        # 중복 이미지 발견! OCR 생략
                        text = cached_by_hash.get("ocr_text") or cached_by_hash.get("text", "")
                        content = {
                            "url": att_url,
                            "type": "image",
                            "text": text
                        }
                        successful.append(content)
                        # 현재 URL도 캐시에 추가
                        self._save_to_cache(att_url, {"ocr_text": text, "type": "image"}, file_hash=file_hash)

                        if logger:
                            url_display = att_url[:50] + "..." if len(att_url) > 50 else att_url
                            logger.log_multimodal_detail(
                                "이미지 첨부 OCR (파일 해시 캐시)",
                                url_display,
                                success=True,
                                detail=f"중복 이미지 - {len(text)}자"
                            )
                        else:
                            print(f"ℹ️  중복 이미지 감지 (파일 해시): OCR 생략 - {len(text)}자")
                        continue

                    # 4. 새 이미지 → OCR API 호출
                    ocr_result = self.upstage_client.extract_text_from_image_url(att_url)

                    if ocr_result and ocr_result.get("text"):
                        text = ocr_result.get("text", "")
                        html = ocr_result.get("html", "")
                        markdown = ocr_result.get("markdown", "")
                        elements = ocr_result.get("elements", [])

                        content = {
                            "url": att_url,
                            "type": "image",
                            "text": text,
                            "html": html,  # HTML 구조 보존 (표, 레이아웃 등)
                            "markdown": markdown,  # Markdown (Upstage API 제공, 고품질!)
                            "elements": elements  # 요소 정보
                        }
                        successful.append(content)
                        self._save_to_cache(att_url, {
                            "ocr_text": text,
                            "ocr_html": html,
                            "ocr_markdown": markdown,
                            "ocr_elements": elements,
                            "type": "image"
                        }, file_hash=file_hash)

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
                        # 성공: 텍스트 추출 완료 (HTML 구조도 함께 저장)
                        content = {
                            "url": att_url,
                            "type": file_type,
                            "text": parse_result.get("text", ""),
                            "html": parse_result.get("html", ""),  # HTML 구조 보존 (표, 레이아웃 등)
                            "markdown": parse_result.get("markdown", ""),  # Markdown (Upstage API 제공, 고품질!)
                            "elements": parse_result.get("elements", [])  # 요소 정보
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

    def _calculate_file_hash(self, file_data: bytes) -> str:
        """
        파일 바이너리 데이터의 MD5 해시 계산

        Args:
            file_data: 파일 바이너리 데이터

        Returns:
            MD5 해시 문자열
        """
        return hashlib.md5(file_data).hexdigest()

    def _get_from_cache_by_file_hash(self, file_hash: str) -> Optional[Dict]:
        """
        파일 해시로 캐시 조회 (중복 이미지 감지)

        Args:
            file_hash: 파일 MD5 해시

        Returns:
            캐시된 처리 결과 또는 None
        """
        try:
            cached = self.cache_collection.find_one({"file_hash": file_hash})
            if cached:
                # MongoDB _id, url, file_hash 제거
                cached.pop("_id", None)
                cached.pop("url", None)
                cached.pop("file_hash", None)
                return cached
        except Exception as e:
            logger.warning(f"파일 해시 캐시 조회 오류: {e}")

        return None

    def _get_from_cache(self, url: str) -> Optional[Dict]:
        """캐시에서 처리 결과 조회"""
        try:
            cached = self.cache_collection.find_one({"url": url})
            if cached:
                # MongoDB _id 제거
                cached.pop("_id", None)
                cached.pop("url", None)
                cached.pop("file_hash", None)
                return cached
        except Exception as e:
            logger.warning(f"캐시 조회 오류: {e}")

        return None

    def _save_to_cache(self, url: str, content: Dict, file_hash: Optional[str] = None):
        """
        처리 결과를 캐시에 저장

        Args:
            url: 원본 URL
            content: 처리 결과 (ocr_text, text 등)
            file_hash: 파일 해시 (선택)
        """
        try:
            cache_data = {"url": url, **content}
            if file_hash:
                cache_data["file_hash"] = file_hash

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
        attachment_urls: List,
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
            attachment_urls: 첨부파일 리스트 (str 또는 {"url": str, "filename": str} 형식)
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
            # 성공한 이미지만 추가 (HTML 구조 포함)
            for img_content in image_result["successful"]:
                content.add_image_content(
                    url=img_content["url"],
                    ocr_text=img_content.get("ocr_text", ""),
                    ocr_html=img_content.get("ocr_html", ""),  # HTML 구조
                    ocr_elements=img_content.get("ocr_elements", []),  # 요소 정보
                    description=img_content.get("description", "")
                )
            # 실패 정보 저장
            failures["image_failed"] = image_result["failed"]
            failures["image_unsupported"] = image_result["unsupported"]

        # 3. 첨부파일 처리 및 추가
        if attachment_urls:
            attachment_result = self.process_attachments(attachment_urls, logger=logger, category=category)
            # 성공한 첨부파일만 추가 (HTML 구조 포함)
            for att_content in attachment_result["successful"]:
                content.add_attachment_content(
                    url=att_content["url"],
                    file_type=att_content["type"],
                    text=att_content["text"],
                    html=att_content.get("html", ""),  # HTML 구조
                    elements=att_content.get("elements", [])  # 요소 정보
                )
            # 실패 정보 저장
            failures["attachment_failed"] = attachment_result["failed"]
            failures["attachment_unsupported"] = attachment_result["unsupported"]

        return content, failures
