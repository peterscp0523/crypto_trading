# 🔐 GitHub Secrets 업데이트 가이드

## ORACLE_WALLET_BASE64 업데이트 필요

현재 GitHub Secrets의 `ORACLE_WALLET_BASE64` 값이 손상되어 Oracle DB 연결이 실패하고 있습니다.

---

## 📋 업데이트 방법

### 1. Base64 값 복사

로컬에서 생성된 `wallet_base64.txt` 파일 내용을 복사:

```bash
cat wallet_base64.txt | pbcopy  # macOS
# 또는
cat wallet_base64.txt  # 직접 복사
```

**주의**: 
- 줄바꿈 없이 한 줄로 되어있어야 함
- 파일 크기: 약 29KB (29,340자)

---

### 2. GitHub Secrets 페이지 접속

1. GitHub 저장소: https://github.com/peterscp0523/crypto_trading
2. Settings → Secrets and variables → Actions
3. Repository secrets 목록에서 `ORACLE_WALLET_BASE64` 찾기

---

### 3. Secret 업데이트

1. `ORACLE_WALLET_BASE64` 옆의 **Update** 버튼 클릭
2. Value 필드에 복사한 Base64 값 붙여넣기
3. **Update secret** 버튼 클릭

---

### 4. 테스트 배포

Secret 업데이트 후:

```bash
# 더미 커밋으로 재배포 트리거
git commit --allow-empty -m "🔄 Test Oracle DB connection"
git push origin main
```

또는:

1. GitHub → Actions → "Deploy to Oracle Cloud"
2. Run workflow → Run workflow 클릭

---

### 5. 연결 확인

배포 완료 후 로그 확인:

```bash
# Actions 로그에서 확인
# "✅ Oracle Wallet 설정 완료" 
# "✅ 데이터베이스 연동: Oracle Cloud"
# 에러 없이 통과해야 함

# 또는 SSH로 직접 확인
ssh -i ~/.ssh/github_actions_oracle ubuntu@140.245.69.95 \
  "docker logs --tail 20 crypto-trading-bot | grep -i oracle"

# 성공 시:
# ✅ Oracle DB 연결 성공
# ✅ 데이터베이스 연동: Oracle Cloud
```

---

## 🚨 문제 해결

### Base64 디코딩 실패 계속될 경우

1. **Wallet 재다운로드**:
   - Oracle Cloud Console
   - Autonomous Database → DB Connection
   - Download Wallet 클릭
   - 새로운 Wallet.zip 다운로드

2. **Base64 재생성**:
   ```bash
   base64 -i Wallet_NEW.zip | tr -d '\n' > wallet_base64_new.txt
   ```

3. **GitHub Secret 재업데이트**

---

## ✅ 현재 상태

- **로컬 Wallet**: `/tmp/wallet/` (VM에 직접 업로드 완료)
- **현재 DB**: SQLite로 폴백 중
- **다음 배포**: Secret 업데이트 후 Oracle DB 자동 연결

---

## 📊 예상 결과

Secret 업데이트 + 재배포 후:

```
✅ Oracle Wallet 설정 완료
✅ Oracle DB 연결 성공
✅ 데이터베이스 연동: Oracle Cloud
✅ 테이블 생성 완료

🤖 봇 시작 (기본 300초 체크, 동적 조절 활성화)
```

거래 데이터가 Oracle DB에 자동 저장됩니다.
