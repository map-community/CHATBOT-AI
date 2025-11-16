# 크롤링 효율성 최적화 구현 완료 보고서

## 📋 개요

이 문서는 크롤링 시스템의 효율성 최적화 및 RAG 품질 향상을 위해 구현된 모든 변경사항을 요약합니다.

**작업 기간**: 현재 세션
**브랜치**: `claude/optimize-crawling-efficiency-011qG8K2BE4f7zsKeLJpiapn`
**상태**: ✅ 모든 변경사항 커밋 및 푸시 완료

---

## 🎯 주요 구현 사항

### 1. 파일 기반 로깅 시스템 ✅

**요구사항**: 콘솔 출력만으로는 추적이 어려워 파일로 저장하여 어떤 게시글이 성공/실패했는지 확인 가능하도록 구현

**구현 내용**:
- **파일**: `src/modules/utils/logging_config.py` (신규 생성)
- **주요 클래스**: `CrawlerLogger`

**기능**:
```python
class CrawlerLogger:
    def __init__(self, log_dir: str = "logs"):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = self.log_dir / f"crawl_{timestamp}.txt"

    # 성공한 게시글 추적
    def log_post_success(self, category, title, url, text_length,
                         image_count, attachment_count, embedding_items)

    # 실패한 게시글 추적 (에러 이유 포함)
    def log_post_failure(self, category, title, url, error)

    # OCR/문서 파싱 상세 로그
    def log_multimodal_detail(self, content_type, url, success, detail)

    # 최종 통계 요약
    def print_summary()
```

**로그 파일 위치**: `logs/crawl_YYYY-MM-DD_HH-MM-SS.txt`

**로그 내용**:
- 각 게시글별 처리 성공/실패 여부
- 텍스트 길이, 이미지 개수, 첨부파일 개수
- OCR/문서 파싱 상세 결과 (URL, 성공 여부, 추출 문자 수)
- 카테고리별 통계 (전체/성공/실패/건너뜀)
- 멀티모달 처리 통계 (이미지 OCR, 문서 파싱)

---

### 2. 단일 URL 디버깅 도구 ✅

**요구사항**: 특정 URL의 전체 처리 과정을 단계별로 추적하여 각 단계의 입력/출력 확인

**구현 내용**:
- **파일**: `src/modules/debug_single_url.py` (신규 생성)
- **문서**: `src/modules/DEBUG_GUIDE.md` (신규 생성)

**9단계 처리 추적**:
1. 크롤러 선택 (카테고리별)
2. HTML 다운로드
3. HTML 파싱 (BeautifulSoup)
4. 텍스트 청크 분할
5. 멀티모달 프로세서 초기화
6. 이미지 OCR 처리
7. 첨부파일 파싱
8. 멀티모달 콘텐츠 생성
9. 임베딩 아이템 생성

**각 단계별 로깅**:
```python
{
    "step_number": 1,
    "step_name": "크롤러 선택",
    "description": "카테고리에 맞는 크롤러 인스턴스 생성",
    "start_time": "2025-11-16T10:30:00",
    "end_time": "2025-11-16T10:30:01",
    "duration_seconds": 1.2,
    "success": true,
    "inputs": {...},
    "outputs": {...},
    "function_calls": [...]
}
```

**출력 파일**:
- `logs/debug/debug_TIMESTAMP/00_summary.json` - 전체 요약
- `logs/debug/debug_TIMESTAMP/01_크롤러_선택.json` - 각 단계별 상세
- `logs/debug/debug_TIMESTAMP/02_HTML_다운로드.json`
- ... (9개 파일)

**사용 방법**:
```bash
python debug_single_url.py "URL" --category notice
```

---

### 3. Upstage API HTML 텍스트 추출 개선 ✅

**문제**: OCR API가 `content.text`는 비워두고 `content.html`의 `<img alt="...">` 속성에만 텍스트를 넣는 경우 발생

**해결 방법**: `_extract_text_from_html()` 메서드 추가

**파일**: `src/modules/processing/upstage_client.py`

**구현 로직**:
```python
def _extract_text_from_html(self, html: str) -> str:
    """HTML에서 텍스트 추출 (BeautifulSoup 사용)"""
    soup = BeautifulSoup(html, 'html.parser')
    texts = []

    # 1. img[alt] 속성 우선 추출 (OCR 결과)
    for img in soup.find_all('img'):
        alt_text = img.get('alt', '').strip()
        if alt_text and alt_text != 'x':
            texts.append(alt_text)

    # 2. 구조화된 태그에서 추출 (h1-h6, p, li, td, th)
    for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                                'p', 'li', 'td', 'th']):
        elem_text = elem.get_text(strip=True)
        if elem_text and not any(elem_text in existing for existing in texts):
            texts.append(elem_text)

    return '\n\n'.join(texts)
```

