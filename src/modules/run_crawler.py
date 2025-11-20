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
        # 단, MongoDB 중복 체크 + 내용 변경 감지 수행
        # 교수 크롤러 형식: (title, text_content, image_list, attachment_list, date, url)
        new_count = 0
        professor_items = []
        for title, text_content, image_list, attachment_list, date, url in combined_professor_data:
            # 중복 체크 (이미지 + 내용 해시로 체크, 내용 바뀌면 재처리)
            first_image = image_list[0] if image_list else None
            if document_processor.is_duplicate(title, first_image, text_content):
                logger.log_post_skipped("professor", title, reason="중복")
                continue

            new_count += 1

            metadata = {
                "title": title,
                "url": url,
                "date": date,
                "content_type": "text",
                "source": "professor_info",
                "category": "professor"
            }
            professor_items.append((text_content, metadata))

            # MongoDB에 처리 완료 표시 (content 해시 저장)
            document_processor.mark_as_processed(title, first_image, text_content)

        all_embedding_items.extend(professor_items)
        logger.info(f"✅ 교수/직원 정보 처리 완료: {new_count}개 새 문서, {len(professor_items)}개 임베딩 아이템")

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

        # ========== 6. Redis 캐시 증분 업데이트 ==========
        if all_embedding_items:
            logger.section_start("🔄 6. Redis 캐시 증분 업데이트")

            try:
                import redis
                import pickle
                import os

                redis_client = redis.Redis(
                    host=os.getenv('REDIS_HOST', 'redis'),
                    port=int(os.getenv('REDIS_PORT', 6379)),
                    decode_responses=False  # pickle 사용 시 필요
                )

                # 기존 Redis 캐시 로드
                cached_data = redis_client.get('pinecone_metadata')

                if cached_data:
                    logger.info("📦 기존 Redis 캐시 발견 - 증분 업데이트 시작")

                    # 기존 데이터 로드
                    (cached_titles, cached_texts, cached_urls, cached_dates,
                     cached_htmls, cached_content_types, cached_sources,
                     cached_image_urls, cached_attachment_urls, cached_attachment_types) = pickle.loads(cached_data)

                    original_count = len(cached_titles)
                    logger.info(f"   기존 문서: {original_count}개")

                    # 새 데이터 추가 (all_embedding_items를 메타데이터로 변환)
                    updated_count = 0
                    added_count = 0

                    for text, metadata in all_embedding_items:
                        title = metadata.get('title', '')
                        source = metadata.get('source', 'original_post')

                        # 교수/직원 정보: 중복 체크 후 업데이트 또는 추가
                        if source == 'professor_info':
                            # title과 source로 기존 항목 찾기
                            found_idx = -1
                            for idx in range(len(cached_titles)):
                                if cached_titles[idx] == title and cached_sources[idx] == source:
                                    found_idx = idx
                                    break

                            if found_idx >= 0:
                                # 기존 항목 업데이트 (내용 변경 반영)
                                cached_texts[found_idx] = text
                                cached_urls[found_idx] = metadata.get('url', '')
                                cached_dates[found_idx] = metadata.get('date', '')
                                cached_content_types[found_idx] = metadata.get('content_type', 'text')
                                cached_image_urls[found_idx] = metadata.get('image_url', '')
                                cached_attachment_urls[found_idx] = metadata.get('attachment_url', '')
                                cached_attachment_types[found_idx] = metadata.get('attachment_type', '')
                                updated_count += 1
                            else:
                                # 새 교수 추가
                                cached_titles.append(title)
                                cached_texts.append(text)
                                cached_urls.append(metadata.get('url', ''))
                                cached_dates.append(metadata.get('date', ''))
                                cached_htmls.append('')  # HTML은 MongoDB에서 조회
                                cached_content_types.append(metadata.get('content_type', 'text'))
                                cached_sources.append(source)
                                cached_image_urls.append(metadata.get('image_url', ''))
                                cached_attachment_urls.append(metadata.get('attachment_url', ''))
                                cached_attachment_types.append(metadata.get('attachment_type', ''))
                                added_count += 1
                        else:
                            # 공지사항/세미나/채용정보: 무조건 추가 (청크 중복 없음)
                            cached_titles.append(title)
                            cached_texts.append(text)
                            cached_urls.append(metadata.get('url', ''))
                            cached_dates.append(metadata.get('date', ''))
                            cached_htmls.append('')  # HTML은 MongoDB에서 조회
                            cached_content_types.append(metadata.get('content_type', 'text'))
                            cached_sources.append(source)
                            cached_image_urls.append(metadata.get('image_url', ''))
                            cached_attachment_urls.append(metadata.get('attachment_url', ''))
                            cached_attachment_types.append(metadata.get('attachment_type', ''))
                            added_count += 1

                    new_count = len(cached_titles) - original_count
                    logger.info(f"   추가: {added_count}개, 업데이트: {updated_count}개")
                    logger.info(f"   총 문서: {len(cached_titles)}개 ({new_count:+d})")

                    # Redis에 업데이트된 데이터 저장
                    updated_cache = (
                        cached_titles, cached_texts, cached_urls, cached_dates,
                        cached_htmls, cached_content_types, cached_sources,
                        cached_image_urls, cached_attachment_urls, cached_attachment_types
                    )
                    redis_client.set('pinecone_metadata', pickle.dumps(updated_cache))

                    logger.info("✅ Redis 캐시 증분 업데이트 완료!")
                else:
                    logger.info("ℹ️  기존 Redis 캐시 없음 - 다음 앱 재시작 시 Pinecone에서 로드됩니다")

            except Exception as e:
                logger.warning(f"⚠️  Redis 캐시 업데이트 실패 (앱 재시작 시 Pinecone에서 로드됩니다): {e}")

        # ========== 7. 최종 상태 출력 ==========
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
