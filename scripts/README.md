# 데이터 백업 & 크롤링 스크립트

크롤링 중 오류 발생 시 데이터 손실을 방지하기 위한 백업/복원 스크립트입니다.

## 📋 스크립트 목록

### 1. `crawl-with-backup.sh` (권장!)
**백업 → 크롤링 → 복원을 자동으로 처리**

```bash
./scripts/crawl-with-backup.sh
```

**동작 순서:**
1. 현재 데이터를 자동 백업
2. 크롤링 실행
3. 성공: 백업 유지
4. 실패: 백업에서 복원할지 선택

**장점:**
- 크롤링 실패해도 데이터 안전
- API 비용 낭비 방지
- 한 번의 명령으로 모든 작업 완료

---

### 2. `backup-data.sh`
**현재 데이터 백업만 수행**

```bash
./scripts/backup-data.sh
```

**용도:**
- 크롤링 전 수동 백업
- 중요한 작업 전 안전장치
- 정기 백업 스케줄링

**백업 위치:** `data-backups/data-backup-YYYYMMDD_HHMMSS/`

---

### 3. `restore-data.sh`
**백업에서 데이터 복원**

```bash
# 사용 가능한 백업 목록 보기
./scripts/restore-data.sh

# 특정 백업에서 복원
./scripts/restore-data.sh data-backup-20251121_120000
```

**주의사항:**
- Docker를 먼저 중지해야 함
- 현재 데이터는 임시 백업됨 (복원 실패 대비)
- **중요:** MongoDB만 복원되며, Pinecone은 별도 정리 필요

---

### 4. `cleanup-pinecone-sync.py` & `cleanup-pinecone.sh`
**Pinecone-MongoDB 동기화 정리**

크롤링 실패 후 복원 시 Pinecone에 남아있는 벡터를 정리합니다.

```bash
# 불일치 항목만 확인 (삭제 없음)
./scripts/cleanup-pinecone.sh --dry-run

# 실제 정리 수행
./scripts/cleanup-pinecone.sh
```

**동작 원리:**
1. MongoDB 문서 URL 목록 가져오기
2. Pinecone 벡터 metadata에서 URL 가져오기
3. Pinecone에만 있고 MongoDB에 없는 벡터 삭제

**언제 사용?**
- 크롤링 실패 후 MongoDB 복원했을 때
- "문서를 찾을 수 없습니다" 에러가 발생할 때
- MongoDB-Pinecone 불일치가 의심될 때

---

## 🎯 사용 시나리오

### 시나리오 1: 안전하게 크롤링하기
```bash
# 전체 과정 자동화 (권장)
./scripts/crawl-with-backup.sh

# 실패 시 자동으로:
#   1. MongoDB 복원 여부 선택
#   2. Pinecone 정리 안내
#   3. 검증 방법 안내
```

### 시나리오 2: 수동 백업 → 크롤링
```bash
# 1. 백업
./scripts/backup-data.sh

# 2. 크롤링
docker exec -it knu-chatbot-app python src/modules/run_crawler.py

# 3. 실패 시 복원
./scripts/restore-data.sh data-backup-20251121_120000

# 4. Pinecone 정리 (필요시)
./scripts/cleanup-pinecone.sh --dry-run  # 먼저 확인
./scripts/cleanup-pinecone.sh            # 실제 정리
```

### 시나리오 3: 로컬 → EC2 데이터 동기화
```bash
# 로컬에서 크롤링 (API 비용 1회만)
./scripts/crawl-with-backup.sh

# EC2로 데이터 복사
rsync -avz --progress \
  -e "ssh -i ~/.ssh/aws-key.pem" \
  ./data/ \
  ubuntu@your-ec2-ip:/opt/knu-chatbot/CHATBOT-AI/data/

# EC2에서 재시작
ssh -i ~/.ssh/aws-key.pem ubuntu@your-ec2-ip
cd /opt/knu-chatbot/CHATBOT-AI
docker compose -f docker-compose.prod.yml down
sudo chown -R 999:999 data
docker compose -f docker-compose.prod.yml up -d
```

---

## 🔧 백업 관리

### 자동 정리
- 7일 이상 된 백업은 자동 삭제됨
- `backup-data.sh` 실행 시마다 정리

### 수동 정리
```bash
# 백업 목록 확인
ls -lht data-backups/

# 특정 백업 삭제
rm -rf data-backups/data-backup-20251120_100000
```

### 백업 크기 확인
```bash
du -sh data-backups/*
```

---

## ⚠️ 주의사항

1. **Docker 중지 필수**
   - 복원 시 반드시 Docker 중지
   - 실행 중 복원하면 DB 손상 위험

2. **권한 문제**
   - EC2에서는 `sudo chown -R 999:999 data`로 권한 설정

3. **디스크 공간**
   - 백업은 data 전체를 복사
   - 디스크 공간 충분한지 확인

4. **Pinecone 동기화**
   - Pinecone은 클라우드 서비스
   - 백업/복원은 MongoDB/Redis만 해당
   - 로컬 ↔ EC2 동기화 시 Pinecone API Key 동일해야 함

---

## 💡 팁

### cron으로 정기 백업
```bash
# crontab -e
# 매일 새벽 2시에 백업
0 2 * * * cd /path/to/CHATBOT-AI && ./scripts/backup-data.sh
```

### Git에서 백업 제외
```bash
# .gitignore에 이미 추가됨
data-backups/
```

---

## 🆘 문제 해결

### "Permission denied" 오류
```bash
# 스크립트 실행 권한 부여
chmod +x scripts/*.sh
```

### Docker 컨테이너 없음
```bash
# Docker 시작
docker compose up -d
```

### 백업이 너무 큼
```bash
# Redis dump 파일만 백업하고 AOF 제외
# (scripts/backup-data.sh 수정 필요)
```
