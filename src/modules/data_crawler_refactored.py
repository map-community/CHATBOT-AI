"""
리팩토링된 크롤러 메인 스크립트

개선 사항:
1. 증분 크롤링: 새 게시글만 처리
2. 중복 제거: 크롤링 전에 중복 체크
3. API 비용 절감: 새 문서만 임베딩 생성
4. 클래스 기반 설계: 유지보수 편의성 향상
5. 상태 관리: 크롤링 이력 추적
"""
from pymongo import MongoClient
from config import CrawlerConfig
from state import CrawlStateManager
from processing import DocumentProcessor, EmbeddingManager
from crawling import (
    NoticeCrawler,
    JobCrawler,
    SeminarCrawler,
    ProfessorCrawler
)
from crawling.professor_crawler import GuestProfessorCrawler, StaffCrawler


def main():
    """메인 크롤링 실행 함수"""

    # MongoDB 클라이언트 초기화
    mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)

    # 각 컴포넌트 초기화
    state_manager = CrawlStateManager(mongo_client)
    document_processor = DocumentProcessor(mongo_client)
    embedding_manager = EmbeddingManager()

    print("\n" + "="*80)
    print("🚀 리팩토링된 크롤러 시작")
    print("="*80 + "\n")

    # 현재 크롤링 상태 출력
    state_manager.print_status()

    # 전체 수집 데이터 저장용
    all_texts = []
    all_titles = []
    all_urls = []
    all_dates = []
    all_images = []

    # ========== 1. 공지사항 크롤링 ==========
    print("\n" + "="*80)
    print("📋 1. 공지사항 크롤링")
    print("="*80)

    notice_crawler = NoticeCrawler()
    notice_latest_id = notice_crawler.get_latest_id()

    if notice_latest_id:
        print(f"✅ 최신 공지사항 ID: {notice_latest_id}")

        # 증분 크롤링: 새 게시글만 크롤링
        crawl_range = state_manager.get_crawl_range('notice', notice_latest_id)

        if len(crawl_range) > 0:
            print(f"🔍 크롤링할 범위: {notice_latest_id} ~ {crawl_range[-1] + 1} ({len(crawl_range)}개)")

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

            # 문서 처리 (중복 체크 포함)
            texts, titles, urls, dates, images, new_count = document_processor.process_documents(notice_data)

            all_texts.extend(texts)
            all_titles.extend(titles)
            all_urls.extend(urls)
            all_dates.extend(dates)
            all_images.extend(images)

            # 상태 업데이트
            state_manager.update_last_processed_id('notice', notice_latest_id, new_count)
            print(f"✅ 공지사항 처리 완료: {new_count}개 새 문서")
        else:
            print("ℹ️  새 공지사항이 없습니다.")
    else:
        print("❌ 공지사항 최신 ID 조회 실패")

    # ========== 2. 채용정보 크롤링 ==========
    print("\n" + "="*80)
    print("💼 2. 채용정보 크롤링")
    print("="*80)

    job_crawler = JobCrawler()
    job_latest_id = job_crawler.get_latest_id()

    if job_latest_id:
        print(f"✅ 최신 채용정보 ID: {job_latest_id}")

        crawl_range = state_manager.get_crawl_range('job', job_latest_id)

        if len(crawl_range) > 0:
            print(f"🔍 크롤링할 범위: {job_latest_id} ~ {crawl_range[-1] + 1} ({len(crawl_range)}개)")

            job_urls = job_crawler.generate_urls(crawl_range)
            job_data = job_crawler.crawl_urls(job_urls)

            texts, titles, urls, dates, images, new_count = document_processor.process_documents(job_data)

            all_texts.extend(texts)
            all_titles.extend(titles)
            all_urls.extend(urls)
            all_dates.extend(dates)
            all_images.extend(images)

            state_manager.update_last_processed_id('job', job_latest_id, new_count)
            print(f"✅ 채용정보 처리 완료: {new_count}개 새 문서")
        else:
            print("ℹ️  새 채용정보가 없습니다.")
    else:
        print("❌ 채용정보 최신 ID 조회 실패")

    # ========== 3. 세미나 크롤링 ==========
    print("\n" + "="*80)
    print("🎓 3. 세미나 크롤링")
    print("="*80)

    seminar_crawler = SeminarCrawler()
    seminar_latest_id = seminar_crawler.get_latest_id()

    if seminar_latest_id:
        print(f"✅ 최신 세미나 ID: {seminar_latest_id}")

        crawl_range = state_manager.get_crawl_range('seminar', seminar_latest_id)

        if len(crawl_range) > 0:
            print(f"🔍 크롤링할 범위: {seminar_latest_id} ~ {crawl_range[-1] + 1} ({len(crawl_range)}개)")

            seminar_urls = seminar_crawler.generate_urls(crawl_range)
            seminar_data = seminar_crawler.crawl_urls(seminar_urls)

            texts, titles, urls, dates, images, new_count = document_processor.process_documents(seminar_data)

            all_texts.extend(texts)
            all_titles.extend(titles)
            all_urls.extend(urls)
            all_dates.extend(dates)
            all_images.extend(images)

            state_manager.update_last_processed_id('seminar', seminar_latest_id, new_count)
            print(f"✅ 세미나 처리 완료: {new_count}개 새 문서")
        else:
            print("ℹ️  새 세미나가 없습니다.")
    else:
        print("❌ 세미나 최신 ID 조회 실패")

    # ========== 4. 교수 정보 크롤링 ==========
    print("\n" + "="*80)
    print("👨‍🏫 4. 교수 및 직원 정보 크롤링")
    print("="*80)

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

    # 문서 처리
    texts, titles, urls, dates, images, new_count = document_processor.process_documents(combined_professor_data)

    all_texts.extend(texts)
    all_titles.extend(titles)
    all_urls.extend(urls)
    all_dates.extend(dates)
    all_images.extend(images)

    print(f"✅ 교수/직원 정보 처리 완료: {new_count}개 새 문서")

    # ========== 5. 임베딩 생성 및 업로드 ==========
    print("\n" + "="*80)
    print("🔄 5. 임베딩 생성 및 Pinecone 업로드")
    print("="*80)

    if all_texts:
        print(f"📊 총 {len(all_texts)}개 텍스트 청크 처리 예정")

        # 임베딩 생성 및 업로드
        uploaded_count = embedding_manager.process_and_upload(
            all_texts, all_titles, all_urls, all_dates
        )

        print(f"✅ 총 {uploaded_count}개 벡터 업로드 완료")
    else:
        print("ℹ️  새로 처리할 문서가 없습니다.")

    # ========== 6. 최종 상태 출력 ==========
    print("\n" + "="*80)
    print("🎉 크롤링 완료")
    print("="*80)

    state_manager.print_status()

    print("\n✅ 모든 작업이 완료되었습니다!\n")


if __name__ == "__main__":
    main()
