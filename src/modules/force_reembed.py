"""
캐싱된 데이터 강제 임베딩 및 Pinecone 업로드

사용 시나리오:
- 이전에 캐싱은 성공했지만 임베딩은 실패한 경우
- notice_collection에는 있지만 Pinecone에는 없는 경우
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from pymongo import MongoClient
from pinecone import Pinecone
from config import CrawlerConfig
from processing.document_processor import DocumentProcessor
from processing.embedding_manager import EmbeddingManager
from utils.logging_config import get_logger

logger = get_logger()


def main():
    """캐싱된 데이터를 강제로 임베딩 및 Pinecone 업로드"""

    logger.info("\n" + "="*80)
    logger.info("🔄 캐싱 데이터 강제 임베딩 및 Pinecone 업로드")
    logger.info("="*80 + "\n")

    # MongoDB 연결
    client = MongoClient(CrawlerConfig.MONGODB_URI)
    db = client[CrawlerConfig.MONGODB_DATABASE]

    # Pinecone 연결
    pc = Pinecone(api_key=CrawlerConfig.PINECONE_API_KEY)
    index = pc.Index(CrawlerConfig.PINECONE_INDEX_NAME)

    # 현재 상태 확인
    notice_coll = db[CrawlerConfig.MONGODB_NOTICE_COLLECTION]
    cache_coll = db['multimodal_cache']

    total_posts = notice_coll.count_documents({})
    total_cache = cache_coll.count_documents({})

    # Pinecone 통계
    stats = index.describe_index_stats()
    total_vectors = stats.get('total_vector_count', 0)

    logger.info(f"📊 현재 상태:")
    logger.info(f"   - notice_collection: {total_posts}개 게시글")
    logger.info(f"   - multimodal_cache: {total_cache}개 캐시")
    logger.info(f"   - Pinecone: {total_vectors}개 벡터")

    # 확인
    logger.info(f"\n⚠️  다음 작업을 수행합니다:")
    logger.info(f"   1. notice_collection 백업 → notice_collection_backup")
    logger.info(f"   2. notice_collection 삭제 (재생성 위해)")
    logger.info(f"   3. Pinecone 전체 삭제 (중복 방지)")
    logger.info(f"   4. multimodal_cache는 유지 (API 재호출 방지)")

    user_input = input(f"\n계속하시겠습니까? (yes/no): ")
    if user_input.lower() != 'yes':
        logger.info("❌ 취소되었습니다.")
        return

    # 1. notice_collection 백업
    logger.info("\n📦 notice_collection 백업 중...")
    backup_coll = db['notice_collection_backup']
    backup_coll.drop()  # 기존 백업 삭제

    # 백업 생성
    for doc in notice_coll.find():
        backup_coll.insert_one(doc)

    logger.info(f"✅ 백업 완료: notice_collection_backup ({backup_coll.count_documents({})}개)")

    # 2. notice_collection 삭제
    logger.info("\n🗑️  notice_collection 삭제 중...")
    notice_coll.drop()
    logger.info("✅ 삭제 완료")

    # 3. Pinecone 전체 삭제
    logger.info(f"\n🗑️  Pinecone 전체 삭제 중... (현재 {total_vectors}개 벡터)")
    try:
        index.delete(delete_all=True)
        logger.info("✅ Pinecone 삭제 완료")
    except Exception as e:
        logger.error(f"❌ Pinecone 삭제 실패: {e}")
        logger.info("   → 수동 삭제 필요할 수 있음")

    logger.info("\n" + "="*80)
    logger.info("✅ 준비 완료!")
    logger.info("="*80)
    logger.info("\n다음 단계:")
    logger.info("1. python src/modules/run_crawler.py 실행")
    logger.info("2. 캐싱 데이터 사용 (API 재호출 없음!)")
    logger.info("3. 임베딩 생성 및 Pinecone 업로드 (처음부터)")
    logger.info("\n예상 소요 시간: 15-25분")
    logger.info("\n복구가 필요하면 (MongoDB만):")
    logger.info("db.notice_collection_backup.find().forEach(function(doc) {")
    logger.info("  db.notice_collection.insert(doc);")
    logger.info("});")
    logger.info("\n⚠️  Pinecone은 복구 불가! run_crawler.py로 재생성 필요")


if __name__ == "__main__":
    main()
