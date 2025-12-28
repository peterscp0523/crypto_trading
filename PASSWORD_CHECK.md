# 🔑 Oracle DB 비밀번호 확인 필요

## 현재 상황

컨테이너의 환경변수:
- ORACLE_DB_PASSWORD=`CryptoTrading@2024!`

.env 파일:
- ORACLE_DB_PASSWORD=`Qtcw5469!`

**→ 비밀번호 불일치!**

## 확인 방법

Oracle Cloud Console에서 실제 비밀번호 확인:

1. Oracle Cloud Console 로그인
2. Autonomous Database → cryptodb 선택
3. Administrator Password 확인

## 해결 방법

### 옵션 1: GitHub Secret이 맞는 경우
그대로 두고 로컬 .env만 수정

### 옵션 2: .env가 맞는 경우
GitHub Secret 업데이트:
1. https://github.com/peterscp0523/crypto_trading/settings/secrets/actions
2. ORACLE_DB_PASSWORD → Update
3. 올바른 비밀번호 입력
4. Update secret

### 옵션 3: 비밀번호 재설정
Oracle Console에서 새 비밀번호 설정 후:
- GitHub Secret 업데이트
- 로컬 .env 업데이트

## 다음 단계

올바른 비밀번호 확인 후 알려주시면:
1. 로컬 .env 업데이트 (필요시)
2. GitHub Secret 업데이트 (필요시)
3. 재배포
