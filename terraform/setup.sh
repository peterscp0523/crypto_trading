#!/bin/bash

# Oracle Cloud 자동 설정 스크립트
# Terraform을 사용하여 Autonomous Database를 생성합니다

set -e

echo "======================================"
echo "🚀 Oracle Cloud 자동 설정"
echo "======================================"
echo ""

# Terraform 설치 확인
if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform이 설치되지 않았습니다."
    echo ""
    echo "설치 방법:"
    echo "  macOS:  brew install terraform"
    echo "  Linux:  https://www.terraform.io/downloads"
    exit 1
fi

echo "✅ Terraform 버전: $(terraform version | head -1)"

# OCI CLI 설치 확인
if ! command -v oci &> /dev/null; then
    echo "❌ OCI CLI가 설치되지 않았습니다."
    echo ""
    echo "설치 방법:"
    echo "  macOS:  brew install oci-cli"
    echo "  Linux:  bash -c \"\$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)\""
    echo ""
    echo "설치 후 실행: oci setup config"
    exit 1
fi

echo "✅ OCI CLI 설치됨"

# OCI 설정 확인
if [ ! -f ~/.oci/config ]; then
    echo "❌ OCI 설정이 없습니다."
    echo ""
    echo "다음 명령으로 설정하세요:"
    echo "  oci setup config"
    exit 1
fi

echo "✅ OCI 설정 완료"
echo ""

# terraform.tfvars 확인
if [ ! -f terraform.tfvars ]; then
    echo "📝 terraform.tfvars 파일 생성 중..."
    cp terraform.tfvars.example terraform.tfvars

    echo ""
    echo "⚠️  terraform.tfvars 파일을 편집해야 합니다!"
    echo ""
    echo "필수 설정:"
    echo "  1. compartment_id: OCI Console > Identity > Compartments에서 확인"
    echo "  2. db_admin_password: 강력한 비밀번호 (12자 이상)"
    echo "  3. db_wallet_password: Wallet 비밀번호"
    echo ""
    read -p "지금 편집하시겠습니까? (y/n) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ${EDITOR:-vim} terraform.tfvars
    else
        echo ""
        echo "terraform.tfvars를 수동으로 편집한 후 다시 실행하세요:"
        echo "  vim terraform.tfvars"
        echo "  ./setup.sh"
        exit 0
    fi
fi

echo "✅ terraform.tfvars 존재"
echo ""

# Compartment ID 확인
COMPARTMENT_ID=$(grep '^compartment_id' terraform.tfvars | cut -d'"' -f2)
if [[ "$COMPARTMENT_ID" == "ocid1.tenancy.oc1..aaaaaaaxxxxxxxxx"* ]]; then
    echo "❌ compartment_id가 예시 값입니다."
    echo "   terraform.tfvars를 편집하여 실제 Compartment OCID를 입력하세요."
    exit 1
fi

echo "✅ Compartment ID 설정됨"
echo ""

# Terraform 초기화
echo "📦 Terraform 초기화 중..."
terraform init
echo ""

# Terraform Plan
echo "📋 실행 계획 확인 중..."
terraform plan
echo ""

# 확인
echo "======================================"
echo "⚠️  주의사항"
echo "======================================"
echo ""
echo "다음 작업을 수행합니다:"
echo "  • Oracle Autonomous Database 생성"
echo "  • Database Wallet 다운로드"
echo "  • GitHub Secrets 정보 생성"
echo ""
echo "소요 시간: 약 5-10분"
echo "비용: Always Free Tier (무료)"
echo ""
read -p "계속하시겠습니까? (yes/no) " -r
echo ""

if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "취소되었습니다."
    exit 0
fi

# Terraform Apply
echo ""
echo "🚀 인프라 생성 중..."
terraform apply -auto-approve

# 성공 메시지
echo ""
echo "======================================"
echo "✅ 생성 완료!"
echo "======================================"
echo ""

# 다음 단계 출력
terraform output -raw next_steps

echo ""
echo "🎉 완료!"
echo ""
