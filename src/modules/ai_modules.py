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
from bs4 import BeautifulSoup

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

# StorageManager 싱글톤 인스턴스 가져오기
storage = get_storage_manager()

# URL 상수
NOTICE_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1"
COMPANY_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_3_b"
SEMINAR_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_4"
PROFESSOR_BASE_URL = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub2_2"

def get_korean_time():
    return datetime.now(pytz.timezone('Asia/Seoul'))

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
        k1=1.5,
        b=0.75,
        redis_client=storage.redis_client  # Redis 캐싱 활성화
    )
    storage.set_bm25_retriever(bm25_retriever)

    # DenseRetriever 초기화
    dense_retriever = DenseRetriever(
        embeddings_factory=get_embeddings,
        pinecone_index=storage.pinecone_index,
        date_adjuster=adjust_date_similarity,
        similarity_scale=3.26,
        noun_weight=0.20,
        digit_weight=0.24
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
        similarity_threshold=0.89
    )
    storage.set_document_clusterer(document_clusterer)

    logger.info("✅ 모든 검색 엔진 초기화 완료!")

                    #################################   24.11.16기준 정확도 측정완료 #####################################################
######################################################################################################################

# 날짜를 파싱하는 함수 (하위 호환성 유지)
# 이제는 utils.date_utils.parse_date_change_korea_time 사용 권장

def parse_date_change_korea_time(date_str):
    """
    날짜 문자열을 datetime 객체로 변환
    ISO 8601 형식과 레거시 한국어 형식 모두 지원

    Args:
        date_str: ISO 8601 형식 또는 "작성일25-10-17 15:48" 형식

    Returns:
        datetime 객체 (한국 시간대)
    """
    # 빈 문자열이면 None
    if not date_str:
        return None

    try:
        # 먼저 ISO 8601 형식 시도 (새 형식)
        dt = datetime.fromisoformat(date_str)
        # 시간대가 없으면 한국 시간대 추가
        if dt.tzinfo is None:
            korea_timezone = pytz.timezone('Asia/Seoul')
            return korea_timezone.localize(dt)
        return dt
    except (ValueError, TypeError):
        pass

    try:
        # 레거시 한국어 형식 시도 (하위 호환성)
        clean_date_str = date_str.replace("작성일", "").strip()
        naive_date = datetime.strptime(clean_date_str, "%y-%m-%d %H:%M")
        # 한국 시간대 추가
        korea_timezone = pytz.timezone('Asia/Seoul')
        return korea_timezone.localize(naive_date)
    except (ValueError, TypeError):
        return None


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

