# 유연한 RAG 아키텍처 (Plugin Architecture)

## 🎯 목표

**모든 컴포넌트를 교체 가능하게 설계**
- Reranker: BGE → FlashRank, Cohere, Voyage
- Embedder: Upstage → OpenAI, Cohere, Voyage
- LLM: Upstage → OpenAI, Anthropic, Gemini
- VectorDB: Pinecone → Weaviate, Milvus, Qdrant
- Retriever: BM25 → BM25+, Elasticsearch

**핵심**: **Config만 바꾸면 교체 가능!** (코드 수정 불필요)

---

## 📁 개선된 폴더 구조

```
src/
├── core/
│   ├── interfaces/                  # 🆕 추상 인터페이스 (계약)
│   │   ├── __init__.py
│   │   ├── reranker.py             # BaseReranker (추상 클래스)
│   │   ├── embedder.py             # BaseEmbedder
│   │   ├── llm.py                  # BaseLLM
│   │   ├── retriever.py            # BaseRetriever
│   │   └── vector_store.py         # BaseVectorStore
│   │
│   ├── retrieval/
│   │   ├── retrievers/
│   │   │   ├── base.py             # BaseRetriever 구현
│   │   │   ├── bm25.py             # BM25Retriever
│   │   │   ├── dense.py            # DenseRetriever
│   │   │   └── hybrid.py           # HybridRetriever
│   │   │
│   │   └── rerankers/              # 🆕 Reranker 플러그인들
│   │       ├── __init__.py
│   │       ├── base.py             # BaseReranker (인터페이스)
│   │       ├── bge_reranker.py     # BGE 구현
│   │       ├── flashrank_reranker.py  # FlashRank 구현
│   │       ├── cohere_reranker.py  # Cohere API 구현
│   │       └── voyage_reranker.py  # Voyage API 구현
│   │
│   ├── generation/
│   │   ├── llms/                   # 🆕 LLM 플러그인들
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # BaseLLM (인터페이스)
│   │   │   ├── upstage_llm.py      # Upstage 구현
│   │   │   ├── openai_llm.py       # OpenAI 구현
│   │   │   └── anthropic_llm.py    # Anthropic 구현
│   │   │
│   │   └── prompt_builder.py
│   │
│   └── ingestion/
│       └── embedders/              # 🆕 Embedder 플러그인들
│           ├── __init__.py
│           ├── base.py             # BaseEmbedder (인터페이스)
│           ├── upstage_embedder.py # Upstage 구현
│           ├── openai_embedder.py  # OpenAI 구현
│           └── cohere_embedder.py  # Cohere 구현
│
├── infrastructure/
│   ├── vector_stores/              # 🆕 VectorDB 플러그인들
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseVectorStore (인터페이스)
│   │   ├── pinecone_store.py       # Pinecone 구현
│   │   ├── weaviate_store.py       # Weaviate 구현
│   │   └── qdrant_store.py         # Qdrant 구현
│   │
│   └── external_apis/
│       ├── upstage/                # Upstage API 클라이언트
│       ├── cohere/                 # Cohere API 클라이언트
│       └── openai/                 # OpenAI API 클라이언트
│
├── factories/                      # 🆕 팩토리 패턴 (런타임 선택)
│   ├── __init__.py
│   ├── reranker_factory.py        # Reranker 생성
│   ├── embedder_factory.py        # Embedder 생성
│   ├── llm_factory.py             # LLM 생성
│   └── vector_store_factory.py    # VectorStore 생성
│
└── config/
    ├── settings.py                # 환경 설정
    ├── ml_settings.yaml           # ML 하이퍼파라미터
    └── plugins.yaml               # 🆕 플러그인 설정
```

---

## 🔧 구현 예시

### **1. 추상 인터페이스 (BaseReranker)**

```python
# src/core/interfaces/reranker.py
from abc import ABC, abstractmethod
from typing import List, Tuple

class BaseReranker(ABC):
    """
    Reranker 추상 인터페이스

    모든 Reranker 구현체는 이 인터페이스를 따라야 합니다.
    """

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
            재순위화된 문서 리스트
        """
        pass

    @abstractmethod
    def compute_score(self, query: str, document: str) -> float:
        """
        단일 문서의 관련성 점수 계산

        Args:
            query: 사용자 질문
            document: 문서 텍스트

        Returns:
            관련성 점수
        """
        pass
```

