#!/usr/bin/env python3
"""
Redis BM25 캐시 삭제 스크립트

MongoDB의 문서가 변경되었으므로, BM25 인덱스를 재생성하기 위해 Redis 캐시를 삭제합니다.
"""

import os
import sys
import redis
from dotenv import load_dotenv
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def clear_bm25_cache():
    """
    Redis에서 BM25 캐시 삭제
    """
    # .env 파일 로드
    load_dotenv()

    # Redis 연결
    try:
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_db = int(os.getenv('REDIS_DB', 0))

        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=False
        )

        # 연결 테스트
        r.ping()
        logger.info(f"✅ Redis 연결 성공 ({redis_host}:{redis_port}, DB {redis_db})")
    except Exception as e:
        logger.error(f"❌ Redis 연결 실패: {e}")
        sys.exit(1)

    # BM25 캐시 키
    cache_key = "bm25_cache_v2"

    # 캐시 존재 확인
    if r.exists(cache_key):
        # 캐시 크기 확인
        cache_data = r.get(cache_key)
        cache_size = len(cache_data) / (1024 * 1024)  # MB

        logger.info(f"📊 BM25 캐시 발견: {cache_size:.2f} MB")

        # 삭제
        r.delete(cache_key)
        logger.info(f"✅ BM25 캐시 삭제 완료!")

        # 검증
        if not r.exists(cache_key):
            logger.info(f"✅ 캐시가 정상적으로 삭제되었습니다.")
        else:
            logger.error(f"❌ 캐시 삭제 실패!")
            sys.exit(1)
    else:
        logger.info(f"ℹ️  BM25 캐시가 존재하지 않습니다. (이미 삭제되었거나 생성되지 않음)")

    r.close()

    logger.info(f"\n{'='*60}")
    logger.info("⚠️  Docker 컨테이너를 재시작하면 새로운 Markdown 데이터로")
    logger.info("   BM25 인덱스가 자동으로 재생성됩니다.")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        clear_bm25_cache()
    except KeyboardInterrupt:
        logger.info("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ 예상치 못한 오류: {e}")
        sys.exit(1)
