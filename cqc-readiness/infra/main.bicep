/*
  cqc-readiness — Azure Infrastructure
  Provisions:
    - App Service Plan (B1, Linux)
    - App Service (Python 3.12)
    - PostgreSQL Flexible Server (Burstable B1ms)
    - Key Vault with Managed Identity access
    - Application Insights + Log Analytics workspace
*/

@description('Base name used for all resource names (e.g. cqcreadiness)')
param baseName string = 'cqcreadiness'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('PostgreSQL admin username')
param dbAdminUser string = 'cqcadmin'

@description('PostgreSQL admin password')
@secure()
param dbAdminPassword string

@description('Microsoft Graph tenant ID')
@secure()
param graphTenantId string

@description('Microsoft Graph client ID')
@secure()
param graphClientId string

@description('Microsoft Graph client secret')
@secure()
param graphClientSecret string

@description('Sender email address registered in Graph')
param graphSenderEmail string

@description('Care Quality Manager alert email')
param cqmAlertEmail string

@description('Admin username for the web dashboard')
param adminUsername string = 'admin'

@description('Bcrypt hash of the admin password')
@secure()
param adminPasswordHash string

// ── Variables ────────────────────────────────────────────────────────────────

var appServicePlanName   = '${baseName}-plan'
var appServiceName       = '${baseName}-app'
var postgresServerName   = '${baseName}-pg'
var keyVaultName         = '${baseName}-kv'
var logAnalyticsName     = '${baseName}-logs'
var appInsightsName      = '${baseName}-ai'
var dbName               = 'cqc_readiness'
var appBaseUrl           = 'https://${appServiceName}.azurewebsites.net'

// ── Log Analytics Workspace ───────────────────────────────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ── Application Insights ──────────────────────────────────────────────────────

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ── App Service Plan ──────────────────────────────────────────────────────────

resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true  // Required for Linux
  }
}

// ── App Service ───────────────────────────────────────────────────────────────

resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name: appServiceName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'uvicorn app.main:app --host 0.0.0.0 --port 8000'
      appSettings: [
        {
          name: 'KEY_VAULT_URL'
          value: keyVault.properties.vaultUri
        }
        {
          name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
          value: appInsights.properties.InstrumentationKey
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
      ]
      alwaysOn: true
      httpLoggingEnabled: true
      detailedErrorLoggingEnabled: true
    }
    httpsOnly: true
  }
}

// ── PostgreSQL Flexible Server ────────────────────────────────────────────────

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-03-01-preview' = {
  name: postgresServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: dbAdminUser
    administratorLoginPassword: dbAdminPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-03-01-preview' = {
  parent: postgresServer
  name: dbName
  properties: {
    charset: 'utf8'
    collation: 'en_US.utf8'
  }
}

// Allow Azure services to connect
resource postgresFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-03-01-preview' = {
  parent: postgresServer
  name: 'AllowAllAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ── Key Vault ─────────────────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
    enableSoftDelete: true
  }
}

// Store all secrets in Key Vault
resource secretDbUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'DATABASE-URL'
  properties: {
    value: 'postgresql+asyncpg://${dbAdminUser}:${dbAdminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/${dbName}'
  }
}

resource secretGraphTenantId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'GRAPH-TENANT-ID'
  properties: { value: graphTenantId }
}

resource secretGraphClientId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'GRAPH-CLIENT-ID'
  properties: { value: graphClientId }
}

resource secretGraphClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'GRAPH-CLIENT-SECRET'
  properties: { value: graphClientSecret }
}

resource secretGraphSenderEmail 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'GRAPH-SENDER-EMAIL'
  properties: { value: graphSenderEmail }
}

resource secretCqmAlertEmail 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'CQM-ALERT-EMAIL'
  properties: { value: cqmAlertEmail }
}

resource secretAppBaseUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'APP-BASE-URL'
  properties: { value: appBaseUrl }
}

resource secretAdminUsername 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ADMIN-USERNAME'
  properties: { value: adminUsername }
}

resource secretAdminPasswordHash 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ADMIN-PASSWORD-HASH'
  properties: { value: adminPasswordHash }
}

// ── RBAC: App Service Managed Identity → Key Vault ────────────────────────────

// Key Vault Secrets User role
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, appService.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output keyVaultUri string = keyVault.properties.vaultUri
output postgresHost string = postgresServer.properties.fullyQualifiedDomainName
output appInsightsConnectionString string = appInsights.properties.ConnectionString
