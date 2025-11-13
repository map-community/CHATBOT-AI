#!/bin/bash

echo "🚀 KNU Chatbot 설치 스크립트"
echo "=============================="

# 1. 가상환경 생성
echo "📦 1. 가상환경 생성 중..."
python3 -m venv venv
source venv/bin/activate

# 2. pip 업그레이드
echo "⬆️  2. pip 업그레이드 중..."
pip install --upgrade pip

# 3. 의존성 설치
echo "📚 3. 의존성 패키지 설치 중..."
pip install -r requirements.txt

# 4. NLTK 데이터 다운로드
echo "📥 4. NLTK 데이터 다운로드 중..."
python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"

# 5. .env 파일 확인
if [ ! -f .env ]; then
    echo "⚠️  5. .env 파일이 없습니다. .env.example을 복사하여 .env를 생성하세요."
    echo "   cp .env.example .env"
    echo "   그 후, .env 파일을 열어 API 키를 입력하세요."
else
    echo "✅ 5. .env 파일이 존재합니다."
fi

# 6. MongoDB 및 Redis 상태 확인
echo "🔍 6. 서비스 상태 확인..."
if command -v systemctl &> /dev/null; then
    echo "  MongoDB 상태:"
    systemctl is-active mongodb || systemctl is-active mongod || echo "  ⚠️  MongoDB가 실행 중이지 않습니다."
    echo "  Redis 상태:"
    systemctl is-active redis || systemctl is-active redis-server || echo "  ⚠️  Redis가 실행 중이지 않습니다."
fi

echo ""
echo "✅ 설치가 완료되었습니다!"
echo ""
echo "다음 단계:"
echo "1. .env 파일에 API 키 입력"
echo "2. MongoDB와 Redis 서비스 시작"
echo "3. python src/modules/data_crawler.py (최초 데이터 크롤링)"
echo "4. python src/app.py (서버 실행)"
