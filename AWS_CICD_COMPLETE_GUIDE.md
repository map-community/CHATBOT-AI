# 🚀 GitHub Actions + AWS 자동 배포 완전 가이드 (초보자용)

> **이 가이드는 완전 초보자를 위한 것입니다. 모든 단계를 상세히 설명합니다.**

## 📚 목차

1. [전체 흐름 이해하기](#1-전체-흐름-이해하기)
2. [사전 준비물](#2-사전-준비물)
3. [AWS 계정 설정](#3-aws-계정-설정)
4. [AWS EC2 서버 생성](#4-aws-ec2-서버-생성)
5. [EC2 서버 초기 설정](#5-ec2-서버-초기-설정)
6. [GitHub Secrets 설정](#6-github-secrets-설정)
7. [GitHub Actions 워크플로우 설정](#7-github-actions-워크플로우-설정)
8. [첫 배포 실행](#8-첫-배포-실행)
9. [문제 해결](#9-문제-해결)

---

## 1. 전체 흐름 이해하기

### 🎯 우리가 만들 시스템

```
로컬 개발 → GitHub Push → GitHub Actions 자동 실행 → AWS 서버에 배포
```

### 📖 각 단계 설명

#### 현재 상황 (로컬에서만 작동)
```bash
# 당신의 노트북에서만 실행
docker-compose up
# ➡️ http://localhost:5000 에서만 접속 가능
```

#### 목표 상황 (AWS 서버에서 작동)
```bash
# 1. 코드 수정
git add .
git commit -m "새 기능 추가"
git push

# 2. GitHub Actions가 자동으로:
#    - 코드 받기
#    - Docker 이미지 빌드
#    - AWS 서버에 배포
#    - 서버 재시작

# 3. 결과: http://your-server-ip:5000 에서 접속 가능!
```

### 🔑 핵심 개념 3가지

#### ① CI/CD란?
- **CI (Continuous Integration)**: 코드 변경사항을 자동으로 테스트
- **CD (Continuous Deployment)**: 테스트 통과한 코드를 자동으로 배포
- **쉽게 말하면**: "푸시하면 자동으로 서버에 올라가는 마법"

#### ② GitHub Actions란?
- GitHub에서 제공하는 무료 자동화 도구
- `.github/workflows/` 폴더에 설정 파일 작성
- 예: "main 브랜치에 푸시되면 → 이 작업들을 실행해줘"

#### ③ AWS EC2란?
- Amazon에서 빌려주는 가상 컴퓨터 (서버)
- 24시간 돌아가는 서버
- 인터넷에서 누구나 접속 가능

---

## 2. 사전 준비물

### ✅ 체크리스트

- [ ] GitHub 계정 (이미 있음)
- [ ] AWS 계정 (없으면 만들어야 함)
- [ ] 신용카드 (AWS 계정 생성 시 필요, 프리티어는 무료)
- [ ] 당신의 프로젝트 코드 (이미 있음)
- [ ] 시간 약 1-2시간

### 💰 비용 예상

#### AWS 프리티어 (12개월 무료)
- **EC2 t2.micro**: 월 750시간 무료 (하나만 돌리면 완전 무료)
- **데이터 전송**: 월 15GB 무료
- **예상 비용**: 무료 (프리티어 범위 내)

#### 프리티어 이후
- **EC2 t2.micro**: 월 약 $10 (₩13,000)
- **EC2 t3.small** (권장): 월 약 $15 (₩20,000)

---

## 3. AWS 계정 설정

### Step 1: AWS 계정 만들기

1. **AWS 홈페이지 접속**
   ```
   https://aws.amazon.com/ko/
   ```

2. **"무료 계정 만들기" 클릭**

3. **정보 입력**
   - 이메일 주소
   - 비밀번호
   - AWS 계정 이름 (예: `knu-chatbot-aws`)

4. **연락처 정보 입력**
   - 이름, 전화번호, 주소
   - **계정 유형**: "개인" 선택

5. **결제 정보 입력**
   - 신용카드 정보 입력
   - **걱정 마세요**: 프리티어 범위 내에서는 무료입니다
   - 카드에서 $1 정도 인증 후 환불됩니다

6. **본인 확인**
   - 전화번호로 인증코드 받기
   - 인증코드 입력

7. **지원 플랜 선택**
   - **"기본 지원 - 무료"** 선택 ✅

8. **완료!** ✅
   - AWS Management Console 로그인 가능

### Step 2: AWS CLI 설치 (로컬 컴퓨터)

**나중에 필요하면 설치하세요. 지금은 스킵 가능합니다.**

---

## 4. AWS EC2 서버 생성

### Step 1: EC2 대시보드 접속

1. **AWS Management Console 로그인**
   ```
   https://console.aws.amazon.com/
   ```

2. **서비스 → EC2 클릭**
   - 상단 검색창에 "EC2" 입력 → 클릭

3. **리전 확인**
   - 우측 상단에서 리전 확인
   - **서울 리전** 선택: `ap-northeast-2`
   - ⚠️ **중요**: 계속 같은 리전을 사용해야 합니다!

### Step 2: EC2 인스턴스 시작

1. **"인스턴스 시작" 버튼 클릭**

2. **이름 및 태그 설정**
   ```
   이름: knu-chatbot-server
   ```

3. **애플리케이션 및 OS 이미지 선택**
   - **Ubuntu Server 22.04 LTS** 선택 ✅
   - 프리 티어 사용 가능 확인 ✅

4. **인스턴스 유형 선택**
   - **t2.micro** 선택 (프리티어 무료) ✅
   - RAM: 1GB, vCPU: 1개
   - **참고**: 나중에 성능이 부족하면 t3.small로 업그레이드

5. **키 페어 생성 (중요!)**
   - "새 키 페어 생성" 클릭
   - **키 페어 이름**: `knu-chatbot-key`
   - **키 페어 유형**: RSA
   - **프라이빗 키 파일 형식**:
     - Windows: `.ppk` 선택
     - Mac/Linux: `.pem` 선택
   - "키 페어 생성" 클릭
   - **⚠️ 중요**: 다운로드된 파일을 안전한 곳에 보관!
     ```
     예: ~/Downloads/knu-chatbot-key.pem
     ```
   - **절대 잃어버리면 안 됩니다!** 이 파일이 서버 접속 열쇠입니다.

6. **네트워크 설정**
   - "편집" 클릭
   - **보안 그룹 이름**: `knu-chatbot-sg`
   - **보안 그룹 규칙** (중요!):

     | 유형 | 프로토콜 | 포트 범위 | 소스 | 설명 |
     |------|----------|----------|------|------|
     | SSH | TCP | 22 | 내 IP | SSH 접속 (자동 설정됨) |
     | HTTP | TCP | 80 | 0.0.0.0/0 | HTTP 접속 |
     | 사용자 지정 TCP | TCP | 5000 | 0.0.0.0/0 | Flask 앱 |
     | 사용자 지정 TCP | TCP | 27017 | 내 IP | MongoDB (선택) |
     | 사용자 지정 TCP | TCP | 6379 | 내 IP | Redis (선택) |

   - "보안 그룹 규칙 추가" 버튼으로 각각 추가

7. **스토리지 구성**
   - **크기**: 30 GiB (프리티어 최대)
   - **볼륨 유형**: gp3 (General Purpose SSD)

8. **고급 세부 정보** (선택사항, 스킵 가능)
   - 기본값 유지

9. **인스턴스 시작 클릭** 🚀

### Step 3: 인스턴스 확인

1. **인스턴스 페이지에서 확인**
   - 상태: "실행 중" ✅
   - 인스턴스 ID: `i-xxxxxxxxxxxxx`
   - 퍼블릭 IPv4 주소: `xx.xx.xx.xx` ← **이걸 기억하세요!**

2. **인스턴스 선택 → 연결 버튼 클릭**
   - 나중에 SSH 접속할 때 필요한 정보 확인

---

## 5. EC2 서버 초기 설정

### Step 1: SSH로 서버 접속

#### Mac/Linux 사용자

```bash
# 1. 키 파일 권한 설정 (필수!)
chmod 400 ~/Downloads/knu-chatbot-key.pem

# 2. SSH 접속
ssh -i ~/Downloads/knu-chatbot-key.pem ubuntu@YOUR_SERVER_IP

# YOUR_SERVER_IP를 실제 IP로 바꾸세요
# 예: ssh -i ~/Downloads/knu-chatbot-key.pem ubuntu@13.125.123.45
```

#### Windows 사용자 (PowerShell)

```powershell
# SSH 접속
ssh -i C:\Users\YourName\Downloads\knu-chatbot-key.pem ubuntu@YOUR_SERVER_IP
```

**또는 PuTTY 사용** (Windows):
1. PuTTY 다운로드: https://www.putty.org/
2. PuTTYgen으로 .ppk 파일 로드
3. PuTTY에서 `ubuntu@YOUR_SERVER_IP` 입력
4. Auth → Private key 에 .ppk 파일 선택
5. Open 클릭

### Step 2: 서버 패키지 업데이트

```bash
# 시스템 업데이트
sudo apt-get update
sudo apt-get upgrade -y

# 필수 패키지 설치
sudo apt-get install -y \
    curl \
    wget \
    git \
    vim \
    ca-certificates \
    gnupg \
    lsb-release
```

### Step 3: Docker 설치

```bash
# 1. Docker 공식 GPG 키 추가
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 2. Docker 저장소 추가
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 3. Docker 설치
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4. Docker 버전 확인
docker --version
# 출력 예: Docker version 24.0.7, build afdd53b

# 5. Docker Compose 버전 확인
docker compose version
# 출력 예: Docker Compose version v2.23.0

# 6. 현재 사용자를 docker 그룹에 추가 (sudo 없이 docker 사용)
sudo usermod -aG docker ubuntu

# 7. 변경사항 적용을 위해 재접속 필요
exit
# 다시 SSH 접속
```

### Step 4: GitHub Actions 배포용 디렉토리 생성

```bash
# 앱 디렉토리 생성
sudo mkdir -p /opt/knu-chatbot
sudo chown ubuntu:ubuntu /opt/knu-chatbot

# 로그 디렉토리 생성
mkdir -p /opt/knu-chatbot/logs
```

### Step 5: 환경변수 파일 생성

```bash
# .env 파일 생성
cd /opt/knu-chatbot
vim .env
```

**vim 에디터 사용법**:
- `i` 키 누르기 → 입력 모드
- 아래 내용 복사해서 붙여넣기
- `ESC` 키 누르기 → 명령 모드
- `:wq` 입력 후 Enter → 저장하고 나가기

**.env 파일 내용** (실제 값으로 바꾸세요!):
```bash
# Upstage API
UPSTAGE_API_KEY=your_upstage_api_key_here

# Pinecone
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX_NAME=info

# MongoDB (Docker Compose 내부)
MONGODB_URI=mongodb://mongodb:27017/

# Redis (Docker Compose 내부)
REDIS_HOST=redis
REDIS_PORT=6379

# Flask
FLASK_ENV=production
```

**파일 권한 설정** (보안):
```bash
chmod 600 .env
```

### Step 6: 방화벽 설정 (UFW)

```bash
# UFW 활성화
sudo ufw enable

# SSH 허용 (22번 포트)
sudo ufw allow 22/tcp

# HTTP 허용 (80번 포트)
sudo ufw allow 80/tcp

# Flask 앱 허용 (5000번 포트)
sudo ufw allow 5000/tcp

# 상태 확인
sudo ufw status
```

---

## 6. GitHub Secrets 설정

GitHub Secrets는 AWS 접속 정보 같은 민감한 데이터를 안전하게 저장하는 곳입니다.

### Step 1: GitHub Repository로 이동

```
https://github.com/YOUR_USERNAME/CHATBOT-AI
```

### Step 2: Settings → Secrets and variables → Actions

1. Repository 페이지에서 **Settings** 클릭
2. 왼쪽 메뉴에서 **Secrets and variables** → **Actions** 클릭
3. **New repository secret** 버튼 클릭

### Step 3: Secrets 추가

아래 Secrets를 하나씩 추가하세요:

#### ① AWS_EC2_HOST
```
Name: AWS_EC2_HOST
Secret: YOUR_SERVER_IP
```
예: `13.125.123.45`

#### ② AWS_EC2_USERNAME
```
Name: AWS_EC2_USERNAME
Secret: ubuntu
```

#### ③ AWS_EC2_SSH_KEY
```
Name: AWS_EC2_SSH_KEY
Secret: (키 파일 전체 내용)
```

**키 파일 내용 복사 방법** (Mac/Linux):
```bash
cat ~/Downloads/knu-chatbot-key.pem
```

출력된 내용 **전체**를 복사 (-----BEGIN부터 -----END까지)
```
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
...
-----END RSA PRIVATE KEY-----
```

#### ④ UPSTAGE_API_KEY
```
Name: UPSTAGE_API_KEY
Secret: your_actual_upstage_api_key
```

#### ⑤ PINECONE_API_KEY
```
Name: PINECONE_API_KEY
Secret: your_actual_pinecone_api_key
```

#### ⑥ PINECONE_INDEX_NAME
```
Name: PINECONE_INDEX_NAME
Secret: info
```

### Step 4: Secrets 확인

- 6개 Secrets가 모두 등록되었는지 확인
- Secret 값은 보안상 표시되지 않습니다 (정상)

---

## 7. GitHub Actions 워크플로우 설정

이제 자동 배포 스크립트를 작성합니다.

### Step 1: 워크플로우 파일 생성

로컬 프로젝트에서:

```bash
# .github/workflows 디렉토리 생성
mkdir -p .github/workflows
```

### Step 2: 배포 워크플로우 파일 작성

`.github/workflows/deploy.yml` 파일이 자동으로 생성될 예정입니다.

---

## 8. 첫 배포 실행

### Step 1: 변경사항 커밋 & 푸시

```bash
git add .
git commit -m "feat: Add GitHub Actions CI/CD workflow"
git push origin main
```

### Step 2: GitHub Actions 확인

1. GitHub Repository → **Actions** 탭 클릭
2. 워크플로우 실행 확인
3. 진행 상황 실시간 확인

### Step 3: 배포 성공 확인

1. **로그 확인**
   ```
   ✅ Checkout code
   ✅ Deploy to EC2
   ✅ Deployment successful
   ```

2. **서버 접속해서 확인**
   ```bash
   ssh -i ~/Downloads/knu-chatbot-key.pem ubuntu@YOUR_SERVER_IP

   # Docker 컨테이너 확인
   docker ps

   # 로그 확인
   docker logs knu-chatbot-app
   ```

3. **브라우저에서 확인**
   ```
   http://YOUR_SERVER_IP:5000/health
   ```

   응답 예:
   ```json
   {
     "status": "healthy",
     "message": "KNU Chatbot Server is running",
     "version": "1.0.0"
   }
   ```

---

## 9. 문제 해결

### ❌ 문제 1: SSH 접속 안 됨

**증상**:
```
Permission denied (publickey)
```

**해결**:
```bash
# 1. 키 파일 권한 확인
chmod 400 ~/Downloads/knu-chatbot-key.pem

# 2. EC2 보안 그룹에서 SSH (22번 포트) 허용 확인
# 3. 올바른 IP 주소 사용 확인
```

### ❌ 문제 2: Docker 컨테이너 실행 안 됨

**증상**:
```
Container exited with code 1
```

**해결**:
```bash
# 1. 로그 확인
docker logs knu-chatbot-app

# 2. .env 파일 확인
cat /opt/knu-chatbot/.env

# 3. 환경변수 누락 확인
# 4. 컨테이너 재시작
docker-compose restart
```

### ❌ 문제 3: 포트 5000 접속 안 됨

**증상**:
```
Connection refused
```

**해결**:
```bash
# 1. 컨테이너 실행 확인
docker ps | grep knu-chatbot-app

# 2. 포트 바인딩 확인
docker port knu-chatbot-app

# 3. EC2 보안 그룹에서 5000번 포트 허용 확인
# 4. UFW 방화벽 확인
sudo ufw status
```

### ❌ 문제 4: GitHub Actions 실패

**증상**:
```
Error: Process completed with exit code 1
```

**해결**:
1. Actions 탭에서 실패한 워크플로우 클릭
2. 에러 메시지 확인
3. GitHub Secrets 올바르게 설정했는지 확인
4. SSH 키 전체 내용 복사했는지 확인

---

## 🎉 축하합니다!

이제 당신의 챗봇이 AWS 서버에서 24시간 돌아갑니다!

### 다음 단계

- [ ] 도메인 연결 (선택)
- [ ] HTTPS 설정 (Let's Encrypt)
- [ ] Nginx 리버스 프록시 설정
- [ ] 모니터링 설정 (CloudWatch)
- [ ] 자동 백업 설정

---

## 📞 도움이 필요하면?

- GitHub Issues: 프로젝트 저장소에 이슈 등록
- AWS 공식 문서: https://docs.aws.amazon.com/
- Docker 공식 문서: https://docs.docker.com/

---

**작성일**: 2025-11-17
**최종 수정**: 2025-11-17
**버전**: 1.0
