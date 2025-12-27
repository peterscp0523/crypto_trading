terraform {
  required_version = ">= 1.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "oci" {
  # 환경변수 또는 ~/.oci/config 파일에서 자동으로 읽음
  # OCI_TENANCY_OCID
  # OCI_USER_OCID
  # OCI_FINGERPRINT
  # OCI_PRIVATE_KEY_PATH
  # OCI_REGION

  region = var.region
}
