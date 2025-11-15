"""
문서 처리
크롤링된 데이터를 처리하고 중복 체크
"""
from typing import List, Tuple, Optional, Dict
from pymongo import MongoClient
from pymongo.collection import Collection
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CrawlerConfig
from processing.multimodal_processor import MultimodalProcessor


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


class DocumentProcessor:
    """
    문서 처리 클래스

    역할:
    - 크롤링된 데이터를 텍스트 청크로 분할
    - 중복 문서 체크 (MongoDB)
    - 문서 메타데이터 관리
    """

    def __init__(
        self,
        mongo_client: Optional[MongoClient] = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
        multimodal_processor: Optional[MultimodalProcessor] = None,
        enable_multimodal: bool = True
    ):
        """
        Args:
            mongo_client: MongoDB 클라이언트
            chunk_size: 텍스트 청크 크기
            chunk_overlap: 청크 간 겹침 크기
            multimodal_processor: 멀티모달 프로세서
            enable_multimodal: 멀티모달 처리 활성화
        """
        if mongo_client is None:
            mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)

        self.client = mongo_client
        self.db = self.client[CrawlerConfig.MONGODB_DATABASE]
        self.collection: Collection = self.db[CrawlerConfig.MONGODB_NOTICE_COLLECTION]

        # 텍스트 분할기 초기화
        chunk_size = chunk_size or CrawlerConfig.CHUNK_SIZE
        chunk_overlap = chunk_overlap or CrawlerConfig.CHUNK_OVERLAP
        self.text_splitter = CharacterTextSplitter(chunk_size, chunk_overlap)

        # 멀티모달 프로세서 초기화
        self.enable_multimodal = enable_multimodal
        if enable_multimodal:
            self.multimodal_processor = multimodal_processor or MultimodalProcessor(mongo_client=mongo_client)
        else:
            self.multimodal_processor = None

    def is_duplicate(self, title: str, image_url: Optional[str] = None) -> bool:
        """
        중복 문서 체크

        Args:
            title: 문서 제목
            image_url: 이미지 URL

        Returns:
            중복이면 True, 아니면 False
        """
        query = {"title": title}

        if image_url and image_url != "No content":
            query["image_url"] = image_url

        return self.collection.find_one(query) is not None

    def mark_as_processed(self, title: str, image_url: Optional[str] = None) -> bool:
        """
        문서를 처리 완료로 표시 (MongoDB에 저장)

        Args:
            title: 문서 제목
            image_url: 이미지 URL

        Returns:
            새로 삽입되면 True, 중복이면 False
        """
        temp_data = {
            "title": title,
            "image_url": image_url if image_url else "No content"
        }

        if not self.is_duplicate(title, image_url):
            self.collection.insert_one(temp_data)
            return True
        else:
            return False

    def process_documents(
        self,
        document_data: List[Tuple[str, str, any, str, str]]
    ) -> Tuple[List[str], List[str], List[str], List[str], List[any], int]:
        """
        문서 리스트 처리

        Args:
            document_data: [(title, text, image, date, url), ...] 형식의 리스트

        Returns:
            (texts, titles, doc_urls, doc_dates, image_urls, new_count) 튜플
            - texts: 분할된 텍스트 리스트
            - titles: 제목 리스트
            - doc_urls: URL 리스트
            - doc_dates: 날짜 리스트
            - image_urls: 이미지 URL 리스트
            - new_count: 새로 처리된 문서 개수
        """
        texts = []
        titles = []
        doc_urls = []
        doc_dates = []
        image_urls = []
        new_count = 0

        for title, doc, image, date, url in document_data:
            # 중복 체크 (크롤링 전에 체크하여 효율성 향상)
            if self.is_duplicate(title, image):
                print(f"⏭️  중복 문서 스킵: {title}")
                continue

            new_count += 1

            # 텍스트가 있는 경우
            if isinstance(doc, str) and doc.strip():
                split_texts = self.text_splitter.split_text(doc)
                texts.extend(split_texts)
                titles.extend([title] * len(split_texts))
                doc_urls.extend([url] * len(split_texts))
                doc_dates.extend([date] * len(split_texts))

                # 이미지 URL 처리
                if image:
                    image_urls.extend([image] * len(split_texts))
                else:
                    image_urls.extend(["No content"] * len(split_texts))
                    image = "No content"

            # 텍스트는 없고 이미지만 있는 경우
            elif image:
                texts.append("No content")
                titles.append(title)
                doc_urls.append(url)
                doc_dates.append(date)
                image_urls.append(image)

            # 텍스트와 이미지 모두 없는 경우
            else:
                texts.append("No content")
                titles.append(title)
                doc_urls.append(url)
                doc_dates.append(date)
                image_urls.append("No content")
                image = "No content"

            # MongoDB에 처리 완료 표시
            self.mark_as_processed(title, image)
            print(f"✅ 새 문서 처리: {title}")

        return texts, titles, doc_urls, doc_dates, image_urls, new_count

    def process_documents_multimodal(
        self,
        document_data: List[Tuple[str, str, any, any, str, str]]
    ) -> Tuple[List[Tuple[str, Dict]], int]:
        """
        멀티모달 문서 리스트 처리 (이미지 OCR, 첨부파일 파싱 포함)

        Args:
            document_data: [(title, text, image_list, attachment_list, date, url), ...] 형식의 리스트

        Returns:
            (embedding_items, new_count) 튜플
            - embedding_items: [(text, metadata), ...] 형식의 리스트
            - new_count: 새로 처리된 문서 개수
        """
        if not self.enable_multimodal or self.multimodal_processor is None:
            print("⚠️  멀티모달 처리가 비활성화되어 있습니다.")
            return [], 0

        embedding_items = []
        new_count = 0

        for title, text, image_list, attachment_list, date, url in document_data:
            # 중복 체크 (이미지 리스트의 첫 번째 이미지로 체크)
            first_image = image_list[0] if image_list else None
            if self.is_duplicate(title, first_image):
                print(f"⏭️  중복 문서 스킵: {title}")
                continue

            new_count += 1

            # 텍스트 청크로 분할
            text_chunks = []
            if isinstance(text, str) and text.strip():
                text_chunks = self.text_splitter.split_text(text)
            else:
                text_chunks = []  # 텍스트 없으면 빈 리스트

            # 멀티모달 콘텐츠 생성 (이미지 OCR, 첨부파일 파싱 포함)
            multimodal_content = self.multimodal_processor.create_multimodal_content(
                title=title,
                url=url,
                date=date,
                text_chunks=text_chunks,
                image_urls=image_list if image_list else [],
                attachment_urls=attachment_list if attachment_list else []
            )

            # 임베딩 아이템으로 변환
            items = multimodal_content.to_embedding_items()
            embedding_items.extend(items)

            # MongoDB에 처리 완료 표시
            self.mark_as_processed(title, first_image)
            print(f"✅ 새 문서 처리 (멀티모달): {title} - {len(items)}개 임베딩 아이템")

        return embedding_items, new_count
