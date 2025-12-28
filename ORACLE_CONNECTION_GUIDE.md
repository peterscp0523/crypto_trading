# Oracle Cloud Database 연결 문제 해결 가이드

## 현재 상황

- ✅ Wallet: GitHub Actions에서 자동 추출
- ✅ 비밀번호: `CryptoTrading@2024!` (확인됨)
- ✅ DSN: ap-chuncheon-1 지역 (Wallet과 일치)
- ❌ **연결 실패**: `DPY-6000: Listener refused connection`

## 문제 원인: Network ACL (접근 제어 목록)

Oracle Autonomous Database는 기본적으로 **Zero Trust** 정책으로 모든 접근을 차단합니다.

## 해결 방법

### 1단계: Oracle Cloud Console 접속

1. https://cloud.oracle.com 로그인
2. 좌측 메뉴 > **Oracle Database** > **Autonomous Database**
3. `CryptoDB` (또는 해당 DB 이름) 클릭

### 2단계: Network ACL 설정 확인

1. DB 상세 페이지에서 **"Network"** 또는 **"Access Control List"** 섹션 찾기
2. 현재 설정 확인:
   - "Secure access from everywhere" → ❌ 모든 IP 차단
   - "Secure access from allowed IPs and VCNs only" → ✅ 특정 IP만 허용

### 3단계: VM IP 추가

**VM의 공인 IP**: `140.245.69.95`

두 가지 방법 중 선택:

#### 방법 A: 임시로 모든 IP 허용 (테스트용)

```
Access Type: Secure access from everywhere
```

⚠️ **보안 주의**: 테스트 후 반드시 특정 IP로 제한할 것

#### 방법 B: VM IP만 허용 (권장)

```
Access Type: Secure access from allowed IPs and VCNs only

IP Notation Type: IP Address
Values: 140.245.69.95/32
```

**만약 안 된다면 서브넷으로 시도:**
```
Values: 140.245.69.0/24
```

### 4단계: 변경사항 적용 대기

ACL 변경 후:
1. DB 상태가 **"Updating..."** 으로 변경됨
2. 5-10분 대기
3. DB 상태가 **"Available"** 이 될 때까지 기다림
4. ⚠️ **Available 상태가 되기 전에는 연결 불가**

### 5단계: 연결 테스트

#### VM에서 테스트 (GitHub Actions 사용)

`.github/workflows/test-oracle-db.yml` 파일 생성:

```yaml
name: Test Oracle DB Connection

on:
  workflow_dispatch:

jobs:
  test-connection:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install oracledb python-dotenv

      - name: Deploy and test on Oracle VM
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.ORACLE_HOST }}
          username: ${{ secrets.ORACLE_USERNAME }}
          key: ${{ secrets.ORACLE_SSH_KEY }}
          script: |
            # Wallet 설정
            mkdir -p /tmp/wallet
            echo "${{ secrets.ORACLE_WALLET_BASE64 }}" | base64 -d > /tmp/wallet.zip
            python3 -c 'import zipfile; zipfile.ZipFile("/tmp/wallet.zip").extractall("/tmp/wallet")'
            rm /tmp/wallet.zip

            # 테스트 스크립트 복사 및 실행
            cd /tmp
            cat > test_db.py << 'PYTHON_SCRIPT'
import oracledb
import os

user = "${{ secrets.ORACLE_DB_USER }}"
password = "${{ secrets.ORACLE_DB_PASSWORD }}"
dsn = "${{ secrets.ORACLE_DB_DSN }}"

try:
    conn = oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
        config_dir="/tmp/wallet",
        wallet_location="/tmp/wallet",
        wallet_password=None
    )
    print("✅✅✅ Oracle DB 연결 성공! ✅✅✅")
    cursor = conn.cursor()
    cursor.execute("SELECT 'Connected!' FROM DUAL")
    result = cursor.fetchone()
    print(f"테스트 쿼리 결과: {result[0]}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"❌ 연결 실패: {e}")
PYTHON_SCRIPT

            python3 test_db.py
```

이 워크플로우를 실행하여 VM에서 직접 연결 테스트를 할 수 있습니다.

## 추가 확인 사항

### 1. mTLS 설정 확인

Oracle Cloud Console > DB 상세 > **"Mutual TLS (mTLS)"** 섹션:
- **"Require mTLS authentication"**: ON (기본값) → Wallet 필수
- OFF로 변경 가능하지만 보안상 권장하지 않음

### 2. 방화벽 확인

VM의 아웃바운드 방화벽에서 포트 `1522` 허용 확인:

```bash
ssh opc@140.245.69.95
sudo iptables -L -n | grep 1522
```

### 3. DB 상태 확인

Oracle Cloud Console에서:
- **Lifecycle State**: AVAILABLE (녹색)
- **Infrastructure**: 모두 정상 (녹색 체크)

## 문제 해결 체크리스트

- [ ] ACL에 VM IP (140.245.69.95/32) 추가됨
- [ ] DB 상태가 "Available"로 변경됨 (5-10분 대기)
- [ ] Wallet 파일이 정상 추출됨 (cwallet.sso 존재)
- [ ] 비밀번호가 정확함 (CryptoTrading@2024!)
- [ ] DSN이 ap-chuncheon-1 지역 사용
- [ ] mTLS가 활성화되어 있음
- [ ] VM 방화벽이 1522 포트 허용

## 연결 성공 후

연결이 성공하면 봇이 자동으로 Oracle DB를 사용하여:
- 거래 내역 저장
- 파라미터 최적화 기록
- 성과 분석 데이터 축적

## 지원

문제가 계속되면:
1. Oracle Cloud Console에서 DB 로그 확인
2. VM에서 `test_oracle_connection.py` 실행하여 상세 에러 확인
3. GitHub Actions 로그에서 연결 시도 내역 확인
