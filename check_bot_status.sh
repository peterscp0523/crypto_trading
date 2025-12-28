#!/bin/bash
# 봇 상태 확인 스크립트

echo "=== Docker Container Status ==="
ssh -i ~/.ssh/github_actions_oracle -o StrictHostKeyChecking=no opc@140.245.69.95 "docker ps -a | grep crypto-trading-bot"

echo ""
echo "=== Recent Logs (Last 200 lines) ==="
ssh -i ~/.ssh/github_actions_oracle -o StrictHostKeyChecking=no opc@140.245.69.95 "docker logs crypto-trading-bot --tail 200"

echo ""
echo "=== Container Environment Check ==="
ssh -i ~/.ssh/github_actions_oracle -o StrictHostKeyChecking=no opc@140.245.69.95 "docker exec crypto-trading-bot printenv | grep -E '(MARKET|CHECK_INTERVAL|ENABLE_MULTI_COIN)'"
