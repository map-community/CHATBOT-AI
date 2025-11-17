#!/bin/bash

###############################################################################
# 로그 확인 스크립트
# 사용법:
#   ./scripts/view-logs.sh          # 모든 로그 실시간 보기
#   ./scripts/view-logs.sh app      # Flask 앱 로그만 보기
#   ./scripts/view-logs.sh mongodb  # MongoDB 로그만 보기
#   ./scripts/view-logs.sh redis    # Redis 로그만 보기
###############################################################################

SERVICE=$1

case $SERVICE in
  app|flask)
    echo "📱 Flask Application Logs (실시간)"
    echo "Press Ctrl+C to exit"
    docker logs -f knu-chatbot-app
    ;;

  mongo|mongodb)
    echo "🍃 MongoDB Logs (실시간)"
    echo "Press Ctrl+C to exit"
    docker logs -f knu-chatbot-mongodb
    ;;

  redis)
    echo "💾 Redis Logs (실시간)"
    echo "Press Ctrl+C to exit"
    docker logs -f knu-chatbot-redis
    ;;

  *)
    echo "📋 All Logs (실시간)"
    echo "Press Ctrl+C to exit"
    docker-compose logs -f
    ;;
esac
