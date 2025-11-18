"""
BM25 Retriever
BM25 알고리즘을 사용한 문서 검색 클래스
"""

import numpy as np
from rank_bm25 import BM25Okapi
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


class BM25Retriever:
    """
    BM25 알고리즘을 사용하여 문서를 검색하는 클래스

    제목과 본문을 결합하여 토큰화하고, BM25 유사도를 계산하여
    가장 관련성 높은 문서를 반환합니다.

    개선사항: 제목뿐만 아니라 본문도 검색하여 첨부파일 내용도 찾을 수 있습니다.
    """

    def __init__(self,
                 titles: List[str],
                 texts: List[str],
                 urls: List[str],
                 dates: List[str],
                 query_transformer,
                 similarity_adjuster,
                 k1: float = 1.5,
                 b: float = 0.75):
        """
        BM25Retriever 초기화

        Args:
            titles: 문서 제목 리스트
            texts: 문서 본문 리스트
            urls: 문서 URL 리스트
            dates: 문서 날짜 리스트
            query_transformer: 질문을 명사로 변환하는 함수 (transformed_query)
            similarity_adjuster: 유사도를 조정하는 함수 (adjust_similarity_scores)
            k1: BM25 k1 파라미터 (기본값: 1.5)
            b: BM25 b 파라미터 (기본값: 0.75)
        """
        self.titles = titles
        self.texts = texts
        self.urls = urls
        self.dates = dates
        self.query_transformer = query_transformer
        self.similarity_adjuster = similarity_adjuster
        self.k1 = k1
        self.b = b

        # BM25 인덱스 생성 (제목 + 본문 결합하여 검색)
        logger.info("🔄 BM25 인덱스 생성 중 (제목+본문 검색)...")
        self.tokenized_documents = [
            query_transformer(title + " " + text)
            for title, text in zip(titles, texts)
        ]
        self.bm25_index = BM25Okapi(self.tokenized_documents, k1=k1, b=b)
        logger.info(f"✅ BM25 인덱스 생성 완료 ({len(titles)}개 문서, 첨부파일 내용 포함)")

    def search(self,
               query_nouns: List[str],
               top_k: int = 25,
               normalize_factor: float = 24.0) -> Tuple[List[Tuple], np.ndarray]:
        """
        BM25 검색 수행

        Args:
            query_nouns: 검색 질문의 명사 리스트
            top_k: 반환할 상위 문서 개수 (기본값: 25)
            normalize_factor: 유사도 정규화 팩터 (기본값: 24.0)

        Returns:
            Tuple[List[Tuple], np.ndarray]:
                - 검색된 문서 리스트 (title, date, text, url)
                - 조정된 유사도 배열
        """
        # BM25 유사도 계산
        similarities = self.bm25_index.get_scores(query_nouns)

        # 유사도 정규화
        similarities = similarities / normalize_factor

        # 유사도 조정 (제목-본문 매칭, 키워드 가중치 등)
        adjusted_similarities = self.similarity_adjuster(
            query_nouns,
            self.titles,
            self.texts,
            similarities
        )

        # 상위 k개 인덱스 추출 (내림차순)
        top_indices = np.argsort(adjusted_similarities)[-top_k:][::-1]

        # 결과 문서 생성
        results = [
            (self.titles[i], self.dates[i], self.texts[i], self.urls[i])
            for i in top_indices
        ]

        logger.debug(f"✅ BM25 검색 완료: {len(results)}개 문서 반환")

        return results, adjusted_similarities

    def get_similarity_score(self, query_nouns: List[str], doc_index: int) -> float:
        """
        특정 문서에 대한 BM25 유사도 점수 반환

        Args:
            query_nouns: 검색 질문의 명사 리스트
            doc_index: 문서 인덱스

        Returns:
            float: BM25 유사도 점수
        """
        similarities = self.bm25_index.get_scores(query_nouns)
        return similarities[doc_index]

    def update_index(self,
                     titles: List[str],
                     texts: List[str],
                     urls: List[str],
                     dates: List[str]):
        """
        BM25 인덱스 업데이트 (문서 추가/삭제 시 사용)

        Args:
            titles: 새로운 문서 제목 리스트
            texts: 새로운 문서 본문 리스트
            urls: 새로운 문서 URL 리스트
            dates: 새로운 문서 날짜 리스트
        """
        logger.info("🔄 BM25 인덱스 업데이트 중...")

        self.titles = titles
        self.texts = texts
        self.urls = urls
        self.dates = dates

        # 제목 + 본문 결합하여 인덱스 생성 (첨부파일 내용 포함)
        self.tokenized_documents = [
            self.query_transformer(title + " " + text)
            for title, text in zip(titles, texts)
        ]
        self.bm25_index = BM25Okapi(self.tokenized_documents, k1=self.k1, b=self.b)

        logger.info(f"✅ BM25 인덱스 업데이트 완료 ({len(titles)}개 문서, 첨부파일 내용 포함)")
