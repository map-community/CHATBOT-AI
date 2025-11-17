"""
로깅 설정

크롤러 실행 로그를 콘솔과 파일에 동시에 저장
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class CrawlerLogger:
    """
    크롤러 전용 로거

    기능:
    - 콘솔과 파일에 동시 로깅
    - 타임스탬프별 로그 파일 생성
    - 게시글별 처리 상태 추적
    """

    def __init__(self, log_dir: str = "logs"):
        """
        Args:
            log_dir: 로그 디렉토리 경로
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # 로그 파일 이름 (타임스탬프)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = self.log_dir / f"crawl_{timestamp}.txt"

        # 로거 초기화
        self.logger = logging.getLogger("crawler")
        self.logger.setLevel(logging.INFO)

        # 기존 핸들러 제거 (중복 방지)
        self.logger.handlers.clear()

        # 파일 핸들러 (UTF-8 인코딩)
        file_handler = logging.FileHandler(
            self.log_file,
            mode='w',
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)

        # 콘솔 핸들러 (UTF-8 인코딩)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # 포맷 설정 (시간, 레벨, 메시지)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # 핸들러 추가
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # 통계 추적
        self.stats = {
            'notice': {'total': 0, 'success': 0, 'failure': 0, 'skipped': 0},
            'job': {'total': 0, 'success': 0, 'failure': 0, 'skipped': 0},
            'seminar': {'total': 0, 'success': 0, 'failure': 0, 'skipped': 0},
            'professor': {'total': 0, 'success': 0, 'failure': 0, 'skipped': 0}
        }

        self.logger.info("="*80)
        self.logger.info(f"📝 로그 파일 생성: {self.log_file}")
        self.logger.info("="*80)

    def info(self, message: str):
        """정보 로그"""
        self.logger.info(message)

    def warning(self, message: str):
        """경고 로그"""
        self.logger.warning(message)

    def error(self, message: str):
        """에러 로그"""
        self.logger.error(message)

    def section_start(self, section_name: str):
        """섹션 시작"""
        self.logger.info("\n" + "="*80)
        self.logger.info(section_name)
        self.logger.info("="*80)

    def section_end(self, section_name: str):
        """섹션 종료"""
        self.logger.info("="*80)
        self.logger.info(f"{section_name} 완료")
        self.logger.info("="*80 + "\n")

    def log_post_success(
        self,
        category: str,
        title: str,
        url: str,
        text_length: int = 0,
        image_count: int = 0,
        attachment_count: int = 0,
        embedding_items: int = 0
    ):
        """
        게시글 처리 성공 로그

        Args:
            category: 카테고리 (notice, job, seminar, professor)
            title: 게시글 제목
            url: 게시글 URL
            text_length: 텍스트 길이
            image_count: 이미지 개수
            attachment_count: 첨부파일 개수
            embedding_items: 임베딩 아이템 개수
        """
        self.stats[category]['success'] += 1
        self.stats[category]['total'] += 1

        details = []
        if text_length > 0:
            details.append(f"텍스트 {text_length}자")
        if image_count > 0:
            details.append(f"이미지 {image_count}개")
        if attachment_count > 0:
            details.append(f"첨부파일 {attachment_count}개")
        if embedding_items > 0:
            details.append(f"임베딩 {embedding_items}개")

        details_str = ", ".join(details) if details else "내용 없음"

        self.logger.info(f"✅ 성공: {title}")
        self.logger.info(f"   URL: {url}")
        self.logger.info(f"   처리 내용: {details_str}")

    def log_post_failure(
        self,
        category: str,
        title: Optional[str],
        url: str,
        error: str
    ):
        """
        게시글 처리 실패 로그

        Args:
            category: 카테고리
            title: 게시글 제목 (없으면 None)
            url: 게시글 URL
            error: 에러 메시지
        """
        self.stats[category]['failure'] += 1
        self.stats[category]['total'] += 1

        title_str = title if title else "제목 없음"
        self.logger.error(f"❌ 실패: {title_str}")
        self.logger.error(f"   URL: {url}")
        self.logger.error(f"   오류: {error}")

    def log_post_skipped(self, category: str, title: str, reason: str = "중복"):
        """
        게시글 스킵 로그

        Args:
            category: 카테고리
            title: 게시글 제목
            reason: 스킵 이유
        """
        self.stats[category]['skipped'] += 1
        self.logger.info(f"⏭️  스킵 ({reason}): {title}")

    def log_multimodal_detail(
        self,
        content_type: str,
        url: str,
        success: bool,
        detail: str = ""
    ):
        """
        멀티모달 콘텐츠 처리 상세 로그

        Args:
            content_type: 콘텐츠 타입 (이미지 OCR, 문서 파싱 등)
            url: 콘텐츠 URL
            success: 성공 여부
            detail: 상세 정보
        """
        status = "✅ 성공" if success else "❌ 실패"
        self.logger.info(f"   {content_type}: {status}")
        self.logger.info(f"      URL: {url}")
        if detail:
            self.logger.info(f"      상세: {detail}")

    def log_embedding_item_structure(
        self,
        title: str,
        embedding_items: list,
        show_sample: bool = True
    ):
        """
        임베딩 아이템 구조 로그 (MongoDB 캐시 및 Pinecone 저장 데이터)

        Args:
            title: 게시글 제목
            embedding_items: [(text, metadata), ...] 리스트
            show_sample: 첫 번째 아이템 샘플 출력 여부
        """
        self.logger.info(f"\n   📦 저장될 데이터 구조 ({len(embedding_items)}개 임베딩 아이템):")

        # 콘텐츠 타입별 개수 집계
        content_types = {}
        html_count = 0

        for _, metadata in embedding_items:
            content_type = metadata.get('content_type', 'unknown')
            content_types[content_type] = content_types.get(content_type, 0) + 1

            # HTML 구조 존재 여부 확인
            if metadata.get('html_available') or metadata.get('html'):
                html_count += 1

        # 타입별 개수 출력
        for content_type, count in content_types.items():
            self.logger.info(f"      - {content_type}: {count}개")

        # HTML 구조 저장 여부
        if html_count > 0:
            self.logger.info(f"      - HTML 구조 보존: {html_count}개 (표/레이아웃 맥락 포함) ✅")

        # 샘플 데이터 출력
        if show_sample and embedding_items:
            text, metadata = embedding_items[0]
            self.logger.info(f"\n   📋 저장 데이터 샘플 (첫 번째 아이템):")
            self.logger.info(f"      제목: {metadata.get('title', 'N/A')}")
            self.logger.info(f"      타입: {metadata.get('content_type', 'N/A')}")
            self.logger.info(f"      소스: {metadata.get('source', 'N/A')}")
            self.logger.info(f"      텍스트 길이: {len(text)}자")

            # HTML 필드 상세 정보
            html_data = metadata.get('html', '')
            if html_data:
                self.logger.info(f"      HTML 구조: ✅ 있음 ({len(html_data)}자)")
            else:
                self.logger.info(f"      HTML 구조: ❌ 없음 (평문 텍스트만)")

            # 텍스트 미리보기
            preview = text[:100].replace('\n', ' ')
            if len(text) > 100:
                preview += "..."
            self.logger.info(f"      텍스트 미리보기: {preview}")

    def log_pinecone_metadata_sample(
        self,
        vector_id: str,
        metadata: dict
    ):
        """
        Pinecone 업로드 메타데이터 샘플 로그

        Args:
            vector_id: 벡터 ID
            metadata: Pinecone 메타데이터
        """
        self.logger.info(f"\n   🔍 Pinecone 메타데이터 샘플 (벡터 ID: {vector_id}):")
        self.logger.info(f"      제목: {metadata.get('title', 'N/A')}")
        self.logger.info(f"      카테고리: {metadata.get('category', 'N/A')}")
        self.logger.info(f"      콘텐츠 타입: {metadata.get('content_type', 'N/A')}")
        self.logger.info(f"      날짜: {metadata.get('date', 'N/A')}")
        self.logger.info(f"      URL: {metadata.get('url', 'N/A')}")

        # 텍스트 필드
        text_data = metadata.get('text', '')
        self.logger.info(f"      텍스트 길이: {len(text_data)}자")

        # HTML 필드 (중요!)
        html_data = metadata.get('html', '')
        if html_data:
            self.logger.info(f"      HTML 구조: ✅ 저장됨 ({len(html_data)}자) - 표/레이아웃 맥락 포함")
        else:
            self.logger.info(f"      HTML 구조: ❌ 없음")

        # html_available 플래그
        if metadata.get('html_available'):
            self.logger.info(f"      HTML 활용 가능: ✅")

        # 이미지/첨부파일 URL
        if metadata.get('image_url'):
            self.logger.info(f"      이미지 URL: {metadata.get('image_url', '')[:50]}...")
        if metadata.get('attachment_url'):
            self.logger.info(f"      첨부파일 URL: {metadata.get('attachment_url', '')[:50]}...")

    def print_summary(self):
        """최종 통계 출력"""
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 크롤링 최종 통계")
        self.logger.info("="*80)

        total_all = 0
        success_all = 0
        failure_all = 0
        skipped_all = 0

        for category, stats in self.stats.items():
            if stats['total'] > 0:
                self.logger.info(f"\n{category.upper()}:")
                self.logger.info(f"  전체: {stats['total']}개")
                self.logger.info(f"  성공: {stats['success']}개")
                self.logger.info(f"  실패: {stats['failure']}개")
                self.logger.info(f"  스킵: {stats['skipped']}개")

                total_all += stats['total']
                success_all += stats['success']
                failure_all += stats['failure']
                skipped_all += stats['skipped']

        self.logger.info("\n" + "-"*80)
        self.logger.info("전체 합계:")
        self.logger.info(f"  전체: {total_all}개")
        self.logger.info(f"  성공: {success_all}개")
        self.logger.info(f"  실패: {failure_all}개")
        self.logger.info(f"  스킵: {skipped_all}개")
        self.logger.info("="*80)

        self.logger.info(f"\n✅ 로그 파일 저장 완료: {self.log_file}\n")

    def close(self):
        """로거 종료"""
        handlers = self.logger.handlers[:]
        for handler in handlers:
            handler.close()
            self.logger.removeHandler(handler)


# 전역 로거 인스턴스 (싱글톤 패턴)
_global_logger: Optional[CrawlerLogger] = None


def get_logger() -> CrawlerLogger:
    """전역 로거 가져오기"""
    global _global_logger
    if _global_logger is None:
        _global_logger = CrawlerLogger()
    return _global_logger


def close_logger():
    """전역 로거 종료"""
    global _global_logger
    if _global_logger is not None:
        _global_logger.close()
        _global_logger = None
