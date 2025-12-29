#!/bin/bash
"""
업비트 20/200 SMA 자동매매 봇 시작 스크립트
Oracle Cloud에서 실행
"""

# 환경변수 로드
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "❌ .env 파일이 없습니다. .env.example을 참고하여 생성하세요."
    exit 1
fi

# Python 가상환경 활성화 (옵션)
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 봇 모드 확인
MODE=${1:-dry}  # 기본값: dry (시뮬레이션)
TIMEFRAME=${2:-1}  # 기본값: 1분봉

echo "=================================================="
echo "🤖 업비트 20/200 SMA 자동매매 봇"
echo "=================================================="
echo "모드: $MODE"
echo "타임프레임: ${TIMEFRAME}분"
echo "=================================================="
echo ""

# 로그 디렉토리 생성
mkdir -p logs

# 현재 시간
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 봇 시작
if [ "$MODE" = "live" ]; then
    echo "⚠️ 실거래 모드로 시작합니다!"
    echo "3초 후 시작..."
    sleep 3
    python3 upbit_20_200_bot.py live $TIMEFRAME 2>&1 | tee logs/bot_live_${TIMESTAMP}.log
else
    echo "🟢 시뮬레이션 모드로 시작합니다"
    python3 upbit_20_200_bot.py $TIMEFRAME 2>&1 | tee logs/bot_dry_${TIMESTAMP}.log
fi
