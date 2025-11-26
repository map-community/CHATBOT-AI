# RAG 시스템 아키텍처 개선 제안

## 📋 현재 상태 분석

### ❌ 발견된 문제점

#### 1. **중복 코드**
- ✅ **해결됨**: `retrieval/keyword_filter.py` (빈 껍데기) 제거
- `preprocessing/keyword_filter.py`로 통합 완료

#### 2. **거대 파일 (God 클래스)**
| 파일 | 줄 수 | 상태 |
|-----|------|------|
| `multimodal_processor.py` | 1,063줄 | ⚠️ 분해 필요 |
| `upstage_client.py` | 1,062줄 | ⚠️ 분해 필요 |
| `ai_modules.py` | 873줄 | ⚠️ 추가 리팩토링 필요 |
| `debug_single_url.py` | 813줄 | ⚠️ scripts/로 이동 필요 |

#### 3. **폴더 구조가 RAG 파이프라인을 반영하지 못함**

**현재 구조 (기술 중심)**:
```
src/modules/
├─ preprocessing/    (전처리?)
├─ processing/       (처리?)  ← 무슨 차이인지 불명확!
├─ retrieval/        (검색)
└─ services/         (서비스)
```

**문제점**:
- `preprocessing`과 `processing`의 역할 구분이 모호
- RAG 파이프라인의 흐름이 보이지 않음
- 새 개발자가 코드를 이해하기 어려움

---

## ✅ RAG 시스템을 위한 올바른 폴더 구조

### **핵심 원칙**: RAG 파이프라인 기반 구조

RAG는 다음 단계로 구성됩니다:
1. **Ingestion** (수집): 데이터 크롤링, 파싱, 임베딩
2. **Retrieval** (검색): 관련 문서 검색
3. **Generation** (생성): LLM 답변 생성
4. **Evaluation** (평가): 품질 검증 (선택)

이 흐름을 폴더 구조에 반영해야 합니다.

---

## 📁 제안하는 폴더 구조

```
src/
├── app.py                        # Flask 앱 엔트리포인트
│
├── config/                       # ✅ 설정 (통합됨)
│   ├── __init__.py
│   ├── settings.py              # 환경 설정 (API keys, DB)
│   ├── ml_settings.py           # ML 하이퍼파라미터
│   └── prompts/                 # LLM 프롬프트 템플릿
│       └── __init__.py
│
├── core/                        # 🆕 핵심 RAG 파이프라인
│   ├── __init__.py
│   │
│   ├── orchestrator.py          # RAG 전체 오케스트레이션
│   │                            # (현재 ai_modules.py의 역할)
│   │
│   ├── ingestion/               # 1️⃣ 데이터 수집 및 처리
│   │   ├── __init__.py
│   │   ├── crawlers/           # 크롤러 (현 crawling/)
│   │   │   ├── base_crawler.py
│   │   │   ├── notice_crawler.py
│   │   │   ├── job_crawler.py
│   │   │   └── professor_crawler.py
│   │   │
│   │   ├── parsers/            # 파서 (현 processing/)
│   │   │   ├── html_parser.py
│   │   │   ├── pdf_parser.py
│   │   │   └── multimodal_parser.py
│   │   │
│   │   ├── chunkers.py         # 텍스트 분할 (현 document_processor.py)
│   │   └── embedders.py        # 임베딩 생성 (현 embedding_manager.py)
│   │
│   ├── retrieval/              # 2️⃣ 검색
│   │   ├── __init__.py
│   │   ├── retrievers/
│   │   │   ├── bm25_retriever.py
│   │   │   ├── dense_retriever.py
│   │   │   ├── hybrid_retriever.py  # BM25 + Dense 결합
│   │   │   └── reranker.py
│   │   │
│   │   └── filters/            # 검색 필터
│   │       ├── keyword_filter.py
│   │       ├── date_filter.py
│   │       └── score_adjuster.py  # 점수 조정 (scoring_service)
│   │
│   ├── generation/             # 3️⃣ 답변 생성
│   │   ├── __init__.py
│   │   ├── llm_client.py       # LLM API 호출
│   │   ├── prompt_builder.py   # 프롬프트 생성
│   │   └── response_formatter.py
│   │
│   └── evaluation/             # 4️⃣ 평가 (옵션)
│       ├── __init__.py
│       ├── metrics.py          # 성능 메트릭
│       └── validators.py       # 응답 검증
│
├── services/                    # 비즈니스 로직 레이어
│   ├── __init__.py
│   ├── document_service.py     # 문서 관리 (Pinecone/MongoDB CRUD)
│   ├── search_service.py       # 검색 오케스트레이션
│   ├── response_service.py     # 응답 생성 오케스트레이션
│   └── cache_service.py        # 캐싱 로직
│
├── infrastructure/              # 🆕 인프라 레이어
│   ├── __init__.py
│   ├── storage/                # 데이터 저장소
│   │   ├── __init__.py
│   │   ├── pinecone_client.py  # Pinecone 접근
│   │   ├── mongodb_client.py   # MongoDB 접근
│   │   └── redis_client.py     # Redis 캐싱
│   │
│   └── external_apis/          # 외부 API 클라이언트
│       ├── __init__.py
│       └── upstage_client.py   # Upstage API
│
├── models/                      # 🆕 데이터 모델 (도메인 객체)
│   ├── __init__.py
│   ├── document.py             # Document 클래스
│   ├── query.py                # Query 클래스
│   ├── chunk.py                # Chunk 클래스
│   └── response.py             # Response 클래스
│
├── utils/                       # 유틸리티 (순수 함수)
│   ├── __init__.py
│   ├── date_utils.py
│   ├── text_utils.py
│   ├── url_utils.py
│   └── retry_helper.py
│
├── constants.py                 # 전역 상수
│
└── scripts/                     # 🆕 운영 스크립트 (src/ 외부로 이동 권장)
    ├── run_crawler.py          # 크롤러 실행
    ├── reset_databases.py      # DB 초기화
    ├── force_reembed.py        # 재임베딩
    └── debug_single_url.py     # 디버깅
```

