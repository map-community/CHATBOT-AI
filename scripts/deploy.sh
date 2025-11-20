#!/bin/bash

# ========================================
# KNU Chatbot 자동 배포 스크립트
# ========================================

set -e  # 에러 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 프로젝트 디렉토리
PROJECT_DIR="/opt/knu-chatbot"
cd "$PROJECT_DIR" || exit 1

# ========================================
# 1. 환경 체크
# ========================================
log_info "배포 환경 체크 중..."

# Docker 설치 확인
if ! command -v docker &> /dev/null; then
    log_error "Docker가 설치되어 있지 않습니다."
    exit 1
fi

# Docker Compose 설치 확인
if ! command -v docker compose &> /dev/null; then
    log_error "Docker Compose가 설치되어 있지 않습니다."
    exit 1
fi

# .env 파일 존재 확인
if [ ! -f .env ]; then
    log_error ".env 파일이 없습니다. .env.production.example을 참고하여 생성하세요."
    exit 1
fi

log_success "환경 체크 완료"

# ========================================
# 2. 백업 (선택사항)
# ========================================
read -p "배포 전 데이터를 백업하시겠습니까? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "데이터 백업 중..."
    ./scripts/backup-mongodb.sh
    log_success "백업 완료"
fi

# ========================================
# 3. Git Pull (선택사항)
# ========================================
if [ -d .git ]; then
    read -p "최신 코드를 pull 받으시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Git pull 실행 중..."
        git pull origin main || log_warning "Git pull 실패, 계속 진행합니다..."
        log_success "Git pull 완료"
    fi
fi

# ========================================
# 4. 기존 컨테이너 중지
# ========================================
log_info "기존 컨테이너 중지 중..."
docker compose -f docker-compose.prod.yml down || true
log_success "컨테이너 중지 완료"

# ========================================
# 5. 이미지 빌드
# ========================================
log_info "Docker 이미지 빌드 중... (시간이 걸릴 수 있습니다)"
docker compose -f docker-compose.prod.yml build --no-cache
log_success "이미지 빌드 완료"

# ========================================
# 6. 컨테이너 시작
# ========================================
log_info "컨테이너 시작 중..."
docker compose -f docker-compose.prod.yml up -d
log_success "컨테이너 시작 완료"

# ========================================
# 7. 헬스 체크
# ========================================
log_info "애플리케이션 헬스 체크 중... (최대 60초 대기)"

MAX_RETRIES=12
RETRY_COUNT=0
SLEEP_TIME=5

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep $SLEEP_TIME
    RETRY_COUNT=$((RETRY_COUNT + 1))

    if curl -f http://localhost:5000/health &> /dev/null; then
        log_success "애플리케이션이 정상적으로 시작되었습니다!"
        break
    else
        log_warning "헬스 체크 실패 ($RETRY_COUNT/$MAX_RETRIES), 재시도 중..."
    fi

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        log_error "애플리케이션 시작 실패. 로그를 확인하세요:"
        log_error "docker compose -f docker-compose.prod.yml logs app"
        exit 1
    fi
done

# ========================================
# 8. 상태 확인
# ========================================
log_info "컨테이너 상태 확인"
docker compose -f docker-compose.prod.yml ps

# ========================================
# 9. 불필요한 리소스 정리
# ========================================
log_info "불필요한 Docker 리소스 정리 중..."
docker system prune -f
log_success "정리 완료"

# ========================================
# 배포 완료
# ========================================
echo ""
log_success "=========================================="
log_success "배포가 완료되었습니다!"
log_success "=========================================="
echo ""
log_info "애플리케이션 URL: http://localhost:5000"
log_info "헬스 체크 URL: http://localhost:5000/health"
echo ""
log_info "로그 확인: docker compose -f docker-compose.prod.yml logs -f"
log_info "컨테이너 상태: docker compose -f docker-compose.prod.yml ps"
echo ""
