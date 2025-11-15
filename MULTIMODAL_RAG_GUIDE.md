# 멀티모달 RAG 시스템 가이드

## 개요

기존 텍스트 전용 RAG 시스템을 **멀티모달 RAG**로 업그레이드했습니다.
- ✅ 텍스트 콘텐츠
- ✅ 이미지 OCR (Upstage OCR API)
- ✅ 첨부파일 파싱 (Upstage Document Parse API)

## 주요 개선사항

### 1. 향상된 Pinecone 메타데이터 구조

#### 기존 구조 (제한적)
```python
{
    "title": "제목",
    "url": "...",
    "date": "작성일25-10-17",
    "text": "내용"
}
```

#### 새로운 구조 (RAG 최적화)
```python
{
    # 기본 정보
    "title": "2025학년도 컴퓨터학부 발전기금...",
    "url": "https://cse.knu.ac.kr/bbs/...",
    "date": "2025-10-17T15:48:00+09:00",  # ISO 8601 형식 (한국 시간대)
    "text": "실제 텍스트 내용",

    # 분류 정보
    "category": "notice",  # notice, job, seminar, professor
    "content_type": "text",  # text, image, attachment
    "source": "original_post",  # original_post, image_ocr, document_parse

    # 위치 정보 (텍스트인 경우)
    "chunk_index": 0,
    "total_chunks": 5,

    # 이미지인 경우
    "image_url": "https://...",
    "image_index": 0,

    # 첨부파일인 경우
    "attachment_url": "https://...",
    "attachment_type": "pdf",
    "attachment_index": 0
}
```

### 2. MongoDB 구조

#### 컬렉션 목적

1. **notice_data**: 문서 중복 체크용 메타데이터
   ```python
   {
       "title": "제목",
       "image_url": "첫 번째 이미지 URL"
   }
   ```

2. **multimodal_cache**: Upstage API 처리 결과 캐시
   ```python
   {
       "url": "https://cse.knu.ac.kr/file.pdf",
       "type": "pdf",
       "text": "파싱된 텍스트...",
       # 또는
       "url": "https://cse.knu.ac.kr/image.jpg",
       "ocr_text": "추출된 텍스트...",
       "description": ""
   }
   ```

3. **crawl_state**: 증분 크롤링 상태 관리
   ```python
   {
       "board_type": "notice",
       "last_processed_id": 28833,
       "last_update": "2025-10-17",
       "processed_count": 150
   }
   ```

### 3. RAG 검색 쿼리 예시

#### 카테고리 필터링
```python
# 공지사항만 검색
filter = {"category": "notice"}

# 채용정보만 검색
filter = {"category": "job"}
```

#### 콘텐츠 타입 필터링
```python
# 텍스트만 검색
filter = {"content_type": "text"}

# 이미지 OCR 결과만 검색
filter = {"content_type": "image"}

# 첨부파일만 검색
filter = {"content_type": "attachment"}
```

#### 복합 필터링
```python
# 공지사항의 PDF 첨부파일만 검색
filter = {
    "category": "notice",
    "content_type": "attachment",
    "attachment_type": "pdf"
}
```

## 데이터베이스 초기화 및 재구축

### 1. 기존 데이터 삭제

```bash
cd /home/user/CHATBOT-AI/src/modules
python reset_databases.py
```

**경고**: 모든 데이터가 삭제됩니다!
- MongoDB: 문서 메타데이터, 크롤링 상태, 멀티모달 캐시
- Pinecone: 모든 벡터 임베딩

### 2. 멀티모달 RAG 데이터 구축

```bash
cd /home/user/CHATBOT-AI/src/modules
python run_crawler.py
```

처리 과정:
1. 공지사항, 채용정보, 세미나, 교수 정보 크롤링
2. 텍스트 분할 (850자 단위, 100자 겹침)
3. 이미지 OCR 처리 (Upstage API)
4. 첨부파일 파싱 (Upstage API)
5. 임베딩 생성 (Upstage Embedding API)
6. Pinecone 저장 (메타데이터 포함)

## 처리 흐름

```
게시글 크롤링 (HTML 파싱)
  ↓
┌─────────────────────────────────┐
│ 1. 텍스트                         │
│    - CharacterTextSplitter       │
│    - 850자 청크, 100자 겹침      │
│    - category: notice            │
│    - content_type: text          │
│    - source: original_post       │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│ 2. 이미지                         │
│    - Upstage OCR API             │
│    - MongoDB 캐시 확인           │
│    - category: notice            │
│    - content_type: image         │
│    - source: image_ocr           │
│    - image_url 저장              │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│ 3. 첨부파일 (PDF, HWP, etc)       │
│    - Upstage Document Parse API  │
│    - MongoDB 캐시 확인           │
│    - category: notice            │
│    - content_type: attachment    │
│    - source: document_parse      │
│    - attachment_url, type 저장   │
└─────────────────────────────────┘
  ↓
Upstage Embedding API
  ↓
Pinecone 벡터 DB 저장
```

