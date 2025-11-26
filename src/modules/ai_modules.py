import os
import re
import time
import pickle
import logging
from datetime import datetime
from collections import defaultdict
import numpy as np
import pytz
from dotenv import load_dotenv
from pinecone import Pinecone
from rank_bm25 import BM25Okapi
from langchain import hub
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain.schema.runnable import Runnable, RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnableSequence, RunnableMap
from langchain_core.runnables import RunnableLambda
from langchain_upstage import UpstageEmbeddings, ChatUpstage
from pymongo import MongoClient

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# .env 파일 로드
load_dotenv()

# Mecab import (logger 정의 이후)
try:
    from konlpy.tag import Mecab
    MECAB_AVAILABLE = True
    logger.info("✅ Mecab 사용 가능 (30-50배 빠른 형태소 분석)")
except Exception as e:
    logger.warning(f"⚠️  Mecab을 불러올 수 없습니다: {e}")
    logger.warning("⚠️  Mecab 없이 계속 진행합니다. 한국어 형태소 분석 정확도가 낮아질 수 있습니다.")
    MECAB_AVAILABLE = False
    Mecab = None

# StorageManager import
from modules.storage_manager import get_storage_manager

# Configuration import
from config.settings import MINIMUM_SIMILARITY_SCORE
from config.prompts import get_qa_prompt, get_temporal_intent_prompt
from config.ml_settings import get_ml_config

# Utils import
from modules.utils.date_utils import get_current_kst as get_korean_time, parse_date_change_korea_time
from modules.utils.url_utils import find_url
from modules.utils.formatter import format_temporal_intent, format_docs

# StorageManager 싱글톤 인스턴스 가져오기
storage = get_storage_manager()

# ML 설정 로드
ml_config = get_ml_config()

# URL 상수
NOTICE_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1"
COMPANY_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_3_b"
SEMINAR_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_4"
PROFESSOR_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_2"

# 단어 명사화 함수 (리팩토링됨 - QueryTransformer 사용)
def transformed_query(content):
    """
    질문을 명사 키워드 리스트로 변환

    Args:
        content: 사용자 질문 (원문)

    Returns:
        List[str]: 추출된 명사 키워드 리스트
    """
    return storage.query_transformer.transform(content)
###################################################################################################


# Dense Retrieval (Upstage 임베딩) - Lazy initialization으로 함수 내에서 생성하도록 변경
# embeddings 객체는 필요할 때 get_embeddings() 함수를 통해 가져옵니다.
def get_embeddings():
    """Upstage Embeddings 객체 반환 (Lazy initialization)"""
    return UpstageEmbeddings(
        api_key=storage.upstage_api_key,
        model="solar-embedding-1-large-query"  # 질문 임베딩용 모델
    )
# dense_doc_vectors = np.array(embeddings.embed_documents(texts))  # 문서 임베딩

def fetch_titles_from_pinecone():
    """
    Pinecone에서 전체 데이터(제목, 텍스트, 메타데이터)를 조회합니다.
    - list() 메서드(Pagination)를 사용하여 개수 제한 없이 모든 ID를 가져옵니다.
    - fetch() 메서드(Batch)를 사용하여 데이터를 효율적으로 가져옵니다.
    - html_available=true인 경우 MongoDB에서 실제 HTML을 가져옵니다.
    """
    logger.info("🔄 Pinecone 전체 데이터 조회 시작...")

    # ==========================================
    # MongoDB 연결 (HTML 조회용)
    # ==========================================
    mongo_collection = None
    mongo_client = None
    try:
        if storage.mongo_collection is not None:
            # StorageManager의 MongoDB connection 사용
            mongo_collection = storage.mongo_collection.database["multimodal_cache"]
            logger.info("✅ MongoDB 연결 성공 (HTML 조회용)")
    except Exception as e:
        logger.warning(f"⚠️  MongoDB 연결 실패 (HTML 없이 진행): {e}")

    # ==========================================
    # 1. 전체 ID 가져오기 (개수 제한 없음!)
    # ==========================================
    all_ids = []
    
    try:
        # namespace가 있다면 지정해야 합니다. (기본값 "")
        # list()는 전체 ID를 페이지네이션하여 모두 가져옵니다.
        for ids in storage.pinecone_index.list(namespace=""): 
            all_ids.extend(ids)
        logger.info(f"📊 총 {len(all_ids)}개의 벡터 ID를 발견했습니다.")

    except Exception as e:
        logger.error(f"❌ ID 리스팅 실패: {e}")
        # 라이브러리 버전 문제일 경우를 대비한 안내
        logger.error("👉 'requirements.txt'의 pinecone 버전을 확인하고 재빌드하세요.")
        return [], [], [], [], [], [], [], [], [], []

    # 데이터가 없으면 안전하게 종료
    if not all_ids:
        logger.warning("⚠️ 조회된 데이터가 0개입니다.")
        return [], [], [], [], [], [], [], [], [], []


    # ==========================================
    # 2. ID로 메타데이터 가져오기 (Batch Fetch)
    # ==========================================
    # 결과를 담을 리스트 초기화
    titles = []
    texts = []
    urls = []
    dates = []
    htmls = []
    content_types = []
    sources = []
    image_urls = []
    attachment_urls = []
    attachment_types = []

    # 한 번에 가져올 배치 크기
    batch_size = 1000

    # 디버깅 카운터 추가
    html_available_count = 0
    mongo_found_count = 0
    html_extracted_count = 0

    # 1,000개씩 끊어서 요청
    for i in range(0, len(all_ids), batch_size):
        logger.info(f"⏳ 데이터 가져오는 중... ({i} / {len(all_ids)})")
        
        batch_ids = all_ids[i:i + batch_size]
        
        try:
            # Fetch 요청
            fetch_response = storage.pinecone_index.fetch(ids=batch_ids)
            
            # 응답 객체를 딕셔너리로 변환 (v3 호환성 해결)
            vectors = {}
            if hasattr(fetch_response, 'to_dict'):
                response_dict = fetch_response.to_dict()
                vectors = response_dict.get('vectors', {})
            elif hasattr(fetch_response, 'vectors'):
                vectors = fetch_response.vectors
            else:
                vectors = fetch_response.get('vectors', {})

            if vectors is None:
                vectors = {}
            
            # 가져온 데이터 파싱
            for vector_id in batch_ids:
                if vector_id in vectors:
                    vector_data = vectors[vector_id]
                    
                    # 메타데이터 추출
                    if isinstance(vector_data, dict):
                        metadata = vector_data.get('metadata', {})
                    elif hasattr(vector_data, 'metadata'):
                        metadata = vector_data.metadata
                    else:
                        metadata = {}

                    if metadata is None:
                        metadata = {}
                    
                    # 리스트에 데이터 추가
                    titles.append(metadata.get("title", ""))
                    texts.append(metadata.get("text", ""))
                    url = metadata.get("url", "")
                    urls.append(url)
                    dates.append(metadata.get("date", ""))

                    # 멀티모달 메타데이터: html_available이면 MongoDB에서 HTML 조회
                    html = ""
                    if metadata.get("html_available"):
                        html_available_count += 1
                        if mongo_collection is not None:
                            try:
                                # html_available=true인 chunk는 이미지/첨부파일에서 추출된 것
                                # MongoDB cache는 image_url 또는 attachment_url을 key로 사용
                                lookup_url = metadata.get("image_url") or metadata.get("attachment_url")

                                if lookup_url:
                                    # 디버깅: URL 로깅 (처음 3개만)
                                    if html_available_count <= 3:
                                        logger.info(f"🔍 조회 시도 URL: {lookup_url[:80]}...")

                                    cached = mongo_collection.find_one({"url": lookup_url})
                                    if cached:
                                        mongo_found_count += 1
                                        # 디버깅: 찾은 경우 로깅
                                        if mongo_found_count <= 3:
                                            logger.info(f"✅ MongoDB에서 발견: {lookup_url[:80]}...")
                                            logger.info(f"   필드: {list(cached.keys())}")

                                        # Markdown 우선 (Upstage API 제공, 고품질 표 구조)
                                        # 이미지: ocr_markdown, 문서: markdown
                                        markdown_content = cached.get("ocr_markdown") or cached.get("markdown", "")

                                        # Markdown이 없으면 HTML 사용 (fallback)
                                        html_content = markdown_content or cached.get("ocr_html") or cached.get("html", "")

                                        if html_content:
                                            html = html_content
                                            html_extracted_count += 1
                                    else:
                                        # 디버깅: 못 찾은 경우 로깅 (처음 3개만)
                                        if html_available_count <= 3:
                                            logger.warning(f"❌ MongoDB에서 못 찾음: {lookup_url[:80]}...")
                                else:
                                    # image_url과 attachment_url이 둘 다 없는 경우
                                    if html_available_count <= 3:
                                        logger.warning(f"⚠️  html_available=true인데 image_url/attachment_url 없음 (board URL: {url[:80]}...)")
                            except Exception as e:
                                logger.warning(f"MongoDB HTML 조회 실패: {e}")

                    htmls.append(html)
                    content_types.append(metadata.get("content_type", "text"))
                    sources.append(metadata.get("source", "original_post"))
                    image_urls.append(metadata.get("image_url", ""))
                    attachment_urls.append(metadata.get("attachment_url", ""))
                    attachment_types.append(metadata.get("attachment_type", ""))
                    
        except Exception as e:
            logger.error(f"⚠️ 배치 Fetch 실패 ({i}~{i+batch_size}): {e}")
            continue

    logger.info(f"✅ 전체 데이터 로드 완료: {len(titles)}개 문서")
    logger.info(f"📊 HTML 조회 통계:")
    logger.info(f"   - html_available=true 문서: {html_available_count}개")
    logger.info(f"   - MongoDB에서 찾은 문서: {mongo_found_count}개")
    logger.info(f"   - 실제 HTML 추출 성공: {html_extracted_count}개")

    return titles, texts, urls, dates, htmls, content_types, sources, image_urls, attachment_urls, attachment_types


