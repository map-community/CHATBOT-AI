"""
임베딩 생성 및 벡터 DB 관리
새 문서만 임베딩 생성하여 API 비용 절감
"""
from typing import List, Tuple, Dict
import numpy as np
from langchain_upstage import UpstageEmbeddings
from pinecone import Pinecone
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CrawlerConfig


class EmbeddingManager:
    """
    임베딩 생성 및 Pinecone 업로드 관리 클래스

    역할:
    - 새 문서만 임베딩 생성 (API 비용 절감)
    - Pinecone에 벡터 업로드
    - 진행 상황 표시
    """

    def __init__(
        self,
        upstage_api_key: str = None,
        pinecone_api_key: str = None,
        index_name: str = None
    ):
        """
        Args:
            upstage_api_key: Upstage API 키
            pinecone_api_key: Pinecone API 키
            index_name: Pinecone 인덱스 이름
        """
        self.upstage_api_key = upstage_api_key or CrawlerConfig.UPSTAGE_API_KEY
        self.pinecone_api_key = pinecone_api_key or CrawlerConfig.PINECONE_API_KEY
        self.index_name = index_name or CrawlerConfig.PINECONE_INDEX_NAME

        # Upstage 임베딩 초기화
        self.embeddings = UpstageEmbeddings(
            api_key=self.upstage_api_key,
            model=CrawlerConfig.EMBEDDING_MODEL
        )

        # Pinecone 초기화
        pc = Pinecone(api_key=self.pinecone_api_key)
        self.index = pc.Index(self.index_name)

    def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        텍스트 리스트에 대한 임베딩 생성

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            임베딩 벡터 numpy 배열
        """
        if not texts:
            return np.array([])

        print(f"\n{'='*80}")
        print(f"📊 임베딩 생성 시작: {len(texts)}개 문서")
        print(f"{'='*80}\n")

        print("🔄 Upstage API로 임베딩 생성 중... (시간이 걸릴 수 있습니다)")
        dense_vectors = np.array(self.embeddings.embed_documents(texts))
        print(f"✅ 임베딩 생성 완료! {len(dense_vectors)}개 벡터 생성됨\n")

        return dense_vectors

    def get_next_vector_id(self) -> int:
        """
        Pinecone에서 다음 사용할 벡터 ID 조회

        Returns:
            다음 ID (기존 최대 ID + 1)
        """
        try:
            # Pinecone stats로 현재 벡터 개수 확인
            stats = self.index.describe_index_stats()
            total_count = stats.get('total_vector_count', 0)
            return total_count
        except Exception as e:
            print(f"⚠️  벡터 ID 조회 실패, 0부터 시작: {e}")
            return 0

    def upload_to_pinecone(
        self,
        embeddings: np.ndarray,
        texts: List[str],
        titles: List[str],
        doc_urls: List[str],
        doc_dates: List[str],
        start_id: int = None
    ) -> int:
        """
        Pinecone에 임베딩 업로드

        Args:
            embeddings: 임베딩 벡터 배열
            texts: 텍스트 리스트
            titles: 제목 리스트
            doc_urls: URL 리스트
            doc_dates: 날짜 리스트
            start_id: 시작 ID (None이면 자동 계산)

        Returns:
            업로드된 벡터 개수
        """
        if len(embeddings) == 0:
            print("⚠️  업로드할 벡터가 없습니다.")
            return 0

        # 시작 ID 결정
        if start_id is None:
            start_id = self.get_next_vector_id()

        print(f"\n{'='*80}")
        print(f"📤 Pinecone 업로드 시작: {len(embeddings)}개 벡터")
        print(f"📍 시작 ID: {start_id}")
        print(f"{'='*80}\n")

        uploaded_count = 0

        for i, embedding in enumerate(embeddings):
            vector_id = start_id + i

            metadata = {
                "title": titles[i],
                "text": texts[i],
                "url": doc_urls[i],
                "date": doc_dates[i]
            }

            # Pinecone에 업로드
            self.index.upsert([(str(vector_id), embedding.tolist(), metadata)])
            uploaded_count += 1

            # 진행 상황 출력
            if (i + 1) % CrawlerConfig.EMBEDDING_BATCH_SIZE == 0:
                progress = (i + 1) / len(embeddings) * 100
                print(f"⏳ 진행: {i + 1}/{len(embeddings)} ({progress:.1f}%)")

        print(f"\n{'='*80}")
        print(f"✅ Pinecone 업로드 완료! 총 {uploaded_count}개 벡터 업로드됨")
        print(f"{'='*80}\n")

        return uploaded_count

    def process_and_upload(
        self,
        texts: List[str],
        titles: List[str],
        doc_urls: List[str],
        doc_dates: List[str]
    ) -> int:
        """
        임베딩 생성 및 Pinecone 업로드를 한 번에 수행

        Args:
            texts: 텍스트 리스트
            titles: 제목 리스트
            doc_urls: URL 리스트
            doc_dates: 날짜 리스트

        Returns:
            업로드된 벡터 개수
        """
        if not texts:
            print("⚠️  처리할 텍스트가 없습니다.")
            return 0

        # 1. 임베딩 생성
        embeddings = self.create_embeddings(texts)

        # 2. Pinecone 업로드
        uploaded_count = self.upload_to_pinecone(
            embeddings, texts, titles, doc_urls, doc_dates
        )

        return uploaded_count

    def process_and_upload_items(
        self,
        embedding_items: List[Tuple[str, Dict]]
    ) -> int:
        """
        임베딩 아이템 리스트 처리 및 Pinecone 업로드 (멀티모달 지원)

        Args:
            embedding_items: [(text, metadata), ...] 형식의 리스트
                metadata에는 title, url, date, content_type 등이 포함

        Returns:
            업로드된 벡터 개수
        """
        if not embedding_items:
            print("⚠️  처리할 아이템이 없습니다.")
            return 0

        # 텍스트와 메타데이터 분리
        texts = [item[0] for item in embedding_items]
        metadatas = [item[1] for item in embedding_items]

        # ✅ 청킹은 이미 완료됨 (베스트 프랙티스 적용)
        # - 게시글 텍스트: document_processor.py에서 청킹 (크롤링 시)
        # - 이미지 OCR: multimodal_processor.py에서 청킹 (임베딩 준비 시)
        # - 첨부파일 파싱: multimodal_processor.py에서 청킹 (임베딩 준비 시)
        # 모든 텍스트가 850자 청크로 분할되어 있으므로 4000 tokens 이내 보장!

        print(f"\n{'='*80}")
        print(f"📊 임베딩 생성 시작: {len(texts)}개 문서")
        print(f"{'='*80}\n")

        # 1. 임베딩 생성
        print("🔄 Upstage API로 임베딩 생성 중... (시간이 걸릴 수 있습니다)")
        embeddings = np.array(self.embeddings.embed_documents(texts))
        print(f"✅ 임베딩 생성 완료! {len(embeddings)}개 벡터 생성됨\n")

        # 2. Pinecone 업로드
        start_id = self.get_next_vector_id()

        print(f"\n{'='*80}")
        print(f"📤 Pinecone 업로드 시작: {len(embeddings)}개 벡터")
        print(f"📍 시작 ID: {start_id}")
        print(f"{'='*80}\n")

        uploaded_count = 0
        sample_logged = False  # 샘플 로그 출력 플래그

        for i, embedding in enumerate(embeddings):
            vector_id = start_id + i

            # 메타데이터 준비 (텍스트는 임베딩 벡터에 이미 포함되므로 preview만 저장)
            metadata = metadatas[i].copy()

            # 검색 결과 미리보기용으로 짧은 텍스트만 저장 (Pinecone 40KB 제한)
            text_preview = texts[i][:200] + "..." if len(texts[i]) > 200 else texts[i]
            metadata["text_preview"] = text_preview

            # Pinecone에 업로드
            self.index.upsert([(str(vector_id), embedding.tolist(), metadata)])
            uploaded_count += 1

            # 첫 번째 벡터의 메타데이터 샘플 출력 (HTML 구조 확인용)
            if not sample_logged:
                self._log_metadata_sample(str(vector_id), metadata)
                sample_logged = True

            # 진행 상황 출력
            if (i + 1) % CrawlerConfig.EMBEDDING_BATCH_SIZE == 0:
                progress = (i + 1) / len(embeddings) * 100
                print(f"⏳ 진행: {i + 1}/{len(embeddings)} ({progress:.1f}%)")

        print(f"\n{'='*80}")
        print(f"✅ Pinecone 업로드 완료! 총 {uploaded_count}개 벡터 업로드됨")
        print(f"{'='*80}\n")

        return uploaded_count

    def _log_metadata_sample(self, vector_id: str, metadata: dict):
        """
        Pinecone 메타데이터 샘플 로그 (첫 번째 벡터)

        Args:
            vector_id: 벡터 ID
            metadata: Pinecone 메타데이터
        """
        print(f"\n{'='*80}")
        print(f"🔍 Pinecone 저장 데이터 샘플 (벡터 ID: {vector_id})")
        print(f"{'='*80}")
        print(f"제목: {metadata.get('title', 'N/A')}")
        print(f"카테고리: {metadata.get('category', 'N/A')}")
        print(f"콘텐츠 타입: {metadata.get('content_type', 'N/A')}")
        print(f"소스: {metadata.get('source', 'N/A')}")
        print(f"날짜: {metadata.get('date', 'N/A')}")
        print(f"URL: {metadata.get('url', 'N/A')[:80]}..." if len(metadata.get('url', '')) > 80 else f"URL: {metadata.get('url', 'N/A')}")

        # 텍스트 미리보기 필드
        text_preview = metadata.get('text_preview', '')
        print(f"\n📝 텍스트 필드:")
        print(f"   길이: {len(text_preview)}자")
        print(f"   미리보기: {text_preview}")

        # HTML 구조 가용성
        print(f"\n🌐 HTML 구조 필드:")
        if metadata.get('html_available'):
            print(f"   ✅ HTML 구조 가용 (캐시에 저장됨)")
            print(f"   용도: 표, 레이아웃 맥락 보존 (필요시 캐시에서 조회)")
        else:
            print(f"   ❌ 없음 (평문 텍스트만)")

        # 이미지/첨부파일 URL
        if metadata.get('image_url'):
            img_url = metadata.get('image_url', '')
            print(f"\n🖼️ 이미지 URL: {img_url[:60]}..." if len(img_url) > 60 else f"\n🖼️ 이미지 URL: {img_url}")
        if metadata.get('attachment_url'):
            att_url = metadata.get('attachment_url', '')
            print(f"\n📎 첨부파일 URL: {att_url[:60]}..." if len(att_url) > 60 else f"\n📎 첨부파일 URL: {att_url}")

        print(f"{'='*80}\n")
