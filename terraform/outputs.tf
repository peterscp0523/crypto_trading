output "autonomous_database_id" {
  description = "Autonomous Database OCID"
  value       = oci_database_autonomous_database.crypto_trading_db.id
}

output "autonomous_database_state" {
  description = "Autonomous Database 상태"
  value       = oci_database_autonomous_database.crypto_trading_db.state
}

output "connection_strings" {
  description = "Database 연결 문자열"
  value       = oci_database_autonomous_database.crypto_trading_db.connection_strings
  sensitive   = false
}

output "db_name" {
  description = "Database 이름"
  value       = oci_database_autonomous_database.crypto_trading_db.db_name
}

output "service_console_url" {
  description = "Database 서비스 콘솔 URL"
  value       = oci_database_autonomous_database.crypto_trading_db.service_console_url
}

output "wallet_file_path" {
  description = "Wallet 파일 경로"
  value       = local_file.wallet_zip.filename
}

output "wallet_base64" {
  description = "Wallet Base64 (GitHub Secret용)"
  value       = oci_database_autonomous_database_wallet.crypto_trading_wallet.content
  sensitive   = true
}

output "github_secrets_file" {
  description = "GitHub Secrets 설정 파일 경로"
  value       = local_file.github_secrets.filename
}

output "next_steps" {
  description = "다음 단계 안내"
  value = "✅ 데이터베이스 생성 완료! GitHub Secrets 파일을 확인하세요: ${local_file.github_secrets.filename}"
}
