# Python 3.11 slim 이미지 사용
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y gcc wget unzip libaio1 && \
    rm -rf /var/lib/apt/lists/*

# Oracle Instant Client 설치 (cx_Oracle 지원)
RUN wget -q https://download.oracle.com/otn_software/linux/instantclient/2111000/instantclient-basic-linux.x64-21.11.0.0.0dbru.zip \
    && mkdir -p /opt/oracle \
    && unzip -q instantclient-basic-linux.x64-21.11.0.0.0dbru.zip -d /opt/oracle \
    && rm instantclient-basic-linux.x64-21.11.0.0.0dbru.zip \
    && echo /opt/oracle/instantclient_21_11 > /etc/ld.so.conf.d/oracle-instantclient.conf \
    && ldconfig

# Oracle 환경변수 설정
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_21_11
ENV TNS_ADMIN=/app/wallet

# Python 패키지 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY *.py ./

# Wallet 디렉토리 생성 (외부 마운트용)
RUN mkdir -p /app/wallet

# 환경변수 설정 (타임존)
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 실행 권한 설정
RUN chmod +x telegram_bot.py

# 실제 거래 봇 실행 (기본값)
CMD ["python", "-u", "run_multi_coin.py"]
