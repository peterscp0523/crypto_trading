FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 라이브러리 설치
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir pyupbit pandas numpy requests

# 애플리케이션 코드 복사
COPY upbit_hybrid_bot.py .
COPY upbit_api.py .

# 환경변수 설정
ENV PYTHONUNBUFFERED=1

# 봇 실행
CMD ["python", "-u", "upbit_hybrid_bot.py"]
