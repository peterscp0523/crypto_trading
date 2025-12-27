# GitHub Secrets 설정 가이드
# 다음 값들을 GitHub Repository Settings > Secrets and variables > Actions에 추가하세요

## Database 설정

ORACLE_DB_USER
${db_user}

ORACLE_DB_PASSWORD
${db_password}

ORACLE_DB_DSN
${db_dsn}

USE_ORACLE_DB
${use_oracle_db}

## Wallet (Base64 인코딩)

ORACLE_WALLET_BASE64
${wallet_base64}

## Connection String (참고용)
# ${connection_string}

---

📝 GitHub Secrets 추가 방법:

1. GitHub 저장소로 이동
2. Settings > Secrets and variables > Actions 클릭
3. "New repository secret" 클릭
4. 위의 각 항목을 Name과 Value에 입력하여 추가

⚠️ 주의: ORACLE_WALLET_BASE64는 매우 긴 문자열입니다. 전체를 복사하여 붙여넣으세요.
