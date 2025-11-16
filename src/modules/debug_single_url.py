"""
단일 URL 크롤링 디버그 도구

특정 URL의 크롤링 전 과정을 상세하게 추적하고 기록합니다.
각 처리 단계별로:
- 입력값과 출력값 저장
- 함수 호출 흐름 로깅
- 중간 결과물 파일로 저장
- 오류 발생 시 상세 정보 기록

사용법:
    python debug_single_url.py <URL> [--category <category>]

예시:
    python debug_single_url.py "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2" --category notice
"""

import sys
import json
import traceback
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import logging

# modules 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from pymongo import MongoClient
from config import CrawlerConfig
from crawling import NoticeCrawler, JobCrawler, SeminarCrawler
from processing import DocumentProcessor
from processing.multimodal_processor import MultimodalProcessor
from processing.upstage_client import UpstageClient


class DebugTracker:
    """
    디버그 추적 클래스

    각 처리 단계의 입력/출력을 기록하고 파일로 저장
    """

    def __init__(self, url: str, category: str = "notice"):
        self.url = url
        self.category = category

        # 디버그 디렉토리 생성 (timestamp 저장)
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.debug_dir = Path("logs/debug") / f"debug_{self.timestamp}"
        self.debug_dir.mkdir(parents=True, exist_ok=True)

        # 로거 설정
        self.logger = self._setup_logger()

        # 단계별 결과 저장
        self.steps: List[Dict[str, Any]] = []
        self.current_step = 0

        self.logger.info("="*80)
        self.logger.info(f"🔍 디버그 세션 시작")
        self.logger.info(f"URL: {url}")
        self.logger.info(f"카테고리: {category}")
        self.logger.info(f"출력 디렉토리: {self.debug_dir}")
        self.logger.info("="*80)

    def _setup_logger(self) -> logging.Logger:
        """로거 설정"""
        logger = logging.getLogger("debug_tracker")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        # 파일 핸들러
        log_file = self.debug_dir / "debug.log"
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # 콘솔 핸들러
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # 포맷
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    def _sanitize_filename(self, text: str, max_length: int = 50) -> str:
        """
        파일/폴더명에 사용할 수 있도록 텍스트 정제

        Args:
            text: 원본 텍스트
            max_length: 최대 길이

        Returns:
            정제된 문자열
        """
        # 파일명에 사용 불가능한 문자 제거
        # Windows/Linux/Mac 공통: / \ : * ? " < > |
        sanitized = re.sub(r'[/\\:*?"<>|]', '', text)

        # 공백을 언더스코어로 치환
        sanitized = sanitized.replace(' ', '_')

        # 연속된 언더스코어를 하나로
        sanitized = re.sub(r'_+', '_', sanitized)

        # 앞뒤 언더스코어 제거
        sanitized = sanitized.strip('_')

        # 길이 제한
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        return sanitized

    def update_folder_name_with_title(self, title: str):
        """
        제목을 포함하도록 폴더명 업데이트

        Args:
            title: 게시글 제목
        """
        try:
            # 제목 정제
            clean_title = self._sanitize_filename(title, max_length=50)

            # 새 폴더명 생성 (기존 timestamp 사용)
            new_dir_name = f"debug_{self.timestamp}_{clean_title}"
            new_debug_dir = self.debug_dir.parent / new_dir_name

            # 기존 폴더를 새 폴더로 이동
            if self.debug_dir.exists() and self.debug_dir != new_debug_dir:
                shutil.move(str(self.debug_dir), str(new_debug_dir))
                self.debug_dir = new_debug_dir

                # 로거의 파일 핸들러 업데이트
                for handler in self.logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        handler.close()
                        self.logger.removeHandler(handler)

                # 새 파일 핸들러 추가
                log_file = self.debug_dir / "debug.log"
                file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
                file_handler.setLevel(logging.DEBUG)
                formatter = logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

                self.logger.info(f"\n📁 폴더명 업데이트: {new_dir_name}")

        except Exception as e:
            self.logger.warning(f"폴더명 업데이트 실패: {e}")

    def start_step(self, step_name: str, description: str):
        """처리 단계 시작"""
        self.current_step += 1
        step_num = f"{self.current_step:02d}"

        self.logger.info("\n" + "="*80)
        self.logger.info(f"STEP {step_num}: {step_name}")
        self.logger.info(f"설명: {description}")
        self.logger.info("="*80)

        self.current_step_data = {
            "step_number": step_num,
            "step_name": step_name,
            "description": description,
            "start_time": datetime.now().isoformat(),
            "input": None,
            "output": None,
            "error": None,
            "success": False
        }

    def log_input(self, input_data: Any, description: str = ""):
        """입력 데이터 로깅"""
        self.logger.info(f"\n📥 입력 데이터{': ' + description if description else ''}")

        if isinstance(input_data, str):
            self.logger.info(f"  타입: str")
            self.logger.info(f"  길이: {len(input_data)} 문자")
            # Data URI는 짧게 표시
            display_str = self._truncate_data_uri(input_data, max_length=200)
            if len(input_data) <= 200 or input_data.startswith('data:'):
                self.logger.info(f"  내용: {display_str}")
            else:
                self.logger.info(f"  내용 (처음 200자): {input_data[:200]}...")
        elif isinstance(input_data, (list, tuple)):
            self.logger.info(f"  타입: {type(input_data).__name__}")
            self.logger.info(f"  개수: {len(input_data)}개")
            if input_data and len(input_data) <= 5:
                for i, item in enumerate(input_data):
                    # 리스트 항목도 Data URI 체크
                    if isinstance(item, str):
                        display_item = self._truncate_data_uri(item, max_length=100)
                    else:
                        display_item = str(item)[:100]
                    self.logger.info(f"  [{i}]: {display_item}")
        elif isinstance(input_data, dict):
            self.logger.info(f"  타입: dict")
            self.logger.info(f"  키: {list(input_data.keys())}")
        else:
            self.logger.info(f"  타입: {type(input_data).__name__}")
            self.logger.info(f"  값: {str(input_data)[:200]}")

        self.current_step_data["input"] = self._serialize(input_data)

    def log_output(self, output_data: Any, description: str = ""):
        """출력 데이터 로깅"""
        self.logger.info(f"\n📤 출력 데이터{': ' + description if description else ''}")

        if isinstance(output_data, str):
            self.logger.info(f"  타입: str")
            self.logger.info(f"  길이: {len(output_data)} 문자")
            # Data URI는 짧게 표시
            display_str = self._truncate_data_uri(output_data, max_length=200)
            if len(output_data) <= 200 or output_data.startswith('data:'):
                self.logger.info(f"  내용: {display_str}")
            else:
                self.logger.info(f"  내용 (처음 200자): {output_data[:200]}...")
        elif isinstance(output_data, (list, tuple)):
            self.logger.info(f"  타입: {type(output_data).__name__}")
            self.logger.info(f"  개수: {len(output_data)}개")
            if output_data and len(output_data) <= 5:
                for i, item in enumerate(output_data):
                    # 리스트 항목도 Data URI 체크
                    if isinstance(item, str):
                        display_item = self._truncate_data_uri(item, max_length=100)
                    else:
                        display_item = str(item)[:100]
                    self.logger.info(f"  [{i}]: {display_item}")
        elif isinstance(output_data, dict):
            self.logger.info(f"  타입: dict")
            self.logger.info(f"  키: {list(output_data.keys())}")
            for key, value in output_data.items():
                if isinstance(value, str):
                    # Data URI는 짧게 표시
                    display_value = self._truncate_data_uri(value, max_length=100)
                    self.logger.info(f"  {key}: {display_value}")
                elif isinstance(value, (list, tuple)):
                    self.logger.info(f"  {key}: [{len(value)}개 항목]")
                else:
                    self.logger.info(f"  {key}: {value}")
        else:
            self.logger.info(f"  타입: {type(output_data).__name__}")
            self.logger.info(f"  값: {str(output_data)[:200]}")

        self.current_step_data["output"] = self._serialize(output_data)

    def log_function_call(self, module: str, function: str, args: Dict[str, Any] = None):
        """함수 호출 로깅"""
        self.logger.info(f"\n🔧 함수 호출")
        self.logger.info(f"  모듈: {module}")
        self.logger.info(f"  함수: {function}")
        if args:
            self.logger.info(f"  인자:")
            for key, value in args.items():
                if isinstance(value, str):
                    # Data URI는 짧게 표시
                    display_value = self._truncate_data_uri(value, max_length=100)
                    self.logger.info(f"    {key}: {display_value}")
                else:
                    self.logger.info(f"    {key}: {value}")

    def end_step(self, success: bool = True, save_to_file: bool = True):
        """처리 단계 종료"""
        self.current_step_data["end_time"] = datetime.now().isoformat()
        self.current_step_data["success"] = success

        # 파일로 저장
        if save_to_file and self.current_step_data.get("output"):
            step_num = self.current_step_data["step_number"]
            step_name = self.current_step_data["step_name"].replace(" ", "_").lower()

            output_file = self.debug_dir / f"{step_num}_{step_name}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_step_data["output"], f, ensure_ascii=False, indent=2)

            self.logger.info(f"\n💾 출력 파일 저장: {output_file.name}")

        status = "✅ 성공" if success else "❌ 실패"
        self.logger.info(f"\n{status}: {self.current_step_data['step_name']}")

        self.steps.append(self.current_step_data)

    def log_error(self, error: Exception):
        """에러 로깅"""
        error_info = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc()
        }

        self.logger.error(f"\n❌ 에러 발생")
        self.logger.error(f"  타입: {error_info['type']}")
        self.logger.error(f"  메시지: {error_info['message']}")
        self.logger.error(f"\n스택 트레이스:\n{error_info['traceback']}")

        self.current_step_data["error"] = error_info
        self.end_step(success=False)

    def save_raw_html(self, html: str):
        """원본 HTML 저장"""
        html_file = self.debug_dir / "01_raw_html.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        self.logger.info(f"💾 원본 HTML 저장: {html_file.name}")

    def generate_summary(self):
        """전체 요약 생성"""
        summary = {
            "url": self.url,
            "category": self.category,
            "debug_dir": str(self.debug_dir),
            "total_steps": len(self.steps),
            "successful_steps": sum(1 for s in self.steps if s.get("success")),
            "failed_steps": sum(1 for s in self.steps if not s.get("success")),
            "steps": self.steps
        }

        summary_file = self.debug_dir / "summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        self.logger.info("\n" + "="*80)
        self.logger.info("📊 최종 요약")
        self.logger.info("="*80)
        self.logger.info(f"전체 단계: {summary['total_steps']}개")
        self.logger.info(f"성공: {summary['successful_steps']}개")
        self.logger.info(f"실패: {summary['failed_steps']}개")
        self.logger.info(f"\n💾 요약 파일: {summary_file}")
        self.logger.info(f"📁 모든 결과: {self.debug_dir}")
        self.logger.info("="*80)

    def _truncate_data_uri(self, url: str, max_length: int = 100) -> str:
        """
        Data URI를 짧게 표시

        Args:
            url: URL 문자열
            max_length: 최대 길이 (Data URI가 아닌 경우)

        Returns:
            짧게 표시된 문자열
        """
        if url.startswith('data:'):
            # Data URI 형식: data:image/png;base64,iVBORw0KGgo...
            if ';base64,' in url:
                parts = url.split(';base64,')
                mime_type = parts[0].replace('data:', '')
                data_preview = parts[1][:20] if len(parts) > 1 else ''
                total_length = len(parts[1]) if len(parts) > 1 else 0
                return f"data:{mime_type};base64,{data_preview}...({total_length} chars)"
            else:
                return f"{url[:50]}... (Data URI, {len(url)} chars)"
        elif len(url) > max_length:
            return f"{url[:max_length]}..."
        return url

    def _serialize(self, data: Any) -> Any:
        """JSON 직렬화 가능한 형태로 변환 (Data URI는 짧게 표시)"""
        if isinstance(data, str):
            # Data URI는 짧게 표시
            return self._truncate_data_uri(data)
        elif isinstance(data, (int, float, bool, type(None))):
            return data
        elif isinstance(data, (list, tuple)):
            return [self._serialize(item) for item in data]
        elif isinstance(data, dict):
            return {key: self._serialize(value) for key, value in data.items()}
        else:
            return str(data)


