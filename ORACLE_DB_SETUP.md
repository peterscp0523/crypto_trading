# Oracle Cloud Database 연결 설정

## 📋 필요한 정보

`.env` 파일에 다음 정보를 입력해야 합니다:

### 1. ORACLE_DB_PASSWORD
- Oracle Cloud Console → Autonomous Database → 생성 시 설정한 ADMIN 비밀번호
- GitHub Secrets: `ORACLE_DB_PASSWORD`

### 2. ORACLE_DB_DSN
- 형식: `(description= (retry_count=20)(retry_delay=3)...)`
- Oracle Cloud Console → Autonomous Database → DB Connection → Connection Strings
- Wallet.zip 안의 `tnsnames.ora` 파일에서 `_high` 부분 복사
- GitHub Secrets: `ORACLE_DB_DSN`

### 3. ORACLE_WALLET_BASE64
- Wallet.zip 파일을 Base64로 인코딩한 값
- GitHub Secrets: `ORACLE_WALLET_BASE64`

---

## 🔧 빠른 설정 (GitHub Secrets 값 사용)

GitHub Actions가 이미 동작하고 있다면, Secrets에 값이 저장되어 있습니다.

**문제**: GitHub Secrets는 보안상 직접 볼 수 없습니다.

**해결책**:
1. Oracle Cloud Console에서 다시 Wallet 다운로드
2. 아래 스크립트로 `.env` 자동 생성

```bash
cd /Users/peterscp/Documents/crypto_trading

# Wallet.zip을 이 폴더에 다운로드 후
./setup_oracle_env.sh Wallet_xxxxx.zip YourAdminPassword
```

---

## ✅ 설정 완료 확인

`.env` 파일 형식:

```bash
USE_ORACLE_DB=true
ORACLE_DB_USER=ADMIN
ORACLE_DB_PASSWORD=YourPassword123!
ORACLE_DB_DSN=(description= (retry_count=20)...)
ORACLE_WALLET_BASE64=UEsDBBQAAAA...매우긴문자열...==
```

---

## 🚀 배포

```bash
git add .env
git commit -m "Enable Oracle Cloud DB"
git push origin main
```
