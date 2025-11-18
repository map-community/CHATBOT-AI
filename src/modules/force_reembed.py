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
from config import CrawlerConfig
from processing.document_processor import DocumentProcessor
from processing.embedding_manager import EmbeddingManager
from utils.logging_config import get_logger

logger = get_logger()


def main():
    """캐싱된 데이터를 강제로 임베딩 및 업로드"""

    logger.info("\n" + "="*80)
    logger.info("🔄 캐싱 데이터 강제 임베딩 및 Pinecone 업로드")
    logger.info("="*80 + "\n")

    # MongoDB 연결
    client = MongoClient(CrawlerConfig.MONGODB_URI)
    db = client[CrawlerConfig.MONGODB_DATABASE]

    # notice_collection에서 모든 게시글 가져오기
    notice_coll = db[CrawlerConfig.MONGODB_NOTICE_COLLECTION]
    cache_coll = db['multimodal_cache']

    total_posts = notice_coll.count_documents({})
    logger.info(f"📊 총 {total_posts}개 게시글 확인")

    # 확인
    user_input = input(f"\n⚠️  notice_collection의 {total_posts}개 게시글을 재임베딩하시겠습니까? (yes/no): ")
    if user_input.lower() != 'yes':
        logger.info("❌ 취소되었습니다.")
        return

    # notice_collection 백업
    logger.info("\n📦 notice_collection 백업 중...")
    backup_coll = db['notice_collection_backup']
    backup_coll.drop()  # 기존 백업 삭제

    # 백업 생성
    for doc in notice_coll.find():
        backup_coll.insert_one(doc)

    logger.info(f"✅ 백업 완료: notice_collection_backup ({backup_coll.count_documents({})}개)")

    # notice_collection 삭제
    logger.info("\n🗑️  notice_collection 삭제 중...")
    notice_coll.drop()
    logger.info("✅ 삭제 완료")

    # multimodal_cache 통계
    total_cache = cache_coll.count_documents({})
    logger.info(f"\n📊 multimodal_cache: {total_cache}개 캐시")

    logger.info("\n" + "="*80)
    logger.info("✅ 준비 완료!")
    logger.info("="*80)
    logger.info("\n다음 단계:")
    logger.info("1. python src/modules/run_crawler.py 실행")
    logger.info("2. 캐싱 데이터 사용 (API 재호출 없음!)")
    logger.info("3. 임베딩 생성 및 Pinecone 업로드")
    logger.info("\n복구가 필요하면:")
    logger.info("db.notice_collection_backup.find().forEach(function(doc) {")
    logger.info("  db.notice_collection.insert(doc);")
    logger.info("});")


if __name__ == "__main__":
    main()
