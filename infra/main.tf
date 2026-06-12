# Container App do juscraper-mcp, deployado DENTRO da infra existente do
# LabDados (resource group, Container Apps Environment e ACR do
# escritorio-servicos) para não criar custo fixo novo. Recursos criados aqui:
# identidade, role de pull no ACR, o container app e o alerta de orçamento.
#
# Decisões de custo (orçamento: R$ 200/mês):
# - min_replicas = 0 (scale-to-zero): MCP streamable HTTP é stateless, então
#   cold start de alguns segundos é aceitável e o custo em idle é zero.
# - max_replicas = 1 e 0.25 vCPU / 0.5 Gi: mesmo no pior caso (réplica ativa
#   24/7 o mês inteiro) o custo fica em torno de R$ 100-120/mês, abaixo do teto.
# - Budget alert em 50%/80%/100% de R$ 200, filtrado para este app.

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

data "azurerm_resource_group" "shared" {
  name = var.resource_group_name
}

data "azurerm_container_app_environment" "shared" {
  name                = var.container_app_environment_name
  resource_group_name = data.azurerm_resource_group.shared.name
}

data "azurerm_container_registry" "shared" {
  name                = var.acr_name
  resource_group_name = data.azurerm_resource_group.shared.name
}

resource "azurerm_user_assigned_identity" "mcp" {
  name                = "${var.app_name}-identity"
  location            = data.azurerm_resource_group.shared.location
  resource_group_name = data.azurerm_resource_group.shared.name
  tags                = var.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = data.azurerm_container_registry.shared.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.mcp.principal_id
}

resource "azurerm_container_app" "mcp" {
  name                         = var.app_name
  container_app_environment_id = data.azurerm_container_app_environment.shared.id
  resource_group_name          = data.azurerm_resource_group.shared.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.mcp.id]
  }

  registry {
    server   = data.azurerm_container_registry.shared.login_server
    identity = azurerm_user_assigned_identity.mcp.id
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = var.app_name
      image  = "${data.azurerm_container_registry.shared.login_server}/${var.app_name}:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "JUSMCP_MAX_PAGINAS"
        value = "5"
      }
      env {
        name  = "JUSMCP_RATE_LIMIT_MAX"
        value = "30"
      }
      env {
        name  = "JUSMCP_MAX_CONCORRENCIA"
        value = "4"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8080
      }
    }

    http_scale_rule {
      name                = "http"
      concurrent_requests = "10"
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  lifecycle {
    # A imagem é atualizada pelo workflow de deploy (az containerapp update);
    # o Terraform não deve reverter para :latest a cada apply.
    ignore_changes = [template[0].container[0].image]
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}

resource "azurerm_consumption_budget_resource_group" "mcp" {
  name              = "${var.app_name}-budget"
  resource_group_id = data.azurerm_resource_group.shared.id
  amount            = var.budget_mensal # na moeda de cobrança da assinatura (BRL)
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  filter {
    dimension {
      name   = "ResourceId"
      values = [azurerm_container_app.mcp.id]
    }
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = var.alert_emails
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = var.alert_emails
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = var.alert_emails
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = var.alert_emails
  }
}
