# Reranker 추상화 마이그레이션 가이드

## 📝 변경 사항

### **구조 변경**

```
Before (하나의 파일):
src/modules/retrieval/
└── reranker.py (161줄)

After (Plugin Architecture):
src/modules/retrieval/
├── reranker.py (42줄, wrapper)
└── rerankers/
    ├── __init__.py
    ├── base.py (BaseReranker 인터페이스)
    └── bge_reranker.py (BGE 구현)

src/factories/
├── __init__.py
└── reranker_factory.py (Factory Pattern)

config/
└── plugins.yaml (플러그인 설정)
```

---

## ✅ 하위 호환성

### **기존 코드 그대로 작동**

```python
# 기존 코드 (변경 불필요)
from modules.retrieval.reranker import DocumentReranker

reranker = DocumentReranker()
reranked_docs = reranker.rerank(query, documents, top_k=5)
```

**동작**: `DocumentReranker`는 이제 `BGEReranker`의 별칭입니다.

---

## 🚀 새로운 사용법

### **방법 1: BGEReranker 직접 사용**

```python
from modules.retrieval.rerankers.bge_reranker import BGEReranker

# BGE Reranker 생성
reranker = BGEReranker(
    model_name="BAAI/bge-reranker-v2-m3",
    use_fp16=True,
    device="cpu"
)

# 사용
reranked_docs = reranker.rerank(
    query="최근 공지사항",
    documents=candidate_docs,
    top_k=5
)
```

### **방법 2: Factory Pattern 사용 (권장)**

```python
from factories.reranker_factory import RerankerFactory

# BGE Reranker 생성
reranker = RerankerFactory.create("bge")

# Config 기반 생성
reranker = RerankerFactory.create(
    "bge",
    model_name="BAAI/bge-reranker-v2-m3",
    use_fp16=True
)

# 사용
reranked_docs = reranker.rerank(query, documents, top_k=5)
```

### **방법 3: Config 파일 사용 (가장 권장)**

```python
from factories.reranker_factory import RerankerFactory
from config.ml_settings import get_reranker_config

# Config에서 Reranker 설정 로드
config = get_reranker_config()
reranker = RerankerFactory.create(
    config["type"],
    **config["config"]
)

# 사용
reranked_docs = reranker.rerank(query, documents, top_k=5)
```

**Config 변경** (`config/plugins.yaml`):
```yaml
reranker:
  type: "bge"
  config:
    model_name: "BAAI/bge-reranker-v2-m3"
    use_fp16: true
    device: "cpu"
```

---

## 🔧 Reranker 교체

### **BGE → FlashRank 교체 (속도 우선)**

**1단계**: FlashRank 구현 추가 (향후)
```python
# src/modules/retrieval/rerankers/flashrank_reranker.py
from .base import BaseReranker

class FlashRankReranker(BaseReranker):
    def __init__(self, model_name="ms-marco-MultiBERT-L-12"):
        from flashrank import Ranker
        self.ranker = Ranker(model_name=model_name)

    def rerank(self, query, documents, top_k=5):
        # FlashRank 로직
        ...
```

**2단계**: Factory에 등록
```python
# src/factories/reranker_factory.py
from modules.retrieval.rerankers.flashrank_reranker import FlashRankReranker
RerankerFactory.register("flashrank", FlashRankReranker)
```

**3단계**: Config만 변경
```yaml
reranker:
  type: "flashrank"  # "bge" → "flashrank"
  config:
    model_name: "ms-marco-MultiBERT-L-12"
```

**코드 수정 불필요!** 🎉

---

## 📊 BaseReranker 인터페이스

모든 Reranker는 다음 메서드를 구현해야 합니다:

```python
from abc import ABC, abstractmethod
from typing import List, Tuple

class BaseReranker(ABC):
    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[Tuple],
        top_k: int = 5
    ) -> List[Tuple]:
        """
        문서들을 재순위화

        Args:
            query: 사용자 질문
            documents: [(score, title, date, text, url), ...]
            top_k: 반환할 상위 문서 개수

        Returns:
            [(new_score, title, date, text, url), ...]
        """
        pass

    @abstractmethod
    def compute_score(self, query: str, document: str) -> float:
        """단일 문서 점수 계산"""
        pass

    def is_available(self) -> bool:
        """사용 가능 여부"""
        return True

    def get_model_info(self) -> dict:
        """모델 정보 반환"""
        return {"name": self.__class__.__name__}
```

---

## 🎯 장점

### **1. 교체 용이성**
- Config만 변경하면 Reranker 교체 가능
- 코드 수정 불필요

### **2. A/B 테스트 가능**
```python
# 여러 Reranker 동시 비교
rerankers = {
    "bge": RerankerFactory.create("bge"),
    "flashrank": RerankerFactory.create("flashrank"),
}

for name, reranker in rerankers.items():
    results = reranker.rerank(query, docs)
    mrr = calculate_mrr(results)
    print(f"{name}: MRR={mrr:.3f}")
```

### **3. 확장성**
- 새 Reranker 추가 시 기존 코드 무수정
- 인터페이스만 구현하면 OK

### **4. 점진적 마이그레이션**
- 기존 코드 그대로 유지
- 새 코드에서만 Factory 사용

---

## 📚 다음 단계

### **향후 추가 가능한 Reranker**

1. **FlashRank** (빠른 속도)
   - 10배 빠름
   - 약간 낮은 정확도

2. **Cohere Rerank API** (높은 정확도)
   - 가장 높은 성능
   - API 비용 발생

3. **Voyage Rerank** (균형)
   - 좋은 성능
   - 합리적인 비용

### **다른 컴포넌트 추상화**

- Embedder (Upstage, OpenAI, Cohere)
- LLM (Upstage, OpenAI, Anthropic)
- VectorStore (Pinecone, Weaviate, Qdrant)

---

## ✅ 체크리스트

- [x] BaseReranker 인터페이스 생성
- [x] BGEReranker 구현 (기존 코드 이동)
- [x] RerankerFactory 구현
- [x] 하위 호환 wrapper 유지
- [x] Config 설정 추가
- [ ] FlashRank 구현 추가 (향후)
- [ ] A/B 테스트 스크립트 (향후)

---

**질문이 있으면 FLEXIBLE_ARCHITECTURE.md를 참고하세요!** 🚀
