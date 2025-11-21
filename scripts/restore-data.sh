#!/bin/bash
# 백업에서 데이터 복원 스크립트

set -e  # 에러 발생 시 즉시 중단

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
BACKUP_DIR="$PROJECT_ROOT/data-backups"

# 인자 확인
if [ -z "$1" ]; then
    echo "========================================="
    echo "❌ 사용법: $0 <백업명>"
    echo "========================================="
    echo ""
    echo "사용 가능한 백업 목록:"
    ls -lht "$BACKUP_DIR" 2>/dev/null || echo "  백업이 없습니다."
    echo ""
    echo "예시:"
    echo "  $0 data-backup-20251121_120000"
    exit 1
fi

BACKUP_NAME="$1"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

echo "========================================="
echo "♻️  데이터 복원 시작"
echo "========================================="
echo "복원할 백업: $BACKUP_NAME"
echo "백업 경로: $BACKUP_PATH"
echo ""

# 백업 존재 확인
if [ ! -d "$BACKUP_PATH" ]; then
    echo "❌ 백업을 찾을 수 없습니다: $BACKUP_PATH"
    echo ""
    echo "사용 가능한 백업 목록:"
    ls -lht "$BACKUP_DIR" 2>/dev/null || echo "  백업이 없습니다."
    exit 1
fi

# 확인 메시지
echo "⚠️  경고: 현재 데이터가 백업으로 대체됩니다!"
echo ""
read -p "계속하시겠습니까? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "❌ 복원이 취소되었습니다."
    exit 0
fi

echo ""

# Docker 중지 확인
if docker ps | grep -q "knu-chatbot"; then
    echo "🛑 Docker 컨테이너를 먼저 중지해야 합니다."
    read -p "Docker를 중지하시겠습니까? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "🛑 Docker 중지 중..."
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" down 2>/dev/null || true
        docker compose -f "$PROJECT_ROOT/docker-compose.prod.yml" down 2>/dev/null || true
    else
        echo "❌ Docker를 중지해주세요: docker compose down"
        exit 1
    fi
fi

# 현재 데이터 임시 백업 (안전장치)
if [ -d "$DATA_DIR" ]; then
    TEMP_BACKUP="$DATA_DIR.before-restore-$(date +%Y%m%d_%H%M%S)"
    echo "💾 현재 데이터 임시 백업 중: $TEMP_BACKUP"
    mv "$DATA_DIR" "$TEMP_BACKUP"
    echo "   (복원 실패 시 여기서 복구 가능)"
fi

# 백업에서 복원
echo "📦 백업에서 데이터 복원 중..."
if command -v rsync &> /dev/null; then
    rsync -a --info=progress2 "$BACKUP_PATH/" "$DATA_DIR/"
else
    cp -r "$BACKUP_PATH" "$DATA_DIR"
fi

# 권한 설정 (Docker용)
if [ -d "$DATA_DIR/mongodb" ]; then
    echo "🔒 MongoDB 권한 설정 중..."
    chmod -R 755 "$DATA_DIR/mongodb" 2>/dev/null || true
fi

if [ -d "$DATA_DIR/redis" ]; then
    echo "🔒 Redis 권한 설정 중..."
    chmod -R 755 "$DATA_DIR/redis" 2>/dev/null || true
fi

echo ""
echo "========================================="
echo "✅ 복원 완료!"
echo "========================================="
echo "복원된 백업: $BACKUP_NAME"
echo ""
echo "💡 다음 단계:"
echo "   1. Docker 시작: docker compose up -d"
echo "   2. 로그 확인: docker logs -f knu-chatbot-app"
echo ""
echo "💡 임시 백업 위치 (문제 발생 시 복구용):"
echo "   $TEMP_BACKUP"
echo ""
