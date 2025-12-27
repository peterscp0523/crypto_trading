# Terraform으로 Oracle Cloud 인프라 자동 생성

이 Terraform 구성은 Oracle Cloud Always Free Tier Autonomous Database를 자동으로 생성하고 설정합니다.

## 🚀 빠른 시작

### 1. 사전 준비

#### Oracle Cloud 계정 설정
1. Oracle Cloud 계정 생성 (https://cloud.oracle.com)
2. Always Free Tier 활성화

#### OCI CLI 설치 및 설정
```bash
# macOS
brew install oci-cli

# Linux
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"

# 설정
oci setup config
```

다음 정보 입력:
- Tenancy OCID (OCI Console > Profile > Tenancy에서 확인)
- User OCID (OCI Console > Profile > User Settings에서 확인)
- Region (예: ap-seoul-1)
- API Key 생성 및 등록

#### Terraform 설치
```bash
# macOS
brew install terraform

# Linux
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/
```

### 2. Terraform 설정

```bash
cd terraform

# 설정 파일 복사
cp terraform.tfvars.example terraform.tfvars

# terraform.tfvars 편집
vim terraform.tfvars
```

**terraform.tfvars 필수 값:**
```hcl
compartment_id = "ocid1.tenancy.oc1..aaa..."  # Tenancy OCID
db_admin_password  = "YourP@ssw0rd123!"        # 12자 이상, 복잡한 비밀번호
db_wallet_password = "WalletP@ss123!"          # Wallet 비밀번호
```

### 3. 인프라 생성

```bash
# 초기화
terraform init

# 계획 확인
terraform plan

# 생성 (약 5-10분 소요)
terraform apply
```

입력 프롬프트에서 `yes` 입력

### 4. 데이터베이스 초기화

```bash
# 테이블 생성
./init_database.sh
```

ADMIN 비밀번호 입력 (terraform.tfvars에 설정한 db_admin_password)

### 5. GitHub Secrets 설정

```bash
# GitHub Secrets 정보 확인
cat outputs/github_secrets.txt
```

출력된 값들을 GitHub Repository Settings > Secrets and variables > Actions에 추가:
- `ORACLE_DB_USER`
- `ORACLE_DB_PASSWORD`
- `ORACLE_DB_DSN`
- `ORACLE_WALLET_BASE64`
- `USE_ORACLE_DB`

### 6. 배포

```bash
cd ..
git add .
git commit -m "Update with Terraform-managed Oracle DB"
git push origin main
```

GitHub Actions가 자동으로 배포를 시작합니다!

---

## 📁 파일 구조

```
terraform/
├── provider.tf              # OCI Provider 설정
├── variables.tf             # 변수 정의
├── autonomous_database.tf   # Autonomous DB 리소스
├── outputs.tf               # 출력 정의
├── init_database.sh         # DB 초기화 스크립트
├── terraform.tfvars.example # 설정 예시
├── .gitignore              # Git 제외 파일
└── outputs/                 # 생성된 파일 (자동)
    ├── Wallet_cryptodb.zip
    ├── wallet/              # 압축 해제된 Wallet
    └── github_secrets.txt   # GitHub Secrets 정보
```

---

## 🔧 주요 명령어

### 상태 확인
```bash
terraform show
```

### 출력 확인
```bash
terraform output
terraform output -json
```

### Wallet Base64 확인
```bash
terraform output -raw wallet_base64
```

### 리소스 삭제 (⚠️ 주의!)
```bash
terraform destroy
```

---

## 🛠️ 트러블슈팅

### OCI 인증 오류
```
Error: missing credentials
```

**해결:**
```bash
# OCI 설정 확인
cat ~/.oci/config

# 재설정
oci setup config
```

### Compartment OCID 찾기
1. OCI Console 로그인
2. Identity > Compartments
3. 루트 compartment의 OCID 복사
4. terraform.tfvars의 `compartment_id`에 붙여넣기

### API Key 등록
1. OCI Console > Profile > User Settings
2. API Keys > Add API Key
3. OCI CLI 설정 시 생성된 공개키 업로드 (~/.oci/oci_api_key_public.pem)

### Terraform State Lock
```
Error: Error acquiring the state lock
```

**해결:**
```bash
terraform force-unlock <LOCK_ID>
```

### Database 비밀번호 요구사항
- 최소 12자
- 대문자 1개 이상
- 소문자 1개 이상
- 숫자 1개 이상
- 특수문자 1개 이상 (!, @, #, $ 등)
- 사용자 이름(ADMIN) 포함 불가

---

## 📊 생성되는 리소스

1. **Autonomous Database**
   - 타입: Transaction Processing (OLTP)
   - OCPU: 1 (Always Free)
   - Storage: 20GB (Always Free)
   - License: License Included

2. **Database Wallet**
   - 타입: Instance Wallet
   - 압축 파일: `outputs/Wallet_cryptodb.zip`
   - 압축 해제: `outputs/wallet/`

3. **Database Tables**
   - candles (캔들 데이터)
   - trades (거래 기록)
   - parameter_history (파라미터 최적화 기록)
   - daily_performance (일일 성과)

---

## 🔒 보안

### Wallet 보안
- ⚠️ Wallet 파일은 민감 정보입니다
- .gitignore에 포함되어 Git에 업로드되지 않음
- 안전한 곳에 백업 보관

### 비밀번호 관리
- terraform.tfvars는 .gitignore에 포함됨
- GitHub Secrets에 안전하게 저장
- 절대 공개 저장소에 커밋하지 마세요

### 네트워크 접근
- 기본 설정: 모든 IP 허용 (0.0.0.0/0)
- 운영 환경에서는 특정 IP만 허용 권장
- autonomous_database.tf의 `whitelisted_ips` 수정

---

## 💰 비용

**Always Free Tier 한도:**
- ✅ Autonomous Database: 2개 (각 1 OCPU, 20GB)
- ✅ 영구 무료 (Always Free)
- ✅ 이 구성은 1개 DB만 생성하므로 완전 무료

**주의:**
- `is_free_tier = false`로 변경 시 과금됩니다!
- OCPU 또는 Storage를 늘리면 과금됩니다!

---

## 📝 다음 단계

1. ✅ Terraform으로 DB 생성
2. ✅ 테이블 초기화
3. ✅ GitHub Secrets 설정
4. ✅ 배포
5. 🔄 데이터 수집 시작 (data_collector.py)
6. 🔍 자동 최적화 시작 (auto_optimizer.py)
7. 🚀 트레이딩 봇 실행

---

## 🆘 도움말

- [Oracle Cloud 문서](https://docs.oracle.com/en-us/iaas/Content/home.htm)
- [Terraform OCI Provider](https://registry.terraform.io/providers/oracle/oci/latest/docs)
- [Autonomous Database 가이드](https://docs.oracle.com/en/cloud/paas/autonomous-database/index.html)

문제가 발생하면 이슈를 등록해주세요!
