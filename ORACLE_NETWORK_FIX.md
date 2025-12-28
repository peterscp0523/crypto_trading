# 🔒 Oracle DB 네트워크 접근 허용 설정

## 문제: Zero Trust로 모든 접근 차단됨

현재 Oracle Autonomous Database가 Zero Trust 모드로 설정되어 있어서 
Oracle Cloud VM에서도 접근할 수 없습니다.

---

## ✅ 해결 방법

### 1. Oracle Cloud Console 접속
1. https://cloud.oracle.com/db/adb
2. **cryptodb** 클릭

### 2. Network 설정 변경
1. 왼쪽 메뉴에서 **"Network"** 또는 **"Security"** 클릭
2. **"Access Control List (ACL)"** 섹션 찾기

### 3. IP 주소 허용

**옵션 A: VM IP만 허용 (권장)**

Oracle Cloud VM의 Public IP 추가:
```
140.245.69.95/32
```

**옵션 B: 전체 허용 (간단하지만 보안 낮음)**

ACL을 **"Secure access from everywhere"**로 변경

---

## 🎯 권장 설정 (옵션 A)

### 단계별 가이드:

1. **Network 탭 클릭**
2. **Edit** 버튼 클릭 (Access Control 섹션)
3. **"IP notation type"** 선택: `IP Address`
4. **"Values"** 입력:
   ```
   140.245.69.95/32
   ```
5. **"Add My IP Address"** 체크 (선택사항 - 로컬에서도 접속)
6. **Save Changes** 클릭

### 설정 후:
- 적용까지 1-2분 소요
- 재배포 필요 없음 (자동 반영)

---

## 🔍 빠른 확인

설정 완료 후 VM에서 테스트:

```bash
# VM에서 Oracle DB 연결 테스트
ssh -i ~/.ssh/github_actions_oracle ubuntu@140.245.69.95 \
  "docker restart crypto-trading-bot && sleep 10 && \
   docker logs --tail 20 crypto-trading-bot | grep -i oracle"

# 성공 시:
# ✅ Oracle DB 연결 성공
# ✅ 데이터베이스 연동: Oracle Cloud
```

---

## 📊 예상 결과

설정 전:
```
⚠️ Oracle DB 연결 실패, SQLite 사용: 
DPY-6000: Listener refused connection
```

설정 후:
```
✅ Oracle DB 연결 성공
✅ 테이블 생성 완료
✅ 데이터베이스 연동: Oracle Cloud
```

---

## 🔐 보안 참고

- **140.245.69.95/32**: VM만 접근 가능 (가장 안전)
- **전체 허용**: 인터넷 어디서나 접근 가능 (편리하지만 위험)
- **Wallet 인증**: IP 허용 + Wallet 파일 모두 필요 (이중 보안)

권장: **VM IP만 허용** + Wallet 인증 (현재 설정)
