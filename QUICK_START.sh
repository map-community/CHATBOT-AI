#!/bin/bash

echo "╔════════════════════════════════════════╗"
echo "║  KNU 챗봇 프로젝트 빠른 시작 가이드   ║"
echo "╚════════════════════════════════════════╝"
echo ""

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. 파일 복사 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  제공받은 파일 복사 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "src/modules/data_crawler.py" ] && [ -f "src/modules/ai_modules.py" ]; then
    echo -e "${GREEN}✅ 파일이 이미 복사되어 있습니다!${NC}"
else
    echo -e "${YELLOW}⚠️  파일 복사가 필요합니다!${NC}"
    echo ""
    echo "다음 2개 파일을 복사해주세요:"
    echo "  • 첫 번째 파일 (크롤링) → src/modules/data_crawler.py"
    echo "  • 두 번째 파일 (RAG)    → src/modules/ai_modules.py"
    echo ""
    echo "자세한 방법은 COPY_FILES_GUIDE.md를 참고하세요:"
    echo "  cat COPY_FILES_GUIDE.md"
    echo ""
    read -p "파일을 복사하셨나요? (y/n): " copied
    if [ "$copied" != "y" ]; then
        echo "파일을 먼저 복사한 후 다시 실행해주세요."
        exit 1
    fi
fi

# 2. 가상환경 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  가상환경 설정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "venv" ]; then
    echo -e "${GREEN}✅ 가상환경이 이미 존재합니다!${NC}"
else
    echo "가상환경을 생성합니다..."
    python3 -m venv venv
    echo -e "${GREEN}✅ 가상환경 생성 완료!${NC}"
fi

# 3. .env 파일 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  환경 변수 설정 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f ".env" ]; then
    echo -e "${GREEN}✅ .env 파일이 존재합니다!${NC}"
else
    echo -e "${YELLOW}⚠️  .env 파일이 없습니다!${NC}"
    echo ""
    read -p ".env 파일을 지금 생성하시겠습니까? (y/n): " create_env
    if [ "$create_env" = "y" ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ .env 파일이 생성되었습니다!${NC}"
        echo ""
        echo -e "${YELLOW}⚠️  중요: .env 파일을 열어 다음 값들을 입력하세요:${NC}"
        echo "  • PINECONE_API_KEY"
        echo "  • UPSTAGE_API_KEY"
        echo ""
        echo "편집: nano .env"
    else
        echo "나중에 .env 파일을 생성해주세요: cp .env.example .env"
    fi
fi

# 4. 의존성 설치
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  의존성 패키지 설치"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

read -p "의존성 패키지를 설치하시겠습니까? (y/n): " install_deps
if [ "$install_deps" = "y" ]; then
    echo "패키지 설치 중... (시간이 걸릴 수 있습니다)"
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('averaged_perceptron_tagger', quiet=True)"
    echo -e "${GREEN}✅ 패키지 설치 완료!${NC}"
fi

# 5. MongoDB/Redis 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  데이터베이스 서비스 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v systemctl &> /dev/null; then
    # MongoDB 확인
    if systemctl is-active --quiet mongodb || systemctl is-active --quiet mongod; then
        echo -e "${GREEN}✅ MongoDB가 실행 중입니다!${NC}"
    else
        echo -e "${YELLOW}⚠️  MongoDB가 실행 중이지 않습니다${NC}"
        echo "시작: sudo systemctl start mongodb"
    fi
    
    # Redis 확인
    if systemctl is-active --quiet redis || systemctl is-active --quiet redis-server; then
        echo -e "${GREEN}✅ Redis가 실행 중입니다!${NC}"
    else
        echo -e "${YELLOW}⚠️  Redis가 실행 중이지 않습니다${NC}"
        echo "시작: sudo systemctl start redis"
    fi
else
    echo "systemctl을 사용할 수 없습니다. 수동으로 서비스를 확인하세요."
fi

# 최종 요약
echo ""
echo "╔════════════════════════════════════════╗"
echo "║           설치 완료 요약               ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "✅ 완료된 작업:"
echo "  • 프로젝트 구조 생성"
echo "  • 설정 파일 생성"
echo ""
echo "📋 다음 단계:"
echo ""
echo "  1. .env 파일에 API 키 입력"
echo "     nano .env"
echo ""
echo "  2. MongoDB/Redis 시작 (필요시)"
echo "     sudo systemctl start mongodb"
echo "     sudo systemctl start redis"
echo ""
echo "  3. 초기 데이터 크롤링 (최초 1회)"
echo "     source venv/bin/activate"
echo "     python src/modules/data_crawler.py"
echo ""
echo "  4. 서버 실행"
echo "     python src/app.py"
echo ""
echo "  5. 테스트"
echo "     curl http://localhost:5000/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 자세한 내용은 다음 문서를 참고하세요:"
echo "  • START_HERE.md        - 시작 가이드"
echo "  • COPY_FILES_GUIDE.md  - 파일 복사 방법"
echo "  • SETUP_GUIDE.md       - 상세 설치 가이드"
echo "  • README.md            - 전체 문서"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

