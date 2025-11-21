# Windows에서 크롤링 실행 가이드

Windows에서는 `.sh` 파일(bash 스크립트)을 직접 실행할 수 없습니다. 다음 방법 중 하나를 선택하세요.

## 🎯 방법 1: PowerShell 스크립트 사용 (권장!)

### 실행 방법
```powershell
# PowerShell 열기
# 프로젝트 디렉토리로 이동
cd C:\Users\Park\Desktop\myAIProjects\CHATBOT-AI

# 스크립트 실행
.\scripts\crawl-with-backup.ps1
```

### 실행 정책 오류 시
```powershell
# 실행 정책 일시적으로 우회
PowerShell -ExecutionPolicy Bypass -File .\scripts\crawl-with-backup.ps1

# 또는 영구적으로 변경 (관리자 권한 필요)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 🐳 방법 2: Docker 명령어 직접 실행

### 간단한 크롤링 (백업 없이)
```powershell
# Docker Desktop 실행 확인
docker ps

# 크롤링 실행
docker exec -it knu-chatbot-app python src/modules/run_crawler.py
```

### 수동 백업 + 크롤링
```powershell
# 1. 백업
docker exec -it knu-chatbot-app bash -c "cd /app && ./scripts/backup-data.sh"

# 2. 크롤링
docker exec -it knu-chatbot-app python src/modules/run_crawler.py

# 3. 실패 시 복원 (백업 이름은 실제로 생성된 것 사용)
docker exec -it knu-chatbot-app bash -c "cd /app && ./scripts/restore-data.sh data-backup-20251121_143520"
```

---

## 🔧 방법 3: Git Bash 사용

Git for Windows가 설치되어 있다면:

```bash
# Git Bash 열기
# 프로젝트 디렉토리로 이동
cd /c/Users/Park/Desktop/myAIProjects/CHATBOT-AI

# bash 스크립트 실행
./scripts/crawl-with-backup.sh
```

---

## 🚨 문제 해결

### "Docker 컨테이너가 실행 중이 아닙니다"
```powershell
# Docker Desktop 실행
# 그 후 컨테이너 시작
docker compose up -d

# 또는 프로덕션 설정 사용
docker compose -f docker-compose.prod.yml up -d
```

### "Access is denied" 오류
```powershell
# 관리자 권한으로 PowerShell 실행
# 또는 Docker 명령어 직접 사용
docker exec -it knu-chatbot-app python src/modules/run_crawler.py
```

### Python으로 .sh 파일 실행하려고 하면?
```powershell
# ❌ 잘못된 방법
python .\scripts\crawl-with-backup.sh

# ✅ 올바른 방법 1 (PowerShell 스크립트)
.\scripts\crawl-with-backup.ps1

# ✅ 올바른 방법 2 (Docker 명령어)
docker exec -it knu-chatbot-app python src/modules/run_crawler.py

# ✅ 올바른 방법 3 (Git Bash)
bash ./scripts/crawl-with-backup.sh
```

---

## 📊 로그 확인

### Docker 로그 보기
```powershell
# 실시간 로그
docker logs -f knu-chatbot-app

# 마지막 100줄
docker logs knu-chatbot-app --tail 100
```

---

## 💾 데이터 백업 확인

### 백업 목록 확인
```powershell
# PowerShell
Get-ChildItem .\data-backups\ | Sort-Object LastWriteTime -Descending

# 또는 Docker 내부에서
docker exec -it knu-chatbot-app bash -c "ls -lht /app/data-backups/"
```

### 백업 크기 확인
```powershell
Get-ChildItem .\data-backups\ | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB
    "$($_.Name): $([math]::Round($size, 2)) GB"
}
```

---

## 🎯 추천 워크플로우

### 로컬 Windows에서 크롤링 → EC2 동기화

```powershell
# 1. Windows에서 크롤링
.\scripts\crawl-with-backup.ps1

# 2. EC2로 데이터 복사 (WSL 또는 Git Bash에서)
# PowerShell에서는 scp 대신 WinSCP 또는 FileZilla 사용 권장

# Git Bash 열기:
cd /c/Users/Park/Desktop/myAIProjects/CHATBOT-AI
rsync -avz --progress \
  -e "ssh -i ~/.ssh/aws-key.pem" \
  ./data/ \
  ubuntu@your-ec2-ip:/opt/knu-chatbot/CHATBOT-AI/data/
```

---

## 📝 참고

- Windows에서는 bash 스크립트(`.sh`)가 직접 실행되지 않음
- PowerShell 스크립트(`.ps1`) 또는 Docker 명령어 사용
- Git Bash 설치 시 bash 스크립트 실행 가능
- 로컬 크롤링 후 EC2 동기화로 API 비용 절감 가능