def find_url(url, title, doc_date, text, doc_url, number):
    return_docs = []
    for i, urls in enumerate(doc_url):
        if urls.startswith(url):  # indexs와 시작이 일치하는지 확인
            return_docs.append((title[i], doc_date[i], text[i], doc_url[i]))
    
    # doc_url[i] 순서대로 정렬
    return_docs.sort(key=lambda x: x[3],reverse=True) 

    # 고유 숫자를 추적하며 number개의 문서 선택
    unique_numbers = set()
    filtered_docs = []

    for doc in return_docs:
        # 숫자가 서로 다른 number개가 모이면 종료
        if len(unique_numbers) >= number:
            break
        url_number = ''.join(filter(str.isdigit, doc[3]))  # URL에서 숫자 추출
        unique_numbers.add(url_number)
        filtered_docs.append(doc)


    return filtered_docs


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

    # 2단계: 복잡한 시간 표현은 LLM으로 해석 (유연하고 정확)
    # "저번학기", "작년 2학기", "다음 학기", "지난달" 등
    complex_temporal_keywords = ['학기', '학년', '년도', '작년', '올해', '내년', '지난', '다음', '전', '후']

    if any(keyword in query for keyword in complex_temporal_keywords):
        logger.info(f"🤔 복잡한 시간 표현 감지 → LLM 리라이팅 시작...")
        llm_filter = rewrite_query_with_llm(query, current_date)
        if llm_filter:
            logger.info(f"✨ LLM 리라이팅 결과: {llm_filter}")
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

    prompt = f"""당신은 대학 학사 일정 시간 표현 전문가입니다.

현재 날짜: {current_date.strftime('%Y년 %m월 %d일')}
현재 학기: {current_year}학년도 {current_semester}학기

한국 대학 학기 기준:
- 1학기: 3월~8월
- 2학기: 9월~2월 (다음해 2월까지)
- 여름학기: 6월~8월
- 겨울학기: 12월~2월

사용자 질문: "{query}"

위 질문에서 시간 표현을 추출하고, 정확한 학년도와 학기를 JSON 형식으로 반환하세요.

출력 형식 (JSON만):
{{
  "year": 2025,
  "semester": 1,
  "reasoning": "현재 2025년 2학기이므로, 저번학기는 2025년 1학기입니다"
}}

시간 표현이 없으면:
{{
  "year": null,
  "semester": null,
  "reasoning": "시간 표현 없음"
}}

예시:
- "저번학기" → {{"year": {current_year if current_semester == 2 else current_year - 1}, "semester": {2 if current_semester == 1 else 1}, "reasoning": "..."}}
- "작년 2학기" → {{"year": {current_year - 1}, "semester": 2, "reasoning": "..."}}
- "다음 학기" → {{"year": {current_year + 1 if current_semester == 2 else current_year}, "semester": {1 if current_semester == 2 else 2}, "reasoning": "..."}}

**중요**: JSON만 출력하고, 다른 텍스트는 포함하지 마세요.
"""

    try:
        llm = ChatUpstage(api_key=storage.upstage_api_key, model="solar-pro")
        response = llm.invoke(prompt)

        # JSON 파싱
        result = json.loads(response.content.strip())

        if result.get('year') is None or result.get('semester') is None:
            return None

        logger.info(f"   💬 LLM 추론: {result.get('reasoning', '')}")

        return {
            'year': result['year'],
            'semester': result['semester']
        }

    except Exception as e:
        logger.warning(f"⚠️  LLM 리라이팅 실패 (규칙 기반으로 폴백): {e}")
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

      # ✅ 시간 표현 감지 및 필터 생성
      temporal_filter = parse_temporal_intent(user_question)

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

      # ✅ 시간 필터 적용 (검색 결과를 날짜 기준으로 필터링)
      if temporal_filter:
          from datetime import datetime

          def matches_temporal_filter(doc_date_str, time_filter):
              """날짜 문자열이 시간 필터 조건을 만족하는지 확인"""
              try:
                  # ISO 포맷 파싱: "2024-09-19T10:57:00+09:00"
                  doc_date = datetime.fromisoformat(doc_date_str.replace('+09:00', ''))
                  doc_year = doc_date.year
                  doc_month = doc_date.month

                  # 학기 계산
                  if 3 <= doc_month <= 8:
                      doc_semester = 1
                  else:
                      doc_semester = 2
                      if doc_month <= 2:
                          doc_year -= 1

                  # 필터 조건 체크
                  if 'year' in time_filter and doc_year != time_filter['year']:
                      return False
                  if 'semester' in time_filter and doc_semester != time_filter['semester']:
                      return False
                  if 'year_from' in time_filter and doc_year < time_filter['year_from']:
                      return False

                  return True
              except Exception as e:
                  logger.debug(f"날짜 파싱 실패: {doc_date_str} - {e}")
                  return True  # 파싱 실패 시 포함 (안전장치)

          # BM25 결과 필터링
          original_bm25_count = len(Bm25_best_docs)
          Bm25_best_docs = [
              (title, date, text, url)
              for title, date, text, url in Bm25_best_docs
              if matches_temporal_filter(date, temporal_filter)
          ]

          # Dense 결과 필터링
          original_dense_count = len(combine_dense_docs)
          combine_dense_docs = [
              (score, doc)
              for score, doc in combine_dense_docs
              if matches_temporal_filter(doc[1], temporal_filter)  # doc[1] = date
          ]

          logger.info(f"📅 날짜 필터링 완료: BM25 {original_bm25_count}→{len(Bm25_best_docs)}개, Dense {original_dense_count}→{len(combine_dense_docs)}개")

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

