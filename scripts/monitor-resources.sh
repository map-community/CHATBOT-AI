#!/bin/bash

# ========================================
# 리소스 사용량 실시간 모니터링
# ========================================

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 경고 임계값
CPU_WARNING=80
MEMORY_WARNING=80
DISK_WARNING=85

# 헤더 출력
print_header() {
    clear
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}  KNU Chatbot 리소스 모니터링${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo -e "시간: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
}

# CPU 사용률 체크
check_cpu() {
    echo -e "${CYAN}[CPU 사용률]${NC}"

    # 전체 CPU 사용률
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
    CPU_INT=${CPU_USAGE%.*}

    if [ "$CPU_INT" -ge "$CPU_WARNING" ]; then
        echo -e "  ${RED}⚠ ${CPU_USAGE}%${NC} (경고!)"
    else
        echo -e "  ${GREEN}✓ ${CPU_USAGE}%${NC}"
    fi

    # 코어별 사용률
    echo -e "\n  코어별 사용률:"
    mpstat -P ALL 1 1 | grep -v "^Average" | tail -n +4 | awk '{printf "    CPU %s: %s%%\n", $2, 100-$NF}'
    echo ""
}

# 메모리 사용량 체크
check_memory() {
    echo -e "${CYAN}[메모리 사용량]${NC}"

    # 메모리 정보
    MEM_INFO=$(free -h | grep "Mem:")
    MEM_TOTAL=$(echo $MEM_INFO | awk '{print $2}')
    MEM_USED=$(echo $MEM_INFO | awk '{print $3}')
    MEM_FREE=$(echo $MEM_INFO | awk '{print $4}')
    MEM_AVAILABLE=$(echo $MEM_INFO | awk '{print $7}')

    # 사용률 계산
    MEM_PERCENT=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    MEM_PERCENT_INT=${MEM_PERCENT%.*}

    if [ "$MEM_PERCENT_INT" -ge "$MEMORY_WARNING" ]; then
        echo -e "  ${RED}⚠ ${MEM_USED} / ${MEM_TOTAL} (${MEM_PERCENT}%)${NC} - 경고!"
    else
        echo -e "  ${GREEN}✓ ${MEM_USED} / ${MEM_TOTAL} (${MEM_PERCENT}%)${NC}"
    fi

    echo -e "  여유 메모리: ${MEM_AVAILABLE}"

    # Swap 메모리
    SWAP_INFO=$(free -h | grep "Swap:")
    SWAP_TOTAL=$(echo $SWAP_INFO | awk '{print $2}')
    SWAP_USED=$(echo $SWAP_INFO | awk '{print $3}')

    if [ "$SWAP_TOTAL" != "0B" ]; then
        echo -e "  Swap: ${SWAP_USED} / ${SWAP_TOTAL}"
    fi
    echo ""
}

# 디스크 사용량 체크
check_disk() {
    echo -e "${CYAN}[디스크 사용량]${NC}"

    # 루트 파티션
    DISK_INFO=$(df -h / | tail -1)
    DISK_TOTAL=$(echo $DISK_INFO | awk '{print $2}')
    DISK_USED=$(echo $DISK_INFO | awk '{print $3}')
    DISK_PERCENT=$(echo $DISK_INFO | awk '{print $5}' | sed 's/%//')

    if [ "$DISK_PERCENT" -ge "$DISK_WARNING" ]; then
        echo -e "  ${RED}⚠ ${DISK_USED} / ${DISK_TOTAL} (${DISK_PERCENT}%)${NC} - 경고!"
    else
        echo -e "  ${GREEN}✓ ${DISK_USED} / ${DISK_TOTAL} (${DISK_PERCENT}%)${NC}"
    fi

    # Docker 볼륨 크기
    if [ -d "/opt/knu-chatbot/data" ]; then
        DATA_SIZE=$(du -sh /opt/knu-chatbot/data 2>/dev/null | cut -f1)
        echo -e "  데이터 디렉토리: ${DATA_SIZE}"
    fi

    if [ -d "/opt/knu-chatbot/logs" ]; then
        LOGS_SIZE=$(du -sh /opt/knu-chatbot/logs 2>/dev/null | cut -f1)
        echo -e "  로그 디렉토리: ${LOGS_SIZE}"
    fi
    echo ""
}

