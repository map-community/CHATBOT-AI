"""
Cohere Reranker Implementation

Cohere의 Rerank API를 사용한 Reranker 구현
"""

import logging
from typing import List, Tuple, Optional
import time

from .base import BaseReranker

logger = logging.getLogger(__name__)

# Cohere import 시도
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  cohere 라이브러리를 불러올 수 없습니다. CohereReranker가 비활성화됩니다.")
    COHERE_AVAILABLE = False
    cohere = None


class CohereReranker(BaseReranker):
    """
    Cohere Rerank API를 사용한 문서 재순위화 클래스

    Cohere의 최신 rerank-v3.5 모델을 사용하여
    검색 엔진(BM25 + Dense)이 반환한 후보 문서들을
    질문과의 실제 관련성을 기준으로 재평가하여 순위를 조정합니다.

    Features:
        - 다국어 지원 (rerank-v3.5는 multilingual 지원)
        - API 기반으로 별도 모델 다운로드 불필요
        - 높은 정확도와 빠른 응답 속도

    Examples:
        >>> reranker = CohereReranker(api_key="your_api_key")
        >>> reranked_docs = reranker.rerank(
        ...     query="최근 공지사항",
        ...     documents=candidate_docs,
        ...     top_k=5
        ... )
    """

    def __init__(
        self,
        api_key: str,
        model: str = "rerank-v3.5",
        max_tokens_per_doc: int = 4096
    ):
        """
        CohereReranker 초기화

        Args:
            api_key: Cohere API 키
            model: 사용할 Rerank 모델
                - "rerank-v3.5": 최신 모델 (다국어 지원, 권장)
                - "rerank-multilingual-v3.0": 이전 다국어 모델
                - "rerank-english-v3.0": 영어 전용
            max_tokens_per_doc: 문서당 최대 토큰 수 (기본 4096)
                - 긴 문서 자동 잘라내기
                - 비용/속도 최적화
        """
        self.api_key = api_key
        self.model = model
        self.max_tokens_per_doc = max_tokens_per_doc
        self.client = None

        if not COHERE_AVAILABLE:
            logger.warning("❌ cohere 라이브러리 미설치. CohereReranker 비활성화 (원본 순서 유지)")
            return

        if not api_key:
            logger.warning("❌ Cohere API 키가 제공되지 않았습니다. CohereReranker 비활성화")
            return

        try:
            logger.info(f"🔄 Cohere Reranker 초기화 중 (model: {model})...")
            start_time = time.time()

            # Cohere V2 Client 사용
            self.client = cohere.ClientV2(api_key=api_key)

            load_time = time.time() - start_time
            logger.info(f"✅ Cohere Reranker 초기화 완료 ({load_time:.2f}초)")

        except Exception as e:
            logger.error(f"❌ Cohere Reranker 초기화 실패: {e}")
            logger.warning("⚠️  CohereReranker 비활성화 (원본 순서 유지)")
            self.client = None

    def is_available(self) -> bool:
        """CohereReranker 사용 가능 여부"""
        return self.client is not None

    def get_model_info(self) -> dict:
        """모델 정보 반환"""
        return {
            "name": "CohereReranker",
            "type": "reranker",
            "model": self.model,
            "max_tokens_per_doc": self.max_tokens_per_doc,
            "available": self.is_available()
        }

    def rerank(
        self,
        query: str,
        documents: List[Tuple],
        top_k: int = 5
    ) -> List[Tuple]:
        """
        문서들을 질문과의 관련성 기준으로 재순위화

        Args:
            query: 사용자 질문
            documents: 재순위화할 문서 리스트
                      [(score, title, date, text, url), ...]
            top_k: 반환할 상위 문서 개수

        Returns:
            List[Tuple]: 재순위화된 문서 리스트 (상위 top_k개)
                        [(rerank_score, title, date, text, url), ...]
        """
        if not self.client:
            # Reranker 사용 불가 시 원본 그대로 반환
            logger.debug("⏭️  CohereReranker 비활성화 - 원본 순서 유지")
            return documents[:top_k]

        if not documents:
            return []

        try:
            start_time = time.time()

            # 문서 텍스트 추출
            doc_texts = []
            for doc in documents:
                # doc = (score, title, date, text, url) 또는 더 긴 tuple
                title = doc[1]
                text = doc[3]

                # 제목 + 본문 결합 (제목이 중요한 신호이므로)
                combined_text = f"{title}\n\n{text}"
                doc_texts.append(combined_text)

            # Cohere Rerank API 호출 (V2Client)
            response = self.client.rerank(
                model=self.model,
                query=query,
                documents=doc_texts,
                top_n=min(top_k, len(documents)),  # API에서 직접 top_k 개만 반환
                max_tokens_per_doc=self.max_tokens_per_doc  # 문서당 토큰 제한
            )

            # 결과 매핑
            reranked_docs = []
            for result in response.results:
                idx = result.index
                rerank_score = result.relevance_score

                original_doc = documents[idx]

                # (original_score, title, date, text, url, ...) →
                # (rerank_score, title, date, text, url)
                reranked_doc = (
                    rerank_score,  # 새로운 점수 (reranker 점수)
                    original_doc[1],  # title
                    original_doc[2],  # date
                    original_doc[3],  # text
                    original_doc[4],  # url
                )
                reranked_docs.append(reranked_doc)

            rerank_time = time.time() - start_time

            # 로깅
            logger.info(f"🔄 Cohere Reranking 완료 ({rerank_time:.2f}초)")
            logger.info(f"   📊 입력: {len(documents)}개 → 출력: {len(reranked_docs)}개")

            # 상위 3개 문서의 점수 로그
            for i, doc in enumerate(reranked_docs[:3]):
                rerank_score = doc[0]
                title = doc[1][:50]
                logger.info(f"   {i+1}. [{rerank_score:.4f}] {title}...")

            return reranked_docs

        except Exception as e:
            logger.error(f"❌ Cohere Reranking 실패: {e}")
            logger.warning("⚠️  원본 순서 유지")
            return documents[:top_k]

    def compute_score(self, query: str, document: str) -> float:
        """
        단일 문서의 관련성 점수 계산

        Args:
            query: 사용자 질문
            document: 문서 텍스트

        Returns:
            float: 관련성 점수
        """
        if not self.client:
            logger.warning("⚠️  CohereReranker 비활성화 - 기본 점수 0.0 반환")
            return 0.0

        try:
            response = self.client.rerank(
                model=self.model,
                query=query,
                documents=[document],
                top_n=1,
                max_tokens_per_doc=self.max_tokens_per_doc
            )

            if response.results:
                return response.results[0].relevance_score
            else:
                return 0.0

        except Exception as e:
            logger.error(f"❌ 점수 계산 실패: {e}")
            return 0.0
