"""
Dense Retriever
Pinecone 벡터 DB와 Upstage Embeddings를 사용한 Dense Retrieval
"""

import numpy as np
import re
from typing import List, Tuple, Callable
import logging

logger = logging.getLogger(__name__)


class DenseRetriever:
    """
    Dense Retrieval 검색 클래스

    Upstage Embeddings로 질문을 벡터화하고,
    Pinecone에서 유사한 문서를 검색합니다.
    """

    def __init__(self,
                 embeddings_factory: Callable,
                 pinecone_index,
                 date_adjuster: Callable,
                 similarity_scale: float = 3.26,
                 noun_weight: float = 0.20,
                 digit_weight: float = 0.24):
        """
        DenseRetriever 초기화

        Args:
            embeddings_factory: Embeddings 객체를 생성하는 함수 (get_embeddings)
            pinecone_index: Pinecone 인덱스 객체
            date_adjuster: 날짜 기반 유사도 조정 함수 (adjust_date_similarity)
            similarity_scale: Pinecone 유사도 스케일 팩터 (기본값: 3.26)
            noun_weight: 명사 매칭 가중치 (기본값: 0.20)
            digit_weight: 숫자 포함 명사 가중치 (기본값: 0.24)
        """
        self.embeddings_factory = embeddings_factory
        self.pinecone_index = pinecone_index
        self.date_adjuster = date_adjuster
        self.similarity_scale = similarity_scale
        self.noun_weight = noun_weight
        self.digit_weight = digit_weight

        logger.info("✅ DenseRetriever 초기화 완료")

    def search(self,
               user_question: str,
               query_nouns: List[str],
               top_k: int = 30) -> List[Tuple[float, Tuple]]:
        """
        Dense Retrieval 검색 수행

        Args:
            user_question: 사용자 질문 (원문)
            query_nouns: 질문에서 추출한 명사 리스트
            top_k: Pinecone에서 가져올 상위 문서 개수 (기본값: 30)

        Returns:
            List[Tuple[float, Tuple]]: (조정된_유사도, (title, date, text, url)) 리스트
        """
        # 1. 질문 임베딩
        embeddings = self.embeddings_factory()
        query_vector = np.array(embeddings.embed_query(user_question))

        # 2. Pinecone 검색
        pinecone_results = self.pinecone_index.query(
            vector=query_vector.tolist(),
            top_k=top_k,
            include_values=False,
            include_metadata=True
        )

        # 3. 결과 추출
        similarities = [res['score'] for res in pinecone_results['matches']]
        documents = [
            (
                res['metadata'].get('title', 'No Title'),
                res['metadata'].get('date', 'No Date'),
                res['metadata'].get('text', ''),
                res['metadata'].get('url', 'No URL')
            )
            for res in pinecone_results['matches']
        ]

        # 4. 유사도 조정 및 결과 생성
        adjusted_results = []
        for idx, doc in enumerate(documents):
            title, date, text, url = doc

            # 초기 유사도 (Pinecone 점수 * 스케일)
            similarity = similarities[idx] * self.similarity_scale

            # 날짜 기반 조정
            similarity = self.date_adjuster(similarity, date, query_nouns)

            # 명사 매칭 기반 조정
            similarity = self._adjust_by_noun_matching(
                similarity, text, query_nouns
            )

            adjusted_results.append((similarity, doc))

        # 5. 유사도 기준 정렬
        adjusted_results.sort(key=lambda x: x[0], reverse=True)

        logger.debug(f"✅ Dense Retrieval 완료: {len(adjusted_results)}개 문서 반환")

        return adjusted_results

    def _adjust_by_noun_matching(self,
                                   similarity: float,
                                   text: str,
                                   query_nouns: List[str]) -> float:
        """
        본문 내 명사 매칭으로 유사도 조정

        Args:
            similarity: 현재 유사도 점수
            text: 문서 본문
            query_nouns: 검색 질문의 명사 리스트

        Returns:
            float: 조정된 유사도
        """
        # 본문에 포함된 명사 찾기
        matching_nouns = [noun for noun in query_nouns if noun in text]

        for noun in matching_nouns:
            # 기본 가중치
            similarity += len(noun) * self.noun_weight

            # 숫자 포함 명사는 추가 가중치
            if re.search(r'\d', noun):
                if noun in text:
                    similarity += len(noun) * self.digit_weight
                else:
                    similarity += len(noun) * self.noun_weight

        return similarity

    def get_embedding_vector(self, text: str) -> np.ndarray:
        """
        텍스트를 임베딩 벡터로 변환

        Args:
            text: 변환할 텍스트

        Returns:
            np.ndarray: 임베딩 벡터
        """
        embeddings = self.embeddings_factory()
        return np.array(embeddings.embed_query(text))
