"""
크롤러 메인 실행 스크립트

기능:
- 경북대 컴퓨터학부 웹사이트 크롤링 (공지사항, 채용정보, 세미나, 교수정보)
- 증분 크롤링으로 새 게시글만 처리
- 문서 처리 및 임베딩 생성
- Pinecone 벡터 DB에 업로드

실행 방법:
    python run_crawler.py
    또는
    docker exec -it knu-chatbot-app python /app/src/modules/run_crawler.py
"""
import sys
from pathlib import Path

# modules 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from pymongo import MongoClient
from config import CrawlerConfig
from state import CrawlStateManager
from processing import DocumentProcessor, EmbeddingManager
from processing.multimodal_processor import MultimodalProcessor
from crawling import (
    NoticeCrawler,
    JobCrawler,
    SeminarCrawler,
    ProfessorCrawler
)
from crawling.professor_crawler import GuestProfessorCrawler, StaffCrawler
from utils.logging_config import get_logger, close_logger


def main():
    """메인 크롤링 실행 함수"""

    # 로거 초기화
    logger = get_logger()

    try:
        # MongoDB 클라이언트 초기화
        mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)

        # 각 컴포넌트 초기화
        state_manager = CrawlStateManager(mongo_client)
        multimodal_processor = MultimodalProcessor(mongo_client=mongo_client)
        document_processor = DocumentProcessor(
            mongo_client=mongo_client,
            multimodal_processor=multimodal_processor,
            enable_multimodal=True
        )
        embedding_manager = EmbeddingManager()

        logger.section_start("🚀 멀티모달 RAG 크롤러 시작")

        # 현재 크롤링 상태 출력
        state_manager.print_status()

        # 전체 임베딩 아이템 저장용
        all_embedding_items = []

        # ========== 1. 공지사항 크롤링 ==========
        logger.section_start("📋 1. 공지사항 크롤링")

        notice_crawler = NoticeCrawler()
        notice_latest_id = notice_crawler.get_latest_id()

        if notice_latest_id:
            logger.info(f"✅ 최신 공지사항 ID: {notice_latest_id}")

            # 증분 크롤링: 새 게시글만 크롤링
            crawl_range = state_manager.get_crawl_range('notice', notice_latest_id)

            if len(crawl_range) > 0:
                logger.info(f"🔍 크롤링할 범위: {notice_latest_id} ~ {crawl_range[-1] + 1} ({len(crawl_range)}개)")

                # URL 생성 및 크롤링
                notice_urls = notice_crawler.generate_urls(crawl_range)

                # 추가 URL (특정 공지사항)
                additional_urls = [
                    f"{CrawlerConfig.BASE_URLS['notice']}&wr_id={wr_id}"
                    for wr_id in CrawlerConfig.ADDITIONAL_NOTICE_IDS
                ]
                notice_urls.extend(additional_urls)

                # 크롤링 실행
                notice_data = notice_crawler.crawl_urls(notice_urls)

                # 멀티모달 문서 처리 (중복 체크, OCR, 첨부파일 파싱 포함)
                embedding_items, new_count = document_processor.process_documents_multimodal(notice_data, category="notice")

                all_embedding_items.extend(embedding_items)

                # 상태 업데이트
                state_manager.update_last_processed_id('notice', notice_latest_id, new_count)
                logger.info(f"✅ 공지사항 처리 완료: {new_count}개 새 문서, {len(embedding_items)}개 임베딩 아이템")
            else:
                logger.info("ℹ️  새 공지사항이 없습니다.")
        else:
            logger.error("❌ 공지사항 최신 ID 조회 실패")

        # ========== 2. 채용정보 크롤링 ==========
        logger.section_start("💼 2. 채용정보 크롤링")

        job_crawler = JobCrawler()
        job_latest_id = job_crawler.get_latest_id()

        if job_latest_id:
            logger.info(f"✅ 최신 채용정보 ID: {job_latest_id}")

            crawl_range = state_manager.get_crawl_range('job', job_latest_id)

            if len(crawl_range) > 0:
                logger.info(f"🔍 크롤링할 범위: {job_latest_id} ~ {crawl_range[-1] + 1} ({len(crawl_range)}개)")

                job_urls = job_crawler.generate_urls(crawl_range)
                job_data = job_crawler.crawl_urls(job_urls)

                embedding_items, new_count = document_processor.process_documents_multimodal(job_data, category="job")

                all_embedding_items.extend(embedding_items)

                state_manager.update_last_processed_id('job', job_latest_id, new_count)
                logger.info(f"✅ 채용정보 처리 완료: {new_count}개 새 문서, {len(embedding_items)}개 임베딩 아이템")
            else:
                logger.info("ℹ️  새 채용정보가 없습니다.")
        else:
            logger.error("❌ 채용정보 최신 ID 조회 실패")

        # ========== 3. 세미나 크롤링 ==========
        logger.section_start("🎓 3. 세미나 크롤링")

        seminar_crawler = SeminarCrawler()
        seminar_latest_id = seminar_crawler.get_latest_id()

        if seminar_latest_id:
            logger.info(f"✅ 최신 세미나 ID: {seminar_latest_id}")

            crawl_range = state_manager.get_crawl_range('seminar', seminar_latest_id)

            if len(crawl_range) > 0:
                logger.info(f"🔍 크롤링할 범위: {seminar_latest_id} ~ {crawl_range[-1] + 1} ({len(crawl_range)}개)")

                seminar_urls = seminar_crawler.generate_urls(crawl_range)
                seminar_data = seminar_crawler.crawl_urls(seminar_urls)

                embedding_items, new_count = document_processor.process_documents_multimodal(seminar_data, category="seminar")

                all_embedding_items.extend(embedding_items)

                state_manager.update_last_processed_id('seminar', seminar_latest_id, new_count)
                logger.info(f"✅ 세미나 처리 완료: {new_count}개 새 문서, {len(embedding_items)}개 임베딩 아이템")
            else:
                logger.info("ℹ️  새 세미나가 없습니다.")
        else:
            logger.error("❌ 세미나 최신 ID 조회 실패")

        # ========== 4. 교수 정보 크롤링 ==========
        logger.section_start("👨‍🏫 4. 교수 및 직원 정보 크롤링")

        # 정교수
        professor_crawler = ProfessorCrawler()
        professor_data = professor_crawler.crawl_all()

        # 초빙교수
        guest_professor_crawler = GuestProfessorCrawler()
        guest_professor_data = guest_professor_crawler.crawl_all()

        # 직원
        staff_crawler = StaffCrawler()
        staff_data = staff_crawler.crawl_all()

        # 합치기
        combined_professor_data = professor_data + guest_professor_data + staff_data

        # 교수/직원 정보는 텍스트만 처리 (이미지 OCR, 첨부파일 파싱 제외)
        # 교수 크롤러 형식: (title, text_content, image_list, attachment_list, date, url)
        for title, text_content, image_list, attachment_list, date, url in combined_professor_data:
            metadata = {
                "title": title,
                "url": url,
                "date": date,
                "content_type": "text",
                "source": "professor_info"
            }
            all_embedding_items.append((text_content, metadata))

        logger.info(f"✅ 교수/직원 정보 처리 완료: {len(combined_professor_data)}개 문서")

        # ========== 5. 임베딩 생성 및 업로드 (멀티모달) ==========
        logger.section_start("🔄 5. 멀티모달 임베딩 생성 및 Pinecone 업로드")

        if all_embedding_items:
            logger.info(f"📊 총 {len(all_embedding_items)}개 임베딩 아이템 처리 예정")
            logger.info(f"   - 텍스트, 이미지 OCR, 첨부파일 파싱 결과 포함")

            # 임베딩 생성 및 업로드 (멀티모달 지원)
            uploaded_count = embedding_manager.process_and_upload_items(all_embedding_items)

            logger.info(f"✅ 총 {uploaded_count}개 벡터 업로드 완료")
        else:
            logger.info("ℹ️  새로 처리할 문서가 없습니다.")

        # ========== 6. 최종 상태 출력 ==========
        logger.section_start("🎉 크롤링 완료")

        state_manager.print_status()

        # 최종 통계 출력
        logger.print_summary()

        logger.info("\n✅ 모든 작업이 완료되었습니다!")

    except Exception as e:
        logger.error(f"❌ 크롤링 중 치명적 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise

    finally:
        # 로거 종료
        close_logger()


if __name__ == "__main__":
    main()