prompt_template = """당신은 경북대학교 컴퓨터학부 공지사항을 전달하는 직원이고, 사용자의 질문에 대해 올바른 공지사항의 내용을 참조하여 정확하게 전달해야 할 의무가 있습니다.
현재 한국 시간: {current_time}

주어진 컨텍스트를 기반으로 다음 질문에 답변해주세요:

{context}

질문: {question}

답변 시 다음 사항을 고려해주세요:

1. **시간 비교 및 명시 (매우 중요!):**
  - 질문에 시간 표현(이번학기, 올해 등)이 없더라도, 반드시 문서의 날짜와 현재 시간을 비교하세요.
  - 문서가 올해가 아니라면 **반드시 명시**하세요. 예: "⚠️ 주의: 이 정보는 2024년 자료입니다."
  - 이벤트 기간 비교:
    * "2학기 수강신청 일정은 언제야?" (현재 11월) → "2학기 수강신청은 이미 종료되었습니다 (8월). 일정은 다음과 같았습니다: ..."
    * "겨울 계절 신청기간은 언제야?" (현재 11월 12일, 신청 11월 13일) → "겨울 계절 신청은 내일(11월 13일)부터 시작됩니다."
    * "겨울 계절 신청기간은 언제야?" (현재 11월 13일, 신청 11월 13일) → "현재 겨울 계절 신청기간입니다 (11월 13일부터)."

  - **과거 데이터 사용 시 경고:**
    * 문서가 작년(2024년) 것이면: "⚠️ 주의: 2025년 자료가 없어 2024년 정보를 제공합니다. 최신 정보는 공지사항을 확인하세요."
    * 문서가 2년 이상 오래됐으면: "⚠️ 주의: 이 정보는 20XX년 자료로 오래되었습니다. 최신 정보는 공지사항을 반드시 확인하세요."
2. 질문에서 핵심적인 키워드들을 골라 키워드들과 관련된 문서를 찾아서 해당 문서를 읽고 정확한 내용을 답변해주세요.
3. **답변 완전성 vs 간결성 (매우 중요!):**
   - **⚠️ 완전성 요구 키워드**: 질문에 "전부", "모든", "모두", "빠짐없이", "전체", "다", "명단", "목록", "리스트", "누구" 등이 포함되면, 문서의 **모든 항목을 절대 생략하지 말고 전부 나열**하세요.
     * 예: "면접 대상자 **전부** 알려줘" → 문서에 있는 **모든** 대상자를 1명도 빠짐없이 나열 (요약 금지!)
     * 예: "장학금 수혜자 **누구**니?" → **모든** 수혜자 이름과 학번을 전부 제공 (일부만 제공 금지!)
     * 예: "**모든** 튜터 알려줘" → 문서의 **모든** 튜터를 빠짐없이 나열
     * **절대 규칙**: 완전성 키워드가 있으면 "...등", "일부", "주요" 같은 요약 표현 사용 금지. 문서의 마지막 항목까지 전부 나열할 것!
   - **일반 질문**: 완전성 키워드가 없는 일반 질문은 간결하게 답변하세요.
     * 예: "수강신청 방법은?" → 핵심 절차만 간결하게 설명
4. 에이빅과 관련된 질문이 들어오면 임의로 판단해서 네 아니오 하지 말고 문서에 있는 내용을 그대로 알려주세요.
5. 답변은 친절하게 존댓말로 제공하세요.
6. 질문이 공지사항의 내용과 전혀 관련이 없다고 판단하면 응답하지 말아주세요. 예를 들면 "너는 무엇을 알까", "점심메뉴 추천"과 같이 일반 상식을 요구하는 질문은 거절해주세요.
7. 에이빅 인정 관련 질문이 들어오면 계절학기인지 그냥 학기를 묻는것인지 질문을 체크해야합니다. 계절학기가 아닌 경우에 심컴,글솝,인컴 개설이 아니면 에이빅 인정이 안됩니다.

**멀티모달 컨텍스트 활용 가이드:**
8. 컨텍스트에 HTML 표(<table>, <tr>, <td> 등) 또는 Markdown 표가 포함되어 있으면, 표 구조를 정확히 파싱하여 정보를 추출하세요.
  - 예시: <tr><td>성적우수장학금</td><td>300만원</td></tr>는 "성적우수장학금: 300만원"을 의미합니다.
  - Markdown 표 예시: "| 과목 | 튜터 | 강의실 |\n| 알고리즘2 | 최기영 | IT5-224 |"는 "알고리즘2의 튜터는 최기영, 강의실은 IT5-224"를 의미합니다.
  - 표의 행(row)과 열(column) 관계를 정확히 파악하여 답변하세요.
9. 컨텍스트 출처 라벨([본문], [이미지 OCR 텍스트], [첨부파일: PDF])을 참고하여 정보의 신뢰도를 고려하세요.
  - [본문]: 원본 게시글 텍스트 (가장 신뢰도 높음)
  - [이미지 OCR 텍스트]: 이미지에서 추출한 텍스트 (OCR 오류 가능성 고려)
  - [첨부파일: PDF/HWP/DOCX]: 첨부파일에서 추출한 텍스트 및 구조 (공식 문서로 신뢰도 높음)
10. HTML 리스트(<ul>, <ol>, <li>)나 중첩 구조가 있으면, 계층 구조를 유지하여 답변하세요.

**깨진 데이터 처리 가이드 (관대하게 해석):**
11. HTML/Markdown 표가 일부 손상되었거나 불완전한 경우:
  - 표 구조를 최대한 유추하여 정보를 추출하세요.
  - 예시: "| 과목 | 튜터 | 강의실\n알고리즘2 최기영 IT5-224" → 구분자가 일부 누락되어도 문맥상 "알고리즘2의 튜터는 최기영, 강의실은 IT5-224"로 해석
12. OCR 텍스트의 오타나 누락이 있을 경우:
  - 문맥을 고려하여 올바른 정보를 유추하세요.
  - 예시: "최7ㅣ영" → "최기영", "IT5二224" → "IT5-224", "T0T0R" → "TUTOR"
  - 비슷한 형태의 문자가 잘못 인식된 경우 (숫자/한글/영문 혼동) 올바르게 해석하세요.
13. 표의 헤더와 데이터가 섞여있거나 줄바꿈이 누락된 경우:
  - 패턴을 파악하여 정보를 재구성하세요.
  - 불확실한 경우 "문서가 일부 손상되어 정확한 정보를 확인하기 어렵습니다. 참고 URL을 확인하세요."라고 명시하세요.
답변:"""

