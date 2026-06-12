variable "subscription_id" {
  description = "Subscription do LabDados"
  type        = string
  default     = "66e9297b-9531-4d75-a0e0-004b2f4f8dde"
}

variable "resource_group_name" {
  description = "Resource group existente (compartilhado com o escritorio-servicos)"
  type        = string
  default     = "resgroup"
}

variable "container_app_environment_name" {
  description = "Container Apps Environment existente"
  type        = string
  default     = "labdados-env"
}

variable "acr_name" {
  description = "Azure Container Registry existente"
  type        = string
  default     = "labdadosdevacr"
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

variable "alert_emails" {
  description = "E-mails que recebem os alertas de orçamento"
  type        = list(string)
  default     = ["julio.trecenti@gmail.com"]
}

variable "tags" {
  type = map(string)
  default = {
    project    = "juscraper-mcp"
    owner      = "labdados@fgv.br"
    managed_by = "terraform"
  }
}
