terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

variable "location" {
  default     = "eastus2"
  description = "Azure region for all resources"
}

variable "project_name" {
  default     = "bmo-agent"
  description = "Project name used in resource naming"
}

variable "foundry_model" {
  default     = "gpt-4.1-nano"
  description = "Model to deploy in Azure AI Foundry"
}

locals {
  prefix = var.project_name
  tags = {
    project     = var.project_name
    environment = "production"
    managed_by  = "terraform"
  }
}

# ─── Resource Group ──────────────────────────────────────────────────────────
resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}-prod"
  location = var.location
  tags     = local.tags
}

# ─── Log Analytics Workspace ─────────────────────────────────────────────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# ─── Application Insights ────────────────────────────────────────────────────
resource "azurerm_application_insights" "main" {
  name                = "appi-${local.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

# ─── Azure Cosmos DB (Free Tier) ─────────────────────────────────────────────
resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-${local.prefix}-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  free_tier_enabled   = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = local.tags
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "${local.prefix}-db"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "users" {
  name                = "users"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/id"]
  throughput          = 400
}

resource "azurerm_cosmosdb_sql_container" "tasks" {
  name                = "tasks"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/user_id"]
  throughput          = 400
}

resource "azurerm_cosmosdb_sql_container" "traces" {
  name                = "traces"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/task_id"]
  throughput          = 400
}

# ─── Azure Key Vault ─────────────────────────────────────────────────────────
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                = "kv-${local.prefix}-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "Set", "List", "Delete"]
  }

  tags = local.tags
}

# ─── Azure AI Services (Foundry) ─────────────────────────────────────────────
resource "azurerm_cognitive_account" "foundry" {
  name                = "ai-${local.prefix}-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "AIServices"
  sku_name            = "S0"

  tags = local.tags
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = var.foundry_model
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.foundry_model
    version = "2025-04-14"
  }

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }
}

# ─── Container Registry ──────────────────────────────────────────────────────
resource "azurerm_container_registry" "main" {
  name                = replace("acr${local.prefix}prod", "-", "")
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.tags
}

# ─── Container Apps Environment ──────────────────────────────────────────────
resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.prefix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# ─── Container App (Backend) ─────────────────────────────────────────────────
resource "azurerm_container_app" "backend" {
  name                         = "${local.prefix}-backend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = 3

    container {
      name   = "backend"
      image  = "${azurerm_container_registry.main.login_server}/backend:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "DATABASE_BACKEND"
        value = "cosmos"
      }
      env {
        name        = "COSMOS_ENDPOINT"
        secret_name = "cosmos-endpoint"
      }
      env {
        name        = "COSMOS_KEY"
        secret_name = "cosmos-key"
      }
      env {
        name  = "COSMOS_DATABASE"
        value = azurerm_cosmosdb_sql_database.main.name
      }
      env {
        name  = "LLM_PROVIDER"
        value = "azure_foundry"
      }
      env {
        name        = "FOUNDRY_ENDPOINT"
        secret_name = "foundry-endpoint"
      }
      env {
        name        = "FOUNDRY_API_KEY"
        secret_name = "foundry-key"
      }
      env {
        name  = "FOUNDRY_MODEL"
        value = var.foundry_model
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-cs"
      }
      env {
        name  = "KEY_VAULT_URL"
        value = azurerm_key_vault.main.vault_uri
      }
      env {
        name  = "AUTH_ENABLED"
        value = "true"
      }
    }
  }

  secret {
    name  = "cosmos-endpoint"
    value = azurerm_cosmosdb_account.main.endpoint
  }
  secret {
    name  = "cosmos-key"
    value = azurerm_cosmosdb_account.main.primary_key
  }
  secret {
    name  = "foundry-endpoint"
    value = azurerm_cognitive_account.foundry.endpoint
  }
  secret {
    name  = "foundry-key"
    value = azurerm_cognitive_account.foundry.primary_access_key
  }
  secret {
    name  = "appinsights-cs"
    value = azurerm_application_insights.main.connection_string
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  tags = local.tags
}

# ─── Static Web App (Frontend) ───────────────────────────────────────────────
resource "azurerm_static_web_app" "frontend" {
  name                = "swa-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = "eastus2"
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.tags
}