# Docker 컨테이너 리소스
check_docker() {
    echo -e "${CYAN}[Docker 컨테이너 리소스]${NC}"

    if ! command -v docker &> /dev/null; then
        echo -e "  ${YELLOW}Docker가 설치되지 않았습니다${NC}"
        return
    fi

    # Docker가 실행 중인지 확인
    if ! docker ps &> /dev/null; then
        echo -e "  ${YELLOW}Docker가 실행되지 않았습니다${NC}"
        return
    fi

    # 컨테이너별 리소스 사용량
    echo -e "  ${BLUE}컨테이너별 사용량:${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}" | \
        grep -E "knu-chatbot|NAME" | \
        while IFS= read -r line; do
            if [[ $line == NAME* ]]; then
                echo -e "    ${line}"
            else
                # 메모리 % 추출
                MEM_PERC=$(echo "$line" | awk '{print $4}' | sed 's/%//')
                if [ ! -z "$MEM_PERC" ] && [ "$MEM_PERC" -ge "70" ] 2>/dev/null; then
                    echo -e "    ${YELLOW}${line}${NC}"
                else
                    echo -e "    ${line}"
                fi
            fi
        done
    echo ""
}

# 프로세스별 메모리 사용량 (Top 5)
check_top_processes() {
    echo -e "${CYAN}[메모리 사용량 Top 5 프로세스]${NC}"
    ps aux --sort=-%mem | head -n 6 | tail -n 5 | \
        awk '{printf "  %s: %s%% (PID: %s)\n", substr($11,1,40), $4, $2}'
    echo ""
}

# 네트워크 연결 확인
check_network() {
    echo -e "${CYAN}[네트워크 연결]${NC}"

    # 포트 리스닝 확인
    echo -e "  리스닝 포트:"
    netstat -tuln 2>/dev/null | grep LISTEN | grep -E ":5000|:27017|:6379|:80|:443" | \
        awk '{print "    "$4}' | sort -u || \
    ss -tuln 2>/dev/null | grep LISTEN | grep -E ":5000|:27017|:6379|:80|:443" | \
        awk '{print "    "$5}' | sort -u
    echo ""
}

# 메인 루프
main() {
    # 모니터링 모드 (1회 / 연속)
    MODE=${1:-once}
    INTERVAL=${2:-5}

    while true; do
        print_header
        check_cpu
        check_memory
        check_disk
        check_docker
        check_top_processes
        check_network

        echo -e "${BLUE}=========================================${NC}"

        if [ "$MODE" == "once" ]; then
            echo ""
            echo "연속 모니터링: $0 watch [간격(초)]"
            echo "예: $0 watch 5"
            break
        else
            echo -e "다음 업데이트: ${INTERVAL}초 후 (Ctrl+C로 종료)"
            echo -e "${BLUE}=========================================${NC}"
            sleep $INTERVAL
        fi
    done
}

# 사용법
if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    echo "사용법:"
    echo "  $0              # 1회 실행"
    echo "  $0 watch [초]   # 연속 모니터링 (기본 5초)"
    echo ""
    echo "예시:"
    echo "  $0              # 현재 상태 확인"
    echo "  $0 watch        # 5초마다 업데이트"
    echo "  $0 watch 10     # 10초마다 업데이트"
    exit 0
fi

# mpstat 설치 확인
if ! command -v mpstat &> /dev/null; then
    echo "⚠️  mpstat이 설치되지 않았습니다. CPU 코어별 통계를 보려면 설치하세요:"
    echo "   sudo apt install -y sysstat"
    echo ""
fi

# 실행
main "$@"
