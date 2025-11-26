"""
Configuration settings for KNU Chatbot
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# --- 1. .env 파일 로드 ---
# BASE_DIR를 기준으로 .env 파일을 찾아서 환경 변수로 로드합니다.
# 이 코드는 os.getenv()가 호출되기 전에 가장 먼저 실행되어야 합니다.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env_path = BASE_DIR / '.env'

if not env_path.exists():
    # .env 파일이 없는 경우, 서버 환경처럼 환경 변수가
    # 이미 시스템에 설정되어 있다고 가정합니다. (경고 메시지는 선택 사항)
    print(f"경고: .env 파일({env_path})을 찾을 수 없습니다. 시스템 환경 변수를 사용합니다.")
    
load_dotenv(dotenv_path=env_path)


# --- 2. 민감 정보 (Secrets) ---
# API 키 등은 절대 기본값을 코드에 남기지 않습니다.
# 값이 없으면(None) 프로그램이 시작조차 되지 않도록 'Fail-Fast' 처리합니다.

# Pinecone Configuration
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
UPSTAGE_API_KEY = os.getenv('UPSTAGE_API_KEY')

# 필수 환경 변수 검증
if not PINECONE_API_KEY:
    raise ValueError("필수 환경 변수 'PINECONE_API_KEY'가 설정되지 않았습니다. .env 파일을 확인하세요.")
if not UPSTAGE_API_KEY:
    raise ValueError("필수 환경 변수 'UPSTAGE_API_KEY'가 설정되지 않았습니다. .env 파일을 확인하세요.")


# --- 3. 서비스 설정 (Configs) ---
# 로컬 개발 환경(localhost)을 위한 '편리한 기본값'을 제공합니다.
# 이 값들은 민감 정보가 아니므로 코드에 남아 있어도 괜찮습니다.
# 운영(배포) 환경에서는 .env 또는 시스템 환경 변수로 이 값들을 덮어쓰게 됩니다.

# Pinecone (Index Name은 민감 정보가 아니므로 기본값 허용)
PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'info')

# MongoDB Configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'knu_chatbot')
MONGODB_COLLECTION = os.getenv('MONGODB_COLLECTION', 'notice_collection')

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

# Flask Configuration
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
# .env 파일의 "True", "true", "1" 문자열을 bool True로 변환
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')


# --- 4. 애플리케이션 로직 상수 ---
# 이 값들은 환경(Dev/Prod)에 따라 바뀌는 값이 아니라,
# 애플리케이션의 고유한 로직/모델을 정의하는 상수들입니다.
# 따라서 .env가 아닌 settings.py에 직접 정의하는 것이 더 명확합니다.

# Logging Configuration
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / 'app.log'

# Embedding Configuration
EMBEDDING_MODEL = 'solar-embedding-1-large'
EMBEDDING_DIMENSION = 4096

# Retrieval Configuration
# ML 하이퍼파라미터는 config/ml_config.yaml 및 ml_settings.py에서 관리
# 하위 호환성을 위해 여기서는 import만 수행
from config.ml_settings import get_ml_config

# ML 설정 로드
_ml_config = get_ml_config()

# 하위 호환성을 위한 상수들 (기존 코드가 이 변수를 참조하는 경우)
BM25_K1 = _ml_config.bm25.k1
BM25_B = _ml_config.bm25.b
CLUSTER_SIMILARITY_THRESHOLD = _ml_config.clustering.similarity_threshold
CHUNK_SIZE = _ml_config.text_processing.chunk_size
CHUNK_OVERLAP = _ml_config.text_processing.chunk_overlap

# 검색 문서 수 (환경별로 다를 수 있음)
TOP_K_DOCUMENTS = 30

# 최소 유사도 임계값 (Minimum Similarity Score Threshold)
# - 검색된 문서와 질문의 관련성을 판단하는 기준점
# - 점수 구성: BM25(~5점) + Dense Retrieval(~1점) + Recency Boost(최대 1.5배)
# - 임계값 미만: "해당 질문은 공지사항에 없는 내용입니다" 응답
# - 임계값 이상: LLM 답변 생성
#
# 조정 가이드:
#   * 값이 너무 높으면 (2.5+): 정상 질문도 차단될 수 있음 (재현율↓)
#   * 값이 너무 낮으면 (1.0-): 관련 없는 질문에도 답변 (정밀도↓)
#   * 현재값 1.8: 실험적으로 설정된 값 (추후 A/B 테스트로 최적화 권장)
MINIMUM_SIMILARITY_SCORE = 1.8

# Reranker 전용 최소 유사도 임계값 (Reranker가 적용된 경우)
# - Reranker는 0~1 범위의 relevance score를 반환 (BGE는 음수도 가능하지만 양수가 일반적)
# - Cohere Reranker: 0~1 범위, 0.5 이상이면 관련성 높음
# - BGE Reranker: 대략 -10~10 범위, 0.3 이상이면 관련성 있음
# - 임계값 미만: "해당 질문은 공지사항에 없는 내용입니다" 응답
# - 임계값 이상: LLM 답변 생성
#
# 조정 가이드:
#   * 값이 너무 높으면 (0.7+): Reranker가 선택한 문서도 차단될 수 있음 (재현율↓)
#   * 값이 너무 낮으면 (0.1-): 관련 없는 문서도 통과 (정밀도↓)
#   * 현재값 0.3: BGE/Cohere 모두 대응 가능한 보수적 값
MINIMUM_RERANKER_SCORE = 0.3