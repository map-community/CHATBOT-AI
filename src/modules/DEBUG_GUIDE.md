# 🔍 단일 URL 크롤링 디버그 가이드

## 개요

특정 URL의 크롤링 전 과정을 **상세하게 추적**하고 **각 단계별 결과를 파일로 저장**하는 디버그 도구입니다.

## 주요 기능

### ✅ 단계별 추적
1. **크롤러 선택** - 카테고리별 크롤러 초기화
2. **HTML 다운로드** - requests로 페이지 다운로드
3. **HTML 파싱** - BeautifulSoup으로 데이터 추출
4. **텍스트 청크 분할** - 긴 텍스트를 chunk 단위로 분할
5. **멀티모달 프로세서 초기화** - OCR 및 문서 파싱 준비
6. **이미지 OCR 처리** - 각 이미지에서 텍스트 추출
7. **첨부파일 파싱** - PDF, HWP 등 문서에서 텍스트 추출
8. **멀티모달 콘텐츠 생성** - 모든 결과 통합
9. **임베딩 아이템 생성** - Pinecone 업로드용 최종 데이터

### ✅ 상세 로깅
- 각 함수 호출 시 **모듈명, 함수명, 인자** 기록
- 입력 데이터와 출력 데이터의 **타입, 길이, 내용** 기록
- 에러 발생 시 **타입, 메시지, 스택 트레이스** 전체 기록

### ✅ 파일 출력
- `debug.log` - 전체 처리 과정 로그 (콘솔 + 파일)
- `01_raw_html.html` - 원본 HTML
- `02_크롤러_선택.json` - 크롤러 정보
- `03_html_파싱.json` - 파싱된 데이터
- `04_텍스트_청크_분할.json` - 분할된 텍스트 청크
- `06_이미지_ocr_처리.json` - OCR 결과
- `07_첨부파일_파싱.json` - 문서 파싱 결과
- `09_임베딩_아이템_생성.json` - 최종 임베딩 아이템
- `summary.json` - 전체 요약

## 사용 방법

### 기본 사용법

```bash
# Docker 환경에서 실행
docker exec -it knu-chatbot-app python /app/src/modules/debug_single_url.py \
  "<URL>" \
  --category <카테고리>
```

### 예시 1: 공지사항 디버그

```bash
docker exec -it knu-chatbot-app python /app/src/modules/debug_single_url.py \
  "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2" \
  --category notice
```

### 예시 2: 채용정보 디버그

```bash
docker exec -it knu-chatbot-app python /app/src/modules/debug_single_url.py \
  "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_2&wr_id=1234" \
  --category job
```

### 예시 3: 세미나 디버그

```bash
docker exec -it knu-chatbot-app python /app/src/modules/debug_single_url.py \
  "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_3&wr_id=5678" \
  --category seminar
```

## 출력 구조

```
logs/debug/debug_2025-11-16_14-30-00/
├── debug.log                        # 전체 로그 (가장 중요!)
├── 01_raw_html.html                 # 원본 HTML
├── 02_html_파싱.json                # 파싱 결과
├── 03_텍스트_청크_분할.json         # 텍스트 청크
├── 06_이미지_ocr_처리.json          # OCR 결과
├── 07_첨부파일_파싱.json            # 문서 파싱
├── 09_임베딩_아이템_생성.json       # 최종 아이템
└── summary.json                     # 요약
```

## 로그 예시

### 콘솔 출력

