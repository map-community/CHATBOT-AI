"""
Pipeline Logger

RAG 파이프라인의 각 단계를 명확하고 체계적으로 로깅하는 유틸리티
단계별 철학과 맥락을 담아내어 디버깅과 모니터링을 용이하게 함
"""
import logging
import time
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PipelineLogger:
    """
    RAG 파이프라인 단계별 구조화 로거

    Features:
    - 단계별 명확한 구분 (PHASE 1, 2, 3...)
    - 들여쓰기 지원으로 하위 작업 명시
    - 타이밍 자동 추적
    - 입력/출력/결정 근거 명시
    """

    def __init__(self, logger_name: str = __name__):
        self.logger = logging.getLogger(logger_name)
        self.indent_level = 0
        self.phase_timings = {}

    def _log(self, level: str, message: str, indent_override: Optional[int] = None):
        """
        들여쓰기를 적용한 로그 출력

        Args:
            level: 로그 레벨 (info, warning, error)
            message: 로그 메시지
            indent_override: 들여쓰기 레벨 강제 지정
        """
        indent = "   " * (indent_override if indent_override is not None else self.indent_level)
        formatted_message = f"{indent}{message}"

        if level == "info":
            self.logger.info(formatted_message)
        elif level == "warning":
            self.logger.warning(formatted_message)
        elif level == "error":
            self.logger.error(formatted_message)
        elif level == "debug":
            self.logger.debug(formatted_message)

    def phase_start(self, phase_num: int, title: str, purpose: str):
        """
        새로운 단계 시작

        Args:
            phase_num: 단계 번호 (1, 2, 3...)
            title: 단계 제목
            purpose: 이 단계의 목적/철학
        """
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info(f"PHASE {phase_num}: {title}")
        self.logger.info("=" * 80)
        self.logger.info(f"📋 목적: {purpose}")
        self.indent_level = 0
        self.phase_timings[phase_num] = time.time()

    def phase_end(self, phase_num: int, summary: Optional[str] = None):
        """
        단계 종료 및 요약

        Args:
            phase_num: 단계 번호
            summary: 단계 결과 요약 (선택)
        """
        elapsed = time.time() - self.phase_timings.get(phase_num, time.time())

        if summary:
            self.logger.info("")
            self.logger.info(f"✅ 완료: {summary}")

        self.logger.info(f"⏱️  소요 시간: {elapsed:.2f}초")
        self.logger.info("=" * 80)
        self.indent_level = 0

    def section(self, title: str, emoji: str = "▶"):
        """
        단계 내 섹션 구분

        Args:
            title: 섹션 제목
            emoji: 아이콘 (기본: ▶)
        """
        self.logger.info("")
        self.logger.info(f"{emoji} {title}")
        self.logger.info("-" * 60)

    def input(self, label: str, value: Any, truncate: Optional[int] = None):
        """
        입력 데이터 로깅

        Args:
            label: 입력 항목명
            value: 입력 값
            truncate: 문자열 자를 길이 (선택)
        """
        if isinstance(value, str) and truncate and len(value) > truncate:
            display_value = value[:truncate] + "..."
        else:
            display_value = value

        self._log("info", f"📥 입력 - {label}: {display_value}")

    def output(self, label: str, value: Any, truncate: Optional[int] = None):
        """
        출력 데이터 로깅

        Args:
            label: 출력 항목명
            value: 출력 값
            truncate: 문자열 자를 길이 (선택)
        """
        if isinstance(value, str) and truncate and len(value) > truncate:
            display_value = value[:truncate] + "..."
        else:
            display_value = value

        self._log("info", f"📤 출력 - {label}: {display_value}")

    def metric(self, label: str, value: Any, unit: str = ""):
        """
        메트릭 로깅 (숫자, 개수 등)

        Args:
            label: 메트릭명
            value: 값
            unit: 단위 (선택)
        """
        unit_str = f" {unit}" if unit else ""
        self._log("info", f"📊 {label}: {value}{unit_str}")

    def decision(self, condition: str, result: bool, reason: str = ""):
        """
        의사결정 로깅

        Args:
            condition: 판단 조건
            result: 판단 결과 (True/False)
            reason: 판단 근거 (선택)
        """
        icon = "✅" if result else "❌"
        self._log("info", f"{icon} 판단: {condition} → {result}")

        if reason:
            self._log("info", f"   ∟ 근거: {reason}")

    def substep(self, message: str):
        """
        하위 작업 로깅

        Args:
            message: 작업 내용
        """
        self._log("info", f"  • {message}")

    def warning(self, message: str, detail: str = ""):
        """
        경고 로깅

        Args:
            message: 경고 메시지
            detail: 상세 정보 (선택)
        """
        self._log("warning", f"⚠️  {message}")

        if detail:
            self._log("warning", f"   ∟ {detail}")

    def error(self, message: str, detail: str = ""):
        """
        에러 로깅

        Args:
            message: 에러 메시지
            detail: 상세 정보 (선택)
        """
        self._log("error", f"❌ {message}")

        if detail:
            self._log("error", f"   ∟ {detail}")

    def debug_data(self, label: str, data: Dict[str, Any]):
        """
        디버그 데이터 구조화 출력

        Args:
            label: 데이터 레이블
            data: 딕셔너리 형태의 디버그 정보
        """
        self._log("debug", f"🔍 디버그 - {label}:")

        for key, value in data.items():
            self._log("debug", f"   • {key}: {value}")

    def ranking_table(self, title: str, items: List[Dict[str, Any]], top_k: int = 5):
        """
        순위 테이블 로깅

        Args:
            title: 테이블 제목
            items: 순위 항목 리스트
                  [{"rank": 1, "score": 0.95, "title": "...", "date": "..."}, ...]
            top_k: 표시할 최대 개수
        """
        self.logger.info("")
        self.logger.info(f"🏆 {title} (Top {min(top_k, len(items))})")
        self.logger.info("-" * 80)

        for i, item in enumerate(items[:top_k]):
            rank = item.get("rank", i + 1)
            score = item.get("score", 0.0)
            title_text = item.get("title", "")
            date = item.get("date", "")
            url = item.get("url", "")
            marker = item.get("marker", "")

            # 제목 길이 제한
            if len(title_text) > 60:
                title_text = title_text[:60] + "..."

            marker_str = f" {marker}" if marker else ""
            self.logger.info(f"   {rank}위: [{score:.4f}]{marker_str} {title_text}")

            if date:
                self.logger.info(f"        날짜: {date}")

            if url:
                url_display = url[:80] + "..." if len(url) > 80 else url
                self.logger.info(f"        URL: {url_display}")

        self.logger.info("-" * 80)

    @contextmanager
    def indent(self):
        """
        Context manager로 들여쓰기 레벨 임시 증가

        Usage:
            with pipeline_logger.indent():
                pipeline_logger.substep("하위 작업")
        """
        self.indent_level += 1
        try:
            yield
        finally:
            self.indent_level -= 1

    @contextmanager
    def timer(self, label: str):
        """
        Context manager로 실행 시간 측정

        Args:
            label: 측정 대상 작업명

        Usage:
            with pipeline_logger.timer("문서 검색"):
                # ... 검색 로직 ...
        """
        start_time = time.time()
        self._log("info", f"⏳ 시작: {label}")

        try:
            yield
        finally:
            elapsed = time.time() - start_time
            self._log("info", f"✅ 완료: {label} ({elapsed:.2f}초)")


# 전역 인스턴스 (싱글톤 패턴)
_pipeline_logger_instance = None


def get_pipeline_logger(logger_name: str = "modules") -> PipelineLogger:
    """
    PipelineLogger 싱글톤 인스턴스 반환

    Args:
        logger_name: 로거 이름

    Returns:
        PipelineLogger 인스턴스
    """
    global _pipeline_logger_instance

    if _pipeline_logger_instance is None:
        _pipeline_logger_instance = PipelineLogger(logger_name)

    return _pipeline_logger_instance
