# 🔧 Oracle DB 연결 문제 해결

## 현재 상황
- Wallet: ✅ 정상 압축 해제
- DSN: ✅ 올바른 리전 (ap-chuncheon-1:1522)
- Password: ✅ 업데이트 완료
- 에러: `DPY-6000: Listener refused connection (Similar to ORA-12506)`

## 가능한 원인

### 1. Oracle Database가 중지됨 (가장 가능성 높음)
Oracle Autonomous Database가 자동으로 중지되었을 수 있습니다.

**확인 방법:**
1. Oracle Cloud Console 로그인
2. Menu → Oracle Database → Autonomous Database
3. cryptodb 선택
4. State 확인:
   - 🟢 AVAILABLE → 정상
   - 🔴 STOPPED → 중지됨 (재시작 필요)

**해결:**
- STOPPED 상태일 경우:
  - "Start" 버튼 클릭
  - 5-10분 대기
  - 재배포

### 2. Wallet이 만료됨
Wallet은 일정 기간 후 만료될 수 있습니다.

**해결:**
1. Oracle Console → DB Connection
2. Download Wallet (새로운 wallet.zip)
3. 로컬에서 새 Base64 생성:
   ```bash
   base64 -i Wallet_NEW.zip | tr -d '\n' > wallet_base64_new.txt
   cat wallet_base64_new.txt | pbcopy
   ```
4. ORACLE_WALLET_BASE64 Secret 업데이트
5. 재배포

### 3. 네트워크/방화벽 문제
Oracle Cloud 방화벽이 접근을 차단하고 있을 수 있습니다.

**확인:**
- Oracle Console → Network → Security Lists
- Ingress Rules에 TCP 1522 포트 허용되어 있는지 확인

### 4. Service Name 불일치
tnsnames.ora의 service name이 실제와 다를 수 있습니다.

**현재 DSN:**
```
service_name=g32903972cf397b_cryptodb_high.adb.oraclecloud.com
```

**확인:**
- Oracle Console → Database Details
- Service Name이 일치하는지 확인

## 즉시 확인 가능한 방법

### Oracle Console에서 DB 상태 확인
가장 먼저 확인해야 할 것:

1. https://cloud.oracle.com/db/adb
2. cryptodb 찾기
3. **State** 열 확인:
   - AVAILABLE (초록색) → 정상, 다른 문제
   - STOPPED (빨간색) → **이것이 문제!** Start 클릭

## 다음 단계

1. **먼저**: Oracle Console에서 DB State 확인
2. STOPPED면: Start 버튼 클릭
3. AVAILABLE면: Wallet 재다운로드 시도

어느 쪽인지 알려주시면 즉시 해결하겠습니다!