### **2. 구체적 구현체들**

#### **2-1. BGE Reranker**
```python
# src/core/retrieval/rerankers/bge_reranker.py
from core.interfaces.reranker import BaseReranker
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

try:
    from FlagEmbedding import FlagReranker
    AVAILABLE = True
except ImportError:
    AVAILABLE = False
    logger.warning("⚠️  FlagEmbedding 미설치 - BGEReranker 사용 불가")

class BGEReranker(BaseReranker):
    """BGE (BAAI) Reranker 구현"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", **kwargs):
        if not AVAILABLE:
            raise ImportError("FlagEmbedding 라이브러리가 설치되지 않았습니다.")

        self.model_name = model_name
        self.reranker = FlagReranker(model_name, **kwargs)
        logger.info(f"✅ BGEReranker 초기화: {model_name}")

    def rerank(self, query: str, documents: List[Tuple], top_k: int = 5) -> List[Tuple]:
        """BGE로 재순위화"""
        if not documents:
            return []

        # (query, document) 쌍 생성
        pairs = [[query, f"{doc[1]}\n\n{doc[3][:500]}"] for doc in documents]

        # Reranking 수행
        scores = self.reranker.compute_score(pairs)

        # 점수 기준 정렬
        reranked = sorted(
            zip(scores, documents),
            key=lambda x: x[0],
            reverse=True
        )

        # Top K 반환
        return [(score, *doc[1:]) for score, doc in reranked[:top_k]]

    def compute_score(self, query: str, document: str) -> float:
        """단일 문서 점수 계산"""
        return self.reranker.compute_score([[query, document]])[0]
```

#### **2-2. FlashRank Reranker**
```python
# src/core/retrieval/rerankers/flashrank_reranker.py
from core.interfaces.reranker import BaseReranker
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

try:
    from flashrank import Ranker, RerankRequest
    AVAILABLE = True
except ImportError:
    AVAILABLE = False
    logger.warning("⚠️  FlashRank 미설치 - FlashRankReranker 사용 불가")

class FlashRankReranker(BaseReranker):
    """FlashRank Reranker 구현 (빠른 경량 모델)"""

    def __init__(self, model_name: str = "ms-marco-MultiBERT-L-12", **kwargs):
        if not AVAILABLE:
            raise ImportError("flashrank 라이브러리가 설치되지 않았습니다.")

        self.model_name = model_name
        self.ranker = Ranker(model_name=model_name, **kwargs)
        logger.info(f"✅ FlashRankReranker 초기화: {model_name}")

    def rerank(self, query: str, documents: List[Tuple], top_k: int = 5) -> List[Tuple]:
        """FlashRank로 재순위화"""
        if not documents:
            return []

        # FlashRank 형식으로 변환
        passages = [
            {"id": i, "text": f"{doc[1]}\n\n{doc[3][:500]}"}
            for i, doc in enumerate(documents)
        ]

        # Reranking 수행
        request = RerankRequest(query=query, passages=passages)
        results = self.ranker.rerank(request)

        # 결과 변환
        reranked = []
        for result in results[:top_k]:
            idx = result["id"]
            score = result["score"]
            doc = documents[idx]
            reranked.append((score, doc[1], doc[2], doc[3], doc[4]))

        return reranked

    def compute_score(self, query: str, document: str) -> float:
        """단일 문서 점수 계산"""
        request = RerankRequest(query=query, passages=[{"id": 0, "text": document}])
        results = self.ranker.rerank(request)
        return results[0]["score"] if results else 0.0
```

