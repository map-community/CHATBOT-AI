"""
Document Combiner
BM25와 Dense Retrieval 결과를 결합하는 클래스
"""

import logging
from typing import List, Tuple, Callable

logger = logging.getLogger(__name__)


class DocumentCombiner:
    """
    BM25와 Dense Retrieval 결과를 결합하는 클래스

    두 검색 방법의 결과를 병합하고, 중복 제거 및 유사도 조정을 수행합니다.
    """

    def __init__(self,
                 keyword_filter: Callable,
                 date_adjuster: Callable):
        """
        DocumentCombiner 초기화

        Args:
            keyword_filter: 키워드 필터링 함수 (last_filter_keyword)
            date_adjuster: 날짜 기반 유사도 조정 함수 (adjust_date_similarity)
        """
        self.keyword_filter = keyword_filter
        self.date_adjuster = date_adjuster
        logger.info("✅ DocumentCombiner 초기화 완료")

    def combine(self,
                dense_results: List[Tuple[float, Tuple]],
                bm25_results: List[Tuple],
                bm25_similarities: 'np.ndarray',
                titles_from_pinecone: List[str],
                query_nouns: List[str],
                user_question: str,
                top_k: int = 20) -> List[Tuple]:
        """
        BM25와 Dense Retrieval 결과를 결합

        Args:
            dense_results: Dense Retrieval 결과 [(similarity, (title, date, text, url)), ...]
            bm25_results: BM25 결과 [(title, date, text, url), ...]
            bm25_similarities: BM25 유사도 배열
            titles_from_pinecone: 전체 제목 리스트 (유사도 매칭용)
            query_nouns: 검색 질문의 명사 리스트
            user_question: 원본 질문
            top_k: 최종 반환할 문서 개수 (기본값: 20)

        Returns:
            List[Tuple]: [(similarity, title, date, text, url), ...] 형태의 결합된 결과
        """
        # Step 1: Dense 결과를 (score, title, text, date, url) 형식으로 변환
        combine_dense_doc = []
        for score, (title, date, text, url) in dense_results:
            combine_dense_doc.append((score, title, text, date, url))

        # Step 2: 키워드 필터링 적용
        combine_dense_doc = self.keyword_filter(
            combine_dense_doc, query_nouns, user_question
        )

        # Step 3: Dense와 BM25 결과 병합
        final_best_docs = []

        # Dense 결과 처리
        for score, title, text, date, url in combine_dense_doc:
            matched = False

            # BM25 결과에서 동일 제목 찾기
            for bm25_doc in bm25_results:
                if bm25_doc[0] == title:  # 제목 일치
                    # 유사도 합산
                    bm25_idx = titles_from_pinecone.index(bm25_doc[0])
                    combined_similarity = score + bm25_similarities[bm25_idx]
                    final_best_docs.append((
                        combined_similarity,
                        bm25_doc[0],  # title
                        bm25_doc[1],  # date
                        bm25_doc[2],  # text
                        bm25_doc[3]   # url
                    ))
                    matched = True
                    break

            if not matched:
                # Dense 결과만 추가
                final_best_docs.append((score, title, date, text, url))

        # Step 4: BM25 결과 중 매칭되지 않은 문서 추가
        for bm25_doc in bm25_results:
            matched = False

            for score, title, text, date, url in combine_dense_doc:
                if bm25_doc[0] == title and bm25_doc[2] == text:
                    matched = True
                    break

            if not matched:
                # BM25 유사도 가져오기
                bm25_idx = titles_from_pinecone.index(bm25_doc[0])
                combined_similarity = bm25_similarities[bm25_idx]

                # 날짜 기반 유사도 조정
                combined_similarity = self.date_adjuster(
                    combined_similarity, bm25_doc[1], query_nouns
                )

                final_best_docs.append((
                    combined_similarity,
                    bm25_doc[0],  # title
                    bm25_doc[1],  # date
                    bm25_doc[2],  # text
                    bm25_doc[3]   # url
                ))

        # Step 5: 유사도 기준 정렬 및 상위 k개 추출
        final_best_docs.sort(key=lambda x: x[0], reverse=True)
        final_best_docs = final_best_docs[:top_k]

        # Step 6: 최종 키워드 필터링
        final_best_docs = self.keyword_filter(
            final_best_docs, query_nouns, user_question
        )
        final_best_docs.sort(key=lambda x: x[0], reverse=True)

        logger.debug(f"✅ 문서 결합 완료: {len(final_best_docs)}개 문서 반환")

        return final_best_docs
