"""
크롤링 설정 파일
모든 하드코딩된 값들을 중앙 관리
"""
import os
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()


class CrawlerConfig:
    """크롤러 설정"""

    # API 키
    PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
    PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'info')
    UPSTAGE_API_KEY = os.getenv('UPSTAGE_API_KEY')

    # MongoDB 설정
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://mongodb:27017/')
    MONGODB_DATABASE = 'knu_chatbot'
    MONGODB_NOTICE_COLLECTION = 'notice_collection'
    MONGODB_STATE_COLLECTION = 'crawl_state'  # 크롤링 상태 저장용

    # 텍스트 분할 설정
    CHUNK_SIZE = 850
    CHUNK_OVERLAP = 100

    # 임베딩 설정
    EMBEDDING_MODEL = 'solar-embedding-1-large-passage'
    EMBEDDING_BATCH_SIZE = 50  # 진행상황 출력 주기

    # 크롤링 URL 설정
    BASE_URLS = {
        'notice': 'https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1',
        'job': 'https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_3_b',
        'seminar': 'https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_4',
        'professor': 'https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_1&lang=kor',
        'guest_professor': 'https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_2&lang=kor',
        'staff': 'https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_5&lang=kor',
    }

    # 크롤링 범위 설정 (하한선 - 더 이상 크롤링하지 않을 최소 ID)
    MIN_IDS = {
        'notice': 27726,
        'job': 1149,
        'seminar': 246,
    }

    # 추가 크롤링할 특정 공지사항 ID
    ADDITIONAL_NOTICE_IDS = [
        27510, 27047, 27614, 27246, 25900,
        27553, 25896, 25817, 25560, 27445, 25804
    ]

    # 동시 요청 설정
    MAX_WORKERS = 3  # ThreadPoolExecutor 워커 수 (API rate limit 고려)

    # 재시도 설정
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # 초
