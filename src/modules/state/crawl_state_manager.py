"""
크롤링 상태 관리
각 게시판별 마지막 처리 ID를 추적하여 증분 크롤링 지원
"""
import sys
from pathlib import Path

# modules 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from typing import Optional, Dict
from pymongo import MongoClient
from config import CrawlerConfig


class CrawlStateManager:
    """
    크롤링 상태 관리 클래스

    역할:
    - 각 게시판별 마지막 처리 ID 저장/조회
    - 크롤링 이력 관리
    - 증분 크롤링 지원
    """

    def __init__(self, mongo_client: Optional[MongoClient] = None):
        """
        Args:
            mongo_client: MongoDB 클라이언트 (없으면 새로 생성)
        """
        if mongo_client is None:
            mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)

        self.client = mongo_client
        self.db = self.client[CrawlerConfig.MONGODB_DATABASE]
        self.collection = self.db[CrawlerConfig.MONGODB_STATE_COLLECTION]

        # 인덱스 생성 (board_type으로 빠른 조회)
        self.collection.create_index("board_type", unique=True)

    def get_last_processed_id(self, board_type: str) -> Optional[int]:
        """
        특정 게시판의 마지막 처리 ID 조회

        Args:
            board_type: 게시판 타입 ('notice', 'job', 'seminar' 등)

        Returns:
            마지막 처리 ID (없으면 None)
        """
        state = self.collection.find_one({"board_type": board_type})

        if state and "last_processed_id" in state:
            return state["last_processed_id"]

        return None

    def update_last_processed_id(
        self,
        board_type: str,
        last_id: int,
        processed_count: int = 0
    ) -> None:
        """
        특정 게시판의 마지막 처리 ID 업데이트

        Args:
            board_type: 게시판 타입
            last_id: 마지막 처리 ID
            processed_count: 처리된 문서 개수
        """
        self.collection.update_one(
            {"board_type": board_type},
            {
                "$set": {
                    "last_processed_id": last_id,
                    "last_updated": datetime.utcnow(),
                    "processed_count": processed_count
                }
            },
            upsert=True  # 없으면 삽입
        )

    def get_crawl_range(self, board_type: str, current_max_id: int) -> range:
        """
        크롤링할 ID 범위 계산 (증분 크롤링)

        Args:
            board_type: 게시판 타입
            current_max_id: 현재 게시판의 최신 ID

        Returns:
            크롤링할 ID range (새 문서만)
        """
        last_processed = self.get_last_processed_id(board_type)
        min_id = CrawlerConfig.MIN_IDS.get(board_type)

        if last_processed is None:
            # 처음 크롤링: 전체 범위
            if min_id is not None:
                return range(current_max_id, min_id - 1, -1)
            else:
                # min_id가 없으면 최신 100개만
                return range(current_max_id, max(1, current_max_id - 100), -1)
        else:
            # 증분 크롤링: 마지막 처리 ID 이후만
            if current_max_id > last_processed:
                return range(current_max_id, last_processed, -1)
            else:
                # 새 문서 없음
                return range(0)

    def get_all_states(self) -> Dict[str, dict]:
        """
        모든 게시판의 크롤링 상태 조회

        Returns:
            {board_type: state_dict} 딕셔너리
        """
        states = {}
        for state in self.collection.find():
            board_type = state.get("board_type")
            if board_type:
                states[board_type] = {
                    "last_processed_id": state.get("last_processed_id"),
                    "last_updated": state.get("last_updated"),
                    "processed_count": state.get("processed_count", 0)
                }
        return states

    def reset_state(self, board_type: str) -> None:
        """
        특정 게시판의 상태 초기화 (전체 재크롤링용)

        Args:
            board_type: 게시판 타입
        """
        self.collection.delete_one({"board_type": board_type})

    def print_status(self) -> None:
        """크롤링 상태 출력"""
        print(f"\n{'='*80}")
        print("📊 크롤링 상태")
        print(f"{'='*80}")

        states = self.get_all_states()

        if not states:
            print("아직 크롤링 이력이 없습니다.")
        else:
            for board_type, state in states.items():
                last_id = state.get("last_processed_id", "N/A")
                last_updated = state.get("last_updated", "N/A")
                count = state.get("processed_count", 0)

                print(f"\n📋 {board_type.upper()}")
                print(f"  - 마지막 처리 ID: {last_id}")
                print(f"  - 마지막 업데이트: {last_updated}")
                print(f"  - 처리된 문서 수: {count}")

        print(f"\n{'='*80}\n")