## 검색 품질 향상 포인트

### 1. 컨텍스트 추적
- `chunk_index`와 `total_chunks`로 전체 문서 내 위치 파악
- 연속된 청크를 찾아 더 긴 문맥 제공 가능

### 2. 출처 명확화
- `source` 필드로 원본/OCR/파싱 구분
- 사용자에게 정보 출처를 명확히 표시

### 3. 필터링 활용
- 특정 카테고리만 검색 (예: 장학금 관련 공지만)
- 특정 파일 타입만 검색 (예: PDF 첨부파일만)

### 4. 멀티모달 결과 통합
- 같은 게시글의 텍스트 + 이미지 OCR + 첨부파일을 함께 제공
- `title`과 `url`로 그룹핑 가능

## 주요 개선 파일

1. **processing/multimodal_processor.py**
   - `to_embedding_items()`: 메타데이터 풍부화

2. **processing/document_processor.py**
   - `process_documents_multimodal()`: 카테고리 추가

3. **run_crawler.py**
   - 각 크롤러에 카테고리 명시

4. **reset_databases.py** (신규)
   - MongoDB, Pinecone 초기화 스크립트

## 다음 단계

1. **데이터베이스 초기화**: `python reset_databases.py`
2. **멀티모달 데이터 구축**: `python run_crawler.py`
3. **RAG 시스템 연동**: 검색 시 메타데이터 활용

## 날짜 형식 개선 (ISO 8601)

### 이전 형식의 문제점

```python
# 기존 날짜 형식
"date": "작성일25-10-17 15:48"
```

**문제점**:
- ❌ 한국어 접두사 "작성일" 포함
- ❌ 2자리 연도 (25 = 2025? 1925?)
- ❌ 표준 형식 아님 (ISO 8601 미준수)
- ❌ 타임존 정보 없음
- ❌ Pinecone에서 날짜 범위 필터링 불가
- ❌ 매 쿼리마다 파싱 오버헤드 발생

### 새로운 형식 (ISO 8601)

```python
# 개선된 날짜 형식
"date": "2025-10-17T15:48:00+09:00"
```

**개선 효과**:
- ✅ 국제 표준 ISO 8601 준수
- ✅ 4자리 연도로 명확성 확보
- ✅ 타임존 정보 포함 (+09:00 = 한국 시간)
- ✅ Pinecone 메타데이터 필터링 가능
- ✅ 파싱 오버헤드 감소
- ✅ 다양한 라이브러리와 호환

### 활용 예시

#### Pinecone 날짜 범위 검색
```python
from datetime import datetime, timedelta

# 최근 7일간 공지사항 검색
now = datetime.now()
week_ago = now - timedelta(days=7)

filter = {
    "category": "notice",
    "date": {"$gte": week_ago.isoformat()}
}

results = index.query(
    vector=embedding,
    filter=filter,
    top_k=10
)
```

#### 날짜 기반 정렬
```python
# ISO 8601 형식은 문자열 정렬만으로도 시간순 정렬 가능
dates = [
    "2025-01-15T10:00:00+09:00",
    "2025-10-17T15:48:00+09:00",
    "2024-12-31T23:59:59+09:00"
]
dates.sort()  # 자동으로 시간순 정렬
```

### 유틸리티 함수

새로운 날짜 유틸리티 모듈 제공:

```python
from utils import korean_to_iso8601, calculate_days_diff

# 한국어 날짜 -> ISO 8601 변환
iso_date = korean_to_iso8601("작성일25-10-17 15:48")
# => "2025-10-17T15:48:00+09:00"

# 날짜 차이 계산
days = calculate_days_diff("2025-10-17T15:48:00+09:00")
# => 현재로부터 며칠 전/후인지 계산
```

### 하위 호환성

기존 코드와의 호환성을 위해 `ai_modules.py`의 `parse_date_change_korea_time()` 함수가 두 형식 모두 지원:

```python
from ai_modules import parse_date_change_korea_time

# ISO 8601 형식 파싱
dt1 = parse_date_change_korea_time("2025-10-17T15:48:00+09:00")

# 레거시 한국어 형식 파싱 (하위 호환)
dt2 = parse_date_change_korea_time("작성일25-10-17 15:48")

# 둘 다 동일한 datetime 객체 반환
```

---

**작성일**: 2025-01-15
**최종 수정**: 2025-01-15
**버전**: 1.1 (멀티모달 RAG + ISO 8601 날짜 형식)
