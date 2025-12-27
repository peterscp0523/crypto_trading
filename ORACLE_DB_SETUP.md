# Oracle Cloud Always Free Tier Database 설정 가이드

## 1. Oracle Cloud Autonomous Database 생성

### Always Free Tier 생성
1. Oracle Cloud 계정 로그인 (https://cloud.oracle.com)
2. **Oracle Database** → **Autonomous Database** 메뉴 이동
3. **Create Autonomous Database** 클릭

### 설정값
- **Compartment**: 기본 compartment
- **Display name**: `crypto-trading-db`
- **Database name**: `cryptodb`
- **Workload type**: Transaction Processing (ATP)
- **Deployment type**: Serverless
- **Always Free 옵션 활성화** ✅
- **OCPU count**: 1 (Always Free 기본값)
- **Storage**: 20GB (Always Free 기본값)
- **Admin password**: 강력한 비밀번호 설정 (예: `MyP@ssw0rd123!`)
- **Network access**: Secure access from everywhere (개발 시)
- **License type**: License Included

생성 완료까지 약 2-3분 소요

---

## 2. Wallet 다운로드 및 설정

### Wallet 다운로드
1. 생성된 데이터베이스 클릭
2. **DB Connection** 버튼 클릭
3. **Wallet Type**: Instance Wallet 선택
4. **Download Wallet** 클릭
5. Wallet 비밀번호 설정 (예: `WalletP@ss123`)
6. `Wallet_cryptodb.zip` 파일 저장

### Wallet 파일 업로드 (Oracle VM)
```bash
# 로컬에서 Oracle VM으로 Wallet 업로드
scp -i ~/.ssh/oracle_key Wallet_cryptodb.zip ubuntu@<ORACLE_VM_IP>:/home/ubuntu/

# VM에 접속
ssh -i ~/.ssh/oracle_key ubuntu@<ORACLE_VM_IP>

# Wallet 디렉토리 생성 및 압축 해제
mkdir -p /home/ubuntu/oracle_wallet
cd /home/ubuntu/oracle_wallet
unzip /home/ubuntu/Wallet_cryptodb.zip
```

### 환경변수 설정
```bash
# VM에서 실행
export TNS_ADMIN=/home/ubuntu/oracle_wallet
export LD_LIBRARY_PATH=/usr/lib/oracle/21/client64/lib:$LD_LIBRARY_PATH
```

---

## 3. Connection String 확인

### tnsnames.ora 확인
Wallet 압축 해제 후 `tnsnames.ora` 파일에서 연결 문자열 확인:

```bash
cat /home/ubuntu/oracle_wallet/tnsnames.ora
```

**예시 출력:**
```
cryptodb_high = (description= (retry_count=20)(retry_delay=3)
  (address=(protocol=tcps)(port=1522)(host=adb.ap-seoul-1.oraclecloud.com))
  (connect_data=(service_name=xxx_cryptodb_high.adb.oraclecloud.com))
  (security=(ssl_server_dn_match=yes)))

cryptodb_medium = ...
cryptodb_low = ...
```

### DSN 선택
- **high**: 최고 성능 (동시 접속 적음)
- **medium**: 중간 성능
- **low**: 낮은 성능 (많은 동시 접속)

**권장**: `cryptodb_medium` 또는 `cryptodb_low`

---

## 4. Oracle Instant Client 설치 (VM)

### Ubuntu 기준 설치
```bash
# Oracle Instant Client 다운로드
wget https://download.oracle.com/otn_software/linux/instantclient/2111000/instantclient-basic-linux.x64-21.11.0.0.0dbru.zip

# 압축 해제
sudo mkdir -p /usr/lib/oracle/21/client64
cd /usr/lib/oracle/21/client64
sudo unzip ~/instantclient-basic-linux.x64-21.11.0.0.0dbru.zip
sudo mv instantclient_21_11/* .
sudo rmdir instantclient_21_11

# 라이브러리 경로 설정
sudo sh -c "echo /usr/lib/oracle/21/client64/lib > /etc/ld.so.conf.d/oracle-instantclient.conf"
sudo ldconfig

# 설치 확인
ls /usr/lib/oracle/21/client64/lib
```

---

## 5. GitHub Secrets 설정

### Repository Settings → Secrets and variables → Actions

다음 Secret 추가:

| Secret Name | Value | 설명 |
|------------|-------|------|
| `ORACLE_DB_USER` | `ADMIN` | 기본 관리자 계정 |
| `ORACLE_DB_PASSWORD` | `MyP@ssw0rd123!` | DB 생성 시 설정한 비밀번호 |
| `ORACLE_DB_DSN` | `cryptodb_medium` | tnsnames.ora의 연결 이름 |
| `ORACLE_WALLET_BASE64` | `<base64 인코딩된 Wallet.zip>` | 아래 참조 |

### Wallet Base64 인코딩
```bash
# 로컬에서 실행
base64 -i Wallet_cryptodb.zip | pbcopy  # macOS
base64 -w 0 Wallet_cryptodb.zip         # Linux
```

출력된 긴 문자열을 `ORACLE_WALLET_BASE64` Secret에 저장

---

## 6. Dockerfile 수정

```dockerfile
FROM python:3.11-slim

# Oracle Instant Client 설치
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

# Oracle Instant Client 다운로드 및 설치
RUN wget https://download.oracle.com/otn_software/linux/instantclient/2111000/instantclient-basic-linux.x64-21.11.0.0.0dbru.zip \
    && mkdir -p /opt/oracle \
    && unzip instantclient-basic-linux.x64-21.11.0.0.0dbru.zip -d /opt/oracle \
    && rm instantclient-basic-linux.x64-21.11.0.0.0dbru.zip

# 환경변수 설정
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_21_11:$LD_LIBRARY_PATH
ENV TNS_ADMIN=/app/wallet

WORKDIR /app

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# Wallet 디렉토리 생성
RUN mkdir -p /app/wallet

CMD ["python", "run_multi_coin.py"]
```

---

## 7. GitHub Actions 배포 스크립트 수정

`.github/workflows/deploy.yml`:

```yaml
- name: Deploy to Oracle Cloud
  uses: appleboy/ssh-action@v1.0.3
  with:
    host: ${{ secrets.ORACLE_HOST }}
    username: ${{ secrets.ORACLE_USERNAME }}
    key: ${{ secrets.ORACLE_SSH_KEY }}
    script: |
      # Wallet 디렉토리 생성
      mkdir -p /tmp/wallet

      # Wallet 파일 디코딩 및 압축 해제
      echo "${{ secrets.ORACLE_WALLET_BASE64 }}" | base64 -d > /tmp/wallet.zip
      unzip -o /tmp/wallet.zip -d /tmp/wallet

      # Docker 이미지 로드
      gunzip -c /tmp/crypto-bot.tar.gz | docker load

      # 기존 컨테이너 중지
      docker stop crypto-trading-bot || true
      docker rm crypto-trading-bot || true

      # 새 컨테이너 실행
      docker run -d \
        --name crypto-trading-bot \
        --restart unless-stopped \
        -v /tmp/wallet:/app/wallet \
        -e UPBIT_ACCESS_KEY="${{ secrets.UPBIT_ACCESS_KEY }}" \
        -e UPBIT_SECRET_KEY="${{ secrets.UPBIT_SECRET_KEY }}" \
        -e TELEGRAM_TOKEN="${{ secrets.TELEGRAM_TOKEN }}" \
        -e TELEGRAM_CHAT_ID="${{ secrets.TELEGRAM_CHAT_ID }}" \
        -e MARKET="${{ secrets.MARKET }}" \
        -e CHECK_INTERVAL="${{ secrets.CHECK_INTERVAL }}" \
        -e ENABLE_MULTI_COIN="true" \
        -e USE_ORACLE_DB="true" \
        -e ORACLE_DB_USER="${{ secrets.ORACLE_DB_USER }}" \
        -e ORACLE_DB_PASSWORD="${{ secrets.ORACLE_DB_PASSWORD }}" \
        -e ORACLE_DB_DSN="${{ secrets.ORACLE_DB_DSN }}" \
        -e TNS_ADMIN="/app/wallet" \
        crypto-trading-bot:latest

      # 정리
      rm /tmp/crypto-bot.tar.gz
      rm /tmp/wallet.zip

      # 로그 확인
      docker logs --tail 50 crypto-trading-bot
```

---

## 8. 로컬 개발 환경 설정

### .env 파일
```bash
# Oracle DB (선택적 - 로컬은 SQLite 사용 권장)
USE_ORACLE_DB=false
ORACLE_DB_USER=ADMIN
ORACLE_DB_PASSWORD=MyP@ssw0rd123!
ORACLE_DB_DSN=cryptodb_medium
TNS_ADMIN=/path/to/wallet
```

### 로컬 테스트 (SQLite)
```bash
# SQLite로 테스트
python database_manager.py
python data_collector.py
python auto_optimizer.py
```

---

## 9. 데이터 수집 및 최적화 스케줄러 실행

### 별도 컨테이너로 실행 (권장)

**데이터 수집기:**
```bash
docker run -d \
  --name crypto-data-collector \
  --restart unless-stopped \
  -v /tmp/wallet:/app/wallet \
  -e UPBIT_ACCESS_KEY="..." \
  -e UPBIT_SECRET_KEY="..." \
  -e USE_ORACLE_DB="true" \
  -e ORACLE_DB_USER="..." \
  -e ORACLE_DB_PASSWORD="..." \
  -e ORACLE_DB_DSN="cryptodb_medium" \
  -e RUN_DATA_COLLECTOR="true" \
  crypto-trading-bot:latest \
  python data_collector.py
```

**자동 최적화:**
```bash
docker run -d \
  --name crypto-auto-optimizer \
  --restart unless-stopped \
  -v /tmp/wallet:/app/wallet \
  -e USE_ORACLE_DB="true" \
  -e ORACLE_DB_USER="..." \
  -e ORACLE_DB_PASSWORD="..." \
  -e ORACLE_DB_DSN="cryptodb_medium" \
  -e MARKET="KRW-ETH" \
  -e RUN_AUTO_OPTIMIZER="true" \
  crypto-trading-bot:latest \
  python auto_optimizer.py
```

---

## 10. 데이터베이스 초기화

### 테이블 자동 생성
테이블은 `database_manager.py` 실행 시 자동으로 생성됩니다.

### 수동 확인 (SQL Developer 또는 SQL*Plus)
```sql
-- 연결 확인
SELECT 'Connected to Oracle DB!' FROM DUAL;

-- 테이블 목록 확인
SELECT table_name FROM user_tables;

-- 캔들 데이터 확인
SELECT market, timeframe, COUNT(*)
FROM candles
GROUP BY market, timeframe;

-- 거래 기록 확인
SELECT market, trade_type, COUNT(*)
FROM trades
GROUP BY market, trade_type;

-- 최적 파라미터 확인
SELECT market, optimization_date, quick_profit, take_profit_1, is_active
FROM parameter_history
WHERE is_active = 1;
```

---

## 11. 트러블슈팅

### cx_Oracle 연결 오류
```
DPI-1047: Cannot locate a 64-bit Oracle Client library
```
**해결**: Oracle Instant Client 재설치 및 `LD_LIBRARY_PATH` 확인

### Wallet 인증 오류
```
ORA-12578: TNS:wallet open failed
```
**해결**: `TNS_ADMIN` 환경변수가 Wallet 디렉토리를 정확히 가리키는지 확인

### 네트워크 접근 오류
```
ORA-12170: TNS:Connect timeout occurred
```
**해결**: Oracle Cloud 데이터베이스의 Network Access 설정에서 VM IP 허용

---

## 12. 비용 확인

### Always Free Tier 한도
- ✅ **Autonomous Database**: 2개 (각 1 OCPU, 20GB)
- ✅ **Compute VM**: 2개 (ARM 기반, 각 1 OCPU, 6GB RAM)
- ✅ **Block Storage**: 200GB
- ✅ **Object Storage**: 20GB

**주의**: Always Free 리소스를 초과하면 과금됩니다!

### 비용 모니터링
Oracle Cloud Console → **Billing & Cost Management** → **Cost Analysis**

---

## 완료!

데이터베이스 설정이 완료되었습니다. 이제 트레이딩 봇이:
1. 📊 1시간마다 캔들 데이터를 DB에 저장
2. 📈 모든 거래를 DB에 기록
3. 🔍 7일마다 자동으로 파라미터 최적화
4. ⚙️ 최적화된 파라미터를 자동으로 적용합니다!
