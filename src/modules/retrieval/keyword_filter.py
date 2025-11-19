
import logging

logger = logging.getLogger(__name__)

class KeywordFilter:
    """
    키워드 기반 문서 필터링 클래스
    """

    def __init__(self):
        pass

    def filter(self, docs, query_noun, user_question):
        """
        문서 리스트를 필터링합니다.
        
        Args:
            docs: 문서 리스트
            query_noun: 명사 키워드 리스트
            user_question: 사용자 질문

        Returns:
            List: 필터링된 문서 리스트
        """
        # 현재는 별도의 필터링 로직 없이 통과시킵니다.
        # 필요 시 여기에 필터링 로직을 추가하세요.
        return docs
