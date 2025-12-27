# 🚀 자동 배포 가이드

GitHub Actions를 통해 Oracle Cloud로 자동 배포되는 암호화폐 트레이딩 봇입니다.

## 📋 사전 준비

### 1. Oracle Cloud 인스턴스 준비

1. Oracle Cloud 계정 생성 및 로그인
2. Compute Instance 생성 (Ubuntu 22.04 권장)
3. SSH 키 생성 및 등록
4. Docker 설치:

```bash
# Oracle Cloud 인스턴스에 접속 후
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
```

### 2. GitHub Repository 설정

1. GitHub에 새 repository 생성
2. Settings → Secrets and variables → Actions로 이동
3. 다음 Secrets 추가:

#### 필수 Secrets:

| Secret Name | 설명 | 예시 |
|------------|------|------|
| `ORACLE_HOST` | Oracle Cloud 인스턴스 IP | `123.456.789.012` |
| `ORACLE_USERNAME` | SSH 사용자명 | `ubuntu` |
| `ORACLE_SSH_KEY` | SSH Private Key | (전체 키 내용) |
| `UPBIT_ACCESS_KEY` | 업비트 Access Key | `wvDGZnnN...` |
| `UPBIT_SECRET_KEY` | 업비트 Secret Key | `Wk2pZr2b...` |
| `TELEGRAM_TOKEN` | 텔레그램 봇 토큰 | `8074867565:AAE...` |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID | `8581550790` |
| `MARKET` | 거래 마켓 | `KRW-ETH` |
| `CHECK_INTERVAL` | 체크 간격 (초) | `300` |

#### 선택 Secrets (Docker Hub 사용 시):

| Secret Name | 설명 |
|------------|------|
| `DOCKERHUB_USERNAME` | Docker Hub 사용자명 |
| `DOCKERHUB_TOKEN` | Docker Hub 액세스 토큰 |

### 3. SSH 키 생성 및 등록

```bash
# 로컬에서 SSH 키 생성
ssh-keygen -t rsa -b 4096 -C "github-actions"

# Public Key를 Oracle Cloud 인스턴스에 추가
cat ~/.ssh/id_rsa.pub
# → Oracle Cloud 인스턴스의 ~/.ssh/authorized_keys에 추가

# Private Key를 GitHub Secrets에 추가
cat ~/.ssh/id_rsa
# → GitHub Secrets의 ORACLE_SSH_KEY에 추가
```

## 🔄 배포 프로세스

### 자동 배포 (권장)

코드 변경 후 GitHub에 푸시하면 자동으로 배포됩니다:

```bash
git add .
git commit -m "Update trading strategy"
git push origin main
```

배포 과정:
1. ✅ GitHub Actions 워크플로우 자동 실행
2. 🐳 Docker 이미지 빌드
3. 📦 Oracle Cloud로 이미지 전송
4. 🚀 컨테이너 재시작
5. 📊 로그 확인

### 수동 배포

GitHub Actions 탭에서 "Deploy to Oracle Cloud" 워크플로우 선택 후 "Run workflow" 클릭

## 🔍 배포 확인

### 1. GitHub Actions 로그 확인

GitHub Repository → Actions 탭에서 워크플로우 실행 상태 확인

### 2. Oracle Cloud에서 직접 확인

```bash
# SSH로 Oracle Cloud 접속
ssh ubuntu@YOUR_ORACLE_IP

# 컨테이너 상태 확인
docker ps -a

# 실시간 로그 확인
docker logs -f crypto-trading-bot

# 최근 로그 50줄 확인
docker logs --tail 50 crypto-trading-bot
```

### 3. 텔레그램으로 확인

봇이 정상 작동하면 텔레그램으로 시작 메시지가 옵니다.

## 🛠️ 문제 해결

### 배포 실패 시

1. **GitHub Actions 로그 확인**
   - Actions 탭에서 실패한 단계 확인
   - 에러 메시지 분석

2. **SSH 연결 문제**
   ```bash
   # SSH 키 권한 확인
   chmod 600 ~/.ssh/id_rsa

   # 수동 SSH 테스트
   ssh -i ~/.ssh/id_rsa ubuntu@YOUR_ORACLE_IP
   ```

3. **Docker 문제**
   ```bash
   # Docker 상태 확인
   sudo systemctl status docker

   # Docker 재시작
   sudo systemctl restart docker
   ```

### 컨테이너 재시작

```bash
# 컨테이너 재시작
docker restart crypto-trading-bot

# 컨테이너 중지
docker stop crypto-trading-bot

# 컨테이너 삭제 후 재생성
docker rm -f crypto-trading-bot
# (GitHub Actions가 자동으로 재생성합니다)
```

### 수동 실행

```bash
# 최신 코드 다운로드
git clone https://github.com/YOUR_USERNAME/crypto_trading.git
cd crypto_trading

# .env 파일 생성
cat > .env << EOF
UPBIT_ACCESS_KEY=your_key
UPBIT_SECRET_KEY=your_secret
TELEGRAM_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
MARKET=KRW-ETH
CHECK_INTERVAL=300
EOF

# Docker 이미지 빌드
docker build -t crypto-trading-bot:latest .

# 컨테이너 실행
docker run -d \
  --name crypto-trading-bot \
  --restart unless-stopped \
  --env-file .env \
  crypto-trading-bot:latest
```

## 📊 모니터링

### 로그 확인

```bash
# 실시간 로그
docker logs -f crypto-trading-bot

# 최근 100줄
docker logs --tail 100 crypto-trading-bot

# 타임스탬프 포함
docker logs -t crypto-trading-bot
```

### 리소스 사용량

```bash
# CPU/메모리 사용량
docker stats crypto-trading-bot

# 전체 상태
docker inspect crypto-trading-bot
```

## 🔐 보안 주의사항

1. ✅ `.env` 파일은 절대 Git에 커밋하지 마세요
2. ✅ GitHub Secrets를 사용해 민감 정보 관리
3. ✅ SSH 키는 안전하게 보관
4. ✅ Oracle Cloud 방화벽 설정 (필요한 포트만 열기)
5. ✅ 정기적으로 로그 모니터링

## 📝 전략 설정

현재 설정:
- **익절**: +3%
- **손절**: -2%
- **트레일링 스톱**: 최고점 대비 -1.5%
- **매수 조건**: 다중 시간대 추세 분석 (1H + 4H)
- **신호 타임프레임**: 15분봉

## 🚨 긴급 중지

```bash
# SSH 접속 후
docker stop crypto-trading-bot

# 또는 GitHub Actions에서 재배포하여 업데이트된 코드 실행
```

## 📞 지원

문제가 있으면 GitHub Issues에 제보해주세요.
