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

# Services import
from modules.services.document_service import DocumentService
from modules.services.search_service import SearchService
from modules.services.llm_service import LLMService
from modules.services.scoring_service import ScoringService
from modules.services.response_service import ResponseService

# Configuration import
from config.settings import MINIMUM_SIMILARITY_SCORE
from config.prompts import get_qa_prompt, get_temporal_intent_prompt
from config.ml_settings import get_ml_config

# Constants import
from modules.constants import (
    NOTICE_BASE_URL,
    COMPANY_BASE_URL,
    SEMINAR_BASE_URL,
    PROFESSOR_BASE_URL
)

# Utils import
from modules.utils.date_utils import get_current_kst as get_korean_time, parse_date_change_korea_time
from modules.utils.url_utils import find_url
from modules.utils.formatter import format_temporal_intent, format_docs

# StorageManager 싱글톤 인스턴스 가져오기
storage = get_storage_manager()

# Service 인스턴스 생성
document_service = DocumentService(storage)
search_service = SearchService(storage)
llm_service = LLMService(storage)
scoring_service = ScoringService(
    date_parser_fn=parse_date_change_korea_time,
    current_time_fn=get_korean_time
)
response_service = ResponseService(
    storage_manager=storage,
    search_service=search_service,
    llm_service=llm_service
)

# ML 설정 로드
ml_config = get_ml_config()

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

# ==========================================
# Document Service Wrapper Functions
# ==========================================
# 하위 호환성을 위한 wrapper 함수들
# 실제 로직은 DocumentService로 이동됨
# ==========================================

def fetch_titles_from_pinecone():
    """
    [DEPRECATED] DocumentService.fetch_all_documents()로 이동됨
    하위 호환성을 위한 wrapper 함수
    """
    return document_service.fetch_all_documents()


# 캐싱 데이터 초기화 함수

def initialize_cache():
    """
    [DEPRECATED] DocumentService.initialize_cache()로 이동됨
    하위 호환성을 위한 wrapper 함수

    캐시 로드 후 Retriever 초기화도 수행
    """
    # 1. 캐시 로드 (DocumentService)
    document_service.initialize_cache()

    # 2. Retriever 초기화 (ai_modules 책임)
    _initialize_retrievers()


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

# ==========================================
# Scoring Service Wrapper Functions
# ==========================================
# 하위 호환성을 위한 wrapper 함수들
# 실제 로직은 ScoringService로 이동됨
# ==========================================

def calculate_weight_by_days_difference(post_date, current_date, query_nouns):
    """
    [DEPRECATED] ScoringService.calculate_weight_by_days_difference()로 이동됨
    하위 호환성을 위한 wrapper 함수
    """
    return scoring_service.calculate_weight_by_days_difference(post_date, current_date, query_nouns)


def adjust_date_similarity(similarity, date_str, query_nouns):
    """
    [DEPRECATED] ScoringService.adjust_date_similarity()로 이동됨
    하위 호환성을 위한 wrapper 함수
    """
    return scoring_service.adjust_date_similarity(similarity, date_str, query_nouns)


def adjust_similarity_scores(query_noun, title, texts, similarities):
    """
    [DEPRECATED] ScoringService.adjust_similarity_scores()로 이동됨
    하위 호환성을 위한 wrapper 함수
    """
    return scoring_service.adjust_similarity_scores(query_noun, title, texts, similarities)


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

def parse_temporal_intent(query, current_date=None):
      """
      [DEPRECATED] LLMService.parse_temporal_intent()로 이동됨

      질문에서 시간 표현을 감지하고 필터 조건을 반환

      Args:
          query: 사용자 질문
          current_date: 현재 날짜 (기본값: 현재 시각)

      Returns:
          dict: {"year": int, "semester": int} 또는 None
      """
      return llm_service.parse_temporal_intent(query, current_date)


def rewrite_query_with_llm(query, current_date):
      """
      [DEPRECATED] LLMService.rewrite_query_with_llm()로 이동됨

      LLM을 사용해 복잡한 시간 표현을 해석

      Args:
          query: 사용자 질문
          current_date: 현재 날짜

      Returns:
          dict: {"year": int, "semester": int} 또는 None
      """
      return llm_service.rewrite_query_with_llm(query, current_date)


def best_docs(user_question):
      """
      [DEPRECATED] SearchService.search_documents()로 이동됨

      사용자 질문에 대한 가장 관련성 높은 문서 검색

      Args:
          user_question: 사용자의 자연어 질문

      Returns:
          Tuple: (검색된 문서 리스트, 쿼리 키워드 리스트)
      """
      return search_service.search_documents(
          user_question=user_question,
          transformed_query_fn=transformed_query,
          find_url_fn=find_url
      )


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
      """
      [DEPRECATED] LLMService.get_answer_from_chain()로 이동됨

      QA Chain 생성 및 관련 문서 처리

      Args:
          best_docs: 검색된 문서 리스트
          user_question: 사용자 질문
          query_noun: 쿼리 명사 리스트
          temporal_filter: 시간 필터

      Returns:
          Tuple: (qa_chain, relevant_docs, relevant_docs_content)
      """
      return llm_service.get_answer_from_chain(
          best_docs=best_docs,
          user_question=user_question,
          query_noun=query_noun,
          temporal_filter=temporal_filter
      )


#######################################################################

##### 유사도 제목 날짜 본문  url image_url순으로 저장됨

# ==========================================
# Response Service Wrapper Function
# ==========================================
# 하위 호환성을 위한 wrapper 함수
# 실제 로직은 ResponseService로 이동됨
# ==========================================

def get_ai_message(question):
    """
    사용자 질문에 대한 AI 응답 생성

    [REFACTORED] ResponseService.generate_response()로 이동됨
    하위 호환성을 위한 wrapper 함수

    Args:
        question: 사용자 질문

    Returns:
        Dict: 응답 JSON
            {
                "answer": str,
                "answerable": bool,
                "references": str,
                "disclaimer": str,
                "images": List[str]
            }
    """
    return response_service.generate_response(
        question=question,
        transformed_query_fn=transformed_query,
        find_url_fn=find_url,
        minimum_similarity_score=MINIMUM_SIMILARITY_SCORE
    )


# ==========================================
# Legacy get_ai_message Implementation (ARCHIVED)
# ==========================================
# 아래는 이전 get_ai_message 구현입니다.
# ResponseService로 완전히 이동되었으므로 참고용으로만 남깁니다.
# 삭제 가능하지만, 일단 주석 처리하여 보관합니다.
# ==========================================

"""
def get_ai_message_legacy(question):
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
"""