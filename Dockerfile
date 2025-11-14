# Python 3.11 slim 이미지 사용
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 환경변수 설정
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 시스템 패키지 업데이트 및 필수 도구 설치
RUN apt-get update && apt-get install -y \
    # Java (KoNLPy 필요)
    default-jdk \
    # 빌드 도구
    build-essential \
    gcc \
    g++ \
    make \
    automake \
    autoconf \
    libtool \
    pkg-config \
    # 네트워크 도구
    curl \
    wget \
    git \
    # 기타
    vim \
    && rm -rf /var/lib/apt/lists/*

# Mecab 설치 (한국어 형태소 분석기)
RUN echo "📦 Mecab 설치 중..." && \
    cd /tmp && \
    # Mecab-ko 다운로드 및 설치
    curl -LO https://bitbucket.org/eunjeon/mecab-ko/downloads/mecab-0.996-ko-0.9.2.tar.gz && \
    tar zxfv mecab-0.996-ko-0.9.2.tar.gz && \
    cd mecab-0.996-ko-0.9.2 && \
    ./configure && \
    make && \
    make check && \
    make install && \
    ldconfig && \
    # Mecab-ko-dic 다운로드 및 설치
    cd /tmp && \
    curl -LO https://bitbucket.org/eunjeon/mecab-ko-dic/downloads/mecab-ko-dic-2.1.1-20180720.tar.gz && \
    tar -zxvf mecab-ko-dic-2.1.1-20180720.tar.gz && \
    cd mecab-ko-dic-2.1.1-20180720 && \
    ./autogen.sh && \
    ./configure && \
    make && \
    make install && \
    # 정리
    cd / && \
    rm -rf /tmp/* && \
    echo "✅ Mecab 설치 완료!"

# 라이브러리 경로 설정
RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/mecab.conf && ldconfig

# requirements.txt 복사 및 Python 패키지 설치
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    echo "✅ Python 패키지 설치 완료!"

# NLTK 데이터 다운로드
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"

# 애플리케이션 코드 복사
COPY . .

# 로그 디렉토리 생성
RUN mkdir -p logs

# 포트 노출
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# 컨테이너 시작 명령
CMD ["python", "src/app.py"]
