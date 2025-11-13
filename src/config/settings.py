"""
Configuration settings for KNU Chatbot
"""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Pinecone Configuration
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY', 'pcsk_3pp5QX_EeyfanpYE8u1G2hKkyLnfhWQMUHvdbUJeBZdULHaFMV5j67XDQwqXDUCBtFLYpt')
PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'info')

# Upstage Configuration
UPSTAGE_API_KEY = os.getenv('UPSTAGE_API_KEY', 'up_6hq78Et2phdvQWCMQLccIVpWJDF5R')

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
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

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
