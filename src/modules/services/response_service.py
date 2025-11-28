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
from modules.utils.pipeline_logger import get_pipeline_logger

logger = logging.getLogger(__name__)
pipeline_log = get_pipeline_logger("modules")


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

        # ============================================================
        # PHASE 1: 질문 전처리 (Question Preprocessing)
        # ============================================================
        pipeline_log.phase_start(
            phase_num=1,
            title="질문 전처리 (Question Preprocessing)",
            purpose="사용자 질문에서 핵심 키워드와 시간 맥락을 추출하여 검색 최적화"
        )

        pipeline_log.input("사용자 질문", question, truncate=100)

        # 시간 의도 파싱
        from datetime import datetime
        temporal_filter = self.llm_service.parse_temporal_intent(question, datetime.now())

        if temporal_filter:
            pipeline_log.metric("시간 의도 감지", "YES")
            pipeline_log.debug_data("Temporal Filter", {
                "year": temporal_filter.get('year', '미지정'),
                "semester": temporal_filter.get('semester', '미지정'),
                "is_ongoing": temporal_filter.get('is_ongoing', False)
            })
        else:
            pipeline_log.metric("시간 의도 감지", "NO")

        # 문서 검색 및 키워드 추출
        with pipeline_log.timer("초기 검색 (BM25 + Dense Retrieval)"):
            top_doc, query_noun = self.search_service.search_documents(
                user_question=question,
                transformed_query_fn=transformed_query_fn,
                find_url_fn=find_url_fn
            )

        pipeline_log.output("추출된 키워드", query_noun)
        pipeline_log.metric("검색 결과 개수", len(top_doc) if top_doc else 0, "개")

        pipeline_log.phase_end(
            phase_num=1,
            summary=f"{len(query_noun) if query_noun else 0}개 키워드 추출, {len(top_doc) if top_doc else 0}개 문서 검색"
        )

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

        # ============================================================
        # PHASE 2: Reranking (문서 재순위화)
        # ============================================================
        pipeline_log.phase_start(
            phase_num=2,
            title="Reranking (문서 재순위화)",
            purpose="Semantic 유사도 기반으로 검색 결과를 재정렬하여 정확도 향상"
        )

        # Reranking 전 Top 10 표시 (연산에 사용되는 모든 항목)
        pipeline_log.ranking_table(
            title="Reranking 전 검색 결과",
            items=[{
                "rank": i+1,
                "score": doc[0],
                "title": doc[1],
                "date": doc[2],
                "url": doc[4]
            } for i, doc in enumerate(top_docs[:10])],
            top_k=10
        )

        # Reranking 적용
        top_docs, reranking_used = self._apply_reranking(top_docs, question)

        pipeline_log.metric("Reranker 사용 여부", "YES" if reranking_used else "NO")
        pipeline_log.phase_end(
            phase_num=2,
            summary=f"{'Reranking 완료' if reranking_used else '원본 순서 유지'} ({len(top_docs)}개 문서)"
        )

        # ============================================================
        # PHASE 3: Temporal Re-boosting (시간 맥락 보정)
        # ============================================================
        if temporal_filter and reranking_used:
            pipeline_log.phase_start(
                phase_num=3,
                title="Temporal Re-boosting (시간 맥락 보정)",
                purpose="Reranker가 무시한 시간 정보를 다시 반영하여 최신성/관련성 향상"
            )

            top_docs = self._apply_temporal_reboosting(top_docs, temporal_filter, reranking_used)

            pipeline_log.phase_end(
                phase_num=3,
                summary="시간 맥락 기반 점수 조정 완료"
            )
        else:
            top_docs = self._apply_temporal_reboosting(top_docs, temporal_filter, reranking_used)

        # ✅ 하이브리드 필터링: 극단적으로 낮은 점수만 사전 제거
        # - Top-k 기반 접근을 유지하되, "절대 불가능한" 케이스만 필터링
        # - BGE: 매우 낮은 음수 (-8 이하), Cohere: 거의 0에 가까운 값 (0.01 이하)
        # - 초기 검색(BM25+Dense): 0.5 이하 (거의 관련 없음)
        if top_docs and len(top_docs) > 0:
            top_score = top_docs[0][0]

            # Reranker 사용 시: 극단적 저점수 필터링
            if reranking_used:
                # BGE는 음수도 가능, Cohere는 0~1 범위
                # 매우 보수적인 임계값: BGE -8 이하, Cohere 0.01 이하만 제거
                EXTREME_LOW_THRESHOLD = -8.0  # BGE 기준
                if top_score < EXTREME_LOW_THRESHOLD:
                    logger.warning(f"⚠️ 극단적 저점수 감지: {top_score:.4f} < {EXTREME_LOW_THRESHOLD}")
                    logger.warning(f"   → 검색 결과가 질문과 거의 무관할 가능성 높음")
                    f_time = time.time() - s_time
                    print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
                    return self._build_no_result_response()

            # 초기 검색 시: 0.5 이하만 제거 (BM25+Dense 스케일)
            else:
                INITIAL_SEARCH_LOW_THRESHOLD = 0.5
                if top_score < INITIAL_SEARCH_LOW_THRESHOLD:
                    logger.warning(f"⚠️ 초기 검색 저점수 감지: {top_score:.4f} < {INITIAL_SEARCH_LOW_THRESHOLD}")
                    logger.warning(f"   → 검색 결과가 질문과 거의 무관할 가능성 높음")
                    f_time = time.time() - s_time
                    print(f"get_ai_message 총 돌아가는 시간 : {f_time}")
                    return self._build_no_result_response()

        # ✅ Top-k 기반 접근: 상대적 순서(Ranking)만 신뢰
        # 참고: BGE 리랭커 아티클 - "절대적 임계값이 아닌 상대적 순서로 판단"
        if reranking_used:
            logger.info("✅ Reranker 사용 → Top-k 기반 상대적 순서 신뢰")
            logger.info("   (극단적 저점수 필터링 후, LLM answerable이 최종 판단)")
        else:
            logger.info("✅ 초기 검색 → Top-k 사용, LLM에 전달")
            logger.info("   (극단적 저점수 필터링 후, LLM answerable이 최종 판단)")

        # ============================================================
        # PHASE 4: 최종 문서 선택 및 검증
        # ============================================================
        pipeline_log.phase_start(
            phase_num=4,
            title="최종 문서 선택 및 검증",
            purpose="Top-5 서로 다른 문서 선택 후 점수 검증 및 다양성 확인"
        )

        # Reranking 후 Top 5 표시 (다양성 확인)
        seen_urls = set()
        unique_url_count = 0
        ranking_items = []

        for i, doc in enumerate(top_docs[:10]):  # Top 10까지 확인 (중복 고려)
            score, title, date, text, url = doc[:5]

            # URL 중복 체크
            if url not in seen_urls:
                seen_urls.add(url)
                unique_url_count += 1
                marker = "🆕"  # 새로운 URL
            else:
                marker = "🔁"  # 중복 URL (같은 문서의 다른 청크)

            ranking_items.append({
                "rank": i+1,
                "score": score,
                "title": title,
                "date": date,
                "url": url,
                "marker": marker
            })

        pipeline_log.ranking_table(
            title="최종 순위 (Reranking 후)",
            items=ranking_items,
            top_k=10
        )

        pipeline_log.metric("문서 다양성", f"Top 10 중 {unique_url_count}개 서로 다른 문서")

        # ✅ 변경: Top-5 서로 다른 문서 추출
        top_k_unique_docs = []
        seen_titles = set()

        for doc in top_docs:
            title = doc[1]
            # 제목 기준으로 중복 제거 (같은 게시글의 다른 청크는 나중에 확장)
            if title not in seen_titles:
                seen_titles.add(title)
                top_k_unique_docs.append(doc)
                if len(top_k_unique_docs) >= 5:
                    break

        # Top-5 서로 다른 문서를 통일된 양식으로 표시
        pipeline_log.ranking_table(
            title="Top-5 서로 다른 문서 선택 (최종 확장 대상)",
            items=[{
                "rank": i+1,
                "score": doc[0],
                "title": doc[1],
                "date": doc[2],
                "url": doc[4]
            } for i, doc in enumerate(top_k_unique_docs)],
            top_k=5
        )

        # Top-1 정보 저장 (이미지 조회 및 backward compatibility)
        final_score = top_k_unique_docs[0][0] if top_k_unique_docs else 0
        final_title = top_k_unique_docs[0][1] if top_k_unique_docs else "No content"
        final_date = top_k_unique_docs[0][2] if top_k_unique_docs else "No content"
        final_text = top_k_unique_docs[0][3] if top_k_unique_docs else "No content"
        final_url = top_k_unique_docs[0][4] if top_k_unique_docs else "No URL"
        final_image = []

        pipeline_log.phase_end(
            phase_num=4,
            summary=f"Top-5 서로 다른 문서 선택 완료 ({len(top_k_unique_docs)}개)"
        )

        # MongoDB 연결 확인 후 이미지 URL 조회 (Top-1 문서만, 하위호환성)
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

        # ============================================================
        # PHASE 5: 문서 확장 (Document Enrichment)
        # ============================================================
        pipeline_log.phase_start(
            phase_num=5,
            title="문서 확장 (Document Enrichment)",
            purpose="Top-5 문서 각각의 모든 청크(본문/첨부파일/이미지) 수집"
        )

        pipeline_log.input("선택된 고유 문서 수", f"{len(top_k_unique_docs)}개")
        for i, doc in enumerate(top_k_unique_docs, 1):
            title = doc[1]
            pipeline_log.substep(f"{i}위: {title[:50]}...")

        enriched_docs = self._enrich_with_same_document_chunks(top_k_unique_docs)

        pipeline_log.output("확장된 총 청크 개수", f"{len(enriched_docs)}개")
        pipeline_log.phase_end(
            phase_num=5,
            summary=f"Top-{len(top_k_unique_docs)}개 문서 → {len(enriched_docs)}개 청크로 확장 완료"
        )

        # ============================================================
        # PHASE 6: LLM 답변 생성 (Answer Generation)
        # ============================================================
        pipeline_log.phase_start(
            phase_num=6,
            title="LLM 답변 생성 (Answer Generation)",
            purpose="확장된 문서를 Context로 LLM에 전달하여 자연어 답변 생성"
        )

        with pipeline_log.timer("QA Chain 생성"):
            qa_chain, relevant_docs, relevant_docs_content = self.llm_service.get_answer_from_chain(
                enriched_docs, question, query_noun, temporal_filter
            )

        pipeline_log.metric("LLM 전달 문서 개수", f"{len(relevant_docs) if relevant_docs else 0}개")
        pipeline_log.metric("LLM 전달 Context 길이", f"{len(relevant_docs_content) if relevant_docs_content else 0}자")

        # ✅ LLM에 전달되는 각 문서 명확히 표시
        if relevant_docs:
            pipeline_log.section("LLM에 전달되는 문서 목록", "📋")

            # 문서 제목별로 그룹화하여 표시
            doc_by_title = {}
            for doc in relevant_docs:
                title = doc.metadata.get('title', 'Unknown')
                source = doc.metadata.get('source', 'unknown')
                content_type = doc.metadata.get('content_type', 'unknown')

                if title not in doc_by_title:
                    doc_by_title[title] = {
                        'title': title,
                        'url': doc.metadata.get('url', 'N/A'),
                        'date': doc.metadata.get('date', 'N/A'),
                        'chunks': []
                    }

                # 개행 제거하여 한 줄로 표시
                content_preview = doc.page_content.replace('\n', ' ').replace('\r', ' ')[:100]
                doc_by_title[title]['chunks'].append({
                    'source': source,
                    'content_type': content_type,
                    'content': content_preview
                })

            # 문서별로 구분하여 표시
            for idx, (title, info) in enumerate(doc_by_title.items(), 1):
                pipeline_log.substep(f"[문서 {idx}] {title[:70]}")
                pipeline_log.substep(f"   📅 날짜: {info['date']}")
                pipeline_log.substep(f"   🔗 URL: {info['url'][:80]}")
                pipeline_log.substep(f"   📦 청크 개수: {len(info['chunks'])}개")

                # 각 청크의 타입 표시
                chunk_types = {}
                for chunk in info['chunks']:
                    source = chunk['source']
                    chunk_types[source] = chunk_types.get(source, 0) + 1

                chunk_summary = ", ".join([f"{src}: {cnt}개" for src, cnt in chunk_types.items()])
                pipeline_log.substep(f"   🏷️  청크 구성: {chunk_summary}")

                # 첫 번째 청크 미리보기
                if info['chunks']:
                    pipeline_log.substep(f"   📄 미리보기: {info['chunks'][0]['content']}...")

                # 문서 구분선
                if idx < len(doc_by_title):
                    pipeline_log.substep("   " + "-" * 70)

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

        # LLM 답변 생성 실행
        pipeline_log.substep("LLM 답변 생성 시작...")

        with pipeline_log.timer("LLM 답변 생성"):
            answer_result = qa_chain.invoke(question)

        pipeline_log.output("LLM 답변 길이", f"{len(answer_result)}자")
        pipeline_log.output("LLM 답변 미리보기", answer_result[:150], truncate=150)

        pipeline_log.phase_end(
            phase_num=6,
            summary=f"LLM 답변 생성 완료 ({len(answer_result)}자)"
        )

        # ============================================================
        # PHASE 7: 응답 구조화 (Response Formatting)
        # ============================================================
        pipeline_log.phase_start(
            phase_num=7,
            title="응답 구조화 (Response Formatting)",
            purpose="LLM 답변을 검증하고 answerable 판단, 참고문서 및 경고 추가"
        )

        # 최종 응답 생성
        data = self._build_final_response(
            answer_result=answer_result,
            relevant_docs=relevant_docs,
            relevant_docs_content=relevant_docs_content,
            final_image=final_image,
            question=question,
            temporal_filter=temporal_filter,
            final_date=final_date
        )

        pipeline_log.metric("answerable 판단", "YES" if data['answerable'] else "NO")
        pipeline_log.metric("이미지 개수", f"{len(data['images'])}개")

        pipeline_log.phase_end(
            phase_num=7,
            summary=f"응답 구조화 완료 (answerable: {data['answerable']})"
        )

        # ============================================================
        # 전체 파이프라인 완료
        # ============================================================
        f_time = time.time() - s_time
        pipeline_log.logger.info("")
        pipeline_log.logger.info("=" * 80)
        pipeline_log.logger.info(f"✅ RAG 파이프라인 전체 완료")
        pipeline_log.logger.info(f"⏱️  총 처리 시간: {f_time:.2f}초")
        pipeline_log.logger.info("=" * 80)

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

    def _apply_temporal_reboosting(
        self,
        top_docs: List[List],
        temporal_filter: Dict,
        reranking_used: bool
    ) -> List[List]:
        """
        Reranking 후 시간 맥락 기반 점수 재조정

        Reranker는 semantic similarity만 고려하고 날짜를 무시하므로,
        사용자가 명시한 시간 정보(년도/학기)나 "현재 진행중" 의도에 따라 부스팅 적용

        Args:
            top_docs: Reranking된 문서 리스트
            temporal_filter: 시간 의도 파싱 결과
                - year: 명시된 년도 (예: 2024)
                - semester: 명시된 학기 (예: 1, 2)
                - is_ongoing: 현재 진행중 의도
            reranking_used: Reranking 사용 여부

        Returns:
            List[List]: 시간 맥락 고려하여 재정렬된 문서 리스트
        """
        from datetime import datetime
        from dateutil.parser import parse

        # Reranking 사용 안했거나, 시간 의도가 없으면 스킵
        if not reranking_used or not temporal_filter:
            return top_docs

        # 명시적 시간 정보 (year/semester) 또는 is_ongoing이 없으면 스킵
        has_explicit_time = temporal_filter.get('year') or temporal_filter.get('semester')
        has_ongoing = temporal_filter.get('is_ongoing')

        if not has_explicit_time and not has_ongoing:
            return top_docs

        logger.info("=" * 60)
        logger.info("🕐 Temporal Re-boosting 시작 (Reranker의 시간 무시 보정)")

        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        # 현재 학기 판단 (3~8월: 1학기, 9~2월: 2학기)
        if 3 <= current_month <= 8:
            current_semester = 1
        else:
            current_semester = 2

        # 사용자가 명시한 시간 정보
        target_year = temporal_filter.get('year')
        target_semester = temporal_filter.get('semester')

        # 부스팅 모드 결정
        if has_explicit_time:
            # Mode 1: Explicit Year/Semester (명시적 시간 지정)
            mode = "explicit"
            logger.info(f"   모드: Explicit Temporal Boosting")
            logger.info(f"   사용자 지정: {target_year or '미지정'}년 {target_semester or '미지정'}학기")
        else:
            # Mode 2: Ongoing (현재 진행중 의도)
            mode = "ongoing"
            target_year = current_year
            target_semester = current_semester
            logger.info(f"   모드: Ongoing Temporal Boosting")
            logger.info(f"   사용자 의도: 현재 진행중 정보 찾기 (is_ongoing=true)")

        logger.info(f"   현재: {current_year}년 {current_semester}학기 ({current_date.strftime('%Y-%m-%d')})")

        # Re-boosting 전 Top 3 로깅
        logger.info(f"   📊 Re-boosting 전 Top 3:")
        for i, doc in enumerate(top_docs[:3]):
            score, title, date, _, _ = doc[:5]
            logger.info(f"      {i+1}위: [{score:.4f}] {title[:40]}... ({date})")

        # 각 문서에 대해 시간 맥락 기반 점수 조정
        for doc in top_docs:
            original_score = doc[0]
            doc_date_str = doc[2]  # ISO 8601 형식 날짜
            doc_title = doc[1]

            try:
                doc_date = parse(doc_date_str)
                doc_year = doc_date.year
                doc_month = doc_date.month

                # 문서 학기 판단
                if 3 <= doc_month <= 8:
                    doc_semester = 1
                else:
                    doc_semester = 2

                # 시간 맥락 기반 부스팅 계산
                boost_factor = 1.0
                reason = ""

                if mode == "explicit":
                    # ✅ Explicit Mode: 사용자가 명시한 년도/학기에 부스팅

                    # 1. Exact Match (년도 + 학기 모두 일치)
                    if (target_year and doc_year == target_year and
                        target_semester and doc_semester == target_semester):
                        boost_factor = 2.0  # 100% 부스팅
                        reason = f"정확히 일치 ({target_year}년 {target_semester}학기)"

                    # 2. Year Match (년도만 일치, 학기 미지정 또는 불일치)
                    elif target_year and doc_year == target_year:
                        if target_semester is None:
                            boost_factor = 1.8  # 80% 부스팅 (년도만 지정했고 일치)
                            reason = f"년도 일치 ({target_year}년)"
                        else:
                            boost_factor = 1.3  # 30% 부스팅 (년도 일치, 학기 불일치)
                            reason = f"년도만 일치 ({target_year}년, 학기 다름)"

                    # 3. Semester Match (학기만 일치, 년도 미지정 또는 불일치)
                    elif target_semester and doc_semester == target_semester:
                        if target_year is None:
                            boost_factor = 1.5  # 50% 부스팅 (학기만 지정했고 일치)
                            reason = f"학기 일치 ({target_semester}학기)"
                        else:
                            boost_factor = 0.9  # 10% 페널티 (학기 일치, 년도 불일치)
                            reason = f"학기만 일치 ({target_semester}학기, 년도 다름)"

                    # 4. 완전 불일치
                    else:
                        boost_factor = 0.6  # 40% 페널티
                        reason = f"불일치 (문서: {doc_year}년 {doc_semester}학기)"

                else:
                    # ✅ Ongoing Mode: 현재 학기에 부스팅 (기존 로직)

                    # 1. 현재 학기 문서: 강력한 부스팅
                    if doc_year == current_year and doc_semester == current_semester:
                        boost_factor = 1.8  # 80% 부스팅
                        reason = f"현재 학기 ({current_year}년 {current_semester}학기)"

                    # 2. 현재 연도 다른 학기: 중간 부스팅
                    elif doc_year == current_year and doc_semester != current_semester:
                        boost_factor = 1.3  # 30% 부스팅
                        reason = f"현재 연도 다른 학기 ({current_year}년 {doc_semester}학기)"

                    # 3. 1년 전: 약간 페널티
                    elif doc_year == current_year - 1:
                        boost_factor = 0.85  # 15% 페널티
                        reason = f"1년 전 ({doc_year}년)"

                    # 4. 2년 이상 전: 강한 페널티
                    elif doc_year < current_year - 1:
                        boost_factor = 0.6  # 40% 페널티
                        reason = f"2년 이상 전 ({doc_year}년)"

                # 점수 조정
                doc[0] = original_score * boost_factor

                if boost_factor != 1.0:
                    logger.info(f"      📅 {doc_title[:30]}...")
                    logger.info(f"         {original_score:.4f} → {doc[0]:.4f} (×{boost_factor:.2f}, {reason})")

            except Exception as e:
                logger.warning(f"   ⚠️ 날짜 파싱 실패: {doc_date_str} ({e})")
                continue

        # 재정렬 (점수 기준 내림차순)
        top_docs.sort(key=lambda x: x[0], reverse=True)

        # Re-boosting 후 Top 3 로깅
        logger.info(f"   🔝 Re-boosting 후 Top 3:")
        for i, doc in enumerate(top_docs[:3]):
            score, title, date, _, _ = doc[:5]
            logger.info(f"      {i+1}위: [{score:.4f}] {title[:40]}... ({date})")

        logger.info("=" * 60)

        return top_docs

    def _enrich_with_same_document_chunks(
        self,
        unique_docs: List[List]
    ) -> List[List]:
        """
        Top-K 서로 다른 문서의 모든 청크 수집 (본문 + 첨부파일 + 이미지 OCR)

        Args:
            unique_docs: Top-K 서로 다른 문서 리스트 (제목 기준 중복 제거됨)

        Returns:
            List[List]: 모든 문서의 확장된 청크 리스트
        """
        enrich_time = time.time()

        if not unique_docs:
            return []

        pipeline_log = get_pipeline_logger()
        all_enriched_docs = []
        seen_texts = set()  # 전역 중복 텍스트 제거용

        # 각 고유 문서에 대해 청크 수집
        for doc_idx, unique_doc in enumerate(unique_docs, 1):
            doc_score = unique_doc[0]
            doc_title = unique_doc[1]
            doc_url = unique_doc[4]

            wr_id = doc_url.split('&wr_id=')[-1] if '&wr_id=' in doc_url else doc_url.split('wr_id=')[-1] if 'wr_id=' in doc_url else None

            pipeline_log.substep(f"[{doc_idx}/{len(unique_docs)}] '{doc_title[:40]}...' 청크 수집 중...")

            # 같은 게시글의 모든 청크 찾기
            doc_chunks = []
            matched_count = 0
            duplicate_count = 0

            for i, cached_title in enumerate(self.storage.cached_titles):
                # 제목 기준 매칭 (이미지/첨부파일 포함)
                if cached_title == doc_title:
                    matched_count += 1

                    text = self.storage.cached_texts[i]
                    url = self.storage.cached_urls[i]
                    content_type = self.storage.cached_content_types[i] if i < len(self.storage.cached_content_types) else "unknown"
                    source = self.storage.cached_sources[i] if i < len(self.storage.cached_sources) else "unknown"

                    # 중복 텍스트 제거
                    text_key = ''.join(text.split())  # 공백 제거 후 비교

                    if text_key not in seen_texts:
                        seen_texts.add(text_key)
                        doc_chunks.append((
                            doc_score,  # 원본 문서의 점수 유지
                            self.storage.cached_titles[i],
                            self.storage.cached_dates[i],
                            text,
                            url,
                            self.storage.cached_htmls[i] if i < len(self.storage.cached_htmls) else "",
                            content_type,
                            source,
                            self.storage.cached_attachment_types[i] if i < len(self.storage.cached_attachment_types) else ""
                        ))
                    else:
                        duplicate_count += 1

            # 타입별 카운트
            original_post_count = sum(1 for chunk in doc_chunks if chunk[7] == "original_post")
            image_count = sum(1 for chunk in doc_chunks if chunk[7] == "image_ocr")
            attachment_count = sum(1 for chunk in doc_chunks if chunk[7] == "document_parse")

            pipeline_log.substep(
                f"   → {len(doc_chunks)}개 청크 수집 "
                f"(본문: {original_post_count}, 이미지: {image_count}, 첨부: {attachment_count}, 중복제거: {duplicate_count})"
            )

            all_enriched_docs.extend(doc_chunks)

        enrich_f_time = time.time() - enrich_time
        pipeline_log.metric("총 청크 수집 시간", f"{enrich_f_time:.2f}초")

        return all_enriched_docs

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
        question: str,
        temporal_filter: Dict = None,
        final_date: str = None
    ) -> Dict[str, Any]:
        """
        최종 응답 JSON 생성

        Args:
            answer_result: LLM 생성 답변
            relevant_docs: 참고 문서 리스트
            relevant_docs_content: 포맷팅된 컨텍스트
            final_image: 이미지 URL 리스트
            question: 사용자 질문
            temporal_filter: 시간 의도 파싱 결과
            final_date: 선택된 문서 날짜

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

            # ✅ Safety Net: LLM이 answerable=true로 판단했지만 답변에 부정 패턴이 있으면 false로 보정
            if answerable:
                # 부정 패턴 목록 (프롬프트와 동일하게 유지)
                negative_patterns = [
                    "에 대한 내용은 없습니다",
                    "에 대한 정보는 없습니다",
                    "정보는 찾을 수 없습니다",
                    "는 명시되어 있지 않습니다",
                    "는 언급되어 있지 않습니다",
                    "에서는 찾을 수 없습니다",
                    "관련 내용이 없습니다",
                    "포함되어 있지 않습니다"
                ]

                # 답변 텍스트에서 부정 패턴 검사
                if any(pattern in llm_answer_text for pattern in negative_patterns):
                    logger.warning(f"⚠️ LLM answerable 오판 감지 (부정 패턴)!")
                    logger.warning(f"   - LLM 판단: answerable=true")
                    logger.warning(f"   - 하지만 답변에 부정 패턴 포함: {[p for p in negative_patterns if p in llm_answer_text]}")
                    logger.warning(f"   - 답변 미리보기: {llm_answer_text[:200]}...")
                    logger.warning(f"   → answerable=false로 보정")
                    answerable = False

            # ✅ Temporal Validation: 현재 진행중 질문인데 과거 데이터로 답변하면 false
            if answerable and temporal_filter and temporal_filter.get('is_ongoing') and final_date:
                from datetime import datetime
                from dateutil.parser import parse

                try:
                    doc_date = parse(final_date)
                    current_date = datetime.now()
                    doc_year = doc_date.year
                    current_year = current_date.year

                    # 1년 이상 차이나면 과거 데이터로 판단
                    if doc_year < current_year:
                        logger.warning(f"⚠️ LLM answerable 오판 감지 (시간 맥락 불일치)!")
                        logger.warning(f"   - LLM 판단: answerable=true")
                        logger.warning(f"   - 사용자 의도: 현재 진행중 정보 (is_ongoing=true)")
                        logger.warning(f"   - 문서 날짜: {doc_year}년 (현재: {current_year}년)")
                        logger.warning(f"   - 시간 차이: {current_year - doc_year}년 전")
                        logger.warning(f"   → answerable=false로 보정")

                        # 답변에 과거 데이터라는 경고 추가
                        year_diff = current_year - doc_year
                        warning_prefix = f"⚠️ 주의: 제공된 문서는 {doc_year}년 자료입니다 ({year_diff}년 전). "
                        if not llm_answer_text.startswith("⚠️"):
                            llm_answer_text = warning_prefix + llm_answer_text

                        # 현재 정보는 최신 공지 확인 안내 추가
                        if "최신 공지" not in llm_answer_text and "공지사항을 확인" not in llm_answer_text:
                            llm_answer_text += f" 현재 {current_year}년 정보는 최신 공지사항을 확인해주세요."

                        answerable = False

                except Exception as e:
                    logger.warning(f"   ⚠️ Temporal Validation 실패: {e}")
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
