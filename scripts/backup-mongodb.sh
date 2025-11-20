#!/bin/bash

# ========================================
# MongoDB 백업 스크립트
# ========================================

set -e

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 설정
PROJECT_DIR="/opt/knu-chatbot"
BACKUP_DIR="$PROJECT_DIR/backups/mongodb"
CONTAINER_NAME="knu-chatbot-mongodb"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="mongodb_backup_$TIMESTAMP"

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

log_info "MongoDB 백업 시작: $BACKUP_NAME"

# 컨테이너 실행 확인
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    log_error "MongoDB 컨테이너가 실행 중이지 않습니다."
    exit 1
fi

# MongoDB 백업 수행
log_info "mongodump 실행 중..."
docker exec "$CONTAINER_NAME" mongodump --out /data/backup/"$BACKUP_NAME"

# 백업 파일 복사
log_info "백업 파일을 호스트로 복사 중..."
docker cp "$CONTAINER_NAME:/data/backup/$BACKUP_NAME" "$BACKUP_DIR/"

# 백업 파일 압축
log_info "백업 파일 압축 중..."
cd "$BACKUP_DIR"
tar -czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"

# 컨테이너 내 백업 파일 삭제
docker exec "$CONTAINER_NAME" rm -rf /data/backup/"$BACKUP_NAME"

# 백업 파일 크기 확인
BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_NAME.tar.gz" | cut -f1)
log_success "백업 완료: $BACKUP_DIR/$BACKUP_NAME.tar.gz ($BACKUP_SIZE)"

# 오래된 백업 파일 삭제 (30일 이상)
log_info "오래된 백업 파일 정리 중..."
find "$BACKUP_DIR" -name "mongodb_backup_*.tar.gz" -mtime +30 -delete
log_success "백업 정리 완료"

# 백업 파일 목록 출력
log_info "현재 백업 파일 목록:"
ls -lh "$BACKUP_DIR"

log_success "MongoDB 백업이 완료되었습니다!"
