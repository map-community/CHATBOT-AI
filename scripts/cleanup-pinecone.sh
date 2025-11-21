#!/bin/bash
# Pinecone-MongoDB 동기화 스크립트 (bash wrapper)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "🧹 Pinecone-MongoDB 동기화"
echo "========================================="
echo ""

# Docker 컨테이너에서 Python 스크립트 실행
if docker ps | grep -q "knu-chatbot-app"; then
    echo "🐳 Docker 컨테이너에서 실행 중..."
    docker exec -it knu-chatbot-app python scripts/cleanup-pinecone-sync.py "$@"
else
    echo "⚠️  Docker 컨테이너가 실행 중이 아닙니다."
    echo "   먼저 Docker를 시작해주세요:"
    echo "   docker compose up -d"
    exit 1
fi
