"""
BGE Reranker Implementation

BAAI의 BGE (BGE-Reranker-v2-m3) 모델을 사용한 Reranker 구현
"""

import logging
from typing import List, Tuple
import time

from .base import BaseReranker

logger = logging.getLogger(__name__)

# FlagEmbedding import 시도
try:
    from FlagEmbedding import FlagReranker  # type: ignore
    RERANKER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  FlagEmbedding을 불러올 수 없습니다. BGEReranker가 비활성화됩니다.")
    RERANKER_AVAILABLE = False
    FlagReranker = None


class BGEReranker(BaseReranker):
    """
    BGE-Reranker를 사용한 문서 재순위화 클래스

    BAAI/bge-reranker-v2-m3 모델을 사용하여
    검색 엔진(BM25 + Dense)이 반환한 후보 문서들을
    질문과의 실제 관련성을 기준으로 재평가하여 순위를 조정합니다.

    Features:
        - 다국어 지원 (한국어 포함)
        - 높은 정확도
        - FP16 지원 (GPU 메모리 절약)

    Examples:
        >>> reranker = BGEReranker()
        >>> reranked_docs = reranker.rerank(
        ...     query="최근 공지사항",
        ...     documents=candidate_docs,
        ...     top_k=5
        ... )
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        use_fp16: bool = True,
        device: str = "cpu"
    ):
        """
        BGEReranker 초기화

        Args:
            model_name: 사용할 Reranker 모델 이름
                - "BAAI/bge-reranker-v2-m3": 다국어 지원 (한국어 포함), 권장
                - "BAAI/bge-reranker-large": 영어 전용, 더 높은 성능
            use_fp16: FP16 사용 여부 (GPU 메모리 절약, 속도 향상)
            device: 디바이스 ("cpu" 또는 "cuda")
        """
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self.device = device
        self.reranker = None

        if not RERANKER_AVAILABLE:
            logger.warning("❌ FlagEmbedding 미설치. BGEReranker 비활성화 (원본 순서 유지)")
            return

        try:
            logger.info(f"🔄 BGE-Reranker 로딩 중: {model_name}")
            start_time = time.time()

            self.reranker = FlagReranker(
                model_name,
                use_fp16=use_fp16,
                device=device
            )

            load_time = time.time() - start_time
            logger.info(f"✅ BGE-Reranker 로딩 완료 ({load_time:.2f}초)")

        except Exception as e:
            logger.error(f"❌ BGE-Reranker 로딩 실패: {e}")
            logger.warning("⚠️  BGEReranker 비활성화 (원본 순서 유지)")
            self.reranker = None

    def is_available(self) -> bool:
        """BGEReranker 사용 가능 여부"""
        return self.reranker is not None

    def get_model_info(self) -> dict:
        """모델 정보 반환"""
        return {
            "name": "BGEReranker",
            "type": "reranker",
            "model": self.model_name,
            "device": self.device,
            "fp16": self.use_fp16,
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
        if not self.reranker:
            # Reranker 사용 불가 시 원본 그대로 반환
            logger.debug("⏭️  BGEReranker 비활성화 - 원본 순서 유지")
            return documents[:top_k]

        if not documents:
            return []

        try:
            start_time = time.time()

            # 문서 리스트를 (query, document_text) 쌍으로 변환
            pairs = []
            for doc in documents:
                # doc = (score, title, date, text, url) 또는 더 긴 tuple
                title = doc[1]
                text = doc[3]

                # 제목 + 본문 결합 (제목이 중요한 신호이므로)
                combined_text = f"{title}\n\n{text[:500]}"  # 500자로 제한 (속도 향상)
                pairs.append([query, combined_text])

            # Reranker로 관련성 점수 계산
            rerank_scores = self.reranker.compute_score(pairs)

            # 스칼라 값으로 변환 (numpy array → float)
            if hasattr(rerank_scores, '__iter__'):
                rerank_scores = [float(score) for score in rerank_scores]
            else:
                rerank_scores = [float(rerank_scores)]

            # 원본 문서에 재순위 점수 추가
            reranked_docs = []
            for doc, rerank_score in zip(documents, rerank_scores):
                # (original_score, title, date, text, url, ...) →
                # (rerank_score, title, date, text, url, ...)
                reranked_doc = (
                    rerank_score,  # 새로운 점수 (reranker 점수)
                    doc[1],        # title
                    doc[2],        # date
                    doc[3],        # text
                    doc[4],        # url
                    *doc[5:]       # 추가 필드들 (있으면)
                )
                reranked_docs.append(reranked_doc)

            # 재순위 점수 기준으로 정렬 (내림차순)
            reranked_docs.sort(key=lambda x: x[0], reverse=True)

            # Top K 선택
            top_docs = reranked_docs[:top_k]

            rerank_time = time.time() - start_time

            # 로깅: 순위 변화 확인
            logger.info(f"🔄 BGE Reranking 완료 ({rerank_time:.2f}초)")
            logger.info(f"   📊 입력: {len(documents)}개 → 출력: {len(top_docs)}개")

            # 상위 3개 문서의 점수 로그
            for i, doc in enumerate(top_docs[:3]):
                rerank_score = doc[0]
                title = doc[1][:50]
                logger.info(f"   {i+1}. [{rerank_score:.4f}] {title}...")

            # 원본 형식으로 반환 (처음 5개 필드만, 추가 필드는 제외)
            final_docs = [
                (doc[0], doc[1], doc[2], doc[3], doc[4])
                for doc in top_docs
            ]

            return final_docs

        except Exception as e:
            logger.error(f"❌ BGE Reranking 실패: {e}")
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
        if not self.reranker:
            logger.warning("⚠️  BGEReranker 비활성화 - 기본 점수 0.0 반환")
            return 0.0

        try:
            score = self.reranker.compute_score([[query, document]])
            return float(score[0]) if hasattr(score, '__iter__') else float(score)
        except Exception as e:
            logger.error(f"❌ 점수 계산 실패: {e}")
            return 0.0
