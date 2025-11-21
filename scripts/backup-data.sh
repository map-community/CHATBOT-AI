#!/bin/bash
# 크롤링 전 데이터 백업 스크립트

set -e  # 에러 발생 시 즉시 중단

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
BACKUP_DIR="$PROJECT_ROOT/data-backups"

# 타임스탬프 생성
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="data-backup-$TIMESTAMP"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

echo "========================================="
echo "💾 데이터 백업 시작"
echo "========================================="
echo "타임스탬프: $TIMESTAMP"
echo "백업 경로: $BACKUP_PATH"
echo ""

# 데이터 디렉토리 존재 확인
if [ ! -d "$DATA_DIR" ]; then
    echo "❌ 데이터 디렉토리가 없습니다: $DATA_DIR"
    exit 1
fi

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

# 데이터 백업 (cp 대신 rsync 사용 - 더 안전)
echo "📦 데이터 복사 중..."
if command -v rsync &> /dev/null; then
    # rsync 있으면 사용 (더 빠르고 안전)
    rsync -a --info=progress2 "$DATA_DIR/" "$BACKUP_PATH/"
else
    # rsync 없으면 cp 사용
    cp -r "$DATA_DIR" "$BACKUP_PATH"
fi

# 백업 크기 확인
BACKUP_SIZE=$(du -sh "$BACKUP_PATH" | cut -f1)

echo ""
echo "========================================="
echo "✅ 백업 완료!"
echo "========================================="
echo "백업 위치: $BACKUP_PATH"
echo "백업 크기: $BACKUP_SIZE"
echo ""

# 오래된 백업 정리 (7일 이상 된 백업 삭제)
echo "🧹 오래된 백업 정리 중... (7일 이상)"
find "$BACKUP_DIR" -name "data-backup-*" -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true

# 현재 백업 목록 출력
echo ""
echo "📋 현재 백업 목록:"
ls -lht "$BACKUP_DIR" | head -n 6

echo ""
echo "💡 백업에서 복원하려면:"
echo "   ./scripts/restore-data.sh $BACKUP_NAME"
echo ""