def debug_url(url: str, category: str = "notice"):
    """
    단일 URL 디버그

    Args:
        url: 크롤링할 URL
        category: 카테고리 (notice, job, seminar)
    """
    tracker = DebugTracker(url, category)

    try:
        # ========== STEP 1: 크롤러 선택 ==========
        tracker.start_step("크롤러 선택", "카테고리에 맞는 크롤러 초기화")
        tracker.log_input(category, "카테고리")

        if category == "notice":
            crawler = NoticeCrawler()
        elif category == "job":
            crawler = JobCrawler()
        elif category == "seminar":
            crawler = SeminarCrawler()
        else:
            raise ValueError(f"지원하지 않는 카테고리: {category}")

        tracker.log_output(type(crawler).__name__, "초기화된 크롤러")
        tracker.log_function_call(
            module=f"crawling.{category}_crawler",
            function=f"{category.capitalize()}Crawler.__init__"
        )
        tracker.end_step(save_to_file=False)

        # ========== STEP 2: HTML 다운로드 ==========
        tracker.start_step("HTML 다운로드", "URL에서 HTML 페이지 다운로드")
        tracker.log_input(url, "URL")
        tracker.log_function_call(
            module="requests",
            function="get",
            args={"url": url}
        )

        import requests
        response = requests.get(url, timeout=30)
        html_content = response.text

        tracker.log_output(html_content, "다운로드된 HTML")
        tracker.save_raw_html(html_content)
        tracker.end_step()

        # ========== STEP 3: HTML 파싱 (BeautifulSoup) ==========
        tracker.start_step("HTML 파싱", "BeautifulSoup으로 HTML 파싱 및 데이터 추출")
        tracker.log_input(html_content[:500], "HTML 내용 (일부)")
        tracker.log_function_call(
            module=f"crawling.{category}_crawler",
            function="extract_from_url",
            args={"url": url}
        )

        # 크롤러의 extract_from_url 메서드 호출
        crawled_data = crawler.extract_from_url(url)

        if crawled_data:
            title, text, image_list, attachment_list, date, crawled_url = crawled_data
            parsed_result = {
                "title": title,
                "text": text[:500] if text else None,
                "text_length": len(text) if text else 0,
                "image_list": image_list,
                "image_count": len(image_list) if image_list else 0,
                "attachment_list": attachment_list,
                "attachment_count": len(attachment_list) if attachment_list else 0,
                "date": date,
                "url": crawled_url
            }
            tracker.log_output(parsed_result, "파싱 결과")
            tracker.end_step()

            # 제목을 얻었으므로 폴더명 업데이트
            tracker.update_folder_name_with_title(title)
        else:
            tracker.log_error(Exception("크롤링 실패: crawl_page가 None 반환"))
            return

        # ========== STEP 4: 텍스트 청크 분할 ==========
        tracker.start_step("텍스트 청크 분할", "긴 텍스트를 청크 단위로 분할")
        tracker.log_input({
            "text": text[:200] if text else "",
            "chunk_size": CrawlerConfig.CHUNK_SIZE,
            "chunk_overlap": CrawlerConfig.CHUNK_OVERLAP
        }, "텍스트 및 설정")
        tracker.log_function_call(
            module="processing.document_processor",
            function="CharacterTextSplitter.split_text"
        )

        from processing.document_processor import CharacterTextSplitter
        text_splitter = CharacterTextSplitter(
            chunk_size=CrawlerConfig.CHUNK_SIZE,
            chunk_overlap=CrawlerConfig.CHUNK_OVERLAP
        )

        if text and text.strip():
            text_chunks = text_splitter.split_text(text)
        else:
            text_chunks = []

        chunk_result = {
            "total_chunks": len(text_chunks),
            "chunks": [
                {
                    "index": i,
                    "length": len(chunk),
                    "content": chunk[:200] + "..." if len(chunk) > 200 else chunk
                }
                for i, chunk in enumerate(text_chunks)
            ]
        }
        tracker.log_output(chunk_result, "청크 분할 결과")
        tracker.end_step()

        # ========== STEP 5: 멀티모달 프로세서 초기화 ==========
        tracker.start_step("멀티모달 프로세서 초기화", "이미지 OCR 및 문서 파싱을 위한 프로세서 초기화")
        tracker.log_function_call(
            module="processing.multimodal_processor",
            function="MultimodalProcessor.__init__"
        )

        mongo_client = MongoClient(CrawlerConfig.MONGODB_URI)
        multimodal_processor = MultimodalProcessor(mongo_client=mongo_client)

        tracker.log_output({
            "enable_image": multimodal_processor.enable_image,
            "enable_attachment": multimodal_processor.enable_attachment
        }, "프로세서 설정")
        tracker.end_step(save_to_file=False)

        # ========== STEP 6: 이미지 OCR 처리 ==========
        if image_list:
            tracker.start_step("이미지 OCR 처리", f"{len(image_list)}개 이미지에서 텍스트 추출")
            tracker.log_input(image_list, "이미지 URL 리스트")
            tracker.log_function_call(
                module="processing.multimodal_processor",
                function="process_images",
                args={"image_urls": image_list}
            )

            ocr_results = []
            for idx, img_url in enumerate(image_list):
                # Data URI는 짧게 표시
                url_display = tracker._truncate_data_uri(img_url, max_length=50)
                tracker.logger.info(f"\n  🖼️  이미지 {idx+1}/{len(image_list)}: {url_display}")

                try:
                    # Upstage OCR API 호출
                    upstage_client = UpstageClient()
                    ocr_result = upstage_client.extract_text_from_image_url(img_url)

                    if ocr_result and ocr_result.get("text"):
                        ocr_data = {
                            "url": tracker._truncate_data_uri(img_url, max_length=100),  # Data URI 짧게 저장
                            "url_full": img_url if not img_url.startswith('data:') else "data_uri",  # 전체 URL (Data URI는 제외)
                            "success": True,
                            "text_length": len(ocr_result["text"]),
                            "text_full": ocr_result["text"],  # 전체 텍스트
                            "html_full": ocr_result.get("html", "")  # HTML 원본도 저장
                        }
                        tracker.logger.info(f"     ✅ OCR 성공: {ocr_data['text_length']}자 추출")
                        tracker.logger.info(f"     텍스트: {ocr_result['text']}")  # 전체 텍스트 로그
                    else:
                        ocr_data = {
                            "url": tracker._truncate_data_uri(img_url, max_length=100),  # Data URI 짧게 저장
                            "url_full": img_url if not img_url.startswith('data:') else "data_uri",
                            "success": False,
                            "error": "텍스트 추출 실패"
                        }
                        tracker.logger.info(f"     ❌ OCR 실패")

                    ocr_results.append(ocr_data)

                except Exception as e:
                    ocr_data = {
                        "url": tracker._truncate_data_uri(img_url, max_length=100),  # Data URI 짧게 저장
                        "url_full": img_url if not img_url.startswith('data:') else "data_uri",
                        "success": False,
                        "error": str(e)
                    }
                    tracker.logger.error(f"     ❌ OCR 에러: {e}")
                    ocr_results.append(ocr_data)

            tracker.log_output({
                "total_images": len(image_list),
                "successful": sum(1 for r in ocr_results if r.get("success")),
                "failed": sum(1 for r in ocr_results if not r.get("success")),
                "results": ocr_results
            }, "OCR 처리 결과")
            tracker.end_step()
        else:
            tracker.logger.info("\nℹ️  이미지가 없어 OCR 단계를 건너뜁니다.")

        # ========== STEP 7: 첨부파일 파싱 ==========
        if attachment_list:
            tracker.start_step("첨부파일 파싱", f"{len(attachment_list)}개 첨부파일에서 텍스트 추출")
            tracker.log_input(attachment_list, "첨부파일 URL 리스트")
            tracker.log_function_call(
                module="processing.multimodal_processor",
                function="process_attachments",
                args={"attachment_urls": attachment_list}
            )

            parse_results = []
            for idx, att_url in enumerate(attachment_list):
                # Data URI는 짧게 표시
                url_display = tracker._truncate_data_uri(att_url, max_length=50)
                tracker.logger.info(f"\n  📄 첨부파일 {idx+1}/{len(attachment_list)}: {url_display}")

                try:
                    # Upstage Document Parse API 호출
                    upstage_client = UpstageClient()
                    parse_result = upstage_client.parse_document_from_url(att_url)

                    if parse_result and parse_result.get("text"):
                        parse_data = {
                            "url": tracker._truncate_data_uri(att_url, max_length=100),  # Data URI 짧게 저장
                            "url_full": att_url if not att_url.startswith('data:') else "data_uri",  # 전체 URL (Data URI는 제외)
                            "success": True,
                            "file_type": Path(att_url).suffix.lower()[1:] if Path(att_url).suffix else "unknown",
                            "text_length": len(parse_result["text"]),
                            "text_full": parse_result["text"],  # 전체 텍스트
                            "html_full": parse_result.get("html", ""),  # HTML 원본도 저장
                            "markdown": parse_result.get("markdown", "")  # Markdown (있으면)
                        }
                        tracker.logger.info(f"     ✅ 파싱 성공: {parse_data['file_type']} - {parse_data['text_length']}자 추출")
                        tracker.logger.info(f"     텍스트: {parse_result['text']}")  # 전체 텍스트 로그
                    else:
                        parse_data = {
                            "url": tracker._truncate_data_uri(att_url, max_length=100),  # Data URI 짧게 저장
                            "url_full": att_url if not att_url.startswith('data:') else "data_uri",
                            "success": False,
                            "error": "텍스트 추출 실패"
                        }
                        tracker.logger.info(f"     ❌ 파싱 실패")

                    parse_results.append(parse_data)

                except Exception as e:
                    parse_data = {
                        "url": tracker._truncate_data_uri(att_url, max_length=100),  # Data URI 짧게 저장
                        "url_full": att_url if not att_url.startswith('data:') else "data_uri",
                        "success": False,
                        "error": str(e)
                    }
                    tracker.logger.error(f"     ❌ 파싱 에러: {e}")
                    parse_results.append(parse_data)

            tracker.log_output({
                "total_attachments": len(attachment_list),
                "successful": sum(1 for r in parse_results if r.get("success")),
                "failed": sum(1 for r in parse_results if not r.get("success")),
                "results": parse_results
            }, "문서 파싱 결과")
            tracker.end_step()
        else:
            tracker.logger.info("\nℹ️  첨부파일이 없어 파싱 단계를 건너뜁니다.")

        # ========== STEP 8: 멀티모달 콘텐츠 생성 ==========
        tracker.start_step("멀티모달 콘텐츠 생성", "텍스트, 이미지, 첨부파일 결과 통합")
        tracker.log_function_call(
            module="processing.multimodal_processor",
            function="create_multimodal_content"
        )

        multimodal_content, failures = multimodal_processor.create_multimodal_content(
            title=title,
            url=url,
            date=date,
            text_chunks=text_chunks,
            image_urls=image_list if image_list else [],
            attachment_urls=attachment_list if attachment_list else []
        )

        content_summary = {
            "title": multimodal_content.title,
            "url": multimodal_content.url,
            "date": multimodal_content.date,
            "text_chunks_count": len(multimodal_content.text_chunks),
            "image_contents_count": len(multimodal_content.image_contents),
            "attachment_contents_count": len(multimodal_content.attachment_contents),
            "failures": {
                "image_failed": len(failures["image_failed"]),
                "image_unsupported": len(failures["image_unsupported"]),
                "attachment_failed": len(failures["attachment_failed"]),
                "attachment_unsupported": len(failures["attachment_unsupported"])
            }
        }
        tracker.log_output(content_summary, "멀티모달 콘텐츠")

        # 실패 검증 (document_processor.py와 동일한 로직)
        has_critical_failure = False
        failure_reasons = []

        # 이미지가 있었는데 추출 실패한 경우
        if image_list and failures["image_failed"]:
            has_critical_failure = True
            failure_reasons.append(f"이미지 OCR 실패 {len(failures['image_failed'])}개")
            tracker.logger.error(f"\n⚠️  경고: 이미지 {len(failures['image_failed'])}개 OCR 실패")

        # 첨부파일이 있었는데 추출 실패한 경우
        if attachment_list and failures["attachment_failed"]:
            has_critical_failure = True
            failure_reasons.append(f"첨부파일 파싱 실패 {len(failures['attachment_failed'])}개")
            tracker.logger.error(f"\n⚠️  경고: 첨부파일 {len(failures['attachment_failed'])}개 파싱 실패")

        # 지원하지 않는 형식은 경고만
        if failures["image_unsupported"]:
            tracker.logger.warning(f"\nℹ️  이미지 {len(failures['image_unsupported'])}개 지원하지 않는 형식")
        if failures["attachment_unsupported"]:
            tracker.logger.warning(f"\nℹ️  첨부파일 {len(failures['attachment_unsupported'])}개 지원하지 않는 형식")

        # 실패가 있으면 예외 발생
        if has_critical_failure:
            error_message = " / ".join(failure_reasons)
            tracker.logger.error(f"\n❌ 게시글 처리 실패: {error_message}")
            tracker.end_step()
            raise Exception(error_message)

        tracker.end_step()

        # ========== STEP 9: 임베딩 아이템 생성 ==========
        tracker.start_step("임베딩 아이템 생성", "Pinecone 업로드용 최종 아이템 생성")
        tracker.log_function_call(
            module="processing.multimodal_processor",
            function="MultimodalContent.to_embedding_items"
        )

        embedding_items = multimodal_content.to_embedding_items()

        # 카테고리 추가
        for text, metadata in embedding_items:
            metadata["category"] = category

        items_detail = []
        for idx, (text, metadata) in enumerate(embedding_items):
            items_detail.append({
                "index": idx,
                "content_type": metadata.get("content_type"),
                "source": metadata.get("source"),
                "text_length": len(text),
                "text_full": text,  # 전체 텍스트 (preview 아님!)
                "metadata": metadata
            })

        tracker.log_output({
            "total_items": len(embedding_items),
            "items": items_detail
        }, "임베딩 아이템")
        tracker.end_step()

        # 최종 요약 생성
        tracker.generate_summary()

    except Exception as e:
        tracker.log_error(e)
        tracker.generate_summary()
        raise


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="단일 URL 크롤링 디버그 도구")
    parser.add_argument("url", help="크롤링할 URL")
    parser.add_argument("--category", "-c", default="notice",
                       choices=["notice", "job", "seminar"],
                       help="카테고리 (기본값: notice)")

    args = parser.parse_args()

    debug_url(args.url, args.category)


if __name__ == "__main__":
    main()