#### **2-3. Cohere Reranker (API)**
```python
# src/core/retrieval/rerankers/cohere_reranker.py
from core.interfaces.reranker import BaseReranker
from typing import List, Tuple
import logging
import os

logger = logging.getLogger(__name__)

try:
    import cohere
    AVAILABLE = True
except ImportError:
    AVAILABLE = False
    logger.warning("⚠️  Cohere SDK 미설치 - CohereReranker 사용 불가")

class CohereReranker(BaseReranker):
    """Cohere Rerank API 구현"""

    def __init__(self, api_key: str = None, model: str = "rerank-english-v3.0", **kwargs):
        if not AVAILABLE:
            raise ImportError("cohere 라이브러리가 설치되지 않았습니다.")

        self.api_key = api_key or os.getenv("COHERE_API_KEY")
        if not self.api_key:
            raise ValueError("COHERE_API_KEY가 설정되지 않았습니다.")

        self.model = model
        self.client = cohere.Client(self.api_key)
        logger.info(f"✅ CohereReranker 초기화: {model}")

    def rerank(self, query: str, documents: List[Tuple], top_k: int = 5) -> List[Tuple]:
        """Cohere API로 재순위화"""
        if not documents:
            return []

        # Cohere 형식으로 변환
        docs_text = [f"{doc[1]}\n\n{doc[3][:1000]}" for doc in documents]

        # Reranking 수행 (API 호출)
        response = self.client.rerank(
            query=query,
            documents=docs_text,
            top_n=top_k,
            model=self.model
        )

        # 결과 변환
        reranked = []
        for result in response.results:
            idx = result.index
            score = result.relevance_score
            doc = documents[idx]
            reranked.append((score, doc[1], doc[2], doc[3], doc[4]))

        return reranked

    def compute_score(self, query: str, document: str) -> float:
        """단일 문서 점수 계산"""
        response = self.client.rerank(
            query=query,
            documents=[document],
            top_n=1,
            model=self.model
        )
        return response.results[0].relevance_score if response.results else 0.0
```

### **3. Factory Pattern (런타임 선택)**

```python
# src/factories/reranker_factory.py
from typing import Optional
from core.interfaces.reranker import BaseReranker
import logging

logger = logging.getLogger(__name__)

class RerankerFactory:
    """
    Reranker 팩토리

    Config 기반으로 적절한 Reranker 구현체를 생성합니다.
    """

    _registry = {}  # 등록된 Reranker들

    @classmethod
    def register(cls, name: str, reranker_class):
        """Reranker 구현체 등록"""
        cls._registry[name] = reranker_class
        logger.info(f"📦 Reranker 등록: {name} → {reranker_class.__name__}")

    @classmethod
    def create(cls, reranker_type: str, **kwargs) -> Optional[BaseReranker]:
        """
        Reranker 생성

        Args:
            reranker_type: "bge", "flashrank", "cohere", "voyage"
            **kwargs: Reranker 초기화 파라미터

        Returns:
            BaseReranker 인스턴스 또는 None
        """
        if reranker_type not in cls._registry:
            logger.error(f"❌ 알 수 없는 Reranker 타입: {reranker_type}")
            logger.info(f"   사용 가능: {list(cls._registry.keys())}")
            return None

        try:
            reranker_class = cls._registry[reranker_type]
            return reranker_class(**kwargs)
        except Exception as e:
            logger.error(f"❌ Reranker 생성 실패 ({reranker_type}): {e}")
            return None


# 기본 Reranker 등록
def register_default_rerankers():
    """기본 Reranker 등록"""
    try:
        from core.retrieval.rerankers.bge_reranker import BGEReranker
        RerankerFactory.register("bge", BGEReranker)
    except ImportError:
        logger.debug("BGEReranker 사용 불가")

    try:
        from core.retrieval.rerankers.flashrank_reranker import FlashRankReranker
        RerankerFactory.register("flashrank", FlashRankReranker)
    except ImportError:
        logger.debug("FlashRankReranker 사용 불가")

    try:
        from core.retrieval.rerankers.cohere_reranker import CohereReranker
        RerankerFactory.register("cohere", CohereReranker)
    except ImportError:
        logger.debug("CohereReranker 사용 불가")

# 초기화 시 자동 등록
register_default_rerankers()
```

### **4. Config 기반 사용**

```yaml
# config/plugins.yaml
reranker:
  type: "bge"  # "bge", "flashrank", "cohere", "voyage"
  config:
    model_name: "BAAI/bge-reranker-v2-m3"
    use_fp16: true
    device: "cpu"

# FlashRank로 교체하려면:
# reranker:
#   type: "flashrank"
#   config:
#     model_name: "ms-marco-MultiBERT-L-12"

# Cohere API로 교체하려면:
# reranker:
#   type: "cohere"
#   config:
#     model: "rerank-english-v3.0"
```

```python
# 사용 예시
from factories.reranker_factory import RerankerFactory
from config.ml_settings import load_plugin_config

# Config 로드
plugin_config = load_plugin_config()
reranker_type = plugin_config["reranker"]["type"]
reranker_kwargs = plugin_config["reranker"]["config"]

# Reranker 생성 (팩토리 패턴)
reranker = RerankerFactory.create(reranker_type, **reranker_kwargs)

# 사용
reranked_docs = reranker.rerank(query="질문", documents=docs, top_k=5)
```