```
================================================================================
🔍 디버그 세션 시작
URL: https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2
카테고리: notice
출력 디렉토리: logs/debug/debug_2025-11-16_14-30-00
================================================================================

================================================================================
STEP 01: 크롤러 선택
설명: 카테고리에 맞는 크롤러 초기화
================================================================================

📥 입력 데이터: 카테고리
  타입: str
  길이: 6 문자
  내용: notice

🔧 함수 호출
  모듈: crawling.notice_crawler
  함수: NoticeCrawler.__init__

📤 출력 데이터: 초기화된 크롤러
  타입: str
  내용: NoticeCrawler

✅ 성공: 크롤러 선택

================================================================================
STEP 02: HTML 다운로드
설명: URL에서 HTML 페이지 다운로드
================================================================================

📥 입력 데이터: URL
  타입: str
  길이: 84 문자
  내용: https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2

🔧 함수 호출
  모듈: requests
  함수: get
  인자:
    url: https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2

📤 출력 데이터: 다운로드된 HTML
  타입: str
  길이: 45678 문자
  내용 (처음 200자): <!DOCTYPE html><html lang="ko"><head>...

💾 원본 HTML 저장: 01_raw_html.html

✅ 성공: HTML 다운로드

================================================================================
STEP 03: HTML 파싱
설명: BeautifulSoup으로 HTML 파싱 및 데이터 추출
================================================================================

📥 입력 데이터: HTML 내용 (일부)
  타입: str
  길이: 500 문자
  내용 (처음 200자): <!DOCTYPE html><html lang="ko"><head>...

🔧 함수 호출
  모듈: crawling.base_crawler
  함수: crawl_page
  인자:
    url: https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2

📤 출력 데이터: 파싱 결과
  타입: dict
  키: ['title', 'text', 'text_length', 'image_list', 'image_count', 'attachment_list', 'attachment_count', 'date', 'url']
  title: 2025학년도 2학기 장학금 운영 계획
  text: [게시글 본문 텍스트...]
  text_length: 1234
  image_list: [2개 항목]
  image_count: 2
  attachment_list: [1개 항목]
  attachment_count: 1
  date: 2025-10-17T15:48:00+09:00
  url: https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2

💾 출력 파일 저장: 03_html_파싱.json

✅ 성공: HTML 파싱

...

================================================================================
STEP 06: 이미지 OCR 처리
설명: 2개 이미지에서 텍스트 추출
================================================================================

📥 입력 데이터: 이미지 URL 리스트
  타입: list
  개수: 2개
  [0]: https://cse.knu.ac.kr/data/editor/2404/abc_123.jpg
  [1]: https://cse.knu.ac.kr/data/editor/2404/def_456.png

🔧 함수 호출
  모듈: processing.multimodal_processor
  함수: process_images
  인자:
    image_urls: ['https://cse.knu.ac.kr/data/editor/2404/abc_123.jpg', ...]

  🖼️  이미지 1/2: https://cse.knu.ac.kr/data/editor/2404/abc_123.jpg
     ✅ OCR 성공: 567자 추출

  🖼️  이미지 2/2: https://cse.knu.ac.kr/data/editor/2404/def_456.png
     ✅ OCR 성공: 234자 추출

📤 출력 데이터: OCR 처리 결과
  타입: dict
  키: ['total_images', 'successful', 'failed', 'results']
  total_images: 2
  successful: 2
  failed: 0
  results: [2개 항목]

💾 출력 파일 저장: 06_이미지_ocr_처리.json

✅ 성공: 이미지 OCR 처리

...

================================================================================
📊 최종 요약
================================================================================
전체 단계: 9개
성공: 9개
실패: 0개

💾 요약 파일: logs/debug/debug_2025-11-16_14-30-00/summary.json
📁 모든 결과: logs/debug/debug_2025-11-16_14-30-00
================================================================================
```

## JSON 파일 예시

### `03_html_파싱.json`

```json
{
  "title": "2025학년도 2학기 장학금 운영 계획",
  "text": "장학금 신청 안내...",
  "text_length": 1234,
  "image_list": [
    "https://cse.knu.ac.kr/data/editor/2404/abc_123.jpg",
    "https://cse.knu.ac.kr/data/editor/2404/def_456.png"
  ],
  "image_count": 2,
  "attachment_list": [
    "https://cse.knu.ac.kr/bbs/download.php?bo_table=sub5_1&wr_id=28848&no=0"
  ],
  "attachment_count": 1,
  "date": "2025-10-17T15:48:00+09:00",
  "url": "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28848&page=2"
}
```

### `06_이미지_ocr_처리.json`

```json
{
  "total_images": 2,
  "successful": 2,
  "failed": 0,
  "results": [
    {
      "url": "https://cse.knu.ac.kr/data/editor/2404/abc_123.jpg",
      "success": true,
      "text_length": 567,
      "text_preview": "장학금 신청 일정\n2025년 10월 1일 ~ 10월 31일..."
    },
    {
      "url": "https://cse.knu.ac.kr/data/editor/2404/def_456.png",
      "success": true,
      "text_length": 234,
      "text_preview": "제출 서류\n1. 신청서\n2. 성적증명서..."
    }
  ]
}
```

### `09_임베딩_아이템_생성.json`

