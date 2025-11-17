# 🚨 GitHub Actions 배포 실패 해결 가이드

## 왜 실패했나요?

가장 가능성 높은 원인들:

### ❌ 1. GitHub Secrets가 설정되지 않음 (90% 확률)
AWS 설정을 아직 하지 않으셨다면 이게 원인입니다.

**확인 방법**:
```
1. GitHub Repository → Settings → Secrets and variables → Actions
2. 다음 6개 Secrets가 있는지 확인:
   - AWS_EC2_HOST
   - AWS_EC2_USERNAME
   - AWS_EC2_SSH_KEY
   - UPSTAGE_API_KEY
   - PINECONE_API_KEY
   - PINECONE_INDEX_NAME
```

**없다면?** → AWS_CICD_COMPLETE_GUIDE.md의 Section 6 따라하기

---

### ❌ 2. EC2 서버가 준비되지 않음
서버를 아직 만들지 않으셨다면 이게 원인입니다.

**확인 방법**:
```
AWS Console → EC2 → Instances → 실행 중인 인스턴스 확인
```

**없다면?** → AWS_CICD_COMPLETE_GUIDE.md의 Section 4 따라하기

---

### ❌ 3. SSH 연결 실패
서버는 있는데 접속이 안 되는 경우

**확인 방법**:
```bash
# 로컬에서 테스트
ssh -i ~/path/to/key.pem ubuntu@YOUR_SERVER_IP

# 접속이 안 되면:
# 1. EC2 보안 그룹에서 22번 포트(SSH) 확인
# 2. IP 주소 올바른지 확인
# 3. 키 파일 권한 확인 (chmod 400)
```

---

## 🔎 에러 로그 확인하는 방법

### Step 1: GitHub Actions 페이지 가기
```
https://github.com/YOUR_USERNAME/CHATBOT-AI/actions
```

### Step 2: 실패한 워크플로우 클릭
빨간색 X 표시된 것 클릭

### Step 3: "Deploy to EC2" Job 클릭
왼쪽에 빨간색 X 표시된 "Deploy to EC2" 클릭

### Step 4: 에러 메시지 찾기
빨간색으로 표시된 부분을 찾아보세요:

#### 케이스 1: "secrets.AWS_EC2_HOST: not found"
```
Error: Input required and not supplied: AWS_EC2_HOST
```
**해결**: GitHub Secrets 설정 필요

#### 케이스 2: "Permission denied (publickey)"
```
Permission denied (publickey).
```
**해결**: SSH 키 확인 필요

#### 케이스 3: "Connection refused" 또는 "Connection timed out"
```
ssh: connect to host xx.xx.xx.xx port 22: Connection refused
```
**해결**: EC2 서버 확인 또는 보안 그룹 설정

---

## ✅ 임시 해결책: 워크플로우 비활성화

AWS 설정을 완료할 때까지 자동 배포를 끄는 방법:

### Option 1: 워크플로우 파일 수정
```bash
# .github/workflows/deploy.yml 파일 수정
# on: 부분을 다음과 같이 변경:

on:
  workflow_dispatch:  # 수동 실행만 허용
  # push:
  #   branches:
  #     - main
```

### Option 2: 워크플로우 비활성화
```
1. GitHub Repository → Actions
2. 왼쪽에서 "Deploy to AWS EC2" 클릭
3. 오른쪽 상단 ... (점 3개) → Disable workflow
```

---

## 🎯 올바른 순서

### Phase 1: AWS 설정 (AWS_CICD_COMPLETE_GUIDE.md 따라하기)
1. ✅ AWS 계정 만들기
2. ✅ EC2 서버 생성
3. ✅ Docker 설치
4. ✅ .env 파일 생성
5. ✅ 서버 테스트 (SSH 접속 확인)

### Phase 2: GitHub Secrets 설정
6. ✅ GitHub Secrets 6개 추가

### Phase 3: 배포 테스트
7. ✅ 코드 수정 후 push
8. ✅ GitHub Actions 성공 확인
9. ✅ 서버 접속해서 동작 확인

---

## 💡 권장 사항

**지금 당장 하실 일**:

1. **워크플로우 비활성화** (임시)
   ```
   GitHub → Actions → Deploy to AWS EC2 → Disable workflow
   ```

2. **AWS 설정 완료**
   - AWS_CICD_COMPLETE_GUIDE.md 처음부터 끝까지 따라하기
   - 예상 시간: 1-2시간

3. **워크플로우 다시 활성화**
   ```
   GitHub → Actions → Deploy to AWS EC2 → Enable workflow
   ```

4. **테스트 push**
   ```bash
   git commit --allow-empty -m "test: CI/CD 테스트"
   git push origin main
   ```

---

## 📞 여전히 안 되면?

1. **에러 로그 전체 복사**
   - GitHub Actions 페이지에서 에러 메시지 전체 복사

2. **Issue 생성**
   ```
   GitHub Repository → Issues → New issue
   제목: [CI/CD] 배포 실패 - [에러 메시지 요약]
   내용: 에러 로그 붙여넣기
   ```

3. **다시 시도**
   - 가이드 문서 처음부터 다시 읽기
   - 빠뜨린 단계가 없는지 확인

---

**작성일**: 2025-11-17
