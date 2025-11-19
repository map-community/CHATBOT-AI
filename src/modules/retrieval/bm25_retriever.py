"""
BM25 Retriever
BM25 알고리즘을 사용한 문서 검색 클래스
"""

import numpy as np
import pickle
from rank_bm25 import BM25Okapi
from typing import List, Tuple
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class BM25Retriever:
    """
    BM25 알고리즘을 사용하여 문서를 검색하는 클래스

    제목, 본문, HTML 구조화 데이터를 결합하여 토큰화하고, BM25 유사도를 계산하여
    가장 관련성 높은 문서를 반환합니다.

    개선사항:
    - 제목뿐만 아니라 본문도 검색하여 첨부파일 내용도 찾을 수 있습니다.
    - HTML 구조화 데이터(표 등)도 검색하여 정확도를 높입니다.
    """

    def __init__(self,
                 titles: List[str],
                 texts: List[str],
                 urls: List[str],
                 dates: List[str],
                 query_transformer,
                 similarity_adjuster,
                 htmls: List[str] = None,
                 k1: float = 1.5,
                 b: float = 0.75,
                 redis_client = None):
        """
        BM25Retriever 초기화

        Args:
            titles: 문서 제목 리스트
            texts: 문서 본문 리스트
            urls: 문서 URL 리스트
            dates: 문서 날짜 리스트
            query_transformer: 질문을 명사로 변환하는 함수 (transformed_query)
            similarity_adjuster: 유사도를 조정하는 함수 (adjust_similarity_scores)
            htmls: HTML 구조화 데이터 리스트 (선택, 표 검색 개선용)
            k1: BM25 k1 파라미터 (기본값: 1.5)
            b: BM25 b 파라미터 (기본값: 0.75)
            redis_client: Redis 클라이언트 (선택, 캐싱용)
        """
        self.titles = titles
        self.texts = texts
        self.urls = urls
        self.dates = dates
        self.htmls = htmls if htmls else []
        self.query_transformer = query_transformer
        self.similarity_adjuster = similarity_adjuster
        self.k1 = k1
        self.b = b
        self.redis_client = redis_client
        
        # 캐시 키 설정
        self.cache_key = "bm25_tokenized_documents"

        # BM25 인덱스 생성 (제목 + 본문 + HTML 텍스트 결합하여 검색)
        self.tokenized_documents = []
        loaded_from_cache = False

        # 1. Redis 캐시 확인
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(self.cache_key)
                if cached_data:
                    cached_tokens = pickle.loads(cached_data)
                    # 문서 개수가 일치하는지 확인 (간단한 유효성 검사)
                    if len(cached_tokens) == len(titles):
                        self.tokenized_documents = cached_tokens
                        loaded_from_cache = True
                        logger.info(f"🚀 Redis에서 BM25 토큰 로드 완료! ({len(self.tokenized_documents)}개)")
                    else:
                        logger.warning(f"⚠️  BM25 캐시 개수 불일치 (캐시: {len(cached_tokens)}, 현재: {len(titles)}). 다시 생성합니다.")
            except Exception as e:
                logger.warning(f"⚠️  Redis에서 BM25 토큰 로드 실패: {e}")

        # 2. 캐시가 없으면 새로 생성
        if not loaded_from_cache:
            logger.info("🔄 BM25 인덱스 생성 중 (제목+본문+HTML 검색)...")
            for i, (title, text) in enumerate(zip(titles, texts)):
                # HTML에서 텍스트 추출
                html_text = ""
                if self.htmls and i < len(self.htmls) and self.htmls[i]:
                    try:
                        soup = BeautifulSoup(self.htmls[i], 'html.parser')
                        html_text = soup.get_text(separator=' ', strip=True)
                    except:
                        html_text = ""

                # 제목 + 본문 + HTML 텍스트 결합
                combined = f"{title} {text} {html_text}".strip()
                self.tokenized_documents.append(query_transformer(combined))
            
            # 3. Redis에 저장
            if self.redis_client:
                try:
                    # 24시간 유효
                    self.redis_client.setex(self.cache_key, 86400, pickle.dumps(self.tokenized_documents))
                    logger.info(f"💾 Redis에 BM25 토큰 저장 완료 ({len(self.tokenized_documents)}개)")
                except Exception as e:
                    logger.warning(f"⚠️  Redis에 BM25 토큰 저장 실패: {e}")

        self.bm25_index = BM25Okapi(self.tokenized_documents, k1=k1, b=b)
        html_count = sum(1 for h in self.htmls if h) if self.htmls else 0
        logger.info(f"✅ BM25 인덱스 생성 완료 ({len(titles)}개 문서, HTML 구조: {html_count}개)")

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
                     dates: List[str],
                     htmls: List[str] = None):
        """
        BM25 인덱스 업데이트 (문서 추가/삭제 시 사용)

        Args:
            titles: 새로운 문서 제목 리스트
            texts: 새로운 문서 본문 리스트
            urls: 새로운 문서 URL 리스트
            dates: 새로운 문서 날짜 리스트
            htmls: HTML 구조화 데이터 리스트 (선택)
        """
        logger.info("🔄 BM25 인덱스 업데이트 중...")

        self.titles = titles
        self.texts = texts
        self.urls = urls
        self.dates = dates
        self.htmls = htmls if htmls else []

        # 제목 + 본문 + HTML 텍스트 결합하여 인덱스 생성
        self.tokenized_documents = []
        for i, (title, text) in enumerate(zip(titles, texts)):
            # HTML에서 텍스트 추출
            html_text = ""
            if self.htmls and i < len(self.htmls) and self.htmls[i]:
                try:
                    soup = BeautifulSoup(self.htmls[i], 'html.parser')
                    html_text = soup.get_text(separator=' ', strip=True)
                except:
                    html_text = ""

            # 제목 + 본문 + HTML 텍스트 결합
            combined = f"{title} {text} {html_text}".strip()
            self.tokenized_documents.append(self.query_transformer(combined))

        # Redis 캐시 업데이트
        if self.redis_client:
            try:
                # 24시간 유효
                self.redis_client.setex(self.cache_key, 86400, pickle.dumps(self.tokenized_documents))
                logger.info(f"💾 Redis BM25 토큰 캐시 업데이트 완료 ({len(self.tokenized_documents)}개)")
            except Exception as e:
                logger.warning(f"⚠️  Redis BM25 토큰 캐시 업데이트 실패: {e}")

        self.bm25_index = BM25Okapi(self.tokenized_documents, k1=self.k1, b=self.b)
        html_count = sum(1 for h in self.htmls if h) if self.htmls else 0
        logger.info(f"✅ BM25 인덱스 업데이트 완료 ({len(titles)}개 문서, HTML 구조: {html_count}개)")
