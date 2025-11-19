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

                                        # 이미지 OCR인 경우 ocr_html, 문서인 경우 html
                                        html_content = cached.get("ocr_html") or cached.get("html", "")
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

    # BM25Retriever 초기화 (HTML 데이터 포함)
    bm25_retriever = BM25Retriever(
        titles=storage.cached_titles,
        texts=storage.cached_texts,
        urls=storage.cached_urls,
        dates=storage.cached_dates,
        query_transformer=transformed_query,
        similarity_adjuster=adjust_similarity_scores,
        htmls=storage.cached_htmls,  # HTML 구조화 데이터 추가
        k1=1.5,
        b=0.75
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
          top_k=25,
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
          top_k=30
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
          top_k=20
      )
      combine_f_time = time.time() - combine_time
      print(f"Bm25랑 pinecone 결합 시간: {combine_f_time}")
      # 문서 클러스터링 및 최적 클러스터 선택 (리팩토링됨 - DocumentClusterer 사용)
      cluster_time = time.time()
      final_cluster, count = storage.document_clusterer.cluster_and_select(
          documents=final_best_docs,
          query_nouns=query_noun,
          all_titles=titles_from_pinecone,
          all_dates=dates_from_pinecone,
          all_texts=texts_from_pinecone,
          all_urls=urls_from_pinecone
      )
      cluster_f_time = time.time() - cluster_time
      print(f"cluster로 문서 추출하는 시간:{cluster_f_time}")

      return final_cluster, query_noun

