"""
Storage Manager
데이터베이스 및 캐시 연결을 관리하는 싱글톤 클래스

이 모듈은 Pinecone, MongoDB, Redis 연결을 캡슐화하고
Lazy Initialization을 통해 필요할 때만 연결을 초기화합니다.
"""

import os
import logging
from typing import Optional
import redis
from pinecone import Pinecone
from pymongo import MongoClient
from dotenv import load_dotenv

# 로깅 설정
logger = logging.getLogger(__name__)


class StorageManager:
    """
    데이터베이스 및 캐시 연결을 관리하는 싱글톤 클래스

    모든 저장소 연결을 중앙에서 관리하고 Lazy Initialization을 통해
    필요할 때만 연결을 초기화합니다.
    """

    _instance: Optional['StorageManager'] = None

    def __new__(cls):
        """싱글톤 패턴 구현"""
        if cls._instance is None:
            cls._instance = super(StorageManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """초기화 (싱글톤이므로 한 번만 실행됨)"""
        if self._initialized:
            return

        # .env 파일 로드
        load_dotenv()

        # 환경 변수 읽기
        self._pinecone_api_key = os.getenv('PINECONE_API_KEY')
        self._index_name = os.getenv('PINECONE_INDEX_NAME', 'info')
        self._upstage_api_key = os.getenv('UPSTAGE_API_KEY')
        self._mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        self._redis_host = os.getenv('REDIS_HOST', 'localhost')
        self._redis_port = int(os.getenv('REDIS_PORT', 6379))

        # Reranker 설정
        self._reranker_type = os.getenv('RERANKER_TYPE', 'bge')
        self._reranker_model = os.getenv('RERANKER_MODEL', 'BAAI/bge-reranker-v2-m3')
        self._reranker_use_fp16 = os.getenv('RERANKER_USE_FP16', 'true').lower() == 'true'
        self._cohere_api_key = os.getenv('COHERE_API_KEY')

        # Lazy initialization용 플래그
        self._pinecone_client = None
        self._pinecone_index = None
        self._mongo_client = None
        self._mongo_db = None
        self._mongo_collection = None
        self._redis_client = None

        # 캐시 변수 초기화 (기본 필드)
        self.cached_titles = []
        self.cached_texts = []
        self.cached_urls = []
        self.cached_dates = []

        # 멀티모달 RAG를 위한 추가 캐시 필드
        self.cached_htmls = []  # HTML 구조 데이터 (표, 레이아웃 등)
        self.cached_content_types = []  # text, image, attachment
        self.cached_sources = []  # original_post, image_ocr, document_parse
        self.cached_image_urls = []  # 이미지 URL
        self.cached_attachment_urls = []  # 첨부파일 URL
        self.cached_attachment_types = []  # pdf, hwp, docx 등

        # Retriever 인스턴스 (캐시 초기화 후 생성됨)
        self._bm25_retriever = None
        self._dense_retriever = None
        self._document_combiner = None
        self._document_clusterer = None
        self._keyword_filter = None
        self._reranker = None  # Document Reranker

        # Preprocessing 인스턴스 (즉시 초기화 - DB 연결 불필요)
        self._query_transformer = None
        self._initialize_preprocessing_modules()

        self._initialized = True
        logger.info("✅ StorageManager 초기화 완료 (연결은 아직 시작되지 않음)")

    def _initialize_preprocessing_modules(self):
        """전처리 모듈 초기화 (DB 연결 불필요)"""
        logger.info("🔄 전처리 모듈 초기화 시작...")
        try:
            logger.info("  📦 preprocessing 모듈 import 시도...")
            from modules.preprocessing import QueryTransformer
            from modules.preprocessing.keyword_filter import KeywordFilter
            logger.info("  ✓ preprocessing 모듈 import 성공")

            logger.info("  🔧 QueryTransformer 생성 시도...")
            self._query_transformer = QueryTransformer(use_mecab=True)
            logger.info("✅ QueryTransformer 초기화 완료")

            logger.info("  🔧 KeywordFilter 생성 시도...")
            self._keyword_filter = KeywordFilter()
            logger.info("✅ KeywordFilter 초기화 완료")
        except ImportError as e:
            logger.error(f"❌ preprocessing 모듈 import 실패: {e}", exc_info=True)
            logger.error(f"   sys.path: {__import__('sys').path}")
            # 실패해도 None으로 유지하여 나중에 재시도 가능하도록
        except Exception as e:
            logger.error(f"❌ 전처리 모듈 초기화 실패: {e}", exc_info=True)
            logger.error(f"   실패 위치: {type(e).__name__}")
            # 실패해도 None으로 유지하여 나중에 재시도 가능하도록

    @property
    def pinecone_api_key(self) -> str:
        """Pinecone API 키 반환"""
        if not self._pinecone_api_key:
            raise ValueError("PINECONE_API_KEY가 설정되지 않았습니다.")
        return self._pinecone_api_key

    @property
    def upstage_api_key(self) -> str:
        """Upstage API 키 반환"""
        if not self._upstage_api_key:
            raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다.")
        return self._upstage_api_key

    @property
    def pinecone_client(self):
        """Pinecone 클라이언트 (Lazy initialization)"""
        if self._pinecone_client is None:
            try:
                logger.info("🔄 Pinecone에 연결 중...")
                self._pinecone_client = Pinecone(api_key=self.pinecone_api_key)
                logger.info("✅ Pinecone 클라이언트 초기화 완료")
            except Exception as e:
                logger.error(f"❌ Pinecone 연결 실패: {e}")
                raise
        return self._pinecone_client

    @property
    def pinecone_index(self):
        """Pinecone 인덱스 (Lazy initialization)"""
        if self._pinecone_index is None:
            try:
                self._pinecone_index = self.pinecone_client.Index(self._index_name)
                logger.info(f"✅ Pinecone 인덱스 '{self._index_name}'에 연결되었습니다.")
            except Exception as e:
                logger.error(f"❌ Pinecone 인덱스 연결 실패: {e}")
                raise
        return self._pinecone_index

    @property
    def mongo_client(self):
        """MongoDB 클라이언트 (Lazy initialization)"""
        if self._mongo_client is None:
            try:
                logger.info("🔄 MongoDB에 연결 중...")
                self._mongo_client = MongoClient(
                    self._mongodb_uri,
                    serverSelectionTimeoutMS=5000
                )
                # 연결 테스트
                self._mongo_client.admin.command('ping')
                logger.info("✅ MongoDB에 연결되었습니다.")
            except Exception as e:
                logger.error(f"❌ MongoDB 연결 실패: {e}")
                logger.warning("⚠️  MongoDB 없이 계속 진행합니다. 일부 기능이 제한될 수 있습니다.")
                self._mongo_client = None
        return self._mongo_client

    @property
    def mongo_db(self):
        """MongoDB 데이터베이스 (Lazy initialization)"""
        if self._mongo_db is None and self.mongo_client is not None:
            self._mongo_db = self.mongo_client["knu_chatbot"]
        return self._mongo_db

    @property
    def mongo_collection(self):
        """MongoDB 컬렉션 (Lazy initialization)"""
        if self._mongo_collection is None and self.mongo_db is not None:
            self._mongo_collection = self.mongo_db["notice_collection"]
        return self._mongo_collection

    @property
    def redis_client(self):
        """Redis 클라이언트 (Lazy initialization)"""
        if self._redis_client is None:
            try:
                logger.info("🔄 Redis에 연결 중...")
                self._redis_client = redis.StrictRedis(
                    host=self._redis_host,
                    port=self._redis_port,
                    db=0,
                    socket_connect_timeout=5
                )
                # 연결 테스트
                self._redis_client.ping()
                logger.info("✅ Redis에 연결되었습니다.")
            except Exception as e:
                logger.error(f"❌ Redis 연결 실패: {e}")
                logger.warning("⚠️  Redis 없이 계속 진행합니다. 캐싱 기능이 비활성화됩니다.")
                self._redis_client = None
        return self._redis_client

    @property
    def bm25_retriever(self):
        """BM25Retriever 인스턴스 (캐시 초기화 후 사용 가능)"""
        if self._bm25_retriever is None:
            logger.warning("⚠️  BM25Retriever가 아직 초기화되지 않았습니다. initialize_cache()를 먼저 호출하세요.")
        return self._bm25_retriever

    def set_bm25_retriever(self, retriever):
        """BM25Retriever 인스턴스 설정 (initialize_cache에서 호출)"""
        self._bm25_retriever = retriever
        logger.info("✅ BM25Retriever 인스턴스 설정 완료")

    @property
    def dense_retriever(self):
        """DenseRetriever 인스턴스 (캐시 초기화 후 사용 가능)"""
        if self._dense_retriever is None:
            logger.warning("⚠️  DenseRetriever가 아직 초기화되지 않았습니다. initialize_cache()를 먼저 호출하세요.")
        return self._dense_retriever

    def set_dense_retriever(self, retriever):
        """DenseRetriever 인스턴스 설정 (initialize_cache에서 호출)"""
        self._dense_retriever = retriever
        logger.info("✅ DenseRetriever 인스턴스 설정 완료")

    @property
    def document_combiner(self):
        """DocumentCombiner 인스턴스 (캐시 초기화 후 사용 가능)"""
        if self._document_combiner is None:
            logger.warning("⚠️  DocumentCombiner가 아직 초기화되지 않았습니다. initialize_cache()를 먼저 호출하세요.")
        return self._document_combiner

    def set_document_combiner(self, combiner):
        """DocumentCombiner 인스턴스 설정 (initialize_cache에서 호출)"""
        self._document_combiner = combiner
        logger.info("✅ DocumentCombiner 인스턴스 설정 완료")

    @property
    def document_clusterer(self):
        """DocumentClusterer 인스턴스 (캐시 초기화 후 사용 가능)"""
        if self._document_clusterer is None:
            logger.warning("⚠️  DocumentClusterer가 아직 초기화되지 않았습니다. initialize_cache()를 먼저 호출하세요.")
        return self._document_clusterer

    def set_document_clusterer(self, clusterer):
        """DocumentClusterer 인스턴스 설정 (initialize_cache에서 호출)"""
        self._document_clusterer = clusterer
        logger.info("✅ DocumentClusterer 인스턴스 설정 완료")

    @property
    def query_transformer(self):
        """QueryTransformer 인스턴스 (StorageManager 초기화 시 자동 생성)"""
        if self._query_transformer is None:
            logger.warning("⚠️  QueryTransformer가 초기화되지 않았습니다. 재초기화를 시도합니다...")
            # 재초기화 시도
            self._initialize_preprocessing_modules()

            # 재초기화도 실패한 경우
            if self._query_transformer is None:
                logger.error("❌ QueryTransformer 초기화 실패! preprocessing 모듈을 확인하세요.")
                raise RuntimeError(
                    "QueryTransformer 초기화에 실패했습니다. "
                    "konlpy와 Mecab이 올바르게 설치되었는지 확인하세요."
                )
        return self._query_transformer

    def set_query_transformer(self, transformer):
        """QueryTransformer 인스턴스 재설정 (일반적으로 불필요)"""
        self._query_transformer = transformer
        logger.info("✅ QueryTransformer 인스턴스 재설정 완료")

    @property
    def keyword_filter(self):
        """KeywordFilter 인스턴스"""
        if self._keyword_filter is None:
            logger.warning("⚠️  KeywordFilter가 초기화되지 않았습니다. 재초기화를 시도합니다...")
            # 재초기화 시도
            self._initialize_preprocessing_modules()

            # 재초기화도 실패한 경우
            if self._keyword_filter is None:
                logger.error("❌ KeywordFilter 초기화 실패! preprocessing 모듈을 확인하세요.")
                raise RuntimeError(
                    "KeywordFilter 초기화에 실패했습니다. "
                    "preprocessing 모듈이 올바르게 설치되었는지 확인하세요."
                )
        return self._keyword_filter

    def set_keyword_filter(self, filter_instance):
        """KeywordFilter 인스턴스 설정"""
        self._keyword_filter = filter_instance
        logger.info("✅ KeywordFilter 인스턴스 설정 완료")

    @property
    def reranker(self):
        """DocumentReranker 인스턴스 (즉시 초기화 가능)"""
        if self._reranker is None:
            logger.info(f"🔄 Reranker 초기화 중 (type: {self._reranker_type})...")
            try:
                from factories.reranker_factory import RerankerFactory

                # Reranker 타입에 따라 적절한 파라미터 전달
                if self._reranker_type == "bge":
                    self._reranker = RerankerFactory.create(
                        reranker_type="bge",
                        model_name=self._reranker_model,
                        use_fp16=self._reranker_use_fp16
                    )
                elif self._reranker_type == "cohere":
                    if not self._cohere_api_key:
                        logger.error("❌ COHERE_API_KEY가 설정되지 않았습니다.")
                        logger.warning("   Reranking이 비활성화됩니다 (원본 순서 유지)")
                        return None

                    self._reranker = RerankerFactory.create(
                        reranker_type="cohere",
                        api_key=self._cohere_api_key,
                        model=os.getenv('COHERE_RERANK_MODEL', 'rerank-multilingual-v3.0')
                    )
                else:
                    logger.error(f"❌ 알 수 없는 Reranker 타입: {self._reranker_type}")
                    logger.warning("   Reranking이 비활성화됩니다 (원본 순서 유지)")
                    return None

                if self._reranker is not None:
                    logger.info("✅ Reranker 초기화 완료")
                else:
                    logger.warning(f"⚠️  Reranker 초기화 실패 (타입: {self._reranker_type})")
                    logger.warning("   Reranking이 비활성화됩니다 (원본 순서 유지)")
            except Exception as e:
                logger.warning(f"⚠️  Reranker 초기화 실패: {e}")
                logger.warning("   Reranking이 비활성화됩니다 (원본 순서 유지)")
                # 실패 시 None 유지 (ai_modules에서 None 체크 필요)
        return self._reranker

    def set_reranker(self, reranker):
        """DocumentReranker 인스턴스 설정"""
        self._reranker = reranker
        logger.info("✅ DocumentReranker 인스턴스 설정 완료")

    def close_all_connections(self):
        """모든 연결 종료"""
        if self._mongo_client is not None:
            self._mongo_client.close()
            logger.info("✅ MongoDB 연결 종료")

        if self._redis_client is not None:
            self._redis_client.close()
            logger.info("✅ Redis 연결 종료")

        logger.info("✅ 모든 저장소 연결 종료 완료")


# 싱글톤 인스턴스를 반환하는 헬퍼 함수
def get_storage_manager() -> StorageManager:
    """StorageManager 싱글톤 인스턴스 반환"""
    return StorageManager()