**효과**:
- OCR "실패" 오류 해결
- 이미지 내 텍스트 정확히 추출
- 구조화된 HTML 내용도 보존

---

### 4. RAG 품질 향상 - HTML 원본 저장 ✅

**요구사항**: 순수 텍스트만 저장하면 구조 정보가 손실되므로 HTML 전체도 함께 저장

**구현 내용**:

**기존 응답 구조**:
```python
return {
    "text": extracted_text  # 텍스트만
}
```

**개선된 응답 구조**:
```python
return {
    "text": extracted_text,           # 검색용 순수 텍스트
    "html": result.get("content", {}).get("html", ""),  # 구조 보존용 HTML
    "full_html": result.get("content", {}).get("html", ""),  # 별칭
    "markdown": result.get("content", {}).get("markdown", ""),  # 마크다운 (있으면)
    "elements": result.get("elements", []),  # 요소 정보
    "source_url": url  # 출처 URL
}
```

**적용 메서드**:
- `parse_document_from_url()` - 문서 파싱
- `extract_text_from_image_url()` - 이미지 OCR

**장점**:
- LLM이 원본 HTML을 보고 더 정확한 답변 생성
- 표, 목록, 제목 등의 구조 정보 보존
- 검색은 `text`, 응답 생성은 `html` 사용 가능

---

### 5. download.php 첨부파일 처리 개선 ✅

**문제**:
```
지원하지 않는 파일 타입: text/html; charset=utf-8
파일명: download.php?bo_table=sub5_1&wr_id=28848&no=0&page=2
```

**원인**:
1. `allow_redirects=False`로 리다이렉트를 따라가지 않음
2. URL에 쿼리 파라미터가 포함된 파일명
3. Content-Disposition 헤더 파싱 미흡
4. Content-Type 기반 확장자 추론 부재

**해결 방법**:

#### 5.1 리다이렉트 활성화
```python
# Before
file_response = requests.get(url, timeout=30)

# After
file_response = requests.get(url, timeout=30, allow_redirects=True)
```

#### 5.2 3단계 파일명 추출 전략

**우선순위 1: Content-Disposition 헤더 (RFC 5987 지원)**
```python
# RFC 5987: filename*=UTF-8''encoded_filename
match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)|filename=([^;]+)",
                  content_disposition)
if match:
    encoded_filename = match.group(1)
    if encoded_filename:
        from urllib.parse import unquote
        filename = unquote(encoded_filename).strip('"\'')
```

**우선순위 2: URL 경로 (쿼리 파라미터 제거)**
```python
if not filename:
    filename = Path(url).name
    # download.php?bo_table=... → download.php
    if '?' in filename:
        filename = filename.split('?')[0]
```

**우선순위 3: Content-Type에서 확장자 추론**
```python
if filename == 'download.php' or not Path(filename).suffix:
    type_to_ext = {
        'application/pdf': '.pdf',
        'application/x-hwp': '.hwp',
        'application/haansofthwp': '.hwp',
        'application/msword': '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        # ...
    }
    for mime_type, ext in type_to_ext.items():
        if mime_type in content_type:
            filename = f"document{ext}"
            break
```

#### 5.3 상세 로깅 추가
```python
logger.info(f"📊 응답 정보: Content-Type={content_type}, Content-Disposition={content_disposition}")
logger.info(f"📄 최종 파일명: {filename}")
```

**효과**:
- download.php URL 정상 처리
- 국제화된 파일명 지원 (UTF-8 인코딩)
- 확장자 없는 파일도 Content-Type 기반 처리
- 디버깅 용이성 향상

---

### 6. 디버그 로그 완전성 개선 ✅

**문제**: 로그에서 `text_preview[:200]`로 텍스트를 잘라서 전체 내용 확인 불가

**해결**:
```python
# Before
"text_preview": text[:200] if text else ""

# After
"text_full": text  # 전체 텍스트 저장
```

**적용 위치**: `debug_single_url.py`의 모든 텍스트 로깅

---

## 📊 변경 파일 목록

### 신규 생성 (4개)
1. `src/modules/utils/logging_config.py` - 로깅 시스템
2. `src/modules/debug_single_url.py` - 디버깅 도구
3. `src/modules/DEBUG_GUIDE.md` - 디버깅 가이드
4. `IMPLEMENTATION_SUMMARY.md` - 이 문서

### 수정 (3개)
1. `src/modules/processing/upstage_client.py`
   - `_extract_text_from_html()` 메서드 추가
   - 응답 구조에 `html`, `full_html`, `markdown` 추가
   - download.php 처리 개선

