#!/bin/bash
# Phase 1 기관급 개선사항 배포 스크립트

echo "================================"
echo "🚀 Phase 1 배포 시작"
echo "================================"
echo ""

# Oracle VM 접속 정보
VM_HOST="132.226.239.181"
VM_USER="ubuntu"
REMOTE_DIR="/home/ubuntu/crypto_trading"

echo "📦 파일 복사 중..."
scp .env telegram_bot.py upbit_api.py execution_manager.py risk_manager.py \
    market_regime.py requirements.txt Dockerfile \
    ${VM_USER}@${VM_HOST}:${REMOTE_DIR}/

if [ $? -ne 0 ]; then
    echo "❌ 파일 복사 실패"
    exit 1
fi

echo "✅ 파일 복사 완료"
echo ""

echo "🔧 Docker 이미지 빌드 및 재시작..."
ssh ${VM_USER}@${VM_HOST} << 'ENDSSH'
cd /home/ubuntu/crypto_trading

# 기존 컨테이너 중지 및 제거
docker stop crypto-bot 2>/dev/null
docker rm crypto-bot 2>/dev/null

# 새 이미지 빌드
docker build -t crypto-bot .

if [ $? -ne 0 ]; then
    echo "❌ Docker 빌드 실패"
    exit 1
fi

# 컨테이너 실행
docker run -d \
    --name crypto-bot \
    --restart unless-stopped \
    --env-file .env \
    crypto-bot

if [ $? -ne 0 ]; then
    echo "❌ Docker 실행 실패"
    exit 1
fi

echo "✅ 컨테이너 시작 완료"

# 로그 확인
sleep 3
docker logs --tail 20 crypto-bot

ENDSSH

if [ $? -ne 0 ]; then
    echo "❌ 배포 실패"
    exit 1
fi

echo ""
echo "================================"
echo "✅ Phase 1 배포 완료"
echo "================================"
echo ""
echo "📋 새로운 기능:"
echo "  ✅ SQLite 데이터베이스 활성화 (거래 기록)"
echo "  ✅ 지정가 주문 (슬리피지 > 0.1%시)"
echo "  ✅ 슬리피지 추정 (호가창 분석)"
echo "  ✅ VaR (Value at Risk) 계산"
echo "  ✅ 리스크 한도 체크"
echo "  ✅ 실행 품질 추적"
echo ""
echo "💡 텔레그램에서 매수 메시지에 다음 정보가 추가됩니다:"
echo "  • VaR(95%, 1일): 최대 예상 손실"
echo "  • 변동성: 일일 변동성"
echo "  • 실행 품질: 슬리피지, 체결 방식"
echo ""
