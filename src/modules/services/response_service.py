"""
Response Service

사용자 질문에 대한 응답 생성을 총괄하는 서비스
검색, Reranking, LLM 답변 생성, 응답 구조화 등을 오케스트레이션
"""
import time
import json
import re
import logging
from typing import Dict, Any, List, Tuple, Optional

from modules.constants import (
    NOTICE_BASE_URL,
    COMPANY_BASE_URL,
    SEMINAR_BASE_URL,
    PROFESSOR_BASE_URL
)

logger = logging.getLogger(__name__)


class ResponseService:
    """
    응답 생성 오케스트레이션 서비스

    Responsibilities:
    - 사용자 질문 처리 파이프라인 전체 관리
    - 검색 → Reranking → LLM 답변 → 응답 구조화
    - 특수 케이스 처리 (키워드 전용 쿼리, 이미지 전용 등)
    """

    def __init__(self, storage_manager, search_service, llm_service):
        """
        Args:
            storage_manager: StorageManager 인스턴스
            search_service: SearchService 인스턴스
            llm_service: LLMService 인스턴스
        """
        self.storage = storage_manager
        self.search_service = search_service
        self.llm_service = llm_service

    def generate_response(
        self,
        question: str,
        transformed_query_fn,
        find_url_fn,
        minimum_similarity_score: float,
        minimum_reranker_score: float = 0.0  # 하위 호환성 유지 (사용 안함)
    ) -> Dict[str, Any]:
        """
        메인 응답 생성 파이프라인

        Args:
            question: 사용자 질문
            transformed_query_fn: 명사 추출 함수
            find_url_fn: URL 검색 함수
            minimum_similarity_score: 최소 유사도 임계값 (사용 안함, 하위 호환성만)
            minimum_reranker_score: 사용 안함 (하위 호환성만)

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
        s_time = time.time()

        # 검색된 문서 정보 로깅 (가장 먼저!)
        logger.info(f"📝 사용자 질문: {question}")

        # ✅ 시간 의도 파싱 (LLM 답변 시 활용)
        from datetime import datetime
        temporal_filter = self.llm_service.parse_temporal_intent(question, datetime.now())

        best_time = time.time()
        top_doc, query_noun = self.search_service.search_documents(
            user_question=question,
            transformed_query_fn=transformed_query_fn,
            find_url_fn=find_url_fn
        )
        best_f_time = time.time() - best_time
        print(f"best_docs 뽑는 시간:{best_f_time}")
        logger.info(f"🔍 추출된 키워드: {query_noun}")

        # query_noun이 없거나 top_doc이 비어있는 경우 처리
        if not query_noun or not top_doc or len(top_doc) == 0:
            return self._build_no_result_response()

        # 키워드 전용 쿼리 처리 (채용/공지/세미나 목록)
        keyword_response = self._handle_keyword_only_query(top_doc, query_noun, question)
        if keyword_response:
            f_time = time.time() - s_time
            print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
            return keyword_response

        top_docs = [list(doc) for doc in top_doc]

        # ✅ Reranking 전 Top 5 로깅
        logger.info("=" * 60)
        logger.info(f"📊 Reranking 전 검색 결과 Top {min(5, len(top_docs))}:")
        for i, doc in enumerate(top_docs[:5]):
            score, title, date, text, url = doc[:5]
            logger.info(f"   {i+1}위: [{score:.4f}] {title[:50]}... ({date})")
        logger.info("=" * 60)

        # ✅ Reranking 적용
        top_docs, reranking_used = self._apply_reranking(top_docs, question)

        # ✅ Top-k 기반 접근: 상대적 순서(Ranking)만 신뢰, 절대적 임계값 제거
        # 참고: BGE 리랭커 아티클 - "절대적 임계값이 아닌 상대적 순서로 판단"
        if reranking_used:
            logger.info("✅ Reranker 사용 → Top-k 기반 상대적 순서 신뢰")
            logger.info("   (절대적 임계값 제거, LLM answerable이 최종 판단)")
        else:
            logger.info("✅ 초기 검색 → Top-k 사용, LLM에 전달")

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
        final_image = self._fetch_images_from_mongodb(final_title)
        if not final_image:
            final_score = 0
            final_title = "No content"
            final_date = "No content"
            final_text = "No content"
            final_url = "No URL"
            final_image = ["No content"]

        # 이미지만 있고 텍스트가 없는 경우 (Top-k로 선택되었으므로 바로 반환)
        if final_image[0] != "No content" and final_text == "No content":
            only_image_response = {
                "answer": None,
                "references": final_url,
                "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
                "images": final_image
            }
            f_time = time.time() - s_time
            print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
            return only_image_response

        # ✅ 같은 게시글의 모든 청크 수집 (본문 + 첨부파일 + 이미지 OCR)
        top_docs = self._enrich_with_same_document_chunks(top_docs)

        # QA Chain 생성
        chain_time = time.time()
        qa_chain, relevant_docs, relevant_docs_content = self.llm_service.get_answer_from_chain(
            top_docs, question, query_noun, temporal_filter
        )
        chain_f_time = time.time() - chain_time
        print(f"chain 생성하는 시간: {chain_f_time}")

        # 🔍 디버깅: get_answer_from_chain 반환값 확인
        logger.info(f"🔍 get_answer_from_chain 반환값 확인:")
        logger.info(f"   qa_chain: {type(qa_chain)} (None? {qa_chain is None})")
        logger.info(f"   relevant_docs: {type(relevant_docs)} (None? {relevant_docs is None}, 개수: {len(relevant_docs) if relevant_docs else 0})")
        logger.info(f"   relevant_docs_content: {type(relevant_docs_content)} (None? {relevant_docs_content is None})")

        # 교수 연락처 특수 처리
        if final_url == PROFESSOR_BASE_URL + "&lang=kor" and any(keyword in query_noun for keyword in ['연락처', '전화', '번호', '전화번호']):
            data = {
                "answer": "해당 교수님은 연락처 정보가 포함되어 있지 않습니다.\n 자세한 정보는 교수진 페이지를 참고하세요.",
                "answerable": False,  # 연락처 정보 없음
                "references": final_url,
                "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
                "images": final_image
            }
            f_time = time.time() - s_time
            print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
            return data

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
            # Top-k로 선택되었으므로 이미지가 있으면 반환
            if final_image[0] != "No content":
                data = {
                    "answer": "해당 질문에 대한 내용은 이미지 파일로 확인해주세요.",
                    "answerable": True,  # 이미지로 답변 제공
                    "references": final_url,
                    "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
                    "images": final_image
                }
                f_time = time.time() - s_time
                print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
                return data
            else:
                f_time = time.time() - s_time
                print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
                return not_in_notices_response

        # ✅ Top-k 기반 접근: 절대적 임계값 제거
        # Reranker/초기검색이 이미 상대적 순서로 Top-k 선택
        # 최종 판단은 LLM의 answerable 필드에 위임
        logger.info(f"✅ Top-1 문서 선택 완료 (score: {final_score:.4f})")
        logger.info(f"   → LLM에 전달하여 answerable 판단 (절대적 임계값 사용 안함)")

        # LLM에서 답변을 생성하는 경우
        logger.info(f"✅ 모든 조건 통과! LLM 답변 생성 시작...")
        answer_time = time.time()

        # qa_chain.invoke() 사용 (기존 방식 유지)
        answer_result = qa_chain.invoke(question)

        answer_f_time = time.time() - answer_time
        print(f"답변 생성하는 시간: {answer_f_time}")

        # 최종 응답 생성
        data = self._build_final_response(
            answer_result=answer_result,
            relevant_docs=relevant_docs,
            relevant_docs_content=relevant_docs_content,
            final_image=final_image,
            question=question
        )

        f_time = time.time() - s_time
        logger.info(f"✅ 총 처리 시간: {f_time:.2f}초")
        print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
        return data

    def _handle_keyword_only_query(
        self,
        top_doc: List,
        query_noun: List[str],
        user_question: str
    ) -> Optional[Dict[str, Any]]:
        """
        키워드 전용 쿼리 처리 (채용/공지/세미나 목록)

        Args:
            top_doc: 검색된 문서 리스트
            query_noun: 추출된 명사 리스트
            user_question: 사용자 질문

        Returns:
            Optional[Dict]: 키워드 전용 응답 또는 None
        """
        if len(query_noun) == 1 and any(keyword in query_noun for keyword in ['채용', '공지사항', '세미나', '행사', '강연', '특강']):
            seen_urls = set()  # 이미 본 URL을 추적하기 위한 집합
            response = f"'{query_noun[0]}'에 대한 정보 목록입니다:\n\n"
            show_url = ""
            if top_doc != None:
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
            return {
                "answer": response,
                "answerable": True,  # 목록 제공 성공
                "references": show_url,  # show_url을 넘기기
                "disclaimer": "\n\n항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL을 참고하여 정확하고 자세한 정보를 확인하세요.",
                "images": ["No content"]
            }

        return None

    def _apply_reranking(
        self,
        top_docs: List[List],
        question: str
    ) -> Tuple[List[List], bool]:
        """
        BGE-Reranker로 문서 재순위화

        Args:
            top_docs: 검색 결과 문서 리스트
            question: 사용자 질문

        Returns:
            Tuple[List[List], bool]: (재순위화된 문서 리스트, Reranking 사용 여부)
        """
        reranking_used = False
        if self.storage.reranker and len(top_docs) > 1:
            # 현재 사용 중인 Reranker 정보 가져오기
            reranker_info = self.storage.reranker.get_model_info()
            reranker_name = reranker_info.get('name', 'Reranker')
            reranker_model = reranker_info.get('model', '')

            logger.info(f"🎯 {reranker_name} 활성화! (모델: {reranker_model})")
            rerank_time = time.time()
            logger.info(f"   입력: {len(top_docs)}개 문서 → Reranking 시작...")

            # Reranker는 tuple 리스트를 기대하므로 변환
            top_docs_tuples = [tuple(doc) for doc in top_docs]

            # Reranking (어차피 1등만 사용하므로 Top 5로 압축)
            reranked_docs_tuples = self.storage.reranker.rerank(
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
        elif not self.storage.reranker:
            logger.info("⏭️  BGE-Reranker 비활성화 (미설치 또는 로딩 실패)")
            logger.info("   → 원본 검색 순서 유지")
        elif len(top_docs) <= 1:
            logger.info("⏭️  BGE-Reranker 스킵 (문서 1개 이하)")
            logger.info("   → Reranking 불필요")

        return top_docs, reranking_used

    def _enrich_with_same_document_chunks(
        self,
        top_docs: List[List]
    ) -> List[List]:
        """
        같은 게시글의 모든 청크 수집 (본문 + 첨부파일 + 이미지 OCR)

        Args:
            top_docs: 검색 결과 문서 리스트

        Returns:
            List[List]: 확장된 문서 리스트
        """
        enrich_time = time.time()

        # Top 문서의 URL 추출 (게시글 URL)
        top_url = top_docs[0][4] if top_docs else None

        if not top_url:
            return top_docs

        # ✅ 변경: URL 기반 매칭 대신 제목 기반 매칭 사용!
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

        for i, url in enumerate(self.storage.cached_urls):
            # ✅ 같은 게시글인지 확인 (제목 기준 - 이미지/첨부파일 포함!)
            if self.storage.cached_titles[i] == top_title:
                total_checked += 1
                matched_count += 1

                text = self.storage.cached_texts[i]
                content_type = self.storage.cached_content_types[i] if i < len(self.storage.cached_content_types) else "unknown"
                source = self.storage.cached_sources[i] if i < len(self.storage.cached_sources) else "unknown"

                # 디버깅 로그 (처음 5개만)
                if matched_count <= 5:
                    html_data = self.storage.cached_htmls[i] if i < len(self.storage.cached_htmls) else ""
                    logger.info(f"   [{matched_count}] URL: {url[:80]}...")
                    logger.info(f"       타입: {content_type}, 소스: {source}")
                    logger.info(f"       텍스트: {len(text)}자, HTML: {len(html_data)}자")
                    logger.info(f"       인덱스: {i}")

                # 빈 텍스트는 건너뛰지 않음! (중요: "No content"도 포함)
                text_key = ''.join(text.split())  # 공백 제거 후 비교

                # 중복 텍스트 제거 (빈 문자열은 제외하지 않음!)
                if text_key not in seen_texts:
                    seen_texts.add(text_key)
                    enriched_docs.append((
                        top_docs[0][0],  # 점수는 top 문서와 동일
                        self.storage.cached_titles[i],
                        self.storage.cached_dates[i],
                        text,
                        url,
                        self.storage.cached_htmls[i] if i < len(self.storage.cached_htmls) else "",
                        self.storage.cached_content_types[i] if i < len(self.storage.cached_content_types) else "unknown",
                        self.storage.cached_sources[i] if i < len(self.storage.cached_sources) else "unknown",
                        self.storage.cached_attachment_types[i] if i < len(self.storage.cached_attachment_types) else ""
                    ))
                else:
                    duplicate_count += 1

        logger.info(f"   📊 매칭 통계: 전체 {len(self.storage.cached_urls)}개 중 {matched_count}개 매칭, {duplicate_count}개 중복 제거")

        # 청크를 찾았으면 top_docs를 교체 (본문 + 첨부파일 + 이미지)
        if enriched_docs:
            logger.info(f"🔧 같은 게시글의 모든 청크 수집: {len(top_docs)}개 → {len(enriched_docs)}개")

            # 타입별 카운트
            original_post_count = 0
            image_count = 0
            attachment_count = 0

            for i, (score, title, date, text, url, html, content_type, source, attachment_type) in enumerate(enriched_docs):
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

        return top_docs

    def _fetch_images_from_mongodb(self, final_title: str) -> List[str]:
        """
        MongoDB에서 이미지 URL 조회

        Args:
            final_title: 문서 제목

        Returns:
            List[str]: 이미지 URL 리스트
        """
        final_image = []

        if self.storage.mongo_collection is not None:
            record = self.storage.mongo_collection.find_one({"title": final_title})
            if record:
                if isinstance(record["image_url"], list):
                    final_image.extend(record["image_url"])
                else:
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
            else:
                print("일치하는 문서 존재 X")
                logger.warning(f"⚠️  MongoDB에서 문서를 찾을 수 없습니다: {final_title}")
        else:
            logger.warning("⚠️  MongoDB 연결 없음 - 이미지 URL 조회 불가")
            final_image = ["No content"]

        return final_image if final_image else ["No content"]

    def _build_no_result_response(self) -> Dict[str, Any]:
        """
        검색 결과 없음 응답 생성

        Returns:
            Dict: 응답 JSON
        """
        notice_url = NOTICE_BASE_URL
        return {
            "answer": "해당 질문은 공지사항에 없는 내용입니다.\n 자세한 사항은 공지사항을 살펴봐주세요.",
            "answerable": False,  # 검색 결과 없음
            "references": notice_url,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": ["No content"]
        }

    def _build_final_response(
        self,
        answer_result: str,
        relevant_docs: List,
        relevant_docs_content: str,
        final_image: List[str],
        question: str
    ) -> Dict[str, Any]:
        """
        최종 응답 JSON 생성

        Args:
            answer_result: LLM 생성 답변
            relevant_docs: 참고 문서 리스트
            relevant_docs_content: 포맷팅된 컨텍스트
            final_image: 이미지 URL 리스트
            question: 사용자 질문

        Returns:
            Dict: 응답 JSON
        """
        # ✅ JSON 파싱 시도 (LLM이 JSON 형식으로 응답했는지 확인)
        llm_answerable = None  # LLM이 판단한 answerable 값
        llm_answer_text = None  # LLM이 생성한 답변 텍스트

        try:
            # JSON 파싱 시도
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
        return {
            "answer": llm_answer_text,  # JSON 파싱된 답변 또는 원본 답변
            "answerable": answerable,  # 답변 가능 여부
            "references": doc_references,
            "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
            "images": final_image
        }
