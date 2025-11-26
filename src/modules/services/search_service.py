"""
Search Service

문서 검색, 랭킹, 재정렬 로직을 담당하는 서비스
"""
import logging
import re
from typing import Tuple, List, Optional
from datetime import datetime

from modules.constants import (
    NOTICE_BASE_URL,
    COMPANY_BASE_URL,
    SEMINAR_BASE_URL
)

logger = logging.getLogger(__name__)


class SearchService:
    """
    문서 검색 및 랭킹 서비스

    Responsibilities:
    - BM25 + Dense Retrieval 검색 오케스트레이션
    - 최근 공지사항/채용/세미나 특별 처리
    - Recency Boosting (날짜 기반 점수 부스팅)
    - URL 기반 중복 제거
    """

    def __init__(self, storage_manager):
        """
        Args:
            storage_manager: StorageManager 인스턴스
        """
        self.storage = storage_manager

        # URL 상수 (constants.py에서 import)
        self.NOTICE_BASE_URL = NOTICE_BASE_URL
        self.COMPANY_BASE_URL = COMPANY_BASE_URL
        self.SEMINAR_BASE_URL = SEMINAR_BASE_URL

    def search_documents(
        self,
        user_question: str,
        transformed_query_fn,
        find_url_fn
    ) -> Tuple[Optional[List], Optional[List]]:
        """
        메인 검색 오케스트레이션

        Args:
            user_question: 사용자 질문
            transformed_query_fn: 명사 추출 함수 (ai_modules.transformed_query)
            find_url_fn: URL 기반 문서 검색 함수 (ai_modules.find_url)

        Returns:
            Tuple[List, List]: (검색 결과 문서 리스트, 쿼리 명사 리스트)
                검색 실패 시 (None, None) 반환

        Process:
            1. Query noun extraction (명사 추출)
            2. Recent notices handling (최근 공지사항 특별 처리)
            3. BM25 + Dense search (하이브리드 검색)
            4. Combine results (결과 결합)
            5. Recency boosting (날짜 부스팅)
            6. URL deduplication (중복 제거)
        """
        import time

        # 1. Query Noun Extraction
        noun_time = time.time()
        query_noun = transformed_query_fn(user_question)
        query_noun_time = time.time() - noun_time
        print(f"명사화 변환 시간 : {query_noun_time}")

        if not query_noun:
            return None, None

        # 2. Recent Notices Handling (최근 공지사항/채용/세미나 특별 처리)
        recent_docs, key = self._handle_recent_notices(
            user_question, query_noun, find_url_fn
        )
        if recent_docs:
            return recent_docs, key

        # 3. BM25 Search
        bm_title_time = time.time()
        bm25_docs, bm25_similarities = self._bm25_search(query_noun)
        bm_title_f_time = time.time() - bm_title_time
        print(f"bm25 문서 뽑는시간: {bm_title_f_time}")

        # 4. Dense Retrieval
        dense_time = time.time()
        dense_docs = self._dense_search(user_question, query_noun)
        pinecone_time = time.time() - dense_time
        print(f"파인콘에서 top k 뽑는데 걸리는 시간 {pinecone_time}")

        # 5. Combine Results
        combine_time = time.time()
        combined_docs = self._combine_results(
            dense_docs, bm25_docs, bm25_similarities, query_noun, user_question
        )
        combine_f_time = time.time() - combine_time
        print(f"Bm25랑 pinecone 결합 시간: {combine_f_time}")

        # 6. Recency Boosting
        boosted_docs = self._apply_recency_boost(combined_docs)

        # 7. URL Deduplication
        final_docs = self._deduplicate_by_url(boosted_docs)

        return final_docs, query_noun

    def _handle_recent_notices(
        self,
        user_question: str,
        query_noun: List[str],
        find_url_fn
    ) -> Tuple[Optional[List], Optional[List]]:
        """
        최근 공지사항/채용/세미나 특별 처리

        Args:
            user_question: 사용자 질문
            query_noun: 추출된 명사 리스트
            find_url_fn: URL 기반 문서 검색 함수

        Returns:
            Tuple[Optional[List], Optional[List]]: (문서 리스트, 키워드 리스트)
                특별 처리 대상이 아니면 (None, None) 반환
        """
        import time

        # 불용어 제거
        remove_noticement = [
            '목록', '리스트', '내용', '제일', '가장', '공고', '공지사항', '필독',
            '첨부파일', '수업', '업데이트', '컴퓨터학부', '컴학', '상위', '정보',
            '관련', '세미나', '행사', '특강', '강연', '공지사항', '채용', '공고',
            '최근', '최신', '지금', '현재'
        ]
        query_nouns = [noun for noun in query_noun if noun not in remove_noticement]

        # 개수 추출
        numbers = 5  # 기본 5개
        check_num = 0
        for noun in query_nouns:
            if '개' in noun:
                num = re.findall(r'\d+', noun)
                if num:
                    numbers = int(num[0])
                    check_num = 1

        # 최근 공지사항/채용/세미나 질문 판별
        has_category = any(
            keyword in query_noun
            for keyword in ['세미나', '행사', '특강', '강연', '공지사항', '채용', '공고']
        )
        has_recent = any(
            keyword in query_noun
            for keyword in ['최근', '최신', '지금', '현재']
        )

        # 특별 처리 조건: (카테고리 키워드 + 최근 키워드 + 명사 거의 없음) OR 개수 지정
        if not (has_category and has_recent and len(query_nouns) < 1 or check_num == 1):
            return None, None

        # 캐시 데이터 가져오기
        titles_from_pinecone = self.storage.cached_titles
        texts_from_pinecone = self.storage.cached_texts
        urls_from_pinecone = self.storage.cached_urls
        dates_from_pinecone = self.storage.cached_dates

        # 0개 요청 (특수 케이스)
        if numbers == 0:
            keys = ['세미나', '행사', '특강', '강연', '공지사항', '채용']
            return None, [keyword for keyword in keys if keyword in user_question]

        # 카테고리별 URL 검색
        return_docs = []
        key = None
        recent_time = time.time()

        if '공지사항' in query_noun:
            key = ['공지사항']
            notice_url = self.NOTICE_BASE_URL + "&wr_id="
            return_docs = find_url_fn(
                notice_url, titles_from_pinecone, dates_from_pinecone,
                texts_from_pinecone, urls_from_pinecone, numbers
            )

        if '채용' in query_noun:
            key = ['채용']
            company_url = self.COMPANY_BASE_URL + "&wr_id="
            return_docs = find_url_fn(
                company_url, titles_from_pinecone, dates_from_pinecone,
                texts_from_pinecone, urls_from_pinecone, numbers
            )

        other_key = ['세미나', '행사', '특강', '강연']
        if any(keyword in query_noun for keyword in other_key):
            seminar_url = self.SEMINAR_BASE_URL + "&wr_id="
            key = [keyword for keyword in other_key if keyword in user_question]
            return_docs = find_url_fn(
                seminar_url, titles_from_pinecone, dates_from_pinecone,
                texts_from_pinecone, urls_from_pinecone, numbers
            )

        recent_finish_time = time.time() - recent_time
        print(f"최근 공지사항 문서 뽑는 시간 {recent_finish_time}")

        if len(return_docs) > 0:
            return return_docs, key

        return None, None

    def _bm25_search(self, query_noun: List[str]) -> Tuple[List, List]:
        """
        BM25 검색 수행

        Args:
            query_noun: 쿼리 명사 리스트

        Returns:
            Tuple[List, List]: (BM25 검색 결과, 유사도 리스트)
        """
        return self.storage.bm25_retriever.search(
            query_nouns=query_noun,
            top_k=50,  # ✨ 25→50 증가: URL 중복 제거 위한 후보군 확대
            normalize_factor=24.0
        )

    def _dense_search(self, user_question: str, query_noun: List[str]) -> List:
        """
        Dense Retrieval 검색 수행

        Args:
            user_question: 사용자 질문
            query_noun: 쿼리 명사 리스트

        Returns:
            List: Dense 검색 결과
        """
        return self.storage.dense_retriever.search(
            user_question=user_question,
            query_nouns=query_noun,
            top_k=50  # ✨ 30→50 증가: URL 중복 제거 위한 후보군 확대
        )

    def _combine_results(
        self,
        dense_results: List,
        bm25_results: List,
        bm25_similarities: List,
        query_nouns: List[str],
        user_question: str
    ) -> List:
        """
        BM25와 Dense Retrieval 결과 결합

        Args:
            dense_results: Dense 검색 결과
            bm25_results: BM25 검색 결과
            bm25_similarities: BM25 유사도 리스트
            query_nouns: 쿼리 명사 리스트
            user_question: 사용자 질문

        Returns:
            List: 결합된 문서 리스트
        """
        titles_from_pinecone = self.storage.cached_titles

        return self.storage.document_combiner.combine(
            dense_results=dense_results,
            bm25_results=bm25_results,
            bm25_similarities=bm25_similarities,
            titles_from_pinecone=titles_from_pinecone,
            query_nouns=query_nouns,
            user_question=user_question,
            top_k=30  # ✨ 20→30 증가: URL 중복 제거 전 후보군 확대
        )

    def _apply_recency_boost(self, docs: List) -> List:
        """
        날짜 부스팅 적용 (최신 문서 우선)

        Args:
            docs: 문서 리스트 [(score, title, date, text, url), ...]

        Returns:
            List: 부스팅 적용 후 재정렬된 문서 리스트
        """
        def calculate_recency_boost(doc_date_str: str) -> float:
            """
            문서 날짜에 따른 가중치 계산

            Args:
                doc_date_str: ISO 8601 형식 날짜 문자열

            Returns:
                float: 부스팅 가중치
                    - 6개월 이내: 1.5 (+50%)
                    - 1년 이내: 1.3 (+30%)
                    - 2년 이내: 1.1 (+10%)
                    - 2년 이상: 0.9 (-10%)
            """
            try:
                current_date = datetime.now()
                doc_date = datetime.fromisoformat(doc_date_str.replace('+09:00', ''))

                # 날짜 차이 계산 (일 단위)
                days_old = (current_date - doc_date).days

                # 가중치 계산
                if days_old < 0:  # 미래 날짜 (오류)
                    return 1.0
                elif days_old <= 180:  # 6개월 이내
                    return 1.5  # 50% 부스팅
                elif days_old <= 365:  # 1년 이내
                    return 1.3  # 30% 부스팅
                elif days_old <= 730:  # 2년 이내
                    return 1.1  # 10% 부스팅
                else:  # 2년 이상
                    return 0.9  # 10% 패널티

            except Exception as e:
                logger.debug(f"날짜 부스팅 계산 실패: {doc_date_str} - {e}")
                return 1.0  # 실패 시 중립

        # 부스팅 적용
        boosted_docs = []
        for score, title, date, text, url in docs:
            boost = calculate_recency_boost(date)
            boosted_score = score * boost
            boosted_docs.append((boosted_score, title, date, text, url))

        # 부스팅된 점수로 재정렬
        boosted_docs.sort(key=lambda x: x[0], reverse=True)

        logger.info(
            f"🚀 날짜 부스팅 완료 "
            f"(최신 문서 우선: 6개월 이내 +50%, 1년 이내 +30%)"
        )

        return boosted_docs

    def _deduplicate_by_url(self, docs: List) -> List:
        """
        URL 기반 중복 제거

        같은 게시글의 서로 다른 청크를 제거하여 검색 결과 다양성 확보
        같은 URL이면 최고 점수 청크만 선택

        Args:
            docs: 문서 리스트 [(score, title, date, text, url), ...]

        Returns:
            List: 중복 제거 후 Top 20 문서
        """
        import time

        dedup_time = time.time()

        seen_urls = {}  # {url: (score, title, date, text, url)}
        deduplicated_docs = []
        duplicate_count = 0
        original_count = len(docs)

        for score, title, date, text, url in docs:
            if url in seen_urls:
                # 같은 URL이 이미 있음 → 점수 비교
                existing_score = seen_urls[url][0]

                if score > existing_score:
                    # 더 높은 점수면 기존 문서 제거하고 새 문서 추가
                    deduplicated_docs.remove(seen_urls[url])
                    deduplicated_docs.append((score, title, date, text, url))
                    seen_urls[url] = (score, title, date, text, url)
                    logger.debug(
                        f"🔄 URL 중복 - 더 높은 점수로 교체: {title[:30]}... "
                        f"({existing_score:.2f} → {score:.2f})"
                    )
                else:
                    # 낮은 점수면 무시
                    duplicate_count += 1
                    logger.debug(
                        f"⏭️  URL 중복 제거: {title[:30]}... "
                        f"(점수: {score:.2f} < {existing_score:.2f})"
                    )
            else:
                # 새 URL이면 추가
                seen_urls[url] = (score, title, date, text, url)
                deduplicated_docs.append((score, title, date, text, url))

        # 점수순 재정렬 후 Top 20
        deduplicated_docs.sort(key=lambda x: x[0], reverse=True)
        final_docs = deduplicated_docs[:20]

        dedup_f_time = time.time() - dedup_time
        unique_urls = len(seen_urls)
        print(
            f"URL 중복 제거: {dedup_f_time:.4f}초 "
            f"(원본: {original_count}개 → 중복 {duplicate_count}개 제거 → "
            f"최종: {len(final_docs)}개 서로 다른 게시글, 고유 URL {unique_urls}개)"
        )

        return final_docs
