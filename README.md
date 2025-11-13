# KNU 컴퓨터학부 AI 챗봇

경북대학교 컴퓨터학부 공지사항, 교수진 정보, 채용 정보, 세미나 정보를 제공하는 RAG 기반 AI 챗봇입니다.

## 📋 주요 기능

- 🔍 **공지사항 검색**: 컴퓨터학부 공지사항 실시간 크롤링 및 검색
- 👨‍🏫 **교수진 정보**: 교수진 및 직원 정보 제공
- 💼 **채용 정보**: 신입/경력 채용 정보 제공
- 🎓 **세미나/행사**: 학부 세미나 및 행사 정보 제공
- 🤖 **AI 답변**: LangChain + Upstage LLM을 활용한 자연어 답변 생성

## 🛠️ 기술 스택

### Backend
- **Flask**: RESTful API 서버
- **LangChain**: RAG 파이프라인 구축
- **Upstage API**: LLM 및 임베딩 모델

### Vector Database
- **Pinecone**: 벡터 데이터베이스
- **FAISS**: 로컬 벡터 검색

### Database
- **MongoDB**: 문서 메타데이터 저장
- **Redis**: 캐싱

### NLP & ML
- **BM25**: 키워드 기반 검색
- **KoNLPy**: 한국어 형태소 분석
- **Dense Retrieval**: 의미 기반 검색

## 📁 프로젝트 구조

```
CHATBOT-AI/
├── src/
│   ├── modules/
│   │   ├── data_crawler.py      # 데이터 크롤링 모듈
│   │   └── ai_modules.py         # RAG 시스템 모듈
│   ├── config/
│   │   └── settings.py           # 설정 파일
│   └── app.py                    # Flask 애플리케이션
├── logs/                          # 로그 파일
├── requirements.txt               # Python 의존성
├── .env.example                   # 환경변수 예시
├── .gitignore
└── README.md
```

## 🚀 시작하기

### 1. 사전 요구사항

- Python 3.9+
- MongoDB (localhost:27017)
- Redis (localhost:6379)
- Pinecone 계정
- Upstage API 키

### 2. 설치

```bash
# 1. 저장소 클론
git clone <repository-url>
cd CHATBOT-AI

# 2. 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 한국어 NLP 리소스 다운로드
python -m nltk.downloader punkt averaged_perceptron_tagger
```

### 3. 환경 변수 설정

`.env.example`을 `.env`로 복사하고 값을 채워넣습니다:

```bash
cp .env.example .env
```

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=info
UPSTAGE_API_KEY=your_upstage_api_key
MONGODB_URI=mongodb://localhost:27017/
```

### 4. 초기 데이터 설정

```bash
# MongoDB와 Redis가 실행 중인지 확인
sudo systemctl status mongodb
sudo systemctl status redis

# 초기 데이터 크롤링 (최초 1회만 실행)
python src/modules/data_crawler.py
```

### 5. 서버 실행

```bash
python src/app.py
```

서버는 `http://localhost:5000`에서 실행됩니다.

## 📡 API 사용법

### POST `/ai/ai-response`

챗봇에게 질문을 보내고 답변을 받습니다.

**요청:**
```json
{
  "question": "2024년 2학기 수강신청 일정이 언제인가요?"
}
```

**응답:**
```json
{
  "answer": "2024년 2학기 수강신청은 이미 종료되었습니다. 수강신청 기간은 8월 13일부터 8월 20일까지였습니다.",
  "references": "\n참고 문서 URL: https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28123",
  "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
  "images": ["No content"]
}
```

**cURL 예시:**
```bash
curl -X POST http://localhost:5000/ai/ai-response \
  -H "Content-Type: application/json" \
  -d '{"question": "최근 공지사항 알려줘"}'
```

## 🔧 주요 모듈 설명

### `data_crawler.py`
- 경북대 컴퓨터학부 웹사이트 크롤링
- 공지사항, 교수진, 채용, 세미나 정보 수집
- Pinecone에 벡터 임베딩 저장
- MongoDB에 메타데이터 저장

### `ai_modules.py`
- BM25 + Dense Retrieval 하이브리드 검색
- 문서 클러스터링 및 유사도 계산
- LangChain을 활용한 RAG 파이프라인
- Redis 캐싱을 통한 성능 최적화

### `app.py`
- Flask RESTful API 서버
- CORS 설정
- 에러 핸들링

## ⚙️ 주요 설정

### 벡터 검색 파라미터
- **BM25**: k1=1.5, b=0.75
- **Top-K**: 20~30개 문서 검색
- **클러스터링 임계값**: 0.89

### 임베딩 모델
- **Upstage**: solar-embedding-1-large (4096차원)

## 🐛 문제 해결

### MongoDB 연결 오류
```bash
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

### Redis 연결 오류
```bash
sudo systemctl start redis
sudo systemctl enable redis
```

### Pinecone 인덱스 생성
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

## 📝 개발 노트

### 데이터 업데이트
정기적으로 크롤러를 실행하여 최신 데이터를 유지합니다:
```bash
# Cron job 설정 (매일 자정)
0 0 * * * cd /path/to/CHATBOT-AI && python src/modules/data_crawler.py
```

### 로그 확인
```bash
tail -f logs/app.log
```

## 📄 라이선스

이 프로젝트는 교육 목적으로 제작되었습니다.

## 👥 기여

버그 리포트 및 기능 제안은 이슈로 등록해주세요.
