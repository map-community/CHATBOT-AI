#!/bin/bash
# 로컬 MongoDB 데이터를 EC2로 안전하게 동기화
# 사용법: ./scripts/sync-to-ec2.sh

set -e

# 설정 (필요시 수정)
EC2_KEY="${EC2_KEY:-$HOME/knu-chatbot-key.pem}"
EC2_USER="${EC2_USER:-ubuntu}"
EC2_HOST="${EC2_HOST:-3.39.153.45}"
EC2_PATH="${EC2_PATH:-/opt/knu-chatbot/CHATBOT-AI}"

echo "========================================="
echo "🚀 로컬 → EC2 데이터 동기화"
echo "========================================="
echo "방법: mongodump (안전, 서비스 중단 없음)"
echo ""

# SSH 키 확인
if [ ! -f "$EC2_KEY" ]; then
    echo "❌ SSH 키를 찾을 수 없습니다: $EC2_KEY"
    echo "   EC2_KEY 환경변수를 설정하거나 스크립트를 수정하세요."
    exit 1
fi

# 1. 로컬에서 MongoDB 덤프
echo "1️⃣  로컬 MongoDB 덤프 생성 중..."
docker exec knu-chatbot-mongodb mongodump --out=/dump --db=knu_chatbot

# 2. 덤프 파일을 Windows/Linux로 복사
echo "2️⃣  덤프 파일 추출 중..."
rm -rf ./mongo-dump-temp
docker cp knu-chatbot-mongodb:/dump ./mongo-dump-temp

# 3. EC2로 전송
echo "3️⃣  EC2로 전송 중..."
rsync -avz --progress \
  -e "ssh -i $EC2_KEY" \
  ./mongo-dump-temp/ \
  $EC2_USER@$EC2_HOST:/tmp/mongo-dump/

# 4. EC2에서 복원
echo "4️⃣  EC2에서 복원 중..."
ssh -i "$EC2_KEY" $EC2_USER@$EC2_HOST << EOF
  cd $EC2_PATH

  # 덤프를 MongoDB 컨테이너로 복사
  docker cp /tmp/mongo-dump knu-chatbot-mongodb:/dump

  # MongoDB에 복원 (--drop: 기존 데이터 삭제 후 복원)
  docker exec knu-chatbot-mongodb mongorestore --db=knu_chatbot /dump/knu_chatbot --drop

  # 임시 파일 정리
  rm -rf /tmp/mongo-dump

  echo "✅ EC2 복원 완료!"
EOF

# 5. 로컬 임시 파일 정리
echo "5️⃣  로컬 임시 파일 정리 중..."
rm -rf ./mongo-dump-temp

echo ""
echo "========================================="
echo "✅ 동기화 완료!"
echo "========================================="
echo "EC2 주소: http://$EC2_HOST:5000"
echo ""
echo "💡 확인 방법:"
echo "   ssh -i $EC2_KEY $EC2_USER@$EC2_HOST"
echo "   docker logs -f knu-chatbot-app"
echo ""