# 캐싱 데이터 초기화 함수

def initialize_cache():
    """
    캐시 초기화 함수 (Redis Fast Track 적용)
    - Redis 캐시가 있으면 3초 로딩
    - 없으면 Pinecone에서 다운로드 후 Redis에 저장 (20분 소요, 최초 1회만)
    """
    try:
        logger.info("🔄 캐시 초기화 시작...")

        # ==========================================
        # 1. Redis 캐시 확인 (Fast Track)
        # ==========================================
        if storage.redis_client is not None:
            try:
                logger.info("🔍 Redis 캐시 확인 중...")
                cached_data = storage.redis_client.get('pinecone_metadata')

                if cached_data:
                    logger.info("🚀 Redis 캐시 발견! 빠른 로딩을 시작합니다...")

                    # Pickle로 저장된 데이터 복원
                    (storage.cached_titles, storage.cached_texts, storage.cached_urls, storage.cached_dates,
                     storage.cached_htmls, storage.cached_content_types, storage.cached_sources,
                     storage.cached_image_urls, storage.cached_attachment_urls, storage.cached_attachment_types) = pickle.loads(cached_data)

                    logger.info(f"✅ Redis 로드 완료! ({len(storage.cached_titles)}개 문서, Pinecone 다운로드 생략)")
                    logger.info(f"   - HTML 구조 있는 문서: {sum(1 for html in storage.cached_htmls if html)}개")
                    logger.info(f"   - 이미지 OCR 문서: {sum(1 for ct in storage.cached_content_types if ct == 'image')}개")
                    logger.info(f"   - 첨부파일 문서: {sum(1 for ct in storage.cached_content_types if ct == 'attachment')}개")

                    # Retriever 초기화로 점프 (Pinecone Fetch 생략!)
                    _initialize_retrievers()
                    logger.info(f"✅ 캐시 초기화 완료! (titles: {len(storage.cached_titles)}, texts: {len(storage.cached_texts)})")
                    return
                else:
                    logger.info("⬇️  Redis에 캐시가 없습니다. Pinecone 다운로드를 시작합니다...")

            except Exception as e:
                logger.warning(f"⚠️  Redis 로드 실패 (Pinecone에서 새로 다운로드합니다): {e}")

        # ==========================================
        # 2. Pinecone에서 데이터 가져오기 (Slow Track)
        # ==========================================
        logger.info("⏳ Pinecone 전체 데이터 다운로드 시작 (최초 1회, 약 20분 소요)...")
        (storage.cached_titles, storage.cached_texts, storage.cached_urls, storage.cached_dates,
         storage.cached_htmls, storage.cached_content_types, storage.cached_sources,
         storage.cached_image_urls, storage.cached_attachment_urls, storage.cached_attachment_types) = fetch_titles_from_pinecone()
        logger.info(f"✅ Pinecone에서 {len(storage.cached_titles)}개 문서 메타데이터를 가져왔습니다.")
        logger.info(f"   - HTML 구조 있는 문서: {sum(1 for html in storage.cached_htmls if html)}개")
        logger.info(f"   - 이미지 OCR 문서: {sum(1 for ct in storage.cached_content_types if ct == 'image')}개")
        logger.info(f"   - 첨부파일 문서: {sum(1 for ct in storage.cached_content_types if ct == 'attachment')}개")

        # ==========================================
        # 3. Redis에 저장 (다음 재시작을 위해)
        # ==========================================
        if storage.redis_client is not None:
            try:
                cache_data = (
                    storage.cached_titles, storage.cached_texts, storage.cached_urls, storage.cached_dates,
                    storage.cached_htmls, storage.cached_content_types, storage.cached_sources,
                    storage.cached_image_urls, storage.cached_attachment_urls, storage.cached_attachment_types
                )
                # 24시간 유효 (86400초)
                storage.redis_client.setex('pinecone_metadata', 86400, pickle.dumps(cache_data))
                logger.info("💾 데이터를 Redis에 저장했습니다. (다음 재시작부터는 3초 로딩!)")
            except Exception as e:
                logger.warning(f"⚠️  Redis 저장 실패 (메모리 캐시만 사용): {e}")
        else:
            logger.warning("⚠️  Redis 미사용 (메모리 캐시만 사용)")

        # Retriever 초기화
        _initialize_retrievers()
        logger.info(f"✅ 캐시 초기화 완료! (titles: {len(storage.cached_titles)}, texts: {len(storage.cached_texts)})")

    except Exception as e:
        logger.error(f"❌ 캐시 초기화 실패: {e}", exc_info=True)
        # 에러가 발생해도 빈 리스트로 초기화하여 앱이 크래시하지 않도록 함
        storage.cached_titles = []
        storage.cached_texts = []
        storage.cached_urls = []
        storage.cached_dates = []
        storage.cached_htmls = []
        storage.cached_content_types = []
        storage.cached_sources = []
        storage.cached_image_urls = []
        storage.cached_attachment_urls = []
        storage.cached_attachment_types = []
        logger.warning("⚠️  캐시를 빈 상태로 초기화했습니다.")


def _initialize_retrievers():
    """Retriever 초기화 로직 (중복 제거를 위한 분리)"""
    logger.info("🔧 검색 엔진(BM25/Dense) 구축 중...")

    from modules.retrieval import (
        BM25Retriever,
        DenseRetriever,
        DocumentCombiner,
        DocumentClusterer
    )

    # BM25Retriever 초기화 (HTML 데이터 포함, Redis 캐싱)
    bm25_retriever = BM25Retriever(
        titles=storage.cached_titles,
        texts=storage.cached_texts,
        urls=storage.cached_urls,
        dates=storage.cached_dates,
        query_transformer=transformed_query,
        similarity_adjuster=adjust_similarity_scores,
        htmls=storage.cached_htmls,  # HTML 구조화 데이터 추가
        k1=ml_config.bm25.k1,
        b=ml_config.bm25.b,
        redis_client=storage.redis_client  # Redis 캐싱 활성화
    )
    storage.set_bm25_retriever(bm25_retriever)

    # DenseRetriever 초기화
    dense_retriever = DenseRetriever(
        embeddings_factory=get_embeddings,
        pinecone_index=storage.pinecone_index,
        date_adjuster=adjust_date_similarity,
        similarity_scale=ml_config.dense_retrieval.similarity_scale,
        noun_weight=ml_config.dense_retrieval.noun_weight,
        digit_weight=ml_config.dense_retrieval.digit_weight
    )
    storage.set_dense_retriever(dense_retriever)

    # DocumentCombiner 초기화
    document_combiner = DocumentCombiner(
        keyword_filter=last_filter_keyword,
        date_adjuster=adjust_date_similarity
    )
    storage.set_document_combiner(document_combiner)

    # DocumentClusterer 초기화
    document_clusterer = DocumentClusterer(
        date_parser=parse_date_change_korea_time,
        similarity_threshold=ml_config.clustering.similarity_threshold
    )
    storage.set_document_clusterer(document_clusterer)

    logger.info("✅ 모든 검색 엔진 초기화 완료!")

                    #################################   24.11.16기준 정확도 측정완료 #####################################################