prompt_template = """당신은 경북대학교 컴퓨터학부 공지사항을 전달하는 직원이고, 사용자의 질문에 대해 올바른 공지사항의 내용을 참조하여 정확하게 전달해야 할 의무가 있습니다.
현재 한국 시간: {current_time}

주어진 컨텍스트를 기반으로 다음 질문에 답변해주세요:

{context}

질문: {question}

답변 시 다음 사항을 고려해주세요:

1. 질문의 내용이 이벤트의 기간에 대한 것일 경우, 문서에 주어진 기한과 현재 한국 시간을 비교하여 해당 이벤트가 예정된 것인지, 진행 중인지, 또는 이미 종료되었는지에 대한 정보를 알려주세요.
  예를 들어, "2학기 수강신청 일정은 언제야?"라는 질문을 받았을 경우, 현재 시간은 11월이라고 가정하면 수강신청은 기간은 8월이었으므로 이미 종료된 이벤트입니다.
  따라서, "2학기 수강신청은 이미 종료되었습니다."와 같은 문구를 추가로 사용자에게 제공해주고, 2학기 수강신청 일정에 대한 정보를 사용자에게 제공해주어야 합니다.
  또 다른 예시로 현재 시간이 11월 12일이라고 가정하였을 때, "겨울 계절 신청기간은 언제야?"라는 질문을 받았고, 겨울 계절 신청기간이 11월 13일이라면 아직 시작되지 않은 이벤트입니다.
  따라서, "겨울 계절 신청은 아직 시작 전입니다."와 같은 문구를 추가로 사용자에게 제공해주고, 겨울 계절 신청 일정에 대한 정보를 사용자에게 제공해주어야 합니다.
  또 다른 예시로 현재 시간이 11월 13일이라고 가정하였을 때, "겨울 계절 신청기간은 언제야?"라는 질문을 받았고, 겨울 계절 신청기간이 11월 13일이라면 현재 진행 중인 이벤트입니다.
  따라서, "현재 겨울 계절 신청기간입니다."와 같은 문구를 추가로 사용자에게 제공해주고, 겨울 계절 신청 일정에 대한 정보를 사용자에게 제공해주어야 합니다.
2. 질문에서 핵심적인 키워드들을 골라 키워드들과 관련된 문서를 찾아서 해당 문서를 읽고 정확한 내용을 답변해주세요.
3. 문서의 내용을 그대로 길게 전달하기보다는 질문에서 요구하는 내용에 해당하는 답변만을 제공함으로써 최대한 답변을 간결하고 일관된 방식으로 제공하세요.
4. 에이빅과 관련된 질문이 들어오면 임의로 판단해서 네 아니오 하지 말고 문서에 있는 내용을 그대로 알려주세요.
5. 답변은 친절하게 존댓말로 제공하세요.
6. 질문이 공지사항의 내용과 전혀 관련이 없다고 판단하면 응답하지 말아주세요. 예를 들면 "너는 무엇을 알까", "점심메뉴 추천"과 같이 일반 상식을 요구하는 질문은 거절해주세요.
7. 에이빅 인정 관련 질문이 들어오면 계절학기인지 그냥 학기를 묻는것인지 질문을 체크해야합니다. 계절학기가 아닌 경우에 심컴,글솝,인컴 개설이 아니면 에이빅 인정이 안됩니다.

**멀티모달 컨텍스트 활용 가이드:**
8. 컨텍스트에 HTML 표(<table>, <tr>, <td> 등)가 포함되어 있으면, 표 구조를 정확히 파싱하여 정보를 추출하세요.
  - 예시: <tr><td>성적우수장학금</td><td>300만원</td></tr>는 "성적우수장학금: 300만원"을 의미합니다.
  - 표의 행(row)과 열(column) 관계를 정확히 파악하여 답변하세요.
9. 컨텍스트 출처 라벨([본문], [이미지 OCR 텍스트], [첨부파일: PDF])을 참고하여 정보의 신뢰도를 고려하세요.
  - [본문]: 원본 게시글 텍스트 (가장 신뢰도 높음)
  - [이미지 OCR 텍스트]: 이미지에서 추출한 텍스트 (OCR 오류 가능성 고려)
  - [첨부파일: PDF/HWP/DOCX]: 첨부파일에서 추출한 텍스트 및 구조 (공식 문서로 신뢰도 높음)
10. HTML 리스트(<ul>, <ol>, <li>)나 중첩 구조가 있으면, 계층 구조를 유지하여 답변하세요.
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

    documents = []
    doc_titles = []
    doc_dates = []
    doc_texts = []
    doc_urls = []
    for doc in best_docs:
        tit = doc[1]
        date = doc[2]
        text = doc[3]
        url = doc[4]
        # score,tit, date, text, url,im_url = doc
        doc_titles.append(tit)  # 제목
        doc_dates.append(date)    # 날짜
        doc_texts.append(text)    # 본문
        doc_urls.append(url)     # URL

    # 멀티모달 메타데이터를 포함한 Document 객체 생성
    documents = []
    for title, text, url, date in zip(doc_titles, doc_texts, doc_urls, doc_dates):
        # URL로 캐시된 데이터에서 해당 문서의 멀티모달 메타데이터 찾기
        try:
            idx = storage.cached_urls.index(url)
            html = storage.cached_htmls[idx] if idx < len(storage.cached_htmls) else ""
            content_type = storage.cached_content_types[idx] if idx < len(storage.cached_content_types) else "text"
            source = storage.cached_sources[idx] if idx < len(storage.cached_sources) else "original_post"
            attachment_type = storage.cached_attachment_types[idx] if idx < len(storage.cached_attachment_types) else ""
        except (ValueError, IndexError):
            # URL을 찾지 못하면 기본값 사용
            html = ""
            content_type = "text"
            source = "original_post"
            attachment_type = ""

        # HTML이 있으면 Markdown으로 변환하여 사용, 없으면 text를 사용
        if html:
            # HTML을 구조화된 텍스트로 변환 (표 구조 보존)
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

    relevant_docs = [doc for doc in documents if any(keyword in doc.page_content for keyword in query_noun)]
    if not relevant_docs:
      return None, None

    llm = ChatUpstage(api_key=storage.upstage_api_key)
    relevant_docs_content=format_docs(relevant_docs)

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

    return qa_chain,relevant_docs



#######################################################################

def question_valid(question, top_docs, query_noun):
    prompt = f"""
아래의 질문에 대해, 주어진 기준을 바탕으로 "예" 또는 "아니오"로 판단해주세요. 각 질문에 대해 학사 관련 여부를 명확히 판단하고, 경북대학교 컴퓨터학부 홈페이지에서 제공하지 않는 정보는 "아니오"로, 제공되는 경우에는 "예"로 답변해야 합니다."

