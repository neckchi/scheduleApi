resource "aws_secretsmanager_secret" "this" {
  description = "Configuration for p2p-schedule-api-of-carriers"
  name        = "${var.environment}/p2p-schedule-api-of-carriers"
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id = aws_secretsmanager_secret.this.id
  secret_string = jsonencode({
    CMA_URL            = data.sops_file.sops-secret.data["CMA_URL"]
    CMA_TOKEN          = data.sops_file.sops-secret.data["CMA_TOKEN"]
    SUDU_URL           = data.sops_file.sops-secret.data["SUDU_URL"]
    SUDU_TOKEN         = data.sops_file.sops-secret.data["SUDU_TOKEN"]
    HMM_URL            = data.sops_file.sops-secret.data["HMM_URL"]
    HMM_TOKEN          = data.sops_file.sops-secret.data["HMM_TOKEN"]
    IQAX_URL           = data.sops_file.sops-secret.data["IQAX_URL"]
    IQAX_TOKEN         = data.sops_file.sops-secret.data["IQAX_TOKEN"]
    MAEU_P2P           = data.sops_file.sops-secret.data["MAEU_P2P"]
    MAEU_LOCATION      = data.sops_file.sops-secret.data["MAEU_LOCATION"]
    MAEU_CUTOFF        = data.sops_file.sops-secret.data["MAEU_CUTOFF"]
    MAEU_TOKEN         = data.sops_file.sops-secret.data["MAEU_TOKEN"]
    MAEU_TOKEN2        = data.sops_file.sops-secret.data["MAEU_TOKEN2"]
    ONEY_URL           = data.sops_file.sops-secret.data["ONEY_URL"]
    ONEY_TURL          = data.sops_file.sops-secret.data["ONEY_TURL"]
    ONEY_TOKEN         = data.sops_file.sops-secret.data["ONEY_TOKEN"]
    ONEY_AUTH          = data.sops_file.sops-secret.data["ONEY_AUTH"]
    ZIM_URL            = data.sops_file.sops-secret.data["ZIM_URL"]
    ZIM_TURL           = data.sops_file.sops-secret.data["ZIM_TURL"]
    ZIM_TOKEN          = data.sops_file.sops-secret.data["ZIM_TOKEN"]
    ZIM_CLIENT         = data.sops_file.sops-secret.data["ZIM_CLIENT"]
    ZIM_SECRET         = data.sops_file.sops-secret.data["ZIM_SECRET"]
    MSCU_URL           = data.sops_file.sops-secret.data["MSCU_URL"]
    MSCU_AUD           = data.sops_file.sops-secret.data["MSCU_AUD"]
    MSCU_OAUTH         = data.sops_file.sops-secret.data["MSCU_OAUTH"]
    MSCU_CLIENT        = data.sops_file.sops-secret.data["MSCU_CLIENT"]
    MSCU_THUMBPRINT    = data.sops_file.sops-secret.data["MSCU_THUMBPRINT"]
    MSCU_SCOPE         = data.sops_file.sops-secret.data["MSCU_SCOPE"]
    MSCU_RSA_KEY       = data.sops_file.sops-secret.data["MSCU_RSA_KEY"]
    HLCU_URL           = data.sops_file.sops-secret.data["HLCU_URL"]
    HLCU_CLIENT_ID     = data.sops_file.sops-secret.data["HLCU_CLIENT_ID"]
    HLCU_CLIENT_SECRET = data.sops_file.sops-secret.data["HLCU_CLIENT_SECRET"]
    HLCU_URL           = data.sops_file.sops-secret.data["HLCU_URL"]
    BASIC_USER         = data.sops_file.sops-secret.data["BASIC_USER"]
    BASIC_PW           = data.sops_file.sops-secret.data["BASIC_PW"]
    REDIS_HOST         = data.sops_file.sops-secret.data["REDIS_HOST"]
    REDIS_PORT         = data.sops_file.sops-secret.data["REDIS_PORT"]
    REDIS_DB           = data.sops_file.sops-secret.data["REDIS_DB"]
    REDIS_USER         = data.sops_file.sops-secret.data["REDIS_USER"]
    REDIS_PW           = data.sops_file.sops-secret.data["REDIS_PW"]
  })

  depends_on = [aws_secretsmanager_secret.this]
}