# HTML → Markdown Migration 가이드

기존 MongoDB의 HTML 데이터를 Markdown으로 변환하여 저장하는 가이드입니다.

## 개요

- **목적**: 기존 11,111개 문서의 HTML을 Markdown으로 변환하여 RAG 품질 및 성능 개선
- **방법**: `html2text` 라이브러리를 사용한 자동 변환
- **장점**: Upstage API 재호출 불필요 (비용 절감), 즉시 전체 문서에 적용

## 실행 순서

### 1. html2text 라이브러리 설치

Docker 컨테이너에 html2text를 추가해야 합니다:

```bash
# requirements.txt에 이미 추가됨
# Docker 이미지 재빌드 또는 컨테이너 내부에서 설치

# 방법 1: Docker 이미지 재빌드 (권장)
docker-compose down
docker-compose build
docker-compose up -d

# 방법 2: 실행 중인 컨테이너에 직접 설치
docker exec chatbot-app pip install html2text==2020.1.16
```

### 2. Migration 스크립트 실행

Docker 컨테이너 내부에서 실행:

```bash
# Docker 컨테이너 접속
docker exec -it chatbot-app bash

# Migration 스크립트 실행
cd /app
python3 migrate_html_to_markdown.py
```

**예상 소요 시간**: 약 5-10분 (11,111개 문서 기준)

**진행 상황**: 1000개마다 진행 상황이 출력됩니다.

### 3. Redis BM25 캐시 삭제

Markdown으로 변환된 데이터로 BM25 인덱스를 재생성하기 위해 기존 캐시를 삭제합니다:

```bash
# Docker 컨테이너 내부에서 실행
python3 clear_bm25_cache.py
```

### 4. Docker 컨테이너 재시작

새로운 Markdown 데이터를 로드하고 BM25 인덱스를 재생성합니다:

```bash
# 컨테이너 재시작
docker-compose restart chatbot-app

# 또는 전체 재시작
docker-compose down
docker-compose up -d
```

### 5. 검증

챗봇에 질문하여 정상 작동 확인:

```bash
# 로그 확인
docker logs -f chatbot-app

# BM25 인덱스 생성 로그 확인
# "✅ BM25 인덱스 생성 완료" 메시지 확인
```

## Migration 스크립트 동작 방식

### migrate_html_to_markdown.py

1. MongoDB `multimodal_cache` 컬렉션의 모든 문서 조회
2. `html` 또는 `ocr_html` 필드가 있는 문서 필터링
3. 이미 `markdown` 또는 `ocr_markdown` 필드가 있으면 **건너뜀** (Upstage API 원본 보존)
4. `html2text` 라이브러리로 HTML → Markdown 변환
5. 변환 결과를 `markdown` 또는 `ocr_markdown` 필드에 저장
6. 1000개 배치 단위로 bulk write 실행

**주요 설정**:
- `body_width = 0`: 줄바꿈 제한 없음 (표 깨짐 방지)
- `ignore_links = False`: 링크 보존
- `ignore_images = False`: 이미지 보존

### clear_bm25_cache.py

1. Redis에 연결
2. `bm25_cache_v2` 키 조회
3. 존재하면 삭제
4. 삭제 확인

## 예상 결과

### Migration 전:
```
📊 전체 문서 수: 11,111개
📊 HTML 필드가 있는 문서 수: 8,500개
📊 이미 Markdown이 있는 문서 수: 0개 (건너뜀)
🎯 변환 대상 문서 수: 8,500개
```

### Migration 후:
```
✅ Migration 완료!
📊 처리된 문서 수: 8,500개
✅ 변환 성공: 8,500개 필드
⏭️  건너뜀: 0개
❌ 오류: 0개

📊 변환 후 Markdown 필드가 있는 문서 수: 8,500개
📈 증가: 8,500개
```

## 성능 개선 효과

1. **토큰 효율성**: Markdown이 HTML보다 30-50% 적은 토큰
2. **LLM 이해도**: 표 구조가 명확히 보존되어 더 정확한 답변
3. **BM25 검색**: Markdown 표 구조가 보존되어 검색 정확도 향상
4. **응답 속도**: HTML→Markdown 변환 비용 절감

## 롤백 방법

문제가 발생하면 `markdown` 및 `ocr_markdown` 필드를 삭제하여 HTML로 되돌릴 수 있습니다:

```javascript
// MongoDB shell에서 실행
use chatbot;

// markdown 필드 삭제
db.multimodal_cache.updateMany(
  {},
  { $unset: { markdown: "", ocr_markdown: "" } }
);
```

그 후 Redis 캐시를 삭제하고 Docker를 재시작합니다.

## 주의사항

1. **Upstage API 원본 Markdown 보존**: 이미 `markdown` 필드가 있는 문서는 변환하지 않습니다 (Upstage 원본이 더 고품질)
2. **배치 처리**: 1000개씩 처리하므로 중단되어도 일부는 변환된 상태
3. **Idempotent**: 여러 번 실행해도 안전 (이미 변환된 문서는 건너뜀)
4. **BM25 캐시 삭제 필수**: 캐시를 삭제하지 않으면 새 Markdown이 반영되지 않음

## 향후 크롤링

- 앞으로 크롤링되는 문서는 Upstage API의 고품질 Markdown이 자동 저장됨
- `multimodal_processor.py`에서 `markdown` 필드를 MongoDB에 저장
- Migration 불필요

## 문제 해결

### "ModuleNotFoundError: No module named 'html2text'"
→ Docker 이미지 재빌드 또는 `pip install html2text==2020.1.16` 실행

### "Redis connection failed"
→ Redis 컨테이너가 실행 중인지 확인: `docker ps | grep redis`

### "MongoDB connection failed"
→ MongoDB 컨테이너가 실행 중인지 확인: `docker ps | grep mongo`

### BM25 인덱스 생성이 너무 오래 걸림
→ 정상입니다. 첫 실행 시 3-5분 소요 (병렬 HTML 파싱)

## 관련 파일

- `migrate_html_to_markdown.py`: HTML → Markdown 변환 스크립트
- `clear_bm25_cache.py`: Redis BM25 캐시 삭제 스크립트
- `requirements.txt`: html2text 라이브러리 추가
- `src/modules/processing/multimodal_processor.py`: Upstage API markdown 저장 로직
- `src/modules/ai_modules.py`: Markdown 우선 검색 로직
- `src/modules/retrieval/bm25_retriever.py`: Markdown 형식 감지 및 보존
