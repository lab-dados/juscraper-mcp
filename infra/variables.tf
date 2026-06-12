# Os valores reais da infra do LabDados (subscription, resource group, ACR, etc.)
# NÃO vivem aqui — este é um repo público. Eles ficam em `terraform.tfvars`
# (gitignored, gerado localmente por quem roda o terraform). Os defaults abaixo
# são só os não-sensíveis (nome do app, orçamento, tags).

variable "subscription_id" {
  description = "Subscription onde os recursos vivem (definir em terraform.tfvars)"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group existente reaproveitado (definir em terraform.tfvars)"
  type        = string
}

variable "container_app_environment_name" {
  description = "Container Apps Environment existente (definir em terraform.tfvars)"
  type        = string
}

variable "acr_name" {
  description = "Azure Container Registry existente (definir em terraform.tfvars)"
  type        = string
}

variable "alert_emails" {
  description = "E-mails que recebem os alertas de orçamento (definir em terraform.tfvars)"
  type        = list(string)
}

variable "app_name" {
  description = "Nome do Container App e da imagem"
  type        = string
  default     = "juscraper-mcp"
}

variable "budget_mensal" {
  description = "Teto mensal de custo do app, na moeda de cobrança da assinatura (BRL)"
  type        = number
  default     = 200
}

variable "budget_start_date" {
  description = "Início do período do budget — deve ser o dia 1º de um mês, em UTC"
  type        = string
  default     = "2026-06-01T00:00:00Z"
}

variable "tags" {
  type = map(string)
  default = {
    project    = "juscraper-mcp"
    owner      = "labdados@fgv.br"
    managed_by = "terraform"
  }
}
