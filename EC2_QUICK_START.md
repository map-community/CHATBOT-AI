# EC2 빠른 시작 가이드

이 가이드는 EC2에서 최소한의 단계로 애플리케이션을 배포하는 방법을 안내합니다.

## 📌 사전 준비사항

1. **EC2 인스턴스**: Ubuntu 22.04 LTS
   - 권장: **t3.large (8GB RAM)** - 안정적 운영
   - 최소: t3.medium (4GB RAM) + Swap 2GB - 개발/테스트용
2. **보안 그룹**: 22(SSH), 80(HTTP), 443(HTTPS) 포트 열기
3. **도메인** (선택사항): HTTPS 사용 시 필요

> 📊 **왜 t3.large?** 실제 코드 분석 결과 BGE-Reranker 모델(1.2GB) + MongoDB/Redis + Flask 등 총 4-7.5GB 메모리 필요. 상세한 분석은 [EC2_DEPLOYMENT_GUIDE.md](EC2_DEPLOYMENT_GUIDE.md) 참고.

---

## 🚀 5분 안에 배포하기

### 1단계: EC2 접속 및 초기 설정

```bash
# EC2 인스턴스 접속
ssh -i your-key.pem ubuntu@your-ec2-ip

# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 타임존 설정
sudo timedatectl set-timezone Asia/Seoul
```

### 2단계: Docker 설치

```bash
# Docker 설치 스크립트 다운로드 및 실행
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker 권한 설정
sudo usermod -aG docker $USER
newgrp docker

# 설치 확인
docker --version
docker compose version
```

### 3단계: 애플리케이션 배포

```bash
# 프로젝트 디렉토리 생성 및 이동
sudo mkdir -p /opt/knu-chatbot
sudo chown $USER:$USER /opt/knu-chatbot
cd /opt/knu-chatbot

# Git 클론
git clone https://github.com/map-community/CHATBOT-AI.git .

# 환경 변수 설정
cp .env.production.example .env
vim .env  # API 키 입력 (PINECONE_API_KEY, UPSTAGE_API_KEY)

# 환경 변수 파일 권한 설정 (보안)
chmod 600 .env

# 데이터 디렉토리 생성
mkdir -p data/mongodb data/redis logs
```

### 4단계: 애플리케이션 실행

```bash
# Docker Compose로 실행
docker compose -f docker-compose.prod.yml up -d --build

# 로그 확인
docker compose -f docker-compose.prod.yml logs -f
```

### 5단계: 동작 확인

```bash
# 헬스 체크
curl http://localhost:5000/health

# 컨테이너 상태 확인
docker compose -f docker-compose.prod.yml ps
```

✅ **배포 완료!** 이제 `http://your-ec2-ip:5000`으로 접속할 수 있습니다.

---

## 🔧 선택사항: 추가 설정

### systemd 서비스 등록 (자동 시작)

```bash
# systemd 서비스 파일 복사
sudo cp /opt/knu-chatbot/scripts/knu-chatbot.service /etc/systemd/system/

# 서비스 파일 수정 (사용자명 확인)
sudo vim /etc/systemd/system/knu-chatbot.service
# User=ubuntu 부분을 현재 사용자명으로 변경

# 서비스 활성화 및 시작
sudo systemctl daemon-reload
sudo systemctl enable knu-chatbot
sudo systemctl start knu-chatbot

# 서비스 상태 확인
sudo systemctl status knu-chatbot
```

### Nginx 리버스 프록시 설정

```bash
# Nginx 설치
sudo apt install -y nginx

# 설정 파일 복사
sudo cp /opt/knu-chatbot/nginx/knu-chatbot.conf /etc/nginx/sites-available/

# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/knu-chatbot.conf /etc/nginx/sites-enabled/

# 기본 사이트 비활성화
sudo rm /etc/nginx/sites-enabled/default

# Nginx 테스트 및 재시작
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

# 방화벽 설정 (5000번 포트 닫기)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

이제 `http://your-ec2-ip`로 접근 가능합니다 (포트 번호 없이).

### 자동 백업 설정

```bash
# 백업 스크립트 권한 설정
chmod +x /opt/knu-chatbot/scripts/backup-mongodb.sh

# Cron 설정 (매일 새벽 2시 백업)
crontab -e

# 다음 라인 추가:
0 2 * * * /opt/knu-chatbot/scripts/backup-mongodb.sh >> /opt/knu-chatbot/logs/backup.log 2>&1
```

### SSL 인증서 설정 (HTTPS)

```bash
# Certbot 설치
sudo apt install -y certbot python3-certbot-nginx

# 인증서 발급 (도메인이 있는 경우)
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 자동 갱신 테스트
sudo certbot renew --dry-run
```

---

## 📊 유용한 명령어

### 애플리케이션 관리

```bash
# 로그 확인
docker compose -f docker-compose.prod.yml logs -f app

# 컨테이너 재시작
docker compose -f docker-compose.prod.yml restart

# 컨테이너 중지
docker compose -f docker-compose.prod.yml down

# 컨테이너 시작
docker compose -f docker-compose.prod.yml up -d

# 컨테이너 상태
docker compose -f docker-compose.prod.yml ps
```

### 업데이트 배포

```bash
cd /opt/knu-chatbot
git pull origin main
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

또는 자동화 스크립트 사용:

```bash
/opt/knu-chatbot/scripts/deploy.sh
```

### 데이터베이스 접근

```bash
# MongoDB 접속
docker exec -it knu-chatbot-mongodb mongosh

# Redis 접속
docker exec -it knu-chatbot-redis redis-cli
```

### 리소스 모니터링

```bash
# Docker 컨테이너 리소스
docker stats

# 시스템 리소스
htop

# 디스크 사용량
df -h

# 로그 크기
du -sh /opt/knu-chatbot/logs
```

---

## 🔍 문제 해결

### 컨테이너가 시작되지 않을 때

```bash
# 로그 확인
docker compose -f docker-compose.prod.yml logs

# 컨테이너 상태 확인
docker ps -a

# 리소스 정리 후 재시작
docker system prune -f
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```

### 메모리 부족 에러

```bash
# Swap 메모리 추가
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 포트가 이미 사용 중일 때

```bash
# 포트 사용 프로세스 확인
sudo lsof -i :5000
sudo lsof -i :27017
sudo lsof -i :6379

# 프로세스 종료 (PID는 위 명령어로 확인)
sudo kill -9 <PID>
```

---

## 📚 더 자세한 정보

상세한 설정 및 고급 기능은 다음 문서를 참고하세요:

- **[EC2_DEPLOYMENT_GUIDE.md](EC2_DEPLOYMENT_GUIDE.md)**: 전체 배포 가이드
- **[docker-compose.prod.yml](docker-compose.prod.yml)**: 프로덕션 Docker Compose 설정
- **[.env.production.example](.env.production.example)**: 환경 변수 예제

---

## 💡 팁

1. **정기 백업**: 매일 자동 백업을 설정하세요
2. **모니터링**: CloudWatch나 Datadog 등으로 리소스 모니터링
3. **로그 관리**: 로그 로테이션을 설정하여 디스크 공간 관리
4. **보안**: MongoDB/Redis 비밀번호 설정, 방화벽 설정
5. **성능**: 트래픽에 따라 인스턴스 타입 조정

---

## 🆘 도움이 필요하신가요?

- **이슈 리포트**: GitHub Issues에 문제를 보고해주세요
- **문서**: [전체 배포 가이드](EC2_DEPLOYMENT_GUIDE.md) 참고
- **로그**: `/opt/knu-chatbot/logs` 디렉토리의 로그 파일 확인
