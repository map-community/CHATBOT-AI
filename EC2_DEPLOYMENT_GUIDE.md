# EC2 프로덕션 환경 배포 가이드

## 📋 목차
1. [EC2 인스턴스 사양 권장사항](#ec2-인스턴스-사양-권장사항)
2. [초기 서버 설정](#초기-서버-설정)
3. [Docker & Docker Compose 설치](#docker--docker-compose-설치)
4. [애플리케이션 배포](#애플리케이션-배포)
5. [프로덕션 환경 설정](#프로덕션-환경-설정)
6. [모니터링 및 로깅](#모니터링-및-로깅)
7. [백업 전략](#백업-전략)
8. [보안 설정](#보안-설정)
9. [문제 해결](#문제-해결)

---

## EC2 인스턴스 사양 권장사항

### 최소 사양
- **인스턴스 타입**: t3.medium (2 vCPU, 4GB RAM)
- **스토리지**: 30GB gp3 EBS
- **운영체제**: Ubuntu 22.04 LTS

### 권장 사양 (프로덕션)
- **인스턴스 타입**: t3.large (2 vCPU, 8GB RAM) 또는 c5.large
- **스토리지**: 50GB gp3 EBS
- **운영체제**: Ubuntu 22.04 LTS
- **추가 볼륨**: MongoDB/Redis 데이터용 별도 EBS 볼륨 (20GB+)

### 서비스별 메모리 사용량 예상
- MongoDB: 1-2GB
- Redis: 500MB-1GB
- Flask App (ML 모델 포함): 2-3GB
- 시스템 오버헤드: 500MB-1GB

---

## 초기 서버 설정

### 1. SSH 접속 및 기본 설정

```bash
# EC2 인스턴스 접속
ssh -i your-key.pem ubuntu@your-ec2-ip

# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 타임존 설정 (한국 시간)
sudo timedatectl set-timezone Asia/Seoul

# 필수 패키지 설치
sudo apt install -y curl git vim htop net-tools
```

### 2. swap 메모리 설정 (메모리 부족 방지)

```bash
# 2GB swap 파일 생성
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 영구 설정
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# swap 확인
free -h
```

### 3. 방화벽 설정

```bash
# UFW 방화벽 활성화
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 5000/tcp  # Flask (임시, 나중에 nginx로 리버스 프록시 설정 시 제거)
sudo ufw enable
sudo ufw status
```

---

## Docker & Docker Compose 설치

### Docker 설치

```bash
# Docker 공식 GPG 키 추가
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Docker 레포지토리 추가
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker 설치
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER
newgrp docker

# Docker 설치 확인
docker --version
docker compose version
```

### Docker 서비스 자동 시작 설정

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

---

## 애플리케이션 배포

### 1. 코드 배포

```bash
# 애플리케이션 디렉토리 생성
sudo mkdir -p /opt/knu-chatbot
sudo chown $USER:$USER /opt/knu-chatbot
cd /opt/knu-chatbot

# Git 클론
git clone https://github.com/map-community/CHATBOT-AI.git .

# 또는 코드를 직접 업로드하는 경우
# scp -i your-key.pem -r ./CHATBOT-AI ubuntu@your-ec2-ip:/opt/knu-chatbot/
```

### 2. 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env
vim .env
```

**프로덕션 .env 설정:**
```env
# Pinecone Configuration
PINECONE_API_KEY=your_actual_pinecone_api_key
PINECONE_INDEX_NAME=info

# Upstage Configuration
UPSTAGE_API_KEY=your_actual_upstage_api_key

# MongoDB Configuration
MONGODB_URI=mongodb://mongodb:27017/
MONGODB_DATABASE=knu_chatbot
MONGODB_COLLECTION=notice_collection

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Flask Configuration
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=False
FLASK_ENV=production
```

### 3. 데이터 디렉토리 설정

```bash
# 데이터 영속성을 위한 디렉토리 생성
mkdir -p /opt/knu-chatbot/data/mongodb
mkdir -p /opt/knu-chatbot/data/redis
mkdir -p /opt/knu-chatbot/logs

# 권한 설정
chmod -R 755 /opt/knu-chatbot/data
chmod -R 755 /opt/knu-chatbot/logs
```

---

## 프로덕션 환경 설정

### 1. 프로덕션용 Docker Compose 사용

프로젝트에 `docker-compose.prod.yml` 파일이 생성되어 있습니다. 이 파일을 사용하여 배포합니다.

```bash
# 프로덕션 환경으로 빌드 및 실행
docker compose -f docker-compose.prod.yml up -d --build

# 로그 확인
docker compose -f docker-compose.prod.yml logs -f

# 상태 확인
docker compose -f docker-compose.prod.yml ps
```

### 2. systemd 서비스 등록

애플리케이션을 시스템 서비스로 등록하여 자동 시작 및 재시작을 보장합니다.

```bash
# systemd 서비스 파일 복사
sudo cp /opt/knu-chatbot/scripts/knu-chatbot.service /etc/systemd/system/

# 서비스 활성화
sudo systemctl daemon-reload
sudo systemctl enable knu-chatbot
sudo systemctl start knu-chatbot

# 서비스 상태 확인
sudo systemctl status knu-chatbot
```

### 3. Nginx 리버스 프록시 설정 (선택사항, 권장)

```bash
# Nginx 설치
sudo apt install -y nginx

# Nginx 설정 파일 복사
sudo cp /opt/knu-chatbot/nginx/knu-chatbot.conf /etc/nginx/sites-available/

# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/knu-chatbot.conf /etc/nginx/sites-enabled/

# 기본 사이트 비활성화
sudo rm /etc/nginx/sites-enabled/default

# Nginx 테스트 및 재시작
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

이제 포트 5000 대신 80번 포트로 접근 가능합니다.

---

## 모니터링 및 로깅

### 1. Docker 로그 확인

```bash
# 전체 로그
docker compose -f docker-compose.prod.yml logs

# 특정 서비스 로그
docker compose -f docker-compose.prod.yml logs app
docker compose -f docker-compose.prod.yml logs mongodb
docker compose -f docker-compose.prod.yml logs redis

# 실시간 로그 확인
docker compose -f docker-compose.prod.yml logs -f app
```

### 2. 애플리케이션 로그

로그 파일은 `/opt/knu-chatbot/logs` 디렉토리에 저장됩니다.

```bash
# 애플리케이션 로그 확인
tail -f /opt/knu-chatbot/logs/app.log

# 로그 로테이션 설정 (선택사항)
sudo cp /opt/knu-chatbot/scripts/logrotate.conf /etc/logrotate.d/knu-chatbot
```

### 3. 리소스 모니터링

```bash
# 실시간 시스템 리소스
htop

# Docker 컨테이너 리소스 사용량
docker stats

# 디스크 사용량
df -h

# MongoDB 데이터 크기
docker exec knu-chatbot-mongodb mongosh --eval "db.stats()"
```

### 4. Health Check

```bash
# 애플리케이션 상태 확인
curl http://localhost:5000/health

# 또는 외부에서
curl http://your-ec2-ip/health
```

---

## 백업 전략

### 1. MongoDB 백업

```bash
# 백업 디렉토리 생성
mkdir -p /opt/knu-chatbot/backups/mongodb

# 수동 백업
docker exec knu-chatbot-mongodb mongodump --out /data/backup
docker cp knu-chatbot-mongodb:/data/backup /opt/knu-chatbot/backups/mongodb/$(date +%Y%m%d_%H%M%S)

# 자동 백업 스크립트 사용 (프로젝트에 포함됨)
chmod +x /opt/knu-chatbot/scripts/backup-mongodb.sh

# Cron 설정 (매일 새벽 2시 백업)
crontab -e
# 추가: 0 2 * * * /opt/knu-chatbot/scripts/backup-mongodb.sh
```

### 2. Redis 백업

Redis는 자동으로 RDB 파일을 생성하며, 데이터는 볼륨에 저장됩니다.

```bash
# Redis 데이터 백업
docker exec knu-chatbot-redis redis-cli SAVE
docker cp knu-chatbot-redis:/data/dump.rdb /opt/knu-chatbot/backups/redis/dump_$(date +%Y%m%d_%H%M%S).rdb
```

### 3. 전체 데이터 볼륨 백업

```bash
# 볼륨 데이터 백업
tar -czf /opt/knu-chatbot/backups/volumes_$(date +%Y%m%d_%H%M%S).tar.gz \
  /opt/knu-chatbot/data
```

### 4. S3 백업 (권장)

AWS S3로 백업을 자동화하면 더욱 안전합니다.

```bash
# AWS CLI 설치
sudo apt install -y awscli

# AWS 자격 증명 설정
aws configure

# S3 백업 스크립트 실행
chmod +x /opt/knu-chatbot/scripts/backup-to-s3.sh
```

---

## 보안 설정

### 1. 환경 변수 보호

```bash
# .env 파일 권한 설정
chmod 600 /opt/knu-chatbot/.env
```

### 2. MongoDB 인증 설정 (권장)

프로덕션 환경에서는 MongoDB에 인증을 추가하는 것이 좋습니다.

```bash
# MongoDB 컨테이너 접속
docker exec -it knu-chatbot-mongodb mongosh

# 관리자 계정 생성
use admin
db.createUser({
  user: "admin",
  pwd: "strong_password_here",
  roles: ["root"]
})

# 애플리케이션 DB 사용자 생성
use knu_chatbot
db.createUser({
  user: "chatbot_user",
  pwd: "another_strong_password",
  roles: ["readWrite"]
})
```

그 후 `docker-compose.prod.yml`에서 인증 정보 추가 필요.

### 3. Redis 비밀번호 설정 (권장)

`docker-compose.prod.yml`에서 Redis 비밀번호 설정이 포함되어 있습니다.

### 4. SSL/TLS 인증서 (HTTPS) 설정

Let's Encrypt를 사용한 무료 SSL 인증서 발급:

```bash
# Certbot 설치
sudo apt install -y certbot python3-certbot-nginx

# 인증서 발급 (도메인이 있는 경우)
sudo certbot --nginx -d your-domain.com

# 자동 갱신 테스트
sudo certbot renew --dry-run
```

---

## 문제 해결

### 1. 컨테이너가 시작되지 않을 때

```bash
# 컨테이너 로그 확인
docker compose -f docker-compose.prod.yml logs

# 개별 컨테이너 상태 확인
docker ps -a

# 컨테이너 재시작
docker compose -f docker-compose.prod.yml restart
```

### 2. 메모리 부족 에러

```bash
# 메모리 사용량 확인
free -h
docker stats

# 불필요한 Docker 리소스 정리
docker system prune -a
```

### 3. MongoDB 연결 실패

```bash
# MongoDB 로그 확인
docker logs knu-chatbot-mongodb

# MongoDB 연결 테스트
docker exec -it knu-chatbot-mongodb mongosh --eval "db.adminCommand('ping')"
```

### 4. Redis 연결 실패

```bash
# Redis 로그 확인
docker logs knu-chatbot-redis

# Redis 연결 테스트
docker exec -it knu-chatbot-redis redis-cli ping
```

### 5. 디스크 공간 부족

```bash
# 디스크 사용량 확인
df -h

# Docker 이미지/컨테이너 정리
docker system prune -a --volumes

# 로그 파일 정리
sudo find /opt/knu-chatbot/logs -name "*.log" -mtime +30 -delete
```

---

## 배포 명령어 요약

### 초기 배포
```bash
cd /opt/knu-chatbot
docker compose -f docker-compose.prod.yml up -d --build
```

### 업데이트 배포
```bash
cd /opt/knu-chatbot
git pull origin main
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

### 빠른 재시작
```bash
docker compose -f docker-compose.prod.yml restart
```

### 완전 재빌드
```bash
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 유용한 명령어 모음

```bash
# 전체 서비스 상태 확인
docker compose -f docker-compose.prod.yml ps

# 로그 실시간 모니터링
docker compose -f docker-compose.prod.yml logs -f

# 특정 서비스만 재시작
docker compose -f docker-compose.prod.yml restart app

# 데이터베이스 접속
docker exec -it knu-chatbot-mongodb mongosh
docker exec -it knu-chatbot-redis redis-cli

# 애플리케이션 컨테이너 쉘 접속
docker exec -it knu-chatbot-app bash
```

---

## 성능 최적화 팁

1. **MongoDB 인덱스 생성**: 자주 조회하는 필드에 인덱스 생성
2. **Redis 메모리 제한 설정**: `maxmemory` 설정으로 메모리 사용량 제한
3. **Gunicorn 워커 수 조정**: CPU 코어 수에 따라 워커 수 조정 (2 * CPU + 1)
4. **CloudWatch 모니터링**: AWS CloudWatch로 리소스 모니터링
5. **로드 밸런서**: 트래픽이 많을 경우 여러 인스턴스와 ALB 사용

---

## 추가 자료

- [AWS EC2 문서](https://docs.aws.amazon.com/ec2/)
- [Docker 문서](https://docs.docker.com/)
- [Flask 프로덕션 배포](https://flask.palletsprojects.com/en/latest/deploying/)
- [MongoDB 프로덕션 체크리스트](https://www.mongodb.com/docs/manual/administration/production-checklist-operations/)