---

## 🎯 마이그레이션 계획

### **Phase 1: 즉시 실행 (긴급)**

| 작업 | 현재 위치 | 목표 위치 | 우선순위 |
|------|----------|-----------|---------|
| 중복 파일 제거 | `retrieval/keyword_filter.py` | 삭제 | ✅ **완료** |
| config 통합 | `modules/config.py` → | `config/crawler_settings.py` | 🔴 High |

### **Phase 2: 구조 개선 (1-2주)**

#### Step 1: `core/` 폴더 생성
```bash
mkdir -p src/core/{ingestion,retrieval,generation,evaluation}
mkdir -p src/core/ingestion/{crawlers,parsers}
mkdir -p src/core/retrieval/{retrievers,filters}
```

#### Step 2: 파일 이동 및 리팩토링

| 현재 파일 | 새 위치 | 작업 |
|----------|---------|------|
| `crawling/` | `core/ingestion/crawlers/` | 이동 |
| `processing/multimodal_processor.py` | `core/ingestion/parsers/multimodal_parser.py` | 분해 + 이동 |
| `processing/upstage_client.py` | `infrastructure/external_apis/upstage_client.py` | 이동 |
| `processing/embedding_manager.py` | `core/ingestion/embedders.py` | 이동 |
| `processing/document_processor.py` | `core/ingestion/chunkers.py` | 이동 |
| `retrieval/bm25_retriever.py` | `core/retrieval/retrievers/` | 이동 |
| `retrieval/dense_retriever.py` | `core/retrieval/retrievers/` | 이동 |
| `retrieval/reranker.py` | `core/retrieval/retrievers/` | 이동 |
| `preprocessing/keyword_filter.py` | `core/retrieval/filters/` | 이동 |
| `services/scoring_service.py` | `core/retrieval/filters/score_adjuster.py` | 이동 + 이름 변경 |

#### Step 3: `ai_modules.py` 분해
```python
# ai_modules.py (873줄) → 다음으로 분해:
core/orchestrator.py              # RAG 파이프라인 총괄 (200줄)
services/search_service.py        # 검색 오케스트레이션 (이미 존재)
services/response_service.py      # 응답 생성 (이미 존재)
```

### **Phase 3: 거대 파일 분해 (2-3주)**

#### `multimodal_processor.py` (1,063줄) 분해:
```python
core/ingestion/parsers/
├── html_parser.py          # HTML 파싱
├── pdf_parser.py           # PDF 파싱
├── image_processor.py      # 이미지 OCR
└── multimodal_orchestrator.py  # 멀티모달 처리 총괄
```

#### `upstage_client.py` (1,062줄) 분해:
```python
infrastructure/external_apis/upstage/
├── base_client.py          # 공통 HTTP 클라이언트
├── document_parser.py      # Document Parse API
├── ocr_client.py          # OCR API
└── layout_analyzer.py     # Layout Analysis API
```

---

## 📊 기대 효과

