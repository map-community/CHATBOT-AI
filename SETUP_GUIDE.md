# 🛠️ 설정 가이드

## 📝 제공하신 파일 배치 방법

제공하신 4개의 Python 파일을 다음과 같이 배치해주세요:

### 1️⃣ 첫 번째 파일 (데이터 크롤링 코드)
**위치**: `src/modules/data_crawler.py`

이 파일은 다음 작업을 수행합니다:
- 경북대 컴퓨터학부 공지사항 크롤링
- 교수진/직원 정보 크롤링
- 채용 정보 크롤링
- 세미나 정보 크롤링
- Pinecone에 벡터 임베딩 저장
- MongoDB에 메타데이터 저장

**수정 필요 사항**:
```python
# 파일 상단에 다음 import 추가
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.config import settings

# 기존 하드코딩된 값들을 설정값으로 변경
pinecone_api_key = settings.PINECONE_API_KEY
index_name = settings.PINECONE_INDEX_NAME
upstage_api_key = settings.UPSTAGE_API_KEY
```

---

### 2️⃣ 두 번째 파일 (RAG 시스템 - 최신 버전)
**위치**: `src/modules/ai_modules.py`

이 파일은 다음 작업을 수행합니다:
- 질문 전처리 및 명사 추출
- BM25 + Dense Retrieval 하이브리드 검색
- 문서 클러스터링
- LangChain RAG 파이프라인
- Redis 캐싱
- 최종 답변 생성

**수정 필요 사항**:
```python
# 파일 상단에 다음 추가
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.config import settings

# 기존 하드코딩된 값들을 설정값으로 변경
pinecone_api_key = settings.PINECONE_API_KEY
index_name = settings.PINECONE_INDEX_NAME
upstage_api_key = settings.UPSTAGE_API_KEY
```

---

### 3️⃣ 세 번째 파일 (이전 버전 RAG)
**위치**: ❌ **사용하지 않음**

이 파일은 이전 버전이므로 배치하지 않습니다.

---

### 4️⃣ 네 번째 파일 (Flask 서버)
**위치**: `src/app.py`

이 파일은 다음 작업을 수행합니다:
- Flask 웹 서버 실행
- `/ai/ai-response` API 엔드포인트 제공
- CORS 설정
- 에러 핸들링

**수정 필요 사항**:
```python
# 파일을 다음과 같이 수정
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from src.modules.ai_modules import get_ai_message, initialize_cache
from src.config import settings

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    CORS(app)

    @app.route('/ai/ai-response', methods=['POST'])
    def ai_response():
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No JSON data provided'}), 400

            question = data.get('question')
            if not isinstance(question, str) or not question.strip():
                return jsonify({'error': 'Invalid or missing question'}), 400

            logger.info(f"Question received: {question}")
            response = get_ai_message(question)
            logger.info(f"Response generated successfully")

            if isinstance(response, dict):
                return jsonify(response)
            else:
                return jsonify({'error': 'Invalid response format from AI module'}), 500

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({'status': 'healthy', 'message': 'Server is running'}), 200

    return app

if __name__ == "__main__":
    # 캐시 초기화
    logger.info("Initializing cache...")
    initialize_cache()
    logger.info("Cache initialized successfully")

    app = create_app()
    logger.info(f"Starting server on {settings.FLASK_HOST}:{settings.FLASK_PORT}")
    app.run(
        host=settings.FLASK_HOST,
        port=settings.FLASK_PORT,
        debug=settings.FLASK_DEBUG
    )
else:
    initialize_cache()
    app = create_app()
```

---

## 🚀 빠른 시작

### 1단계: 파일 배치
위 가이드대로 4개 파일을 배치하고 수정합니다.

### 2단계: 의존성 설치
```bash
chmod +x setup.sh
./setup.sh
```

또는 수동으로:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m nltk.downloader punkt averaged_perceptron_tagger
```

### 3단계: 환경 변수 설정
```bash
cp .env.example .env
nano .env  # 또는 vim, vi 등
```

다음 값들을 입력:
- `PINECONE_API_KEY`: Pinecone API 키
- `UPSTAGE_API_KEY`: Upstage API 키
- 나머지는 기본값 사용 가능

### 4단계: MongoDB 및 Redis 시작
```bash
# MongoDB 시작
sudo systemctl start mongodb
# 또는
sudo systemctl start mongod

# Redis 시작
sudo systemctl start redis
# 또는
sudo systemctl start redis-server

# 상태 확인
sudo systemctl status mongodb
sudo systemctl status redis
```

### 5단계: 초기 데이터 크롤링 (최초 1회만)
```bash
source venv/bin/activate
python src/modules/data_crawler.py
```

⚠️ **주의**: 이 작업은 시간이 오래 걸릴 수 있습니다 (30분~1시간).

### 6단계: 서버 실행
```bash
python src/app.py
```

서버가 `http://localhost:5000`에서 실행됩니다.

---

## 🧪 테스트

### Health Check
```bash
curl http://localhost:5000/health
```

### AI 질문 테스트
```bash
curl -X POST http://localhost:5000/ai/ai-response \
  -H "Content-Type: application/json" \
  -d '{"question": "2024년 2학기 수강신청 일정 알려줘"}'
```

---

## 📌 문제 해결

### Pinecone 인덱스가 없는 경우
Python 콘솔에서:
```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your_api_key")
pc.create_index(
    name="info",
    dimension=4096,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)
```

### MongoDB 연결 오류
```bash
sudo systemctl restart mongodb
sudo systemctl enable mongodb
```

### Redis 연결 오류
```bash
sudo systemctl restart redis
sudo systemctl enable redis
```

### 포트 충돌
`.env` 파일에서 `FLASK_PORT`를 변경하세요.

---

## 📂 최종 디렉토리 구조

```
CHATBOT-AI/
├── src/
│   ├── __init__.py
│   ├── app.py                    # Flask 서버 (4번째 파일 수정)
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── data_crawler.py       # 데이터 크롤링 (1번째 파일 수정)
│   │   └── ai_modules.py         # RAG 시스템 (2번째 파일 수정)
│   └── config/
│       ├── __init__.py
│       └── settings.py           # 설정 파일
├── logs/                          # 로그 파일 디렉토리
├── venv/                          # 가상환경 (자동 생성)
├── requirements.txt
├── .env                           # 환경 변수 (직접 생성)
├── .env.example
├── .gitignore
├── setup.sh                       # 설치 스크립트
├── README.md
└── SETUP_GUIDE.md                # 이 파일
```

---

## 🎯 다음 단계

1. ✅ 파일 배치 및 수정
2. ✅ 의존성 설치
3. ✅ 환경 변수 설정
4. ✅ MongoDB/Redis 시작
5. ✅ 초기 데이터 크롤링
6. ✅ 서버 실행
7. ✅ API 테스트

모든 단계가 완료되면 챗봇이 정상적으로 작동합니다! 🎉