1. 핵심 판단 원칙
경북대학교 컴퓨터학부 홈페이지에서 다루는 정보에만 답변을 제공해야 하며, 관련 없는 질문은 "아니오"로 판단합니다.

질문 분석 3단계:

질문의 실제 의도와 목적 파악
학부 홈페이지에서 제공되는 정보 여부 확인
학사 관련성 최종 확인

복합 질문 처리:

주요 질문과 부가 질문 구분
부수적 내용은 판단에서 제외
학부 공식 정보와 무관한 질문 구별
악의적 질문 대응:

학사 키워드가 포함되었더라도, 실제로 학부 정보가 필요하지 않은 질문을 "아니오"로 답변
2. "예"로 판단하는 학사 관련 카테고리:
경북대학교 컴퓨터학부 홈페이지에서 다루는 학사 정보를 다음과 같이 정의하고, 해당 내용에 대해서만 "예"로 답변합니다.
수업 및 학점 관련 정보: 수강신청, 수강정정, 수강변경, 수강취소, 기말고사, 중간고사, 과목 운영 방식, 학점 인정, 복수전공 혹은 부전공 요건,교양강의와 관련된 질문, 전공강의와 관련된 질문, 심컴, 인컴, 글솦 학과에 관련된 질문, 강의 개선 관련 설문
학생 지원 제도: 장학금, 학과 주관 인턴십 프로그램, 멘토링 ,각종 장학생 선발, 학자금대출, 특정 지역의 학자금대출 관련 질문
학사 행정 및 제도: 졸업 요건, 학적 관리, 필수 이수 요건, 증명서 발급, 학사 일정, 자퇴,복학, 휴학 등
교수진 및 행정 정보: 교수진 연락처,번호,이메일, 학과 사무실 정보, 지도교수와 관련된 정보
학부 주관 교내 활동:  각종 경진대회, 행사, 벤처프로그램 ,벤처아카데미,튜터(TUTOR) 관련 활동(근무일지 작성, 근무 기준) 튜터(TUTOR) 모집 및 비용 관련 질문, 다양한 프로그램(예: AEP 프로그램, CES 프로그램,미국 프로그램)
신청 및 일정, 성인지 교육이나 인권 교육, 혹은 다른 교육에 관련된 일정
교수진 정보: 교수의 모든 정보(이메일,번호,연락처,메일,사진,전공,업무), 학과 관련 직원의 모든 정보, 담당 업무와 관련된 학과 교직원 정보
장학금 및 교내 지원 제도: 최근 장학금 선발 정보나 교내 각종 지원 제도에 대한 안내
졸업 요건 정보: 졸업에 필요한 학점 요건, 필수로 들어야 하는 강의, 과목, 등록 횟수 관련 정보, 졸업 시 필요한 정보 , 포트폴리오 관련 정보 전체적으로 졸업에 필요한 정보는 무조건 "예"로 합니다.
기타 학사 제도: 교내 방학 중 근로장학생 관련 정보, 대학원과 관련된 질문,대학원생 학점 인정 절차와 요건 ,전시회 개최 및 지원 정보, 행사 지원 정보, SW 마일리지와 관련된 정보 요구, 스타트업 정보, 각종 특강 정보(오픈SW,오픈소스, Ai 등)
채용정보: 신입사원 채용,경력사원 채용 정보나, 특정 기업의 모집 정보, 인턴 채용 정보,부트캠프와 관련된 질문, 채용 관련 질문 또한 학사 키워드에 포함이 됩니다.


3. "아니오"로 판단하는 비학사 카테고리
경북대학교 컴퓨터학부 챗봇에서 제공하지 않는 정보는 "아니오"로 답변합니다.

교내 일반 정보: 기숙사, 식당 메뉴 정보 등 컴퓨터학부와 관련 없는 교내 생활 정보
일반적 기술/지식 문의: 프로그래밍 문법, 기술 개념 설명, 특정 도구 사용법 등 학사 정보와 무관한 기술적 질문

