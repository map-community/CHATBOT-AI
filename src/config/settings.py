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
BM25_K1 = 1.5
BM25_B = 0.75
TOP_K_DOCUMENTS = 30
CLUSTER_SIMILARITY_THRESHOLD = 0.89
MINIMUM_SIMILARITY_SCORE = 1.8

# Text Splitting Configuration
CHUNK_SIZE = 850
CHUNK_OVERLAP = 100