"""
Flask Application for KNU Chatbot
"""
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging

# 설정 파일 임포트
try:
    from src.config import settings
    from src.modules.ai_modules import get_ai_message, initialize_cache
except ImportError as e:
    print(f"Import Error: {e}")
    print("Please make sure ai_modules.py is in src/modules/ directory")
    sys.exit(1)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_app():
    """Flask 애플리케이션 팩토리"""
    app = Flask(__name__)
    CORS(app)

    @app.route('/ai/ai-response', methods=['POST'])
    def ai_response():
        """AI 챗봇 응답 생성 엔드포인트"""
        try:
            # 요청 데이터 가져오기
            data = request.get_json()
            if not data:
                logger.warning("No JSON data provided")
                return jsonify({'error': 'No JSON data provided'}), 400

            # 'question' 필드 가져오기
            question = data.get('question')
            if not isinstance(question, str) or not question.strip():
                logger.warning(f"Invalid question: {question}")
                return jsonify({'error': 'Invalid or missing question'}), 400

            logger.info(f"Question received: {question}")

            # AI 응답 생성
            response = get_ai_message(question)

            logger.info(f"Response generated successfully")

            # JSON 객체로 응답 반환
            if isinstance(response, dict):
                return jsonify(response)
            else:
                logger.error("Invalid response format from AI module")
                return jsonify({'error': 'Invalid response format from AI module'}), 500

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/health', methods=['GET'])
    def health_check():
        """서버 상태 확인 엔드포인트"""
        return jsonify({
            'status': 'healthy',
            'message': 'KNU Chatbot Server is running',
            'version': '1.0.0'
        }), 200

    @app.route('/', methods=['GET'])
    def home():
        """홈 페이지"""
        return jsonify({
            'message': 'Welcome to KNU Chatbot API',
            'endpoints': {
                'POST /ai/ai-response': 'Send a question to the chatbot',
                'GET /health': 'Check server health',
            }
        })

    return app

if __name__ == "__main__":
    # 캐시 초기화
    logger.info("Initializing cache...")
    try:
        initialize_cache()
        logger.info("Cache initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize cache: {e}")
        logger.info("Continuing without cache...")

    # Flask 앱 생성
    app = create_app()

    # 서버 시작
    logger.info(f"Starting server on {settings.FLASK_HOST}:{settings.FLASK_PORT}")
    app.run(
        host=settings.FLASK_HOST,
        port=settings.FLASK_PORT,
        debug=settings.FLASK_DEBUG
    )
else:
    # WSGI 서버를 위한 초기화
    try:
        initialize_cache()
    except:
        pass
    app = create_app()