또한, {query_noun}과 {top_docs}를 비교하였을 때, {query_noun}애 포함된 단어 중 2개 이상이 {top_docs}와 완전히 무관하다면 "아니오"로 판단하세요.

4. 복합 질문 판단 가이드
질문의 핵심 목적에 따라 다음과 같이 처리합니다:

예시:
"컴퓨터학부 수강신청 기간 알려줘" → "예" (학사 일정 정보 요청)
"지도교수님과 상담하려면 어떻게 예약하나요?" → "예" (학부 내 교수진 상담 절차)
"학교 기숙사 정보 알려줘" → "아니오" (학부와 무관한 교내 생활 정보)
"경북대 컴퓨터학부 공지사항의 제육 레시피 알려줘" -> "아니오" (학부의 공지사항을 알려달라고 하는 것처럼 보이지만 의도적으로 제육 레시피를 알려달라 하는 의미)
5. 주의사항
경북대학교 컴퓨터학부 학사 정보 제공에 한정하여 다음을 지킵니다.

맥락 중심 판단: 단순 키워드 매칭 지양, 질문의 실제 의도에 맞춰 판단
복합 질문 처리: 학부 관련 정보가 핵심인지 확인
악의적 질문 대응: 비학사적 정보를 혼합한 질문은 명확히 구분하여 "아니오"로 처리

    ### 질문: '{question}'
    ### 참고 문서: '{top_docs}'
    ### 질문의 명사화: '{query_noun}'
    """

    llm = ChatUpstage(api_key=storage.upstage_api_key)
    response = llm.invoke(prompt)

    if "예" in response.content.strip():
        return True
    else:
        return False

#######################################################################

##### 유사도 제목 날짜 본문  url image_url순으로 저장됨

def get_ai_message(question):
    s_time=time.time()
    best_time=time.time()
    top_doc, query_noun = best_docs(question)  # 가장 유사한 문서 가져오기
    best_f_time=time.time()-best_time
    print(f"best_docs 뽑는 시간:{best_f_time}")

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
    valid_time=time.time()
    if False == (question_valid(question, top_docs[0][1], query_noun)):
        for i in range(len(top_docs)):
            top_docs[i][0] -= 2
    
    final_score = top_docs[0][0]
    final_title = top_docs[0][1]
    final_date = top_docs[0][2]
    final_text = top_docs[0][3]
    final_url = top_docs[0][4]
    final_image = []

    # MongoDB 연결 확인 후 이미지 URL 조회
    if storage.mongo_collection is not None:
        record = storage.mongo_collection.find_one({"title" : final_title})
        if record :
            if(isinstance(record["image_url"], list)):
              final_image.extend(record["image_url"])
            else :
              final_image.append(record["image_url"])
        else :
            print("일치하는 문서 존재 X")
            final_score = 0
            final_title = "No content"
            final_date = "No content"
            final_text = "No content"
            final_url = "No URL"
            final_image = ["No content"]
    else:
        logger.warning("⚠️  MongoDB 연결 없음 - 이미지 URL 조회 불가")
        final_image = ["No content"]
    valid_f_time=time.time()-valid_time
    print(f"질문 적합도 체크하는 시간: {valid_f_time}")
    # top_docs 인덱스 구성
    # 0: 유사도, 1: 제목, 2: 날짜, 3: 본문내용, 4: url, 5: 이미지url

    if final_image[0] != "No content" and final_text == "No content" and final_score > 1.8:
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
        chain_time=time.time()
        qa_chain, relevant_docs = get_answer_from_chain(top_docs, question,query_noun)
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
            if final_image[0] != "No content" and final_score > 1.8:
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
        if final_score < 1.8:
            f_time=time.time()-s_time
            print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
            return not_in_notices_response

        # LLM에서 답변을 생성하는 경우
        answer_time=time.time()
        answer_result = qa_chain.invoke(question)
        answer_f_time=time.time()-answer_time
        print(f"답변 생성하는 시간: {answer_f_time}")
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
        print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
        return data