######################################################################################################################

# 날짜를 파싱하는 함수 (하위 호환성 유지)
# 이제는 utils.date_utils.parse_date_change_korea_time 사용 권장

def calculate_weight_by_days_difference(post_date, current_date, query_nouns):

    # 날짜 차이 계산 (일 단위)
    days_diff = (current_date - post_date).days

    # 기준 날짜 (24-01-01 00:00) 설정
    baseline_date_str = "24-01-01 00:00"
    baseline_date = parse_date_change_korea_time(baseline_date_str)
    graduate_weight = 1.0 if any(keyword in query_nouns for keyword in ['졸업', '인터뷰']) else 0
    scholar_weight = 1.0 if '장학' in query_nouns else 0
    # 작성일이 기준 날짜 이전이면 가중치를 1.35로 고정
    if post_date <= baseline_date:
        return 1.35 + graduate_weight / 5

    # '최근', '최신' 등의 키워드가 있는 경우, 최근 가중치를 추가
    add_recent_weight = 1.5 if any(keyword in query_nouns for keyword in ['최근', '최신', '지금', '현재']) else 0

    # **10일 단위 구분**: 최근 문서에 대한 세밀한 가중치 부여
    if days_diff <= 6:
        return 1.355 + add_recent_weight + graduate_weight + scholar_weight
    elif days_diff <= 12:
        return 1.330 + add_recent_weight / 3.0 + graduate_weight / 1.2 + scholar_weight / 1.5
    elif days_diff <= 18:
        return 1.321 + add_recent_weight / 5.0 + graduate_weight / 1.3 + scholar_weight / 2.0
    elif days_diff <= 24:
        return 1.310 + add_recent_weight / 7.0 + graduate_weight / 1.4 + scholar_weight / 2.5
    elif days_diff <= 30:
        return 1.290 + add_recent_weight / 9.0 + graduate_weight / 1.5 + scholar_weight / 3.0
    elif days_diff <= 36:
        return 1.270 + graduate_weight / 1.6 + scholar_weight / 3.5
    elif days_diff <= 45:
        return 1.250 +graduate_weight / 1.7 + scholar_weight / 4.0
    elif days_diff <= 60:
        return 1.230 +graduate_weight / 1.8 + scholar_weight / 4.5
    elif days_diff <= 90:
        return 1.210 +graduate_weight / 2.0 + scholar_weight / 5.0

    # **월 단위 구분**: 2개월 이후는 월 단위로 단순화
    month_diff = (days_diff - 90) // 30
    month_weight_map = {
        0: 1.19,
        1: 1.17 - add_recent_weight / 6 - scholar_weight / 10,
        2: 1.15 - add_recent_weight / 5 - scholar_weight / 9,
        3: 1.13 - add_recent_weight / 4 - scholar_weight / 7,
        4: 1.11 - add_recent_weight / 3  - scholar_weight / 5,
    }

    # 기본 가중치 반환 (6개월 이후)
    return month_weight_map.get(month_diff, 0.88 - add_recent_weight /2  - scholar_weight / 5)


# 유사도를 조정하는 함수

def adjust_date_similarity(similarity, date_str,query_nouns):
    # 현재 한국 시간
    current_time = get_korean_time()
    # 작성일 파싱
    post_date = parse_date_change_korea_time(date_str)
    # 가중치 계산
    weight = calculate_weight_by_days_difference(post_date, current_time,query_nouns)
    # 조정된 유사도 반환
    return similarity * weight

# 사용자 질문에서 추출한 명사와 각 문서 제목에 대한 유사도를 조정하는 함수
# (이전 버전은 삭제되었습니다 - 최적화된 버전만 유지)

def adjust_similarity_scores(query_noun, title, texts, similarities):
    query_noun_set = set(query_noun)
    title_tokens = [set(titl.split()) for titl in title]

    for idx, titl_tokens in enumerate(title_tokens):
        matching_noun = query_noun_set.intersection(titl_tokens)
        
        if texts[idx] == "No content":
            similarities[idx] *= 1.5
            if "국가장학금" in query_noun_set and "국가장학금" in titl_tokens:
                similarities[idx] *= 5.0
        
        for noun in matching_noun:
            len_adjustment = len(noun) * 0.21
            similarities[idx] += len_adjustment
            if re.search(r'\d', noun):  # 숫자 포함 여부
                similarities[idx] += len(noun) * (0.22 if noun in titl_tokens else 0.19)

        if query_noun_set.intersection({'대학원', '대학원생'}) and titl_tokens.intersection({'대학원', '대학원생'}):
            similarities[idx] += 2.0
        if not query_noun_set.intersection({'대학원', '대학원생'}) and '대학원' in titl_tokens:
            similarities[idx] -= 2.0

    return similarities


#############################################################################################

# 키워드 필터링 함수 (리팩토링됨 - KeywordFilter 사용)
def last_filter_keyword(DOCS, query_noun, user_question):
    """
    키워드 기반 문서 필터링

    Args:
        DOCS: 문서 리스트 [(score, title, date, text, url), ...]
        query_noun: 검색 질문의 명사 리스트
        user_question: 원본 질문

    Returns:
        List[Tuple]: 필터링된 문서 리스트 (유사도 조정됨)
    """
    return storage.keyword_filter.filter(DOCS, query_noun, user_question)

#################################################################################################

########################################################################################  best_docs 시작 ##########################################################################################

def parse_temporal_intent(query, current_date=None):
    """
    질문에서 시간 표현을 감지하고 필터 조건을 반환합니다.

    Args:
        query: 사용자 질문
        current_date: 현재 날짜 (기본값: 현재 시각)

    Returns:
        dict: {"year": int, "semester": int, "date_from": datetime} 또는 None
    """
    from datetime import datetime

    if current_date is None:
        current_date = datetime.now()

    current_year = current_date.year
    current_month = current_date.month

    # 한국 학기 계산: 1학기(3-8월), 2학기(9-2월)
    # 단, 1-2월은 전년도 2학기로 간주
    if 3 <= current_month <= 8:
        current_semester = 1
    else:  # 9-12월 또는 1-2월
        current_semester = 2
        if current_month <= 2:
            current_year -= 1  # 1-2월은 전년도 2학기

    # 1단계: 간단한 시간 표현은 규칙으로 처리 (빠르고 비용 0)
    simple_temporal_keywords = {
        '이번학기': {'year': current_year, 'semester': current_semester},
        '이번 학기': {'year': current_year, 'semester': current_semester},
        '이번학년': {'year': current_year, 'semester': current_semester},
        '이번 학년': {'year': current_year, 'semester': current_semester},
        '올해': {'year': current_year},
        '금년': {'year': current_year},
        '최근': {'year_from': current_year - 1},  # 최근 1년
    }

    for keyword, time_filter in simple_temporal_keywords.items():
        if keyword in query:
            logger.info(f"⏰ 시간 표현 감지 (규칙): '{keyword}' → {time_filter}")
            return time_filter

    # 2단계: 모든 질문을 LLM으로 분석 (시간 의도 파악)
    # 키워드 체크 제거 → 모든 질문에서 시간 의도 감지
    # 예: "인턴십 있어?" → 암묵적으로 현재 진행중인 것을 묻는 것
    logger.info(f"🤔 LLM으로 시간 의도 분석 중...")
    llm_filter = rewrite_query_with_llm(query, current_date)
    if llm_filter:
        logger.info(f"✨ LLM 분석 결과: {llm_filter}")
        return llm_filter

    return None


