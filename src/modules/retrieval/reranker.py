"""
Document Reranker
BGE-Reranker를 사용하여 검색된 문서를 질문과의 관련성 기준으로 재순위화
"""

import logging
from typing import List, Tuple
import time

logger = logging.getLogger(__name__)

# FlagEmbedding import 시도
try:
    from FlagEmbedding import FlagReranker
    RERANKER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  FlagEmbedding을 불러올 수 없습니다. Reranking이 비활성화됩니다.")
    RERANKER_AVAILABLE = False
    FlagReranker = None


class DocumentReranker:
    """
    BGE-Reranker를 사용한 문서 재순위화 클래스

    검색 엔진(BM25 + Dense)이 반환한 후보 문서들을
    질문과의 실제 관련성을 기준으로 재평가하여 순위를 조정합니다.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", use_fp16: bool = True):
        """
        DocumentReranker 초기화

        Args:
            model_name: 사용할 Reranker 모델 이름
                - "BAAI/bge-reranker-v2-m3": 다국어 지원 (한국어 포함), 권장
                - "BAAI/bge-reranker-large": 영어 전용, 더 높은 성능
            use_fp16: FP16 사용 여부 (GPU 메모리 절약, 속도 향상)
        """
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self.reranker = None

        if not RERANKER_AVAILABLE:
            logger.warning("❌ FlagEmbedding 미설치. Reranking 비활성화 (원본 순서 유지)")
            return

        try:
            logger.info(f"🔄 BGE-Reranker 로딩 중: {model_name}")
            start_time = time.time()

            self.reranker = FlagReranker(
                model_name,
                use_fp16=use_fp16,
                device='cpu'  # GPU 있으면 'cuda'로 변경 가능
            )

            load_time = time.time() - start_time
            logger.info(f"✅ BGE-Reranker 로딩 완료 ({load_time:.2f}초)")

        except Exception as e:
            logger.error(f"❌ BGE-Reranker 로딩 실패: {e}")
            logger.warning("⚠️  Reranking 비활성화 (원본 순서 유지)")
            self.reranker = None

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
        """
        if not self.reranker:
            # Reranker 사용 불가 시 원본 그대로 반환
            logger.debug("⏭️  Reranker 비활성화 - 원본 순서 유지")
            return documents[:top_k]

        if not documents:
            return []

        try:
            start_time = time.time()

            # 문서 리스트를 (query, document_text) 쌍으로 변환
            pairs = []
            for doc in documents:
                # doc = (score, title, date, text, url)
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
                # (original_score, title, date, text, url) →
                # (rerank_score, title, date, text, url, original_score)
                reranked_doc = (
                    rerank_score,  # 새로운 점수 (reranker 점수)
                    doc[1],  # title
                    doc[2],  # date
                    doc[3],  # text
                    doc[4],  # url
                    doc[0]   # original_score (참고용)
                )
                reranked_docs.append(reranked_doc)

            # 재순위 점수 기준으로 정렬 (내림차순)
            reranked_docs.sort(key=lambda x: x[0], reverse=True)

            # Top K 선택
            top_docs = reranked_docs[:top_k]

            rerank_time = time.time() - start_time

            # 로깅: 순위 변화 확인
            logger.info(f"🔄 Reranking 완료 ({rerank_time:.2f}초)")
            logger.info(f"   📊 입력: {len(documents)}개 → 출력: {len(top_docs)}개")

            # 상위 3개 문서의 점수 변화 로그
            for i, doc in enumerate(top_docs[:3]):
                rerank_score = doc[0]
                original_score = doc[5]
                title = doc[1][:50]
                logger.info(f"   {i+1}. [{rerank_score:.4f} ← {original_score:.4f}] {title}...")

            # 원본 형식으로 변환 (original_score 제거)
            final_docs = [
                (doc[0], doc[1], doc[2], doc[3], doc[4])
                for doc in top_docs
            ]

            return final_docs

        except Exception as e:
            logger.error(f"❌ Reranking 실패: {e}")
            logger.warning("⚠️  원본 순서 유지")
            return documents[:top_k]
