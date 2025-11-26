"""
LLM Service

LLM 기반 작업(시간 의도 파싱, QA Chain 생성)을 담당하는 서비스
"""
import logging
import json
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

from langchain.schema import Document
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_upstage import ChatUpstage

logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM 기반 작업 서비스

    Responsibilities:
    - 시간 의도 파싱 (parse_temporal_intent)
    - LLM 기반 시간 표현 해석 (rewrite_query_with_llm)
    - QA Chain 생성 (get_answer_from_chain)
    """

    def __init__(self, storage_manager):
        """
        Args:
            storage_manager: StorageManager 인스턴스
        """
        self.storage = storage_manager

    def parse_temporal_intent(
        self,
        query: str,
        current_date: Optional[datetime] = None
    ) -> Optional[Dict]:
        """
        질문에서 시간 표현을 감지하고 필터 조건을 반환

        Args:
            query: 사용자 질문
            current_date: 현재 날짜 (기본값: 현재 시각)

        Returns:
            dict: {"year": int, "semester": int, "date_from": datetime} 또는 None

        Examples:
            >>> parse_temporal_intent("이번학기 수강신청")
            {'year': 2024, 'semester': 1}

            >>> parse_temporal_intent("최근 공지사항")
            {'year_from': 2023}
        """
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
        llm_filter = self.rewrite_query_with_llm(query, current_date)
        if llm_filter:
            logger.info(f"✨ LLM 분석 결과: {llm_filter}")
            return llm_filter

        return None

    def rewrite_query_with_llm(
        self,
        query: str,
        current_date: datetime
    ) -> Optional[Dict]:
        """
        LLM을 사용해 복잡한 시간 표현을 해석하고 필터 조건을 생성

        Args:
            query: 사용자 질문
            current_date: 현재 날짜

        Returns:
            dict: {"year": int, "semester": int} 또는 None

        Examples:
            >>> rewrite_query_with_llm("작년 수강신청", datetime(2024, 3, 1))
            {'year': 2023, 'semester': 1, 'is_ongoing': False, 'is_policy': False}
        """
        from config.prompts import get_temporal_intent_prompt

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
            llm = ChatUpstage(api_key=self.storage.upstage_api_key, model="solar-mini")
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

    def get_answer_from_chain(
        self,
        best_docs: List,
        user_question: str,
        query_noun: List[str],
        temporal_filter: Optional[Dict] = None
    ) -> Tuple[Any, List[Document], str]:
        """
        QA Chain 생성 및 관련 문서 처리

        Args:
            best_docs: 검색된 문서 리스트 [(score, title, date, text, url, html, ...), ...]
            user_question: 사용자 질문
            query_noun: 쿼리 명사 리스트
            temporal_filter: 시간 필터 (parse_temporal_intent 결과)

        Returns:
            Tuple[Any, List[Document], str]:
                - qa_chain: LangChain QA Chain
                - relevant_docs: Document 객체 리스트
                - relevant_docs_content: 포맷팅된 컨텍스트 문자열

        Process:
            1. HTML/Markdown 중복 제거
            2. Document 객체 생성
            3. 키워드 필터링 (여러 게시글 혼재 시)
            4. QA Chain 생성
        """
        from modules.utils.date_utils import get_current_kst as get_korean_time
        from modules.utils.formatter import format_temporal_intent, format_docs

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

        logger.info(
            f"   🔄 중복 제거 후: {len(deduplicated_docs)}개 청크 "
            f"({duplicate_html_count}개 Markdown 중복 제거)"
        )
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
                from modules.utils.html_parser import is_markdown, html_to_markdown_with_text

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
            doc_obj = Document(
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
            documents.append(doc_obj)

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
            logger.info(
                f"   ✅ 같은 게시글 청크 감지 → 키워드 필터링 스킵 "
                f"({len(documents)}개 모두 포함)"
            )
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
            api_key=self.storage.upstage_api_key,
            max_tokens=4096  # 긴 명단도 완전히 나열할 수 있도록 충분한 토큰 확보
        )
        relevant_docs_content = format_docs(relevant_docs)

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

        # QA Prompt Template 가져오기
        from modules.ai_modules import get_qa_prompt_template
        PROMPT = get_qa_prompt_template()

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