def rewrite_query_with_llm(query, current_date):
    """
    LLM을 사용해 복잡한 시간 표현을 해석하고 필터 조건을 생성합니다.

    Args:
        query: 사용자 질문
        current_date: 현재 날짜

    Returns:
        dict: {"year": int, "semester": int} 또는 None
    """
    from datetime import datetime
    import json

    current_year = current_date.year
    current_month = current_date.month

    # 현재 학기 계산
    if 3 <= current_month <= 8:
        current_semester = 1
    else:
        current_semester = 2
        if current_month <= 2:
            current_year -= 1

    # 프롬프트 템플릿 로드
    prompt_template = get_temporal_intent_prompt()

    # 동적 값 계산
    prev_year = current_year if current_semester == 2 else current_year - 1
    prev_semester = 2 if current_semester == 1 else 1
    last_year = current_year - 1

    # 프롬프트 포맷팅
    prompt = prompt_template.format(
        current_date=current_date.strftime('%Y년 %m월 %d일'),
        current_semester=f"{current_year}학년도 {current_semester}학기",
        query=query,
        prev_year=prev_year,
        prev_semester=prev_semester,
        last_year=last_year
    )

    try:
        llm = ChatUpstage(api_key=storage.upstage_api_key, model="solar-mini")
        response = llm.invoke(prompt)

        # JSON 파싱
        result = json.loads(response.content.strip())

        # 로그: LLM 응답 JSON 전체
        logger.info(f"   📋 LLM 응답 JSON: {json.dumps(result, ensure_ascii=False)}")

        # 로그: LLM 추론 과정
        logger.info(f"   💬 LLM 시간 분석: {result.get('reasoning', '')}")

        # ✅ 새로운 필드 추출
        is_ongoing = result.get('is_ongoing', False)
        is_policy = result.get('is_policy', False)
        year = result.get('year')
        semester = result.get('semester')

        # 필터 조건 생성
        if is_ongoing:
            # "진행중" 의도 감지
            logger.info(f"   🎯 '진행중' 의도 감지됨 (is_ongoing=true)")
            return {
                'type': 'ongoing',
                'is_ongoing': True,
                'is_policy': is_policy
            }

        elif year is not None and semester is not None:
            # 학기 필터 (기존 로직 유지)
            logger.info(f"   📅 학기 필터: {year}학년도 {semester}학기")
            return {
                'year': year,
                'semester': semester,
                'is_ongoing': False,
                'is_policy': is_policy
            }

        elif is_policy:
            # 정책 질문 (시간 무관)
            logger.info(f"   📜 정책 질문 감지 (시간 필터 비활성화)")
            return {
                'type': 'policy',
                'is_policy': True,
                'is_ongoing': False
            }

        else:
            # 시간 표현 없음
            logger.debug(f"   ℹ️  시간 표현 없음")
            return None

    except Exception as e:
        logger.warning(f"⚠️  LLM 시간 파싱 실패 (규칙 기반으로 폴백): {e}")
        return None


def best_docs(user_question):
      # 사용자 질문
      noun_time=time.time()
      query_noun=transformed_query(user_question)
      query_noun_time=time.time()-noun_time
      print(f"명사화 변환 시간 : {query_noun_time}")
      titles_from_pinecone, texts_from_pinecone, urls_from_pinecone, dates_from_pinecone = storage.cached_titles, storage.cached_texts, storage.cached_urls, storage.cached_dates
      if not query_noun:
        return None,None
      #######  최근 공지사항, 채용, 세미나, 행사, 특강의 단순한 정보를 요구하는 경우를 필터링 하기 위한 매커니즘 ########
      remove_noticement = ['목록','리스트','내용','제일','가장','공고', '공지사항','필독','첨부파일','수업','업데이트',
                           '컴퓨터학부','컴학','상위','정보','관련','세미나','행사','특강','강연','공지사항','채용','공고','최근','최신','지금','현재']
      query_nouns = [noun for noun in query_noun if noun not in remove_noticement]
      return_docs=[]
      key=None
      numbers=5 ## 기본으로 5개 문서 반환할 것.
      check_num=0
      recent_time=time.time()
      for noun in query_nouns:
        if '개' in noun:
            # 숫자 추출
            num = re.findall(r'\d+', noun)
            if num:
                numbers=int(num[0])
                check_num=1
      if (any(keyword in query_noun for keyword in ['세미나','행사','특강','강연','공지사항','채용','공고'])and any(keyword in query_noun for keyword in ['최근','최신','지금','현재'])and len(query_nouns)<1 or check_num==1):    
        if numbers ==0:
          #### 0개의 keyword에 대해서 질문한다면? ex) 가장 최근 공지사항 0개 알려줘######
          keys=['세미나','행사','특강','강연','공지사항','채용']
          return None,[keyword for keyword in keys if keyword in user_question]
        if '공지사항' in query_noun:
          key=['공지사항']
          notice_url = NOTICE_BASE_URL + "&wr_id="
          return_docs=find_url(notice_url,titles_from_pinecone,dates_from_pinecone,texts_from_pinecone,urls_from_pinecone,numbers)
        if '채용' in query_noun:
          key=['채용']
          company_url = COMPANY_BASE_URL + "&wr_id="
          return_docs=find_url(company_url,titles_from_pinecone,dates_from_pinecone,texts_from_pinecone,urls_from_pinecone,numbers)
        other_key = ['세미나', '행사', '특강', '강연']
        if any(keyword in query_noun for keyword in other_key):
          seminar_url = SEMINAR_BASE_URL + "&wr_id="
          key = [keyword for keyword in other_key if keyword in user_question]
          return_docs=find_url(seminar_url,titles_from_pinecone,dates_from_pinecone,texts_from_pinecone,urls_from_pinecone,numbers)
        recent_finish_time=time.time()-recent_time
        print(f"최근 공지사항 문서 뽑는 시간 {recent_finish_time}")
        if (len(return_docs)>0):
          return return_docs,key


      remove_noticement = ['제일','가장','공고', '공지사항','필독','첨부파일','수업','컴학','상위','관련']

      # BM25 검색 (리팩토링됨 - BM25Retriever 사용)
      bm_title_time = time.time()
      Bm25_best_docs, adjusted_similarities = storage.bm25_retriever.search(
          query_nouns=query_noun,
          top_k=50,  # ✨ 25→50 증가: URL 중복 제거 위한 후보군 확대
          normalize_factor=24.0
      )
      bm_title_f_time = time.time() - bm_title_time
      print(f"bm25 문서 뽑는시간: {bm_title_f_time}")
      ####################################################################################################
      # Dense Retrieval (리팩토링됨 - DenseRetriever 사용)
      dense_time = time.time()
      combine_dense_docs = storage.dense_retriever.search(
          user_question=user_question,
          query_nouns=query_noun,
          top_k=50  # ✨ 30→50 증가: URL 중복 제거 위한 후보군 확대
      )
      pinecone_time = time.time() - dense_time
      print(f"파인콘에서 top k 뽑는데 걸리는 시간 {pinecone_time}")

      # ## 결과 출력
      # print("\n통합된 파인콘문서 유사도:")
      # for score, doc in combine_dense_docs:
      #     title, date, text, url = doc
      #     print(f"제목: {title}\n유사도: {score} {url}")
      #     print('---------------------------------')


      #################################################3#################################################3
      #####################################################################################################3

      # BM25와 Dense Retrieval 결과 결합 (리팩토링됨 - DocumentCombiner 사용)
      combine_time = time.time()
      final_best_docs = storage.document_combiner.combine(
          dense_results=combine_dense_docs,
          bm25_results=Bm25_best_docs,
          bm25_similarities=adjusted_similarities,
          titles_from_pinecone=titles_from_pinecone,
          query_nouns=query_noun,
          user_question=user_question,
          top_k=30  # ✨ 20→30 증가: URL 중복 제거 전 후보군 확대
      )
      combine_f_time = time.time() - combine_time
      print(f"Bm25랑 pinecone 결합 시간: {combine_f_time}")

      # ✅ 날짜 부스팅 (Recency Boost) - 시간 표현 없어도 최신 문서 우선!
      # 사용자 지적: "시간 맥락 없으면 당연히 최신순으로"
      from datetime import datetime

      def calculate_recency_boost(doc_date_str):
          """문서 날짜에 따른 가중치 계산 (최신 문서 우선)"""
          try:
              current_date = datetime.now()
              doc_date = datetime.fromisoformat(doc_date_str.replace('+09:00', ''))

              # 날짜 차이 계산 (일 단위)
              days_old = (current_date - doc_date).days

              # 가중치 계산
              if days_old < 0:  # 미래 날짜 (오류)
                  return 1.0
              elif days_old <= 180:  # 6개월 이내 (이번학기/저번학기)
                  return 1.5  # 50% 부스팅
              elif days_old <= 365:  # 1년 이내 (작년)
                  return 1.3  # 30% 부스팅
              elif days_old <= 730:  # 2년 이내
                  return 1.1  # 10% 부스팅
              else:  # 2년 이상
                  return 0.9  # 10% 패널티

          except Exception as e:
              logger.debug(f"날짜 부스팅 계산 실패: {doc_date_str} - {e}")
              return 1.0  # 실패 시 중립

      # 결합된 결과에 날짜 부스팅 적용
      boosted_docs = []
      for score, title, date, text, url in final_best_docs:
          boost = calculate_recency_boost(date)
          boosted_score = score * boost
          boosted_docs.append((boosted_score, title, date, text, url))

      # 부스팅된 점수로 재정렬
      boosted_docs.sort(key=lambda x: x[0], reverse=True)
      final_best_docs = boosted_docs

      logger.info(f"🚀 날짜 부스팅 완료 (최신 문서 우선: 6개월 이내 +50%, 1년 이내 +30%)")

      # ✨ URL 기반 중복 제거 (같은 게시글의 서로 다른 청크 제거)
      # 목적: 검색 결과 다양성 확보 (Top N이 모두 서로 다른 게시글이 되도록)
      # 전략: 같은 URL(게시글)에서 최고 점수 청크만 선택
      # 효과:
      #   - BGE-Reranker 효율성 향상 (서로 다른 문서 재정렬)
      #   - 로그 가독성 향상 (다양성 지표 개선)
      #   - 향후 확장 대비 (복수 답변, 관련 문서 추천 등)
      dedup_time = time.time()

      seen_urls = {}  # {url: (score, title, date, text, url)}
      deduplicated_docs = []
      duplicate_count = 0
      original_count = len(final_best_docs)

      for score, title, date, text, url in final_best_docs:
          if url in seen_urls:
              # 같은 URL이 이미 있음 → 점수 비교
              existing_score = seen_urls[url][0]

              if score > existing_score:
                  # 더 높은 점수면 기존 문서 제거하고 새 문서 추가
                  deduplicated_docs.remove(seen_urls[url])
                  deduplicated_docs.append((score, title, date, text, url))
                  seen_urls[url] = (score, title, date, text, url)
                  logger.debug(f"🔄 URL 중복 - 더 높은 점수로 교체: {title[:30]}... ({existing_score:.2f} → {score:.2f})")
              else:
                  # 낮은 점수면 무시
                  duplicate_count += 1
                  logger.debug(f"⏭️  URL 중복 제거: {title[:30]}... (점수: {score:.2f} < {existing_score:.2f})")
          else:
              # 새 URL이면 추가
              seen_urls[url] = (score, title, date, text, url)
              deduplicated_docs.append((score, title, date, text, url))

      # 점수순 재정렬 후 Top 20
      deduplicated_docs.sort(key=lambda x: x[0], reverse=True)
      final_best_docs = deduplicated_docs[:20]

      dedup_f_time = time.time() - dedup_time
      unique_urls = len(seen_urls)
      print(f"URL 중복 제거: {dedup_f_time:.4f}초 (원본: {original_count}개 → 중복 {duplicate_count}개 제거 → 최종: {len(final_best_docs)}개 서로 다른 게시글, 고유 URL {unique_urls}개)")

      # 클러스터링 제거: URL 중복 제거만으로 충분 (각 게시글당 대표 청크 1개 선택 완료)
      # get_ai_message()에서 최종 선택된 문서의 전체 청크를 다시 수집하므로 클러스터링 불필요
      return final_best_docs, query_noun