---

## 🎯 장점

### **1. 교체 용이성**
```bash
# BGE → FlashRank 교체
# 코드 수정 없이 config만 변경!
vim config/plugins.yaml  # type: "bge" → "flashrank"
```

### **2. A/B 테스트 가능**
```python
# 여러 Reranker 동시 비교
rerankers = {
    "bge": RerankerFactory.create("bge"),
    "flashrank": RerankerFactory.create("flashrank"),
    "cohere": RerankerFactory.create("cohere")
}

for name, reranker in rerankers.items():
    results = reranker.rerank(query, docs)
    evaluate(results)  # 성능 비교
```

### **3. 점진적 마이그레이션**
```python
# 기존 코드는 그대로 유지하면서 새 Reranker 테스트
if USE_NEW_RERANKER:
    reranker = RerankerFactory.create("flashrank")
else:
    reranker = DocumentReranker()  # 기존 BGE
```

### **4. 확장성**
```python
# 새 Reranker 추가 (예: Voyage)
# 1. core/retrieval/rerankers/voyage_reranker.py 생성
# 2. RerankerFactory.register("voyage", VoyageReranker)
# 3. config에서 type: "voyage" 설정
# → 기존 코드 수정 불필요!
```

---

## 📊 다른 컴포넌트 적용

### **Embedder**
```python
# core/interfaces/embedder.py
class BaseEmbedder(ABC):
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        pass

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        pass

# 구현체
- UpstageEmbedder (현재)
- OpenAIEmbedder (text-embedding-3-large)
- CohereEmbedder (embed-multilingual-v3.0)
- VoyageEmbedder (voyage-2)
```

### **LLM**
```python
# core/interfaces/llm.py
class BaseLLM(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass

    @abstractmethod
    def stream(self, prompt: str, **kwargs) -> Iterator[str]:
        pass

# 구현체
- UpstageLLM (현재)
- OpenAILLM (gpt-4)
- AnthropicLLM (claude-3-opus)
- GeminiLLM (gemini-pro)
```

### **VectorStore**
```python
# core/interfaces/vector_store.py
class BaseVectorStore(ABC):
    @abstractmethod
    def search(self, query_vector: List[float], top_k: int) -> List[Dict]:
        pass

    @abstractmethod
    def upsert(self, vectors: List[Tuple], metadata: List[Dict]):
        pass

# 구현체
- PineconeStore (현재)
- WeaviateStore
- QdrantStore
- MilvusStore
```

---

## 🚀 마이그레이션 계획

### **Phase 1: Reranker 추상화 (1주)**
1. `core/interfaces/reranker.py` 생성 (BaseReranker)
2. `core/retrieval/rerankers/` 폴더 생성
3. BGE 구현을 `bge_reranker.py`로 분리
4. Factory 패턴 구현
5. 기존 코드에 wrapper 유지 (하위 호환성)

### **Phase 2: 다른 Reranker 추가 (1주)**
1. FlashRank 구현 추가
2. Cohere API 구현 추가
3. A/B 테스트 스크립트 작성
4. 성능 비교 후 최적 Reranker 선정

### **Phase 3: 다른 컴포넌트 적용 (2-3주)**
1. Embedder 추상화
2. LLM 추상화
3. VectorStore 추상화

---

## 📚 참고 자료

### **디자인 패턴**
- **Strategy Pattern**: 런타임에 알고리즘 교체
- **Factory Pattern**: 객체 생성 로직 분리
- **Dependency Injection**: 외부에서 의존성 주입

### **RAG 시스템 플러그인 아키텍처**
- [LangChain Pluggable Architecture](https://python.langchain.com/docs/concepts/architecture/)
- [LlamaIndex Module System](https://docs.llamaindex.ai/en/stable/module_guides/)
- [Haystack Pipeline Architecture](https://haystack.deepset.ai/overview/intro)

---

## ✅ 다음 단계

이 문서를 팀과 공유하고:
1. Reranker 추상화 우선 진행
2. FlashRank, Cohere 성능 비교
3. 다른 컴포넌트로 확대

**질문이 있으면 언제든지!** 🚀
