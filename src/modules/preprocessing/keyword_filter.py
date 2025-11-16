"""
Keyword Filter
키워드 기반 문서 유사도 필터링 클래스
"""

import re
import logging
import sys
from pathlib import Path
from typing import List, Tuple

# utils 모듈 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import korean_to_iso8601

logger = logging.getLogger(__name__)


class KeywordFilter:
    """
    키워드 기반으로 문서 유사도를 필터링하는 클래스

    특정 키워드 패턴에 따라 유사도 점수를 조정합니다.
    """

    def __init__(self):
        """KeywordFilter 초기화"""
        # 특정 URL에 대한 wr_id 목록 (중요 문서)
        self.target_numbers = [27510, 27047, 27614, 27246, 25900, 27553, 25896, 28183, 27807, 25817, 25804]
        logger.info("✅ KeywordFilter 초기화 완료")

    def filter(self,
               documents: List[Tuple],
               query_nouns: List[str],
               user_question: str) -> List[Tuple]:
        """
        키워드 기반 문서 필터링

        Args:
            documents: 문서 리스트 [(score, title, date, text, url), ...]
            query_nouns: 검색 질문의 명사 리스트
            user_question: 원본 질문

        Returns:
            List[Tuple]: 필터링된 문서 리스트 (유사도 조정됨)
        """
        filtered_docs = []

        for idx, doc in enumerate(documents):
            score, title, date, text, url = doc

            # 현장실습 관련 필터
            score = self._filter_field_practice(score, title, query_nouns)

            # 특정 URL 부스팅
            score = self._boost_important_urls(score, url, query_nouns, text)

            # 기타 키워드 필터링
            score = self._apply_keyword_filters(
                score, title, date, text, url, query_nouns, user_question
            )

            filtered_docs.append((score, title, date, text, url))

        return filtered_docs

    def _filter_field_practice(self,
                                 score: float,
                                 title: str,
                                 query_nouns: List[str]) -> float:
        """현장실습 관련 필터링"""
        if not any(keyword in query_nouns for keyword in ["현장", "실습", "현장실습"]) and \
           any(keyword in title for keyword in ["현장실습", "대체", "기준"]):
            score -= 1.0
        return score

    def _boost_important_urls(self,
                               score: float,
                               url: str,
                               query_nouns: List[str],
                               text: str) -> float:
        """특정 URL 유사도 부스팅"""
        match = re.search(r"wr_id=(\d+)", url)
        if match:
            extracted_number = int(match.group(1))
            if extracted_number in self.target_numbers:
                # 에이빅 관련
                if any(keyword in query_nouns for keyword in ['에이빅', 'ABEEK']) and \
                   any(keyword in text for keyword in ['에이빅', 'ABEEK']):
                    if extracted_number == 27047:
                        score += 0.3
                    else:
                        score += 1.5
                else:
                    if '폐강' not in query_nouns:
                        score += 0.8
                    if '계절' in query_nouns:
                        score -= 2.0
                    if '전과' in query_nouns:
                        score -= 1.0
                    if '유예' in query_nouns and '학사' in query_nouns and extracted_number == 28183:
                        score += 0.45
        return score

    def _apply_keyword_filters(self,
                                 score: float,
                                 title: str,
                                 date: str,
                                 text: str,
                                 url: str,
                                 query_nouns: List[str],
                                 user_question: str) -> float:
        """다양한 키워드 필터 적용"""
        # 기념 관련
        if '기념' in query_nouns and '기념' in title and \
           url == "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_4&wr_id=354":
            score += 0.5

        # 스탬프
        if '스탬프' not in query_nouns and '스탬프' in title:
            score -= 0.5

        # 기말/중간고사
        if '기말' in query_nouns and '기말' in title:
            score += 1.0
        if '중간' in query_nouns and '중간' in title:
            score += 1.0

        # 졸업 포트폴리오
        if '졸업' in query_nouns and '졸업' not in title and \
           '포트폴리오' in query_nouns and '포트폴리오' in title:
            score -= 1.0
        if '졸업' in query_nouns and '포트폴리오' in title and \
           '졸업' in title and '포트폴리오' in query_nouns:
            score += 1.0

        # TUTOR
        if 'TUTOR' in title and 'TUTOR' not in query_nouns:
            score -= 1.0

        # 계절학기 관련
        class_word = ['신청', '취소', '변경']
        for keyword in class_word:
            if keyword in query_nouns and '계절' in query_nouns and keyword in title:
                score += 1.3
                break

        # 자퇴/전과
        if '자퇴' in title and '자퇴' in query_nouns:
            score += 1.0
        if '전과' in title and '전과' in query_nouns:
            score += 1.0

        # 조기
        if '조기' in title and '조기' not in query_nouns:
            score -= 0.5

        # 수강 관련
        score = self._filter_course_registration(score, title, url, query_nouns)

        # 설문
        if '설문' not in query_nouns and '설문' in title:
            score -= 0.5

        # 군 관련
        score = self._filter_military(score, title, query_nouns)

        # 복학/휴학
        if '복학' in query_nouns and '복학' in title:
            score += 1.0
        if '휴학' in query_nouns and '휴학' in title:
            score += 1.0

        # 카카오
        if '카카오' in title and '카카오' in query_nouns:
            score += 0.6

        # 설계
        if '설계' in title:
            score -= 0.4

        # 오픈소스
        if '오픈소스' in query_nouns and '오픈소스' in title:
            score += 0.5

        # SDG
        if 'SDG' in query_nouns and 'SDG' in title:
            score += 2.9

        # 인턴십
        if any(keyword in query_nouns for keyword in ['인턴', '인턴십']) and \
           any(keyword in query_nouns for keyword in ['인도', '베트남']):
            score += 1.0

        # 수요조사
        if any(keyword in title for keyword in ['수요', '조사']) and \
           not any(keyword in query_nouns for keyword in ['수요', '조사']):
            score -= 0.6

        # 여름/겨울 학기
        score = self._filter_season(score, title, query_nouns)

        # 1학기/2학기
        score = self._filter_semester(score, title, query_nouns)

        # 종합설계프로젝트
        if any(keyword in text for keyword in ['종프', '종합설계프로젝트']) and \
           any(keyword in user_question for keyword in ['종프', '종합설계프로젝트']):
            score += 0.7
            if '설명회' in query_nouns and '설명회' in title:
                score += 0.7
            else:
                score -= 1.0

        # 부전공/복수전공
        score = self._filter_major(score, title, url, query_nouns, user_question)

        # 대학원
        score = self._filter_graduate_school(score, title, text, query_nouns)

        # 직원/교수
        score = self._filter_staff_professor(score, title, date, text, url, query_nouns, user_question)

        # 수강 키워드 매칭
        score = self._filter_course_keyword_match(score, title, url, query_nouns)

        return score

    def _filter_course_registration(self,
                                      score: float,
                                      title: str,
                                      url: str,
                                      query_nouns: List[str]) -> float:
        """수강 관련 필터링"""
        if '수강' in title:
            if url == "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28180":
                score -= 3.0
            if any(keyword in query_nouns for keyword in ['폐강', '재이수']):
                if '폐강' in query_nouns and any(keyword in title for keyword in ['신청', '정정']):
                    score += 2.0
                else:
                    score += 0.8
                if '재이수' in query_nouns:
                    if '꾸러미' in title:
                        score += 1.0
                    elif '신청' in title:
                        score += 2.0
                    else:
                        score += 1.5
        return score

    def _filter_military(self,
                          score: float,
                          title: str,
                          query_nouns: List[str]) -> float:
        """군 관련 필터링"""
        if any(keyword in query_nouns for keyword in ['군', '군대']) and '군' in title:
            if '학점' in title and '학점' not in query_nouns:
                score -= 1.0
            else:
                score += 1.5
        if '군' not in query_nouns and '군' in title:
            score -= 1.0
        return score

    def _filter_season(self,
                        score: float,
                        title: str,
                        query_nouns: List[str]) -> float:
        """계절학기 필터링"""
        if '여름' in query_nouns and any(keyword in title for keyword in ['겨울', "동계"]):
            score -= 1.0
        if '겨울' in query_nouns and any(keyword in title for keyword in ['하계', "여름"]):
            score -= 1.0
        if '여름' in query_nouns and any(keyword in title for keyword in ['하계', "여름"]):
            score += 0.7
            if '벤처아카데미' in query_nouns:
                score += 2.0
        if '겨울' in query_nouns and any(keyword in title for keyword in ['겨울', "동계"]):
            score += 0.7
            if '벤처아카데미' in query_nouns:
                score += 2.0
        return score

    def _filter_semester(self,
                          score: float,
                          title: str,
                          query_nouns: List[str]) -> float:
        """학기 필터링"""
        if '1학기' in query_nouns and '1학기' in title:
            score += 1.0
        if '2학기' in query_nouns and '2학기' in title:
            score += 1.0
        if '1학기' in query_nouns and '2학기' in title:
            score -= 1.0
        if '2학기' in query_nouns and '1학기' in title:
            score -= 1.0
        return score

    def _filter_major(self,
                       score: float,
                       title: str,
                       url: str,
                       query_nouns: List[str],
                       user_question: str) -> float:
        """전공 관련 필터링"""
        # 부전공
        if '부전공' in query_nouns and '부전공' in title:
            score += 1.0

        # 복수전공
        if any(keyword in query_nouns for keyword in ['복전', '복수', '복수전공']) and \
           any(keyword in title for keyword in ['복수']):
            score += 0.7
        if not any(keyword in query_nouns for keyword in ['복전', '복수', '복수전공']) and \
           any(keyword in title for keyword in ['복수']):
            score -= 1.4

        # 심컴
        if any(keyword in title for keyword in ['심컴', '심화컴퓨터전공', '심화 컴퓨터공학', '심화컴퓨터공학']):
            if any(keyword in user_question for keyword in ['심컴', '심화컴퓨터전공']):
                score += 0.7
            else:
                if "컴퓨터비전" not in query_nouns:
                    score -= 0.7
        # 글솝
        elif any(keyword in title for keyword in ['글로벌소프트웨어전공', '글로벌SW전공', '글로벌소프트웨어융합전공', '글솝', '글솦']):
            if any(keyword in user_question for keyword in ['글로벌소프트웨어융합전공', '글로벌소프트웨어전공', '글로벌SW전공', '글솝', '글솦']):
                score += 0.7
            else:
                score -= 0.8
        # 인컴
        elif any(keyword in title for keyword in ['인컴', '인공지능컴퓨팅']):
            if any(keyword in user_question for keyword in ['인컴', '인공지능컴퓨팅']):
                score += 0.7
                if url == "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=27553":
                    score += 1.0
            else:
                score -= 0.8

        # 벤처아카데미
        if any(keyword in user_question for keyword in ['벤처', '아카데미']) and \
           any(keyword in title for keyword in ['벤처아카데미', '벤처스타트업아카데미', '벤처스타트업']):
            if any(keyword in user_question for keyword in ['스타트업']) and \
               any(keyword in title for keyword in ['스타트업']):
                score += 0.5
            elif not any(keyword in user_question for keyword in ['스타트업']) and \
                 any(keyword in title for keyword in ['벤처스타트업아카데미', '벤처스타트업아카데미', '스타트업', '스타트', '벤처스타트업']):
                score -= 2.5
            else:
                score += 2.0

        return score

    def _filter_graduate_school(self,
                                  score: float,
                                  title: str,
                                  text: str,
                                  query_nouns: List[str]) -> float:
        """대학원 관련 필터링"""
        # 계약학과/대학원/타대학원 키워드 패널티
        if any(keyword in text for keyword in ['계약학과', '대학원', '타대학원']) and \
           not any(keyword in query_nouns for keyword in ['계약학과', '대학원', '타대학원']):
            score -= 0.8

        # 대학원 키워드
        keywords = ['대학원', '대학원생']
        if any(keyword in query_nouns for keyword in keywords) and \
           any(keyword in title for keyword in keywords):
            score += 2.0
        elif not any(keyword in query_nouns for keyword in keywords) and \
             any(keyword in title for keyword in keywords):
            if '학부생' in query_nouns and '연구' in query_nouns:
                score += 1.0
            else:
                score -= 2.0

        if any(keyword in query_nouns for keyword in ['대학원', '대학원생']) and \
           any(keyword in title for keyword in ['대학원', '대학원생']):
            score += 2.0

        return score

    def _filter_staff_professor(self,
                                  score: float,
                                  title: str,
                                  date: str,
                                  text: str,
                                  url: str,
                                  query_nouns: List[str],
                                  user_question: str) -> float:
        """직원/교수 관련 필터링"""
        # 직원 담당 업무
        if any(keyword in user_question for keyword in ['담당', '업무', '일', '근무', '관련']) and \
           any(keyword in query_nouns for keyword in ['직원', '선생', '선생님']):
            if url != "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_5&lang=kor":
                score -= 3.0
            else:
                score += 1.0
                # IT와 E 모두 처리
                for keyword in ['IT', 'E']:
                    if keyword in query_nouns:
                        valid_numbers = ['4', '5'] if keyword == 'IT' else ['9']
                        building_number = [num for num in query_nouns if num in valid_numbers]
                        if building_number:
                            combined_building = f"{keyword}{building_number[0]}"
                            if combined_building in text:
                                score += 0.5
                            else:
                                score -= 0.8
                if '대학원' in query_nouns:
                    if not any(keyword in query_nouns for keyword in ['지원', '계약']) and \
                       any(keyword in text for keyword in ['지원', '계약']):
                        score -= 0.8
                    else:
                        score += 0.5

        # 교수 관련 (기준 날짜로 교수 정보 판별)
        # ISO 8601 형식: "2024-01-01T00:00:00+09:00"
        professor_baseline_date = korean_to_iso8601("작성일24-01-01 00:00")
        if (any(keyword in query_nouns for keyword in ['담당', '업무', '일', '근무']) or
            any(keyword in query_nouns for keyword in ['직원', '교수', '선생', '선생님'])) and \
           date == professor_baseline_date:
            if any(keys in query_nouns for keys in ['교수']):
                check = 0
                compare_url = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_5&lang=kor"
                if compare_url == url:
                    check = 1
                if check == 0:
                    score += 0.5
                else:
                    score -= 0.9
            else:
                score += 4.0

        if not any(keys in query_nouns for keys in ['교수']) and \
           any(keys in title for keys in ['담당교수', '교수']):
            score -= 0.7

        return score

    def _filter_course_keyword_match(self,
                                       score: float,
                                       title: str,
                                       url: str,
                                       query_nouns: List[str]) -> float:
        """수강 키워드 매칭 필터링"""
        match = re.search(r"(?<![\[\(])\b수강\w*\b(?![\]\)])", title)
        if match:
            full_keyword = match.group(0)
            if full_keyword not in query_nouns:
                match = re.search(r"wr_id=(\d+)", url)
                if match:
                    extracted_number = int(match.group(1))
                    if extracted_number in self.target_numbers:
                        score -= 0.2
                    else:
                        score -= 0.7
            else:
                score += 0.8
        return score
