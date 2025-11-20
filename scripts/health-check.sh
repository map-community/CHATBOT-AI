#!/bin/bash

# ========================================
# 애플리케이션 헬스 체크 스크립트
# ========================================

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 아이콘
CHECK="✓"
CROSS="✗"
INFO="ℹ"

# 상태 체크 함수
check_service() {
    local service_name=$1
    local command=$2

    if eval "$command" &> /dev/null; then
        echo -e "${GREEN}${CHECK}${NC} $service_name: ${GREEN}정상${NC}"
        return 0
    else
        echo -e "${RED}${CROSS}${NC} $service_name: ${RED}실패${NC}"
        return 1
    fi
}

echo "========================================="
echo "  KNU Chatbot 헬스 체크"
echo "========================================="
echo ""

TOTAL_CHECKS=0
PASSED_CHECKS=0

# 1. Docker 체크
echo -e "${BLUE}[Docker]${NC}"
if check_service "Docker 서비스" "systemctl is-active --quiet docker"; then
    ((PASSED_CHECKS++))
fi
((TOTAL_CHECKS++))
echo ""

# 2. 컨테이너 체크
echo -e "${BLUE}[컨테이너 상태]${NC}"

if check_service "MongoDB 컨테이너" "docker ps | grep -q knu-chatbot-mongodb"; then
    ((PASSED_CHECKS++))
fi
((TOTAL_CHECKS++))

if check_service "Redis 컨테이너" "docker ps | grep -q knu-chatbot-redis"; then
    ((PASSED_CHECKS++))
fi
((TOTAL_CHECKS++))

if check_service "App 컨테이너" "docker ps | grep -q knu-chatbot-app"; then
    ((PASSED_CHECKS++))
fi
((TOTAL_CHECKS++))
echo ""

# 3. 서비스 헬스 체크
echo -e "${BLUE}[서비스 응답]${NC}"

if check_service "MongoDB 연결" "docker exec knu-chatbot-mongodb mongosh --eval 'db.adminCommand(\"ping\")' --quiet"; then
    ((PASSED_CHECKS++))
fi
((TOTAL_CHECKS++))

if check_service "Redis 연결" "docker exec knu-chatbot-redis redis-cli ping"; then
    ((PASSED_CHECKS++))
fi
((TOTAL_CHECKS++))

if check_service "App 헬스 체크" "curl -sf http://localhost:5000/health"; then
    ((PASSED_CHECKS++))
fi
((TOTAL_CHECKS++))
echo ""

# 4. 리소스 체크
echo -e "${BLUE}[리소스 사용량]${NC}"

# 메모리 사용량
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
echo -e "${INFO} 메모리 사용률: ${MEMORY_USAGE}%"

# 디스크 사용량
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
echo -e "${INFO} 디스크 사용률: ${DISK_USAGE}%"

# Docker 컨테이너 리소스
echo -e "${INFO} Docker 컨테이너 리소스:"
docker stats --no-stream --format "  - {{.Name}}: CPU {{.CPUPerc}} | MEM {{.MemUsage}}" | grep knu-chatbot
echo ""

# 5. 데이터 크기 체크
echo -e "${BLUE}[데이터 크기]${NC}"

if [ -d "/opt/knu-chatbot/data/mongodb" ]; then
    MONGODB_SIZE=$(du -sh /opt/knu-chatbot/data/mongodb 2>/dev/null | cut -f1)
    echo -e "${INFO} MongoDB 데이터: ${MONGODB_SIZE}"
fi

if [ -d "/opt/knu-chatbot/data/redis" ]; then
    REDIS_SIZE=$(du -sh /opt/knu-chatbot/data/redis 2>/dev/null | cut -f1)
    echo -e "${INFO} Redis 데이터: ${REDIS_SIZE}"
fi

if [ -d "/opt/knu-chatbot/logs" ]; then
    LOGS_SIZE=$(du -sh /opt/knu-chatbot/logs 2>/dev/null | cut -f1)
    echo -e "${INFO} 로그 크기: ${LOGS_SIZE}"
fi
echo ""

# 6. 최근 로그 에러 체크
echo -e "${BLUE}[최근 에러 로그]${NC}"
if [ -f "/opt/knu-chatbot/logs/app.log" ]; then
    ERROR_COUNT=$(grep -c "ERROR" /opt/knu-chatbot/logs/app.log 2>/dev/null || echo 0)
    echo -e "${INFO} 총 에러 수: ${ERROR_COUNT}"

    echo -e "${INFO} 최근 에러 (최대 3개):"
    grep "ERROR" /opt/knu-chatbot/logs/app.log 2>/dev/null | tail -3 | while read line; do
        echo "  $line"
    done || echo "  (에러 없음)"
else
    echo -e "${YELLOW}${INFO}${NC} 로그 파일을 찾을 수 없습니다."
fi
echo ""

# 결과 요약
echo "========================================="
echo -e "  결과: ${PASSED_CHECKS}/${TOTAL_CHECKS} 체크 통과"

if [ $PASSED_CHECKS -eq $TOTAL_CHECKS ]; then
    echo -e "  상태: ${GREEN}모든 서비스 정상${NC}"
    echo "========================================="
    exit 0
elif [ $PASSED_CHECKS -ge $((TOTAL_CHECKS * 2 / 3)) ]; then
    echo -e "  상태: ${YELLOW}일부 서비스 비정상${NC}"
    echo "========================================="
    exit 1
else
    echo -e "  상태: ${RED}심각한 문제 발생${NC}"
    echo "========================================="
    exit 2
fi
