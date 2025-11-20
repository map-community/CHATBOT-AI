# 비용 최적화 가이드

> 트래픽이 적은 경우 월 $12-15로 운영 가능!

## 🎯 비용 절감 전략

### 전략 1: Reranker 제거 (권장) ⭐

**절감액: 1.2GB 메모리**

Reranker는 검색 정확도를 높이지만 필수는 아닙니다.
- BM25 + Dense Retrieval만으로도 충분히 작동
- 검색 정확도 약간 감소 (체감상 큰 차이 없음)

**적용 방법:**

1. `requirements.txt` 수정:
```bash
# FlagEmbedding==1.2.10  ← 이 줄 주석 처리 또는 삭제
```

2. 결과:
```
기존 메모리: 4-7.5GB → t3.large (8GB, $60/월) 필요
최적화: 2.8-6.3GB → t3.small (2GB, $15/월) 가능
```

3. 코드는 자동으로 Reranker 없이 작동:
```python
# storage_manager.py에서 자동 처리
if storage.reranker and len(top_docs) > 1:
    # Reranker 사용
else:
    # 원본 순서 유지 (자동 fallback)
```

---

### 전략 2: ARM 인스턴스 (Graviton2/3) 사용

**절감액: 20%**

ARM 프로세서는 동일 성능에 20% 저렴:
- t3.small → t4g.small: $15 → **$12/월**
- t3.medium → t4g.medium: $30 → **$24/월**
- t3.large → t4g.large: $60 → **$48/월**

**적용 방법:**

1. EC2 인스턴스 생성 시 `t4g` 시리즈 선택

2. `Dockerfile` 수정:
```dockerfile
# 첫 줄 수정
FROM --platform=linux/arm64 python:3.11-slim
```

3. 재빌드:
```bash
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
```

**주의:** ARM은 일부 패키지 호환성 문제 가능 (mecab-python3는 문제없음)

---

### 전략 3: Spot 인스턴스

**절감액: 70-90%**

| 인스턴스 | 온디맨드 | Spot | 절감 |
|----------|----------|------|------|
| t3.small | $15/월 | $3/월 | 80% |
| t3.medium | $30/월 | $5-10/월 | 70-80% |
| t3.large | $60/월 | $10-15/월 | 75-80% |

**적용 방법:**

1. EC2 콘솔에서 "스팟 인스턴스" 요청
2. 스팟 가격 기록 확인 (중단 빈도 낮은 타입 선택)
3. Auto Scaling Group 설정 (중단 시 자동 재시작)

**장점:**
- 비용 대폭 절감
- 대부분의 경우 안정적

**단점:**
- AWS가 필요 시 회수 (2분 전 경고)
- 학습/개발용 프로젝트에 적합, 프로덕션에는 비권장

**추천 조합: Spot + Auto Scaling + 데이터 백업**

---

### 전략 4: 컨테이너 메모리 제한 강화

`docker-compose.prod.yml`에서 메모리 제한 줄이기:

```yaml
services:
  mongodb:
    deploy:
      resources:
        limits:
          memory: 512M  # 2G → 512M
        reservations:
          memory: 256M

  redis:
    deploy:
      resources:
        limits:
          memory: 256M  # 1G → 256M

  app:
    deploy:
      resources:
        limits:
          memory: 1.5G  # 4G → 1.5G (Reranker 없으면)
```

---

## 💰 추천 조합

### 🥇 최고 가성비: **Reranker 제거 + ARM**

```
인스턴스: t4g.small (2GB, ARM)
비용: $12/월
메모리: 충분
성능: 트래픽 적으면 OK
```

**적용:**
```bash
1. requirements.txt에서 FlagEmbedding 주석
2. EC2에서 t4g.small 선택
3. Dockerfile에 --platform=linux/arm64 추가
```

---

### 🥈 최저가: **Spot 인스턴스**

```
인스턴스: t3.medium Spot (4GB)
비용: $5-10/월
Reranker: 사용 가능
```

**주의:** 중단 대비 백업 필수

---

### 🥉 안정적: **Reranker 제거만**

```
인스턴스: t3.small (2GB)
비용: $15/월
안정성: 높음
```

---

## 📈 트래픽 증가 시 업그레이드 경로

```
1. t4g.small (2GB, $12) - Reranker 없음
   ↓ (트래픽 증가)
2. t4g.medium (4GB, $24) - Reranker 추가
   ↓ (더 증가)
3. t4g.large (8GB, $48) - Reranker + 여유
   ↓ (고트래픽)
4. c6g.xlarge (8GB, 4 vCPU, $100) - CPU 강화
```

---

## 🔍 메모리 사용량 실측 방법

배포 후 실제 메모리 확인:

```bash
# 1. 리소스 모니터링
/opt/knu-chatbot/scripts/monitor-resources.sh watch

# 2. Docker 컨테이너별 메모리
docker stats

# 3. 실제 메모리 여유 확인
free -h
```

**예상 결과 (Reranker 없음):**
```
Total:     2.0G
Used:      1.5-1.8G
Available: 200-500M
→ t3.small 충분!
```

---

## ⚠️ 주의사항

### Reranker 제거 시
- 검색 정확도 약간 감소
- 대부분의 쿼리는 문제없음
- 복잡한 질문에서 관련 없는 문서가 상위에 올라올 수 있음

### ARM 인스턴스 사용 시
- Python 패키지 대부분 호환
- mecab-python3, konlpy 모두 작동 확인됨
- 일부 바이너리 패키지는 빌드 시간 증가 가능

### Spot 인스턴스 사용 시
- 중단 대비 백업 필수
- Auto Scaling Group 설정 권장
- 데이터는 EBS 볼륨에 저장 (중단 시에도 보존)

---

## 📊 실제 비용 예시 (월 기준)

| 구성 | EC2 | EBS (50GB) | 데이터 전송 | 총합 |
|------|-----|------------|-------------|------|
| 초저비용 | $12 | $5 | $1 | **$18** |
| Spot | $8 | $5 | $1 | **$14** |
| 기존 | $60 | $5 | $1 | **$66** |

**절감액: $44-48/월 (73-80% 절감!)**

---

## 🎯 결론

**트래픽이 적다면:**
1. Reranker 제거 (FlagEmbedding 주석)
2. t4g.small (ARM) 또는 t3.small 사용
3. **월 $12-15로 운영 가능!**

**비용을 최소화하려면:**
1. t3.medium Spot 사용
2. **월 $5-10으로 운영 가능!**

**원래 생각하신 t3.small이 정답이었습니다!** ✅
