# 🔄 CI/CD 분리 가이드

## 📖 CI와 CD가 뭔가요?

### 🧪 CI (Continuous Integration) - 지속적 통합
**"코드가 제대로 작동하는지 자동으로 확인"**

```
코드 push → 자동으로 실행:
  ✅ 문법 오류 확인
  ✅ Docker 이미지 빌드 테스트
  ✅ 필수 파일 존재 확인

결과: 코드 품질 보장! ✨
```

### 🚀 CD (Continuous Deployment) - 지속적 배포
**"검증된 코드를 서버에 올리기"**

```
버튼 클릭 (수동) → 배포 실행:
  🔐 "deploy" 입력으로 확인
  🚀 AWS 서버에 배포
  ✅ 헬스체크 확인

결과: 서버에서 앱 실행! 🎉
```

---

## 🎯 왜 분리했나요?

### ❌ 분리 전 (문제점)

```
코드 push → CI + CD 자동 실행
  ↓
AWS 설정 안 되어있음
  ↓
배포 실패 ❌
  ↓
계속 에러 발생 😭
```

**문제**:
- AWS 설정 전에 push하면 무조건 에러
- 실수로 main에 push하면 바로 배포됨
- 테스트 중인 코드도 서버에 올라감

### ✅ 분리 후 (해결!)

```
코드 push → CI만 자동 실행 ✅
  ↓
코드 품질 확인
  ↓
문제 없으면 통과!

배포하고 싶을 때:
  ↓
Actions 탭 → Run workflow 버튼 클릭
  ↓
"deploy" 입력으로 확인
  ↓
배포 시작 🚀
```

**장점**:
- AWS 설정 전에도 CI는 정상 작동 ✅
- 실수로 배포되는 것 방지 ✅
- 배포 시점을 내가 결정 ✅

---

## 📋 현재 워크플로우 2개

### 1️⃣ CI (자동 실행) - `.github/workflows/ci.yml`