2. `src/modules/processing/document_processor.py`
   - 로깅 시스템 통합
   - 성공/실패 추적

3. `src/modules/run_crawler.py`
   - 로깅 시스템 사용
   - 섹션별 로그 구조화

---

## 🔍 검증 방법

### 1. 로깅 시스템 테스트
```bash
docker exec -it knu-chatbot-app python /app/src/modules/run_crawler.py
```

**확인 사항**:
- `logs/crawl_YYYY-MM-DD_HH-MM-SS.txt` 파일 생성 확인
- 각 게시글별 성공/실패 로그 확인
- 최종 통계 요약 확인

### 2. 단일 URL 디버깅
```bash
docker exec -it knu-chatbot-app python /app/src/modules/debug_single_url.py \
  "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2" \
  --category notice
```

**확인 사항**:
- 9개 단계 모두 성공하는지 확인
- 이미지 OCR에서 텍스트 정상 추출 확인
- 첨부파일 다운로드 및 파싱 성공 확인
- `logs/debug/debug_TIMESTAMP/` 디렉토리에 10개 JSON 파일 생성 확인

### 3. 특정 이슈 검증

**OCR HTML 텍스트 추출**:
- 이미지 URL 디버깅
- `content.text`가 비어있어도 `content.html`의 alt 속성에서 추출되는지 확인

**download.php 처리**:
- 첨부파일이 있는 게시글 디버깅
- 파일명이 올바르게 추출되는지 확인
- PDF/HWP 등 다양한 파일 형식 테스트

**RAG 품질**:
- MongoDB `documents` 컬렉션 확인
- `html` 필드에 원본 HTML이 저장되는지 확인
- Pinecone 메타데이터에 구조 정보 포함 확인

---

## 🎉 성과

### 1. 추적성 향상
- 모든 처리 과정이 파일로 기록되어 사후 분석 가능
- 게시글별 성공/실패 이유 명확히 파악
- 멀티모달 처리 (OCR, 문서 파싱) 상세 로그

### 2. 디버깅 효율성
- 단일 URL로 전체 파이프라인 검증 가능
- 각 단계별 입력/출력 확인으로 문제 지점 즉시 파악
- JSON 형식으로 자동 분석 가능

### 3. RAG 품질 개선
- HTML 구조 정보 보존으로 LLM 응답 정확도 향상
- 표, 목록, 제목 등의 맥락 정보 활용 가능
- 검색과 생성을 분리하여 최적화

### 4. 안정성 향상
- download.php 같은 동적 URL 처리
- 리다이렉트 자동 추적
- 다양한 파일명 형식 지원 (국제화 포함)
- OCR 결과의 다양한 응답 형식 처리

---

## 🔄 Git 커밋 이력

```bash
8aa7074 fix: download.php 첨부파일 처리 개선
f68d0ad feat: RAG 품질 향상 - HTML 원본 및 전체 텍스트 저장
ae6e5eb fix: Upstage API 응답에서 HTML 텍스트 추출 개선
d7f803a fix: 이미지 분석 api request data에 ocr : auto 추가
4d22ab6 fix: 디버그 스크립트 크롤러 메서드명 수정
982827b feat: 단일 URL 크롤링 디버그 도구 추가
```

**브랜치 상태**: ✅ 모든 커밋 푸시 완료

---

## 📝 추가 권장 사항

### 1. 운영 환경 배포 전 테스트
```bash
# 전체 크롤링 테스트 (로그 확인)
docker exec -it knu-chatbot-app python /app/src/modules/run_crawler.py

# 문제가 있었던 URL들 개별 테스트
docker exec -it knu-chatbot-app python /app/src/modules/debug_single_url.py \
  "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2" \
  --category notice
```

### 2. 로그 파일 모니터링
- `logs/` 디렉토리 주기적 확인
- 실패 로그 패턴 분석
- 디스크 용량 관리 (오래된 로그 삭제)

### 3. RAG 성능 평가
- HTML 저장 전후 답변 품질 비교
- 표/목록 포함 질문으로 테스트
- 필요시 프롬프트에 HTML 활용 방법 추가

---

## ✅ 완료 체크리스트

- [x] 파일 기반 로깅 시스템 구현
- [x] 단일 URL 디버깅 도구 구현
- [x] OCR HTML 텍스트 추출 개선
- [x] RAG 품질 향상 (HTML 저장)
- [x] download.php 첨부파일 처리 개선
- [x] 디버그 로그 완전성 개선
- [x] 모든 변경사항 커밋 및 푸시
- [x] 구현 문서 작성

**최종 상태**: ✅ 모든 작업 완료

---

**작성 일시**: 2025-11-16
**작성자**: Claude (AI Assistant)
