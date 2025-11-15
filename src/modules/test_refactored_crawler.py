"""
리팩토링된 크롤러 테스트 스크립트

실제 크롤링 없이 구조만 테스트합니다.
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


def test_imports():
    """모듈 임포트 테스트"""
    print("\n" + "="*80)
    print("🧪 1. 모듈 임포트 테스트")
    print("="*80)

    try:
        print("✅ CrawlerConfig 임포트 성공")
        print("✅ CrawlStateManager 임포트 성공")
        print("✅ DocumentProcessor 임포트 성공")
        print("✅ EmbeddingManager 임포트 성공")
        print("✅ Crawler 클래스들 임포트 성공")
        return True
    except Exception as e:
        print(f"❌ 임포트 실패: {e}")
        return False


def test_config():
    """설정 파일 테스트"""
    print("\n" + "="*80)
    print("🧪 2. 설정 파일 테스트")
    print("="*80)

    try:
        print(f"✅ MongoDB URI: {CrawlerConfig.MONGODB_URI}")
        print(f"✅ Pinecone Index: {CrawlerConfig.PINECONE_INDEX_NAME}")
        print(f"✅ Chunk Size: {CrawlerConfig.CHUNK_SIZE}")
        print(f"✅ Base URLs 개수: {len(CrawlerConfig.BASE_URLS)}")
        return True
    except Exception as e:
        print(f"❌ 설정 테스트 실패: {e}")
        return False


def test_state_manager():
    """상태 관리 테스트"""
    print("\n" + "="*80)
    print("🧪 3. 상태 관리 테스트")
    print("="*80)

    try:
        state_manager = CrawlStateManager()
        print("✅ CrawlStateManager 초기화 성공")

        # 현재 상태 조회
        state_manager.print_status()

        # 테스트용 상태 저장
        test_board = 'test_board'
        state_manager.update_last_processed_id(test_board, 100, 10)
        print(f"✅ 테스트 상태 저장 성공")

        # 조회
        last_id = state_manager.get_last_processed_id(test_board)
        print(f"✅ 마지막 처리 ID 조회: {last_id}")

        # 삭제
        state_manager.reset_state(test_board)
        print(f"✅ 테스트 상태 삭제 성공")

        return True
    except Exception as e:
        print(f"❌ 상태 관리 테스트 실패: {e}")
        return False


def test_document_processor():
    """문서 처리 테스트"""
    print("\n" + "="*80)
    print("🧪 4. 문서 처리 테스트")
    print("="*80)

    try:
        processor = DocumentProcessor()
        print("✅ DocumentProcessor 초기화 성공")

        # 텍스트 분할 테스트
        splitter = processor.text_splitter
        test_text = "테스트 " * 200  # 긴 텍스트
        chunks = splitter.split_text(test_text)
        print(f"✅ 텍스트 분할 성공: {len(chunks)}개 청크")

        # 테스트 문서 데이터
        test_doc_data = [
            ("테스트 제목1", "테스트 내용1", [], "2024-01-01", "http://test.com/1"),
            ("테스트 제목2", "테스트 내용2", ["img.jpg"], "2024-01-02", "http://test.com/2"),
        ]

        texts, titles, urls, dates, images, new_count = processor.process_documents(test_doc_data)
        print(f"✅ 문서 처리 성공: {new_count}개 새 문서")
        print(f"   - 총 텍스트 청크: {len(texts)}개")

        return True
    except Exception as e:
        print(f"❌ 문서 처리 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_crawlers():
    """크롤러 초기화 테스트"""
    print("\n" + "="*80)
    print("🧪 5. 크롤러 초기화 테스트")
    print("="*80)

    try:
        notice_crawler = NoticeCrawler()
        print("✅ NoticeCrawler 초기화 성공")

        job_crawler = JobCrawler()
        print("✅ JobCrawler 초기화 성공")

        seminar_crawler = SeminarCrawler()
        print("✅ SeminarCrawler 초기화 성공")

        professor_crawler = ProfessorCrawler()
        print("✅ ProfessorCrawler 초기화 성공")

        # URL 생성 테스트
        test_range = range(100, 95, -1)
        urls = notice_crawler.generate_urls(test_range)
        print(f"✅ URL 생성 테스트: {len(urls)}개 URL 생성")

        return True
    except Exception as e:
        print(f"❌ 크롤러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_embedding_manager():
    """임베딩 관리자 테스트 (초기화만)"""
    print("\n" + "="*80)
    print("🧪 6. 임베딩 관리자 테스트")
    print("="*80)

    try:
        embedding_mgr = EmbeddingManager()
        print("✅ EmbeddingManager 초기화 성공")

        # 다음 벡터 ID 조회 테스트
        next_id = embedding_mgr.get_next_vector_id()
        print(f"✅ 다음 벡터 ID: {next_id}")

        return True
    except Exception as e:
        print(f"❌ 임베딩 관리자 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """전체 테스트 실행"""
    print("\n" + "="*80)
    print("🚀 리팩토링된 크롤러 구조 테스트")
    print("="*80)

    results = []

    results.append(("모듈 임포트", test_imports()))
    results.append(("설정 파일", test_config()))
    results.append(("상태 관리", test_state_manager()))
    results.append(("문서 처리", test_document_processor()))
    results.append(("크롤러", test_crawlers()))
    results.append(("임베딩 관리", test_embedding_manager()))

    # 결과 요약
    print("\n" + "="*80)
    print("📊 테스트 결과 요약")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"{status} - {name}")

    print(f"\n총 {passed}/{total} 테스트 통과")

    if passed == total:
        print("\n🎉 모든 테스트 통과! 리팩토링된 크롤러를 사용할 수 있습니다.")
    else:
        print("\n⚠️  일부 테스트 실패. 문제를 해결한 후 다시 시도하세요.")

    print("="*80 + "\n")


if __name__ == "__main__":
    main()