# PromptTemplate 객체 생성
PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["current_time", "context", "question"]
)

def format_docs(docs):
    """
    문서 리스트를 LLM이 이해하기 쉬운 형식으로 포맷팅
    출처(원본/이미지OCR/첨부파일)를 라벨로 표시하여 맥락 제공
    각 청크에 제목 정보를 명시하여 문맥 단절(Context Fragmentation) 문제 해결

    Args:
        docs: Document 객체 리스트

    Returns:
        str: 포맷팅된 컨텍스트 문자열
    """
    formatted = []

    for doc in docs:
        # 메타데이터에서 제목 추출
        title = doc.metadata.get('title', '제목 없음')

        # 출처에 따라 라벨 생성
        source = doc.metadata.get('source', 'original_post')
        content_type = doc.metadata.get('content_type', 'text')

        if source == "image_ocr":
            label = "[이미지 OCR 텍스트]"
        elif source == "document_parse":
            # 첨부파일 타입 표시
            attachment_type = doc.metadata.get('attachment_type', 'document')
            label = f"[첨부파일: {attachment_type.upper()}]"
        else:
            # 원본 게시글
            label = "[본문]"

        # 제목 + 라벨 + 내용 (제목을 명시하여 청크의 문맥 제공)
        formatted.append(f"문서 제목: {title}\n{label}\n{doc.page_content}")

    return "\n\n".join(formatted)


