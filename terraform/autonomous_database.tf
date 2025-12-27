resource "oci_database_autonomous_database" "crypto_trading_db" {
  compartment_id = var.compartment_id
  db_name        = var.db_name
  display_name   = var.db_display_name

  # Always Free Tier 설정
  is_free_tier                     = var.is_free_tier
  cpu_core_count                   = var.cpu_core_count
  data_storage_size_in_tbs         = var.data_storage_size_in_tbs

  # Autonomous Database 타입
  db_workload                      = "OLTP"  # Transaction Processing
  is_auto_scaling_enabled          = false   # Always Free는 auto-scaling 불가

  # 관리자 비밀번호
  admin_password                   = var.db_admin_password

  # 라이센스 타입
  license_model                    = "LICENSE_INCLUDED"

  # 네트워크 접근 (모든 IP 허용 - 실제 운영 시 제한 권장)
  whitelisted_ips                  = ["0.0.0.0/0"]
  is_mtls_connection_required      = true  # mTLS 필수 (Wallet 사용)

  # 자동 백업 (Always Free는 자동 백업 제공)
  is_auto_scaling_for_storage_enabled = false

  # 태그
  freeform_tags = {
    "Project"     = "CryptoTrading"
    "Environment" = "Production"
    "ManagedBy"   = "Terraform"
  }
}

# Wallet 다운로드
resource "oci_database_autonomous_database_wallet" "crypto_trading_wallet" {
  autonomous_database_id = oci_database_autonomous_database.crypto_trading_db.id
  password               = var.db_wallet_password

  # Wallet 타입 (Instance Wallet)
  generate_type = "SINGLE"

  # base64로 인코딩된 wallet을 파일로 저장
  base64_encode_content = true
}

# Wallet을 로컬 파일로 저장
resource "local_file" "wallet_zip" {
  content_base64 = oci_database_autonomous_database_wallet.crypto_trading_wallet.content
  filename       = "${path.module}/outputs/Wallet_${var.db_name}.zip"

  depends_on = [
    oci_database_autonomous_database_wallet.crypto_trading_wallet
  ]
}

# Wallet을 압축 해제할 디렉토리 생성
resource "null_resource" "extract_wallet" {
  provisioner "local-exec" {
    command = <<-EOT
      mkdir -p ${path.module}/outputs/wallet
      unzip -o ${path.module}/outputs/Wallet_${var.db_name}.zip -d ${path.module}/outputs/wallet
    EOT
  }

  depends_on = [
    local_file.wallet_zip
  ]
}

# GitHub Secrets 업데이트를 위한 출력 파일 생성
resource "local_file" "github_secrets" {
  content = templatefile("${path.module}/templates/github_secrets.tpl", {
    db_user            = "ADMIN"
    db_password        = var.db_admin_password
    db_dsn             = "${var.db_name}_medium"
    wallet_base64      = oci_database_autonomous_database_wallet.crypto_trading_wallet.content
    use_oracle_db      = "true"
    connection_string  = oci_database_autonomous_database.crypto_trading_db.connection_strings[0].profiles[1].value
  })

  filename = "${path.module}/outputs/github_secrets.txt"

  depends_on = [
    oci_database_autonomous_database.crypto_trading_db,
    oci_database_autonomous_database_wallet.crypto_trading_wallet
  ]
}
