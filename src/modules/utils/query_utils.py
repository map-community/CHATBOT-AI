"""
Query 및 임베딩 관련 유틸리티 함수
"""
from datetime import datetime
import pytz
from langchain_upstage import UpstageEmbeddings


def get_korean_time():
    """현재 한국 시간(KST) 반환"""
    return datetime.now(pytz.timezone('Asia/Seoul'))


def transformed_query(content):
    """
    질문을 명사 키워드 리스트로 변환
    
    Args:
        content: 사용자 질문 (원문)
    
    Returns:
        List[str]: 추출된 명사 키워드 리스트
    """
    from modules.storage_manager import StorageManager
    storage = StorageManager()
    return storage.query_transformer.transform(content)


def get_embeddings():
    """
    Upstage Embeddings 객체 반환 (Lazy initialization)
    
    Returns:
        UpstageEmbeddings: Upstage 임베딩 모델 인스턴스
    """
    from modules.storage_manager import StorageManager
    storage = StorageManager()
    return UpstageEmbeddings(
        api_key=storage.upstage_api_key,
        model="solar-embedding-1-large-query"  # 질문 임베딩용 모델
    )