def get_answer_from_chain(best_docs, user_question,query_noun):

    # ✅ best_docs에서 메타데이터 직접 추출 (URL로 다시 찾지 않음)
    documents = []
    for doc in best_docs:
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
            # Markdown 형식 감지 (Upstage API 제공, 고품질 표 구조)
            # 이미 Markdown이면 그대로 사용 (토큰 효율적, LLM 최적화)
            if '|' in html and ('---' in html or '\n' in html):
                # Markdown 표 형식
                page_content = html
            else:
                # HTML → Markdown 변환 (fallback)
                try:
                    soup = BeautifulSoup(html, 'html.parser')

                    # 테이블이 있으면 Markdown 표로 변환
                    markdown_content = ""
                    for table in soup.find_all('table'):
                        markdown_content += "\n\n**[표 데이터]**\n"
                        rows = table.find_all('tr')
                        for row_idx, row in enumerate(rows):
                            cells = row.find_all(['th', 'td'])
                            row_text = " | ".join([cell.get_text(strip=True) for cell in cells])
                            markdown_content += f"| {row_text} |\n"
                            # 헤더 행 다음에 구분선 추가
                            if row_idx == 0:
                                markdown_content += "| " + " | ".join(["---"] * len(cells)) + " |\n"
                        markdown_content += "\n"

                    # 테이블 외 텍스트 추출
                    for table in soup.find_all('table'):
                        table.decompose()  # 테이블 제거 (중복 방지)

                    plain_text_from_html = soup.get_text(separator='\n', strip=True)

                    # 최종 page_content: Markdown 표 + 평문
                    page_content = (markdown_content + "\n" + plain_text_from_html).strip()

                    # 내용이 없으면 원본 text 사용
                    if not page_content:
                        page_content = text
                except Exception as e:
                    logger.debug(f"HTML 변환 실패, 원본 텍스트 사용: {e}")
                    page_content = text
        else:
            page_content = text

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
      return None, None

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
    logger.info(f"   📄 실제 전달되는 Context 요약 (각 청크당 앞 20자 + 뒤 20자):")
    logger.info(f"{'='*80}")

    # 각 청크를 "\n\n문서 제목:"으로 분리
    chunks = relevant_docs_content.split('\n\n문서 제목:')
    for i, chunk in enumerate(chunks):
        if i > 0:  # 첫 번째는 빈 문자열이므로 스킵
            chunk = '문서 제목:' + chunk  # 분리 시 제거된 부분 복원

        chunk_len = len(chunk)

        if chunk_len <= 40:
            # 40자 이하면 전체 출력
            logger.info(chunk)
        else:
            # 앞 20자 + ... + 뒤 20자
            preview = chunk[:20] + f'... ({chunk_len - 40}자 생략) ...' + chunk[-20:]
            logger.info(preview)

        if i < len(chunks) - 1:
            logger.info('')  # 청크 구분용 빈 줄

    logger.info(f"{'='*80}")

    qa_chain = (
        {
            "current_time": lambda _: get_korean_time().strftime("%Y년 %m월 %d일 %H시 %M분"),
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
    best_time=time.time()
    top_doc, query_noun = best_docs(question)  # 가장 유사한 문서 가져오기
    best_f_time=time.time()-best_time
    print(f"best_docs 뽑는 시간:{best_f_time}")

    # 검색된 문서 정보 로깅
    logger.info(f"📝 사용자 질문: {question}")
    logger.info(f"🔍 추출된 키워드: {query_noun}")

    # query_noun이 없거나 top_doc이 비어있는 경우 처리
    if not query_noun or not top_doc or len(top_doc) == 0:
        notice_url = "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1"
        not_in_notices_response = {
            "answer": "해당 질문은 공지사항에 없는 내용입니다.\n 자세한 사항은 공지사항을 살펴봐주세요.",
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

    if final_image[0] != "No content" and final_text == "No content" and final_score > MINIMUM_SIMILARITY_SCORE:
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
                        logger.info(f"   [{matched_count}] URL: {url[:80]}...")
                        logger.info(f"       타입: {content_type}, 소스: {source}, 텍스트: {len(text)}자")

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
                本문_count = 0
                image_count = 0
                attachment_count = 0

                for i, (score, title, date, text, url, html, content_type, source, attachment_type) in enumerate(enriched_docs):
                    # ✅ source를 tuple에서 직접 사용 (URL로 찾지 않음)
                    if source == "original_post":
                        本文_count += 1
                    elif source == "image_ocr":
                        image_count += 1
                    elif source == "document_parse":
                        attachment_count += 1

                logger.info(f"   📦 본문 청크: {本문_count}개")
                logger.info(f"   🖼️  이미지 OCR 청크: {image_count}개")
                logger.info(f"   📎 첨부파일 청크: {attachment_count}개")
                top_docs = enriched_docs
            else:
                logger.warning(f"⚠️  같은 게시글 청크를 찾지 못했습니다! wr_id={wr_id}")
                logger.warning(f"   Top URL: {top_url}")

        enrich_f_time = time.time() - enrich_time
        print(f"청크 수집 시간: {enrich_f_time}")

        chain_time=time.time()
        qa_chain, relevant_docs, relevant_docs_content = get_answer_from_chain(top_docs, question,query_noun)
        chain_f_time=time.time()-chain_time
        print(f"chain 생성하는 시간: {chain_f_time}")
        if final_url == PROFESSOR_BASE_URL + "&lang=kor" and any(keyword in query_noun for keyword in ['연락처', '전화', '번호', '전화번호']):
            data = {
                "answer": "해당 교수님은 연락처 정보가 포함되어 있지 않습니다.\n 자세한 정보는 교수진 페이지를 참고하세요.",
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
            "references": notice_url,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": ["No content"]
        }

        # 답변 생성 실패
        if not qa_chain or not relevant_docs:
            if final_image[0] != "No content" and final_score > MINIMUM_SIMILARITY_SCORE:
                data = {
                    "answer": "해당 질문에 대한 내용은 이미지 파일로 확인해주세요.",
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

        # 유사도가 낮은 경우
        if final_score < MINIMUM_SIMILARITY_SCORE:
            f_time=time.time()-s_time
            print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
            return not_in_notices_response

        # LLM에서 답변을 생성하는 경우
        answer_time=time.time()

        # qa_chain.invoke() 사용 (기존 방식 유지)
        answer_result = qa_chain.invoke(question)

        answer_f_time=time.time()-answer_time
        print(f"답변 생성하는 시간: {answer_f_time}")

        logger.info(f"💬 LLM 답변 생성 완료:")
        logger.info(f"   답변 길이: {len(answer_result)}자")
        logger.info(f"   답변 미리보기: {answer_result[:150]}...")
        logger.info(f"   사용된 참고문서 수: {len(relevant_docs)}")

        # 답변 검증 및 경고 추가 (범용)
        completeness_keywords = ['전부', '모든', '모두', '빠짐없이', '전체', '다', '명단', '목록', '리스트', '누구']
        has_completeness_request = any(keyword in question for keyword in completeness_keywords)

        # 완전성 요구 + Context와 답변 차이가 크면 경고
        if has_completeness_request:
            # Context에 있는 숫자 패턴 (학번, 날짜 등)
            import re
            context_numbers = len(re.findall(r'\b20\d{6,8}\b', relevant_docs_content))
            answer_numbers = len(re.findall(r'\b20\d{6,8}\b', answer_result))

            logger.info(f"   📊 완전성 검증: Context {context_numbers}건 / 답변 {answer_numbers}건")

            # Context의 50% 미만만 답변에 포함되면 경고
            if context_numbers >= 10 and answer_numbers < context_numbers * 0.5:
                logger.warning(f"   ⚠️ 완전성 요구했으나 답변 불완전! LLM이 임의로 요약한 것으로 판단")
                answer_result += f"\n\n⚠️ 일부 내용이 생략되었을 수 있습니다 (문서: 약 {context_numbers}건 / 답변: {answer_numbers}건). 전체 내용은 참고 URL을 확인하세요."

        doc_references = "\n".join([
            f"\n참고 문서 URL: {doc.metadata['url']}"
            for doc in relevant_docs[:1] if doc.metadata.get('url') != 'No URL'
        ])

        # JSON 형식으로 반환할 객체 생성
        data = {
            "answer": answer_result,
            "references": doc_references,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": final_image
        }
        f_time=time.time()-s_time
        logger.info(f"✅ 총 처리 시간: {f_time:.2f}초")
        print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
        return data