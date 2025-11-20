# AWS 보안 그룹 설정 가이드

Spring Boot 서버에서 AI 챗봇 서버로 안전하게 접근하기 위한 AWS 보안 그룹 설정 가이드입니다.

## 🎯 목표

- **외부 접근 차단**: 인터넷에서 AI 서버 직접 접근 불가
- **내부 통신 허용**: Spring Boot 서버만 AI 서버에 접근 가능
- **비용 절감**: AWS 내부망(Private IP) 사용으로 데이터 전송료 무료

---

## 📊 아키텍처

```
[사용자]
   ↓ HTTPS
[Spring Boot 서버] (api.mongle.site)
   ↓ HTTP (AWS 내부망)
[AI 챗봇 서버] (Private IP: 172.31.x.x)
   ↓
[MongoDB, Redis, Pinecone]
```

---

## 🔧 1단계: AI 서버 정보 확인

### AI 서버 EC2 인스턴스

```bash
# EC2에 접속해서 확인
ssh -i your-key.pem ubuntu@3.39.153.45

# Private IP 확인
ip addr show | grep "inet 172"
# 출력 예시: inet 172.31.37.76/20
```

**확인할 정보:**
- **Public IP**: `3.39.153.45` (외부 접근용, 나중에 차단)
- **Private IP**: `172.31.37.76` (AWS 내부망, Spring Boot 서버가 사용)
- **보안 그룹**: `sg-xxxxxxxxx` (AI 서버의 보안 그룹 ID)

---

## 🔒 2단계: AI 서버 보안 그룹 수정

### 현재 상태 (변경 전)

| 타입 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| HTTP | TCP | 5000 | 0.0.0.0/0 | ❌ 전 세계 개방 (위험!) |
| SSH | TCP | 22 | Your IP | ✅ 관리자만 접근 |

### 변경 후 (권장)

| 타입 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| Custom TCP | TCP | 5000 | `sg-spring-boot` | ✅ Spring Boot 서버만 접근 |
| SSH | TCP | 22 | Your IP | ✅ 관리자만 접근 |

### AWS Console에서 설정 방법

1. **EC2 Console → 보안 그룹** 으로 이동
2. AI 서버의 보안 그룹 선택
3. **인바운드 규칙 → 편집** 클릭
4. 기존 5000번 포트 규칙 **삭제**
5. **규칙 추가** 클릭:
   - **유형**: Custom TCP
   - **프로토콜**: TCP
   - **포트 범위**: 5000
   - **소스**:
     - **옵션 1** (권장): Spring Boot 서버의 보안 그룹 ID 선택 (`sg-xxxxxxxxx`)
     - **옵션 2** (간단): Spring Boot 서버의 Private IP/32 입력 (예: `172.31.10.20/32`)
   - **설명**: Allow from Spring Boot server
6. **규칙 저장**

---

## 🌐 3단계: Spring Boot 서버 설정 확인

### Spring Boot 서버 정보 확인

Spring Boot 서버(api.mongle.site)의 다음 정보를 확인하세요:

```bash
# Spring Boot EC2에 접속
ssh -i your-key.pem ubuntu@your-spring-boot-ip

# Private IP 확인
ip addr show | grep "inet 172"
# 출력 예시: inet 172.31.10.20/20

# 보안 그룹 확인 (AWS Console)
# EC2 → 인스턴스 → 보안 탭 → 보안 그룹 ID 복사
```

**확인할 정보:**
- **Private IP**: `172.31.10.20` (예시)
- **보안 그룹**: `sg-spring-boot-xxxx`
- **VPC**: AI 서버와 **같은 VPC**에 있어야 함

---

## ✅ 4단계: 연결 테스트

### Spring Boot 서버에서 테스트

```bash
# Spring Boot EC2에서 실행
ssh -i your-key.pem ubuntu@your-spring-boot-ip

# AI 서버 Private IP로 Health Check 테스트
curl http://172.31.37.76:5000/health

# 성공 응답 예시:
# {"status":"healthy","message":"KNU Chatbot Server is running","version":"1.0.0"}
```

### 외부에서 차단 확인

```bash
# 로컬 컴퓨터에서 실행 (차단되어야 정상)
curl http://3.39.153.45:5000/health

# 예상 응답: Connection timeout (정상!)
```

---

## 🔑 5단계: Spring Boot Application 설정

### application.yml (또는 application.properties)

```yaml
# application.yml
ai:
  chatbot:
    base-url: http://172.31.37.76:5000  # Private IP 사용!
    timeout: 30000  # 30초 (AI 응답 대기)
    connect-timeout: 5000  # 5초
```

또는

```properties
# application.properties
ai.chatbot.base-url=http://172.31.37.76:5000
ai.chatbot.timeout=30000
ai.chatbot.connect-timeout=5000
```

---

## 🚨 주의사항

### ✅ DO

- **Private IP 사용**: Spring Boot → AI 서버 통신은 반드시 Private IP 사용
- **같은 VPC**: 두 서버가 같은 VPC에 있어야 Private IP 통신 가능
- **보안 그룹**: Spring Boot 보안 그룹 ID로 소스 지정 (IP 변경에도 자동 대응)

### ❌ DON'T

- **Public IP 사용 금지**: `3.39.153.45` 대신 `172.31.37.76` 사용
- **0.0.0.0/0 개방 금지**: AI 서버를 인터넷에 노출하지 마세요
- **다른 VPC**: 다른 VPC에 있으면 VPC Peering 설정 필요

---

## 📋 체크리스트

설정 완료 후 다음을 확인하세요:

- [ ] AI 서버 Private IP 확인 완료
- [ ] AI 서버 보안 그룹에서 5000번 포트 규칙 수정 완료
- [ ] Spring Boot 서버에서 `curl` 테스트 성공
- [ ] 외부(로컬)에서 접근 차단 확인
- [ ] Spring Boot `application.yml`에 Private IP 설정 완료
- [ ] API 명세서 확인 및 테스트 완료

---

## 🆘 트러블슈팅

### 문제: Connection timeout

**원인**:
- 보안 그룹 규칙이 제대로 설정되지 않음
- 다른 VPC에 있음

**해결**:
```bash
# 1. VPC 확인
aws ec2 describe-instances --instance-ids i-xxxxx --query 'Reservations[0].Instances[0].VpcId'

# 2. 보안 그룹 인바운드 규칙 확인
aws ec2 describe-security-groups --group-ids sg-xxxxx
```

### 문제: Connection refused

**원인**: AI 서버 컨테이너가 실행 중이지 않음

**해결**:
```bash
# AI 서버 EC2에서
docker ps | grep knu-chatbot-app
docker logs knu-chatbot-app --tail 50
```

### 문제: 502 Bad Gateway (Spring Boot)

**원인**: Private IP가 잘못되었거나 AI 서버 초기화 중

**해결**:
- Private IP 재확인
- AI 서버 로그 확인 (초기화 완료 대기)

---

## 📞 문의

설정 중 문제가 발생하면 AI 서버 관리자에게 문의하세요:

- AI 서버 Private IP
- 보안 그룹 ID
- Health check 결과
