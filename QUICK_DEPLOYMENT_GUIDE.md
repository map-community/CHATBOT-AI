# ⚡ 빠른 배포 가이드

이미 AWS_CICD_COMPLETE_GUIDE.md를 읽고 설정을 완료한 사람을 위한 빠른 참고 가이드입니다.

## 📋 체크리스트

### AWS EC2 서버 준비됨?
- [ ] EC2 인스턴스 실행 중
- [ ] 보안 그룹: 22, 80, 5000 포트 열림
- [ ] Docker 설치됨
- [ ] `/opt/knu-chatbot/.env` 파일 생성됨

### GitHub Secrets 설정됨?
- [ ] `AWS_EC2_HOST` (서버 IP)
- [ ] `AWS_EC2_USERNAME` (ubuntu)
- [ ] `AWS_EC2_SSH_KEY` (키 파일 전체 내용)
- [ ] `UPSTAGE_API_KEY`
- [ ] `PINECONE_API_KEY`
- [ ] `PINECONE_INDEX_NAME`

## 🚀 자동 배포 (GitHub Actions)

```bash
# 코드 수정 후
git add .
git commit -m "feat: 새 기능 추가"
git push origin main

# GitHub Actions가 자동으로 배포 시작!
# https://github.com/YOUR_USERNAME/CHATBOT-AI/actions 에서 진행상황 확인
```

## 🔧 수동 배포 (EC2 서버에서)

### SSH 접속
```bash
ssh -i ~/path/to/knu-chatbot-key.pem ubuntu@YOUR_SERVER_IP
```

### 배포 스크립트 실행
```bash
cd /opt/knu-chatbot/CHATBOT-AI
./scripts/deploy-manual.sh
```

## 📊 서버 상태 확인

```bash
# 전체 상태 확인
./scripts/server-status.sh

# 컨테이너 상태
docker-compose ps

# 헬스체크
curl http://localhost:5000/health
```

## 📋 로그 확인

```bash
# 모든 로그 (실시간)
./scripts/view-logs.sh

# Flask 앱 로그만
./scripts/view-logs.sh app

# MongoDB 로그만
./scripts/view-logs.sh mongodb

# Redis 로그만
./scripts/view-logs.sh redis
```

## 🛠️ 유용한 명령어

### 컨테이너 관리
```bash
# 컨테이너 재시작
docker-compose restart

# 컨테이너 중지
docker-compose down

# 컨테이너 시작
docker-compose up -d

# 특정 컨테이너 재시작
docker-compose restart app
```

### 로그 확인 (단발성)
```bash
# 전체 로그 (마지막 100줄)
docker-compose logs --tail 100

# Flask 앱 로그
docker logs knu-chatbot-app --tail 50

# 실시간 로그
docker logs -f knu-chatbot-app
```

### 디버깅
```bash
# 컨테이너 내부 접속
docker exec -it knu-chatbot-app bash

# 환경변수 확인
docker exec knu-chatbot-app env | grep -E "UPSTAGE|PINECONE|MONGODB|REDIS"

# 네트워크 확인
docker network ls
docker network inspect chatbot-ai_chatbot-network
```

### 디스크 정리
```bash
# 사용하지 않는 이미지 삭제
docker image prune -a

# 사용하지 않는 볼륨 삭제
docker volume prune

# 전체 정리 (주의!)
docker system prune -a --volumes
```

## 🔥 문제 해결

### 컨테이너가 계속 재시작됨
```bash
# 로그 확인
docker logs knu-chatbot-app --tail 100

# .env 파일 확인
cat .env

# 컨테이너 재빌드
docker-compose build --no-cache
docker-compose up -d
```

### 포트 5000 접속 안 됨
```bash
# 컨테이너 실행 확인
docker ps | grep knu-chatbot-app

# 포트 바인딩 확인
docker port knu-chatbot-app

# 방화벽 확인
sudo ufw status
```

### MongoDB 연결 안 됨
```bash
# MongoDB 컨테이너 확인
docker logs knu-chatbot-mongodb --tail 50

# 네트워크 연결 확인
docker exec knu-chatbot-app ping mongodb -c 3
```

### 디스크 공간 부족
```bash
# 디스크 사용량 확인
df -h

# Docker 디스크 사용량
docker system df

# 정리
docker system prune -a
```

## 🌐 외부 접속 테스트

### 로컬에서 서버 테스트
```bash
# 헬스체크
curl http://YOUR_SERVER_IP:5000/health

# API 테스트
curl -X POST http://YOUR_SERVER_IP:5000/ai/ai-response \
  -H "Content-Type: application/json" \
  -d '{"question": "안녕하세요"}'
```

## 📞 도움말

### GitHub Actions 로그 확인
```
https://github.com/YOUR_USERNAME/CHATBOT-AI/actions
```

### AWS EC2 콘솔
```
https://console.aws.amazon.com/ec2/
```

### 문제 발생 시
1. GitHub Actions 로그 확인
2. EC2 서버 로그 확인 (`./scripts/view-logs.sh`)
3. 서버 상태 확인 (`./scripts/server-status.sh`)
4. 이슈 등록: https://github.com/YOUR_USERNAME/CHATBOT-AI/issues

---

**참고**: 더 자세한 내용은 `AWS_CICD_COMPLETE_GUIDE.md`를 확인하세요.
