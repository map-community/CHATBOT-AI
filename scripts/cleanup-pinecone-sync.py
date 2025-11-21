#!/usr/bin/env python3
"""
Pinecone-MongoDB 동기화 스크립트

기능:
- MongoDB와 Pinecone 간 불일치 감지
- Pinecone에만 있고 MongoDB에 없는 벡터 삭제
- 크롤링 실패 후 복원 시 사용

사용법:
    python scripts/cleanup-pinecone-sync.py [--dry-run]
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "src" / "modules"))

from pymongo import MongoClient
from pinecone import Pinecone
from config import CrawlerConfig
import argparse


def main():
    parser = argparse.ArgumentParser(description="Pinecone-MongoDB 동기화")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 삭제 없이 불일치 항목만 출력"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🔍 Pinecone-MongoDB 동기화 검사 시작")
    print("=" * 60)
    print()

    # MongoDB 연결
    print("📦 MongoDB 연결 중...")
    mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)
    db = mongo_client[CrawlerConfig.DB_NAME]
    collection = db[CrawlerConfig.COLLECTION_NAME]

    # MongoDB 문서 URL 목록 가져오기
    mongodb_docs = list(collection.find({}, {"url": 1, "title": 1, "_id": 0}))
    mongodb_urls = set(doc["url"] for doc in mongodb_docs if "url" in doc)

    print(f"   MongoDB 문서: {len(mongodb_urls)}개")
    print()

    # Pinecone 연결
    print("🔗 Pinecone 연결 중...")
    pc = Pinecone(api_key=CrawlerConfig.PINECONE_API_KEY)
    index = pc.Index(CrawlerConfig.PINECONE_INDEX_NAME)

    # Pinecone 통계
    stats = index.describe_index_stats()
    total_vectors = stats.get("total_vector_count", 0)
    print(f"   Pinecone 벡터: {total_vectors}개")
    print()

    # Pinecone 벡터 ID 목록 가져오기 (페이지네이션)
    print("📋 Pinecone 벡터 목록 가져오는 중...")
    pinecone_ids = []

    # Pinecone에서 모든 벡터 ID 가져오기
    # (주의: 대용량의 경우 시간이 오래 걸림)
    try:
        # namespace 없이 전체 쿼리
        # Pinecone v3 API는 list() 또는 query()로 ID 가져오기
        # 여기서는 query()를 사용 (top_k=10000)

        # 더미 벡터로 쿼리 (모든 벡터 가져오기)
        dummy_vector = [0.0] * 1024  # Solar embedding dimension

        query_response = index.query(
            vector=dummy_vector,
            top_k=10000,  # 최대 10000개
            include_metadata=True
        )

        for match in query_response.get("matches", []):
            vector_id = match.get("id", "")
            metadata = match.get("metadata", {})
            url = metadata.get("url", "")

            if url:
                pinecone_ids.append((vector_id, url))

    except Exception as e:
        print(f"⚠️  Pinecone 쿼리 실패: {e}")
        print("   대용량 인덱스의 경우 Pinecone 콘솔에서 수동 확인이 필요합니다.")
        return

    print(f"   조회된 벡터: {len(pinecone_ids)}개")
    print()

    # 불일치 감지
    print("🔍 불일치 감지 중...")
    orphan_vectors = []  # Pinecone에만 있는 벡터

    for vector_id, url in pinecone_ids:
        if url not in mongodb_urls:
            orphan_vectors.append((vector_id, url))

    print()
    print("=" * 60)
    print("📊 검사 결과")
    print("=" * 60)
    print(f"MongoDB 문서:        {len(mongodb_urls)}개")
    print(f"Pinecone 벡터:       {len(pinecone_ids)}개")
    print(f"불일치 벡터:         {len(orphan_vectors)}개")
    print()

    if not orphan_vectors:
        print("✅ Pinecone-MongoDB 동기화 완료!")
        print("   불일치 항목이 없습니다.")
        return

    # 불일치 항목 출력
    print("⚠️  Pinecone에만 있는 벡터 (MongoDB에 없음):")
    for i, (vector_id, url) in enumerate(orphan_vectors[:10], 1):
        print(f"   {i}. {url}")

    if len(orphan_vectors) > 10:
        print(f"   ... 외 {len(orphan_vectors) - 10}개")
    print()

    # Dry run 모드
    if args.dry_run:
        print("🔍 [Dry Run] 실제 삭제는 수행되지 않았습니다.")
        print()
        print("💡 실제 삭제하려면:")
        print("   python scripts/cleanup-pinecone-sync.py")
        return

    # 삭제 확인
    print("⚠️  경고: 이 벡터들을 Pinecone에서 삭제합니다!")
    response = input("계속하시겠습니까? (yes/no): ")

    if response.lower() != "yes":
        print("❌ 삭제가 취소되었습니다.")
        return

    # Pinecone에서 삭제
    print()
    print("🗑️  Pinecone 벡터 삭제 중...")

    deleted_count = 0
    batch_size = 100  # 한 번에 100개씩 삭제

    for i in range(0, len(orphan_vectors), batch_size):
        batch = orphan_vectors[i:i+batch_size]
        ids_to_delete = [vector_id for vector_id, _ in batch]

        try:
            index.delete(ids=ids_to_delete)
            deleted_count += len(ids_to_delete)
            print(f"   진행: {deleted_count}/{len(orphan_vectors)}개 삭제됨")
        except Exception as e:
            print(f"   ⚠️  삭제 실패 (배치 {i//batch_size + 1}): {e}")

    print()
    print("=" * 60)
    print("✅ Pinecone 정리 완료!")
    print("=" * 60)
    print(f"삭제된 벡터: {deleted_count}개")
    print()
    print("💡 검증 방법:")
    print("   1. Pinecone 콘솔에서 벡터 개수 확인")
    print("   2. 테스트 질문으로 정상 작동 확인")
    print()


if __name__ == "__main__":
    main()
