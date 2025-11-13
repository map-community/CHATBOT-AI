import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import requests
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from langchain_upstage import UpstageEmbeddings
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from pinecone import Pinecone
from langchain_upstage import ChatUpstage
from langchain import hub
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from langchain.schema import Document
import re
from datetime import datetime
import pytz
from langchain.schema.runnable import Runnable
from langchain.chains import RetrievalQAWithSourcesChain, RetrievalQA
from langchain.schema.runnable import RunnableSequence, RunnableMap
from langchain_core.runnables import RunnableLambda
import nltk
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag
from konlpy.tag import Okt
from collections import defaultdict
import numpy as np
from IPython.display import display, HTML
from rank_bm25 import BM25Okapi
from difflib import SequenceMatcher
from pymongo import MongoClient
from pinecone import Index
import redis
import pickle
import time
import logging

# 설정 가져오기
try:
    from src.config import settings
    PINECONE_API_KEY = settings.PINECONE_API_KEY
    PINECONE_INDEX_NAME = settings.PINECONE_INDEX_NAME
    UPSTAGE_API_KEY = settings.UPSTAGE_API_KEY
    MONGODB_URI = settings.MONGODB_URI
    REDIS_HOST = settings.REDIS_HOST
    REDIS_PORT = settings.REDIS_PORT
    REDIS_DB = settings.REDIS_DB
except ImportError:
    # Fallback to environment variables
    PINECONE_API_KEY = os.getenv('PINECONE_API_KEY', 'pcsk_3pp5QX_EeyfanpYE8u1G2hKkyLnfhWQMUHvdbUJeBZdULHaFMV5j67XDQwqXDUCBtFLYpt')
    PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'info')
    UPSTAGE_API_KEY = os.getenv('UPSTAGE_API_KEY', 'up_6hq78Et2phdvQWCMQLccIVpWJDF5R')
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))

# Pinecone API 설정 및 초기화
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

def get_korean_time():
    return datetime.now(pytz.timezone('Asia/Seoul'))

# mongodb 연결
client = MongoClient(MONGODB_URI)
db = client["knu_chatbot"]
collection = db["notice_collection"]

# Redis client 연결
redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

