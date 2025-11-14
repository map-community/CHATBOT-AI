# KNU 컴퓨터학부 AI 챗봇 설치 가이드

경북대학교 컴퓨터학부 공지사항 AI 챗봇을 로컬 환경에서 실행하는 방법을 안내합니다.

## 📋 사전 요구사항

### 1. Docker 및 Docker Compose 설치
- **Docker Desktop** (Windows/Mac): [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
- **Docker Engine** (Linux): [https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/)

설치 확인:
```bash
docker --version
docker-compose --version
```

### 2. API 키 준비
다음 서비스의 API 키가 필요합니다:
- **Pinecone** (벡터 데이터베이스): [https://www.pinecone.io/](https://www.pinecone.io/)
- **Upstage** (임베딩 & LLM): [https://www.upstage.ai/](https://www.upstage.ai/)

---

## 🚀 설치 및 실행

### 1. 프로젝트 클론

```bash
git clone https://github.com/map-community/CHATBOT-AI.git
cd CHATBOT-AI
```

### 2. 환경변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 다음 내용을 입력합니다:

```env
# Pinecone 설정
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX_NAME=info

# Upstage 설정
UPSTAGE_API_KEY=your_upstage_api_key_here

# MongoDB 설정
MONGODB_URI=mongodb://mongodb:27017/

# Redis 설정
REDIS_HOST=redis
REDIS_PORT=6379
```

**⚠️ 주의:** `.env` 파일은 절대 Git에 커밋하지 마세요! (`.gitignore`에 이미 포함되어 있습니다)

### 3. Pinecone 인덱스 생성

Pinecone 콘솔에서 다음 설정으로 인덱스를 생성합니다:

- **Index Name**: `info` (또는 `.env`의 `PINECONE_INDEX_NAME`과 동일하게)
- **Dimensions**: `4096`
- **Metric**: `cosine`
- **Cloud**: `AWS`
- **Region**: `us-east-1`

### 4. Docker 이미지 빌드 및 실행

#### Windows (PowerShell)
```powershell
# BuildKit 활성화 (빠른 빌드)
$env:DOCKER_BUILDKIT=1

# Docker Compose로 빌드 및 실행
docker-compose up --build -d
```

#### Linux/Mac
```bash
# BuildKit 활성화
export DOCKER_BUILDKIT=1

# Docker Compose로 빌드 및 실행
docker-compose up --build -d
```

**예상 빌드 시간:** 10-15분 (Mecab 컴파일 포함)

### 5. 실행 상태 확인

```bash
# 로그 확인
docker-compose logs -f app

# 컨테이너 상태 확인
docker-compose ps
```

**정상 실행 시 로그:**
```
✅ API 키를 .env 파일에서 성공적으로 로드했습니다.
✅ Mecab 사용 가능 (30-50배 빠른 형태소 분석)
✅ Pinecone 인덱스 'info'에 연결되었습니다.
✅ MongoDB에 연결되었습니다.
✅ Redis에 연결되었습니다.
🔄 캐시 초기화 시작...
✅ Pinecone에서 XXXX개 문서 메타데이터를 가져왔습니다.
✅ 캐시 초기화 완료!
* Running on http://127.0.0.1:5000
```

### 6. 초기 데이터 크롤링

**⚠️ 중요:** 처음 실행 시 Pinecone에 공지사항 데이터를 업로드해야 합니다.

```bash
# Docker 컨테이너 접속
docker-compose exec app bash

# 크롤러 실행 (경북대 컴퓨터학부 공지사항 수집)
cd /app/src/modules
python data_crawler.py

# 완료 후 컨테이너 종료
exit
```

**예상 시간:** 10-15분

**크롤링 진행 상황:**
```
================================================================================
🌐 경북대 컴퓨터학부 공지사항 크롤링 시작
📋 크롤링할 URL 개수: XXXX개
================================================================================

🔄 웹 크롤링 중... (수 분 소요될 수 있습니다)

================================================================================
✅ 웹 크롤링 완료! XXXX개 공지사항 수집됨
================================================================================

📊 임베딩 생성 시작: XXXX개 문서
🔄 Upstage API로 임베딩 생성 중...
✅ 임베딩 생성 완료!

📤 Pinecone 업로드 시작: XXXX개 벡터
⏳ 진행: 50/XXXX (XX.X%)
...
✅ Pinecone 업로드 완료!
```

### 7. 애플리케이션 재시작

크롤링 완료 후 캐시를 새로고침하기 위해 재시작합니다:

```bash
docker-compose restart app
```

---

## 🧪 API 테스트

### Health Check

```bash
curl http://127.0.0.1:5000/health
```

**응답:**
```json
{
  "status": "healthy",
  "message": "KNU Chatbot Server is running",
  "version": "1.0.0"
}
```

### 챗봇 질문

#### Linux/Mac
```bash
curl -X POST http://127.0.0.1:5000/ai/ai-response \
  -H "Content-Type: application/json" \
  -d '{"question":"컴퓨터학부 졸업요건이 뭐야?"}'
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:5000/ai/ai-response" `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"question":"컴퓨터학부 졸업요건이 뭐야?"}'
```

**응답 예시:**
```json
{
  "answer": "컴퓨터학부 졸업요건은...",
  "references": "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=...",
  "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다...",
  "images": ["No content"]
}
```

---

## 🔧 유용한 명령어

### 컨테이너 관리

```bash
# 컨테이너 시작
docker-compose up -d

# 컨테이너 중지
docker-compose down

# 컨테이너 재시작
docker-compose restart app

# 로그 확인 (실시간)
docker-compose logs -f app

# 컨테이너 접속
docker-compose exec app bash
```

### 캐시 재초기화

코드 변경 후 캐시를 새로고침하려면:

```bash
docker-compose restart app
```

또는 수동으로:

```bash
docker-compose exec app python -c "
from src.modules.ai_modules import initialize_cache
print('🔄 캐시 재초기화 중...')
initialize_cache()
print('✅ 캐시 재초기화 완료!')
"
```

### 데이터베이스 확인

#### MongoDB 문서 개수 확인
```bash
docker-compose exec mongodb mongosh knu_chatbot --eval "db.notice_collection.countDocuments({})"
```

#### Pinecone 벡터 개수 확인
```bash
docker-compose exec app python -c "
from pinecone import Pinecone
import os
from dotenv import load_dotenv

load_dotenv()
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
index = pc.Index('info')
stats = index.describe_index_stats()
print(f'Pinecone 벡터 개수: {stats.total_vector_count}')
"
```

---

## 🐛 문제 해결

### 1. "division by zero" 에러

**원인:** 캐시가 비어있거나 초기화되지 않음

**해결:**
```bash
docker-compose restart app
```

### 2. "No module named 'konlpy'" 에러

**원인:** Docker 이미지가 오래됨

**해결:**
```bash
docker-compose down
docker-compose up --build
```

### 3. "해당 질문은 공지사항에 없는 내용입니다" 응답

**가능한 원인:**
- 초기 데이터 크롤링을 하지 않음
- 캐시가 오래됨

**해결:**
1. 크롤링 실행 (위 "6. 초기 데이터 크롤링" 참고)
2. 애플리케이션 재시작: `docker-compose restart app`

### 4. Docker 빌드가 너무 느림

**해결:** BuildKit 캐시를 사용하고 있는지 확인

```bash
# 환경변수 설정
export DOCKER_BUILDKIT=1  # Linux/Mac
$env:DOCKER_BUILDKIT=1    # Windows PowerShell

# 재빌드 (기존 이미지가 있으면 빠름)
docker-compose up --build
```

### 5. 저장 공간 부족

**정리 방법:**

```bash
# 사용하지 않는 Docker 리소스 삭제
docker system prune -a

# 현재 디스크 사용량 확인
docker system df
```

---

## 📦 서비스 구성

이 프로젝트는 다음 서비스로 구성됩니다:

| 서비스 | 포트 | 용도 |
|--------|------|------|
| **app** | 5000 | Flask API 서버 |
| **mongodb** | 27017 | 공지사항 메타데이터 저장 |
| **redis** | 6379 | 캐시 |

---

## 🔒 보안 주의사항

1. **`.env` 파일 관리**
   - 절대 Git에 커밋하지 마세요
   - API 키를 공개 저장소에 노출하지 마세요

2. **프로덕션 배포**
   - Flask 개발 서버 대신 Gunicorn/uWSGI 사용
   - HTTPS 설정
   - API 키 환경변수로 관리
   - 방화벽 설정

---

## 📝 추가 정보

- **프로젝트 GitHub**: https://github.com/map-community/CHATBOT-AI
- **이슈 리포트**: https://github.com/map-community/CHATBOT-AI/issues
- **Docker Hub**: N/A

---

## 👥 기여

이 프로젝트에 기여하고 싶으시다면 Pull Request를 보내주세요!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.
