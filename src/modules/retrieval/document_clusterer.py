"""
Document Clusterer
문서 클러스터링 및 최적 문서 선택 클래스
"""

import re
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Tuple, Callable

logger = logging.getLogger(__name__)


class DocumentClusterer:
    """
    문서를 클러스터링하고 최적의 클러스터를 선택하는 클래스

    제목 유사도를 기반으로 문서를 그룹화하고,
    유사도/날짜/키워드를 종합적으로 분석하여 최적의 문서 그룹을 선택합니다.
    """

    def __init__(self,
                 date_parser: Callable,
                 similarity_threshold: float = 0.89):
        """
        DocumentClusterer 초기화

        Args:
            date_parser: 날짜 문자열을 datetime 객체로 변환하는 함수
            similarity_threshold: 클러스터링 유사도 임계값 (기본값: 0.89)
        """
        self.date_parser = date_parser
        self.similarity_threshold = similarity_threshold
        logger.info("✅ DocumentClusterer 초기화 완료")

    def cluster_and_select(self,
                           documents: List[Tuple],
                           query_nouns: List[str],
                           all_titles: List[str],
                           all_dates: List[str],
                           all_texts: List[str],
                           all_urls: List[str]) -> Tuple[List[Tuple], int]:
        """
        문서를 클러스터링하고 최적의 클러스터를 선택

        Args:
            documents: 정렬할 문서 리스트 [(similarity, title, date, text, url), ...]
            query_nouns: 검색 질문의 명사 리스트
            all_titles: 전체 문서 제목 리스트 (중복 문서 찾기용)
            all_dates: 전체 문서 날짜 리스트
            all_texts: 전체 문서 본문 리스트
            all_urls: 전체 문서 URL 리스트

        Returns:
            Tuple[List[Tuple], int]: (최종 문서 리스트, 중복 문서 개수)
        """
        # Step 1: 문서 클러스터링
        clusters = self._cluster_documents_by_similarity(documents)

        # Step 2: 최적 클러스터 선택
        sorted_cluster = self._select_best_cluster(clusters, query_nouns)

        # Step 3: 중복 제목 문서 추가 및 유사도 부스팅
        final_cluster, count = self._organize_documents(
            sorted_cluster, all_titles, all_dates, all_texts, all_urls
        )

        logger.debug(f"✅ 클러스터링 완료: {len(clusters)}개 클러스터 → {count}개 중복 문서 포함")

        return final_cluster[:count], count

    def _cluster_documents_by_similarity(self,
                                          docs: List[Tuple],
                                          threshold: float = None) -> List[List[Tuple]]:
        """
        제목 유사도 기반 문서 클러스터링

        Args:
            docs: 문서 리스트 [(similarity, title, date, text, url), ...]
            threshold: 유사도 임계값 (None일 경우 self.similarity_threshold 사용)

        Returns:
            List[List[Tuple]]: 클러스터 리스트
        """
        if threshold is None:
            threshold = self.similarity_threshold

        clusters = []

        for doc in docs:
            title = doc[1]
            added_to_cluster = False

            # 기존 클러스터와 비교
            for cluster in clusters:
                cluster_title = cluster[0][1]
                similarity = SequenceMatcher(None, cluster_title, title).ratio()

                # 유사도가 threshold 이상이면 클러스터에 추가
                if similarity >= threshold:
                    cluster_date = self.date_parser(cluster[0][2])
                    doc_date = self.date_parser(doc[2])
                    date_diff_days = abs(cluster_date - doc_date).days

                    # 제목이 동일하거나, 조건을 만족하면 추가
                    similarity_diff = -doc[0] + cluster[0][0]
                    text_different = cluster[0][3] != doc[3]

                    if (cluster_title == title or
                        (similarity_diff < 0.6 and text_different and date_diff_days < 60)):
                        cluster.append(doc)

                    added_to_cluster = True
                    break

            # 유사한 클러스터가 없으면 새 클러스터 생성
            if not added_to_cluster:
                clusters.append([doc])

        return clusters

    def _select_best_cluster(self,
                              clusters: List[List[Tuple]],
                              query_nouns: List[str]) -> List[Tuple]:
        """
        최적의 클러스터 선택 및 정렬

        Args:
            clusters: 클러스터 리스트
            query_nouns: 검색 질문의 명사 리스트

        Returns:
            List[Tuple]: 선택된 클러스터의 문서 리스트 (정렬됨)
        """
        if len(clusters) == 1:
            # 클러스터가 1개면 유사도순 정렬
            return sorted(clusters[0], key=lambda doc: doc[0], reverse=True)

        # 상위 2개 클러스터의 최고 유사도
        top_0_similarity = clusters[0][0][0]
        top_1_similarity = clusters[1][0][0]

        # 키워드 체크
        recency_keywords = ["최근", "최신", "현재", "지금"]
        has_recency_keyword = any(
            keyword in word for word in query_nouns for keyword in recency_keywords
        )

        last_cluster_similarity = clusters[-1][0][0]

        # Case 1: 상위 2개 클러스터 유사도 차이가 작은 경우 (<=0.3)
        if top_0_similarity - top_1_similarity <= 0.3:
            return self._handle_ambiguous_query(
                clusters, query_nouns, has_recency_keyword,
                top_0_similarity, top_1_similarity, last_cluster_similarity
            )
        # Case 2: 유사도 차이가 명확한 경우
        else:
            return self._handle_clear_query(
                clusters, query_nouns, has_recency_keyword
            )

    def _handle_ambiguous_query(self,
                                 clusters: List[List[Tuple]],
                                 query_nouns: List[str],
                                 has_recency_keyword: bool,
                                 top_0_sim: float,
                                 top_1_sim: float,
                                 last_sim: float) -> List[Tuple]:
        """
        모호한 질문 처리 (상위 클러스터 간 유사도 차이가 작을 때)

        Args:
            clusters: 클러스터 리스트
            query_nouns: 검색 질문의 명사 리스트
            has_recency_keyword: 최신/최근 키워드 포함 여부
            top_0_sim: 1등 클러스터 유사도
            top_1_sim: 2등 클러스터 유사도
            last_sim: 마지막 클러스터 유사도

        Returns:
            List[Tuple]: 선택된 클러스터의 문서 리스트
        """
        # 최근 키워드가 있거나, 모든 문서 유사도가 비슷한 경우 (<=0.3)
        if has_recency_keyword or (top_0_sim - last_sim <= 0.3):
            # 모든 문서가 비슷하면 날짜순 정렬
            if top_0_sim - last_sim <= 0.3:
                sorted_clusters = sorted(clusters, key=lambda c: c[0][2], reverse=True)
                return sorted_clusters[0]
            # 최근 키워드 O, 상위 2개만 비슷한 경우
            else:
                if top_0_sim - top_1_sim <= 0.3:
                    # 날짜 비교하여 더 최근 클러스터 선택
                    date1 = self.date_parser(clusters[0][0][2])
                    date2 = self.date_parser(clusters[1][0][2])
                    result_date = (date1 - date2).days

                    result_docs = clusters[1] if result_date < 0 else clusters[0]
                    return sorted(result_docs, key=lambda doc: doc[2], reverse=True)
                else:
                    # 유사도순 정렬
                    sorted_clusters = sorted(clusters, key=lambda c: c[0][0], reverse=True)
                    return sorted_clusters[0]
        else:
            # 최근 키워드 X, 두 클러스터 비교
            if top_0_sim - top_1_sim <= 0.1:
                # 차이가 거의 없으면 날짜 비교
                date1 = self.date_parser(clusters[0][0][2])
                date2 = self.date_parser(clusters[1][0][2])
                result_date = (date1 - date2).days

                result_docs = clusters[1] if result_date < 0 else clusters[0]
                return sorted(result_docs, key=lambda doc: doc[2], reverse=True)
            else:
                # 약간의 차이는 있으므로 유사도순
                result_docs = clusters[0]
                return sorted(result_docs, key=lambda doc: doc[0], reverse=True)

    def _handle_clear_query(self,
                             clusters: List[List[Tuple]],
                             query_nouns: List[str],
                             has_recency_keyword: bool) -> List[Tuple]:
        """
        명확한 질문 처리 (상위 클러스터 간 유사도 차이가 명확할 때)

        Args:
            clusters: 클러스터 리스트
            query_nouns: 검색 질문의 명사 리스트
            has_recency_keyword: 최신/최근 키워드 포함 여부

        Returns:
            List[Tuple]: 선택된 클러스터의 문서 리스트
        """
        number_pattern = r"\d"
        period_words = ["여름", "겨울"]

        has_number = any(re.search(number_pattern, word) for word in query_nouns)
        has_period_word = any(key in word for word in query_nouns for key in period_words)

        # 최근 키워드 O, 또는 숫자/기간어가 없는 경우
        if has_recency_keyword or (not has_number or not has_period_word):
            # 숫자나 기간어가 있으면 유사도 우선
            if has_number or has_period_word:
                result_docs = clusters[0]

                # "N차" 형태가 여러 개 있으면 날짜순
                nth_count = sum(1 for doc in result_docs if re.search(r'\d+차', doc[1]))
                if nth_count > 1:
                    return sorted(result_docs, key=lambda doc: doc[2], reverse=True)
                else:
                    return sorted(result_docs, key=lambda doc: doc[0], reverse=True)
            else:
                # 그냥 최신순
                result_docs = clusters[0]
                return sorted(result_docs, key=lambda doc: doc[2], reverse=True)
        else:
            # 유사도순 정렬
            result_docs = clusters[0]
            return sorted(result_docs, key=lambda doc: doc[0], reverse=True)

    def _organize_documents(self,
                             sorted_cluster: List[Tuple],
                             titles: List[str],
                             dates: List[str],
                             texts: List[str],
                             urls: List[str]) -> Tuple[List[Tuple], int]:
        """
        중복 제목 문서 추가 및 유사도 부스팅

        Args:
            sorted_cluster: 선택된 클러스터 문서 리스트
            titles: 전체 제목 리스트
            dates: 전체 날짜 리스트
            texts: 전체 본문 리스트
            urls: 전체 URL 리스트

        Returns:
            Tuple[List[Tuple], int]: (재구성된 문서 리스트, 중복 문서 개수)
        """
        # 첫 번째 문서를 기준으로 설정
        top_doc = sorted_cluster[0]
        top_title = top_doc[1]

        new_sorted_cluster = []
        count = 0

        # titles에서 top_title과 같은 제목을 가진 모든 문서 추가
        for i, title in enumerate(titles):
            if title == top_title:
                count += 1
                new_doc = (top_doc[0], titles[i], dates[i], texts[i], urls[i])
                new_sorted_cluster.append(new_doc)

        # 중복 문서에 유사도 부스팅 적용 (마지막 문서 제외)
        for i in range(count - 1):
            boosted_doc = list(new_sorted_cluster[i])
            boosted_doc[0] = boosted_doc[0] + 0.2 * count
            new_sorted_cluster[i] = tuple(boosted_doc)

        # sorted_cluster에서 top_title이 아닌 문서들 추가
        for doc in sorted_cluster:
            if doc[1] != top_title:
                new_sorted_cluster.append(doc)

        return new_sorted_cluster, count
