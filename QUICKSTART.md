# 🚀 빠른 시작 가이드

Oracle Cloud 데이터베이스를 포함한 완전 자동화된 트레이딩 봇 설정

## 📋 필요한 것

1. ✅ Oracle Cloud 계정 (Always Free Tier)
2. ✅ GitHub 계정
3. ✅ 업비트 API 키
4. ✅ 텔레그램 봇 토큰

---

## 🎯 5단계로 완료하기

### 1단계: OCI CLI 설치 및 설정 (5분)

```bash
# macOS
brew install oci-cli

# Linux
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"

# 설정
oci setup config
```

**필요한 정보:**
- Tenancy OCID: OCI Console > Profile > Tenancy
- User OCID: OCI Console > Profile > User Settings
- Region: `ap-seoul-1` (서울)
- API Key: 자동 생성 또는 기존 키 사용

### 2단계: Terraform 설치 (2분)

```bash
# macOS
brew install terraform

# Linux
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/
```

### 3단계: 데이터베이스 생성 (10분)

```bash
cd terraform

# 설정 파일 복사
cp terraform.tfvars.example terraform.tfvars

# 설정 편집
vim terraform.tfvars
```

**terraform.tfvars 필수 입력:**
```hcl
compartment_id = "ocid1.tenancy.oc1..aaa..."  # Tenancy OCID (1단계에서 확인)
db_admin_password  = "YourP@ssw0rd123!"        # 12자+, 대소문자+숫자+특수문자
db_wallet_password = "WalletP@ss456!"          # Wallet 비밀번호
```

**자동 설정 실행:**
```bash
./setup.sh
```

완료되면:
- ✅ Autonomous Database 생성됨
- ✅ Wallet 다운로드됨 (`outputs/Wallet_cryptodb.zip`)
- ✅ 테이블 자동 생성됨
- ✅ GitHub Secrets 파일 생성됨 (`outputs/github_secrets.txt`)

### 4단계: GitHub Secrets 설정 (3분)

```bash
# Secrets 정보 확인
cat outputs/github_secrets.txt
```

**GitHub Repository에 추가:**
1. GitHub 저장소 > Settings > Secrets and variables > Actions
2. "New repository secret" 클릭
3. 다음 항목들을 차례로 추가:

| Name | Value (github_secrets.txt에서 복사) |
|------|--------------------------------------|
| `UPBIT_ACCESS_KEY` | 업비트 API Access Key |
| `UPBIT_SECRET_KEY` | 업비트 API Secret Key |
| `TELEGRAM_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 텔레그램 Chat ID |
| `MARKET` | KRW-ETH (또는 원하는 코인) |
| `CHECK_INTERVAL` | 300 |
| `ORACLE_DB_USER` | ADMIN |
| `ORACLE_DB_PASSWORD` | (terraform.tfvars의 db_admin_password) |
| `ORACLE_DB_DSN` | cryptodb_medium |
| `ORACLE_WALLET_BASE64` | (긴 Base64 문자열 전체 복사) |
| `USE_ORACLE_DB` | true |
| `ORACLE_HOST` | Oracle VM IP 주소 |
| `ORACLE_USERNAME` | ubuntu (또는 VM 사용자명) |
| `ORACLE_SSH_KEY` | SSH Private Key |

### 5단계: 배포 (자동)

```bash
cd ..
git push origin main
```

GitHub Actions가 자동으로:
- 🐳 Docker 이미지 빌드
- 📦 Oracle VM에 배포
- 🚀 트레이딩 봇 시작

---

## ✅ 확인

### 배포 확인
GitHub > Actions 탭에서 워크플로우 진행 상황 확인

### 봇 상태 확인
텔레그램에서 `/status` 명령 전송

### 로그 확인
```bash
ssh -i ~/.ssh/oracle_key ubuntu@<ORACLE_VM_IP>
docker logs -f crypto-trading-bot
```

---

## 🔧 선택적 설정

### 데이터 수집 시작 (1시간마다)

```bash
ssh -i ~/.ssh/oracle_key ubuntu@<ORACLE_VM_IP>

docker run -d \
  --name crypto-data-collector \
  --restart unless-stopped \
  -v /tmp/wallet:/app/wallet \
  -e UPBIT_ACCESS_KEY="..." \
  -e UPBIT_SECRET_KEY="..." \
  -e USE_ORACLE_DB="true" \
  -e ORACLE_DB_USER="ADMIN" \
  -e ORACLE_DB_PASSWORD="..." \
  -e ORACLE_DB_DSN="cryptodb_medium" \
  -e RUN_DATA_COLLECTOR="true" \
  crypto-trading-bot:latest \
  python data_collector.py
```

### 자동 최적화 시작 (7일마다)

```bash
docker run -d \
  --name crypto-auto-optimizer \
  --restart unless-stopped \
  -v /tmp/wallet:/app/wallet \
  -e USE_ORACLE_DB="true" \
  -e ORACLE_DB_USER="ADMIN" \
  -e ORACLE_DB_PASSWORD="..." \
  -e ORACLE_DB_DSN="cryptodb_medium" \
  -e MARKET="KRW-ETH" \
  -e RUN_AUTO_OPTIMIZER="true" \
  crypto-trading-bot:latest \
  python auto_optimizer.py
```

---

## 🎉 완료!

이제 트레이딩 봇이:
- 📊 모멘텀이 강한 코인을 자동으로 선택
- 💾 모든 거래를 Oracle Cloud DB에 기록
- 🔍 7일마다 자동으로 파라미터 최적화
- 📱 텔레그램으로 실시간 알림

---

## 📚 추가 문서

- [terraform/README.md](terraform/README.md) - Terraform 상세 가이드
- [ORACLE_DB_SETUP.md](ORACLE_DB_SETUP.md) - 수동 DB 설정 가이드
- [DATABASE_FEATURES.md](DATABASE_FEATURES.md) - DB 기능 설명
- [DEPLOYMENT.md](DEPLOYMENT.md) - 배포 가이드
- [README.md](README.md) - 프로젝트 전체 문서

---

## ❓ 문제 해결

### Terraform 오류
```bash
cd terraform
terraform destroy  # 리소스 삭제
terraform apply    # 재생성
```

### 배포 실패
- GitHub Actions > 실패한 워크플로우 > 로그 확인
- Secrets 값이 올바른지 확인
- Docker 빌드 로그 확인

### 봇 연결 안 됨
```bash
# 컨테이너 로그 확인
docker logs crypto-trading-bot

# 컨테이너 재시작
docker restart crypto-trading-bot
```

### DB 연결 오류
- Wallet 파일이 올바른지 확인
- TNS_ADMIN 환경변수 확인
- ORACLE_DB_PASSWORD 확인

---

## 💰 비용

**Always Free Tier 사용 시:**
- ✅ 완전 무료
- ✅ 영구 무료 (시간 제한 없음)
- ✅ 신용카드 청구 없음

**주의:**
- 리소스를 Always Free 한도 내에서만 생성
- `is_free_tier = true` 유지
- OCPU/Storage 증가 시 과금 발생

---

## 🆘 도움이 필요하세요?

- 📖 문서를 먼저 확인하세요
- 💬 이슈 등록: GitHub Issues
- 📧 문의: [이메일 주소]

즐거운 트레이딩 되세요! 🚀
