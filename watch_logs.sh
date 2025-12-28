#!/bin/bash
# 봇 로그 실시간 모니터링 스크립트

echo "🔍 봇 로그 실시간 모니터링 시작..."
echo "종료하려면 Ctrl+C를 누르세요"
echo ""

# SSH 키 파일 경로
SSH_KEY="$HOME/.ssh/github_actions_oracle"
VM_HOST="140.245.69.95"
VM_USER="opc"

# SSH로 접속해서 docker logs -f 실행
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$VM_USER@$VM_HOST" \
  "docker logs -f --tail 50 crypto-trading-bot"
