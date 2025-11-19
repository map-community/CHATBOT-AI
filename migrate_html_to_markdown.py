#!/usr/bin/env python3
"""
MongoDB HTML → Markdown Migration Script

기존 MongoDB multimodal_cache 컬렉션의 HTML 필드를 Markdown으로 변환하여 저장합니다.
- html → markdown
- ocr_html → ocr_markdown

주의: 이미 markdown 필드가 있는 문서는 건너뜁니다 (Upstage API 원본이 더 고품질이므로)
"""

import os
import sys
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
import html2text
from typing import List, Dict
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# html2text 설정
h = html2text.HTML2Text()
h.ignore_links = False  # 링크 보존
h.ignore_images = False  # 이미지 보존
h.ignore_emphasis = False  # 강조 보존
h.body_width = 0  # 줄바꿈 제한 없음 (표 깨짐 방지)


def convert_html_to_markdown(html_content: str) -> str:
    """
    HTML을 Markdown으로 변환

    Args:
        html_content: HTML 문자열

    Returns:
        Markdown 문자열
    """
    if not html_content or not html_content.strip():
        return ""

    try:
        markdown = h.handle(html_content)
        return markdown.strip()
    except Exception as e:
        logger.warning(f"⚠️  HTML 변환 실패: {e}")
        return ""


def migrate_html_to_markdown():
    """
    MongoDB의 HTML 필드를 Markdown으로 변환하여 저장
    """
    # .env 파일 로드
    load_dotenv()

    # MongoDB 연결
    try:
        client = MongoClient(os.getenv('MONGODB_URI'))
        db = client['chatbot']
        collection = db['multimodal_cache']
        logger.info("✅ MongoDB 연결 성공")
    except Exception as e:
        logger.error(f"❌ MongoDB 연결 실패: {e}")
        sys.exit(1)

    # 전체 문서 수 확인
    total_docs = collection.count_documents({})
    logger.info(f"📊 전체 문서 수: {total_docs:,}개")

    # HTML이 있는 문서 수 확인
    html_docs_count = collection.count_documents({
        "$or": [
            {"html": {"$exists": True, "$ne": ""}},
            {"ocr_html": {"$exists": True, "$ne": ""}}
        ]
    })
    logger.info(f"📊 HTML 필드가 있는 문서 수: {html_docs_count:,}개")

    # 이미 markdown이 있는 문서 수 확인 (건너뛸 대상)
    existing_markdown_count = collection.count_documents({
        "$or": [
            {"markdown": {"$exists": True, "$ne": ""}},
            {"ocr_markdown": {"$exists": True, "$ne": ""}}
        ]
    })
    logger.info(f"📊 이미 Markdown이 있는 문서 수: {existing_markdown_count:,}개 (건너뜀)")

    # 변환 대상 조회 (HTML은 있지만 Markdown은 없는 문서)
    query = {
        "$and": [
            {
                "$or": [
                    {"html": {"$exists": True, "$ne": ""}},
                    {"ocr_html": {"$exists": True, "$ne": ""}}
                ]
            },
            {
                "$and": [
                    {"markdown": {"$exists": False}},
                    {"ocr_markdown": {"$exists": False}}
                ]
            }
        ]
    }

    target_docs_count = collection.count_documents(query)
    logger.info(f"🎯 변환 대상 문서 수: {target_docs_count:,}개")

    if target_docs_count == 0:
        logger.info("✅ 변환할 문서가 없습니다!")
        client.close()
        return

    # 확인 메시지
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 HTML → Markdown 변환을 시작합니다...")
    logger.info(f"{'='*60}\n")

    # 배치 처리 (1000개씩)
    batch_size = 1000
    processed = 0
    converted = 0
    skipped = 0
    errors = 0

    cursor = collection.find(query).batch_size(batch_size)

    bulk_operations: List[UpdateOne] = []

    for doc in cursor:
        doc_id = doc['_id']
        url = doc.get('url', 'N/A')

        update_fields = {}

        try:
            # html → markdown
            if 'html' in doc and doc['html'] and 'markdown' not in doc:
                markdown = convert_html_to_markdown(doc['html'])
                if markdown:
                    update_fields['markdown'] = markdown
                    converted += 1

            # ocr_html → ocr_markdown
            if 'ocr_html' in doc and doc['ocr_html'] and 'ocr_markdown' not in doc:
                ocr_markdown = convert_html_to_markdown(doc['ocr_html'])
                if ocr_markdown:
                    update_fields['ocr_markdown'] = ocr_markdown
                    converted += 1

            # 업데이트할 필드가 있으면 bulk operation 추가
            if update_fields:
                bulk_operations.append(
                    UpdateOne(
                        {'_id': doc_id},
                        {'$set': update_fields}
                    )
                )
            else:
                skipped += 1

        except Exception as e:
            logger.error(f"❌ 문서 처리 실패 ({url[:50]}...): {e}")
            errors += 1

        processed += 1

        # 1000개마다 bulk write 실행 및 진행 상황 출력
        if len(bulk_operations) >= batch_size:
            try:
                result = collection.bulk_write(bulk_operations, ordered=False)
                logger.info(f"📝 진행: {processed:,}/{target_docs_count:,} ({processed/target_docs_count*100:.1f}%) | 변환: {converted:,} | 건너뜀: {skipped:,} | 오류: {errors:,}")
                bulk_operations = []
            except Exception as e:
                logger.error(f"❌ Bulk write 실패: {e}")
                errors += len(bulk_operations)
                bulk_operations = []

    # 남은 bulk operations 실행
    if bulk_operations:
        try:
            result = collection.bulk_write(bulk_operations, ordered=False)
            logger.info(f"📝 진행: {processed:,}/{target_docs_count:,} (100.0%) | 변환: {converted:,} | 건너뜀: {skipped:,} | 오류: {errors:,}")
        except Exception as e:
            logger.error(f"❌ Bulk write 실패: {e}")
            errors += len(bulk_operations)

    # 최종 통계
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Migration 완료!")
    logger.info(f"{'='*60}")
    logger.info(f"📊 처리된 문서 수: {processed:,}개")
    logger.info(f"✅ 변환 성공: {converted:,}개 필드")
    logger.info(f"⏭️  건너뜀: {skipped:,}개")
    logger.info(f"❌ 오류: {errors:,}개")

    # 검증: 변환 후 markdown 필드 수 확인
    final_markdown_count = collection.count_documents({
        "$or": [
            {"markdown": {"$exists": True, "$ne": ""}},
            {"ocr_markdown": {"$exists": True, "$ne": ""}}
        ]
    })
    logger.info(f"\n📊 변환 후 Markdown 필드가 있는 문서 수: {final_markdown_count:,}개")
    logger.info(f"📈 증가: {final_markdown_count - existing_markdown_count:,}개")

    client.close()

    logger.info(f"\n{'='*60}")
    logger.info("⚠️  중요: 다음 작업을 수행하세요!")
    logger.info(f"{'='*60}")
    logger.info("1. Redis BM25 캐시 삭제 (재인덱싱 필요)")
    logger.info("2. Docker 컨테이너 재시작 (새 데이터 로드)")
    logger.info("")


if __name__ == "__main__":
    try:
        migrate_html_to_markdown()
    except KeyboardInterrupt:
        logger.info("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ 예상치 못한 오류: {e}")
        sys.exit(1)
