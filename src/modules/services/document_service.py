"""
Document Service

Pinecone 및 MongoDB에서 문서 데이터를 페칭하고 캐싱하는 서비스
"""
import logging
import pickle
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)


class DocumentService:
    """
    문서 데이터 관리 서비스

    Responsibilities:
    - Pinecone에서 전체 문서 메타데이터 페칭
    - MongoDB에서 HTML/Markdown 콘텐츠 조회
    - Redis 캐싱 관리
    - StorageManager 캐시 초기화
    """

    def __init__(self, storage_manager):
        """
        Args:
            storage_manager: StorageManager 인스턴스
        """
        self.storage = storage_manager

    def fetch_all_documents(self) -> Tuple[List, ...]:
        """
        Pinecone에서 전체 데이터(제목, 텍스트, 메타데이터)를 조회

        Process:
        1. list() 메서드(Pagination)로 모든 ID 가져오기
        2. fetch() 메서드(Batch)로 메타데이터 효율적으로 가져오기
        3. html_available인 경우 MongoDB에서 실제 HTML 조회

        Returns:
            Tuple[List, ...]: (titles, texts, urls, dates, htmls, content_types,
                               sources, image_urls, attachment_urls, attachment_types)
        """
        logger.info("🔄 Pinecone 전체 데이터 조회 시작...")

        # MongoDB 연결 (HTML 조회용)
        mongo_collection = None
        try:
            if self.storage.mongo_collection is not None:
                mongo_collection = self.storage.mongo_collection.database["multimodal_cache"]
                logger.info("✅ MongoDB 연결 성공 (HTML 조회용)")
        except Exception as e:
            logger.warning(f"⚠️  MongoDB 연결 실패 (HTML 없이 진행): {e}")

        # 1. 전체 ID 가져오기
        all_ids = self._fetch_all_vector_ids()
        if not all_ids:
            return self._empty_result()

        # 2. 배치로 메타데이터 가져오기
        return self._fetch_metadata_in_batches(all_ids, mongo_collection)

    def _fetch_all_vector_ids(self) -> List[str]:
        """Pinecone에서 모든 벡터 ID 가져오기"""
        all_ids = []

        try:
            for ids in self.storage.pinecone_index.list(namespace=""):
                all_ids.extend(ids)
            logger.info(f"📊 총 {len(all_ids)}개의 벡터 ID를 발견했습니다.")
        except Exception as e:
            logger.error(f"❌ ID 리스팅 실패: {e}")
            logger.error("👉 'requirements.txt'의 pinecone 버전을 확인하고 재빌드하세요.")
            return []

        if not all_ids:
            logger.warning("⚠️ 조회된 데이터가 0개입니다.")

        return all_ids

    def _fetch_metadata_in_batches(
        self,
        all_ids: List[str],
        mongo_collection
    ) -> Tuple[List, ...]:
        """배치 단위로 메타데이터 페칭"""
        # 결과 리스트 초기화
        titles, texts, urls, dates = [], [], [], []
        htmls, content_types, sources = [], [], []
        image_urls, attachment_urls, attachment_types = [], [], []

        # 통계 카운터
        html_available_count = 0
        mongo_found_count = 0
        html_extracted_count = 0

        # 1,000개씩 배치 처리
        batch_size = 1000
        for i in range(0, len(all_ids), batch_size):
            logger.info(f"⏳ 데이터 가져오는 중... ({i} / {len(all_ids)})")

            batch_ids = all_ids[i:i + batch_size]

            try:
                # Pinecone Fetch
                fetch_response = self.storage.pinecone_index.fetch(ids=batch_ids)
                vectors = self._extract_vectors_from_response(fetch_response)

                # 각 벡터 데이터 파싱
                for vector_id in batch_ids:
                    if vector_id not in vectors:
                        continue

                    vector_data = vectors[vector_id]
                    metadata = self._extract_metadata(vector_data)

                    # 기본 메타데이터 추가
                    titles.append(metadata.get("title", ""))
                    texts.append(metadata.get("text", ""))
                    url = metadata.get("url", "")
                    urls.append(url)
                    dates.append(metadata.get("date", ""))

                    # HTML 조회 (html_available인 경우)
                    html = ""
                    if metadata.get("html_available"):
                        html_available_count += 1
                        html, found = self._fetch_html_from_mongodb(
                            metadata, mongo_collection, html_available_count
                        )
                        if found:
                            mongo_found_count += 1
                            html_extracted_count += 1

                    htmls.append(html)
                    content_types.append(metadata.get("content_type", "text"))
                    sources.append(metadata.get("source", "original_post"))
                    image_urls.append(metadata.get("image_url", ""))
                    attachment_urls.append(metadata.get("attachment_url", ""))
                    attachment_types.append(metadata.get("attachment_type", ""))

            except Exception as e:
                logger.error(f"⚠️ 배치 Fetch 실패 ({i}~{i+batch_size}): {e}")
                continue

        # 통계 로깅
        self._log_statistics(
            len(titles), html_available_count,
            mongo_found_count, html_extracted_count
        )

        return (titles, texts, urls, dates, htmls, content_types,
                sources, image_urls, attachment_urls, attachment_types)

    def _extract_vectors_from_response(self, fetch_response) -> dict:
        """Fetch 응답에서 벡터 딕셔너리 추출 (버전 호환성 처리)"""
        vectors = {}

        if hasattr(fetch_response, 'to_dict'):
            response_dict = fetch_response.to_dict()
            vectors = response_dict.get('vectors', {})
        elif hasattr(fetch_response, 'vectors'):
            vectors = fetch_response.vectors
        else:
            vectors = fetch_response.get('vectors', {})

        return vectors or {}

    def _extract_metadata(self, vector_data) -> dict:
        """벡터 데이터에서 메타데이터 추출"""
        if isinstance(vector_data, dict):
            return vector_data.get('metadata', {}) or {}
        elif hasattr(vector_data, 'metadata'):
            return vector_data.metadata or {}
        return {}

    def _fetch_html_from_mongodb(
        self,
        metadata: dict,
        mongo_collection,
        count: int
    ) -> Tuple[str, bool]:
        """
        MongoDB에서 HTML/Markdown 조회

        Args:
            metadata: Pinecone 메타데이터
            mongo_collection: MongoDB 컬렉션
            count: 현재까지 조회 시도 횟수 (로깅용)

        Returns:
            Tuple[str, bool]: (HTML/Markdown 콘텐츠, 찾았는지 여부)
        """
        if mongo_collection is None:
            return "", False

        try:
            # image_url 또는 attachment_url로 조회
            lookup_url = metadata.get("image_url") or metadata.get("attachment_url")

            if not lookup_url:
                if count <= 3:
                    url = metadata.get("url", "")
                    logger.warning(f"⚠️  html_available=true인데 image_url/attachment_url 없음 (board URL: {url[:80]}...)")
                return "", False

            # 디버깅 로깅 (처음 3개만)
            if count <= 3:
                logger.info(f"🔍 조회 시도 URL: {lookup_url[:80]}...")

            # MongoDB 조회
            cached = mongo_collection.find_one({"url": lookup_url})

            if cached:
                if count <= 3:
                    logger.info(f"✅ MongoDB에서 발견: {lookup_url[:80]}...")
                    logger.info(f"   필드: {list(cached.keys())}")

                # Markdown 우선 (Upstage API 제공, 고품질 표 구조)
                markdown_content = cached.get("ocr_markdown") or cached.get("markdown", "")
                # Markdown이 없으면 HTML 사용 (fallback)
                html_content = markdown_content or cached.get("ocr_html") or cached.get("html", "")

                if html_content:
                    return html_content, True
            else:
                if count <= 3:
                    logger.warning(f"❌ MongoDB에서 못 찾음: {lookup_url[:80]}...")

        except Exception as e:
            logger.warning(f"MongoDB HTML 조회 실패: {e}")

        return "", False

    def _log_statistics(
        self,
        total_count: int,
        html_available: int,
        mongo_found: int,
        html_extracted: int
    ):
        """통계 로깅"""
        logger.info(f"✅ 전체 데이터 로드 완료: {total_count}개 문서")
        logger.info(f"📊 HTML 조회 통계:")
        logger.info(f"   - html_available=true 문서: {html_available}개")
        logger.info(f"   - MongoDB에서 찾은 문서: {mongo_found}개")
        logger.info(f"   - 실제 HTML 추출 성공: {html_extracted}개")

    def _empty_result(self) -> Tuple[List, ...]:
        """빈 결과 반환"""
        empty_list = []
        return (empty_list, empty_list, empty_list, empty_list, empty_list,
                empty_list, empty_list, empty_list, empty_list, empty_list)

    def initialize_cache(self):
        """
        캐시 초기화 (Redis Fast Track 적용)

        Process:
        1. Redis 캐시 확인 (있으면 3초 로딩)
        2. 없으면 Pinecone에서 다운로드 (20분 소요, 최초 1회만)
        3. Redis에 저장 (다음 재시작 시 Fast Track)
        4. Retriever 초기화
        """
        try:
            logger.info("🔄 캐시 초기화 시작...")

            # 1. Redis 캐시 확인 (Fast Track)
            if self._load_from_redis_cache():
                return  # Fast Track 성공

            # 2. Pinecone에서 데이터 가져오기 (Slow Track)
            self._load_from_pinecone()

            # 3. Redis에 저장 (다음을 위해)
            self._save_to_redis_cache()

            logger.info(f"✅ 캐시 초기화 완료! (titles: {len(self.storage.cached_titles)}, texts: {len(self.storage.cached_texts)})")
            logger.info(f"   ⚠️  Retriever 초기화는 ai_modules에서 별도로 수행됩니다.")

        except Exception as e:
            logger.error(f"❌ 캐시 초기화 실패: {e}", exc_info=True)
            self._initialize_empty_cache()

    def _load_from_redis_cache(self) -> bool:
        """Redis 캐시에서 로드 (Fast Track)"""
        if self.storage.redis_client is None:
            return False

        try:
            logger.info("🔍 Redis 캐시 확인 중...")
            cached_data = self.storage.redis_client.get('pinecone_metadata')

            if not cached_data:
                logger.info("⬇️  Redis에 캐시가 없습니다. Pinecone 다운로드를 시작합니다...")
                return False

            # Redis 캐시 발견!
            logger.info("🚀 Redis 캐시 발견! 빠른 로딩을 시작합니다...")

            # Pickle 데이터 복원
            (self.storage.cached_titles, self.storage.cached_texts,
             self.storage.cached_urls, self.storage.cached_dates,
             self.storage.cached_htmls, self.storage.cached_content_types,
             self.storage.cached_sources, self.storage.cached_image_urls,
             self.storage.cached_attachment_urls, self.storage.cached_attachment_types
            ) = pickle.loads(cached_data)

            self._log_cache_stats("Redis")

            logger.info(f"✅ 캐시 로드 완료! (titles: {len(self.storage.cached_titles)}, texts: {len(self.storage.cached_texts)})")
            logger.info(f"   ⚠️  Retriever 초기화는 ai_modules에서 별도로 수행됩니다.")
            return True

        except Exception as e:
            logger.warning(f"⚠️  Redis 로드 실패 (Pinecone에서 새로 다운로드합니다): {e}")
            return False

    def _load_from_pinecone(self):
        """Pinecone에서 데이터 가져오기 (Slow Track)"""
        logger.info("⏳ Pinecone 전체 데이터 다운로드 시작 (최초 1회, 약 20분 소요)...")

        (self.storage.cached_titles, self.storage.cached_texts,
         self.storage.cached_urls, self.storage.cached_dates,
         self.storage.cached_htmls, self.storage.cached_content_types,
         self.storage.cached_sources, self.storage.cached_image_urls,
         self.storage.cached_attachment_urls, self.storage.cached_attachment_types
        ) = self.fetch_all_documents()

        self._log_cache_stats("Pinecone")

    def _save_to_redis_cache(self):
        """Redis에 캐시 저장"""
        if self.storage.redis_client is None:
            logger.warning("⚠️  Redis 미사용 (메모리 캐시만 사용)")
            return

        try:
            cache_data = (
                self.storage.cached_titles, self.storage.cached_texts,
                self.storage.cached_urls, self.storage.cached_dates,
                self.storage.cached_htmls, self.storage.cached_content_types,
                self.storage.cached_sources, self.storage.cached_image_urls,
                self.storage.cached_attachment_urls, self.storage.cached_attachment_types
            )
            # 24시간 유효 (86400초)
            self.storage.redis_client.setex(
                'pinecone_metadata', 86400, pickle.dumps(cache_data)
            )
            logger.info("💾 데이터를 Redis에 저장했습니다. (다음 재시작부터는 3초 로딩!)")

        except Exception as e:
            logger.warning(f"⚠️  Redis 저장 실패 (메모리 캐시만 사용): {e}")

    def _log_cache_stats(self, source: str):
        """캐시 통계 로깅"""
        logger.info(f"✅ {source}에서 {len(self.storage.cached_titles)}개 문서 메타데이터를 가져왔습니다.")
        logger.info(f"   - HTML 구조 있는 문서: {sum(1 for html in self.storage.cached_htmls if html)}개")
        logger.info(f"   - 이미지 OCR 문서: {sum(1 for ct in self.storage.cached_content_types if ct == 'image')}개")
        logger.info(f"   - 첨부파일 문서: {sum(1 for ct in self.storage.cached_content_types if ct == 'attachment')}개")

    def _initialize_empty_cache(self):
        """에러 시 빈 캐시로 초기화"""
        self.storage.cached_titles = []
        self.storage.cached_texts = []
        self.storage.cached_urls = []
        self.storage.cached_dates = []
        self.storage.cached_htmls = []
        self.storage.cached_content_types = []
        self.storage.cached_sources = []
        self.storage.cached_image_urls = []
        self.storage.cached_attachment_urls = []
        self.storage.cached_attachment_types = []
