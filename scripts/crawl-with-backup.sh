#!/bin/bash
# 백업 + 크롤링 + 복원 통합 스크립트
# 크롤링 실패 시 자동으로 백업에서 복원

set -e  # 에러 발생 시 즉시 중단

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "🚀 안전 크롤링 시작"
echo "========================================="
echo "1. 데이터 백업"
echo "2. 크롤링 실행"
echo "3. 성공/실패 처리"
echo "========================================="
echo ""

# ========== 1단계: 백업 ==========
echo "📍 1단계: 데이터 백업"
"$SCRIPT_DIR/backup-data.sh"

# 백업 이름 저장 (복원용)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="data-backup-$TIMESTAMP"

echo ""
echo "========================================="

# ========== 2단계: 크롤링 ==========
echo "📍 2단계: 크롤링 실행"
echo "========================================="
echo ""

CRAWL_SUCCESS=false

# Docker 실행 중인지 확인
if ! docker ps | grep -q "knu-chatbot-app"; then
    echo "⚠️  Docker 컨테이너가 실행 중이 아닙니다."
    echo "🚀 Docker 시작 중..."
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" up -d || \
    docker compose -f "$PROJECT_ROOT/docker-compose.prod.yml" up -d

    echo "⏳ 컨테이너 초기화 대기 중... (30초)"
    sleep 30
fi

# 크롤링 실행 (에러 캐치)
if docker exec -it knu-chatbot-app python src/modules/run_crawler.py; then
    CRAWL_SUCCESS=true
    echo ""
    echo "========================================="
    echo "✅ 크롤링 성공!"
    echo "========================================="
else
    CRAWL_SUCCESS=false
    echo ""
    echo "========================================="
    echo "❌ 크롤링 실패!"
    echo "========================================="
fi

echo ""

# ========== 3단계: 성공/실패 처리 ==========
if [ "$CRAWL_SUCCESS" = true ]; then
    echo "📍 3단계: 성공 처리"
    echo "========================================="
    echo "✅ 백업 유지됨: $BACKUP_NAME"
    echo "   (필요시 복원 가능)"
    echo ""
    echo "💡 백업에서 복원하려면:"
    echo "   ./scripts/restore-data.sh $BACKUP_NAME"
    echo ""
else
    echo "📍 3단계: 실패 처리"
    echo "========================================="
    echo "❌ 크롤링이 실패했습니다."
    echo ""
    echo "⚠️  중요: Pinecone-MongoDB 불일치 위험!"
    echo "   크롤링 중 Pinecone에 벡터가 업로드되었을 수 있습니다."
    echo "   MongoDB만 복원하면 Pinecone과 불일치 발생!"
    echo ""
    read -p "백업에서 복원하시겠습니까? (yes/no): " -r

    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo ""
        echo "♻️  백업에서 복원 중..."
        "$SCRIPT_DIR/restore-data.sh" "$BACKUP_NAME"

        echo ""
        echo "🧹 Pinecone 정리 중..."
        echo "   (크롤링 중 추가된 벡터 삭제 시도)"

        # Pinecone 정리 스크립트 실행 (있다면)
        if [ -f "$SCRIPT_DIR/cleanup-pinecone.sh" ]; then
            "$SCRIPT_DIR/cleanup-pinecone.sh" "$BACKUP_NAME" || echo "⚠️  Pinecone 정리 실패 (수동 확인 필요)"
        else
            echo "⚠️  Pinecone 정리 스크립트 없음"
            echo ""
            echo "📋 수동 정리 방법:"
            echo "   1. Pinecone 콘솔에서 벡터 개수 확인"
            echo "   2. MongoDB 문서 개수와 비교"
            echo "   3. 불일치 시 다음 명령으로 재구축:"
            echo "      docker exec -it knu-chatbot-app python src/modules/force_reembed.py"
        fi

        echo ""
        echo "🚀 Docker 재시작 중..."
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" down 2>/dev/null || \
        docker compose -f "$PROJECT_ROOT/docker-compose.prod.yml" down 2>/dev/null || true

        docker compose -f "$PROJECT_ROOT/docker-compose.yml" up -d || \
        docker compose -f "$PROJECT_ROOT/docker-compose.prod.yml" up -d

        echo ""
        echo "========================================="
        echo "✅ MongoDB 복원 완료!"
        echo "========================================="
        echo "⚠️  주의: Pinecone 동기화 확인 필요"
        echo ""
        echo "💡 검증 방법:"
        echo "   1. 테스트 질문 실행"
        echo "   2. '문서를 찾을 수 없습니다' 에러 발생 시:"
        echo "      → Pinecone 재구축 필요"
        echo "      → docker exec -it knu-chatbot-app python src/modules/force_reembed.py"
        echo ""
    else
        echo "⚠️  백업은 유지됩니다: $BACKUP_NAME"
        echo ""
        echo "⚠️  중요: Pinecone-MongoDB 불일치 가능성!"
        echo "   크롤링이 실패했지만 Pinecone에는 벡터가 추가되었을 수 있습니다."
        echo ""
        echo "💡 권장 조치:"
        echo "   1. 테스트 질문으로 정상 작동 확인"
        echo "   2. 오류 발생 시 백업에서 복원:"
        echo "      ./scripts/restore-data.sh $BACKUP_NAME"
        echo "   3. 또는 Pinecone 재구축:"
        echo "      docker exec -it knu-chatbot-app python src/modules/force_reembed.py"
    fi
fi

echo ""
echo "========================================="
echo "🎉 작업 완료"
echo "========================================="
