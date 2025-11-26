"""
Reranker Factory

Config 기반으로 적절한 Reranker 구현체를 생성합니다.
"""

from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class RerankerFactory:
    """
    Reranker 팩토리

    Config 기반으로 적절한 Reranker 구현체를 생성합니다.

    Examples:
        >>> # BGE Reranker 생성
        >>> reranker = RerankerFactory.create("bge")

        >>> # Config로 생성
        >>> reranker = RerankerFactory.create(
        ...     "bge",
        ...     model_name="BAAI/bge-reranker-v2-m3",
        ...     use_fp16=True
        ... )
    """

    _registry: Dict[str, type] = {}  # 등록된 Reranker 클래스들

    @classmethod
    def register(cls, name: str, reranker_class: type) -> None:
        """
        Reranker 구현체 등록

        Args:
            name: Reranker 이름 (예: "bge", "flashrank", "cohere")
            reranker_class: Reranker 클래스
        """
        cls._registry[name] = reranker_class
        logger.info(f"📦 Reranker 등록: '{name}' → {reranker_class.__name__}")

    @classmethod
    def create(
        cls,
        reranker_type: str,
        **kwargs: Any
    ) -> Optional['BaseReranker']:
        """
        Reranker 생성

        Args:
            reranker_type: Reranker 타입 ("bge", "flashrank", "cohere" 등)
            **kwargs: Reranker 초기화 파라미터

        Returns:
            BaseReranker 인스턴스 또는 None (실패 시)

        Examples:
            >>> reranker = RerankerFactory.create("bge")
            >>> reranker = RerankerFactory.create("bge", use_fp16=True)
        """
        if reranker_type not in cls._registry:
            logger.error(f"❌ 알 수 없는 Reranker 타입: '{reranker_type}'")
            logger.info(f"   사용 가능한 타입: {list(cls._registry.keys())}")
            return None

        try:
            reranker_class = cls._registry[reranker_type]
            reranker = reranker_class(**kwargs)
            logger.info(f"✅ Reranker 생성 완료: {reranker_type}")
            return reranker
        except Exception as e:
            logger.error(f"❌ Reranker 생성 실패 ({reranker_type}): {e}")
            return None

    @classmethod
    def list_available(cls) -> list:
        """
        사용 가능한 Reranker 타입 목록 반환

        Returns:
            List[str]: 등록된 Reranker 타입 리스트
        """
        return list(cls._registry.keys())


# ==========================================
# 기본 Reranker 등록
# ==========================================

def _register_default_rerankers() -> None:
    """기본 Reranker 등록"""
    # BGE Reranker
    try:
        from modules.retrieval.rerankers.bge_reranker import BGEReranker
        RerankerFactory.register("bge", BGEReranker)
    except ImportError as e:
        logger.debug(f"BGEReranker 등록 실패: {e}")

    # Cohere Reranker
    try:
        from modules.retrieval.rerankers.cohere_reranker import CohereReranker
        RerankerFactory.register("cohere", CohereReranker)
    except ImportError as e:
        logger.debug(f"CohereReranker 등록 실패: {e}")

    # 향후 추가 가능:
    # try:
    #     from modules.retrieval.rerankers.flashrank_reranker import FlashRankReranker
    #     RerankerFactory.register("flashrank", FlashRankReranker)
    # except ImportError:
    #     logger.debug("FlashRankReranker 사용 불가")


# 모듈 로드 시 자동 등록
_register_default_rerankers()
