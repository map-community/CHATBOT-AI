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
from multiprocessing import Pool, cpu_count
import time
import os

logger = logging.getLogger(__name__)


def get_safe_cpu_count() -> int:
    """
    Docker CPU 제한을 고려한 안전한 CPU 개수 반환

    Returns:
        사용 가능한 CPU 개수

    Note:
        1. 환경변수 OMP_NUM_THREADS 우선 사용 (Docker에서 설정)
        2. 없으면 물리 CPU의 절반 사용 (컨텍스트 스위칭 최소화)
        3. 최소 1개 보장
    """
    # Docker 환경변수 우선 확인
    env_threads = os.getenv("OMP_NUM_THREADS")
    if env_threads:
        try:
            return max(1, int(env_threads))
        except ValueError:
            pass

    # 물리 CPU의 절반 사용 (안전한 기본값)
    physical_cores = cpu_count() or 1
    return max(1, physical_cores // 2)


def _parse_html_to_text(html_or_markdown: str) -> str:
    """
    HTML 또는 Markdown을 텍스트로 변환 (병렬 처리용 top-level 함수)

    Args:
        html_or_markdown: HTML 또는 Markdown 문자열

    Returns:
        파싱된 텍스트

    Note:
        - Markdown (Upstage API 제공): 표 구조 보존, 그대로 반환
        - HTML (fallback): BeautifulSoup으로 파싱
    """
    if not html_or_markdown:
        return ""

    # Markdown 형식 감지 (표 형식: '|' 구분자)
    # Markdown이면 그대로 반환 (이미 LLM이 이해하기 좋은 형태)
    if '|' in html_or_markdown and ('---' in html_or_markdown or '\n' in html_or_markdown):
        # Markdown 표 형식으로 보임
        return html_or_markdown

    # HTML이면 파싱
    try:
        soup = BeautifulSoup(html_or_markdown, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except Exception:
        # 파싱 실패 시 원본 반환
        return html_or_markdown


# ✅ 병렬 토큰화용 전역 함수 (top-level에 정의해야 multiprocessing에서 pickle 가능)
_global_query_transformer = None

def _set_global_query_transformer(transformer):
    """병렬 프로세스용 전역 transformer 설정"""
    global _global_query_transformer
    _global_query_transformer = transformer

def _tokenize_combined_text(combined_text: str) -> list:
    """
    텍스트를 토큰화 (병렬 처리용 top-level 함수)

    Args:
        combined_text: 결합된 텍스트 (제목 + 본문 + HTML)

    Returns:
        토큰 리스트
    """
    global _global_query_transformer
    if _global_query_transformer is None:
        # fallback: 공백 기준 split (형태소 분석 없음)
        return combined_text.split()
    return _global_query_transformer(combined_text)


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

        # 캐시 키 설정 (v2: HTML 파싱 결과 포함)
        self.cache_key = "bm25_cache_v2"

        # BM25 인덱스 생성 (제목 + 본문 + HTML 텍스트 결합하여 검색)
        self.tokenized_documents = []
        html_texts = []  # 파싱된 HTML 텍스트
        loaded_from_cache = False

        # 1. Redis 캐시 확인
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(self.cache_key)
                if cached_data:
                    cache_obj = pickle.loads(cached_data)
                    # v2 캐시 구조: {"tokenized_documents": [...], "html_texts": [...], "doc_count": N}
                    if isinstance(cache_obj, dict) and cache_obj.get("doc_count") == len(titles):
                        self.tokenized_documents = cache_obj["tokenized_documents"]
                        html_texts = cache_obj.get("html_texts", [])
                        loaded_from_cache = True
                        logger.info(f"🚀 Redis에서 BM25 캐시 로드 완료! ({len(self.tokenized_documents)}개 문서)")
                    else:
                        logger.warning(f"⚠️  BM25 캐시 버전 또는 개수 불일치. 다시 생성합니다.")
            except Exception as e:
                logger.warning(f"⚠️  Redis에서 BM25 캐시 로드 실패: {e}")

        # 2. 캐시가 없으면 새로 생성
        if not loaded_from_cache:
            start_time = time.time()
            logger.info("🔄 BM25 인덱스 생성 중 (제목+본문+HTML 검색)...")

            # 2-1. HTML 파싱 (병렬 처리)
            html_count = sum(1 for h in self.htmls if h) if self.htmls else 0
            if html_count > 0:
                logger.info(f"   📄 HTML 파싱 시작 ({html_count}개, 병렬 처리: {get_safe_cpu_count()}코어)...")
                parse_start = time.time()

                # 병렬 처리로 HTML 파싱
                with Pool(processes=get_safe_cpu_count()) as pool:
                    html_texts = pool.map(_parse_html_to_text, self.htmls)

                parse_time = time.time() - parse_start
                logger.info(f"   ✅ HTML 파싱 완료 ({parse_time:.2f}초)")
            else:
                # HTML이 없으면 빈 문자열 리스트
                html_texts = [""] * len(titles)

            # 2-2. 토큰화 (제목 + 본문 + HTML 텍스트)
            logger.info(f"   🔤 토큰화 준비 중 ({len(titles)}개 문서)...")
            tokenize_start = time.time()

            # ✅ 1단계: 텍스트 결합
            logger.info(f"      [1/2] 텍스트 결합 중...")
            combined_texts = []
            for i, (title, text) in enumerate(zip(titles, texts)):
                html_text = html_texts[i] if i < len(html_texts) else ""
                combined = f"{title} {text} {html_text}".strip()
                combined_texts.append(combined)

            logger.info(f"      [1/2] 텍스트 결합 완료 ({len(combined_texts)}개)")

            # ✅ 2단계: 병렬 토큰화 (실제 형태소 분석 - 시간 소요!)
            logger.info(f"      [2/2] 병렬 토큰화 진행 중 ({get_safe_cpu_count()}코어, Mecab 형태소 분석)...")
            logger.info(f"      ⏳ 예상 소요 시간: 1-2분 (13000개 기준)")

            parallel_start = time.time()
            # 🚀 최적화 1: chunksize 추가 (프로세스 생성 오버헤드 최소화)
            # 13073개 / 2코어 = 6500개/코어 → chunksize 동적 계산
            chunksize = max(1, len(combined_texts) // (get_safe_cpu_count() * 10))
            logger.info(f"      📦 Batch 크기: {chunksize} (프로세스 통신 최소화)")

            with Pool(processes=get_safe_cpu_count(), initializer=_set_global_query_transformer, initargs=(query_transformer,)) as pool:
                self.tokenized_documents = pool.map(_tokenize_combined_text, combined_texts, chunksize=chunksize)

            parallel_time = time.time() - parallel_start
            logger.info(f"      [2/2] 병렬 토큰화 완료! ({parallel_time:.2f}초, {len(combined_texts)/parallel_time:.0f}문서/초)")

            tokenize_time = time.time() - tokenize_start
            logger.info(f"   ✅ 토큰화 완료 ({tokenize_time:.2f}초, 속도: {len(titles)/tokenize_time:.0f}문서/초)")

            # 3. Redis에 저장 (v2 구조)
            if self.redis_client:
                try:
                    cache_obj = {
                        "tokenized_documents": self.tokenized_documents,
                        "html_texts": html_texts,
                        "doc_count": len(titles)
                    }
                    # 24시간 유효
                    self.redis_client.setex(self.cache_key, 86400, pickle.dumps(cache_obj))

                    # 캐시 크기 확인
                    cache_size = len(pickle.dumps(cache_obj)) / (1024 * 1024)  # MB
                    logger.info(f"💾 Redis에 BM25 캐시 저장 완료 ({len(self.tokenized_documents)}개, {cache_size:.2f}MB)")
                except Exception as e:
                    logger.warning(f"⚠️  Redis에 BM25 캐시 저장 실패: {e}")

            total_time = time.time() - start_time
            logger.info(f"   ⏱️  총 소요 시간: {total_time:.2f}초")

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
        start_time = time.time()
        logger.info("🔄 BM25 인덱스 업데이트 중...")

        self.titles = titles
        self.texts = texts
        self.urls = urls
        self.dates = dates
        self.htmls = htmls if htmls else []

        # HTML 파싱 (병렬 처리)
        html_count = sum(1 for h in self.htmls if h) if self.htmls else 0
        html_texts = []

        if html_count > 0:
            logger.info(f"   📄 HTML 파싱 시작 ({html_count}개, 병렬 처리: {get_safe_cpu_count()}코어)...")
            parse_start = time.time()

            # 병렬 처리로 HTML 파싱
            with Pool(processes=get_safe_cpu_count()) as pool:
                html_texts = pool.map(_parse_html_to_text, self.htmls)

            parse_time = time.time() - parse_start
            logger.info(f"   ✅ HTML 파싱 완료 ({parse_time:.2f}초)")
        else:
            html_texts = [""] * len(titles)

        # 토큰화 (제목 + 본문 + HTML 텍스트)
        logger.info(f"   🔤 토큰화 준비 중 ({len(titles)}개 문서)...")
        tokenize_start = time.time()

        # ✅ 1단계: 텍스트 결합
        logger.info(f"      [1/2] 텍스트 결합 중...")
        combined_texts = []
        for i, (title, text) in enumerate(zip(titles, texts)):
            html_text = html_texts[i] if i < len(html_texts) else ""
            combined = f"{title} {text} {html_text}".strip()
            combined_texts.append(combined)

        logger.info(f"      [1/2] 텍스트 결합 완료 ({len(combined_texts)}개)")

        # ✅ 2단계: 병렬 토큰화 (실제 형태소 분석 - 시간 소요!)
        logger.info(f"      [2/2] 병렬 토큰화 진행 중 ({get_safe_cpu_count()}코어, Mecab 형태소 분석)...")
        logger.info(f"      ⏳ 예상 소요 시간: 1-2분 (13000개 기준)")

        parallel_start = time.time()
        # 🚀 최적화 1: chunksize 추가 (프로세스 생성 오버헤드 최소화)
        chunksize = max(1, len(combined_texts) // (get_safe_cpu_count() * 10))
        logger.info(f"      📦 Batch 크기: {chunksize} (프로세스 통신 최소화)")

        with Pool(processes=get_safe_cpu_count(), initializer=_set_global_query_transformer, initargs=(self.query_transformer,)) as pool:
            self.tokenized_documents = pool.map(_tokenize_combined_text, combined_texts, chunksize=chunksize)

        parallel_time = time.time() - parallel_start
        logger.info(f"      [2/2] 병렬 토큰화 완료! ({parallel_time:.2f}초, {len(combined_texts)/parallel_time:.0f}문서/초)")

        tokenize_time = time.time() - tokenize_start
        logger.info(f"   ✅ 토큰화 완료 ({tokenize_time:.2f}초, 속도: {len(titles)/tokenize_time:.0f}문서/초)")

        # Redis 캐시 업데이트 (v2 구조)
        if self.redis_client:
            try:
                cache_obj = {
                    "tokenized_documents": self.tokenized_documents,
                    "html_texts": html_texts,
                    "doc_count": len(titles)
                }
                # 24시간 유효
                self.redis_client.setex(self.cache_key, 86400, pickle.dumps(cache_obj))

                cache_size = len(pickle.dumps(cache_obj)) / (1024 * 1024)  # MB
                logger.info(f"💾 Redis BM25 캐시 업데이트 완료 ({len(self.tokenized_documents)}개, {cache_size:.2f}MB)")
            except Exception as e:
                logger.warning(f"⚠️  Redis BM25 캐시 업데이트 실패: {e}")

        self.bm25_index = BM25Okapi(self.tokenized_documents, k1=self.k1, b=self.b)
        html_count = sum(1 for h in self.htmls if h) if self.htmls else 0

        total_time = time.time() - start_time
        logger.info(f"✅ BM25 인덱스 업데이트 완료 ({len(titles)}개 문서, HTML 구조: {html_count}개, {total_time:.2f}초)")
