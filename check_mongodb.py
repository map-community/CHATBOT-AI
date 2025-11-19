#!/usr/bin/env python3
"""
MongoDB 데이터베이스 및 컬렉션 상태 확인
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

print(f"🔍 MONGODB_URI: {os.getenv('MONGODB_URI')}")
print()

try:
    client = MongoClient(os.getenv('MONGODB_URI'))

    # 1. 모든 데이터베이스 목록
    print("="*60)
    print("📊 데이터베이스 목록:")
    print("="*60)
    for db_name in client.list_database_names():
        print(f"  - {db_name}")

    print()

    # 2. chatbot DB의 컬렉션 목록
    db = client['chatbot']
    print("="*60)
    print("📊 'chatbot' DB의 컬렉션 목록:")
    print("="*60)
    for coll_name in db.list_collection_names():
        count = db[coll_name].count_documents({})
        print(f"  - {coll_name}: {count:,}개 문서")

    print()

    # 3. multimodal_cache 상세 확인
    collection = db['multimodal_cache']
    total = collection.count_documents({})

    print("="*60)
    print(f"📊 'multimodal_cache' 컬렉션 상세:")
    print("="*60)
    print(f"전체 문서 수: {total:,}개")

    # HTML 필드 확인
    html_count = collection.count_documents({
        "$or": [
            {"html": {"$exists": True, "$ne": ""}},
            {"ocr_html": {"$exists": True, "$ne": ""}}
        ]
    })
    print(f"HTML 필드가 있는 문서: {html_count:,}개")

    # Markdown 필드 확인
    markdown_count = collection.count_documents({
        "$or": [
            {"markdown": {"$exists": True, "$ne": ""}},
            {"ocr_markdown": {"$exists": True, "$ne": ""}}
        ]
    })
    print(f"Markdown 필드가 있는 문서: {markdown_count:,}개")

    print()

    # 4. 샘플 문서 확인
    if total > 0:
        print("="*60)
        print("📝 샘플 문서 (처음 1개):")
        print("="*60)
        sample = collection.find_one()
        if sample:
            print(f"필드 목록: {list(sample.keys())}")
            print(f"URL: {sample.get('url', 'N/A')[:80]}...")

            # HTML 필드 확인
            if 'html' in sample:
                print(f"html 필드: 있음 ({len(sample['html'])} 문자)")
            else:
                print(f"html 필드: 없음")

            if 'ocr_html' in sample:
                print(f"ocr_html 필드: 있음 ({len(sample['ocr_html'])} 문자)")
            else:
                print(f"ocr_html 필드: 없음")

            # Markdown 필드 확인
            if 'markdown' in sample:
                print(f"markdown 필드: 있음 ({len(sample['markdown'])} 문자)")
            else:
                print(f"markdown 필드: 없음")

            if 'ocr_markdown' in sample:
                print(f"ocr_markdown 필드: 있음 ({len(sample['ocr_markdown'])} 문자)")
            else:
                print(f"ocr_markdown 필드: 없음")

    client.close()

except Exception as e:
    print(f"❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()
