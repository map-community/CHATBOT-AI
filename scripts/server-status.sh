#!/bin/bash

###############################################################################
# 서버 상태 확인 스크립트
# 사용법: ./scripts/server-status.sh
###############################################################################

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "📊 KNU Chatbot Server Status"
echo "========================================="
echo "Time: $(date)"
echo ""

# 1. Docker 상태
echo "${GREEN}[1] Docker Status${NC}"
echo "-------------------"
docker --version
docker compose version
echo ""

# 2. 컨테이너 상태
echo "${GREEN}[2] Container Status${NC}"
echo "-------------------"
docker compose ps
echo ""

# 3. 디스크 사용량
echo "${GREEN}[3] Disk Usage${NC}"
echo "-------------------"
df -h | grep -E '^Filesystem|/$'
echo ""

# 4. 메모리 사용량
echo "${GREEN}[4] Memory Usage${NC}"
echo "-------------------"
free -h
echo ""

# 5. CPU 사용량
echo "${GREEN}[5] CPU Usage${NC}"
echo "-------------------"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print "CPU Usage: " 100 - $1"%"}'
echo ""

# 6. 네트워크 연결
echo "${GREEN}[6] Network Connections${NC}"
echo "-------------------"
netstat -tuln | grep -E ':5000|:27017|:6379' || echo "No active connections on monitored ports"
echo ""

# 7. 헬스체크
echo "${GREEN}[7] Application Health Check${NC}"
echo "-------------------"
HEALTH_RESPONSE=$(curl -s http://localhost:5000/health 2>/dev/null)

if [ $? -eq 0 ]; then
    echo "✅ Health check successful!"
    echo "Response: $HEALTH_RESPONSE"
else
    echo "❌ Health check failed!"
fi
echo ""

# 8. 최근 로그 (마지막 10줄)
echo "${GREEN}[8] Recent Logs${NC}"
echo "-------------------"
echo "${YELLOW}MongoDB:${NC}"
docker logs knu-chatbot-mongodb --tail 3 2>/dev/null || echo "Container not running"
echo ""
echo "${YELLOW}Redis:${NC}"
docker logs knu-chatbot-redis --tail 3 2>/dev/null || echo "Container not running"
echo ""
echo "${YELLOW}Flask App:${NC}"
docker logs knu-chatbot-app --tail 5 2>/dev/null || echo "Container not running"
echo ""

echo "========================================="
echo "✅ Status check complete!"
echo "========================================="