### 1. **명확한 책임 분리**
- 각 폴더가 RAG 단계를 명확히 반영
- 새 개발자가 코드 흐름을 쉽게 이해

### 2. **유지보수성 향상**
- 버그 발생 시 책임 영역이 명확
- 파일 크기 감소로 가독성 증가

### 3. **확장성 확보**
- 새 Retriever 추가 → `core/retrieval/retrievers/`에만 추가
- 새 파서 추가 → `core/ingestion/parsers/`에만 추가

### 4. **테스트 용이성**
- 각 모듈이 독립적으로 테스트 가능
- Mock 객체 주입이 쉬워짐

---

## 🏗️ 구현 가이드라인

### **Clean Architecture 원칙**

```
┌─────────────────────────────────────┐
│         core/ (도메인 로직)         │  ← 가장 안정적 (변경 적음)
│   RAG 파이프라인의 핵심 알고리즘    │
└─────────────────────────────────────┘
              ↑
┌─────────────────────────────────────┐
│      services/ (비즈니스 로직)      │  ← 중간 계층
│     오케스트레이션 및 워크플로우     │
└─────────────────────────────────────┘
              ↑
┌─────────────────────────────────────┐
│   infrastructure/ (외부 의존성)     │  ← 가장 불안정 (변경 많음)
│    DB, API 등 외부 시스템 연동      │
└─────────────────────────────────────┘
```

**의존성 규칙**:
- `core/`는 어디에도 의존하지 않음 (순수 도메인 로직)
- `services/`는 `core/`에만 의존
- `infrastructure/`는 `services/`, `core/` 모두 의존 가능
- `app.py`는 모든 계층을 조합

### **RAG 특화 권장사항**

#### 1. **벡터 DB 추상화**
```python
# infrastructure/storage/vector_store.py
class VectorStore(ABC):
    @abstractmethod
    def search(self, query_vector, top_k):
        pass

# infrastructure/storage/pinecone_client.py
class PineconeVectorStore(VectorStore):
    def search(self, query_vector, top_k):
        # Pinecone 구현
```

**장점**: Pinecone → Weaviate/Milvus 교체 시 core/ 수정 불필요

#### 2. **LLM Provider 추상화**
```python
# core/generation/llm_client.py
class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass

# infrastructure/external_apis/upstage_llm.py
class UpstageLLM(LLMClient):
    def generate(self, prompt: str) -> str:
        # Upstage API 호출
```

**장점**: Upstage → OpenAI/Anthropic 교체 시 core/ 수정 불필요

#### 3. **실험 추적 (MLOps)**
```python
# core/evaluation/metrics.py
class RAGMetrics:
    def calculate_mrr(self, results):
        """Mean Reciprocal Rank 계산"""
        pass

    def calculate_ndcg(self, results):
        """NDCG 계산"""
        pass

# scripts/evaluate_rag.py
if __name__ == "__main__":
    metrics = RAGMetrics()
    # A/B 테스트: BM25 vs Dense vs Hybrid
```

**장점**: 검색 알고리즘 성능 비교 가능

---

## 🚀 시작하기

### **최소 변경으로 즉시 적용 가능한 개선**

1. ✅ **중복 파일 제거** (완료)
2. **config 통합**: `modules/config.py` → `config/crawler_settings.py`
3. **scripts 이동**: `modules/*.py` → `scripts/*.py` (실행 스크립트)
4. **거대 파일 경고**: 1,000줄 넘는 파일은 PR 시 강제 리뷰

### **점진적 마이그레이션**

- 한 번에 모든 파일을 이동하지 말 것
- 기능별로 하나씩 이동 + 테스트
- 하위 호환성 유지 (wrapper 함수)

---

## 📚 참고 자료

### **RAG 시스템 설계 모범 사례**
- [LangChain Architecture](https://python.langchain.com/docs/concepts/architecture/)
- [LlamaIndex Best Practices](https://docs.llamaindex.ai/en/stable/understanding/putting_it_all_together/apps/)
- [Pinecone RAG Guide](https://www.pinecone.io/learn/retrieval-augmented-generation/)

### **Clean Architecture**
- Robert C. Martin의 "Clean Architecture"
- [Python Clean Architecture Example](https://github.com/cosmic-python/book)

---

## ✅ 다음 단계

이 문서를 팀과 공유하고 다음을 논의하세요:
1. Phase 1 (긴급) 작업 즉시 착수
2. Phase 2, 3의 우선순위 조정
3. 마이그레이션 일정 수립
4. 테스트 전략 수립

**질문이 있으면 언제든지 물어보세요!** 🚀
