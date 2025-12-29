# Python 3.11 slim 이미지 사용
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 (oracledb는 추가 패키지 불필요)
RUN apt-get update && \
    rm -rf /var/lib/apt/lists/*

# Python 패키지 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY *.py ./

# 환경변수 설정 (타임존)
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 실행 권한 설정
RUN chmod +x upbit_20_200_bot.py

# 실제 거래 봇 실행 (20/200 SMA 전략)
CMD ["python", "-u", "upbit_20_200_bot.py", "live", "1"]
