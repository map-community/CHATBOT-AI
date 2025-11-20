"""
교수/직원 정보 삭제 스크립트

목적:
- Auto-increment ID → Title hash ID 전환을 위한 기존 데이터 정리
- MongoDB, Pinecone, Redis에서 교수/직원 정보 전체 삭제

실행 방법:
    python cleanup_professor_data.py

주의:
- 삭제된 데이터는 복구 불가능
- 실행 전 백업 권장
- 삭제 후 크롤링 재실행 필요
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from pymongo import MongoClient
from pinecone import Pinecone
import redis
import os
from config import CrawlerConfig


def cleanup_mongodb():
    """MongoDB에서 교수/직원 정보 삭제"""
    print("\n" + "="*80)
    print("🗑️  MongoDB 정리 시작")
    print("="*80)

    try:
        mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)
        db = mongo_client['chatbot_db']
        collection = db['processed_documents']

        # source: "professor_info"인 문서 삭제
        # 교수 정보는 title이 "[교수]", "[초빙교수]", "[직원]"으로 시작
        result = collection.delete_many({
            "$or": [
                {"title": {"$regex": "^\\[교수\\]"}},
                {"title": {"$regex": "^\\[초빙교수\\]"}},
                {"title": {"$regex": "^\\[직원\\]"}}
            ]
        })

        print(f"✅ MongoDB 삭제 완료: {result.deleted_count}개 문서")

        # 확인
        remaining = collection.count_documents({
            "$or": [
                {"title": {"$regex": "^\\[교수\\]"}},
                {"title": {"$regex": "^\\[초빙교수\\]"}},
                {"title": {"$regex": "^\\[직원\\]"}}
            ]
        })

        if remaining > 0:
            print(f"⚠️  잔여 문서: {remaining}개 (정상일 수 있음)")
        else:
            print(f"✅ 교수/직원 정보 전체 삭제 확인")

    except Exception as e:
        print(f"❌ MongoDB 정리 실패: {e}")
        raise


def cleanup_pinecone():
    """Pinecone에서 교수/직원 정보 벡터 삭제"""
    print("\n" + "="*80)
    print("🗑️  Pinecone 정리 시작")
    print("="*80)

    try:
        pc = Pinecone(api_key=CrawlerConfig.PINECONE_API_KEY)
        index = pc.Index(CrawlerConfig.PINECONE_INDEX_NAME)

        # source: "professor_info" 필터로 조회 후 삭제
        # Pinecone은 delete_by_metadata 지원하지 않으므로 query로 ID 찾기

        print("🔍 교수/직원 정보 벡터 검색 중...")

        # 더미 벡터로 query (metadata filter 사용)
        results = index.query(
            vector=[0.0] * 4096,  # 더미 벡터 (dimension 맞춰야 함)
            filter={"source": {"$eq": "professor_info"}},
            top_k=10000,  # 최대한 많이 조회
            include_metadata=True
        )

        vector_ids = [match['id'] for match in results.get('matches', [])]

        if vector_ids:
            print(f"📋 발견된 벡터: {len(vector_ids)}개")
            print(f"🗑️  삭제 중...")

            # Pinecone delete는 배치로 처리 (1000개씩)
            batch_size = 1000
            for i in range(0, len(vector_ids), batch_size):
                batch = vector_ids[i:i+batch_size]
                index.delete(ids=batch)
                print(f"   삭제: {i+1}~{min(i+batch_size, len(vector_ids))} ({len(batch)}개)")

            print(f"✅ Pinecone 삭제 완료: {len(vector_ids)}개 벡터")
        else:
            print(f"ℹ️  삭제할 벡터 없음 (이미 정리됨)")

    except Exception as e:
        print(f"❌ Pinecone 정리 실패: {e}")
        print(f"⚠️  수동 삭제 필요할 수 있음")
        # Pinecone 오류는 치명적이지 않으므로 계속 진행


def cleanup_redis():
    """Redis Pinecone 메타데이터 캐시 삭제"""
    print("\n" + "="*80)
    print("🗑️  Redis 캐시 정리 시작")
    print("="*80)

    try:
        redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=False
        )

        # pinecone_metadata 캐시 전체 삭제
        # (앱 재시작 시 Pinecone에서 재로드됨)
        result = redis_client.delete('pinecone_metadata')

        if result:
            print(f"✅ Redis 캐시 삭제 완료: pinecone_metadata")
            print(f"ℹ️  다음 앱 시작 시 Pinecone에서 재로드됩니다")
        else:
            print(f"ℹ️  삭제할 캐시 없음 (이미 정리됨)")

    except Exception as e:
        print(f"❌ Redis 정리 실패: {e}")
        print(f"⚠️  수동 삭제 필요: redis-cli DEL pinecone_metadata")


def main():
    """메인 실행 함수"""
    print("\n" + "="*80)
    print("🧹 교수/직원 정보 정리 시작")
    print("="*80)
    print("\n⚠️  경고: 다음 데이터가 삭제됩니다:")
    print("   - MongoDB: 교수/직원/초빙교수 문서")
    print("   - Pinecone: source='professor_info' 벡터")
    print("   - Redis: pinecone_metadata 캐시")
    print("\n💡 이 작업은 Title hash ID 전환을 위한 사전 작업입니다.")
    print("   삭제 후 크롤링을 재실행하면 새 ID 체계로 저장됩니다.\n")

    response = input("계속하시겠습니까? (yes/no): ")

    if response.lower() != 'yes':
        print("\n❌ 작업 취소됨")
        return

    try:
        # 1. MongoDB 정리
        cleanup_mongodb()

        # 2. Pinecone 정리
        cleanup_pinecone()

        # 3. Redis 정리
        cleanup_redis()

        print("\n" + "="*80)
        print("✅ 모든 정리 작업 완료!")
        print("="*80)
        print("\n📌 다음 단계:")
        print("   1. run_crawler.py 실행")
        print("   2. 교수/직원 정보가 새 hash ID로 저장됨")
        print("   3. 앱 재시작 시 Redis 캐시 자동 생성\n")

    except Exception as e:
        print("\n" + "="*80)
        print(f"❌ 정리 작업 중 오류 발생: {e}")
        print("="*80)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
