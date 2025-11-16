"""
데이터베이스 초기화 스크립트

MongoDB와 Pinecone의 모든 데이터를 삭제하고 새로 시작
멀티모달 RAG 시스템으로 전환하기 위해 기존 데이터 정리
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from pymongo import MongoClient
from pinecone import Pinecone
from config import CrawlerConfig


def reset_mongodb():
    """MongoDB 초기화"""
    print("\n" + "="*80)
    print("🗑️  MongoDB 초기화 시작")
    print("="*80 + "\n")

    try:
        client = MongoClient(CrawlerConfig.MONGODB_URI)
        db = client[CrawlerConfig.MONGODB_DATABASE]

        # 삭제할 컬렉션 목록
        collections_to_drop = [
            CrawlerConfig.MONGODB_NOTICE_COLLECTION,  # 기존 문서 메타데이터
            "crawl_state",  # 크롤링 상태
            "multimodal_cache"  # 멀티모달 캐시
        ]

        for collection_name in collections_to_drop:
            if collection_name in db.list_collection_names():
                count = db[collection_name].count_documents({})
                db[collection_name].drop()
                print(f"✅ {collection_name} 삭제 완료 ({count}개 문서)")
            else:
                print(f"ℹ️  {collection_name} - 컬렉션 없음")

        print(f"\n✅ MongoDB 초기화 완료!")

    except Exception as e:
        print(f"❌ MongoDB 초기화 실패: {e}")
        raise


def reset_pinecone():
    """Pinecone 초기화"""
    print("\n" + "="*80)
    print("🗑️  Pinecone 초기화 시작")
    print("="*80 + "\n")

    try:
        pc = Pinecone(api_key=CrawlerConfig.PINECONE_API_KEY)
        index = pc.Index(CrawlerConfig.PINECONE_INDEX_NAME)

        # 인덱스 통계 확인
        stats = index.describe_index_stats()
        total_vectors = stats.get('total_vector_count', 0)

        print(f"📊 현재 벡터 개수: {total_vectors:,}개")

        if total_vectors > 0:
            # 모든 벡터 삭제
            print(f"🔄 모든 벡터 삭제 중...")
            index.delete(delete_all=True)
            print(f"✅ {total_vectors:,}개 벡터 삭제 완료!")
        else:
            print("ℹ️  Pinecone 인덱스가 이미 비어있습니다.")

        # 삭제 후 확인
        stats_after = index.describe_index_stats()
        remaining = stats_after.get('total_vector_count', 0)
        print(f"📊 삭제 후 벡터 개수: {remaining}개")

        print(f"\n✅ Pinecone 초기화 완료!")

    except Exception as e:
        print(f"❌ Pinecone 초기화 실패: {e}")
        raise


def main():
    """메인 실행 함수"""
    print("\n" + "="*80)
    print("⚠️  데이터베이스 초기화")
    print("="*80)
    print("\n⚠️  경고: 모든 데이터가 삭제됩니다!")
    print("   - MongoDB: 문서 메타데이터, 크롤링 상태, 멀티모달 캐시")
    print("   - Pinecone: 모든 벡터 임베딩\n")

    # 사용자 확인
    response = input("정말로 초기화하시겠습니까? (yes/no): ")

    if response.lower() != 'yes':
        print("\n❌ 초기화가 취소되었습니다.")
        return

    print("\n🚀 초기화를 시작합니다...\n")

    try:
        # MongoDB 초기화
        reset_mongodb()

        # Pinecone 초기화
        reset_pinecone()

        print("\n" + "="*80)
        print("🎉 모든 데이터베이스 초기화 완료!")
        print("="*80)
        print("\n✅ 이제 run_crawler.py를 실행하여 멀티모달 RAG 데이터를 구축하세요.")
        print("   python src/modules/run_crawler.py\n")

    except Exception as e:
        print(f"\n❌ 초기화 중 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
