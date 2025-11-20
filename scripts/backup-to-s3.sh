#!/bin/bash

# ========================================
# S3 백업 스크립트
# ========================================

set -e

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

# .env 파일에서 S3 설정 로드
if [ -f /opt/knu-chatbot/.env ]; then
    source /opt/knu-chatbot/.env
else
    log_error ".env 파일을 찾을 수 없습니다."
    exit 1
fi

# S3 설정 확인
if [ -z "$AWS_S3_BUCKET" ]; then
    log_error "AWS_S3_BUCKET이 설정되지 않았습니다."
    log_info ".env 파일에 다음 항목을 추가하세요:"
    log_info "AWS_ACCESS_KEY_ID=your_access_key"
    log_info "AWS_SECRET_ACCESS_KEY=your_secret_key"
    log_info "AWS_S3_BUCKET=your_bucket_name"
    log_info "AWS_REGION=ap-northeast-2"
    exit 1
fi

# 설정
PROJECT_DIR="/opt/knu-chatbot"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
S3_PATH="s3://$AWS_S3_BUCKET/knu-chatbot-backups"

log_info "S3 백업 시작: $S3_PATH"

# AWS CLI 설치 확인
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI가 설치되어 있지 않습니다."
    log_info "설치 명령: sudo apt install -y awscli"
    exit 1
fi

# 1. MongoDB 백업
log_info "MongoDB 백업 중..."
/opt/knu-chatbot/scripts/backup-mongodb.sh

# 2. Redis 백업
log_info "Redis 백업 중..."
mkdir -p "$BACKUP_DIR/redis"
docker exec knu-chatbot-redis redis-cli SAVE
docker cp knu-chatbot-redis:/data/dump.rdb "$BACKUP_DIR/redis/dump_$TIMESTAMP.rdb"

# 3. 환경 설정 백업 (민감 정보 제외)
log_info "환경 설정 백업 중..."
mkdir -p "$BACKUP_DIR/config"
cp "$PROJECT_DIR/docker-compose.prod.yml" "$BACKUP_DIR/config/"
# .env는 민감 정보가 있으므로 백업 제외 (필요시 별도 암호화하여 백업)

# 4. 로그 백업 (최근 7일치)
log_info "로그 백업 중..."
mkdir -p "$BACKUP_DIR/logs"
find "$PROJECT_DIR/logs" -name "*.log" -mtime -7 -exec cp {} "$BACKUP_DIR/logs/" \;

# 5. 전체 백업 파일 압축
log_info "백업 파일 압축 중..."
cd "$PROJECT_DIR"
tar -czf "backup_full_$TIMESTAMP.tar.gz" -C backups .

# 6. S3로 업로드
log_info "S3로 백업 파일 업로드 중..."
aws s3 cp "backup_full_$TIMESTAMP.tar.gz" "$S3_PATH/backup_full_$TIMESTAMP.tar.gz" \
    --region "${AWS_REGION:-ap-northeast-2}" \
    --storage-class STANDARD_IA

# 백업 파일 크기 확인
BACKUP_SIZE=$(du -h "backup_full_$TIMESTAMP.tar.gz" | cut -f1)
log_success "S3 업로드 완료: $S3_PATH/backup_full_$TIMESTAMP.tar.gz ($BACKUP_SIZE)"

# 7. 로컬 백업 파일 정리 (선택사항)
log_warning "로컬 백업 파일을 삭제하시겠습니까? (y/N)"
read -r -n 1 response
echo
if [[ "$response" =~ ^([yY])$ ]]; then
    rm "backup_full_$TIMESTAMP.tar.gz"
    log_info "로컬 백업 파일 삭제됨"
else
    log_info "로컬 백업 파일 유지: backup_full_$TIMESTAMP.tar.gz"
fi

# 8. S3에서 오래된 백업 삭제 (30일 이상)
log_info "S3에서 오래된 백업 파일 정리 중..."
aws s3 ls "$S3_PATH/" --region "${AWS_REGION:-ap-northeast-2}" | \
    while read -r line; do
        createDate=$(echo "$line" | awk '{print $1" "$2}')
        createDate=$(date -d "$createDate" +%s)
        olderThan=$(date -d "30 days ago" +%s)
        if [[ $createDate -lt $olderThan ]]; then
            fileName=$(echo "$line" | awk '{print $4}')
            if [[ $fileName != "" ]]; then
                aws s3 rm "$S3_PATH/$fileName" --region "${AWS_REGION:-ap-northeast-2}"
                log_info "삭제됨: $fileName"
            fi
        fi
    done

log_success "S3 백업이 완료되었습니다!"
log_info "복원 방법:"
log_info "1. aws s3 cp $S3_PATH/backup_full_$TIMESTAMP.tar.gz ."
log_info "2. tar -xzf backup_full_$TIMESTAMP.tar.gz"
log_info "3. 각 서비스별로 데이터 복원"
