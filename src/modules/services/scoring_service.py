"""
Scoring Service

문서 점수 조정 로직을 담당하는 서비스
날짜 기반 가중치, 유사도 조정 등
"""
import re
import logging
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)


class ScoringService:
    """
    문서 점수 조정 서비스

    Responsibilities:
    - 날짜 기반 가중치 계산 (최신성 반영)
    - 유사도 점수 조정 (키워드 매칭, 숫자 포함 등)
    """

    def __init__(self, date_parser_fn, current_time_fn):
        """
        Args:
            date_parser_fn: 날짜 파싱 함수 (utils.date_utils.parse_date_change_korea_time)
            current_time_fn: 현재 시간 함수 (utils.date_utils.get_current_kst)
        """
        self.parse_date = date_parser_fn
        self.get_current_time = current_time_fn

    def calculate_weight_by_days_difference(
        self,
        post_date: datetime,
        current_date: datetime,
        query_nouns: List[str]
    ) -> float:
        """
        날짜 차이에 따른 가중치 계산

        Args:
            post_date: 게시글 작성일
            current_date: 현재 시간
            query_nouns: 쿼리 명사 리스트

        Returns:
            float: 가중치 (0.88 ~ 1.355+)

        Logic:
            - 최신 문서일수록 높은 가중치
            - 특정 키워드(졸업, 장학 등)에 따라 추가 가중치
            - 기준 날짜(24-01-01) 이전 문서는 고정 가중치
        """
        # 날짜 차이 계산 (일 단위)
        days_diff = (current_date - post_date).days

        # 기준 날짜 (24-01-01 00:00) 설정
        baseline_date_str = "24-01-01 00:00"
        baseline_date = self.parse_date(baseline_date_str)
        graduate_weight = 1.0 if any(keyword in query_nouns for keyword in ['졸업', '인터뷰']) else 0
        scholar_weight = 1.0 if '장학' in query_nouns else 0

        # 작성일이 기준 날짜 이전이면 가중치를 1.35로 고정
        if post_date <= baseline_date:
            return 1.35 + graduate_weight / 5

        # '최근', '최신' 등의 키워드가 있는 경우, 최근 가중치를 추가
        add_recent_weight = 1.5 if any(keyword in query_nouns for keyword in ['최근', '최신', '지금', '현재']) else 0

        # **10일 단위 구분**: 최근 문서에 대한 세밀한 가중치 부여
        if days_diff <= 6:
            return 1.355 + add_recent_weight + graduate_weight + scholar_weight
        elif days_diff <= 12:
            return 1.330 + add_recent_weight / 3.0 + graduate_weight / 1.2 + scholar_weight / 1.5
        elif days_diff <= 18:
            return 1.321 + add_recent_weight / 5.0 + graduate_weight / 1.3 + scholar_weight / 2.0
        elif days_diff <= 24:
            return 1.310 + add_recent_weight / 7.0 + graduate_weight / 1.4 + scholar_weight / 2.5
        elif days_diff <= 30:
            return 1.290 + add_recent_weight / 9.0 + graduate_weight / 1.5 + scholar_weight / 3.0
        elif days_diff <= 36:
            return 1.270 + graduate_weight / 1.6 + scholar_weight / 3.5
        elif days_diff <= 45:
            return 1.250 + graduate_weight / 1.7 + scholar_weight / 4.0
        elif days_diff <= 60:
            return 1.230 + graduate_weight / 1.8 + scholar_weight / 4.5
        elif days_diff <= 90:
            return 1.210 + graduate_weight / 2.0 + scholar_weight / 5.0

        # **월 단위 구분**: 2개월 이후는 월 단위로 단순화
        month_diff = (days_diff - 90) // 30
        month_weight_map = {
            0: 1.19,
            1: 1.17 - add_recent_weight / 6 - scholar_weight / 10,
            2: 1.15 - add_recent_weight / 5 - scholar_weight / 9,
            3: 1.13 - add_recent_weight / 4 - scholar_weight / 7,
            4: 1.11 - add_recent_weight / 3 - scholar_weight / 5,
        }

        # 기본 가중치 반환 (6개월 이후)
        return month_weight_map.get(month_diff, 0.88 - add_recent_weight / 2 - scholar_weight / 5)

    def adjust_date_similarity(
        self,
        similarity: float,
        date_str: str,
        query_nouns: List[str]
    ) -> float:
        """
        날짜 기반 유사도 조정

        Args:
            similarity: 원본 유사도
            date_str: 작성일 (문자열)
            query_nouns: 쿼리 명사 리스트

        Returns:
            float: 조정된 유사도
        """
        # 현재 한국 시간
        current_time = self.get_current_time()
        # 작성일 파싱
        post_date = self.parse_date(date_str)
        # 가중치 계산
        weight = self.calculate_weight_by_days_difference(post_date, current_time, query_nouns)
        # 조정된 유사도 반환
        return similarity * weight

    def adjust_similarity_scores(
        self,
        query_noun: List[str],
        title: List[str],
        texts: List[str],
        similarities: List[float]
    ) -> List[float]:
        """
        사용자 질문에서 추출한 명사와 각 문서 제목에 대한 유사도를 조정

        Args:
            query_noun: 쿼리 명사 리스트
            title: 문서 제목 리스트
            texts: 문서 본문 리스트
            similarities: 유사도 리스트

        Returns:
            List[float]: 조정된 유사도 리스트

        Logic:
            - 제목 매칭 시 가중치 추가
            - 숫자 포함 명사 매칭 시 추가 가중치
            - "No content" 문서는 제목 의존도가 높으므로 부스팅
            - 대학원 키워드 특별 처리
        """
        query_noun_set = set(query_noun)
        title_tokens = [set(titl.split()) for titl in title]

        for idx, titl_tokens in enumerate(title_tokens):
            matching_noun = query_noun_set.intersection(titl_tokens)

            if texts[idx] == "No content":
                similarities[idx] *= 1.5
                if "국가장학금" in query_noun_set and "국가장학금" in titl_tokens:
                    similarities[idx] *= 5.0

            for noun in matching_noun:
                len_adjustment = len(noun) * 0.21
                similarities[idx] += len_adjustment
                if re.search(r'\d', noun):  # 숫자 포함 여부
                    similarities[idx] += len(noun) * (0.22 if noun in titl_tokens else 0.19)

            if query_noun_set.intersection({'대학원', '대학원생'}) and titl_tokens.intersection({'대학원', '대학원생'}):
                similarities[idx] += 2.0
            if not query_noun_set.intersection({'대학원', '대학원생'}) and '대학원' in titl_tokens:
                similarities[idx] -= 2.0

        return similarities
