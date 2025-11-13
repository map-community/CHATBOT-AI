# 🚀 KNU 챗봇 프로젝트 시작하기

> **상태**: 프로젝트 구조 생성 완료 ✅
> **다음 단계**: 제공하신 Python 파일 복사 필요 📋

---

## 📊 현재 프로젝트 상태

### ✅ 완료된 작업
- [x] 프로젝트 디렉토리 구조 생성
- [x] 필수 설정 파일 생성 (requirements.txt, .env.example, .gitignore)
- [x] Flask 애플리케이션 (`src/app.py`) 생성
- [x] 설정 모듈 (`src/config/settings.py`) 생성
- [x] 자동 설치 스크립트 (`setup.sh`) 생성
- [x] 상세 문서 작성 (README.md, SETUP_GUIDE.md 등)

### ⏳ 해야 할 작업
1. **제공하신 Python 파일 2개를 복사** ⬅️ **지금 여기!**
2. 의존성 패키지 설치
3. 환경 변수 설정 (.env)
4. MongoDB/Redis 설정
5. 초기 데이터 크롤링
6. 서버 실행 및 테스트

---

## 🎯 지금 바로 시작하기

### Step 1: 제공하신 파일 복사하기 📋

**COPY_FILES_GUIDE.md**를 열어서 다음 2개 파일을 복사하세요:

```bash
cat COPY_FILES_GUIDE.md
```

복사해야 할 파일:
1. **첫 번째 파일** (크롤링 코드) → `src/modules/data_crawler.py`
2. **두 번째 파일** (RAG 시스템) → `src/modules/ai_modules.py`

⚠️ **주의**: 파일 복사 후 API 키를 설정값으로 변경해야 합니다!

---

### Step 2: 자동 설치 실행 🔧

```bash
chmod +x setup.sh
./setup.sh
```

이 스크립트가 자동으로:
- 가상환경 생성
- 패키지 설치
- NLTK 데이터 다운로드
- 서비스 상태 확인

---

### Step 3: 환경 변수 설정 ⚙️

```bash
cp .env.example .env
nano .env  # 또는 vim .env
```

다음 값을 입력하세요:
```env
PINECONE_API_KEY=your_actual_pinecone_key
UPSTAGE_API_KEY=your_actual_upstage_key
```

---

### Step 4: MongoDB & Redis 시작 🗄️

```bash
# MongoDB 시작
sudo systemctl start mongodb

# Redis 시작
sudo systemctl start redis

# 상태 확인
sudo systemctl status mongodb
sudo systemctl status redis
```

---

### Step 5: 초기 데이터 크롤링 📡

```bash
source venv/bin/activate
python src/modules/data_crawler.py
```

⏰ **소요 시간**: 30분~1시간 (최초 1회만 필요)

---

### Step 6: 서버 실행 🎉

```bash
python src/app.py
```

서버가 `http://localhost:5000`에서 실행됩니다!

---

## 🧪 빠른 테스트

### Health Check
```bash
curl http://localhost:5000/health
```

**예상 응답**:
```json
{
  "status": "healthy",
  "message": "KNU Chatbot Server is running",
  "version": "1.0.0"
}
```

### AI 질문 테스트
```bash
curl -X POST http://localhost:5000/ai/ai-response \
  -H "Content-Type: application/json" \
  -d '{"question": "컴퓨터학부 공지사항 최근 것 알려줘"}'
```

---

## 📁 프로젝트 구조

```
CHATBOT-AI/
├── src/
│   ├── app.py                    ✅ Flask 서버 (생성됨)
│   ├── modules/
│   │   ├── data_crawler.py       ⏳ 복사 필요!
│   │   └── ai_modules.py         ⏳ 복사 필요!
│   └── config/
│       └── settings.py           ✅ 설정 파일 (생성됨)
├── logs/                          ✅ 로그 디렉토리 (생성됨)
├── requirements.txt               ✅ 의존성 목록 (생성됨)
├── .env.example                   ✅ 환경변수 예시 (생성됨)
├── .env                           ⏳ 생성 필요!
├── setup.sh                       ✅ 설치 스크립트 (생성됨)
├── README.md                      ✅ 프로젝트 문서 (생성됨)
├── SETUP_GUIDE.md                 ✅ 설치 가이드 (생성됨)
├── COPY_FILES_GUIDE.md            ✅ 파일 복사 가이드 (생성됨)
└── START_HERE.md                  ✅ 이 파일
```

---

## 📚 문서 가이드

각 문서의 용도:

| 문서 | 용도 |
|------|------|
| **START_HERE.md** (이 파일) | 👉 첫 시작 가이드 |
| **COPY_FILES_GUIDE.md** | 제공하신 파일 복사 방법 |
| **SETUP_GUIDE.md** | 상세 설치 및 설정 가이드 |
| **README.md** | 프로젝트 전체 문서 |

---

## 🆘 문제 해결

### MongoDB가 없는 경우
```bash
# Ubuntu/Debian
sudo apt-get install mongodb

# CentOS/RHEL
sudo yum install mongodb
```

### Redis가 없는 경우
```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# CentOS/RHEL
sudo yum install redis
```

### Pinecone 인덱스 생성
```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your_key")
pc.create_index(
    name="info",
    dimension=4096,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)
```

---

## ✅ 체크리스트

완료하면 체크하세요:

- [ ] 제공하신 Python 파일 2개를 복사했다
- [ ] API 키 하드코딩을 설정값으로 변경했다
- [ ] `setup.sh`를 실행했다
- [ ] `.env` 파일을 생성하고 API 키를 입력했다
- [ ] MongoDB와 Redis를 시작했다
- [ ] 초기 데이터 크롤링을 완료했다
- [ ] 서버가 정상적으로 실행된다
- [ ] `/health` 엔드포인트가 응답한다
- [ ] AI 질문 테스트가 성공했다

---

## 🎉 모든 단계 완료 시

축하합니다! 🎊

이제 경북대 컴퓨터학부 AI 챗봇이 정상적으로 작동합니다!

**다음 단계**:
- 정기적으로 `data_crawler.py` 실행하여 최신 데이터 유지
- 프로덕션 환경에서는 Gunicorn 등의 WSGI 서버 사용
- Nginx를 리버스 프록시로 설정
- HTTPS 설정 (Let's Encrypt)
- 로그 모니터링 설정

자세한 내용은 `README.md`를 참고하세요!

---

**질문이나 문제가 있으신가요?**
각 가이드 문서를 참고하거나 로그 파일(`logs/app.log`)을 확인하세요.
