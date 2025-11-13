# 📋 파일 복사 가이드

제공하신 4개의 Python 파일을 프로젝트에 배치하는 방법입니다.

## 방법 1: 직접 복사 (권장)

### 1️⃣ 첫 번째 파일 → `src/modules/data_crawler.py`

1. 제공하신 **첫 번째 파일**(크롤링 코드)의 내용을 복사합니다.
2. 다음 명령어로 파일을 생성합니다:

```bash
nano src/modules/data_crawler.py
# 또는
vim src/modules/data_crawler.py
```

3. 복사한 내용을 붙여넣습니다.
4. 저장하고 종료합니다 (nano: Ctrl+X, Y, Enter / vim: :wq)

---

### 2️⃣ 두 번째 파일 → `src/modules/ai_modules.py`

1. 제공하신 **두 번째 파일**(RAG 시스템 코드)의 내용을 복사합니다.
2. 다음 명령어로 파일을 생성합니다:

```bash
nano src/modules/ai_modules.py
# 또는
vim src/modules/ai_modules.py
```

3. 복사한 내용을 붙여넣습니다.
4. 저장하고 종료합니다.

---

### 3️⃣ 세 번째 파일

❌ **이 파일은 사용하지 않습니다** (이전 버전이므로)

---

### 4️⃣ 네 번째 파일

✅ **이미 `src/app.py`로 생성되었습니다!**

---

## 방법 2: Python 스크립트로 복사

다음 Python 스크립트를 사용하여 파일을 복사할 수 있습니다:

```python
# copy_files.py

# 파일 1: data_crawler.py 내용
file1_content = """
# 여기에 첫 번째 파일의 전체 내용을 붙여넣으세요
"""

# 파일 2: ai_modules.py 내용
file2_content = """
# 여기에 두 번째 파일의 전체 내용을 붙여넣으세요
"""

# 파일 저장
with open('src/modules/data_crawler.py', 'w', encoding='utf-8') as f:
    f.write(file1_content)

with open('src/modules/ai_modules.py', 'w', encoding='utf-8') as f:
    f.write(file2_content)

print("✅ 파일 복사 완료!")
```

실행:
```bash
python copy_files.py
```

---

## ⚠️ 중요: 설정 값 수정

파일을 복사한 후, **반드시** 다음 수정을 해주세요:

### `src/modules/data_crawler.py` 수정

파일 상단 (import 섹션 바로 아래)에 다음을 추가:

```python
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from src.config import settings
    pinecone_api_key = settings.PINECONE_API_KEY
    index_name = settings.PINECONE_INDEX_NAME
    upstage_api_key = settings.UPSTAGE_API_KEY
except ImportError:
    # Fallback - 기존 하드코딩된 값 사용
    pinecone_api_key = 'pcsk_3pp5QX_EeyfanpYE8u1G2hKkyLnfhWQMUHvdbUJeBZdULHaFMV5j67XDQwqXDUCBtFLYpt'
    index_name = 'info'
    upstage_api_key = 'up_6hq78Et2phdvQWCMQLccIVpWJDF5R'
```

그리고 **기존의 하드코딩된 API 키 라인을 삭제하거나 주석 처리**:

```python
# 삭제하거나 주석 처리할 라인들:
# pinecone_api_key='pcsk_3pp5QX_EeyfanpYE8u1G2hKkyLnfhWQMUHvdbUJeBZdULHaFMV5j67XDQwqXDUCBtFLYpt'
# index_name = 'info'
# upstage_api_key = 'up_6hq78Et2phdvQWCMQLccIVpWJDF5R'
```

---

### `src/modules/ai_modules.py` 수정

마찬가지로 파일 상단에 다음을 추가:

```python
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from src.config import settings
    PINECONE_API_KEY = settings.PINECONE_API_KEY
    PINECONE_INDEX_NAME = settings.PINECONE_INDEX_NAME
    UPSTAGE_API_KEY = settings.UPSTAGE_API_KEY
    MONGODB_URI = settings.MONGODB_URI
    REDIS_HOST = settings.REDIS_HOST
    REDIS_PORT = settings.REDIS_PORT
    REDIS_DB = settings.REDIS_DB
except ImportError:
    # Fallback
    PINECONE_API_KEY = os.getenv('PINECONE_API_KEY', 'pcsk_3pp5QX_EeyfanpYE8u1G2hKkyLnfhWQMUHvdbUJeBZdULHaFMV5j67XDQwqXDUCBtFLYpt')
    PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'info')
    UPSTAGE_API_KEY = os.getenv('UPSTAGE_API_KEY', 'up_6hq78Et2phdvQWCMQLccIVpWJDF5R')
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
```

그리고 **기존의 하드코딩된 API 키 라인을 삭제하거나 주석 처리**.

---

## 🔍 파일 복사 확인

다음 명령어로 파일이 제대로 생성되었는지 확인:

```bash
ls -lh src/modules/

# 다음과 같이 표시되어야 합니다:
# -rw-r--r-- 1 user user  XXK ... data_crawler.py
# -rw-r--r-- 1 user user  XXK ... ai_modules.py
```

파일 내용 미리보기:
```bash
head -n 20 src/modules/data_crawler.py
head -n 20 src/modules/ai_modules.py
```

---

## ✅ 다음 단계

파일 복사가 완료되었으면:

1. `.env` 파일 설정
2. 의존성 패키지 설치
3. MongoDB/Redis 시작
4. 초기 데이터 크롤링 실행

자세한 내용은 `SETUP_GUIDE.md`를 참고하세요!
