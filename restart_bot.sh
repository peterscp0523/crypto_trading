#!/bin/bash
# 봇 재시작 스크립트

echo "기존 봇 종료 중..."
pkill -f "python.*run_multi_coin.py"
sleep 2

echo "새 봇 시작..."
nohup python3 run_multi_coin.py > bot.log 2>&1 &

echo "봇 시작됨 (PID: $!)"
echo "로그: tail -f bot.log"
