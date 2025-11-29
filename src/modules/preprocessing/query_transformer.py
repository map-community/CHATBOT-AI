"""
Query Transformer
사용자 질문을 명사 키워드로 변환하는 클래스
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)

# Mecab import 시도
try:
    from konlpy.tag import Mecab
    MECAB_AVAILABLE = True
except Exception as e:
    logger.warning(f"⚠️  Mecab을 불러올 수 없습니다: {e}")
    MECAB_AVAILABLE = False
    Mecab = None


class QueryTransformer:
    """
    사용자 질문을 명사 키워드 리스트로 변환하는 클래스

    다양한 패턴 매칭과 형태소 분석을 통해 핵심 키워드를 추출합니다.
    """

    # 불용어(stopwords) 정의: 검색에 불필요한 일반 단어 제거
    STOPWORDS = {
        # 메타 표현 (검색 의도가 아님)
        '포함', '전부', '모두', '다', '말하다', '알려주다', '설명하다', '보여주다',
        '있다', '없다', '하다', '되다', '이다', '아니다',

        # 일반 명사 (너무 흔함)
        '문서', '게시글', '글', '내용', '정보', '자료', '데이터',
        '것', '거', '수', '때', '곳', '점', '건', '개',

        # 질문 표현
        '질문', '답변', '대답',

        # 시간 표현 (별도 파싱됨)
        '오늘', '어제', '내일', '요즘', '최근',

        # 조사/어미 잔류물
        '이', '가', '을', '를', '은', '는', '에', '에서', '으로', '부터', '까지'
    }

    def __init__(self, use_mecab: bool = True):
        """
        QueryTransformer 초기화

        Args:
            use_mecab: Mecab 형태소 분석기 사용 여부 (기본값: True)
        """
        self.use_mecab = use_mecab and MECAB_AVAILABLE
        self.mecab = Mecab() if self.use_mecab else None

        if self.use_mecab:
            logger.info("✅ QueryTransformer 초기화 완료 (Mecab 사용)")
        else:
            logger.info("✅ QueryTransformer 초기화 완료 (Mecab 미사용)")

    def transform(self, content: str) -> List[str]:
        """
        질문을 명사 키워드 리스트로 변환

        Args:
            content: 사용자 질문 (원문)

        Returns:
            List[str]: 추출된 명사 키워드 리스트
        """
        query_nouns = []

        # 1. 숫자와 특정 단어가 결합된 패턴 추출 (예: '2024학년도', '1월' 등)
        pattern = r'\d+(?:학년도|년|학년|월|일|학기|시|분|초|기|개|차)?'
        number_matches = re.findall(pattern, content)
        query_nouns += number_matches

        # 추출된 단어를 content에서 제거
        for match in number_matches:
            content = content.replace(match, '')

        # 2. 영어 단어 추출 (대문자로 변환)
        english_pattern = r'[a-zA-Z]+'
        english_matches = re.findall(english_pattern, content)
        english_matches_upper = [match.upper() for match in english_matches]
        query_nouns += english_matches_upper

        # content에서 영어 단어 제거
        for match in english_matches:
            content = re.sub(rf'\b{re.escape(match)}\b', '', content)

        # 3. 특수 키워드 처리 (도메인 지식 기반)
        query_nouns.extend(self._extract_special_keywords(content))

        # 4. Mecab 형태소 분석기를 이용한 추가 명사 추출 (불용어 제거)
        if self.use_mecab and self.mecab:
            additional_nouns = [
                noun for noun in self.mecab.nouns(content)
                if len(noun) > 1 and noun not in self.STOPWORDS  # ✅ 불용어 필터링 추가
            ]
            query_nouns += additional_nouns
        else:
            # Mecab 없이 간단한 토큰화 (불용어 제거)
            simple_tokens = content.split()
            additional_nouns = [
                token for token in simple_tokens
                if len(token) > 1 and token not in self.STOPWORDS  # ✅ 불용어 필터링 추가
            ]
            query_nouns += additional_nouns

        # 5. 후처리: 특정 조건에서 추가 키워드 삽입
        query_nouns = self._post_process_keywords(query_nouns, content)

        # 6. 중복 제거
        query_nouns = list(set(query_nouns))

        return query_nouns

    def _extract_special_keywords(self, content: str) -> List[str]:
        """
        도메인 특화 키워드 추출

        Args:
            content: 처리할 텍스트

        Returns:
            List[str]: 추출된 특수 키워드 리스트
        """
        keywords = []

        # 시간표 제거
        if '시간표' in content:
            content = content.replace('시간표', '')

        # EXIT -> 출구
        if 'EXIT' in content.upper():
            keywords.append('출구')

        # 벤처아카데미
        if any(keyword in content for keyword in ['벤처아카데미', '벤처아카데미']):
            keywords.append("벤처아카데미")

        # 군 관련
        if '군' in content:
            keywords.append('군')

        # 인컴 -> 인공지능컴퓨팅
        if '인컴' in content:
            keywords.append('인공지능컴퓨팅')
        if '인공' in content and '지능' in content and '컴퓨팅' in content:
            keywords.append('인공지능컴퓨팅')

        # 학부생
        if '학부생' in content:
            keywords.append('학부생')

        # 공대 -> E
        if '공대' in content:
            keywords.append('E')

        # 설명회
        if '설명회' in content:
            keywords.append('설명회')

        # 컴학 -> 컴퓨터학부
        if '컴학' in content:
            keywords.append('컴퓨터학부')

        # 컴퓨터비전
        if '컴퓨터' in content and '비전' in content:
            keywords.append('컴퓨터비전')

        # 컴퓨터학부
        if '컴퓨터' in content and '학부' in content:
            keywords.append('컴퓨터학부')

        # 차
        if '차' in content:
            keywords.append('차')

        # 국가장학금
        if '국가 장학금' in content or '국가장학금' in content:
            keywords.append('국가장학금')

        # 종프 -> 종합설계프로젝트
        if '종프' in content or '종합설계프로젝트' in content:
            keywords.append('종합설계프로젝트')

        # 대회 -> 경진대회
        if '대회' in content:
            keywords.append('경진대회')

        # 튜터 -> TUTOR
        if '튜터' in content:
            keywords.append('TUTOR')

        # 탑싯 -> TOPCIT
        if '탑싯' in content:
            keywords.append('TOPCIT')

        # 시험
        if '시험' in content:
            keywords.append('시험')

        # 하계/동계
        if '하계' in content:
            keywords.extend(['여름', '하계'])
        if '동계' in content:
            keywords.extend(['겨울', '동계'])
        if '겨울' in content:
            keywords.extend(['겨울', '동계'])
        if '여름' in content:
            keywords.extend(['여름', '하계'])

        # 성인지/첨성인
        if '성인지' in content:
            keywords.append('성인지')
        if '첨성인' in content:
            keywords.append('첨성인')

        # 글솦 -> 글솝
        if '글솦' in content:
            keywords.append('글솝')

        # 수꾸 -> 수강꾸러미
        if '수꾸' in content:
            keywords.append('수강꾸러미')

        # 장학금/장학생
        if '장학금' in content:
            keywords.extend(['장학생', '장학'])
        if '장학생' in content:
            keywords.extend(['장학금', '장학'])

        # 에이빅 -> ABEEK
        if '에이빅' in content:
            keywords.extend(['에이빅', 'ABEEK'])

        # 선이수/선후수
        if '선이수' in content or '선후수' in content:
            keywords.append('선이수')

        # 학자금
        if '학자금' in content:
            keywords.append('학자금')

        # 오픈소스
        if any(keyword in content for keyword in ['오픈 소스', '오픈소스']):
            keywords.append('오픈소스')

        # 군휴학
        if any(keyword in content for keyword in ['군', '군대']) and '휴학' in content:
            keywords.extend(['군', '군휴학', '군입대'])

        # 카테캠 -> 카카오 테크 캠퍼스
        if '카테캠' in content:
            keywords.extend(['카카오', '테크', '캠퍼스'])

        # 재이수
        re_keyword = ['재이수', '재 이수', '재 수강', '재수강']
        if any(key in content for key in re_keyword):
            keywords.append('재이수')

        # 과목/강의/강좌
        if '과목' in content:
            keywords.append('강의')
        if '강의' in content:
            keywords.extend(['과목', '강좌'])
        if '강좌' in content:
            keywords.append('강좌')

        # 외국어
        if '외국어' in content:
            keywords.append('외국어')

        # 부전공
        if '부' in content and '전공' in content:
            keywords.append('부전공')

        # 계절학기
        if '계절' in content and '학기' in content:
            keywords.append('수업')

        # 세미나/특강/강연
        related_keywords = ['세미나', '특강', '강연']
        if any(keyword in content for keyword in related_keywords):
            keywords.extend(related_keywords)

        # 공지사항
        notice_keywords = ['공지', '사항', '공지사항']
        if any(keyword in content for keyword in notice_keywords):
            keywords.append('공지사항')

        # 신입사원
        employee_keywords = ['사원', '신입사원']
        if any(keyword in content for keyword in employee_keywords):
            keywords.append('신입')

        return keywords

    def _post_process_keywords(self, query_nouns: List[str], content: str) -> List[str]:
        """
        키워드 후처리 (조건부 추가/삭제)

        Args:
            query_nouns: 현재 키워드 리스트
            content: 원본 텍스트

        Returns:
            List[str]: 후처리된 키워드 리스트
        """
        # 인도가 없고 인턴십이 있으면 베트남 추가
        if '인도' not in query_nouns and '인턴십' in query_nouns:
            query_nouns.append('베트남')

        # 수강 관련 키워드 결합
        if '수강' in content:
            related_keywords = ['변경', '신청', '정정', '취소', '꾸러미']
            for keyword in related_keywords:
                if keyword in content:
                    combined_keyword = '수강' + keyword
                    query_nouns.append(combined_keyword)

                    # '수강' 단독 제거
                    if '수강' in query_nouns:
                        query_nouns.remove('수강')

                    # 관련 키워드 제거
                    for kw in related_keywords:
                        if kw in query_nouns:
                            query_nouns.remove(kw)
                    break

        # 꾸러미 + 수강신청
        if '꾸러미' in content and '수강신청' in query_nouns:
            query_nouns.append('신청')

        return query_nouns
