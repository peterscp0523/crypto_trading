#!/bin/bash
# Oracle Cloud DB .env 자동 설정 스크립트

if [ $# -ne 2 ]; then
    echo "사용법: $0 <Wallet.zip> <ADMIN 비밀번호>"
    echo "예시: $0 Wallet_cryptodb.zip MyPassword123!"
    exit 1
fi

WALLET_FILE=$1
ADMIN_PASSWORD=$2

if [ ! -f "$WALLET_FILE" ]; then
    echo "❌ Wallet 파일을 찾을 수 없습니다: $WALLET_FILE"
    exit 1
fi

echo "🔧 Oracle Cloud DB 설정 시작..."
echo ""

# 1. Wallet Base64 인코딩
echo "📦 Wallet Base64 인코딩 중..."
WALLET_BASE64=$(base64 -i "$WALLET_FILE" | tr -d '\n')
echo "✅ Base64 인코딩 완료 (${#WALLET_BASE64} bytes)"

# 2. DSN 추출
echo "📄 DSN 추출 중..."
TEMP_DIR=$(mktemp -d)
unzip -q "$WALLET_FILE" -d "$TEMP_DIR"

if [ ! -f "$TEMP_DIR/tnsnames.ora" ]; then
    echo "❌ tnsnames.ora 파일을 찾을 수 없습니다"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# _high connection string 추출
DSN=$(grep -A 10 "_high =" "$TEMP_DIR/tnsnames.ora" | grep -v "^#" | tr -d '\n' | sed 's/.*= //')

if [ -z "$DSN" ]; then
    echo "❌ DSN 추출 실패"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "✅ DSN 추출 완료"

# 임시 디렉토리 삭제
rm -rf "$TEMP_DIR"

# 3. .env 파일 업데이트
echo "📝 .env 파일 업데이트 중..."

# 기존 .env 백업
if [ -f .env ]; then
    cp .env .env.backup
    echo "📋 기존 .env를 .env.backup으로 백업했습니다"
fi

# Oracle DB 설정 부분만 업데이트
if [ -f .env ]; then
    # Oracle 설정 제거
    sed -i.tmp '/^USE_ORACLE_DB=/d' .env
    sed -i.tmp '/^ORACLE_DB_USER=/d' .env
    sed -i.tmp '/^ORACLE_DB_PASSWORD=/d' .env
    sed -i.tmp '/^ORACLE_DB_DSN=/d' .env
    sed -i.tmp '/^ORACLE_WALLET_BASE64=/d' .env
    sed -i.tmp '/^USE_DB=/d' .env
    sed -i.tmp '/# 데이터베이스 설정/d' .env
    rm .env.tmp
fi

# 새 Oracle 설정 추가
cat >> .env << ENVEOF

# 데이터베이스 설정 (Oracle Cloud DB 사용)
USE_ORACLE_DB=true
ORACLE_DB_USER=ADMIN
ORACLE_DB_PASSWORD=$ADMIN_PASSWORD
ORACLE_DB_DSN=$DSN
ORACLE_WALLET_BASE64=$WALLET_BASE64
ENVEOF

echo "✅ .env 파일 업데이트 완료"
echo ""

# 4. 확인
echo "================================"
echo "✅ Oracle Cloud DB 설정 완료!"
echo "================================"
echo ""
echo "📋 설정 내용:"
echo "  • USE_ORACLE_DB: true"
echo "  • ORACLE_DB_USER: ADMIN"
echo "  • ORACLE_DB_PASSWORD: ***"
echo "  • ORACLE_DB_DSN: ${DSN:0:50}..."
echo "  • ORACLE_WALLET_BASE64: ${#WALLET_BASE64} bytes"
echo ""
echo "🚀 다음 단계:"
echo "  1. git add .env"
echo "  2. git commit -m 'Enable Oracle Cloud DB'"
echo "  3. git push origin main"
echo ""
echo "  또는 수동 배포:"
echo "  ./deploy_phase1.sh"
echo ""