**언제 실행?**
- main 브랜치에 push할 때
- Pull Request 만들 때
- develop 브랜치에 push할 때
- claude/** 브랜치에 push할 때

**뭘 하나요?**
```
✅ Job 1: Code Quality Check
   - Python 문법 검사
   - 코드 통계 출력

✅ Job 2: Docker Build Validation
   - Docker 이미지 빌드 테스트
   - 빌드만 하고 push는 안 함

✅ Job 3: Environment Variables Check
   - .env.example 파일 확인
   - 필수 파일 존재 확인

✅ Job 4: CI Summary
   - 전체 결과 요약
```

**확인 방법**:
```
GitHub Repository → Actions → CI (Continuous Integration)
초록색 체크 = 성공 ✅
빨간색 X = 실패 ❌
```

### 2️⃣ CD (수동 실행) - `.github/workflows/deploy.yml`

**언제 실행?**
- 수동으로만! (버튼 클릭)

**뭘 하나요?**
```
1. 배포 확인 ("deploy" 입력 필수)
2. SSH로 EC2 서버 접속
3. 최신 코드 받기
4. Docker 이미지 빌드
5. 컨테이너 재시작
6. 헬스체크
7. 배포 성공/실패 알림
```

---

## 🚀 사용 방법

### Step 1: 코드 작성 및 Push

```bash
# 1. 코드 수정
vim src/app.py

# 2. Commit
git add .
git commit -m "feat: 새 기능 추가"

# 3. Push (CI 자동 실행됨!)
git push origin main
```

**결과**:
- GitHub Actions에서 CI 워크플로우 자동 실행
- 약 1-2분 소요
- 성공하면 초록색 체크 ✅

### Step 2: CI 결과 확인

```
1. GitHub Repository 이동
2. "Actions" 탭 클릭
3. 최신 워크플로우 확인
   - 초록색 체크 = 배포 가능! ✅
   - 빨간색 X = 문제 있음, 수정 필요 ❌
```

### Step 3: 배포 (수동)

#### ⚠️ 사전 준비
AWS 설정이 완료되어야 합니다:
- [ ] EC2 서버 실행 중
- [ ] Docker 설치됨
- [ ] GitHub Secrets 6개 설정됨
- [ ] SSH 접속 테스트 완료

**설정 안 되었다면?**
→ `AWS_CICD_COMPLETE_GUIDE.md` 먼저 따라하기!

#### 배포 실행하기

```
1. GitHub Repository → Actions 탭
2. 왼쪽에서 "CD (Deploy to AWS)" 클릭
3. 오른쪽 상단 "Run workflow" 버튼 클릭

4. 입력 창이 나타남:
   ┌─────────────────────────────────────┐
   │ Use workflow from: main             │
   ├─────────────────────────────────────┤
   │ Deployment environment:             │
   │ ▼ production                        │
   ├─────────────────────────────────────┤
   │ Type "deploy" to confirm:           │
   │ [                              ]    │
   ├─────────────────────────────────────┤
   │          Run workflow               │
   └─────────────────────────────────────┘

5. "Type "deploy" to confirm" 칸에 deploy 입력
6. "Run workflow" 버튼 클릭
7. 배포 시작! 🚀
```

#### 배포 진행 상황 확인

```
Actions 탭에서 실시간 로그 확인:
  ⏳ Deploy to EC2 (in progress...)
  ├─ ✅ Confirm deployment
  ├─ ✅ Checkout code
  ├─ ✅ Setup SSH key
  ├─ ✅ Test SSH connection
  ├─ ⏳ Deploy to EC2 (2m 30s...)
  └─ ⏳ Verify deployment
```

#### 배포 완료!

```
✅ All steps completed successfully!

서버 접속:
http://YOUR_SERVER_IP:5000/health

응답 예시:
{
  "status": "healthy",
  "message": "KNU Chatbot Server is running",
  "version": "1.0.0"
}
```

---

## 💡 실제 사용 시나리오

### 시나리오 1: 기능 개발

```
1. 로컬에서 기능 개발
2. git push origin main
3. CI 자동 실행 → 통과 ✅
4. 테스트 더 필요 → 아직 배포 안 함
5. 내일 다시 수정
6. git push origin main
7. CI 자동 실행 → 통과 ✅
8. 준비 완료! → Actions에서 수동 배포 🚀
```

### 시나리오 2: 긴급 버그 수정

```
1. 버그 발견!
2. 급하게 수정
3. git push origin main
4. CI 자동 실행 → 통과 ✅
5. 바로 Actions → Run workflow
6. "deploy" 입력 → 배포
7. 3분 후 서버에 반영 ✅
```

### 시나리오 3: 실험적 기능

```
1. claude/new-feature 브랜치 생성
2. 실험적 기능 개발
3. git push origin claude/new-feature
4. CI 자동 실행 → 통과 ✅
5. 배포는 안 함 (실험 중이니까)
6. 더 테스트
7. 준비되면 main에 merge
8. 그때 배포 결정
```

---

## 🔧 고급 설정

### 자동 배포로 다시 변경하고 싶다면?

`.github/workflows/deploy.yml` 파일 수정:

```yaml
on:
  workflow_dispatch:  # 수동 실행 유지

  # 아래 주석 해제하면 자동 배포
  push:
    branches:
      - main
```

### 태그 기반 배포 (권장!)

```yaml
on:
  workflow_dispatch:  # 수동도 가능

  push:
    tags:
      - 'v*.*.*'  # v1.0.0, v2.1.3 같은 태그에서만 배포
```

**사용 방법**:
```bash
git tag v1.0.0
git push origin v1.0.0
# → 자동 배포!
```

---

## 📊 CI/CD 상태 뱃지 (선택사항)

README에 추가하면 멋있어요!

```markdown
![CI](https://github.com/YOUR_USERNAME/CHATBOT-AI/actions/workflows/ci.yml/badge.svg)
![CD](https://github.com/YOUR_USERNAME/CHATBOT-AI/actions/workflows/deploy.yml/badge.svg)
```

결과:
![CI](https://img.shields.io/badge/CI-passing-brightgreen)
![CD](https://img.shields.io/badge/CD-manual-blue)

---

## 🆘 문제 해결

### CI가 계속 실패해요

```bash
# 로그 확인
GitHub → Actions → 실패한 워크플로우 클릭 → 빨간색 X 클릭

# 일반적인 원인:
1. Python 문법 오류 → 로컬에서 수정 후 다시 push
2. Docker 빌드 실패 → Dockerfile 확인
3. 파일 누락 → requirements.txt 등 확인
```

### CD 버튼이 안 보여요

```
Actions 탭 → 왼쪽에서 "CD (Deploy to AWS)" 클릭
→ 오른쪽 상단 "Run workflow" 버튼

없으면:
1. .github/workflows/deploy.yml 파일이 main 브랜치에 있는지 확인
2. 파일을 push했는지 확인
3. 몇 분 기다린 후 새로고침
```

### "deploy" 입력했는데 실패해요

```
에러 메시지: "You must type 'deploy' to confirm"

해결:
- 정확히 소문자 "deploy"를 입력했는지 확인
- 앞뒤 공백 없이 입력
- 오타 확인
```

### AWS 연결 실패

```
에러 메시지: "Permission denied (publickey)"

해결:
1. GitHub Secrets 확인 (AWS_EC2_HOST, AWS_EC2_SSH_KEY 등)
2. EC2 서버가 실행 중인지 확인
3. 보안 그룹에서 22번 포트 열려있는지 확인

→ TROUBLESHOOTING_DEPLOYMENT.md 참고
```

---

## 🎓 요약

### CI (자동)
```
✅ 코드 push할 때마다 자동 실행
✅ 코드 품질 검사
✅ 빌드 테스트
✅ 1-2분 소요
```

### CD (수동)
```
⚠️ 버튼 클릭해야만 실행
⚠️ "deploy" 입력 필요
⚠️ AWS 설정 완료 필수
⚠️ 2-3분 소요
```

### 워크플로우

```
1. 코드 작성
2. git push
3. CI 자동 실행 ✅
4. 결과 확인
5. 준비되면 CD 수동 실행
6. 배포 완료! 🎉
```

---

**작성일**: 2025-11-17
**최종 수정**: 2025-11-17
**버전**: 2.0
