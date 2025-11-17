#!/bin/bash

###############################################################################
# 수동 배포 스크립트 (EC2 서버에서 직접 실행용)
# 사용법: ./scripts/deploy-manual.sh
###############################################################################

set -e  # 에러 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 배포 시작
echo "========================================="
log_info "Starting manual deployment..."
echo "Time: $(date)"
echo "========================================="

# 1. Docker 설치 확인
log_info "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed!"
    log_error "Please install Docker first:"
    echo "  curl -fsSL https://get.docker.com -o get-docker.sh"
    echo "  sudo sh get-docker.sh"
    exit 1
fi

log_info "Docker version: $(docker --version)"
log_info "Docker Compose version: $(docker compose version)"

# 2. 프로젝트 디렉토리로 이동
APP_DIR=$(pwd)
log_info "Working directory: $APP_DIR"

# 3. .env 파일 확인
if [ ! -f ".env" ]; then
    log_error ".env file not found!"
    log_warn "Please create .env file with required environment variables."
    log_warn "You can copy from .env.example:"
    echo "  cp .env.example .env"
    echo "  vim .env  # Edit with your actual values"
    exit 1
fi

log_info ".env file found ✓"

# 4. 기존 컨테이너 중지
log_info "Stopping existing containers..."
docker compose down || log_warn "No containers to stop"

# 5. Docker 이미지 빌드
log_info "Building Docker images..."
log_warn "This may take several minutes..."

docker compose build --no-cache

if [ $? -eq 0 ]; then
    log_info "Docker images built successfully ✓"
else
    log_error "Docker build failed!"
    exit 1
fi

# 6. 컨테이너 시작
log_info "Starting containers..."
docker compose up -d

if [ $? -eq 0 ]; then
    log_info "Containers started successfully ✓"
else
    log_error "Failed to start containers!"
    exit 1
fi

# 7. 컨테이너 상태 확인
echo ""
log_info "Container status:"
docker compose ps

# 8. 헬스체크 대기
echo ""
log_info "Waiting for health check..."
log_warn "This may take up to 60 seconds..."

MAX_RETRIES=12
RETRY_COUNT=0
HEALTH_OK=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 5
    RETRY_COUNT=$((RETRY_COUNT + 1))

    log_info "Health check attempt $RETRY_COUNT/$MAX_RETRIES..."

    HEALTH_STATUS=$(curl -s http://localhost:5000/health 2>/dev/null | grep -o '"status":"healthy"' || echo "")

    if [ ! -z "$HEALTH_STATUS" ]; then
        HEALTH_OK=true
        break
    fi
done

if [ "$HEALTH_OK" = true ]; then
    log_info "Health check passed! ✓"
else
    log_error "Health check failed!"
    log_error "Application logs:"
    docker logs knu-chatbot-app --tail 50
    exit 1
fi

# 9. 배포 완료
echo ""
echo "========================================="
log_info "✅ Deployment completed successfully!"
echo "========================================="
echo "Access your application at:"
echo "  - Health check: http://localhost:5000/health"
echo "  - API endpoint: http://localhost:5000/ai/ai-response"
echo ""
log_info "Useful commands:"
echo "  - View logs:       docker compose logs -f"
echo "  - Stop containers: docker compose down"
echo "  - Restart:         docker compose restart"
echo "========================================="
