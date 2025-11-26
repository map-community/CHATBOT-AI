"""
Document Reranker (Backward Compatibility Wrapper)

[REFACTORED] 이 모듈은 하위 호환성을 위한 wrapper입니다.
실제 구현은 rerankers/bge_reranker.py로 이동되었습니다.

Migration Guide:
    # 기존 코드 (계속 작동함)
    from modules.retrieval.reranker import DocumentReranker
    reranker = DocumentReranker()

    # 새 코드 (권장)
    from modules.retrieval.rerankers.bge_reranker import BGEReranker
    reranker = BGEReranker()

    # 또는 Factory 사용 (가장 권장)
    from factories.reranker_factory import RerankerFactory
    reranker = RerankerFactory.create("bge")
"""

import logging
from typing import List, Tuple

# 실제 구현체 import
from .rerankers.bge_reranker import BGEReranker

logger = logging.getLogger(__name__)

# ==========================================
# 하위 호환성을 위한 별칭
# ==========================================
DocumentReranker = BGEReranker

# FlagEmbedding 가용성 (하위 호환)
try:
    from FlagEmbedding import FlagReranker
    RERANKER_AVAILABLE = True
except ImportError:
    RERANKER_AVAILABLE = False

__all__ = ["DocumentReranker", "RERANKER_AVAILABLE", "BGEReranker"]
