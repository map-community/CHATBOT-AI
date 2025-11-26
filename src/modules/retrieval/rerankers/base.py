"""
Base Reranker Interface

모든 Reranker 구현체가 따라야 하는 추상 인터페이스
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    """
    Reranker 추상 베이스 클래스

    모든 Reranker 구현체는 이 인터페이스를 구현해야 합니다.
    이를 통해 Reranker를 쉽게 교체할 수 있습니다.

    Examples:
        >>> reranker = BGEReranker()
        >>> reranked_docs = reranker.rerank(query="질문", documents=docs, top_k=5)

        >>> # 다른 Reranker로 교체
        >>> reranker = FlashRankReranker()
        >>> reranked_docs = reranker.rerank(query="질문", documents=docs, top_k=5)
    """

    @abstractmethod
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
                      또는 [(score, title, date, text, url, ...), ...] (추가 필드 가능)
            top_k: 반환할 상위 문서 개수

        Returns:
            List[Tuple]: 재순위화된 문서 리스트 (상위 top_k개)
                        [(new_score, title, date, text, url), ...]

        Raises:
            NotImplementedError: 구현되지 않은 경우
        """
        raise NotImplementedError("rerank() 메서드를 구현해야 합니다.")

    @abstractmethod
    def compute_score(self, query: str, document: str) -> float:
        """
        단일 문서의 관련성 점수 계산

        Args:
            query: 사용자 질문
            document: 문서 텍스트

        Returns:
            float: 관련성 점수 (높을수록 관련성 높음)

        Raises:
            NotImplementedError: 구현되지 않은 경우
        """
        raise NotImplementedError("compute_score() 메서드를 구현해야 합니다.")

    def is_available(self) -> bool:
        """
        Reranker 사용 가능 여부 확인

        Returns:
            bool: 사용 가능하면 True, 아니면 False
        """
        return True

    def get_model_info(self) -> dict:
        """
        Reranker 모델 정보 반환

        Returns:
            dict: 모델 정보 (name, type, version 등)
        """
        return {
            "name": self.__class__.__name__,
            "type": "reranker",
            "available": self.is_available()
        }