```json
{
  "total_items": 8,
  "items": [
    {
      "index": 0,
      "content_type": "text",
      "source": "original_post",
      "text_length": 850,
      "text_preview": "장학금 신청 안내...",
      "metadata": {
        "title": "2025학년도 2학기 장학금 운영 계획",
        "url": "https://...",
        "date": "2025-10-17T15:48:00+09:00",
        "content_type": "text",
        "chunk_index": 0,
        "total_chunks": 2,
        "source": "original_post",
        "category": "notice"
      }
    },
    {
      "index": 1,
      "content_type": "text",
      "source": "original_post",
      "text_length": 384,
      "text_preview": "문의사항은...",
      "metadata": {
        "title": "2025학년도 2학기 장학금 운영 계획",
        "url": "https://...",
        "date": "2025-10-17T15:48:00+09:00",
        "content_type": "text",
        "chunk_index": 1,
        "total_chunks": 2,
        "source": "original_post",
        "category": "notice"
      }
    },
    {
      "index": 2,
      "content_type": "image",
      "source": "image_ocr",
      "text_length": 580,
      "text_preview": "[이미지 텍스트]\n장학금 신청 일정...",
      "metadata": {
        "title": "2025학년도 2학기 장학금 운영 계획",
        "url": "https://...",
        "date": "2025-10-17T15:48:00+09:00",
        "content_type": "image",
        "image_url": "https://cse.knu.ac.kr/data/editor/2404/abc_123.jpg",
        "image_index": 0,
        "source": "image_ocr",
        "category": "notice"
      }
    },
    {
      "index": 3,
      "content_type": "attachment",
      "source": "document_parse",
      "text_length": 2345,
      "text_preview": "[첨부파일: HWP]\n2025학년도 2학기 장학금 운영 계획...",
      "metadata": {
        "title": "2025학년도 2학기 장학금 운영 계획",
        "url": "https://...",
        "date": "2025-10-17T15:48:00+09:00",
        "content_type": "attachment",
        "attachment_url": "https://cse.knu.ac.kr/bbs/download.php?...",
        "attachment_type": "hwp",
        "attachment_index": 0,
        "source": "document_parse",
        "category": "notice"
      }
    }
  ]
}
```

## 에러 디버깅

### 에러 발생 시 로그

```
================================================================================
STEP 06: 이미지 OCR 처리
설명: 1개 이미지에서 텍스트 추출
================================================================================

  🖼️  이미지 1/1: https://cse.knu.ac.kr/data/editor/2404/broken.jpg
     ❌ OCR 에러: HTTPError: 404 Client Error: Not Found

❌ 에러 발생
  타입: HTTPError
  메시지: 404 Client Error: Not Found for url: https://...

스택 트레이스:
Traceback (most recent call last):
  File "/app/src/modules/debug_single_url.py", line 450, in debug_url
    ocr_result = upstage_client.extract_text_from_image_url(img_url)
  File "/app/src/modules/processing/upstage_client.py", line 123, in extract_text_from_image_url
    response.raise_for_status()
  File "/usr/local/lib/python3.11/site-packages/requests/models.py", line 1021, in raise_for_status
    raise HTTPError(http_error_msg, response=self)
requests.exceptions.HTTPError: 404 Client Error: Not Found for url: https://...

❌ 실패: 이미지 OCR 처리
```

## 활용 방법

### 1. 크롤링 문제 진단
- 어떤 단계에서 실패하는지 정확히 파악
- 에러 메시지와 스택 트레이스로 원인 분석

### 2. 데이터 검증
- 각 단계의 출력 데이터 확인
- 예상한 값과 실제 값 비교

### 3. 성능 분석
- 각 단계별 소요 시간 확인 (로그의 타임스탬프 참조)
- 병목 구간 식별

### 4. 새 크롤러 개발
- 다른 웹사이트 크롤링 시 참고
- 필요한 데이터 구조 파악

## 주의사항

1. **API 크레딧**: OCR 및 Document Parse는 Upstage API를 호출하므로 크레딧이 소모됩니다.
2. **처리 시간**: 이미지/첨부파일이 많으면 시간이 오래 걸릴 수 있습니다.
3. **MongoDB 연결**: 캐시 조회를 위해 MongoDB 연결이 필요합니다.

## 문제 해결

### Docker 컨테이너가 실행 중이 아닌 경우

```bash
docker ps -a
docker start knu-chatbot-app
```

### 권한 오류

```bash
chmod +x src/modules/debug_single_url.py
```

### 로그 디렉토리 권한

```bash
mkdir -p src/modules/logs/debug
chmod 777 src/modules/logs/debug
```

## 확장

필요에 따라 다음 기능을 추가할 수 있습니다:

1. **교수 정보 크롤링 지원**: `--category professor` 옵션 추가
2. **비교 모드**: 두 URL의 결과 비교
3. **성능 측정**: 각 단계별 소요 시간 측정
4. **시각화**: 처리 흐름을 그래프로 표시

## 라이센스

이 도구는 프로젝트의 일부로 동일한 라이센스를 따릅니다.