# QA 프롬프트 템플릿 로드 (전역 변수)
_qa_prompt_template = None

def get_qa_prompt_template():
    """QA 프롬프트 PromptTemplate 객체 반환 (Lazy loading)"""
    global _qa_prompt_template
    if _qa_prompt_template is None:
        prompt_text = get_qa_prompt()
        _qa_prompt_template = PromptTemplate(
            template=prompt_text,
            input_variables=["current_time", "temporal_intent", "context", "question"]
        )
    return _qa_prompt_template

# PromptTemplate 객체 (하위 호환성 유지)
PROMPT = get_qa_prompt_template()


def get_answer_from_chain(best_docs, user_question, query_noun, temporal_filter=None):

    # ✅ HTML(Markdown) 중복 제거 - 비싼 Upstage API 결과 최대 활용!
    # 같은 이미지의 여러 청크가 모두 같은 Markdown을 가지므로 첫 번째만 사용
    seen_htmls = set()
    deduplicated_docs = []
    duplicate_html_count = 0

    # 디버깅: 중복 제거 전 문서 목록
    logger.info(f"   📦 중복 제거 전: {len(best_docs)}개 청크")
    for i, doc in enumerate(best_docs[:10]):  # 처음 10개만
        source = doc[7] if len(doc) > 7 else "unknown"
        html_len = len(doc[5]) if len(doc) > 5 and doc[5] else 0
        text_len = len(doc[3])
        logger.info(f"      [{i+1}] {source}: text={text_len}자, html={html_len}자")

    for doc in best_docs:
        html = doc[5] if len(doc) > 5 else ""

        # HTML이 있고 이미 본 적 있으면 스킵 (중복 Markdown 제거)
        if html and html in seen_htmls:
            duplicate_html_count += 1
            continue

        # 새로운 HTML이거나 HTML이 없으면 추가
        if html:
            seen_htmls.add(html)
        deduplicated_docs.append(doc)

    logger.info(f"   🔄 중복 제거 후: {len(deduplicated_docs)}개 청크 ({duplicate_html_count}개 Markdown 중복 제거)")
    if duplicate_html_count > 0:
        logger.info(f"      💡 고유 Markdown: {len(seen_htmls)}개 (Upstage API 결과 효율적 활용)")

    # ✅ best_docs에서 메타데이터 직접 추출 (URL로 다시 찾지 않음)
    documents = []
    markdown_used = 0
    html_converted = 0
    text_fallback = 0

    for doc in deduplicated_docs:
        score = doc[0]
        title = doc[1]
        date = doc[2]
        text = doc[3]
        url = doc[4]
        # ✅ 메타데이터를 tuple에서 직접 가져옴 (버그 수정!)
        html = doc[5] if len(doc) > 5 else ""
        content_type = doc[6] if len(doc) > 6 else "text"
        source = doc[7] if len(doc) > 7 else "original_post"
        attachment_type = doc[8] if len(doc) > 8 else ""

        # HTML/Markdown 우선 사용 (표 구조 보존), 없으면 text 사용
        if html:
            from utils.html_parser import is_markdown, html_to_markdown_with_text

            # Markdown 형식 감지 (Upstage API 제공, 고품질 표 구조)
            # 이미 Markdown이면 그대로 사용 (토큰 효율적, LLM 최적화)
            if is_markdown(html):
                # ① Markdown 표 형식 (Upstage API 결과)
                page_content = html
                markdown_used += 1
            else:
                # ② HTML → Markdown 변환 (fallback)
                page_content = html_to_markdown_with_text(html)

                # 내용이 없으면 원본 text 사용
                if not page_content:
                    page_content = text
                    text_fallback += 1
                else:
                    html_converted += 1
        else:
            # ③ html 없음 → text 사용
            page_content = text
            text_fallback += 1

        # 날짜 파싱 (ISO 8601과 레거시 형식 모두 지원)
        try:
            if date.startswith("작성일"):
                doc_date = datetime.strptime(date, '작성일%y-%m-%d %H:%M')
            else:
                doc_date = datetime.fromisoformat(date)
        except:
            doc_date = datetime.now()

        # Document 객체 생성 (멀티모달 메타데이터 포함)
        doc = Document(
            page_content=page_content,  # HTML 우선, 없으면 text
            metadata={
                "title": title,
                "url": url,
                "doc_date": doc_date,
                "content_type": content_type,
                "source": source,
                "attachment_type": attachment_type,
                "plain_text": text  # 원본 텍스트도 보관
            }
        )
        documents.append(doc)

    # 폴백 통계 로그
    logger.info(f"   📊 콘텐츠 소스 통계:")
    logger.info(f"      ① Markdown (Upstage API): {markdown_used}개")
    logger.info(f"      ② HTML → Markdown 변환: {html_converted}개")
    logger.info(f"      ③ Text 폴백: {text_fallback}개")
    logger.info(f"      총 {len(documents)}개 문서 생성")

    # ✅ 개선된 필터링: 같은 게시글의 모든 청크 vs 키워드 필터링
    # 핵심 개선: 같은 게시글에서 수집된 청크들은 이미 BM25 + Dense + Reranker로 검증됨
    # → 키워드 필터링으로 중요 정보(이름, 학번 등)를 담은 청크가 제거되는 문제 해결

    # 모든 문서가 같은 게시글인지 확인 (제목 기준)
    unique_titles = set(doc.metadata.get('title', '') for doc in documents)

    if len(unique_titles) == 1:
        # ✅ 같은 게시글의 청크들 → 모두 포함 (키워드 필터링 스킵)
        # 이유: 이미 멀티스테이지 검색(BM25 + Dense + Reranker)으로 최적 게시글 선정 완료
        # 해당 게시글의 모든 정보(본문, 이미지 OCR, 첨부파일)를 LLM에 전달해야 완전한 답변 가능
        logger.info(f"   ✅ 같은 게시글 청크 감지 → 키워드 필터링 스킵 ({len(documents)}개 모두 포함)")
        relevant_docs = documents
    else:
        # ❌ 여러 게시글 혼재 → 키워드 필터링 적용
        logger.info(f"   🔍 여러 게시글 혼재 ({len(unique_titles)}개) → 키워드 필터링 적용")
        relevant_docs = [
            doc for doc in documents if
            any(keyword in doc.page_content for keyword in query_noun) or  # 키워드 매칭
            doc.metadata.get('source') in ['image_ocr', 'document_parse']  # 멀티모달 항상 포함
        ]

    if not relevant_docs:
      return None, None, None

    # 🔍 디버깅: 각 청크의 내용 길이 확인 (데이터 누락 검증)
    logger.info(f"   📋 LLM에 전달될 청크 상세:")
    for i, doc in enumerate(relevant_docs):
        source = doc.metadata.get('source', 'unknown')
        content_len = len(doc.page_content)
        logger.info(f"      청크{i+1}: [{source}] {content_len}자")

    # LLM 초기화 (명단 질문을 위한 충분한 max_tokens 설정)
    llm = ChatUpstage(
        api_key=storage.upstage_api_key,
        max_tokens=4096  # 긴 명단도 완전히 나열할 수 있도록 충분한 토큰 확보
    )
    relevant_docs_content=format_docs(relevant_docs)

    # 🔍 디버깅: 전체 context 크기 및 내용 확인
    logger.info(f"   📊 전체 Context 크기: {len(relevant_docs_content)}자")
    logger.info(f"   📄 실제 전달되는 Context 요약 (각 청크당 앞 100자 + 뒤 100자):")
    logger.info(f"{'='*80}")

    # 각 청크를 "\n\n문서 제목:"으로 분리
    chunks = relevant_docs_content.split('\n\n문서 제목:')
    for i, chunk in enumerate(chunks):
        if i > 0:  # 첫 번째는 빈 문자열이므로 스킵
            chunk = '문서 제목:' + chunk  # 분리 시 제거된 부분 복원

        chunk_len = len(chunk)

        if chunk_len <= 200:
            # 200자 이하면 전체 출력
            logger.info(chunk)
        else:
            # 앞 100자 + ... + 뒤 100자
            preview = chunk[:100] + f'... ({chunk_len - 200}자 생략) ...' + chunk[-100:]
            logger.info(preview)

        if i < len(chunks) - 1:
            logger.info('')  # 청크 구분용 빈 줄

    logger.info(f"{'='*80}")

    qa_chain = (
        {
            "current_time": lambda _: get_korean_time().strftime("%Y년 %m월 %d일 %H시 %M분"),
            "temporal_intent": lambda _: format_temporal_intent(temporal_filter),
            "context": RunnableLambda(lambda _: relevant_docs_content),
            "question": RunnablePassthrough()
        }
        | PROMPT
        | llm
        | StrOutputParser()
    )

    return qa_chain, relevant_docs, relevant_docs_content



#######################################################################

##### 유사도 제목 날짜 본문  url image_url순으로 저장됨

def get_ai_message(question):
    s_time=time.time()

    # 검색된 문서 정보 로깅 (가장 먼저!)
    logger.info(f"📝 사용자 질문: {question}")

    # ✅ 시간 의도 파싱 (LLM 답변 시 활용)
    from datetime import datetime
    temporal_filter = parse_temporal_intent(question, datetime.now())

    best_time=time.time()
    top_doc, query_noun = best_docs(question)  # 가장 유사한 문서 가져오기
    best_f_time=time.time()-best_time
    print(f"best_docs 뽑는 시간:{best_f_time}")
    logger.info(f"🔍 추출된 키워드: {query_noun}")

    # query_noun이 없거나 top_doc이 비어있는 경우 처리
    if not query_noun or not top_doc or len(top_doc) == 0:
        notice_url = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1"
        not_in_notices_response = {
            "answer": "해당 질문은 공지사항에 없는 내용입니다.\n 자세한 사항은 공지사항을 살펴봐주세요.",
            "answerable": False,  # 검색 결과 없음
            "references": notice_url,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": ["No content"]
        }
        return not_in_notices_response
    if len(query_noun)==1 and any(keyword in query_noun for keyword in ['채용','공지사항','세미나','행사','강연','특강']):
      seen_urls = set()  # 이미 본 URL을 추적하기 위한 집합
      response = f"'{query_noun[0]}'에 대한 정보 목록입니다:\n\n"
      show_url=""
      if top_doc !=None:
        for title, date, _, url in top_doc:  # top_doc에서 제목, 날짜, URL 추출
            if url not in seen_urls:
                response += f"제목: {title}, 날짜: {date} \n----------------------------------------------------\n"
                seen_urls.add(url)  # URL 추가하여 중복 방지
      if '채용' in query_noun:
        show_url = COMPANY_BASE_URL + "&wr_id="
      elif '공지사항' in query_noun:
        show_url = NOTICE_BASE_URL + "&wr_id="
      else:
        show_url = SEMINAR_BASE_URL + "&wr_id="

      # 최종 data 구조 생성
      data = {
        "answer": response,
        "answerable": True,  # 목록 제공 성공
        "references": show_url,  # show_url을 넘기기
        "disclaimer": "\n\n항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL을 참고하여 정확하고 자세한 정보를 확인하세요.",
        "images": ["No content"]
      }
      f_time=time.time()-s_time
      print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
      return data
    top_docs = [list(doc) for doc in top_doc]

    # ✅ Reranking 전 Top 5 로깅
    logger.info("=" * 60)
    logger.info(f"📊 Reranking 전 검색 결과 Top {min(5, len(top_docs))}:")
    for i, doc in enumerate(top_docs[:5]):
        score, title, date, text, url = doc[:5]
        logger.info(f"   {i+1}위: [{score:.4f}] {title[:50]}... ({date})")
    logger.info("=" * 60)

    # ✅ BGE-Reranker로 문서 재순위화 (관련성 기준)
    reranking_used = False  # Reranking 사용 여부 추적
    if storage.reranker and len(top_docs) > 1:
        logger.info("🎯 BGE-Reranker 활성화!")
        rerank_time = time.time()
        logger.info(f"   입력: {len(top_docs)}개 문서 → Reranking 시작...")

        # Reranker는 tuple 리스트를 기대하므로 변환
        top_docs_tuples = [tuple(doc) for doc in top_docs]

        # Reranking (어차피 1등만 사용하므로 Top 5로 압축)
        reranked_docs_tuples = storage.reranker.rerank(
            query=question,
            documents=top_docs_tuples,
            top_k=5  # 최대 5개로 압축 (1등만 사용하므로 효율화)
        )

        # 다시 리스트로 변환
        top_docs = [list(doc) for doc in reranked_docs_tuples]
        reranking_used = True  # Reranking 사용됨

        rerank_f_time = time.time() - rerank_time
        logger.info(f"   출력: {len(top_docs)}개 문서 (처리 시간: {rerank_f_time:.2f}초)")
        print(f"✅ Reranking 완료: {rerank_f_time:.2f}초")
    elif not storage.reranker:
        logger.info("⏭️  BGE-Reranker 비활성화 (미설치 또는 로딩 실패)")
        logger.info("   → 원본 검색 순서 유지")
    elif len(top_docs) <= 1:
        logger.info("⏭️  BGE-Reranker 스킵 (문서 1개 이하)")
        logger.info("   → Reranking 불필요")

    # ✅ Reranking 후 Top 5 로깅
    logger.info("=" * 60)
    logger.info(f"🔝 Reranking 후 최종 결과 Top {min(5, len(top_docs))}:")
    seen_urls = set()
    unique_url_count = 0
    for i, doc in enumerate(top_docs[:5]):
        score, title, date, text, url = doc[:5]

        # URL 중복 체크
        if url not in seen_urls:
            seen_urls.add(url)
            unique_url_count += 1
            url_marker = "🆕"  # 새로운 URL
        else:
            url_marker = "🔁"  # 중복 URL (같은 문서의 다른 청크)

        logger.info(f"   {i+1}위: [{score:.4f}] {url_marker} {title[:50]}... ({date})")
        logger.info(f"      URL: {url}")

    logger.info(f"   💡 다양성: Top 5 중 {unique_url_count}개 서로 다른 문서")
    logger.info("=" * 60)

    final_score = top_docs[0][0]
    final_title = top_docs[0][1]
    final_date = top_docs[0][2]
    final_text = top_docs[0][3]
    final_url = top_docs[0][4]
    final_image = []

    # 최종 선택된 문서 정보 로깅
    logger.info(f"📄 최종 선택 문서:")
    logger.info(f"   제목: {final_title}")
    logger.info(f"   날짜: {final_date}")
    logger.info(f"   유사도: {final_score:.4f}")
    logger.info(f"   URL: {final_url}")
    logger.info(f"   본문 길이: {len(final_text)}자")
    if len(final_text) > 0:
        logger.info(f"   본문 미리보기: {final_text[:100]}...")

    # MongoDB 연결 확인 후 이미지 URL 조회
    if storage.mongo_collection is not None:
        record = storage.mongo_collection.find_one({"title" : final_title})
        if record :
            if(isinstance(record["image_url"], list)):
              final_image.extend(record["image_url"])
            else :
              final_image.append(record["image_url"])
            logger.info(f"   이미지: {len(final_image)}개")

            # HTML 구조 정보 로깅
            if record.get("html"):
                html_length = len(record["html"])
                logger.info(f"   HTML 구조: ✅ 있음 ({html_length}자)")
            else:
                logger.info(f"   HTML 구조: ❌ 없음")

            # 콘텐츠 타입 로깅
            content_type = record.get("content_type", "unknown")
            source = record.get("source", "unknown")
            logger.info(f"   콘텐츠 타입: {content_type}")
            logger.info(f"   소스: {source}")
        else :
            print("일치하는 문서 존재 X")
            logger.warning(f"⚠️  MongoDB에서 문서를 찾을 수 없습니다: {final_title}")
            final_score = 0
            final_title = "No content"
            final_date = "No content"
            final_text = "No content"
            final_url = "No URL"
            final_image = ["No content"]
    else:
        logger.warning("⚠️  MongoDB 연결 없음 - 이미지 URL 조회 불가")
        final_image = ["No content"]

    # top_docs 인덱스 구성
    # 0: 유사도, 1: 제목, 2: 날짜, 3: 본문내용, 4: url, 5: 이미지url

    # Reranker 점수는 음수일 수 있으므로 final_score < 0이면 유사도 체크 스킵
    if final_image[0] != "No content" and final_text == "No content" and (final_score < 0 or final_score > MINIMUM_SIMILARITY_SCORE):
        # JSON 형식으로 반환할 객체 생성
        only_image_response = {
            "answer": None,
            "references": final_url,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": final_image
        }
        f_time=time.time()-s_time
        print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
        return only_image_response

    # 이미지 + LLM 답변이 있는 경우.
    else:
        # ✅ 핵심 개선: 같은 URL의 모든 청크(본문 + 첨부파일 + 이미지)를 LLM에 전달!
        # 문제: 클러스터링 결과는 본문 청크만 포함 (첨부파일 누락)
        # 해결: 같은 게시글의 모든 청크를 명시적으로 가져옴
        enrich_time = time.time()

        # Top 문서의 URL 추출 (게시글 URL)
        top_url = top_docs[0][4] if top_docs else None

        if top_url:
            # ✅ 변경: URL 기반 매칭 대신 제목 기반 매칭 사용!
            # 이유: 이미지 URL(/data/editor/...)은 wr_id를 포함하지 않음
            # 해결: 같은 게시글의 모든 청크는 같은 제목을 공유하므로 제목으로 매칭
            top_title = top_docs[0][1]  # 첫 번째 문서의 제목
            wr_id = top_url.split('&wr_id=')[-1] if '&wr_id=' in top_url else top_url.split('wr_id=')[-1] if 'wr_id=' in top_url else None

            logger.info(f"🔍 같은 게시글 청크 검색: 제목='{top_title}' (wr_id={wr_id})")

            # 같은 게시글의 모든 청크 찾기 (본문 + 첨부파일 + 이미지 OCR)
            enriched_docs = []
            seen_texts = set()  # 중복 텍스트 제거용

            # 디버깅: 매칭 상황 추적
            total_checked = 0
            matched_count = 0
            duplicate_count = 0

            for i, url in enumerate(storage.cached_urls):
                # ✅ 같은 게시글인지 확인 (제목 기준 - 이미지/첨부파일 포함!)
                if storage.cached_titles[i] == top_title:
                    total_checked += 1
                    matched_count += 1

                    text = storage.cached_texts[i]
                    content_type = storage.cached_content_types[i] if i < len(storage.cached_content_types) else "unknown"
                    source = storage.cached_sources[i] if i < len(storage.cached_sources) else "unknown"

                    # 디버깅 로그 (처음 5개만)
                    if matched_count <= 5:
                        html_data = storage.cached_htmls[i] if i < len(storage.cached_htmls) else ""
                        logger.info(f"   [{matched_count}] URL: {url[:80]}...")
                        logger.info(f"       타입: {content_type}, 소스: {source}")
                        logger.info(f"       텍스트: {len(text)}자, HTML: {len(html_data)}자")
                        logger.info(f"       인덱스: {i}")

                    # 빈 텍스트는 건너뛰지 않음! (중요: "No content"도 포함)
                    text_key = ''.join(text.split())  # 공백 제거 후 비교

                    # 중복 텍스트 제거 (빈 문자열은 제외하지 않음!)
                    if text_key not in seen_texts:  # ✅ 'text_key and' 제거 (빈 텍스트도 포함)
                        seen_texts.add(text_key)
                        enriched_docs.append((
                            top_docs[0][0],  # 점수는 top 문서와 동일
                            storage.cached_titles[i],
                            storage.cached_dates[i],
                            text,
                            url,
                            storage.cached_htmls[i] if i < len(storage.cached_htmls) else "",
                            storage.cached_content_types[i] if i < len(storage.cached_content_types) else "unknown",
                            storage.cached_sources[i] if i < len(storage.cached_sources) else "unknown",
                            storage.cached_attachment_types[i] if i < len(storage.cached_attachment_types) else ""
                        ))
                    else:
                        duplicate_count += 1

            logger.info(f"   📊 매칭 통계: 전체 {len(storage.cached_urls)}개 중 {matched_count}개 매칭, {duplicate_count}개 중복 제거")

            # 청크를 찾았으면 top_docs를 교체 (본문 + 첨부파일 + 이미지)
            if enriched_docs:
                logger.info(f"🔧 같은 게시글의 모든 청크 수집: {len(top_docs)}개 → {len(enriched_docs)}개")

                # 타입별 카운트 (source 기준으로 정확히 카운트)
                original_post_count = 0
                image_count = 0
                attachment_count = 0

                for i, (score, title, date, text, url, html, content_type, source, attachment_type) in enumerate(enriched_docs):
                    # ✅ source를 tuple에서 직접 사용 (URL로 찾지 않음)
                    if source == "original_post":
                        original_post_count += 1
                    elif source == "image_ocr":
                        image_count += 1
                    elif source == "document_parse":
                        attachment_count += 1

                logger.info(f"   📦 본문 청크: {original_post_count}개")
                logger.info(f"   🖼️  이미지 OCR 청크: {image_count}개")
                logger.info(f"   📎 첨부파일 청크: {attachment_count}개")
                top_docs = enriched_docs
            else:
                logger.warning(f"⚠️  같은 게시글 청크를 찾지 못했습니다! wr_id={wr_id}")
                logger.warning(f"   Top URL: {top_url}")

        enrich_f_time = time.time() - enrich_time
        print(f"청크 수집 시간: {enrich_f_time}")

        chain_time=time.time()
        qa_chain, relevant_docs, relevant_docs_content = get_answer_from_chain(top_docs, question, query_noun, temporal_filter)
        chain_f_time=time.time()-chain_time
        print(f"chain 생성하는 시간: {chain_f_time}")

        # 🔍 디버깅: get_answer_from_chain 반환값 확인
        logger.info(f"🔍 get_answer_from_chain 반환값 확인:")
        logger.info(f"   qa_chain: {type(qa_chain)} (None? {qa_chain is None})")
        logger.info(f"   relevant_docs: {type(relevant_docs)} (None? {relevant_docs is None}, 개수: {len(relevant_docs) if relevant_docs else 0})")
        logger.info(f"   relevant_docs_content: {type(relevant_docs_content)} (None? {relevant_docs_content is None})")
        if final_url == PROFESSOR_BASE_URL + "&lang=kor" and any(keyword in query_noun for keyword in ['연락처', '전화', '번호', '전화번호']):
            data = {
                "answer": "해당 교수님은 연락처 정보가 포함되어 있지 않습니다.\n 자세한 정보는 교수진 페이지를 참고하세요.",
                "answerable": False,  # 연락처 정보 없음
                "references": final_url,
                "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
                "images": final_image
            }
            f_time=time.time()-s_time
            print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
            return data
            
        # prof_title=final_title
        # prof_url=["https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_2",
        #           "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_5",
        #           "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_1"]
        # prof_name=""
        # # 정규식을 이용하여 숫자 이전의 문자열을 추출
        # if any(final_url.startswith(url) for url in prof_url):
        #     match = re.match(r"^[^\dA-Za-z]+", prof_title)
        #     if match:
        #         prof_name = match.group().strip()  # 숫자 이전의 문자열을 교수 이름으로 저장
        #     else:
        #         prof_name = prof_title.strip()  # 숫자가 없으면 전체 문자열을 교수 이름으로 저장
        #     prof_name = re.sub(r"\s+", "", prof_name)
        #     user_question = re.sub(r"\s+", "", question)
        #     if prof_name not in user_question:
        #         refer_url=""
        #         if '직원' in query_noun:
        #             refer_url=prof_url[1]
        #         else:
        #             refer_url=prof_url[2]
        #         data = {
        #             "answer": "존재하지 않는 교수님 정보입니다. 자세한 정보는 교수진 페이지를 참고하세요.",
        #             "references": refer_url,
        #             "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
        #             "images": ["No content"]
        #         }
        #         return data

        # 공지사항에 존재하지 않을 경우
        notice_url = NOTICE_BASE_URL
        not_in_notices_response = {
            "answer": "해당 질문은 공지사항에 없는 내용입니다.\n 자세한 사항은 공지사항을 살펴봐주세요.",
            "answerable": False,  # 검색 결과 없음
            "references": notice_url,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": ["No content"]
        }

        # 답변 생성 실패
        if not qa_chain or not relevant_docs:
            logger.warning(f"⚠️ 답변 생성 실패 조건 진입!")
            logger.warning(f"   조건: not qa_chain ({not qa_chain}) or not relevant_docs ({not relevant_docs})")
            logger.warning(f"   → 기본 응답 반환 예정")
            # Reranker 점수는 음수일 수 있으므로 final_score < 0이면 유사도 체크 스킵
            if final_image[0] != "No content" and (final_score < 0 or final_score > MINIMUM_SIMILARITY_SCORE):
                data = {
                    "answer": "해당 질문에 대한 내용은 이미지 파일로 확인해주세요.",
                    "answerable": True,  # 이미지로 답변 제공
                    "references": final_url,
                    "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
                    "images": final_image
                }
                f_time=time.time()-s_time
                print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
                return data
            else:
                f_time=time.time()-s_time
                print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
                return not_in_notices_response

        # 유사도가 낮은 경우 (단, Reranker 점수는 음수일 수 있으므로 체크 스킵)
        # BGE-Reranker 점수 범위: 약 -10 ~ +10 (음수도 정상)
        # BM25 점수 범위: 0 ~ 무한대 (항상 양수)
        if final_score >= 0 and final_score < MINIMUM_SIMILARITY_SCORE:
            logger.warning(f"⚠️ 유사도 조건 진입!")
            logger.warning(f"   final_score ({final_score:.4f}) < MINIMUM_SIMILARITY_SCORE ({MINIMUM_SIMILARITY_SCORE})")
            logger.warning(f"   → 기본 응답 반환")
            f_time=time.time()-s_time
            print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
            return not_in_notices_response
        elif final_score < 0:
            logger.info(f"✅ Reranker 점수 감지 ({final_score:.4f}) → 유사도 체크 스킵")

        # LLM에서 답변을 생성하는 경우
        logger.info(f"✅ 모든 조건 통과! LLM 답변 생성 시작...")
        answer_time=time.time()

        # qa_chain.invoke() 사용 (기존 방식 유지)
        answer_result = qa_chain.invoke(question)

        answer_f_time=time.time()-answer_time
        print(f"답변 생성하는 시간: {answer_f_time}")

        # ✅ JSON 파싱 시도 (LLM이 JSON 형식으로 응답했는지 확인)
        import json
        import re

        llm_answerable = None  # LLM이 판단한 answerable 값
        llm_answer_text = None  # LLM이 생성한 답변 텍스트

        try:
            # JSON 파싱 시도
            # LLM이 가끔 ```json...``` 로 감쌀 수 있으므로 정리
            clean_result = answer_result.strip()
            if clean_result.startswith("```json"):
                clean_result = clean_result[7:]
            if clean_result.startswith("```"):
                clean_result = clean_result[3:]
            if clean_result.endswith("```"):
                clean_result = clean_result[:-3]
            clean_result = clean_result.strip()

            parsed = json.loads(clean_result)

            # JSON 파싱 성공
            if "answerable" in parsed and "answer" in parsed:
                llm_answerable = parsed["answerable"]
                llm_answer_text = parsed["answer"]
                logger.info(f"✅ JSON 파싱 성공: answerable={llm_answerable}")
                logger.info(f"   답변 길이: {len(llm_answer_text)}자")
                logger.info(f"   답변 미리보기: {llm_answer_text[:150]}...")
            else:
                logger.warning(f"⚠️ JSON 파싱 성공했으나 필수 필드 누락 → 폴백 사용")

        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON 파싱 실패 (LLM이 형식 안 지킴) → 폴백 패턴 매칭 사용")
            logger.debug(f"   에러: {e}")
            logger.debug(f"   원본 응답: {answer_result[:200]}...")

        # JSON 파싱 실패 시: 기존 answer_result 사용
        if llm_answer_text is None:
            llm_answer_text = answer_result
            logger.info(f"💬 LLM 답변 생성 완료 (비-JSON 형식):")
            logger.info(f"   답변 길이: {len(llm_answer_text)}자")
            logger.info(f"   답변 미리보기: {llm_answer_text[:150]}...")

        logger.info(f"   사용된 참고문서 수: {len(relevant_docs)}")

        # 답변 검증 및 경고 추가 (범용)
        completeness_keywords = ['전부', '모든', '모두', '빠짐없이', '전체', '다', '명단', '목록', '리스트', '누구']
        has_completeness_request = any(keyword in question for keyword in completeness_keywords)

        # 완전성 요구 + Context와 답변 차이가 크면 경고
        if has_completeness_request:
            # Context에 있는 숫자 패턴 (학번, 날짜 등)
            context_numbers = len(re.findall(r'\b20\d{6,8}\b', relevant_docs_content))
            answer_numbers = len(re.findall(r'\b20\d{6,8}\b', llm_answer_text))

            logger.info(f"   📊 완전성 검증: Context {context_numbers}건 / 답변 {answer_numbers}건")

            # Context의 50% 미만만 답변에 포함되면 경고
            if context_numbers >= 10 and answer_numbers < context_numbers * 0.5:
                logger.warning(f"   ⚠️ 완전성 요구했으나 답변 불완전! LLM이 임의로 요약한 것으로 판단")
                llm_answer_text += f"\n\n⚠️ 일부 내용이 생략되었을 수 있습니다 (문서: 약 {context_numbers}건 / 답변: {answer_numbers}건). 전체 내용은 참고 URL을 확인하세요."

        doc_references = "\n".join([
            f"\n참고 문서 URL: {doc.metadata['url']}"
            for doc in relevant_docs[:1] if doc.metadata.get('url') != 'No URL'
        ])

        # ✅ answerable 최종 판단
        if llm_answerable is not None:
            # JSON 파싱 성공 → LLM이 직접 판단한 값 사용
            answerable = llm_answerable
            logger.info(f"✅ answerable 판단: JSON 파싱 결과 사용 (LLM 직접 판단: {answerable})")
        else:
            # JSON 파싱 실패 → 폴백: 패턴 매칭으로 판단
            answer_start = llm_answer_text[:150]
            if answer_start.startswith("제공된 문서에는") and any(phrase in answer_start for phrase in ["없습니다", "포함되어 있지 않습니다"]):
                answerable = False
            else:
                answerable = True
            logger.info(f"⚠️ answerable 판단: 폴백 패턴 매칭 사용 (결과: {answerable})")

        if answerable:
            logger.info("✅ LLM이 문서에서 답변을 찾았습니다")
        else:
            logger.info("❌ LLM이 문서에서 답변을 찾지 못했습니다 (프론트엔드에서 질문 작성 요청 안내 표시)")

        # JSON 형식으로 반환할 객체 생성
        data = {
            "answer": llm_answer_text,  # JSON 파싱된 답변 또는 원본 답변
            "answerable": answerable,  # 답변 가능 여부
            "references": doc_references,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": final_image
        }
        f_time=time.time()-s_time
        logger.info(f"✅ 총 처리 시간: {f_time:.2f}초")
        print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
        return data